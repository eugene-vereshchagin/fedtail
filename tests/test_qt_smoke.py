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


def gone(w):
    """Closed, or already deleted by Qt after closing (that's fine too)."""
    try:
        return not w.isVisible()
    except RuntimeError:
        return True


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
        self.pump(until=lambda: gone(dlg))
        self.pump(until=lambda: self.core.get_draft("reply:013") is None)
        self.assertEqual(self.world.posted[-1][2], "013")

        # a new post: the dialog closes and the post opens as a thread
        dlg = Compose(self.win)
        dlg.show()
        dlg.text.setPlainText("новый пост")
        self.assertEqual(dlg.lang.currentData(), "")  # post.language = "": as in settings
        self.assertEqual([dlg.lang.itemData(i) for i in range(dlg.lang.count())],
                         ["", "ru", "en", "ka", "uk"])
        dlg.set_language("ka")
        dlg.send()
        self.pump(until=lambda: gone(dlg))
        self.assertEqual(self.world.posted[-1][:3], ("новый пост", "private", None))
        self.assertEqual(self.world.languages[-1], "ka")

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

        # Esc: first the find bar, then every lane closes behind the curtain; nothing
        # is marked read meanwhile; a click on a lane (or Enter) opens it again
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtWidgets import QApplication

        def key(k):
            for t in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                QApplication.sendEvent(self.win, QKeyEvent(t, k, Qt.KeyboardModifier.NoModifier))

        def esc():
            key(Qt.Key.Key_Escape)
        self.win.select_lane("people")
        self.win.find_bar.open()
        esc()
        self.assertFalse(self.win.find_bar.isVisible())
        self.assertFalse(self.win.curtain_shown())
        esc()
        self.pump(0.1)
        self.assertTrue(self.win.curtain_shown())
        self.assertTrue(self.win.isVisible())
        self.assertIsNone(self.core._active_lane)
        self.assertFalse(self.win.lane_widgets["people"].view.isVisible())  # nothing "seen"
        key(Qt.Key.Key_Return)
        self.pump(0.1)
        self.assertFalse(self.win.curtain_shown())
        esc()
        self.win.select_lane("comments")
        self.pump(0.1)
        self.assertFalse(self.win.curtain_shown())
        self.assertEqual(self.win.current_lane(), "comments")
        self.win.cfg["ui"]["esc"] = "tray"  # the old way, by a flag
        esc()
        self.pump(0.1)
        self.assertTrue(not self.win.isVisible() or self.win.isMinimized())
        self.win.cfg["ui"]["esc"] = "curtain"
        self.win.showNormal()
        self.pump(0.1)
        self.win.select_lane("people")

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
        # asked again right away: no new download, it fails at once
        calls = []
        imgs._download = lambda url, side: calls.append(url) or good
        imgs.get("https://x/broken.png", got.append, failed=lambda: failed.append(1))
        self.assertEqual((calls, len(failed)), ([], 2))
        imgs.broken["https://x/broken.png"] -= Images.RETRY_AFTER + 1  # time passed
        imgs.get("https://x/broken.png", got.append, failed=lambda: failed.append(1))
        self.pump(until=lambda: len(got) == 2)
        self.assertNotIn("https://x/broken.png", imgs.broken)

        # the memory cache keeps to its budget in bytes, dropping the oldest first
        from PySide6.QtGui import QPixmap
        imgs.mem_budget = 3 * 100 * 100 * 4
        for i in range(5):
            pm = QPixmap(100, 100)
            imgs._remember((f"u{i}", 1200), pm)
        self.assertEqual(list(k for k, _s in imgs.mem), ["u2", "u3", "u4"])
        self.assertLessEqual(imgs.mem_bytes, imgs.mem_budget)

        # saving takes the original from the cache, never overwrites
        import hashlib
        url = "https://x/cat.png"
        (imgs.cache_dir / hashlib.sha1(url.encode()).hexdigest()).write_bytes(b"PNGDATA")
        folder = Path(self._tmp.name) / "saved"
        first = self.bridge_wait(imgs.save(url, folder))
        second = self.bridge_wait(imgs.save(url, folder))
        self.assertEqual((first.name, second.name), ("cat.png", "cat-1.png"))
        self.assertEqual(first.read_bytes(), b"PNGDATA")

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

        # diagnostics: Qt messages into the log, widget counts in the stats line
        from PySide6.QtCore import qInstallMessageHandler

        from fedtail import diag
        from fedtail.frontends.qt import diagnostics
        dog, beat = diagnostics.install(self.app, self.win, self.core.cfg)
        snap = diag.stats()
        self.assertGreater(snap["qt.widgets"], 10)
        self.assertIn("core.statuses", snap)
        dog.stop()
        beat.stop()
        qInstallMessageHandler(None)

        # someone's profile inside the app: info card, follow; a click on the name
        # in their own tab goes back up to it; hashtags open a tab of their own
        from fedtail.frontends.qt.feed import AccountWidget, TagWidget
        self.win.on_link("fedtail:account/B")
        prof = self.win.tabs.currentWidget()
        self.assertIsInstance(prof, AccountWidget)
        self.pump(until=lambda: prof.acc is not None and prof._info_layout.count())
        prof._toggle_follow()
        self.pump(until=lambda: prof.relation.get("following"))
        self.win.on_link("fedtail:account/B")  # same tab: no new one
        self.assertIs(self.win.tabs.currentWidget(), prof)
        self.win.on_link("fedtail:tag/linux")
        self.assertIsInstance(self.win.tabs.currentWidget(), TagWidget)
        self.win.close_tab(self.win.tabs.currentIndex())
        self.win.close_tab(self.win.tabs.indexOf(prof))

        # search: people with a Follow button, tags; followers lists from a profile
        from fedtail.frontends.qt.feed import AccountRow, PeopleWidget, SearchWidget, TagRow
        self.win.open_search("bob")
        search = self.win.tabs.currentWidget()
        self.assertIsInstance(search, SearchWidget)
        self.pump(until=lambda: search.box.findChildren(AccountRow))
        row = search.box.findChildren(AccountRow)[0]
        was = bool(row.relation.get("following"))
        row._toggle()
        self.pump(until=lambda: bool(row.relation.get("following")) != was)
        search.run("#lin")
        self.pump(until=lambda: search.box.findChildren(TagRow))
        self.win.open_people({"id": "ME", "acct": "veresk"}, "followers")
        self.assertIsInstance(self.win.tabs.currentWidget(), PeopleWidget)
        self.win.close_tab(self.win.tabs.currentIndex())
        self.win.close_tab(self.win.tabs.indexOf(search))

        # the sidebar in sections; Alt+N counts lanes, not headers; browse lanes
        self.assertEqual(self.win.lane_order[:4], ["global", "people", "local", "bots"])
        self.assertIn("global", self.win.lane_order)
        self.win.select_lane("global")
        self.pump(0.2)
        self.assertEqual(self.core._active_lane, "global")
        self.win.select_lane("people")

        # notifications go out through notify-send (a fake one here that records its
        # arguments), and stay quiet only about the lane that's on screen
        import stat
        rec = Path(self._tmp.name) / "notify-args"
        fake = Path(self._tmp.name) / "notify-send"
        fake.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" >> {rec}\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        n = self.win.notifier
        n.notify_send, n.backend = str(fake), "desktop"
        reply = self.core.store.get_status("013")
        n.notify([("comments", reply)])
        self.pump(until=lambda: rec.exists() and "--wait" in rec.read_text())
        args = rec.read_text().splitlines()
        self.assertIn("--app-name=fedtail", args)
        self.assertTrue(any(a.startswith("--action=open=") for a in args))
        rec.unlink()
        self.win.select_lane("comments")
        self.pump(0.1)
        self.win.isActiveWindow = lambda: True  # the reader is looking at that lane
        n.notify([("comments", reply)])
        n.notify([("mentions", reply)])
        self.pump(until=lambda: rec.exists())
        self.pump(0.3)
        text = rec.read_text()
        self.assertEqual(text.count("--wait"), 1)  # only the mention
        del self.win.isActiveWindow
        self.win.select_lane("people")

        # silence: a filter added in the dialog, a mute from a post's menu, a post folded
        # by a "warn" filter
        from fedtail.frontends.qt.card import CardSpec, PostRow
        from fedtail.frontends.qt.silence import SilenceDialog
        dlg = SilenceDialog(self.win)
        dlg.show()
        dlg.words.setText("крипта, nft")
        dlg._add_filter()
        self.pump(until=lambda: dlg.filter_list.count() == 1)
        dlg.filter_list.setCurrentRow(0)
        dlg._delete_filter()
        self.pump(until=lambda: dlg.filter_list.count() == 0)
        self.win.on_link("fedtail:mute/013")
        self.pump(until=lambda: "B" in self.core.muted)
        dlg.reload()
        self.pump(until=lambda: dlg.muted_list.count() == 1)
        dlg.muted_list.setCurrentRow(0)
        dlg._undo(dlg.muted_list, "mute")
        self.pump(until=lambda: "B" not in self.core.muted)
        dlg.accept()
        folded = dict(self.core.store.get_status("013"),
                      filtered=[{"filter": {"title": "шум", "filter_action": "warn"}}])
        row = PostRow(CardSpec(key="x", status=folded), self.win.ctx)
        self.assertFalse(row.cw_open)

        # editing my post: the editor fetches what I typed, sends the change, the card
        # gets "edited" with the versions behind it
        mine = self.world.add(status("120", ME, text="очепятка"), home=True)
        self.core.store.put_statuses([mine])
        dlg = Compose(self.win, edit=mine)
        dlg.show()
        self.pump(until=lambda: dlg.text.toPlainText() == "очепятка")
        self.assertFalse(dlg.vis.isEnabled())
        dlg.text.setPlainText("опечатка")
        dlg.send()
        self.pump(until=lambda: "опечатка" in self.core.store.get_status("120")["content"])
        self.pump(until=lambda: gone(dlg))
        edited = self.core.store.get_status("120")
        self.assertTrue(edited.get("edited_at"))
        self.win.show_history(edited)
        self.pump(0.3)

        # conversations view: one card per thread, the line about the rest
        self.win.select_lane("comments")
        lane = self.win.lane_widgets["comments"]
        self.pump(0.2)
        lane.conv_btn.setChecked(True)
        lane._toggle_conversations()
        self.pump(0.2)
        keys = [k for k in lane.view.order if not k.startswith("__")]
        self.assertTrue(keys and all(k.startswith("conv:") for k in keys))
        self.assertTrue(self.core.get_state("conversations.comments"))
        lane.conv_btn.setChecked(False)
        lane._toggle_conversations()
        self.pump(0.2)
        self.assertFalse(any(k.startswith("conv:") for k in lane.view.order))
        self.win.select_lane("people")

        # the command line, Point-style
        bar = self.win.cmdline
        alias = self.core.short_ids([self.core.store.get_status("013")])["013"]
        before = len(self.world.posted)
        bar.edit.setText(f"#{alias} согласен")
        self.assertIn(alias, bar.hint.text())  # says what Enter will do
        bar.run()
        self.pump(until=lambda: len(self.world.posted) > before)
        text, _vis, reply_to, _md = self.world.posted[-1]
        self.assertEqual(reply_to, "013")
        self.assertTrue(text.startswith("@") and text.endswith("согласен"))
        bar.edit.setText(f"S #{alias}")
        bar.run()
        self.pump(until=lambda: self.core.subscribed(self.core.store.get_status("013")))
        bar.edit.setText("@bob")
        bar.run()
        self.pump(until=lambda: isinstance(self.win.tabs.currentWidget(), AccountWidget))
        self.win.close_tab(self.win.tabs.currentIndex())
        n = len(self.world.posted)
        bar.edit.setText("просто мысль вслух")
        bar.run()
        self.pump(until=lambda: len(self.world.posted) > n)
        self.assertEqual(self.world.posted[-1][:3], ("просто мысль вслух", "private", None))
        bar.edit.clear()

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
        self.pump(until=lambda: self.world.profile_updates and gone(dlg))
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
        # the half-transparent Save button in the corner saves the picture on screen
        saved = []
        self.win.ctx.save_image, keep = saved.append, self.win.ctx.save_image
        try:
            self.assertIsNotNone(ov.btn_save)
            self.assertGreater(ov.buttons.x(), self.win.width() // 2)  # top right
            ov.btn_save.click()
        finally:
            self.win.ctx.save_image = keep
        self.assertEqual(saved, [pic[0]])
        ov.close_viewer()
        self.assertFalse(ov.isVisible())

    def test_short_id_goes_to_the_command_line(self):
        bar = self.win.cmdline
        self.assertTrue(bar.hint.isHidden())  # nothing typed: the line takes the width
        self.win.on_link("fedtail:alias/isf")
        self.assertEqual(bar.edit.text(), "#isf ")
        bar.edit.setText("#abc/2 привет")
        self.win.on_link("fedtail:alias/k9")
        self.assertEqual(bar.edit.text(), "#k9 привет")  # the number replaced, text kept
        bar.edit.setText("просто текст")
        self.win.on_link("fedtail:alias/k9")
        self.assertEqual(bar.edit.text(), "#k9 просто текст")
        self.assertEqual(bar.edit.cursorPosition(), len(bar.edit.text()))

    def test_poll_vote_on_the_card(self):
        from PySide6.QtWidgets import QProgressBar, QPushButton, QRadioButton
        st = self.world.add(status("030", BOB, minute=30, text="чай или кофе?"), home=True)
        st["poll"] = {"id": "P1", "expired": False, "multiple": False, "voted": False,
                      "own_votes": [], "votes_count": 3, "voters_count": 3,
                      "expires_at": "2099-01-01T00:00:00Z",
                      "options": [{"title": "чай", "votes_count": 2},
                                  {"title": "кофе", "votes_count": 1}]}
        self.win.start()
        self.pump(until=lambda: self.core.me is not None and "people" in self.win.lane_widgets)
        self.core.poll_once()
        lane = self.win.lane_widgets["people"]
        self.pump(until=lambda: "030" in lane.view.rows)
        row = lane.view.rows["030"]
        radios = row.findChildren(QRadioButton)
        self.assertEqual([r.text() for r in radios], ["чай", "кофе"])
        self.assertEqual(row.findChildren(QProgressBar), [])  # no results before voting
        vote = next(b for b in row.findChildren(QPushButton) if b.text() == "Голосовать")
        self.assertFalse(vote.isEnabled())
        radios[1].setChecked(True)
        self.assertTrue(vote.isEnabled())
        vote.click()
        self.pump(until=lambda: lane.view.rows["030"].findChildren(QProgressBar))
        bars = lane.view.rows["030"].findChildren(QProgressBar)
        self.assertEqual([b.value() for b in bars], [50, 50])
        self.assertEqual([b.property("mine") for b in bars], ["false", "true"])
        self.assertEqual(self.world.statuses["030"]["poll"]["own_votes"], [1])

    def test_sidebar_sections_fold(self):
        self.win.start()
        self.pump(until=lambda: self.core.me is not None and "people" in self.win.lane_widgets)
        self.core.poll_once()
        self.pump(until=lambda: self.win.lane_items["comments"].count == 1)
        rows = {self.win.lanes.item(i).data(0x0100): self.win.lanes.item(i)
                for i in range(self.win.lanes.count())}
        head = self.win.group_heads["personal"]
        self.win.fold_group("personal")
        self.assertTrue(rows["comments"].isHidden())
        self.assertFalse(rows["people"].isHidden())
        self.assertEqual((head.arrow.text(), head.badge.text()), ("▸", "1"))
        self.assertFalse(head.badge.isHidden())
        # kept across a rebuild (lists change) and a restart
        self.win._rebuild_sidebar()
        row = next(self.win.lanes.item(i) for i in range(self.win.lanes.count())
                   if self.win.lanes.item(i).data(0x0100) == "comments")
        self.assertTrue(row.isHidden())
        self.assertEqual(self.core.get_state("folded_groups"), ["personal"])
        self.win.fold_group("personal")
        self.assertFalse(row.isHidden())
        self.assertTrue(self.win.group_heads["personal"].badge.isHidden())

    def test_count_on_the_icon(self):
        from PySide6.QtGui import QIcon

        from fedtail.frontends.qt import badge
        self.assertEqual([badge.text(n) for n in (0, 7, 100)], ["", "7", "99+"])
        base = QIcon(self.win.windowIcon())
        self.assertIs(badge.icon_with_count(base, 0), base)
        drawn = badge.icon_with_count(base, 5).pixmap(64, 64).toImage()
        plain = base.pixmap(64, 64).toImage()
        self.assertNotEqual(drawn, plain)  # the badge is painted in
        self.win.start()
        self.pump(until=lambda: self.core.me is not None and "people" in self.win.lane_widgets)
        self.core.poll_once()
        # the comment on my post counts (comments is in ui.icon_count), Home doesn't
        self.pump(until=lambda: getattr(self.win, "_tray_count", 0) == 1)
        sent = []
        self.win.launcher = type("L", (), {"set": lambda _s, n: sent.append(n)})()
        self.win.update_badges()
        self.assertEqual(sent, [1])

    def test_open_thread_grows_and_says_why_replies_come(self):
        from PySide6.QtCore import Qt

        from fedtail.frontends.qt.feed import ThreadWidget

        self.world.following.add("B")
        self.win.start()
        self.pump(until=lambda: self.core.me is not None and "people" in self.win.lane_widgets)
        self.core.poll_once()
        self.win.on_link("fedtail:thread/011")
        tab = self.win.tabs.currentWidget()
        self.assertIsInstance(tab, ThreadWidget)
        self.pump(until=lambda: tab.loaded and len(tab.view.rows) == 1)
        # not subscribed, but Bob is followed: the header says why his replies come
        self.pump(until=lambda: "@bob" in tab.header.info.text())

        # a reply arrives by the poll: the open thread takes it in by itself
        self.world.add(status("015", NEWS, "011", "B", minute=15), home=True)
        self.core.poll_once()
        self.pump(until=lambda: "015" in tab.view.rows)

        # one that only F5 can find (not in any lane): F5 reloads the thread on screen
        self.world.statuses["016"] = status("016", NEWS, "015", "N", minute=16)
        try:
            from PySide6.QtTest import QTest
        except ImportError:  # Debian has no QtTest
            self.win.refresh()
        else:
            self.win.activateWindow()
            self.pump(0.3)
            print("F5 test: active window is ours:", self.app.activeWindow() is self.win,
                  file=__import__("sys").stderr)
            QTest.keyClick(self.win.tabs.currentWidget(), Qt.Key.Key_F5)
        self.pump(until=lambda: "016" in tab.view.rows)

        # subscribed: the explanation goes away
        self.win.bridge.call(self.core.subscribe(tab.root))
        self.pump(until=lambda: "@bob" not in tab.header.info.text())

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
