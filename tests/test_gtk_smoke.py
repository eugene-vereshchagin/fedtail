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
        self.assertIsInstance(reply.get_first_child().get_next_sibling().get_next_sibling(),
                              (Gtk.Expander, Gtk.Label))

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
        self.win.on_link("fedtail:account/1")
        self.assertEqual(opened, ["https://e.test/x"])
        self.assertTrue(self.win.status_line.get_text())

    def test_like_updates_the_card(self):
        lane = self._lane("home")
        card = next(c for c in lane.rows.values() if c.post.id == "011")
        self.win.act("like", card.post)
        self.assertTrue(pump(lambda: card.post.mine.liked, 5))


def _cards(win):
    from fedtail.frontends.gtk.window import _cards as cards
    for page in win.threads.values():
        yield from cards(page)


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
