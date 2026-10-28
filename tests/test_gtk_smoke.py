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
from fedtail.model import real  # noqa: E402

from . import fakes  # noqa: E402
from .fakes import BOB, ME, NEWS, FakeApi, status  # noqa: E402


def _done(value):
    """A future already done (a fake core call)."""
    from concurrent.futures import Future
    f = Future()
    f.set_result(value)
    return f


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
class _GtkBase(unittest.TestCase):
    UI = {}  # more of [ui] for a test class of its own (the split layout)
    START = True  # False: the window made and shown, start() left to the test

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
                                         "frontend": "gtk", "adwaita": "off", **self.UI}})
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
        if not self.START:
            return
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

    def _need_active(self):
        """Seen means on screen in the active window: on a desktop where another
        window has the focus (or the screen is locked, at night) it never is."""
        if not pump(lambda: self.win.is_active(), 2):
            self.skipTest("the window isn't active (another one has the focus)")


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkFirstFrameTest(_GtkBase):
    START = False

    def test_the_curtain_swings_from_the_first_frame(self):
        """As Qt's: the window opens on the curtain with its opossum swinging, nothing
        connected; first_paint runs the start (and so the tray's asking) only once a
        frame is out; the start lane lifts the curtain; after the first round the swing
        runs out."""
        from unittest import mock

        from fedtail.frontends.gtk import tray
        from fedtail.frontends.gtk.window import first_paint
        self.assertIsNone(self.core.me)
        self.assertTrue(self.win.curtain_shown())
        self.assertTrue(self.win._swing_on)
        self.core.start_polling = lambda: None  # the first round by hand, below
        made = []
        painted = []
        with mock.patch.object(tray, "make", lambda win, done: made.append(painted[:])):
            first_paint(self.win, lambda: (painted.append(self.win._swing_on),
                                           self.win.start()))
            self.assertEqual((painted, made), ([], []))  # not before a frame
            self.assertTrue(pump(lambda: made, 5))
        self.assertEqual(painted, [True])  # the opossum swung before the start began
        self.assertEqual(made, [[True]])  # the tray asked for after the first frame
        self.assertTrue(pump(lambda: not self.win.curtain_shown(), 5))  # home lifts it
        self.win.close_all()
        self.assertTrue(self.win._swing_on)  # still starting: the first round not in
        self.core.poll_once()
        self.assertTrue(pump(lambda: not self.win._swing_on, 5))
        self.win.select_lane("home")  # a click on a lane still lifts the curtain
        self.assertFalse(self.win.curtain_shown())

    def test_the_tray_comes_without_waiting(self):
        """tray.make asks the bus and hands the tray over later (or None): the window's
        start never stands on it."""
        from unittest import mock

        from fedtail.frontends.gtk import tray
        got = []
        tray.make(self.win, got.append)
        self.assertTrue(pump(lambda: got, 5))
        self.assertTrue(got[0] is None or isinstance(got[0], tray.Tray))
        if got[0] is not None:
            got[0].close()
        # handed to the window: kept, and one coming after the window went is let go
        fake = mock.Mock()
        self.win._tray_made(fake)
        self.assertIs(self.win.tray, fake)
        late = mock.Mock()
        self.win._tray_made(late)
        late.close.assert_called_once()
        self.win.tray = None


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkSmokeTest(_GtkBase):

    def test_lanes_and_cards(self):
        self.assertIn("home", self.win.lane_rows)
        lane = self._lane("home")
        # (built in batches between frames: a busy machine may not have them all yet)
        self.assertTrue(pump(lambda: len(lane.rows) >= 3, 5), len(lane.rows))
        texts = [c.post.text for c in lane.rows.values()]
        self.assertTrue(any("привет" in t for t in texts))
        # the reply's warning hides its text; "show" / "hide" by it, as Qt's
        reply = next(c for c in lane.rows.values() if c.post.warning)
        from fedtail.core import config as config_mod
        # open or not as ui.expand_cw / ui.arts_mode say, the pictures with it
        was = config_mod.expand_cw(self.core.cfg)
        self.assertEqual(reply.cw_open, was)
        self.assertEqual(reply.cw_btn.get_label(), i18n._("cw_hide" if was else "cw_show"))
        reply.cw_btn.emit("clicked")
        self.assertEqual(reply.cw_inner.get_visible(), not was)
        self.assertEqual(reply.cw_btn.get_label(), i18n._("cw_show" if was else "cw_hide"))

    def test_seen_posts_get_read(self):
        """The window is active and every post fits: all are seen, so all are read."""
        self._need_active()
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

    def test_main_menu_and_a_narrow_window(self):
        for name in ("write", "refresh", "profile", "config", "logs", "about", "quit"):
            self.assertIsNotNone(self.win.lookup_action(name), name)
        lane = self._lane("home")
        self.win.set_default_size(560, 500)  # ui.max_width is wider: the column narrows
        self.assertTrue(pump(lambda: 0 < self.win.get_width() <= 600, 3),
                        f"the window stays {self.win.get_width()} px wide")
        pump(timeout=0.3)
        self.assertLessEqual(lane.list.get_width(), lane.get_width())
        self.assertLessEqual(lane.get_width(), self.win.get_width())

    def test_report_a_bug_on_github(self):
        """As Qt's: the scrubbed draft, then GitHub's new-issue page."""
        from fedtail.frontends.gtk.issue import IssueWindow
        self.assertIsNotNone(self.win.lookup_action("issue"))
        w = IssueWindow(self.win)
        self.assertIn(i18n._("issue_system"), w.body())
        w.text.get_buffer().set_text("сломалось на https://example.test/@mira/1")
        opened = []
        self.win.open_url = opened.append
        w.go()
        self.assertTrue(opened[0].startswith("https://github.com/"))
        self.assertNotIn("example.test", opened[0])

    def test_settings_window_writes_one_line(self):
        """The settings window as Qt's: a switch goes into config.toml at once, that line
        only; the search finds over every chapter."""
        from fedtail.frontends.common import settings
        from fedtail.frontends.gtk.settings import SettingsWindow
        self.assertIsNotNone(self.win.lookup_action("settings"))
        f = self.core.paths.config_file
        f.write_text(config.example_text("ru"), "utf-8")
        w = SettingsWindow(self.win)
        w.present()
        pump(timeout=0.2)
        o = settings.option(w.chapters, "appearance.emoji")
        before = f.read_text("utf-8")
        w.controls[o.name].set_active(not o.value)
        self.assertTrue(pump(lambda: f.read_text("utf-8") != before))
        after = f.read_text("utf-8")
        self.assertEqual(sum(a != b for a, b in zip(before.splitlines(), after.splitlines(),
                                                    strict=True)), 1)
        self.assertTrue(w.restart.get_visible())
        w.search.set_text("шрифт")  # (the entry waits a moment before it searches)
        self.assertTrue(pump(lambda: "appearance.emoji" not in w.controls))
        self.assertIn("appearance.font_size", w.controls)
        w.close()

    def test_what_qt_has_gtk_has(self):
        """The details docs/src/parity.toml once listed GTK without: menu tooltips,
        the profile's tooltip, the face that opens a profile and tells a screen reader,
        the columns' tab named so, the commands' help in a window."""
        model = self.win.menu.model()
        hints = {}

        def walk(m):
            for i in range(m.get_n_items()):
                label = m.get_item_attribute_value(i, "label", None)
                tip_v = m.get_item_attribute_value(i, "tooltip", None)
                if label is not None and tip_v is not None:
                    hints[label.get_string()] = tip_v.get_string()
                for link in ("section", "submenu"):
                    sub = m.get_item_link(i, link)
                    if sub is not None:
                        walk(sub)
        walk(model)
        for key, tipkey in (("whats_this", "whats_this_tip"), ("try_theme", "try_theme_tip"),
                            ("accounts_merge", "accounts_merge_tip"),
                            ("debug_tracing", "debug_tracing_tip")):
            self.assertEqual(hints.get(i18n._(key)), i18n._(tipkey), key)
        self.assertEqual(self.win.profile_label._ft_tip, i18n._("footer_profile_tip"))
        lane = self._lane("home")
        self.assertTrue(pump(lambda: any(True for _ in lane.cards()), 3)
                        if hasattr(lane, "cards") else True)
        self.win.set_columns(True)
        label = self.win.tabs.get_tab_label(self.win.stack)
        self.assertEqual(label.get_label(), i18n._("columns"))
        self.win.set_columns(False)
        self.assertEqual(self.win.tabs.get_tab_label(self.win.stack).get_label(),
                         i18n._("gtk_lanes"))
        from fedtail.frontends.gtk import dialogs
        w = dialogs.info(self.win, i18n._("cmd_help_title"), i18n._("cmd_help"))
        self.assertEqual(w.get_title(), i18n._("cmd_help_title"))
        w.close()
        if self.win.cmdline is not None:
            self.win.cmdline.entry.set_text("?")
            self.win.cmdline.run()
            pump(timeout=0.2)

    def test_the_menu_and_what_it_opens(self):
        """≡ as Qt's: its items made, and each window or tab they open comes up
        without an error (on the fake server)."""
        menu = self.win.menu
        model = menu.model()
        labels = []

        def walk(m):
            for i in range(m.get_n_items()):
                label = m.get_item_attribute_value(i, "label", None)
                if label is not None:
                    labels.append(label.get_string())
                for link in ("section", "submenu"):
                    sub = m.get_item_link(i, link)
                    if sub is not None:
                        walk(sub)
        walk(model)
        for key in ("tender_menu", "accounts", "try_theme", "debug_menu", "help_title",
                    "about", "open_config", "silence_muted"):
            self.assertTrue(any(i18n._(key) in x for x in labels), key)
        errors = []
        self.win.error = lambda e: errors.append(str(e))
        self.win.bridge.on_error = errors.append
        for name in ("filters", "muted", "scheduled", "server", "federation", "help",
                     "test_notify", "stacks", "census", "trim", "whats_this"):
            self.win.activate_action("win." + name, None)
            pump(timeout=0.3)
        self.assertTrue(self.win.hints_on)
        self.win.activate_action("win.whats_this", None)
        self.assertFalse(self.win.hints_on)
        self.win.open_search("bob")
        pump(lambda: "search" in self.win.extra_tabs, 3)
        self.win.open_tag("linux")
        pump(timeout=0.3)
        self.assertIn("tag:linux", self.win.extra_tabs)
        self.assertEqual(errors, [])
        for w in list(Gtk.Window.list_toplevels()):
            if w is not self.win:
                w.close()

    def test_columns_and_full_width(self):
        lane = self._lane("home")
        self.win.columns_btn.set_active(True)
        pump(timeout=0.3)
        self.assertIsNotNone(self.win.columns)
        self.assertIn("home", self.win.columns.frames)
        self.assertIs(lane.get_parent(), self.win.columns.frames["home"])
        self.assertTrue(self.win.lane_on_screen("home"))
        self.win.columns_btn.set_active(False)
        pump(timeout=0.3)
        self.assertIsNone(self.win.columns)
        self.assertIs(lane.get_parent(), self.win.stack)
        self.win.wide_btn.set_active(not self.win.wide_btn.get_active())
        pump(timeout=0.2)
        self.assertEqual(bool(self.core.cfg["ui"]["max_width"]),
                         not self.win.wide_btn.get_active())

    def test_a_section_folds(self):
        from fedtail.frontends.gtk.window import SectionRow
        heads = [r for r in _walk(self.win.sidebar) if isinstance(r, SectionRow)]
        if not heads:
            self.skipTest("no sections in this sidebar")
        head = heads[0]
        self.win._row_activated(self.win.sidebar, head)
        self.assertTrue(all(not self.win.lane_rows[n].get_visible() for n in head.names))
        self.win._row_activated(self.win.sidebar, head)
        self.assertTrue(all(self.win.lane_rows[n].get_visible() for n in head.names))

    def test_filters_and_the_funnel(self):
        """The header's choices (common/lane.py): posts only, the media funnel."""
        lane = self._lane("home")
        pump(lambda: lane.positioned and not lane._pending(), 5)
        everything = len(lane.rows)
        lane._filter_buttons["posts"].set_active(True)  # no replies
        pump(lambda: lane.positioned and not lane._pending(), 5)
        self.assertLess(len(lane.rows), everything)
        self.assertFalse(any(c.post.reply_to for c in lane.rows.values()))
        lane._filter_buttons["all"].set_active(True)
        pump(lambda: len(lane.rows) == everything, 5)
        lane.media_checks["text"].set_active(False)  # posts with pictures only: none here
        pump(lambda: not lane.rows, 5)
        self.assertFalse(lane.rows)
        self.assertTrue(lane.info.get_text())
        lane.media_checks["text"].set_active(True)
        pump(lambda: len(lane.rows) == everything, 5)
        self.assertEqual(len(lane.rows), everything)

    def test_new_post_joins_at_the_bottom(self):
        lane = self._lane("home")
        # the lane done building first (in a busy run it may still be): what's on screen
        pump(lambda: lane.positioned and not lane._pending() and len(lane.order) ==
             len(lane.keys), 5)
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
        # the header, as Qt's: what it is, Subscribe
        head = self.win.threads["013"].head
        self.assertTrue(pump(lambda: head.root is not None, 3))
        self.assertIn(i18n._("thread_info", n=1).split()[0], head.info.get_text())
        # a warning in the thread: every one of them opened at once (and closed)
        self.assertTrue(head.cw_all.get_visible())
        from fedtail.frontends.gtk.card import Card
        warned = [c for c in _walk(self.win.threads["013"]) if isinstance(c, Card)
                  and getattr(c, "cw_inner", None) is not None]
        self.assertTrue(warned)
        head.cw_all.emit("clicked")
        self.assertTrue(all(c.cw_open for c in warned))
        head.cw_all.emit("clicked")
        self.assertFalse(any(c.cw_open for c in warned))
        was = bool(self.view.subscribed(head.root))
        head.sub.set_active(not was)
        self.assertTrue(pump(lambda: bool(self.view.subscribed(head.root)) != was, 3))
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

    def test_post_text_is_one_layout_with_links(self):
        from fedtail.frontends.gtk.textblock import TextBlock, links_of
        shown, links = links_of('при&amp;вет <a href="https://e.test/?a=1&amp;b=2">ссылка</a>!',
                                "#123456")
        self.assertNotIn("<a", shown)
        self.assertEqual(len(links), 1)
        start, end, url = links[0]
        self.assertEqual(url, "https://e.test/?a=1&b=2")
        text = "при&вет ссылка!".encode()
        self.assertEqual(text[start:end].decode(), "ссылка")
        lane = self._lane("home")
        card = next(c for c in lane.rows.values() if c.post.id == "011")
        body = next(w for w in _walk(card) if isinstance(w, TextBlock))
        self.assertIn("привет", body.text())
        pump(lambda: body.get_width() > 0, 3)
        followed = []
        body.on_link = followed.append
        start, end, url = body.links[0]
        idx = (start + end) // 2
        rect = body.layout.index_to_pos(idx)
        from fedtail.frontends.gtk.gi_setup import Pango
        x, y = rect.x / Pango.SCALE + 1, rect.y / Pango.SCALE + 1
        self.assertEqual(body.link_at(x, y), "https://e.test/")
        self.assertIsNone(body.link_at(0, 0))  # "привет": no link

    def test_like_updates_the_card(self):
        lane = self._lane("home")
        card = next(c for c in lane.rows.values() if c.post.id == "011")
        # ☆ by the word, or the desktop icon theme's star (the system theme: "desktop")
        self.assertTrue("☆" in "".join(b.get_text() or "" for b in _walk(card.actions)
                                       if isinstance(b, Gtk.Label))
                        or any(isinstance(w, Gtk.Image) for w in _walk(card.actions)))
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

    def test_what_the_post_menu_opens(self):
        """The ⋯ items that open a window or a tab — a post's versions, a complaint,
        who liked it, the quotes of my post — and "read up to here": as in Qt, no
        "not here yet"."""
        said = []
        self.win.status = lambda text, *a: said.append(text)
        before = set(Gtk.Window.list_toplevels())
        self.win.on_link("fedtail:history/011")
        self.win.on_link("fedtail:report/011")
        pump(timeout=0.5)
        new = [w for w in Gtk.Window.list_toplevels() if w not in before]
        self.assertGreaterEqual(len(new), 2)
        self.win.on_link("fedtail:favourited_by/011")
        self.win.on_link("fedtail:quotes/010")
        pump(timeout=0.5)
        self.assertIn("favourited_by:011", self.win.extra_tabs)
        self.assertIn("quotes:010", self.win.extra_tabs)
        self.win.on_link("fedtail:readupto/012")
        pump(timeout=0.3)
        self.assertNotIn(i18n._("gtk_not_yet"), said)
        for w in new:
            w.close()

    def test_vote_in_a_poll(self):
        """A poll not voted in: options and Vote, as in Qt; voted — the results."""
        st = status("020", BOB, minute=20, text="опрос", vis="public")
        st["poll"] = {"id": "P2", "expired": False, "multiple": False, "voted": False,
                      "own_votes": [], "votes_count": 3, "voters_count": 3,
                      "expires_at": "2099-01-01T12:00:00Z",
                      "options": [{"title": "да", "votes_count": 2},
                                  {"title": "нет", "votes_count": 1}]}
        self.world.add(st, home=True)
        self.core.poll_once()
        lane = self._lane("home")
        self.assertTrue(pump(lambda: any(c.post.id == "020" for c in lane.rows.values()), 5))
        card = next(c for c in lane.rows.values() if c.post.id == "020")
        checks = [w for w in _walk(card) if isinstance(w, Gtk.CheckButton)]
        vote = next(w for w in _walk(card) if isinstance(w, Gtk.Button) and
                    w.get_label() == i18n._("poll_vote"))
        self.assertEqual([c.get_label() for c in checks], ["да", "нет"])
        self.assertFalse(vote.get_sensitive())
        checks[1].set_active(True)
        self.assertTrue(vote.get_sensitive())
        vote.emit("clicked")
        self.assertTrue(pump(lambda: not any(isinstance(w, Gtk.CheckButton)
                                             for w in _walk(card)), 5))
        # "refresh": fresh counts from the server
        self.world.statuses["020"]["poll"]["options"][0]["votes_count"] = 40
        self.world.statuses["020"]["poll"]["votes_count"] = 42
        foot = next(w for w in _walk(card) if isinstance(w, Gtk.Label)
                    and i18n._("poll_refresh") in (w.get_text() or ""))
        foot.emit("activate-link", "fedtail:poll-refresh")

        def texts():
            return " ".join(w.get_text() for w in _walk(card) if isinstance(w, Gtk.Label))
        self.assertTrue(pump(lambda: "95%" in texts(), 5), texts())

    def test_profile_buttons_as_in_qt(self):
        """A profile's buttons come from common/profile.py (as Qt offers them) and do
        their thing: mute, a note, whom they follow."""
        from fedtail.frontends.common import profile as prof
        self.win.open_account("B")
        page = self.win.accounts.get("B")
        self.assertIsNotNone(page)

        def labels():
            return [b.get_label() for b in _walk(page) if isinstance(b, Gtk.Button)]
        self.assertTrue(pump(lambda: i18n._("mute") in labels(), 5))
        for key in ("block", "note_edit", "copy_handle"):
            self.assertIn(i18n._(key), labels())
        mute = next(b for b in _walk(page) if isinstance(b, Gtk.Button)
                    and b.get_label() == i18n._("mute"))
        mute.emit("clicked")  # how long first, and posts only or not
        ask = self.win._asking
        self.assertEqual([k for k, _r in ask.radios][:2], [0, 3600])
        ask.radios[2][1].set_active(True)  # a day
        ask.tick.set_active(True)
        ask.ok.emit("clicked")
        self.assertTrue(pump(lambda: i18n._("unmute") in labels(), 5))
        self.assertEqual(self.world.mute_terms["B"], {"duration": 86400, "notifications": False})
        asked = []
        self.win.ask_text = lambda title, q, then, text="", allow_empty=False: \
            asked.append(then)
        note = next(b for b in _walk(page) if isinstance(b, Gtk.Button)
                    and b.get_label() == i18n._("note_edit"))
        note.emit("clicked")
        self.assertEqual(len(asked), 1)
        self.assertEqual(prof.parse_langs("ru; en  de"), ["ru", "en", "de"])

    def test_esc_closes_every_lane_behind_a_curtain(self):
        """As Qt (ui.esc = "curtain"): Esc — no lane on screen, what comes waits,
        counted; Enter — the last lane again."""
        from gi.repository import Gdk
        self.assertTrue(self.win._key(None, Gdk.KEY_Escape, 0, 0))
        self.assertTrue(self.win.curtain_shown())
        self.assertIsNone(self.win.sidebar.get_selected_row())
        # a poll round on: the curtain's opossum swings; over: it stands still
        from unittest import mock
        with mock.patch.object(type(self.core), "poll_state", create=True,
                               return_value={"busy": True}):
            self.win._curtain_swing()
            self.assertTrue(self.win._swing_on)
            self.assertGreater(len(self.win._swing_frames()), 10)
        with mock.patch.object(type(self.core), "poll_state", create=True,
                               return_value={"busy": False}):  # (the window may poll now)
            self.win._curtain_swing()
        # the swing runs out first, then stands still (as Qt's)
        self.assertTrue(pump(lambda: not self.win._swing_on, 5))
        self.world.add(status("030", BOB, minute=30, text="пока шторка"), home=True)
        self.core.poll_once()
        self.assertTrue(pump(lambda: i18n._("lane_home") in
                             self.win.curtain_info.get_text(), 5),
                        self.win.curtain_info.get_text())
        self.win.set_focus(None)  # (not the Enter of a field: the command line's)
        self.assertTrue(self.win._key(None, Gdk.KEY_Return, 0, 0))
        self.assertFalse(self.win.curtain_shown())
        self.assertEqual(self.win._current_lane(), "home")

    def test_the_status_line_says_what_qt_says(self):
        """Connecting, the server down (again in 20 s), a link not opened, deleted."""
        self.assertTrue(self.win._hello.startswith("@"))
        self.win._connect_failed("HTTP 502: Bad Gateway")
        self.assertIn(i18n._("server_down", err="HTTP 502: Bad Gateway"),
                      self.win.status_line.get_text())
        self.win.open_url("file:///etc/passwd")
        self.assertEqual(self.win.status_line.get_text(), i18n._("link_refused"))
        self.win.on_event("status_deleted", "999")
        self.assertEqual(self.win.status_line.get_text(), i18n._("deleted"))

    def test_translate_and_read_whole(self):
        """⋯ → Translate puts the server's translation in the text's place (the original
        a click away); 📄 the whole text opens a page — as in Qt."""
        from fedtail.model import Translation
        lane = self._lane("home")
        card = next(c for c in lane.rows.values() if c.post.id == "011")
        self.view.translate = lambda p: _done(Translation("<p>hello</p>", "ru", "test"))
        from dataclasses import replace
        self.core.caps = replace(self.core.caps, translation=False)
        card.translate()  # a server that can't: said, as in Qt
        self.assertIn(i18n._("translate_none"), self.win.status_line.get_text())
        self.core.caps = replace(self.core.caps, translation=True)
        card.translate()
        self.assertTrue(pump(lambda: getattr(card, "showing_translation", False), 3))
        card.translate()
        self.assertFalse(card.showing_translation)
        self.view.long_form = lambda st: _done({"name": "Статья", "start": "", "end": "",
                                                "location": "", "summary": "",
                                                "content": "<p>всё</p>",
                                                "url": "https://e.test/a"})
        before = set(Gtk.Window.list_toplevels())
        self.win.read_whole(card.post)
        pump(timeout=0.4)
        new = [w for w in Gtk.Window.list_toplevels() if w not in before]
        self.assertEqual([w.get_title() for w in new], ["Статья"])
        for w in new:
            w.close()

    def test_add_to_list(self):
        """"Add to list" from a post's ⋯ and a profile, as in Qt: someone not followed —
        the ticks dead under "follow first", Follow right there."""
        lane = self._lane("home")
        card = next(c for c in lane.rows.values() if c.post.id == "011")
        card._fill_menu(card.more)
        labels = [b.get_label() for b in _walk(card.more.get_popover())
                  if isinstance(b, Gtk.Button)]
        self.assertIn(i18n._("add_to_list"), labels)
        pop = self.win.lists_popover(card.post.author, card.more)
        self.assertTrue(pump(lambda: any(
            isinstance(w, Gtk.Label) and w.get_text() == i18n._("list_follow_first")
            for w in _walk(pop)), 3))
        pop.popdown()

    def test_collections_in_a_place_window(self):
        """Collections (Mastodon 4.6): the shared place in a window of its own — made
        from its form, someone put in from "Add to collection", as the web page does."""
        pw = self.win.open_place("collections")
        self.assertTrue(pump(lambda: "name" in pw.fields, 3))
        pw.fields["name"][1].set_text("Друзья")
        pw.press(pw.places.page("collections").submit)
        self.assertTrue(pump(lambda: len(self.world.collections) == 1, 3))
        cid = next(iter(self.world.collections))
        put = self.win.open_place("collect", "B")
        self.assertTrue(pump(lambda: put.rows.get_first_child() is not None and
                             any(isinstance(w, Gtk.Button) for w in _walk(put.rows)), 3))
        toggle = next(w for w in _walk(put.rows) if isinstance(w, Gtk.Button))
        toggle.emit("clicked")
        self.assertTrue(pump(lambda: self.world.collections[cid]["members"], 3))
        pw.window.close()
        put.window.close()

    def test_place_and_settings_scrollbars_beside_the_buttons(self):
        """A place (≡ → Lanes) and the settings: the scrollbar takes a strip of its own,
        as in Qt — not GTK's overlay one drawn over "Take", "Edit…" at the right edge;
        the content ends left of the scrollbar."""
        from gi.repository import Graphene

        from fedtail.frontends.gtk.settings import SettingsWindow
        pw = self.win.open_place("lanes")
        self.assertTrue(pump(lambda: any(isinstance(w, Gtk.Button)
                                         for w in _walk(pw.rows)), 3))
        sw = Gtk.ScrolledWindow
        scroll = pw.rows.get_ancestor(sw)
        self.assertFalse(scroll.get_overlay_scrolling())
        s = SettingsWindow(self.win)
        s.present()
        pump(timeout=0.3)
        # the chapters and the page (a drop-down's own popup list is GTK's business)
        for w in (s.list.get_ancestor(sw), s.scroll):
            self.assertFalse(w.get_overlay_scrolling())
        # the rows' right edge stops where the vertical scrollbar begins
        pw.window.set_default_size(640, 200)
        pump(timeout=0.3)
        bar = scroll.get_vscrollbar()
        if bar.get_mapped() and bar.get_width() > 0:
            ok, pt = pw.rows.compute_point(scroll, Graphene.Point().init(
                pw.rows.get_width(), 0))
            self.assertTrue(ok)
            self.assertLessEqual(pt.x, bar.get_allocation().x + 0.5)
        s.close()
        pw.window.close()

    def test_a_lists_menu_in_the_sidebar(self):
        """A right click on a list: who's in it, up/down, rename, exclusive, delete —
        as in Qt; on another lane: a new list."""
        from fedtail.frontends.gtk import lists
        row = next((r for n, r in self.win.lane_rows.items() if not n.startswith("list:")))
        pop = lists.lane_menu(self.win, row)
        if self.win.cfg["lists"]["enabled"]:
            labels = [b.get_label() for b in _walk(pop) if isinstance(b, Gtk.Button)]
            self.assertIn(i18n._("list_new"), labels)
            pop.popdown()
        made = []
        self.win.call(self.view.create_list("Друзья"), made.append)
        self.assertTrue(pump(lambda: made and f"list:{made[0].id}" in self.win.lane_rows, 5))
        row = self.win.lane_rows[f"list:{made[0].id}"]
        pop = lists.lane_menu(self.win, row)
        labels = [b.get_label() for b in _walk(pop) if isinstance(b, Gtk.Button)]
        for key in ("list_people", "list_rename", "list_delete"):
            self.assertIn(i18n._(key), labels)
        pop.popdown()
        page = lists.open_list_people(self.win, made[0])
        self.assertIsNotNone(page)

    def test_announcements(self):
        """The server's announcements as Qt's strip: shown, "Got it" sends it away."""
        from fedtail.model import Announcement
        bar = self.win.announce_bar
        bar.got([Announcement(id="A1", html="<p>Обновление сервера в полночь</p>")])
        self.assertTrue(bar.get_visible())
        self.assertIn("Обновление", bar.body.get_text())
        bar.dismiss()
        self.assertFalse(bar.get_visible())

    def test_about_says_what_qt_says(self):
        before = set(Gtk.Window.list_toplevels())
        self.win.about()
        pump(timeout=0.3)
        new = [w for w in Gtk.Window.list_toplevels() if w not in before]
        self.assertEqual(len(new), 1)
        # the cards (gtk/about.py), as Qt's: every label's words, made_by_long among them
        words = []

        def walk(w):
            if isinstance(w, Gtk.Label):
                words.append(w.get_label())
            child = w.get_first_child()
            while child is not None:
                walk(child)
                child = child.get_next_sibling()
        walk(new[0])
        self.assertIn(i18n._("made_by_long"), words)
        new[0].close()

    def test_edit_my_profile(self):
        """My profile's Edit as in Qt: loaded, only what changed goes to the server."""
        ed = self.win.edit_profile()
        self.assertTrue(pump(lambda: ed.loaded is not None, 5))
        self.assertEqual(ed.changes(), {})
        ed.name.set_text("Новое имя")
        self.assertEqual(ed.changes(), {"name": "Новое имя"})
        ed.dlg.close()

    def test_find_in_the_lane(self):
        """Ctrl+F as in Qt: the words, "1 of 1", the card brought and marked."""
        bar = self.win.find_bar
        bar.open()
        self.assertTrue(bar.get_visible())
        bar.entry.set_text("коммент")
        bar.search(jump=True)
        lv = self.win.current_lane_view()
        self.assertIsNotNone(lv, "no lane in front")
        self.assertEqual(len(bar.hits), 1)
        self.assertTrue(pump(lambda: bar._marked is not None, 3))
        self.assertTrue(bar._marked.has_css_class("ft-found"))
        self.assertEqual(bar.count.get_text(), i18n._("find_count", i=1, n=1))
        bar.entry.set_text("нет такого слова")
        bar.search(jump=True)
        self.assertEqual(bar.count.get_text(), i18n._("find_none"))
        bar.close_bar()
        self.assertFalse(bar.get_visible())

    def test_find_deeper_and_in_every_lane(self):
        """As Qt: "Deeper" looks through everything stored for the lane; "In every
        lane" — everything stored, lane by lane, and goes to the lane of the match."""
        bar = self.win.find_bar
        bar.open()
        bar.entry.set_text("коммент")
        bar.search(jump=True)
        self.assertTrue(bar.deeper.get_visible())
        bar.deeper.emit("clicked")
        self.assertTrue(pump(lambda: bar.deeper.get_sensitive(), 3))
        bar.everywhere.set_active(True)
        self.assertTrue(pump(lambda: bar.all_hits, 5))
        self.assertFalse(bar.deeper.get_visible())
        lanes = {h["lane"] for h in bar.all_hits}
        self.assertIn("home", lanes)
        self.assertTrue(pump(lambda: bar._marked is not None, 3))
        bar.everywhere.set_active(False)  # (remembered: off again for the next tests)
        bar.close_bar()

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
        # "you replied" under the post answered, at once (not at the next poll)
        card = next(c for c in self._lane("home").rows.values() if c.post.id == "011")
        self.assertTrue(pump(lambda: bool(card.mine_ids), 5))

    def test_the_editor_is_a_panel_in_the_window(self):
        """As Qt's: over the window's middle, following its size; language, Later,
        Preview, Discard; one editor at a time."""
        dlg = self.win.compose()
        self.assertIs(dlg.get_parent(), self.win.overlay)
        pump(lambda: dlg.get_width() > 0, 3)
        self.assertLessEqual(dlg.get_width(), self.win.overlay.get_width())
        self.assertEqual(dlg.language(), self.core.cfg["post"].get("language") or "")
        dlg._set_language("ka")
        self.assertEqual(dlg.language(), "ka")
        dlg.buffer.set_text("**жирно** и _нет_")
        prev = dlg.preview()
        self.assertTrue(prev.get_visible())
        prev.close()
        later = dlg.ask_schedule()
        later.close()
        other = self.win.compose()  # the first one goes, its text kept — and back
        self.assertTrue(dlg.closed)
        self.assertIsNone(dlg.get_parent())
        self.assertEqual(other._text(), "**жирно** и _нет_")
        asked = []
        self.win.confirm = lambda _t, _x, then: asked.append(then)
        other.discard()
        asked[0]()
        self.assertTrue(other.closed)
        self.assertFalse(self.view.get_draft(other.key))

    def test_the_formatting_buttons(self):
        """post.format_bar: as Qt's — Markdown around the selection, off again, one undo."""
        self.core.cfg["account"]["markdown"] = "on"
        self.addCleanup(self.core.cfg["account"].__setitem__, "markdown", "auto")
        self.core.cfg["post"]["format_bar"] = "left"
        self.addCleanup(self.core.cfg["post"].__setitem__, "format_bar", "left")
        dlg = self.win.compose()
        self.assertIsNotNone(dlg.format_bar)
        from gi.repository import Gtk as G
        self.assertEqual(dlg.format_bar.get_orientation(), G.Orientation.VERTICAL)
        self.assertIsNotNone(dlg.format_bar.get_next_sibling())  # the first: the text after
        dlg.buffer.set_text("say hi 😀 now")
        b = dlg.buffer
        b.select_range(b.get_iter_at_offset(4), b.get_iter_at_offset(8))
        dlg.format_bar.buttons["bold"].emit("clicked")
        self.assertEqual(dlg._text(), "say **hi 😀** now")
        s, e = b.get_selection_bounds()
        self.assertEqual((s.get_offset(), e.get_offset()), (6, 10))
        dlg.format_bar.buttons["bold"].emit("clicked")
        self.assertEqual(dlg._text(), "say hi 😀 now")
        dlg.format_bar.buttons["list"].emit("clicked")
        self.assertTrue(dlg._text().startswith("- say"))
        dlg.close()
        self.core.cfg["post"]["format_bar"] = "bottom"  # a row under the text
        dlg = self.win.compose()
        self.assertEqual(dlg.format_bar.get_orientation(), G.Orientation.HORIZONTAL)
        self.assertIsNone(dlg.format_bar.get_next_sibling())  # the last one: below
        dlg.close()
        self.core.cfg["post"]["format_bar"] = "off"
        dlg = self.win.compose()
        self.assertIsNone(dlg.format_bar)
        dlg.close()

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

    def test_pictures_dropped_and_pasted(self):
        """As Qt's: files and pictures dropped on the editor or pasted with Ctrl+V become
        attachments (a picture without a file kept as PNG in the profile's folder); a
        drop on the window starts a post with them; text on the clipboard stays text."""
        import struct
        import zlib

        from gi.repository import Gio

        from fedtail.frontends.gtk import dropin
        png = Path(self._tmp.name) / "drop.png"

        def chunk(k, d):
            return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d))
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(
            ">IIBBBBB", 2, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(
                b"\x00" + b"\x10\x20\x30" * 2)) + chunk(b"IEND", b""))
        texture = Gdk.Texture.new_from_filename(str(png))
        note = Path(self._tmp.name) / "note.txt"
        note.write_text("x")
        files = Gdk.FileList.new_from_list([Gio.File.new_for_path(str(png)),
                                            Gio.File.new_for_path(str(note))])
        data = self.view.paths.data_dir
        self.assertEqual(dropin.paths_of(files, data), [str(png)])  # media only
        pasted = dropin.paths_of(texture, data)
        self.assertEqual(len(pasted), 1)
        self.assertTrue(Path(pasted[0]).is_file())
        self.assertEqual(Path(pasted[0]).parent, Path(data) / "attachments")

        dlg = self.win.compose()
        dlg.add_paths([str(png), str(png)])  # each once
        self.assertEqual([m[0] for m in dlg.media], [str(png)])
        # Ctrl+V: a picture on the clipboard goes in as an attachment
        clip = dlg.get_clipboard()
        clip.set_content(Gdk.ContentProvider.new_for_value(texture))
        self.assertEqual(dropin.wants_paste(clip), "picture")
        self.assertTrue(dlg._paste_key(None, Gdk.KEY_v, 0, Gdk.ModifierType.CONTROL_MASK))
        self.assertTrue(pump(lambda: len(dlg.media) == 2, 3))
        # files copied in a file manager
        clip.set_content(Gdk.ContentProvider.new_for_value(
            Gdk.FileList.new_from_list([Gio.File.new_for_path(str(png))])))
        self.assertEqual(dropin.wants_paste(clip), "files")
        # text: not ours, the text field pastes it
        clip.set("просто текст")
        self.assertIsNone(dropin.wants_paste(clip))
        self.assertFalse(dlg._paste_key(None, Gdk.KEY_v, 0, Gdk.ModifierType.CONTROL_MASK))
        dlg.buffer.set_text("")
        dlg.close()
        # dropped on the window: a new post with the picture
        self.win._dropped([str(png)])
        c = self.win.composer
        self.assertIsNotNone(c)
        self.assertFalse(c.closed)
        # (the first editor's two pictures came back with its draft: the drop adds none)
        self.assertEqual([m[0] for m in c.media].count(str(png)), 1)
        for item in list(c.media):
            c._remove_media(item, c.media_box.get_first_child())
        c.close()

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
        # the focus point and the description, in a window of their own (as Qt's)
        fd = dlg._focus_dialog(dlg.media[0])
        fd._clicked(0, 0)  # the top left corner
        self.assertEqual(fd.focus, [-1.0, 1.0])
        fd.text.get_buffer().set_text("полоска")
        fd._ok()
        self.assertEqual(dlg._media_list(), [[str(png), "полоска", [-1.0, 1.0]]])
        dlg.media[0][1].set_text("")
        # #tags all small: screen readers spell them as one word — said
        dlg.buffer.set_text("#georgianews")
        self.assertTrue(pump(lambda: dlg.camel.get_visible(), 2))
        asked = []
        dlg._ask_alt = lambda n, *_a: asked.append(n)
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

    def _events(self, lane):
        """The event rows a lane has on screen (gtk/lane.py EventRow), top to bottom."""
        from fedtail.frontends.gtk.lane import EventRow
        return [lane.rows[k] for k in lane.order if isinstance(lane.rows[k], EventRow)]

    def _open_lane(self, name):
        self.assertIn(name, self.win.lane_rows)
        self.win.select_lane(name)
        lane = self.win.lane_views[name]
        self.assertTrue(pump(lambda: lane.positioned, 5))
        return lane

    def _some_activity(self):
        mine = self.core.store.get_status("010")
        self.world.act("x1", "favourite", BOB, mine, minute=1)
        self.world.act("x2", "favourite", NEWS, mine, minute=2)
        self.world.act("x3", "follow", NEWS, minute=3)
        self.core.poll_once()  # the first fetch: history
        self.world.act("x4", "reblog", BOB, mine, minute=4)
        self.core.poll_once()
        pump(timeout=0.3)

    def test_activity_lane(self):
        """Activity is a lane like any other (LaneView, its rows from LaneModel): the
        likes listed, two of one post in one row, × at the row's end, seen on screen
        counts down, Clear asks and clears."""
        from fedtail.frontends.gtk.lane import LaneView
        self._some_activity()
        lane = self._open_lane("activity")
        self.assertIsInstance(lane, LaneView)
        self.assertTrue(pump(lambda: len(self._events(lane)) == 3, 5))  # likes: one row
        kinds = sorted(r.kind for r in self._events(lane))
        self.assertEqual(kinds, ["favourite", "follow", "reblog"])
        like = next(r for r in self._events(lane) if r.kind == "favourite")
        words = " ".join(w.get_text() for w in _walk(like) if isinstance(w, Gtk.Label))
        self.assertIn("«", words)  # the post it is about, a line of its own
        self.assertIn(i18n._("act_favourite"), words)
        # × at the row's right end, whatever the words' length
        pump(timeout=0.3)
        for r in self._events(lane):
            x = next(b for b in _walk(r) if isinstance(b, Gtk.Button) and b.get_label() == "×")
            ok, bounds = x.compute_bounds(r)
            self.assertTrue(ok)
            self.assertGreater(bounds.get_x() + bounds.get_width(), r.get_width() - 40)
        # on screen in an active window: seen, here and in the core
        if pump(lambda: self.win.is_active(), 2):
            self.assertTrue(pump(lambda: self.core.unread_count("activity") == 0, 5))
            self.assertTrue(pump(lambda: not any(r.unread for r in self._events(lane)), 5))
        # Clear: asked first, then gone here and on the server
        self.assertIsNotNone(lane.clear_btn)
        self.assertTrue(lane.clear_btn.get_visible())
        asked = []
        self.win.confirm = lambda _t, _x, then: asked.append(then)
        lane.clear_btn.emit("clicked")
        self.assertEqual(len(asked), 1)
        asked[0]()
        self.assertTrue(pump(lambda: not self.world.activity and not self._events(lane), 5))
        self.assertIsNone(self._lane("home").clear_btn)  # a lane of posts has none

    def test_events_unread_until_all_read(self):
        """Not seen yet: an event row looks unread as a post does; "mark all read" marks
        the lane's events seen too."""
        self._some_activity()
        self.win.view.mark_activity_seen = lambda upto=None: None  # nothing seen by scrolling
        lane = self._open_lane("activity")
        self.assertTrue(pump(lambda: len(self._events(lane)) == 3, 5))
        # the first fetch is history (seen); what came after it is new
        boost = next(r for r in self._events(lane) if r.kind == "reblog")
        self.assertTrue(boost.unread)
        self.assertTrue(boost.has_css_class("ft-unread"))
        self.assertGreater(self.core.unread_count("activity"), 0)
        del self.win.view.mark_activity_seen
        lane.mark_all_read()
        self.assertTrue(pump(lambda: self.core.unread_count("activity") == 0, 5))
        self.assertTrue(pump(lambda: not any(r.unread for r in self._events(lane)), 5))

    def test_event_hidden_by_its_cross(self):
        self._some_activity()
        lane = self._open_lane("activity")
        self.assertTrue(pump(lambda: len(self._events(lane)) == 3, 5))
        follow = next(r for r in self._events(lane) if r.kind == "follow")
        x = next(b for b in _walk(follow) if isinstance(b, Gtk.Button) and b.get_label() == "×")
        x.emit("clicked")
        self.assertTrue(pump(lambda: sorted(r.kind for r in self._events(lane)) ==
                             ["favourite", "reblog"], 5))

    def test_follow_request_answered_by_its_button(self):
        """A follow request is an event: in Activity (no Requests lane shown) with its
        two buttons; ✔ lets them in and the row goes."""
        self.world.requests.append(BOB)
        self.core.poll_once()
        pump(timeout=0.3)
        lane = self._open_lane("activity")
        self.assertTrue(pump(lambda: any(r.kind == "follow_request"
                                         for r in self._events(lane)), 5))
        row = next(r for r in self._events(lane) if r.kind == "follow_request")
        ok = [b for b in _walk(row) if isinstance(b, Gtk.Button) and
              b.get_label() == i18n._("ok_interaction")]
        self.assertEqual(len(ok), 1)
        ok[0].emit("clicked")
        self.assertTrue(pump(lambda: not self.world.requests and
                             not any(r.kind == "follow_request" for r in self._events(lane)),
                             5))

    def test_activity_chips_filter(self):
        """Activity's quick filters are its rule's switches, as any lane's: "follows"
        shows only the follows."""
        self._some_activity()
        lane = self._open_lane("activity")
        self.assertTrue(pump(lambda: len(self._events(lane)) == 3, 5))
        follows = next(k for k, w in lane.lm.chips if w == "@actf_follows")
        self.assertIn(follows, lane._filter_buttons)
        lane._filter_buttons[follows].set_active(True)
        self.assertTrue(pump(lambda: [r.kind for r in self._events(lane)] == ["follow"], 5))
        lane._filter_buttons["all"].set_active(True)
        self.assertTrue(pump(lambda: len(self._events(lane)) == 3, 5))

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

    def test_select_text_and_quote_it_in_a_reply(self):
        """As Qt: text selected in a post — right click: Quote in reply, Copy; the
        quote goes into the reply already open, where its cursor is."""
        lane = self._lane("home")
        card = next(c for c in lane.rows.values() if c.post.id == "011")
        block = card.body_block
        n = len("привет".encode())
        block.select(0, n)
        self.assertEqual(block.selected(), "привет")
        pop = card._selection_menu(block.selected(), 0, 0)
        labels = [w.get_label() for w in _walk(pop) if isinstance(w, Gtk.Button)]
        self.assertEqual(labels, [i18n._("quote_in_reply"), i18n._("copy")])
        quote = next(w for w in _walk(pop) if isinstance(w, Gtk.Button)
                     and w.get_label() == i18n._("quote_in_reply"))
        quote.emit("clicked")
        dlg = self.win.composer
        self.assertIsNotNone(dlg)
        self.assertIn("> привет", dlg._text())
        block.select(n + 1, n + 1 + len("жирно".encode()))
        again = self.win.quote_reply(card.entry, block.selected())
        self.assertIs(again, dlg)  # the same reply, the second quote in it
        self.assertIn("> жирно", dlg._text())
        dlg.close()

    def test_which_account_of_mine_got_it(self):
        """All accounts in one window: "→ @account" on the card, in its own colour."""
        from fedtail.frontends.common.lane import account_color
        from fedtail.frontends.gtk.card import Card
        card = Card(self.win.ctx, "x", self.view.by_id("011"), via="@w")
        labels = [w.get_text() for w in _walk(card) if isinstance(w, Gtk.Label)]
        self.assertTrue(any("→ @w" in t for t in labels), labels)
        self.assertRegex(account_color("@w"), r"^#[0-9a-f]{6}$")
        self.assertEqual(account_color("@w"), account_color("@W"))

    def test_messenger_themes_head_the_card_as_a_chat(self):
        """shape.card_header = "chat" (qip, mra, icq): "Name (time)" in one line, as Qt's —
        not the name, the @address and the time apart (the night of 23.10)."""

        from fedtail.frontends.gtk.card import Card
        theme = self.win.ctx.theme
        was = theme.shape, theme.words
        try:
            theme.shape = dict(was[0], card_header="chat")
            theme.words = dict(was[1], chat="{name} ({when})")
            card = Card(self.win.ctx, "x", self.view.by_id("011"))
        finally:
            theme.shape, theme.words = was
        labels = [w.get_text() for w in _walk(card) if isinstance(w, Gtk.Label)]
        post = self.view.by_id("011")
        self.assertTrue(any(t.startswith(post.author.name or post.author.handle) and "(" in t
                            for t in labels), labels)
        self.assertFalse(any(t == "@" + post.author.handle for t in labels), labels)

    def test_a_pictures_menu_saves_it(self):
        from fedtail.model import Media
        card = next(iter(self._lane("home").rows.values()))
        m = Media(card.post.ref, "image", url="https://e.test/a.png")
        asked = []
        self.win.images.save = lambda url, where: (asked.append(url), _done("/x/a.png"))[1]
        pop = card._media_menu(card, m)
        buttons = [w for w in _walk(pop) if isinstance(w, Gtk.Button)]
        self.assertEqual([b.get_label() for b in buttons],
                         [i18n._("save_image"), i18n._("open_browser"), i18n._("copy_link")])
        buttons[0].emit("clicked")
        self.assertTrue(pump(lambda: asked, 2))
        self.assertEqual(asked, ["https://e.test/a.png"])

    def test_every_widget_measures_sanely(self):
        """No widget of a card says its least height is more than its natural one at
        the width it has (GTK 4.18 warned so of the Card, 7 500 lines a bench)."""
        from fedtail.frontends.gtk.card import Card
        from fedtail.frontends.gtk.measure import report
        lane = self._lane("home")
        pump(lambda: lane.positioned and not lane._pending(), 5)
        bad = report([c for c in lane.rows.values() if c.get_mapped()], stop=Card)
        self.assertEqual(bad, [], f"GTK {Gtk.get_major_version()}."
                                  f"{Gtk.get_minor_version()}.{Gtk.get_micro_version()}")
        from fedtail.frontends.gtk.measure import boxes_418
        for size in ((1000, 700), (640, 480)):  # the whole window, wide and narrow
            self.win.set_default_size(*size)
            pump(timeout=0.4)
            self.assertEqual(boxes_418(self.win), [], f"at {size}")
        # and the tabs: a profile, a thread
        self.win.open_account("B")
        pump(lambda: "B" in self.win.accounts, 3)
        pump(timeout=0.6)
        self.assertEqual(boxes_418(self.win), [], "a profile")
        self.win.open_thread("013")
        pump(timeout=0.6)
        self.assertEqual(boxes_418(self.win), [], "a thread")
        self.win.open_search("bob")
        pump(timeout=0.6)
        self.assertEqual(boxes_418(self.win), [], "the search: people")

    def test_a_profile_pages_back_then_from_their_server(self):
        """As Qt: the posts page by page; my server out of older ones — "▼ older —
        from their server" for someone from elsewhere."""
        self.win.open_account("B")
        self.assertTrue(pump(lambda: getattr(self.win.accounts.get("B"), "posts_part",
                                             None) is not None, 5))
        part = self.win.accounts["B"].posts_part
        self.assertTrue(pump(lambda: part.cards, 5))
        self.assertTrue(all(real(c.entry).author.id == "B" or c.entry is not None
                            for c in part.cards))
        for _i in range(5):  # to the end of what my server has
            if part.older_origin:
                break
            pump(lambda: part.more_btn.get_sensitive(), 3)
            part.more_btn.emit("clicked")
            pump(timeout=0.3)
        self.assertTrue(part.older_origin)
        self.assertEqual(part.more_btn.get_label(),
                         i18n._("older_from_origin", host=part.host))

    def test_choose_answers_only_on_ok(self):
        from fedtail.frontends.gtk.dialogs import choose
        got = []
        w = choose(self.win, "t", "q", [("a", "A"), ("b", "B")], lambda *a: got.append(a))
        self.assertIsNone(w.tick)
        w.radios[1][1].set_active(True)
        w.ok.emit("clicked")
        self.assertEqual(got, [("b", False)])
        w = choose(self.win, "t", "q", [("a", "A")], lambda *a: got.append(a), check="x")
        w.close()  # closed: no answer
        self.assertEqual(len(got), 1)

    def test_profile_posts_replies_media(self):
        """Above someone's posts, as in Qt: posts (no replies to others), all, media."""
        self.world.add(status("014", BOB, "gone", "X", minute=14, text="чужой разговор"))
        pic = self.world.statuses["013"]
        pic["media_attachments"] = [{"id": "m", "type": "image", "url": "https://e.test/a.png"}]
        self.win.open_account("B")
        self.assertTrue(pump(lambda: getattr(self.win.accounts.get("B"), "posts_part",
                                             None) is not None, 5))
        part = self.win.accounts["B"].posts_part
        self.assertEqual(part.show, "posts")
        ids = lambda: sorted(real(c.entry).id for c in part.cards)  # noqa: E731
        self.assertTrue(pump(lambda: ids() == ["011"], 5), ids())
        part.show_buttons["all"].set_active(True)
        self.assertTrue(pump(lambda: ids() == ["011", "013", "014"], 5), ids())
        part.show_buttons["media"].set_active(True)
        self.assertTrue(pump(lambda: ids() == ["013"], 5), ids())
        self.assertFalse(part.show_buttons["all"].get_active())

    def test_spelling_in_the_editor(self):
        """As in Qt: the error wave under a misspelled word, the fix and "Add to
        dictionary" in the text's menu (core/spell.py, with a made-up dictionary)."""
        from unittest import mock

        from fedtail.core import spell

        from .test_spell import FakeBackend
        spell._checkers.clear()
        with mock.patch.object(spell, "_backend", FakeBackend()):
            c = self.win.compose_panel()
            c._set_language("en")
            sp = c.spell
            sp.repick()
            self.assertIsNotNone(sp.checker)
            c.buffer.set_text("Helo wrold")
            self.assertTrue(pump(lambda: sp.marked() == [(0, 4), (5, 10)], 3))
            menu = sp.menu_for(7)
            self.assertEqual(menu.get_n_items(), 2)  # the fixes, then "Add"
            fixes = menu.get_item_link(0, "section")
            self.assertEqual(fixes.get_item_attribute_value(0, "label", None).get_string(), "world")
            sp.replace("world")
            self.assertEqual(sp.text(), "Helo world")
            self.assertTrue(pump(lambda: sp.marked() == [(0, 4)], 3))
            menu = sp.menu_for(2)
            fixes = menu.get_item_link(0, "section")
            self.assertEqual(fixes.get_item_attribute_value(0, "label", None).get_string(),
                             i18n._("spell_none"))
            sp.add("Helo")
            self.assertEqual(sp.marked(), [])
            self.assertIsNone(sp.menu_for(2))  # a good word: the menu as it was
            c.close()
            self.assertEqual(sp._timer, 0)
        spell._checkers.clear()

    def test_another_servers_lane(self):
        """≡ → Another server's lane…: as in Qt — a tab of its posts, fetched into
        mine; more by the server's own cursor; a closed one says so."""
        far = [dict(status(f"8{i:02d}", BOB, minute=i, vis="public", text=f"far {i}"),
                    uri=f"https://far.example/s/{i}", id=f"f{i}") for i in range(20)]
        for s in far:  # what my server gets when it looks them up
            self.world.remote[s["uri"]] = dict(s, id="L" + s["id"])
        asked = []

        def origin(url):
            asked.append(url)
            if "closed.example" in url:
                return None  # 401 to strangers
            return far if "max_id" not in url else []
        self.core._origin_get = origin
        page = self.win.open_remote_lane("far.example")
        self.assertTrue(pump(lambda: page.remote_more.get_parent() is not None, 5))
        self.assertIs(self.win.open_remote_lane("far.example"), page)  # one tab a server
        page.remote_more.emit("clicked")
        self.assertTrue(pump(lambda: any("max_id=f19" in u for u in asked), 5))
        self.assertTrue(pump(lambda: page.remote_more.get_parent() is None, 5))  # no more
        closed = self.win.open_remote_lane("closed.example")
        self.assertTrue(pump(lambda: closed.remote_info.get_text()
                             == i18n._("remote_public_closed", host="closed.example"), 5))

    def test_rest_of_the_api(self):
        """0.20, as in Qt: a filter edited, a cover for a video, an edited post's
        descriptions, a report by the server's rules, the profile's newer switches and
        tag suggestions, the posts sharing a link, the server's terms, blocks and
        translator."""
        from fedtail.frontends.common import server, timed
        from fedtail.frontends.gtk import dialogs, postinfo

        # a filter edited: the window's answer, then saved
        made = self.core.add_filter("шум", ["крипта", "nft"]).result()
        dlg = dialogs.silence(self.win)
        self.assertTrue(pump(lambda: dlg.filters.get_row_at_index(0) is not None, 5))
        dlg.filters.select_row(dlg.filters.get_row_at_index(0))
        dlg.change_filter()  # the edit window, filled from the filter
        ed = dlg.editing
        self.assertEqual(ed.words.get_text(), "крипта, nft")
        ed.words.set_text("nft, web3")
        ed.action.set_selected(1)
        ed.ok.emit("clicked")
        self.assertTrue(pump(lambda: self.world.filters[made["id"]]["filter_action"] == "hide",
                             5))
        self.assertEqual(sorted(k["keyword"] for k in self.world.filters[made["id"]]["keywords"]),
                         ["nft", "web3"])
        self.assertEqual(timed.filter_changes("", "a, b", "warn", [], timed.KEEP),
                         {"title": None, "words": ["a", "b"], "action": "warn",
                          "contexts": ["home"], "expires_in": None})
        dlg.close()

        # a video gets a cover; it goes with it to the server (the 4th part)
        c = self.win.compose_panel()
        c.add_paths(["/tmp/clip.mp4"])
        c.pick_cover("/tmp/clip.mp4", "/tmp/cover.jpg")
        self.assertEqual(c._media_list(), [["/tmp/clip.mp4", "", None, "/tmp/cover.jpg"]])
        c.covers.clear()
        c.media.clear()

        # my post edited: its picture's description changed, the picture stays
        mine = self.world.add(status("121", ME, text="с картинкой"), home=True)
        mine["media_attachments"] = [{"id": "m7", "type": "image", "description": "старое",
                                      "url": "https://example.test/m7.png"}]
        self.core.store.put_statuses([mine])
        ed = self.win.compose_panel(edit=self.view.by_id("121"))
        self.assertTrue(pump(lambda: ed._text() == "с картинкой", 5))
        self.assertEqual(len(ed.remote), 1)
        self.assertEqual(ed.media_changes(), {})
        ed.remote[0][1].set_text("новое")
        self.assertEqual(ed.media_changes(), {"m7": ("новое", None)})
        ed.send()
        self.assertTrue(pump(lambda: self.world.statuses["121"]["media_attachments"][0]
                             .get("description") == "новое", 5))

        # a report by the server's rules: they come when "breaks the rules" is picked
        rep = postinfo.report(self.win, self.view.by_id("011"))
        rep.kind.set_selected(2)  # violation
        self.assertTrue(pump(lambda: rep.rule_ticks, 5))
        rep.send(None)  # no rule ticked: not sent
        self.assertEqual(self.world.reports, [])
        rep.rule_ticks[0][1].set_active(True)
        rep.send(None)
        self.assertTrue(pump(lambda: self.world.reports, 5))
        self.assertEqual(self.world.reports[-1][4:], ("violation", ["1"]))

        # the profile's newer switches, sent only when changed; tags to put forward
        prof = self.win.edit_profile()
        self.assertTrue(pump(lambda: prof.loaded is not None and prof.suggest_buttons, 5))
        self.assertEqual(prof.changes(), {})
        prof.hide_collections.set_active(True)
        prof.attribution.set_text("blog.example, news.example")
        self.assertEqual(prof.changes(), {"hide_collections": True,
                                          "attribution_domains": ["blog.example",
                                                                  "news.example"]})
        prof.suggest_buttons[0].emit("clicked")
        self.assertTrue(pump(lambda: "fedi" in self.world.my_tags, 5))
        prof.save()
        self.assertTrue(pump(lambda: self.world.profile_updates, 5))
        self.assertTrue(self.world.profile_updates[-1]["hide_collections"])

        # who else shared a link: a tab of their posts; none — said so
        self.world.statuses["011"]["card"] = {"url": "https://news.example/a"}
        page = self.win.open_link_posts("https://news.example/a")
        self.assertTrue(pump(lambda: page.link_more.get_parent() is not None, 5))
        empty = self.win.open_link_posts("https://nothing.example/")
        self.assertTrue(pump(lambda: empty.link_info.get_text() == i18n._("link_posts_none"),
                             5))

        # the server about itself: terms, whom it cut off, its translator
        info = self.view.server_info().result()
        page = server.server_more_html(info, lambda h: h)
        for words in (i18n._("server_terms"), "bad.example", i18n._("server_block_suspend"),
                      i18n._("server_translates", langs="en → ru, de; ru → en")):
            self.assertIn(words, page)

    def test_timed_filters_hidden_posts_and_list_replies(self):
        from fedtail.frontends.gtk import dialogs, lists
        from fedtail.protocols.mastodon import adapter
        dlg = dialogs.silence(self.win)
        dlg.words.set_text("спойлер")
        dlg.span.set_selected(2)  # a day
        dlg.add.emit("clicked")
        self.assertTrue(pump(lambda: self.world.filters, 5))
        made = next(iter(self.world.filters.values()))
        self.assertEqual(made["expires_in"], 86400)
        when = adapter.word_filter(made).expires.astimezone().strftime("%d.%m.%Y %H:%M")

        def rows():
            out, r = [], dlg.filters.get_first_child()
            while r is not None:
                out.append(r.get_child().get_label())
                r = r.get_next_sibling()
            return out
        self.assertTrue(pump(lambda: any(i18n._("filter_until", until=when) in t
                                         for t in rows()), 5), rows())
        # hide this post: in the ⋯ menu (common/actions.py), asked once
        from fedtail.frontends.common import actions
        card = self._lane("home").rows["011"]
        self.assertIn("fedtail:hidepost/011",
                      [i.url for i in actions.menu(card.entry, card._actx())])
        self.win.confirm = lambda title, text, then, yes="": then()
        self.win.on_link("fedtail:hidepost/011")
        self.assertTrue(pump(lambda: "011" in self.core.hidden_posts, 5))
        dlg.reload()
        self.assertTrue(pump(lambda: any(i18n._("posts_n", n=1) in t for t in rows()), 5),
                        rows())
        dlg.close()
        # whose replies a list shows: three radio buttons in the list's menu
        made = []
        self.win.call(self.view.create_list("Друзья"), made.append)
        self.assertTrue(pump(lambda: made and f"list:{made[0].id}" in self.win.lane_rows, 5))
        pop = lists.lane_menu(self.win, self.win.lane_rows[f"list:{made[0].id}"])
        radios = [b for b in _walk(pop) if isinstance(b, Gtk.CheckButton)
                  and b.get_label() in dict(self._policies()).values()]
        self.assertEqual(len(radios), 3)
        self.assertTrue(radios[0].get_active())  # "list", the server's default
        radios[2].set_active(True)
        self.assertTrue(pump(lambda: self.world.lists[made[0].id]["replies_policy"] == "none",
                             5))
        pop.popdown()

    @staticmethod
    def _policies():
        from fedtail.frontends.common import timed
        return timed.replies_policies()

    def test_a_group_of_tags(self):
        """Several tags typed into the search: their tab, as Qt's; "＋ to lanes" puts it
        in the sidebar, and its right-click menu takes it out."""
        from fedtail.core import taggroups
        from fedtail.frontends.gtk import lists
        spec = taggroups.parse("#linux #georgia")
        page = self.win.open_search("#linux #georgia")
        self.assertIsNotNone(page)
        save = next(w for w in _walk(page) if isinstance(w, Gtk.Button)
                    and w.get_label() == i18n._("tags_save"))
        save.emit("clicked")
        name = taggroups.lane_name(spec)
        self.assertTrue(pump(lambda: name in self.win.lane_rows, 5))
        pop = lists.lane_menu(self.win, self.win.lane_rows[name])
        drop = next(w for w in _walk(pop) if isinstance(w, Gtk.Button)
                    and w.get_label() == i18n._("tags_drop"))
        drop.emit("clicked")
        self.assertTrue(pump(lambda: name not in self.win.lane_rows, 5))

    def test_tag_tab_follows_and_features(self):
        from fedtail.frontends.gtk.people import TagRow
        page = self.win.open_tag("linux")

        def row():
            return next((w for w in _walk(page) if isinstance(w, TagRow)), None)
        self.assertTrue(pump(lambda: row() is not None, 3))
        r = row()
        self.assertEqual(r.follow.get_label(), i18n._("tag_follow"))
        r.follow.emit("clicked")
        self.assertTrue(pump(lambda: "linux" in self.world.followed_tags, 3))
        self.assertTrue(pump(lambda: r.follow.get_label() == i18n._("tag_unfollow"), 3))
        self.assertIsNotNone(r.feature)
        self.assertTrue(pump(lambda: r.feature.get_sensitive(), 3))
        r.feature.emit("clicked")
        self.assertTrue(pump(lambda: "linux" in self.world.my_tags, 3))
        self.assertTrue(pump(lambda: r.feature.get_label() == i18n._("tag_unfeature"), 3))


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkPanelsTest(_GtkBase):
    """What comes over the window: the pictures' viewer, the help; and the pictures in a
    card, the desktop notification, ≡ → Quit."""

    def _post_with_pictures(self, n):
        from fedtail.protocols.mastodon import adapter

        def offline(*_a, **_k):
            raise OSError("no network in the tests")
        self.win.images.http.get = offline
        raw = status("090", BOB, minute=30, text="картинки")
        raw["media_attachments"] = [
            {"id": f"m{i}", "type": "image", "url": f"https://e.test/{i}.png",
             "preview_url": f"https://e.test/{i}s.png", "description": f"картинка {i}",
             "meta": {"original": {"width": 800, "height": 400}}} for i in range(n)]
        return adapter.post(raw, "t")

    def test_pictures_keep_their_shape(self):
        from fedtail.frontends.gtk.card import Card
        one = Card(self.win.ctx, "090", self._post_with_pictures(1))
        grid = one.media_box
        cell = grid.get_child_at(0, 0)
        w, h = cell.w, cell.h  # the box it asks for (fit_box): narrower with the window
        # one alone: as tall as ui.image_height allows within the lane, its shape kept
        self.assertGreater(h, 300)
        self.assertEqual(w, 2 * h)
        V = Gtk.Orientation.VERTICAL
        self.assertEqual(cell.measure(V, w // 2)[1], h // 2)  # half as wide: half as tall
        self.assertLess(cell.measure(Gtk.Orientation.HORIZONTAL, -1)[0], 200)
        four = Card(self.win.ctx, "091", self._post_with_pictures(4))
        self.assertIsNotNone(four.media_box.get_child_at(2, 0))  # three in a row
        self.assertIsNotNone(four.media_box.get_child_at(0, 1))
        self.assertEqual(four.media_box.get_child_at(0, 0).h, 115)

    def test_the_player_over_the_window(self):
        """A video: the player over the window, its keys as Qt's (no media backend
        here: it is built and driven all the same); without one — the browser."""
        from fedtail.frontends.gtk import player
        from fedtail.model import Media
        ref = self.view.by_id("011").ref
        vids = [Media(ref, "video", url="https://e.test/a.mp4"),
                Media(ref, "gifv", url="https://e.test/b.mp4")]
        opened = []
        self.win.open_url = opened.append
        if not player.available():
            self.assertIsNone(self.win.play_media(vids, 0))
            self.assertEqual(opened, ["https://e.test/a.mp4"])
        p = player.VideoPlayer(self.win, vids, 0)
        self.assertIs(self.win.player, p)
        self.assertTrue(p.next_btn.get_visible())
        self.assertTrue(p.pause_btn.get_visible())  # as Qt's: ⏸ in the bar
        self.assertEqual(p.keys.get_text(), i18n._("player_keys_many"))
        p.toggle_pause()
        self.assertEqual(p.pause_btn.get_label(), "⏸" if p.stream.get_playing() else "▶")
        p.go(1)  # the gifv: a silent loop
        self.assertTrue(p.stream.get_loop())
        self.assertTrue(p.stream.get_muted())
        self.assertFalse(p.pause_btn.get_visible())  # a gif: no pause, no sound
        self.assertEqual(p.keys.get_text(), i18n._("gif_keys_many"))
        p.toggle_mute()
        self.assertFalse(p.stream.get_muted())
        p.open_outside()
        self.assertEqual(opened[-1], "https://e.test/b.mp4")
        from gi.repository import Gdk
        self.assertTrue(p._key(None, Gdk.KEY_Escape, 0, 0))
        self.assertIsNone(self.win.player)

    def test_viewer_over_the_window(self):
        from fedtail.frontends.gtk import viewer
        media = list(self._post_with_pictures(3).media)
        v = viewer.show(self.win, media, 1)
        self.assertIs(v.get_parent(), self.win.overlay)
        self.assertIn("2 / 3", v.caption.get_text())
        v.go(1)
        self.assertEqual(v.i, 2)
        v.go(1)
        self.assertEqual(v.i, 0)
        v._set_actual(True)
        self.assertTrue(v.actual)
        # Esc with the keys elsewhere (the card clicked to open it): the viewer goes, the
        # tabs and lanes under it stay
        pages = self.win.tabs.get_current_page()
        from gi.repository import Gdk as _Gdk
        self.assertTrue(self.win._key(None, _Gdk.KEY_Escape, 0, 0))
        self.assertTrue(v.closed)
        self.assertEqual(self.win.tabs.get_current_page(), pages)
        self.assertFalse(self.win.curtain_shown())
        v = viewer.show(self.win, media, 1)
        v.close()
        self.assertIsNone(v.get_parent())
        self.assertIsNone(self.win.viewer)
        self.win.cfg["ui"]["image_viewer"] = "browser"
        opened = []
        self.win.open_url = opened.append
        self.assertIsNone(viewer.show(self.win, media, 0))
        self.assertEqual(opened, ["https://e.test/0.png"])

    def test_help_is_a_panel_in_the_window(self):
        before = set(Gtk.Window.list_toplevels())
        panel = self.win.open_help()
        pump(timeout=0.3)
        self.assertIs(panel.get_parent(), self.win.overlay)
        self.assertEqual(set(Gtk.Window.list_toplevels()), before)  # no window of its own
        self.assertEqual(panel.current, "index")
        self.assertTrue(panel.blocks)
        from fedtail.frontends import helpdocs
        other = next(p.name for p in helpdocs.pages() if p.name != "index")
        panel.show_page(other)
        self.assertEqual(panel.current, other)
        panel.back()
        self.assertEqual(panel.current, "index")
        panel.search.set_text("тема")
        panel._filter("тема")
        self.assertTrue(panel.found.get_visible())
        panel.close()
        self.assertFalse(panel.get_visible())
        self.assertIs(self.win.open_help(), panel)  # the same one, back where it was
        self.assertTrue(panel.get_visible())

    def test_notification_goes_out(self):
        from fedtail.frontends import notifytext
        sent = []

        class App:
            def send_notification(self, _id, n):
                sent.append(n)
        n = self.win.notifier
        n.app, n.backend = App(), "gio"
        n.show(notifytext.Note("t", "b", "home"))
        self.assertEqual(len(sent), 1)

    def test_quit_quits(self):
        # ≡ → Quit: the menu's action (run once the menu has gone), as a click on it does
        self.assertTrue(self.win.activate_action("win.quit", None))
        pump(timeout=0.3)
        self.assertTrue(self.win.quitting)
        self.assertFalse(self.win.get_visible())


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkSplitTest(_GtkBase):
    """ui.layout = "split": the roster window, the lanes in tabs, the input line."""
    UI = {"layout": "split"}

    def test_last_tab_closed_the_window_goes(self):
        """The last tab closed: the messages window hides, the roster stays (as Qt's);
        opening something from the roster brings it back."""
        win = self.win
        win.present()
        pump(lambda: "home" in win.lane_tabs, 5)
        for name in list(win.lane_tabs):
            win.close_lane_tab(name)
        for key in list(getattr(win, "extra_tabs", {})):
            win.close_extra(key)
        for root in list(win.threads):
            win.close_thread(root)
        self.assertTrue(pump(lambda: not win.get_visible(), 3))
        self.assertTrue(win.roster.get_visible())
        win.roster.open("home")
        self.assertTrue(pump(lambda: win.get_visible() and "home" in win.lane_tabs, 3))

    def test_menus_made_ahead_open_on_one_click(self):
        """≡ in the roster: its popover made ahead (as after start), so one click opens it
        — built on the click, the release after a long build closed it again."""
        btns = list(self.win.menu.buttons)
        self.assertGreaterEqual(len(btns), 2)  # the roster's ≡ and its accounts at least
        for b, make in btns:
            make(b)
            self.assertIsNotNone(b.get_popover())
        b = self.win.roster.menu_btn
        b.popup()
        self.assertTrue(pump(lambda: b.get_popover().get_mapped(), 3))
        b.popdown()

    def test_a_contact_card_on_hover(self):
        """As QIP (and Qt's split layout): who this is, beside the face."""
        from dataclasses import replace

        from fedtail.frontends.gtk import contact
        from fedtail.model import Relationship
        bob = replace(self.view.by_id("011").author, posts=12, followers=3, following=4,
                      note="<p>пишу про роутеры</p>")
        self.view.relation_known = lambda _id: Relationship(following=True,
                                                            followed_by=True)
        words = [t for t, _css in contact.lines(self.view, bob, self.win.theme.date)]
        self.assertEqual(words[0], "@" + bob.handle)
        self.assertIn(i18n._("faces_mutual"), words)
        self.assertIn("пишу про роутеры", words)
        self.assertIn(i18n._("card_counts", posts=12, followers=3, following=4), words)
        box = contact.card(self.win, bob)
        self.assertTrue(any(isinstance(w, Gtk.Label) and w.get_text() == "пишу про роутеры"
                            for w in _walk(box)))
        state = contact.hover(self.win, self.win.dock.face, lambda: bob)
        self.assertIsNone(state["pop"])

    def test_roster_tabs_and_the_input_line(self):
        win = self.win
        self.assertIsNotNone(win.roster)
        self.assertTrue(win.roster.get_visible())
        self.assertFalse(win.stack.get_visible())
        pump(lambda: win.roster.rows, 5)
        self.assertIn("home", win.roster.rows)
        self.assertIn("home", win.lane_tabs)  # the start lane: a tab of its own
        lane = win.lane_tabs["home"]
        self.assertTrue(win.lane_on_screen("home"))
        win.roster.open("to_me")  # a lane of the set (fedtail's: "To me", not "replies")
        pump(timeout=0.3)
        self.assertIn("to_me", win.lane_tabs)
        self.assertTrue(win.lane_on_screen("to_me"))
        win.close_lane_tab("to_me")
        self.assertNotIn("to_me", win.lane_tabs)
        # the input line: a new post over a lane; a reply when the card's button says so
        win.tabs.set_current_page(win.tabs.page_num(lane))
        pump(timeout=0.2)
        dock = win.dock
        self.assertIsNone(dock.target)
        post = self.view.by_id("011")
        win.compose(reply_to=post)  # the card's Reply: into the input line, not a window
        self.assertEqual(dock.target.id, "011")
        self.assertTrue(dock._text().startswith("@bob"))
        dock.buffer.insert_at_cursor("ответ снизу")
        before = len(self.world.posted)
        dock.send()
        self.assertTrue(pump(lambda: len(self.world.posted) > before, 5))
        self.assertEqual(self.world.posted[-1][2], "011")
        # a command goes to the command line, a post doesn't
        dock._set_text("#zz9 привет")
        self.assertIsNotNone(dock.command())
        dock._set_text("@bob привет")
        self.assertIsNone(dock.command())
        # a private talk: its tab, written to privately
        bob = post.author
        win.write_to(bob)
        pump(timeout=0.3)
        self.assertIn("talk:" + bob.id, win.extra_tabs)
        self.assertEqual(dock.visibility, "direct")
        # the author bar follows what's read
        win.tabs.set_current_page(win.tabs.page_num(lane))
        pump(timeout=0.3)
        win._follow_author(lane)
        if win.author_bar is not None:
            self.assertTrue(win.author_bar.who is None or win.author_bar.who.id)
        # another theme: the lanes' tabs drawn anew, in their places
        win.try_theme("psi")
        pump(timeout=0.3)
        self.assertIn("home", win.lane_tabs)
        self.assertIsNot(win.lane_tabs["home"], lane)
        self.assertTrue(win.lane_on_screen("home"))
        lane = win.lane_tabs["home"]
        # the tabs: in rows of chips, one a page (the lanes' stack none)
        rows = win.tab_rows
        self.assertIsNotNone(rows)
        rows.sync()
        self.assertEqual(set(rows.chips), set(rows.pages()))
        self.assertNotIn(win.stack, rows.chips)
        self.assertFalse(win.tabs.get_show_tabs())
        n = len(rows.chips)
        rows.close(win.extra_tabs["talk:" + bob.id])
        pump(timeout=0.3)
        self.assertEqual(len(rows.chips), n - 1)
        # the roster's look and folds
        win.roster.set_look("compact", True)
        win.roster.toggle("standard")
        win.roster.toggle("standard")
        # closing the messages window keeps the roster
        win.close()
        pump(timeout=0.2)
        self.assertFalse(win.get_visible())
        self.assertTrue(win.roster.get_visible())


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkPicturesTest(_GtkBase):
    """The theme's own set in the split layout: its pictures on the buttons, the
    messengers' too (psi: PNGs — drawn even where gdk-pixbuf reads no SVG)."""
    UI = {"layout": "split", "theme": "psi"}

    def test_theme_pictures_on_the_buttons(self):
        from fedtail.frontends.gtk import icons
        win = self.win
        self.assertEqual(icons.how(win.theme), "own")
        self.assertTrue(icons.wanted(win.theme))
        self.assertIsInstance(win.dock.send_btn.get_child(), Gtk.Box)  # picture + "Send"
        self.assertIsInstance(win.dock.cw_btn.get_child(), Gtk.Image)
        lane = win.lane_tabs["home"]
        card = next(iter(lane.rows.values()))
        pictures = [w for w in _walk(card.actions) if isinstance(w, Gtk.Image)]
        self.assertTrue(pictures)  # Reply, Favourite… with their pictures
        self.assertIsNotNone(icons.nobody(win.theme, 36))
        win.try_theme("terminal")  # no pictures: the words come back
        self.assertEqual(icons.how(win.theme), "words")
        self.assertEqual(win.dock.send_btn.get_label(), i18n._("dock_send"))
        self.assertIsNone(icons.image("menu", win.theme))
        win.try_theme("system")  # the desktop's, by freedesktop names
        self.assertEqual(icons.how(win.theme), "desktop")


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkAgentTest(_GtkBase):
    """The split layout in a Mail.ru Agent theme: a face column beside the posts."""
    UI = {"layout": "split", "theme": "mra"}

    def test_agent_face(self):
        win = self.win
        self.assertIsNone(win.author_bar)
        face = win.agent_face
        self.assertIsNotNone(face)
        self.assertTrue(face.get_visible())
        pump(lambda: "home" in win.lane_tabs, 5)
        lane = win.lane_tabs["home"]
        win.tabs.set_current_page(win.tabs.page_num(lane))
        pump(lambda: getattr(lane, "positioned", True), 5)
        win._follow_author(lane)
        self.assertIsNotNone(face.who)  # someone's face, never an empty frame
        bob = self.view.by_id("011").author
        win.write_to(bob)  # a talk: whom I talk to
        pump(timeout=0.3)
        win._follow_author()
        self.assertEqual(face.who.id, bob.id)
        self.assertTrue(face.name.get_text())


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
class GtkImagesTest(unittest.TestCase):
    """common/images.py with GTK's pictures: read small, to disk, from disk."""

    def test_a_picture_comes_small_and_is_kept_on_disk(self):
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf

        from fedtail.frontends.gtk import images

        pix = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 300, 200)
        pix.fill(0x336699FF)
        ok, data = pix.save_to_bufferv("png", [], [])
        self.assertTrue(ok)
        tex = images.decode(bytes(data), 100)
        self.assertEqual((tex.get_width(), tex.get_height()), (100, 67))
        self.assertIsNone(images.decode(b"not a picture", 100))

        class Resp:
            headers = {"Content-Type": "image/png"}
            is_redirect = False

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def raise_for_status(self):
                pass

            def iter_content(self, _size):
                yield bytes(data)

            def close(self):
                pass

        class Bridge:
            def call(self, future, ok=None, fail=None):
                future.add_done_callback(lambda f: GLib.idle_add(
                    lambda: (ok(f.result()) if ok else None) and False))
                return future

        with tempfile.TemporaryDirectory() as tmp:
            core = type("C", (), {"cfg": {"ui": {}}, "_own_hosts": lambda self: set(),
                                  "paths": type("P", (), {"cache_dir": Path(tmp)})()})()
            imgs = images.Images(core, Bridge())
            imgs.http.get = lambda url, timeout, **_kw: Resp()
            got = []
            try:
                imgs.get("https://media.example/a.png", got.append, max_side=50)
                self.assertTrue(pump(lambda: got, 5))
                self.assertEqual(got[0].get_width(), 50)
                self.assertTrue(imgs.local("https://media.example/a.png"))  # on disk now
                # one picture asked at two sizes at once: downloaded once (the night of
                # 22.10: twice, both to a 120 s timeout)
                import threading
                calls, out = [], []

                def slow_get(url, timeout, **_kw):
                    calls.append(url)
                    time.sleep(0.3)
                    return Resp()
                imgs.http.get = slow_get
                b = "https://media.example/b.png"
                ts = [threading.Thread(target=lambda side=side: out.append(
                    imgs._download(b, side))) for side in (40, 80)]
                for t in ts:
                    t.start()
                for t in ts:
                    t.join(5)
                self.assertEqual(len(calls), 1)
                self.assertEqual(sorted(x.get_width() for x in out), [40, 80])
            finally:
                imgs.shutdown()


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
