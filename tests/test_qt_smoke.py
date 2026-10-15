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
        self.win.images.get = lambda url, cb, *a, **k: None  # no network in tests
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

    def bridge_wait(self, fut):
        self.pump(until=fut.done)
        return fut.result()

    def test_whole_flow(self):
        from fedtail.frontends.qt.compose import Compose
        from fedtail.frontends.qt.feed import LaneWidget, ThreadWidget

        self.win.start()
        self.pump(until=lambda: self.core.me is not None and "people" in self.win.lane_widgets)
        self.core.poll_once()
        lane = self.win.lane_widgets["people"]
        posts = lambda v: [r for r in v.rows.values() if r.status_id is not None]
        self.pump(until=lambda: len(posts(lane.view)) == 4)  # bot is not in "people"
        self.assertIn("__sep__", lane.view.rows)  # "new below" after my own (read) post
        badge = self.win.lane_items["people"].badge
        self.assertTrue(badge.isVisible() or badge.text())  # unread badge
        self.assertEqual(badge.text(), "3")
        from PySide6.QtWidgets import QToolButton
        buttons = lane.view.rows["011"].findChildren(QToolButton)
        self.assertGreaterEqual(len(buttons), 4)  # reply, fav, thread, open (+ boost if public)
        self.assertTrue(any(b.text().startswith("Ответить") for b in buttons))

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

        # the content warning field hides until asked for
        dlg = Compose(self.win)
        dlg.show()
        self.assertFalse(dlg.cw.isVisible())
        dlg.cw_btn.setChecked(True)
        self.assertTrue(dlg.cw.isVisible())
        dlg.reject()

        # dropped / pasted pictures become attachments, once each, within the limit
        from PySide6.QtCore import QMimeData, QUrl
        from PySide6.QtGui import QColor, QImage

        from fedtail.frontends.qt.compose import media_paths, save_image
        img = QImage(40, 30, QImage.Format.Format_RGB32)
        img.fill(QColor("#2a86c4"))
        saved = save_image(self.core, img)
        self.assertTrue(saved and saved.endswith(".png"))
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(saved), QUrl.fromLocalFile("/tmp/notes.txt")])
        self.assertEqual(media_paths(mime), [saved])
        dlg = Compose(self.win, attach=[saved])
        dlg.show()
        self.assertEqual(dlg.media.count(), 1)
        self.assertTrue(dlg._take(mime))
        self.assertEqual(dlg.media.count(), 1)  # the same file isn't added twice
        raw = QMimeData()
        raw.setImageData(img)
        self.assertTrue(dlg._take(raw))
        self.assertEqual(dlg.media.count(), 2)
        dlg.reject()
        self.core.delete_draft(dlg.key)
        self.pump(0.1)

        # Esc closes too
        dlg = Compose(self.win)
        dlg.show()
        dlg.reject()
        self.assertFalse(dlg.isVisible())

        # Esc: first the find bar, then the whole window goes off the screen
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtWidgets import QApplication

        def esc():
            for t in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                QApplication.sendEvent(self.win, QKeyEvent(t, Qt.Key.Key_Escape,
                                                           Qt.KeyboardModifier.NoModifier))
        self.win.find_bar.open()
        esc()
        self.assertFalse(self.win.find_bar.isVisible())
        self.assertTrue(self.win.isVisible() and not self.win.isMinimized())
        esc()
        self.pump(0.1)
        self.assertTrue(not self.win.isVisible() or self.win.isMinimized())
        self.win.showNormal()
        self.pump(0.1)

        # a picture that won't load: the preview is tried, then the card says so
        from PySide6.QtGui import QImage

        from fedtail.frontends.qt.images import Images
        imgs = Images(self.core, self.win.bridge)
        good = QImage(8, 8, QImage.Format.Format_RGB32)

        def fake_download(url, _side):
            if "broken" in url:
                raise OSError("timeout")
            return good
        imgs._download = fake_download
        got, failed = [], []
        imgs.get("https://x/broken.png", got.append, failed=lambda: failed.append(1))
        imgs.get("https://x/ok.png", got.append, failed=lambda: failed.append(1))
        self.pump(until=lambda: failed and got)
        self.assertEqual((len(got), len(failed)), (1, 1))

        # lists: a block under the lanes, a lane each, ticks in a post's menu
        from PySide6.QtWidgets import QMenu
        self.bridge_wait(self.core.create_list("Друзья", add="B"))
        self.pump(until=lambda: any(n.startswith("list:") for n in self.win.lane_items))
        name = next(n for n in self.win.lane_items if n.startswith("list:"))
        self.win.select_lane(name)
        self.pump(0.2)
        self.assertEqual(self.win.lane_widgets[name].header.title.text().strip("= "),
                         "Друзья")
        menu = QMenu()
        self.win.fill_list_menu(menu, {"id": "B"})
        ticks = [a for a in menu.actions() if a.isCheckable()]
        self.assertEqual([(a.text(), a.isChecked()) for a in ticks], [("Друзья", True)])
        self.bridge_wait(self.core.delete_list(name[len("list:"):]))
        self.pump(until=lambda: name not in self.win.lane_items)
        self.win.select_lane("people")

        # activity: favourites of one post gather in one row
        from fedtail.frontends.qt.feed import ActivityWidget
        mine = self.core.store.get_status("012") or {"id": "012"}
        self.world.act("x1", "favourite", fakes.BOB, mine, minute=1)
        self.world.act("x2", "favourite", fakes.NEWS, mine, minute=2)
        self.world.act("x3", "follow", fakes.NEWS, minute=3)
        self.core.poll_once()  # first fetch of activity: history
        self.world.act("x4", "reblog", fakes.BOB, mine, minute=4)
        self.core.poll_once()
        self.pump(0.2)
        self.assertEqual(self.core.activity_unread(), 1)
        groups = ActivityWidget.groups(self.core.activity_entries())
        self.assertEqual([(g["key"][0], len(g["entries"])) for g in groups],
                         [("reblog", 1), ("follow", 1), ("favourite", 2)])
        self.win.select_lane("activity")
        self.pump(0.2)
        self.assertIsInstance(self.win.lane_widgets["activity"], ActivityWidget)
        self.win.select_lane("people")

        # my profile: a tab with an edit button; the editor sends only what changed
        from fedtail.frontends.qt.profile import ProfileDialog
        self.win.open_my_profile()
        mine = self.win.tabs.currentWidget()
        self.assertTrue(mine.mine)
        dlg = ProfileDialog(self.win)
        dlg.show()
        self.pump(until=lambda: dlg.save_btn.isEnabled())
        self.assertEqual(dlg.bio.toPlainText(), "о себе")
        self.assertEqual(dlg.field_edits[0][1].text(), "x.org")
        self.assertEqual(dlg.changes(), {})
        dlg.name.setText("Вереск Новый")
        dlg.locked.setChecked(True)
        self.assertEqual(dlg.changes(), {"display_name": "Вереск Новый", "locked": True})
        dlg.save()
        self.pump(until=lambda: self.world.profile_updates and not dlg.isVisible())
        self.pump(until=lambda: "Вереск Новый" in self.win.account_name.text())
        self.win.close_tab(self.win.tabs.currentIndex())

        # a thread can be followed from its header
        self.win.on_link("fedtail:thread/013")
        thread = self.win.tabs.currentWidget()
        self.pump(until=lambda: thread.sub_btn.isEnabled())
        was = thread.sub_btn.isChecked()
        thread.sub_btn.click()
        self.pump(until=lambda: thread.sub_btn.isEnabled() and
                  thread.sub_btn.isChecked() != was)
        self.assertEqual(self.core.subscribed(thread.root), not was)
        self.win.close_tab(self.win.tabs.currentIndex())

        # Ctrl+F finds posts in the lane on screen and marks the one it stands on
        self.win.select_lane("people")
        self.pump(0.2)
        from fedtail.core.model import snippet
        view = self.win.current_view()
        self.assertIs(view, self.win.lane_widgets["people"].view)
        key = next(k for k in view.order if view.rows[k].status_id)
        word = snippet(view.rows[key].spec.status).split()[0]
        bar = self.win.find_bar
        bar.open()
        bar.edit.setText(word.upper())
        bar.search(jump=True)
        self.assertIn(key, bar.hits)
        self.assertEqual(view.rows[bar.hits[bar.pos]].card.property("found"), "true")
        bar.edit.setText("нет-такого-слова-нигде")
        bar.search(jump=True)
        self.assertEqual(bar.hits, [])
        bar.close_bar()
        self.assertFalse(bar.isVisible())

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

        # pictures open over the main window, fitted to it
        from PySide6.QtGui import QPixmap

        from fedtail.frontends.qt.viewer import ImageOverlay
        pic = self.core.store.get_status("013")["media_attachments"]
        self.win.show_images(pic, 0)
        ov = self.win.findChild(ImageOverlay)
        self.assertIsNotNone(ov)
        self.assertEqual(ov.geometry(), self.win.rect())
        ov._loaded(0, QPixmap(3000, 2000))
        r = ov.image_rect()  # a huge picture is fitted into the window
        self.assertLessEqual(r.width(), self.win.width())
        self.assertLessEqual(r.height(), self.win.height())
        ov._loaded(0, QPixmap(200, 100))
        self.assertEqual(ov.image_rect().width(), 400)  # small ones grow, up to 2x
        ov.toggle_actual()
        self.assertEqual(ov.image_rect().width(), 200)
        ov.close_viewer()
        self.assertFalse(ov.isVisible())

    def test_lane_opens_where_reading_stopped(self):
        """All read → stand at the newest; some unread → at the first unread.
        Long posts make Qt lay out in several passes: the position must survive that."""
        long_text = "длинный пост " * 120
        for i in range(60):
            self.world.local.append(status(f"5{i:02d}", BOB, minute=i % 60, text=long_text))
            self.world.add(status(f"6{i:02d}", NEWS, minute=i % 60, text=long_text), home=True)
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.core.poll_once()
        local = [st["id"] for _, st in self.core.lane_entries("local")]
        self.core.mark_read(local)
        bots = [st["id"] for _, st in self.core.lane_entries("bots")]
        self.core.mark_read(bots[:-20])  # 20 newest stay unread

        self.win.select_lane("local")
        view = self.win.lane_widgets["local"].view
        self.pump(2.5)
        sb = view.verticalScrollBar()
        self.assertGreater(sb.maximum(), 0)
        self.assertEqual(sb.value(), sb.maximum())

        self.win.select_lane("bots")
        view = self.win.lane_widgets["bots"].view
        self.pump(1.0)  # well before reading kicks in
        first_unread = view.rows[view.unread_keys()[0]]
        top = view._top(first_unread) - view.verticalScrollBar().value()
        self.assertTrue(-20 < top < 90, top)  # just under the "new below" divider
        self.assertIn("__sep__", view.rows)

    def test_terminal_theme(self):
        from fedtail.frontends.qt import theme as themes
        cfg, _ = config.validate({"ui": {"theme": "terminal"}})
        t = themes.apply(self.app, cfg)
        self.assertEqual(t.bg, "#000000")


if __name__ == "__main__":
    unittest.main()
