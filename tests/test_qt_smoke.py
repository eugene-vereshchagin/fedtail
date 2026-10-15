"""Drive the real Qt window against the fake API, offscreen.

Skipped when PySide6 is not installed (CI installs it).
"""

import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

from fedtail import i18n  # noqa: E402
from fedtail.core import auth, config, paths  # noqa: E402
from fedtail.core.app import Core  # noqa: E402

from . import fakes  # noqa: E402
from .fakes import BOB, ME, NEWS, FakeApi, status  # noqa: E402


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class QtSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from fedtail.frontends.qt import theme as themes
        from fedtail.frontends.qt.bridge import Bridge
        from fedtail.frontends.qt.window import MainWindow

        i18n.setup("ru")
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        FakeApi.world = w = fakes.World()
        mine = w.add(status("010", ME, minute=10, text="мой пост"), home=True)
        w.add(status("011", BOB, minute=11, text="привет"), home=True)
        w.add(status("012", NEWS, minute=12, text="новости"), home=True)
        pic = status("013", BOB, mine["id"], "ME", minute=13, text="коммент")
        pic["media_attachments"] = [{"type": "image", "url": "https://example.test/a.png",
                                     "preview_url": "https://example.test/a_s.png",
                                     "meta": {"small": {"width": 400, "height": 300}}}]
        pic["spoiler_text"] = "осторожно"
        w.add(pic, home=True, mention=True)
        w.add(status("014", BOB, "gone", "X", minute=14, text="чужой разговор"), home=True)
        self.world = w

        cfg, _ = config.validate({"feed": {"first_run_mark_read": False}})
        p = paths.resolve("t", config=str(tmp / "c.toml"), data=str(tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        self.core = Core(cfg, p, api_class=FakeApi)
        self.bridge = Bridge(self.core)
        self.theme = themes.apply(self.app, cfg)
        self.win = MainWindow(self.core, self.bridge, self.theme)
        self.win.images.get = lambda url, cb, *a: None  # no network in tests
        self.win.show()

    def tearDown(self):
        self.win.quitting = True
        self.win.tray = None
        self.win.hide()
        self.win.deleteLater()
        self.core.shutdown()
        self.pump(0.1)
        self._tmp.cleanup()

    def pump(self, seconds=0.0, until=None, timeout=5.0):
        end = time.time() + (timeout if until else seconds)
        while time.time() < end:
            self.app.processEvents()
            if until and until():
                return True
            time.sleep(0.01)
        if until:
            self.fail("condition not reached")
        return True

    def test_whole_flow(self):
        from fedtail.frontends.qt.compose import Compose
        from fedtail.frontends.qt.feed import LaneWidget, ThreadWidget

        self.win.start()
        self.pump(until=lambda: self.core.me is not None and "people" in self.win.lane_widgets)
        self.core.poll_once()
        lane = self.win.lane_widgets["people"]
        self.pump(until=lambda: len(lane.view.rows) == 4)  # bot is not in "people"
        self.assertIn("(", self.win.sidebar.item(0).text())  # unread badge

        # reply context strip gets filled in once parents arrive
        self.pump(until=lambda: self.core.parent_of(self.core.store.get_status("014")) == "missing")
        self.win.select_lane("bots")
        bots = self.win.lane_widgets["bots"]
        self.assertIsInstance(bots, LaneWidget)
        self.assertEqual(len(bots.view.rows), 1)

        self.win.select_lane("comments")
        self.assertEqual(len(self.win.lane_widgets["comments"].view.rows), 1)
        self.win.select_lane("requests")

        # thread opens as a tab, as a tree
        self.win.on_link("fedtail:thread/013")
        tab = self.win.tabs.currentWidget()
        self.assertIsInstance(tab, ThreadWidget)
        self.pump(until=lambda: len(tab.view.rows) == 2)
        self.assertEqual(tab.view.rows["013"].spec.depth, 1)

        # fav updates the card everywhere
        self.win.on_link("fedtail:fav/011")
        self.pump(until=lambda: self.core.store.get_status("011")["favourited"])

        # mark all read
        lane.mark_all_read()
        self.pump(until=lambda: self.core.unread_count("people") == 0)

        # reply with a draft that survives closing the window
        # (the dialogs are really shown: a hidden QDialog closes differently,
        #  which is how "Sending…" got stuck on screen once)
        dlg = Compose(self.win, self.core.store.get_status("013"))
        dlg.show()
        self.assertTrue(dlg.text.toPlainText().startswith("@bob@mastodon.social"))
        self.assertEqual(dlg.vis.currentData(), "private")
        dlg.text.setPlainText("@bob@mastodon.social ага")
        dlg.close()  # the window's X
        self.assertFalse(dlg.isVisible())
        self.assertEqual(self.core.get_draft("reply:013")["text"], "@bob@mastodon.social ага")
        dlg = Compose(self.win, self.core.store.get_status("013"))
        dlg.show()
        self.assertEqual(dlg.text.toPlainText(), "@bob@mastodon.social ага")
        dlg.send()
        self.pump(until=lambda: self.world.posted)
        self.pump(until=lambda: not dlg.isVisible())
        self.pump(until=lambda: self.core.get_draft("reply:013") is None)
        self.assertEqual(self.world.posted[-1][2], "013")

        # a new post: the dialog closes and the post opens as a thread
        dlg = Compose(self.win)
        dlg.show()
        dlg.text.setPlainText("новый пост")
        dlg.send()
        self.pump(until=lambda: not dlg.isVisible())
        self.assertEqual(self.world.posted[-1][:3], ("новый пост", "private", None))

        # Esc closes too
        dlg = Compose(self.win)
        dlg.show()
        dlg.reject()
        self.assertFalse(dlg.isVisible())

        # "posts only" hides replies, and remembers it
        self.win.select_lane("people")
        people = self.win.lane_widgets["people"]
        people.only_posts.setChecked(True)
        self.pump(0.1)
        self.assertNotIn("013", [r.status_id for r in people.view.rows.values()])
        self.assertTrue(self.core.posts_only("people"))
        people.only_posts.setChecked(False)
        self.pump(0.1)
        self.assertIn("013", [r.status_id for r in people.view.rows.values()])

        # pictures open in our own viewer
        from fedtail.frontends.qt.viewer import ImageViewer
        pic = self.core.store.get_status("013")["media_attachments"]
        self.win.show_images(pic, 0)
        viewers = [w for w in self.app.topLevelWidgets()
                   if isinstance(w, ImageViewer) and w.isVisible()]
        self.assertEqual(len(viewers), 1)
        from PySide6.QtGui import QPixmap
        pm = QPixmap(3000, 2000)
        viewers[0].canvas.set_pixmap(pm)
        r = viewers[0].canvas._target()  # a huge picture is fitted into the window
        self.assertLessEqual(r.width(), viewers[0].canvas.width() + 1)
        self.assertLessEqual(r.height(), viewers[0].canvas.height() + 1)
        viewers[0].canvas.toggle_actual()
        self.assertEqual(viewers[0].canvas._target().width(), 3000)
        viewers[0].accept()
        self.assertFalse(viewers[0].isVisible())

    def test_terminal_theme(self):
        from fedtail.frontends.qt import theme as themes
        cfg, _ = config.validate({"ui": {"theme": "terminal"}})
        t = themes.apply(self.app, cfg)
        self.assertEqual(t.bg, "#000000")


if __name__ == "__main__":
    unittest.main()
