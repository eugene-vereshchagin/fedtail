"""Drive the GTK window against the fake API. Skipped without PyGObject + GTK 4 or
without a display (CI runs it under xvfb-run)."""

import os
import tempfile
import time
import unittest
from pathlib import Path

try:
    from fedtail.frontends.gtk.gi_setup import GLib, Gtk
    HAVE_GTK = Gtk.init_check() if hasattr(Gtk, "init_check") else True
    from gi.repository import Gdk
    HAVE_GTK = HAVE_GTK and Gdk.Display.get_default() is not None
except ImportError:
    HAVE_GTK = False

from fedtail import i18n  # noqa: E402
from fedtail.core import auth, config, paths  # noqa: E402
from fedtail.core.app import Core  # noqa: E402

from . import fakes  # noqa: E402
from .fakes import BOB, ME, NEWS, FakeApi, status  # noqa: E402


def pump(until=None, timeout=3.0):
    """Run the main loop until until() is true (or a while, when None)."""
    ctx = GLib.MainContext.default()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        while ctx.pending():
            ctx.iteration(False)
        if until is not None and until():
            return True
        time.sleep(0.01)
    return until is None


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkSmokeTest(unittest.TestCase):
    def setUp(self):
        from fedtail.core.view import View
        from fedtail.frontends.gtk import theme as themes
        from fedtail.frontends.gtk.bridge import Bridge
        from fedtail.frontends.gtk.window import MainWindow
        i18n.setup("ru")
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        tmp = Path(self._tmp.name)
        os.environ["XDG_CONFIG_HOME"] = str(tmp / "xdg")
        FakeApi.world = w = fakes.World()
        mine = w.add(status("010", ME, minute=10, text="мой пост"), home=True)
        w.add(status("011", BOB, minute=11, text="<p>привет <b>жирно</b> &amp; "
                                                  "<a href=\"https://e.test/\">ссылка</a></p>"),
              home=True)
        w.add(status("012", NEWS, minute=12, text="новости"), home=True)
        reply = status("013", BOB, mine["id"], "ME", minute=13, text="коммент")
        reply["spoiler_text"] = "осторожно"
        w.add(reply, home=True, mention=True)
        self.world = w
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False},
                                  "ui": {"start_lane": "home", "arts_mode": False,
                                         "frontend": "gtk", "adwaita": "off"}})
        p = paths.resolve("t", config=str(tmp / "c.toml"), data=str(tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        self.core = Core(cfg, p, api_class=FakeApi)
        self.core._origin_json = lambda url: None
        self.view = View(self.core)
        self.bridge = Bridge(self.view)
        self.errors = []
        self.theme = themes.apply(cfg)
        self.win = MainWindow(None, self.core, self.view, self.bridge, self.theme)
        self.bridge.on_error = self.errors.append  # the window's own goes: catch them
        self.win.present()
        self.win.start()
        self.assertTrue(pump(lambda: self.win.lane_rows, 5), "never connected")
        self.core.poll_once()
        pump(lambda: self._lane("home") and self._lane("home").rows, 5)

    def tearDown(self):
        self.assertEqual(self.errors, [], "a handler failed")
        self.win.quitting = True
        self.win.close()  # as a user would: the lanes stop their queued work
        self.win.destroy()
        pump(timeout=0.1)
        self.core.shutdown()
        self._tmp.cleanup()

    def _lane(self, name):
        return self.win.lane_views.get(name)

    def test_lanes_and_cards(self):
        self.assertIn("home", self.win.lane_rows)
        lane = self._lane("home")
        self.assertGreaterEqual(len(lane.rows), 3)
        texts = [c.post.text for c in lane.rows.values()]
        self.assertTrue(any("привет" in t for t in texts))
        # the reply's warning hides its text in an expander
        reply = next(c for c in lane.rows.values() if c.post.warning)
        self.assertTrue(any(isinstance(w, Gtk.Expander) for w in _walk(reply)))

    def test_seen_posts_get_read(self):
        """The window is active and every post fits: all are seen, so all are read."""
        lane = self._lane("home")
        self.assertTrue(pump(lambda: not any(c.unread for c in lane.rows.values()), 5))
        self.assertFalse(self.view.unread([c.entry for c in lane.rows.values()]))

    def test_all_read_clears_badge(self):
        lane = self._lane("home")
        lane.mark_all_read()
        pump(timeout=0.3)
        self.assertFalse(any(c.unread for c in lane.rows.values()))
        self.win.update_badges()
        self.assertFalse(self.win.lane_rows["home"].badge.get_visible())

    def test_new_post_joins_at_the_bottom(self):
        lane = self._lane("home")
        before = list(lane.order)
        self.world.add(status("020", BOB, minute=20, text="новое"), home=True)
        self.core.poll_once()
        pump(lambda: len(lane.order) == len(before) + 1, 5)
        self.assertEqual(lane.order[:len(before)], before)
        self.assertEqual(lane.rows[lane.order[-1]].post.id, "020")

    def test_thread_opens_in_a_tab(self):
        lane = self._lane("home")
        reply = next(c for c in lane.rows.values() if c.post.id == "013")
        self.win.open_thread(reply.post)
        self.assertTrue(pump(lambda: self.win.tabs.get_n_pages() == 2 and
                             any(True for _ in _cards(self.win)), 5))
        self.win.close_thread("013")
        self.assertEqual(self.win.tabs.get_n_pages(), 1)

    def test_links(self):
        opened = []
        self.win.open_url = opened.append
        self.win.on_link("https://e.test/x")
        self.assertEqual(opened, ["https://e.test/x"])
        self.win.on_link("fedtail:account/B")  # a profile: a tab with the posts
        self.assertTrue(pump(lambda: "B" in self.win.accounts and
                             any(isinstance(w, Gtk.Button) and
                                 w.get_label() in (i18n._("follow"), i18n._("unfollow"))
                                 for w in _walk(self.win.accounts["B"])), 5))
        self.win._close_current_tab()
        self.assertNotIn("B", self.win.accounts)
        self.win.on_link("fedtail:thread/011")
        self.assertTrue(pump(lambda: "011" in self.win.threads, 5))
        self.win.on_link("fedtail:copyhandle/bob%40social.example")
        self.assertIn("@bob@social.example", self.win.status_line.get_text())

    def test_like_updates_the_card(self):
        lane = self._lane("home")
        card = next(c for c in lane.rows.values() if c.post.id == "011")
        fav = next(b for b in _walk(card.actions) if isinstance(b, Gtk.Button))
        self.assertIn("☆", fav.get_label() + "".join(
            b.get_label() or "" for b in _walk(card.actions) if isinstance(b, Gtk.Button)))
        self.win.on_link("fedtail:fav/011")
        self.assertTrue(pump(lambda: card.post.mine.liked, 5))
        self.assertTrue(any("ft-active" in b.get_css_classes() for b in _walk(card.actions)
                            if isinstance(b, Gtk.Button)))

    def test_post_menu_from_the_shared_list(self):
        lane = self._lane("home")
        card = next(c for c in lane.rows.values() if c.post.id == "011")
        card._fill_menu(card.more)
        labels = [b.get_label() for b in _walk(card.more.get_popover())
                  if isinstance(b, Gtk.Button)]
        self.assertIn(i18n._("open_browser"), labels)
        self.assertIn(i18n._("block_acct", acct="bob@social.example"), labels)
        self.assertNotIn(i18n._("delete"), labels)  # not mine

    def test_delete_asks_first(self):
        asked = []
        self.win.confirm = lambda title, text, then: asked.append(then)
        self.win.on_link("fedtail:delete/010")
        self.assertEqual(len(asked), 1)
        self.assertNotIn("010", self.world.deleted if hasattr(self.world, "deleted") else [])
        asked[0]()  # yes
        self.assertTrue(pump(lambda: self.view.by_id("010") is None or
                             getattr(self.world, "deleted", None), 5))

    def test_reply_in_the_editor(self):
        from fedtail.frontends.gtk.compose import ComposeWindow
        post = self.view.by_id("011")
        dlg = self.win.compose(reply_to=post)
        self.assertIsInstance(dlg, ComposeWindow)
        self.assertTrue(dlg._text().startswith("@bob@social.example"))
        dlg.buffer.insert_at_cursor("ответ из GTK")
        before = len(self.world.posted)
        dlg.send()
        self.assertTrue(pump(lambda: len(self.world.posted) > before, 5))
        text, _vis, reply_to, _md = self.world.posted[-1]
        self.assertEqual(reply_to, "011")
        self.assertTrue(text.endswith("ответ из GTK"))
        self.assertFalse(self.view.get_draft(dlg.key))

    def test_editor_keeps_a_draft(self):
        dlg = self.win.compose()
        dlg.buffer.set_text("недописанное")
        dlg.close()
        pump(timeout=0.2)
        self.assertEqual(self.view.get_draft(dlg.key)["text"], "недописанное")
        again = self.win.compose()
        self.assertEqual(again._text(), "недописанное")
        again.buffer.set_text("")
        again.close()
        pump(timeout=0.2)
        self.assertFalse(self.view.get_draft(again.key))

    def test_editor_pictures_and_poll(self):
        import struct
        import zlib
        png = Path(self._tmp.name) / "p.png"
        raw = b"\x00" + b"\x10\x20\x30" * 4

        def chunk(k, d):
            return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d))
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(
            ">IIBBBBB", 4, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) +
            chunk(b"IEND", b""))
        dlg = self.win.compose()
        dlg._add_media(str(png))
        self.assertFalse(dlg.poll_btn.get_sensitive())  # pictures or a poll, not both
        self.assertTrue(dlg.sensitive_btn.get_visible())
        asked = []
        dlg._ask_alt = asked.append
        dlg.buffer.set_text("с картинкой")
        dlg.send()
        self.assertEqual(asked, [1])  # no description: asked first
        dlg._remove_media(dlg.media[0], dlg.media_box.get_first_child())
        self.assertTrue(dlg.poll_btn.get_sensitive())
        dlg.poll_btn.set_active(True)
        self.assertFalse(dlg.attach_btn.get_sensitive())
        dlg.poll_options[0].set_text("да")
        self.assertIsNone(dlg.poll_data())  # one option is no poll
        dlg.poll_options[1].set_text("нет")
        self.assertEqual(dlg.poll_data()["options"], ["да", "нет"])
        dlg.close()
        pump(timeout=0.2)
        back = self.win.compose()
        self.assertTrue(back.poll_btn.get_active())  # the draft kept the poll
        self.assertEqual(back.poll_options[1].get_text(), "нет")
        back.close()

    def test_notifications(self):
        shown = []
        n = self.win.notifier
        n.show = shown.append
        n.cfg = dict(n.cfg, enabled=True, when_focused=True)
        n.notify([("mentions", self.core.store.get_status("013"))])
        self.assertEqual(len(shown), 1)
        self.assertEqual(shown[0].lane, "mentions")
        n.opened("thread:013")  # a click: the thread
        self.assertTrue(pump(lambda: "013" in self.win.threads, 5))

    def test_activity_lane(self):
        mine = self.core.store.get_status("010")
        self.world.act("x1", "favourite", BOB, mine, minute=1)
        self.world.act("x2", "favourite", NEWS, mine, minute=2)
        self.world.act("x3", "follow", NEWS, minute=3)
        self.core.poll_once()  # the first fetch: history
        self.world.act("x4", "reblog", BOB, mine, minute=4)
        self.core.poll_once()
        pump(timeout=0.3)
        self.assertIn("activity", self.win.lane_rows)
        self.win.sidebar.select_row(self.win.lane_rows["activity"])
        lane = self.win.lane_views["activity"]
        self.assertTrue(pump(lambda: lane.positioned, 5))
        rows = [w for w in _walk(lane.list) if hasattr(w, "newest_sort")]
        self.assertEqual(len(rows), 3)  # the two likes of one post are one row
        # on screen in an active window: seen
        self.assertTrue(pump(lambda: self.core.activity_unread() == 0, 5))

    def test_command_line(self):
        bar = self.win.cmdline
        self.assertIsNotNone(bar)
        alias = self.view.short_ids([self.view.by_id("011")])["011"]
        bar.entry.set_text(f"#{alias} согласен")
        self.assertIn(alias, bar.hint.get_text())  # says what Enter will do
        before = len(self.world.posted)
        bar.run()
        self.assertTrue(pump(lambda: len(self.world.posted) > before, 5))
        self.assertEqual(self.world.posted[-1][2], "011")
        self.assertTrue(pump(lambda: bar.entry.get_text() == "", 2))
        self.win.on_link(f"fedtail:alias/{alias}")
        self.assertEqual(bar.entry.get_text(), f"#{alias} ")


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkBigLaneTest(unittest.TestCase):
    """Thousands of posts in a lane: only a window of them is built, in batches, so the
    main loop never stops for long (the first try froze the desktop for good: 5.6 s for
    1500 posts). The bound is loose: under Xvfb GTK paints in software, a frame of new
    cards there takes a few tenths of a second that a real desktop doesn't."""

    N = 2000
    STEP_MAX = 1.0  # s: the longest a single turn of the main loop may take

    def setUp(self):
        from fedtail.core.view import View
        from fedtail.frontends.gtk import theme as themes
        from fedtail.frontends.gtk.bridge import Bridge
        from fedtail.frontends.gtk.window import MainWindow
        from fedtail.protocols.mastodon import adapter
        i18n.setup("ru")
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        tmp = Path(self._tmp.name)
        FakeApi.world = fakes.World()
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False},
                                  "ui": {"start_lane": "home", "adwaita": "off"}})
        p = paths.resolve("t", config=str(tmp / "c.toml"), data=str(tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        self.core = Core(cfg, p, api_class=FakeApi)
        self.view = View(self.core)
        self.big = [(f"{i:05d}", adapter.post(
            status(f"{i:05d}", BOB, minute=i % 59, text="<p>пост " + "текст " * 30 + "</p>"),
            "t")) for i in range(self.N)]
        self.view.entries = lambda lane: self.big if lane == "home" else []
        self.view.unread = lambda entries: set()  # all read: the lane opens at its end
        self.win = MainWindow(None, self.core, self.view, Bridge(self.view), themes.apply(cfg))
        self.win.set_default_size(900, 600)
        self.win.present()
        self.worst = 0.0
        self.win.start()
        self.loop(lambda: self.lane() is not None and self.lane().positioned, 10)

    def tearDown(self):
        self.win.close()  # as a user would: the lanes stop their queued work
        self.win.destroy()
        pump(timeout=0.1)
        self.core.shutdown()
        self._tmp.cleanup()

    def lane(self):
        return self.win.lane_views.get("home")

    def loop(self, until, timeout=5.0):
        """pump(), keeping the longest single step of the main loop."""
        ctx = GLib.MainContext.default()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            while ctx.pending():
                t = time.monotonic()
                ctx.iteration(False)
                self.worst = max(self.worst, time.monotonic() - t)
            if until():
                return True
            time.sleep(0.005)
        return False

    def test_only_a_window_is_built_and_the_loop_keeps_going(self):
        from fedtail.frontends.gtk import lane as lane_mod
        lv = self.lane()
        self.assertLessEqual(len(lv.rows), lane_mod.WINDOW)
        self.assertEqual(lv.order[-1], self.big[-1][0])  # opened at the newest end
        self.assertLess(self.worst, self.STEP_MAX, "the main loop stopped for too long")

    def test_scrolling_up_grows_without_a_jump(self):
        lv = self.lane()
        before = len(lv.rows)
        grow, lv._grow = lv._grow, lambda: None
        lv.adj.set_value(0)  # at the top of what's built…
        pump(timeout=0.3)
        top = lv._first_visible()
        offset = lv._y(lv.rows[top]) - lv.adj.get_value()
        lv._grow = grow
        lv._grow()  # …older ones join above
        self.assertTrue(self.loop(lambda: len(lv.rows) > before, 5))
        self.loop(lambda: not lv._pending() and lv._held_upper is None, 5)
        pump(timeout=0.2)
        # the post at the top is still where it was on screen: the view moved with it
        self.assertAlmostEqual(lv._y(lv.rows[top]) - lv.adj.get_value(), offset, delta=2)
        self.assertGreater(lv.adj.get_value(), 0)
        self.assertLess(self.worst, self.STEP_MAX)


def _walk(widget):
    """widget and everything inside it."""
    if widget is None:
        return
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from _walk(child)
        child = child.get_next_sibling()


def _cards(win):
    from fedtail.frontends.gtk.window import _cards as cards
    for page in win.threads.values():
        yield from cards(page)


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class TitlebarTest(unittest.TestCase):
    def test_desktop_frame_outside_gnome(self):
        from unittest import mock

        from fedtail.frontends.gtk import gi_setup
        from fedtail.frontends.gtk.window import own_titlebar
        cfg = {"ui": {"gtk_headerbar": "auto"}}
        with mock.patch.object(gi_setup, "Adw", None):
            for desk, own in (("KDE", False), ("XFCE", False), ("X-Cinnamon", False),
                              ("GNOME", True), ("ubuntu:GNOME", True), ("", False)):
                with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": desk}):
                    self.assertEqual(own_titlebar(cfg), own, desk)
            with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE"}):
                self.assertTrue(own_titlebar({"ui": {"gtk_headerbar": "on"}}))
        with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "GNOME"}):
            self.assertFalse(own_titlebar({"ui": {"gtk_headerbar": "off"}}))


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkThemeTest(unittest.TestCase):
    def test_every_theme_makes_css_gtk_takes(self):
        from fedtail.frontends import themefile
        from fedtail.frontends.gtk import theme as themes
        for p in sorted(themefile.BUILTIN_DIR.glob("*.toml")):
            data, _w = themefile.load(p.stem)
            css = themes.Theme(data, themes.desktop()).css("Sans", 1.1)
            prov = Gtk.CssProvider()
            errors = []
            prov.connect("parsing-error",
                         lambda _p, _s, e, errors=errors: errors.append(e.message))
            themes._load_css(prov, css)
            self.assertEqual(errors, [], p.stem)


if __name__ == "__main__":
    unittest.main()
