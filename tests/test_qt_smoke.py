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
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
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

        cfg, _ = config.validate({"feed": {"first_run_mark_read": False},
                                  "ui": {"start_lane": "last", "arts_mode": False}})
        p = paths.resolve("t", config=str(tmp / "c.toml"), data=str(tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        self.core = Core(cfg, p, api_class=FakeApi)
        self.core._origin_json = lambda url: None  # tests never reach other servers
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
        from PySide6.QtWidgets import QPushButton

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
        self.assertTrue(dlg.text.toPlainText().startswith("@bob@social.example"))
        self.assertEqual(dlg.vis.currentData(), "private")
        dlg.text.setPlainText("@bob@social.example ага")
        dlg.close()  # the window's X
        self.assertFalse(dlg.isVisible())
        self.assertEqual(self.core.get_draft("reply:013")["text"], "@bob@social.example ага")
        dlg = Compose(self.win, self.core.store.get_status("013"))
        dlg.show()
        self.assertEqual(dlg.text.toPlainText(), "@bob@social.example ага")
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

        # a poll: choices, how long, one or several
        dlg = Compose(self.win)
        dlg.show()
        dlg.text.setPlainText("что выбрать?")
        dlg.poll_btn.setChecked(True)
        self.assertTrue(dlg.poll_box.isVisible())
        self.assertFalse(dlg.attach_btn.isEnabled())  # pictures or a poll
        dlg.poll_options[0].setText("GoToSocial")
        dlg.poll_options[1].setText("Mastodon")
        dlg.poll_multiple.setChecked(True)
        dlg.send()
        self.pump(until=lambda: gone(dlg))
        self.assertEqual(self.world.extras[-1]["poll"],
                         {"options": ["GoToSocial", "Mastodon"], "expires_in": 86400,
                          "multiple": True})

        # a quote: the quoted post shown above, its id sent; who may quote mine from config
        self.core.cfg["post"]["quote_policy"] = "followers"
        dlg = Compose(self.win, quote=self.core.store.get_status("011"))
        dlg.show()
        self.assertEqual(dlg.key, "quote:011")
        dlg.text.setPlainText("вот это")
        dlg.send()
        self.pump(until=lambda: gone(dlg))
        self.assertEqual(self.world.extras[-1]["quote"], "011")
        self.assertEqual(self.world.extras[-1]["quote_policy"], "followers")
        self.core.cfg["post"]["quote_policy"] = ""

        # later: the server keeps it; the list shows it and can cancel it
        dlg = Compose(self.win)
        dlg.show()
        dlg.text.setPlainText("утром")
        dlg.ask_schedule().accept()
        self.pump(until=lambda: gone(dlg))
        self.assertEqual(self.world.scheduled[-1]["params"]["text"], "утром")
        self.assertTrue(self.world.scheduled[-1]["scheduled_at"].endswith("Z"))
        sched, lst = self.win.show_scheduled()
        self.pump(until=lambda: lst.count() and "утром" in lst.item(0).text())
        lst.setCurrentRow(0)
        next(b for b in sched.findChildren(QPushButton)).click()
        self.pump(until=lambda: not self.world.scheduled)
        sched.close()

        # @names and #tags complete: the people seen in the lanes, then the server's
        dlg = Compose(self.win)
        dlg.show()
        self.core.store.people_counts()
        dlg.text.setPlainText("привет @bo")
        cur = dlg.text.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        dlg.text.setTextCursor(cur)
        dlg._suggest_tags()
        offered = dlg._tag_model.stringList()
        self.assertTrue(any(x.startswith("@bob@social.example") for x in offered), offered)
        dlg._put_tag(offered[0])
        self.assertEqual(dlg.text.toPlainText(), "привет @bob@social.example ")
        self.core.cfg["post"]["complete_mentions"] = False
        dlg.text.setPlainText("@bo")
        dlg.text.moveCursor(cur.MoveOperation.End)
        dlg._suggest_tags()
        self.assertFalse(dlg.tag_completer.popup().isVisible())
        self.core.cfg["post"]["complete_mentions"] = True
        self.core._emoji = [{"shortcode": "blobcat"}, {"shortcode": "catjam"}]
        dlg.text.setPlainText("ну :cat")
        dlg.text.moveCursor(cur.MoveOperation.End)
        dlg._suggest_tags()
        self.assertEqual(dlg._tag_model.stringList(), [":catjam:", ":blobcat:"])
        dlg._put_tag(":catjam:")
        self.assertEqual(dlg.text.toPlainText(), "ну :catjam: ")
        dlg.text.setPlainText("в 12:30")
        dlg.text.moveCursor(cur.MoveOperation.End)
        self.assertEqual(dlg._token_at_cursor(), (None, None))
        dlg.reject()

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
        self.assertEqual([str(Path(p)) for p in media_paths(mime)], [str(Path(saved))])
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

        def fake_download(url, _side, _patient=False, _big=False):
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
        imgs._download = lambda url, side, patient=False, big=False: calls.append(url) or good
        imgs.get("https://x/broken.png", got.append, failed=lambda: failed.append(1))
        self.assertEqual((calls, len(failed)), ([], 2))
        imgs.broken["https://x/broken.png"] -= Images.RETRY_AFTER + 1  # time passed
        imgs.get("https://x/broken.png", got.append, failed=lambda: failed.append(1))
        self.pump(until=lambda: len(got) == 2)
        self.assertNotIn("https://x/broken.png", imgs.broken)

        # a network failure gets a second, patient try before it counts as broken
        imgs.SECOND_TRY_AFTER = 50
        tries = []

        def slow_server(url, _side, patient=False, _big=False):
            tries.append(patient)
            if not patient:
                imgs.why[url] = ("network", "ReadTimeout")
                raise OSError("timeout")
            return good
        imgs._download = slow_server
        late = []
        imgs.get("https://x/slow.png", late.append, failed=lambda: late.append(None))
        self.pump(until=lambda: late)
        self.assertEqual(tries, [False, True])
        self.assertIsNotNone(late[0])

        # a preview that gave up is asked again once its original comes (the viewer)
        ready = {"now": False}

        def fetching(url, _side, patient=False, _big=False):
            if "prev" in url and not ready["now"]:
                imgs.why[url] = ("format", "?")  # not a network error: no second try
                raise OSError("not yet")
            return good
        imgs._download = fetching
        shown, gave_up = [], []
        imgs.get("https://x/prev.png", shown.append, failed=lambda: gave_up.append(1),
                 original="https://x/full.png")
        self.pump(until=lambda: gave_up)
        ready["now"] = True
        imgs.get("https://x/full.png", lambda pm: None, 4000)
        self.pump(until=lambda: shown)

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
        # a narrow window: the buttons wrap onto more lines, none is squeezed
        from PySide6.QtWidgets import QPushButton
        self.win.resize(700, 700)
        self.pump(0.3)
        btns = [b for b in prof.info.findChildren(QPushButton) if b.isVisible()]
        self.assertTrue(btns)
        for b in btns:
            self.assertGreaterEqual(b.width(), b.sizeHint().width(), b.text())
            right = b.mapTo(prof.info, b.rect().topRight()).x()
            self.assertLessEqual(right, prof.info.width(), b.text())  # and none sticks out
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

        if os.name != "nt":  # the fake notify-send is a shell script
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
            self.pump(until=lambda: rec.exists() and "--wait" in rec.read_text("utf-8"))
            args = rec.read_text("utf-8").splitlines()
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
            text = rec.read_text("utf-8")
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
        lane.set_view("conversations")
        self.pump(0.2)
        keys = [k for k in lane.view.order if not k.startswith("__")]
        self.assertTrue(keys and all(k.startswith("conv:") for k in keys))
        self.assertTrue(self.core.choice("conversations.comments"))
        lane.set_view("feed")
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
        people.set_filter("posts")
        self.pump(0.1)
        self.assertNotIn("013", [r.status_id for r in people.view.rows.values()])
        self.assertTrue(self.core.posts_only("people"))
        people.set_filter("all")
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
        # the original won't show (a format Qt can't read): the viewer says so, and the
        # small copy stays on screen instead of "loading…" forever
        ov._small(0, QPixmap(40, 30))
        self.assertFalse(ov.preview)  # the original was already there: no downgrade
        ov.pm = None
        ov._small(0, QPixmap(40, 30))
        self.assertTrue(ov.preview)
        self.win.images.why[ov.url()] = ("format", "image/avif")
        ov._failed(0)
        self.assertIn("image/avif", ov.problem)
        ov.pm = None
        ov.update()
        self.pump(0.05)  # paints the explanation instead of "loading…"
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

    def test_merged_window(self):
        """All accounts in one window: the other account's posts in Home, marked."""
        from PySide6.QtWidgets import QLabel

        from fedtail.core.merged import MergedCore
        from fedtail.frontends.qt.bridge import Bridge
        from fedtail.frontends.qt.window import MainWindow
        work = fakes.World()
        work.me = dict(ME, id="W", acct="w", username="w")
        work.add(status("700", BOB, minute=50, text="через work"), home=True)
        FakeApi.worlds = {"https://work.example": work}
        self.addCleanup(setattr, FakeApi, "worlds", {})
        tmp = Path(self._tmp.name)
        p = paths.resolve("work", config=str(tmp / "w.toml"), data=str(tmp / "w"))
        auth.save(p.auth_file, {"server": "https://work.example", "token": "tok"})
        other = Core(self.core.cfg, p, api_class=FakeApi)
        merged = MergedCore(self.core, {"work": other})
        self.win.quitting = True
        self.win.hide()
        win = MainWindow(merged, Bridge(merged), self.theme)
        win.images.get = lambda url, cb, *a, **k: None
        self.addCleanup(lambda: (setattr(win, "quitting", True), win.hide(), other.shutdown()))
        win.show()
        win.start()
        self.pump(until=lambda: self.core.me is not None and other.me is not None)
        self.core.poll_once()
        other.poll_once()
        win.select_lane("people")
        lane = win.lane_widgets["people"]
        self.pump(until=lambda: "work~700" in lane.view.rows and "011" in lane.view.rows)
        marks = [w.text() for w in lane.view.rows["work~700"].findChildren(QLabel)
                 if w.objectName() == "via"]
        self.assertEqual(marks, ["→ @w"])
        self.assertEqual([w for w in lane.view.rows["011"].findChildren(QLabel)
                          if w.objectName() == "via"], [])  # mine: no mark
        win.on_link("fedtail:fav/work~700")  # acts through work
        self.pump(until=lambda: work.statuses["700"].get("favourited"))
        menu = win.accounts_menu()
        merge = next(a for a in menu.actions() if a.text() == "Все аккаунты в одном окне")
        self.assertTrue(merge.isChecked())

    def test_single_picture_preview_first_then_original(self):
        from PySide6.QtGui import QPixmap

        from fedtail.frontends.qt.card import CardSpec, PostRow
        asked = []

        def fake_get(url, cb, *a, **k):
            asked.append(url)
            cb(QPixmap(40, 30))
        self.win.images.get = fake_get
        st = status("091", BOB, minute=1)
        st["media_attachments"] = [{"type": "image", "url": "https://x/big.jpg",
                                    "preview_url": "https://x/small.jpg",
                                    "meta": {"original": {"width": 4000, "height": 3000}}}]
        bigs = []
        self.win.images.get = lambda url, cb, *a, **k: (bigs.append(k.get("big", False)),
                                                        fake_get(url, cb))
        PostRow(CardSpec(key="091", status=st), self.win.ctx)
        pictures = [u for u in asked if u and "/x/" in u]  # (the avatar has no address)
        self.assertEqual(pictures, ["https://x/small.jpg", "https://x/big.jpg"])
        # the original goes to its own workers, the preview doesn't
        flags = [b for u, b in zip(asked, bigs, strict=True) if u and "/x/" in u]
        self.assertEqual(flags, [False, True])

    def test_originals_dont_wait_behind_stuck_previews(self):
        """Every preview worker stuck on a slow server: an original still comes, and it
        comes already shrunk to the feed size by the decoder."""
        import threading

        from PySide6.QtCore import QBuffer, QIODevice
        from PySide6.QtGui import QImage

        from fedtail.frontends.qt import images as imgmod
        photo = QImage(3000, 2000, QImage.Format.Format_RGB32)
        photo.fill(0x336699)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        photo.save(buf, "JPG")
        data = bytes(buf.data())
        small = imgmod.decode(data, 600)
        self.assertEqual((small.width(), small.height()), (600, 400))

        release = threading.Event()

        class Resp:
            content = data
            headers = {"Content-Type": "image/jpeg"}

            def raise_for_status(self):
                pass

        def fake_http(url, timeout):
            if "slow" in url:
                release.wait(10)
            return Resp()
        self.core.paths.cache_dir.mkdir(parents=True, exist_ok=True)
        im = imgmod.Images(self.core, self.bridge)
        im.http.get = fake_http
        try:
            for i in range(im.FEED_WORKERS + 2):
                im.get(f"https://slow.example/p{i}.jpg", lambda pm: None)
            got = []
            im.get("https://fast.example/original.jpg", got.append, big=True)
            self.pump(until=lambda: got, timeout=5)
            self.assertLessEqual(max(got[0].width(), got[0].height()), imgmod.FEED_SIDE)
            self.assertTrue(im.waiting)  # the previews are still stuck meanwhile
            c = im.counts()  # the stats line: what happened, where it waits
            self.assertEqual((c["done"], c["originals"]), (1, 1))
            self.assertGreaterEqual(c["queued"], 1)
            self.assertEqual(im.counts()["done"], 0)  # since the last stats line
        finally:
            release.set()
            im.shutdown()

    def test_video_called_a_picture(self):
        """A server that calls an mp4 an "image": a video with a ▶, not a broken picture."""
        from PySide6.QtWidgets import QLabel

        from fedtail.frontends.qt.card import CardSpec, PostRow, _true_kind
        clip = {"type": "image", "url": "https://x.example/media/clip.mp4?x=1",
                "preview_url": None, "meta": {"original": {"width": 320, "height": 480}}}
        self.assertEqual(_true_kind(clip)["type"], "video")
        self.assertEqual(_true_kind(dict(clip, url="https://x/a.png"))["type"], "image")
        st = status("090", BOB, minute=1)
        st["media_attachments"] = [clip]
        row = PostRow(CardSpec(key="090", status=st), self.win.ctx)
        texts = [w.text() for w in row.findChildren(QLabel)]
        self.assertTrue(any(t.startswith("▶") for t in texts), texts)

    def test_link_card(self):
        """A post with a link gets the page's card; feed.link_cards turns it down or off."""
        from PySide6.QtWidgets import QFrame, QLabel

        from fedtail.frontends.qt.card import CardSpec, PostRow
        st = status("091", BOB, minute=1)
        st["card"] = {"url": "https://www.news.example/a", "title": "Заголовок статьи",
                      "description": "Описание", "image": "https://news.example/a.png"}
        cards = lambda row: row.findChildren(QFrame, "linkCard")
        texts = lambda row: [w.text() for w in row.findChildren(QLabel)]
        row = PostRow(CardSpec(key="091", status=st), self.win.ctx)
        self.assertEqual(len(cards(row)), 1)
        self.assertIn("news.example", texts(row))
        self.assertTrue(any("Описание" in t for t in texts(row)))
        self.win.ctx.cfg["feed"]["link_cards"] = "text"
        row = PostRow(CardSpec(key="091", status=st), self.win.ctx)
        self.assertFalse(row.findChildren(QLabel, "linkCardImage"))
        self.assertFalse(any("Описание" in t for t in texts(row)))
        self.win.ctx.cfg["feed"]["link_cards"] = "off"
        self.assertEqual(cards(PostRow(CardSpec(key="091", status=st), self.win.ctx)), [])
        self.win.ctx.cfg["feed"]["link_cards"] = "full"

    def test_quotes(self):
        """A quote post: the quoted one framed inside; a pending one says so; off as sent."""
        from PySide6.QtWidgets import QFrame, QLabel

        from fedtail.frontends.qt.card import CardSpec, PostRow
        inner = status("093", NEWS, minute=1, text="исходная новость")
        st = status("094", BOB, minute=2, text="смотрите")
        st["content"] += '<p class="quote-inline">RE: <a href="x">x</a></p>'
        st["quote"] = {"state": "accepted", "quoted_status": inner}
        texts = lambda row: " ".join(w.text() for w in row.findChildren(QLabel))
        row = PostRow(CardSpec(key="094", status=st), self.win.ctx)
        self.assertEqual(len(row.findChildren(QFrame, "quoteBox")), 1)
        self.assertIn("исходная новость", texts(row))
        self.assertNotIn("RE:", texts(row))
        st["quote"] = {"state": "pending", "quoted_status_id": "093"}
        row = PostRow(CardSpec(key="094", status=st), self.win.ctx)
        self.assertFalse(row.findChildren(QFrame, "quoteBox"))
        self.assertIn("одобрения", texts(row))
        self.win.ctx.cfg["feed"]["quotes"] = "off"
        st["quote"] = {"state": "accepted", "quoted_status": inner}
        row = PostRow(CardSpec(key="094", status=st), self.win.ctx)
        self.assertIn("RE:", texts(row))
        self.assertNotIn("исходная новость", texts(row))
        self.win.ctx.cfg["feed"]["quotes"] = "card"

    def test_translate(self):
        from PySide6.QtWidgets import QLabel

        from fedtail.frontends.qt.card import CardSpec, PostRow
        st = status("096", BOB, minute=1, text="გამარჯობა")
        st["language"] = "ka"
        asked = []
        self.win.ctx.translate = lambda s, done: (asked.append(s["id"]), done(
            {"content": "<p>привет</p>", "detected_source_language": "ka",
             "provider": "DeepL.com"}))
        row = PostRow(CardSpec(key="096", status=st), self.win.ctx)
        text = lambda: " ".join(w.text() for w in row.findChildren(QLabel))
        row._translate()
        self.assertEqual(asked, ["096"])
        self.assertIn("привет", text())
        self.assertIn("DeepL", text())
        row._translate()  # back to the original, without asking again
        self.assertIn("გამარჯობა", text())
        self.assertEqual(asked, ["096"])

    def test_post_keys(self):
        """j / k walk the posts, f likes the one under the cursor."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtWidgets import QApplication
        self.win.start()
        self.pump(until=lambda: self.core.me is not None and "people" in self.win.lane_widgets)
        self.core.poll_once()
        self.win.select_lane("people")
        view = self.win.lane_widgets["people"].view
        self.pump(until=lambda: "011" in view.rows)

        def key(k):
            QApplication.sendEvent(view, QKeyEvent(QKeyEvent.Type.KeyPress, k,
                                                   Qt.KeyboardModifier.NoModifier))
        key(Qt.Key.Key_J)
        first = view.cursor_key
        self.assertIsNotNone(first)
        key(Qt.Key.Key_J)
        self.assertNotEqual(view.cursor_key, first)
        key(Qt.Key.Key_K)
        self.assertEqual(view.cursor_key, first)
        self.assertEqual(view.rows[first].card.property("keyed"), True)
        sid = view.rows[first].spec.status["id"]
        key(Qt.Key.Key_F)
        self.pump(until=lambda: self.world.statuses[sid].get("favourited"))
        self.win.cfg["ui"]["post_keys"] = False
        key(Qt.Key.Key_J)
        self.assertEqual(view.cursor_key, first)
        self.win.cfg["ui"]["post_keys"] = True

    def test_report(self):
        from PySide6.QtWidgets import QCheckBox, QComboBox, QPlainTextEdit, QPushButton
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.core.poll_once()
        dlg = self.win.report(self.core.store.get_status("011"))
        dlg.findChild(QPlainTextEdit).setPlainText("реклама")
        combo = dlg.findChild(QComboBox)
        combo.setCurrentIndex(combo.findData("spam"))
        self.assertTrue(dlg.findChild(QCheckBox).isChecked())  # Bob is from elsewhere
        send = next(b for b in dlg.findChildren(QPushButton) if b.objectName() == "primary")
        send.click()
        self.pump(until=lambda: self.world.reports)
        self.assertEqual(self.world.reports[-1], ("B", ["011"], "реклама", True, "spam"))

    def test_pinned_on_profile(self):
        from fedtail.frontends.qt.feed import AccountWidget
        self.world.statuses["011"]["pinned"] = True
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.win.on_link("fedtail:account/B")
        tab = self.win.tabs.currentWidget()
        self.assertIsInstance(tab, AccountWidget)
        self.pump(until=lambda: "pin:011" in tab.view.rows)
        self.assertEqual(tab.view.order[0], "pin:011")
        self.assertNotIn("011", tab.view.rows)  # not twice

    def test_featured_on_profile(self):
        from PySide6.QtWidgets import QLabel

        from fedtail.frontends.qt.feed import AccountWidget
        self.world.featured["B"] = {"tags": [{"name": "fediverse", "statuses_count": "12"}],
                                    "people": [fakes.NEWS]}
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.win.on_link("fedtail:account/B")
        tab = self.win.tabs.currentWidget()
        self.assertIsInstance(tab, AccountWidget)
        rows = lambda: [w.text() for w in tab.info.findChildren(QLabel)
                        if w.objectName() == "featured"]
        self.pump(until=lambda: len(rows()) == 2)
        self.assertIn("fedtail:tag/fediverse", rows()[0])
        self.assertIn("(12)", rows()[0])
        self.assertIn("fedtail:account/N", rows()[1])

    def test_media_grid_square_around_focus(self):
        from PySide6.QtGui import QColor, QPixmap

        from fedtail.frontends.qt import card as card_module
        from fedtail.frontends.qt.card import CardSpec, PostRow
        self.assertEqual(card_module._focus({"meta": {"focus": {"x": 2, "y": "-0.5"}}}),
                         (1.0, -0.5))
        self.assertEqual(card_module._focus({}), (0.0, 0.0))
        # a 300×150 picture into 150×150: focus at the right edge → the right half
        self.assertEqual(card_module._crop_rect(300, 150, 150, 150, (1.0, 0.0)), (150, 0))
        self.assertEqual(card_module._crop_rect(300, 150, 150, 150, (0.0, 0.0)), (75, 0))
        self.assertEqual(card_module._crop_rect(150, 300, 150, 150, (0.0, 1.0)), (0, 0))  # top
        pm = QPixmap(300, 150)
        pm.fill(QColor("red"))
        self.assertEqual(card_module._fit(pm, 150, 150, 0, (0.0, 0.0)).size().width(), 150)
        st = status("096", BOB, minute=1)
        st["media_attachments"] = [
            {"type": "image", "url": f"https://x.example/{i}.png",
             "preview_url": f"https://x.example/{i}_s.png",
             "meta": {"small": {"width": 400, "height": 100}, "focus": {"x": 0.5, "y": 0}}}
            for i in range(2)]
        sizes = lambda: [w.size().toTuple() for w in row.findChildren(card_module.ClickLabel)
                         if w.objectName() == "media"]
        row = PostRow(CardSpec(key="096", status=st), self.win.ctx)
        self.assertNotEqual(sizes()[0], (150, 150))  # natural: its own shape
        self.core.cfg["ui"]["media_grid"] = "square"
        row = PostRow(CardSpec(key="096", status=st), self.win.ctx)
        self.assertEqual(sizes(), [(150, 150), (150, 150)])
        self.core.cfg["ui"]["media_grid"] = "natural"

    def test_alt_text_caption_and_reminder(self):
        from PySide6.QtGui import QColor, QPixmap
        from PySide6.QtWidgets import QLabel

        from fedtail.frontends.qt.card import CardSpec, PostRow
        from fedtail.frontends.qt.compose import Compose
        st = status("097", BOB, minute=1)
        st["media_attachments"] = [{"type": "image", "url": "https://x.example/a.png",
                                    "preview_url": "https://x.example/a_s.png",
                                    "description": "кот на окне"}]
        caps = lambda r: [w for w in r.findChildren(QLabel) if w.objectName() == "altCaption"]
        self.assertEqual(caps(PostRow(CardSpec(key="097", status=st), self.win.ctx)), [])
        self.core.cfg["ui"]["alt_text"] = "caption"
        row = PostRow(CardSpec(key="097", status=st), self.win.ctx)
        self.assertIn("кот на окне", caps(row)[0].text())
        media = [w for w in row.findChildren(QLabel) if w.objectName() == "media"]
        self.assertEqual(media[0].accessibleDescription(), "кот на окне")
        self.core.cfg["ui"]["alt_text"] = "tooltip"

        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        pic = Path(self._tmp.name) / "p.png"
        pm = QPixmap(8, 8)
        pm.fill(QColor("blue"))
        pm.save(str(pic))
        dlg = Compose(self.win)
        dlg.show()
        dlg.text.setPlainText("смотрите")
        dlg._add_media(str(pic))
        before = len(self.world.posted)
        dlg.send()
        self.assertTrue(dlg.alt_box.isVisible())
        self.assertEqual(len(self.world.posted), before)  # asked first
        anyway = next(b for b in dlg.alt_box.buttons() if b.text() == i18n._("alt_send_anyway"))
        anyway.click()
        self.pump(until=lambda: len(self.world.posted) == before + 1)

        # describe it, with a focus point: both go with the upload
        from fedtail.frontends.qt import focus as focus_module
        self.assertEqual(focus_module.to_focus(0, 0, 100, 50), (-1.0, 1.0))
        self.assertEqual(focus_module.to_focus(75, 25, 100, 50), (0.5, 0.0))
        self.assertEqual(focus_module.from_focus((0.5, 0.0), 100, 50), (75.0, 25.0))
        dlg = Compose(self.win)
        dlg.show()
        dlg.text.setPlainText("ещё")
        dlg._add_media(str(pic))
        dlg.send()
        describe = next(b for b in dlg.alt_box.buttons() if b.text() == i18n._("alt_describe"))
        describe.click()
        fd = dlg.focus_dialog
        fd._clicked(fd.src.width() * 0.75, fd.src.height() * 0.5)
        fd.text.setPlainText("синий квадрат")
        fd.accept()
        self.assertEqual(dlg._media_list()[0][1:], ["синий квадрат", [0.5, 0.0]])
        dlg.send()
        self.pump(until=lambda: self.world.uploads and
                  self.world.uploads[-1][1:] == ("синий квадрат", [0.5, 0.0]))

    def test_sensitive_media_covered(self):
        from PySide6.QtWidgets import QLabel

        from fedtail.frontends.qt.card import CardSpec, PostRow
        st = status("095", BOB, minute=1)
        st["sensitive"] = True
        st["media_attachments"] = [{"type": "image", "url": "https://x.example/a.png",
                                    "preview_url": "https://x.example/a_s.png",
                                    "meta": {"small": {"width": 400, "height": 300}}}]
        asked = []
        self.win.images.get = lambda url, cb, *a, **k: asked.append(url)
        row = PostRow(CardSpec(key="095", status=st), self.win.ctx)
        covers = [w for w in row.findChildren(QLabel) if w.text().startswith("⚠")]
        self.assertEqual(len(covers), 1)
        self.assertNotIn("https://x.example/a_s.png", asked)  # not even downloaded
        covers[0].clicked.emit()
        self.assertIn("https://x.example/a_s.png", asked)
        self.win.ctx.cfg["feed"]["sensitive_media"] = "show"
        asked.clear()
        PostRow(CardSpec(key="095", status=st), self.win.ctx)
        self.assertIn("https://x.example/a_s.png", asked)
        self.win.ctx.cfg["feed"]["sensitive_media"] = "hide"

    def test_arts_mode(self):
        """ui.arts_mode: no CW folding, no covers, server filters don't fold, no report."""
        from PySide6.QtWidgets import QLabel

        from fedtail.frontends.qt.card import CardSpec, PostRow
        from fedtail.i18n import _
        st = status("096", BOB, minute=1, text="как есть")
        st["sensitive"] = True
        st["spoiler_text"] = "осторожно"
        st["filtered"] = [{"filter": {"title": "шум", "filter_action": "warn"}}]
        st["media_attachments"] = [{"type": "image", "url": "https://x.example/b.png",
                                    "preview_url": "https://x.example/b_s.png",
                                    "meta": {"small": {"width": 400, "height": 300}}}]
        bare = dict(st, spoiler_text="", filtered=[])
        cfg = self.win.ctx.cfg
        cfg["ui"]["expand_cw"] = False

        def menu_texts(row):
            from PySide6.QtWidgets import QMenu
            return [a.text() for m in row.findChildren(QMenu) for a in m.actions()]

        asked = []
        self.win.images.get = lambda url, cb, *a, **k: asked.append(url)
        try:
            row = PostRow(CardSpec(key="096", status=st), self.win.ctx)
            self.assertFalse(row.cw_open)  # off: folded as usual
            self.assertIn(_("report"), menu_texts(row))
            cfg["ui"]["arts_mode"] = True
            row = PostRow(CardSpec(key="096", status=st), self.win.ctx)
            self.assertTrue(row.cw_open)  # neither the CW nor the filter folds it
            self.assertNotIn(_("report"), menu_texts(row))
            row = PostRow(CardSpec(key="097", status=bare), self.win.ctx)
            covers = [w for w in row.findChildren(QLabel) if w.text().startswith("⚠")]
            self.assertEqual(covers, [])
            self.assertIn("https://x.example/b_s.png", asked)  # shown straight away
        finally:
            cfg["ui"]["arts_mode"] = False
            cfg["ui"]["expand_cw"] = True

    def test_cw_card_makes_no_window_of_its_own(self):
        """A post under a CW: its folded part is shown or hidden while the card is being
        built — it must have its parent by then, or Qt makes a native window for it."""
        from PySide6.QtWidgets import QWidget

        from fedtail.frontends.qt.card import CardSpec, PostRow
        st = status("098", BOB, minute=1, text="под катом")
        st["spoiler_text"] = "осторожно"
        orphans = []
        real_set = QWidget.setVisible

        def watch(w, on):
            if on and w.parent() is None:
                orphans.append(w)
            real_set(w, on)
        QWidget.setVisible = watch
        try:
            for open_ in (True, False):
                self.win.ctx.cfg["ui"]["expand_cw"] = open_
                PostRow(CardSpec(key="098", status=st), self.win.ctx)
        finally:
            QWidget.setVisible = real_set
            self.win.ctx.cfg["ui"]["expand_cw"] = True
        self.assertEqual(orphans, [])

    def test_custom_emoji(self):
        """:blobcat: in a post and a name: a picture once it's downloaded."""
        from PySide6.QtWidgets import QLabel

        from fedtail.frontends.qt.card import CardSpec, PostRow
        st = status("092", BOB, minute=1, text="привет :blobcat:")
        st["emojis"] = [{"shortcode": "blobcat", "url": "https://s.example/b.png"}]
        st["account"] = dict(st["account"], display_name="Bob :blobcat:",
                             emojis=st["emojis"])
        asked = []
        self.win.images.get = lambda url, cb, *a, **k: asked.append((url, cb))
        self.win.images.local = lambda url: None
        row = PostRow(CardSpec(key="092", status=st), self.win.ctx)
        html = lambda: " ".join(w.text() for w in row.findChildren(QLabel))
        self.assertIn(":blobcat:", html())
        self.assertTrue(asked)
        self.win.images.local = lambda url: "/tmp/b.png"  # it came
        for url, cb in asked:
            if (url or "").endswith("b.png"):  # the emoji, not the avatar
                cb(None)
        self.assertIn("<img", html())
        self.assertNotIn(">привет :blobcat:", html())
        self.win.ctx.cfg["feed"]["custom_emoji"] = False
        row = PostRow(CardSpec(key="092", status=st), self.win.ctx)
        self.assertNotIn("<img", " ".join(w.text() for w in row.findChildren(QLabel)))
        self.win.ctx.cfg["feed"]["custom_emoji"] = True

    def test_unread_only(self):
        """Unread: what was unread on opening stays while you read it; leaving thins it."""
        self.win.start()
        self.pump(until=lambda: self.core.me is not None and "people" in self.win.lane_widgets)
        self.core.poll_once()
        self.core.mark_read(["011"])
        self.win.select_lane("people")
        lane = self.win.lane_widgets["people"]
        self.pump(until=lambda: "014" in lane.view.rows)
        posts = lambda: sorted(k for k in lane.view.rows if not k.startswith("__"))
        lane.set_filter("unread")
        self.pump(0.2)
        self.assertNotIn("011", posts())  # read already: not here
        self.assertIn("014", posts())
        self.assertFalse(lane.btn_older.isVisible())
        self.core.mark_read(["014"])  # read while looking at it: stays, greyed
        self.pump(0.1)
        self.assertIn("014", posts())
        self.win.select_lane("comments")  # leave and come back: it's gone
        self.pump(0.1)
        self.win.select_lane("people")
        self.pump(until=lambda: "014" not in lane.view.rows)
        self.assertEqual(self.core.choice("unread_only.people"), True)  # kept for this run
        self.assertIsNone(self.core.get_state("unread_only.people"))  # not past it

    def test_compose_inline_panel(self):
        """The post window lives inside the main one (the keyboard layout stays)."""
        from fedtail.frontends.qt.compose import Compose
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        first = Compose(self.win)
        first.show()
        self.assertFalse(first.isWindow())  # a panel, not a window of its own
        self.assertTrue(self.win.isAncestorOf(first))
        self.assertTrue(self.win.rect().contains(first.geometry()))
        first.text.setPlainText("черновик")
        second = Compose(self.win, self.core.store.get_status("011"))
        second.show()
        self.assertTrue(gone(first))  # one at a time…
        self.assertEqual(self.core.get_draft(first.key)["text"], "черновик")  # …kept
        second.reject()
        self.assertTrue(gone(second))
        self.win.cfg["ui"]["compose"] = "window"
        third = Compose(self.win)
        third.show()
        self.assertTrue(third.isWindow())  # the old way, when asked for
        third.reject()

    def test_start_lane(self):
        self.win.cfg["ui"]["start_lane"] = "none"  # the default: nothing opens by itself
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.pump(until=self.win.curtain_shown)
        self.assertNotIn("people", self.win.lane_widgets)  # not even built, nothing read
        self.win.cfg["ui"]["start_lane"] = "comments"
        self.win._open_start_lane()
        self.assertFalse(self.win.curtain_shown())
        self.assertIn("comments", self.win.lane_widgets)

    def test_tabs_and_the_curtain(self):
        """A tab already open, called from under the curtain, comes out of it (my own
        profile from my name); Enter in the sidebar search opens the search, not the last
        lane; a sidebar rebuild (lists refreshed) leaves the tab in front where it is."""
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent

        from fedtail.frontends.qt.feed import AccountWidget, SearchWidget
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.pump(until=lambda: "people" in self.win.lane_items)
        me = self.core.me["id"]
        self.win.open_account(me)
        prof = self.win.tabs.currentWidget()
        self.assertIsInstance(prof, AccountWidget)
        self.win.close_all()  # Esc: the curtain
        self.assertTrue(self.win.curtain_shown())
        self.win.open_account(me)  # a click on my name
        self.assertFalse(self.win.curtain_shown())
        self.assertIs(self.win.tabs.currentWidget(), prof)
        # Enter in the sidebar search, from the curtain
        self.win.close_all()
        box = self.win.search_box
        box.setFocus()
        box.setText("linux")
        for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            self.app.sendEvent(box, QKeyEvent(kind, Qt.Key.Key_Return,
                                              Qt.KeyboardModifier.NoModifier))
        self.pump(0.05)
        self.assertFalse(self.win.curtain_shown())
        self.assertIsInstance(self.win.tabs.currentWidget(), SearchWidget)
        # the sidebar built again behind the search tab: the search stays in front
        self.win._rebuild_sidebar()
        self.pump(0.05)
        self.assertIsInstance(self.win.tabs.currentWidget(), SearchWidget)

    def test_download_in_pieces_no_half_files(self):
        """Saving a video not in the cache: written a piece at a time under its own name;
        a download cut off halfway leaves nothing behind."""
        from fedtail.frontends.qt.images import Images
        imgs = Images(self.core, self.win.bridge)
        folder = Path(self._tmp.name) / "dl"

        class Resp:
            def __init__(self, chunks, fail=False):
                self.chunks, self.fail = chunks, fail
                self.headers = {"Content-Type": "video/mp4"}

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def raise_for_status(self):
                pass

            def iter_content(self, _size):
                yield from self.chunks
                if self.fail:
                    raise OSError("connection reset")

        class Http:
            def __init__(self, resp):
                self.resp, self.kw = resp, None

            def get(self, url, **kw):
                self.kw = kw
                return self.resp

        imgs.http = Http(Resp([b"ab", b"cd", b"ef"]))
        path = self.bridge_wait(imgs.save("https://x/clip.mp4", folder))
        self.assertEqual(path.read_bytes(), b"abcdef")
        self.assertTrue(imgs.http.kw.get("stream"))
        imgs.http = Http(Resp([b"half"], fail=True))
        fut = imgs.save("https://x/other.mp4", folder)
        self.pump(until=fut.done)
        with self.assertRaises(OSError):
            fut.result()
        self.assertEqual(sorted(f.name for f in folder.iterdir()), [path.name])

    def test_activity_rows_say_when_and_approve(self):
        """A row in Likes & boosts says when; one waiting for my approval has the two
        buttons, and ✔ answers the server's request."""
        from PySide6.QtWidgets import QLabel, QPushButton

        from fedtail.i18n import _
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        mine = self.world.add(status("190", ME, minute=1, vis="public"), home=True)
        reply = dict(status("191", BOB, minute=2, vis="public"), in_reply_to_id="190")
        self.world.act("q1", "favourite", NEWS, mine, minute=1)
        self.world.act("q2", "pending.reply", BOB, reply, minute=2)
        self.world.interactions = [{"id": "rq", "type": "reply", "account": BOB,
                                    "status": mine, "reply": reply}]
        self.core.poll_once()
        self.win.select_lane("activity")
        self.pump(0.2)
        w = self.win.lane_widgets["activity"]
        when = self.theme.date("2099-10-14T11:01:00.000Z")
        self.assertTrue(any(when in lab.text() for lab in w.findChildren(QLabel)))
        ok = [b for b in w.findChildren(QPushButton) if b.text() == _("ok_interaction")]
        self.assertEqual(len(ok), 1)
        ok[0].click()
        self.pump(until=lambda: self.world.answered == [("rq", True)])

    def test_new_pill_agrees_with_the_store(self):
        self.win.start()
        self.pump(until=lambda: self.core.me is not None and "people" in self.win.lane_widgets)
        self.core.poll_once()
        lane = self.win.lane_widgets["people"]
        self.win.select_lane("people")
        self.pump(until=lambda: lane.pill.text() and not lane.pill.isHidden())
        # read by a road that sends no event (another client, an old bug): the pill
        # follows the store the next time it's drawn
        self.core.store.mark_read([r.status_id for r in lane.view.rows.values()
                                   if r.status_id])
        lane.update_strip()
        self.assertTrue(lane.pill.isHidden())
        # someone goes into a list: Home drops them at once, the badge and pill agree
        self.world.add(status("040", BOB, minute=40), home=True)
        self.core.poll_once()
        self.pump(until=lambda: "040" in lane.view.rows)
        self.bridge_wait(self.core.create_list("Друзья", add="B"))
        self.pump(until=lambda: "040" not in lane.view.rows)
        self.assertEqual(self.win.lane_items["people"].count, len(lane.view.unread_keys()))

    def test_accounts_menu_switches_profiles(self):
        from fedtail.core import profiles
        fake = [{"name": "default", "acct": "veresk", "display_name": "", "logged_in": True,
                 "server": "https://example.test"},
                {"name": "t", "acct": "me", "display_name": "", "logged_in": True,
                 "server": "https://example.test"},
                {"name": "work", "acct": "", "display_name": "", "logged_in": False,
                 "server": ""}]
        launched, quit_ = [], []
        keep = profiles.listing, profiles.launch, self.win.quit
        profiles.listing, profiles.launch = lambda: fake, launched.append
        self.win.quit = lambda: quit_.append(1)
        try:
            m = self.win.accounts_menu()
            acts = [a for a in m.actions() if a.text()]
            self.assertEqual(acts[0].text(), "@veresk@example.test")
            current = acts[1]  # this window's profile is "t"
            self.assertTrue(current.isChecked() and not current.isEnabled())
            self.assertIn("work", acts[2].text())
            acts[2].trigger()
            self.pump(0.5)
            self.assertEqual((launched, quit_), (["work"], [1]))
        finally:
            profiles.listing, profiles.launch, self.win.quit = keep

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
        # a long title and note give way ("…", whole text in the tooltip): no wider window
        before = self.win.minimumSizeHint().width(), self.win.width()
        tab.header.info.setText("очень длинное пояснение " * 20)
        tab.header.title.setText("очень длинный заголовок " * 20)
        self.pump(0.1)
        self.assertEqual((self.win.minimumSizeHint().width(), self.win.width()), before)
        self.assertIn("пояснение", tab.header.info.toolTip())

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
        lane = self.win.lane_widgets["bots"]
        self.assertTrue("__sep__" in view.rows, f"separator={lane.separator} "
                      f"positioned={lane.positioned} unread={len(view.unread_keys())} "
                      f"rows={len(view.rows)} active={self.win.isActiveWindow()}")

    def test_big_lane_builds_cards_around_the_reading_place(self):
        """A lane of hundreds: only the cards around the first unread are built at first;
        scrolling up builds more above without moving what's on screen; going to a post
        far away builds there; "all read" covers the cards not built too."""
        self.win.cfg["feed"]["build_at_once"] = 10  # a small window: 40 posts make "big"
        for i in range(60):
            self.world.add(status(f"8{i:03d}", NEWS, minute=i % 60,
                                  text="длинный пост " * (60 + i % 30) + str(i)), home=True)
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.core.poll_once()
        bots = [st["id"] for _, st in self.core.lane_entries("bots")]
        self.assertGreaterEqual(len(bots), 40)
        self.core.mark_read(bots[:-5])  # the newest 5 unread
        self.win.select_lane("bots")
        lane = self.win.lane_widgets["bots"]
        view = lane.view
        self.pump(1.5)
        self.assertLess(len(view.rows), len(view.model))  # not all built
        first = view.unread_keys()[0]
        self.assertIn(first, view.rows)  # the reading place is
        self.assertEqual(len(view.unread_keys()), 5)

        # up: more is built above, and the post at the top of the screen stays put
        sb = view.verticalScrollBar()
        built = len(view.rows)
        top_key = view.order[0]
        sb.setValue(0)
        view._touched()
        y = view._top(view.rows[top_key]) - sb.value()
        self.pump(until=lambda: len(view.rows) > built)
        self.pump(0.3)
        self.assertEqual(view._top(view.rows[top_key]) - sb.value(), y)

        # far away: its card is built there
        oldest = view.model[0].key
        if oldest not in view.rows:
            view.scroll_to(oldest, "top")
            self.assertIn(oldest, view.rows)

        # "all read" is about the whole lane, built or not
        lane.mark_all_read()
        self.pump(0.2)
        self.assertEqual(self.core.unread_ids(self.core.lane_entries("bots")), set())

    def test_cards_far_behind_are_let_go(self):
        """Reading a long lane from the oldest to the newest: cards far behind go again,
        so a few hundred read posts don't stay built, and the post on top stays put."""
        self.win.cfg["feed"]["build_at_once"] = 10
        for i in range(80):
            self.world.add(status(f"7{i:03d}", NEWS, minute=i % 60,
                                  text="пост " * (40 + i % 20) + str(i)), home=True)
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.core.poll_once()
        self.win.select_lane("bots")
        view = self.win.lane_widgets["bots"].view
        self.pump(1.0)
        view.scroll_to(view.model[0].key, "top")
        self.pump(0.3)
        sb = view.verticalScrollBar()
        most = 0
        for _ in range(60):  # down, a screen at a time, as a reader would
            sb.setValue(sb.value() + view.viewport().height())
            view._touched()
            self.pump(0.08)
            most = max(most, len(view.rows))
            if view.order and view.order[-1] == view.model[-1].key and \
                    sb.value() >= sb.maximum():
                break
        self.assertEqual(view.order[-1], view.model[-1].key)  # read to the end
        self.assertLessEqual(most, 3 * 10 + 10)  # never all 80 built
        self.assertLess(len(view.rows), len(view.model))
        # the post on top stays where it is when the ones behind go: build more behind
        # it (as scrolling up does), let it settle, then let them go again
        sb.setValue(max(0, sb.value() - 2 * view.viewport().height()))
        view._touched()
        self.pump(1.8)  # grown above, laid out, the scroll target let go
        view.build_at_once = 4  # a smaller window: the next trim has something to drop
        top, y = view._anchor()
        before = len(view.rows)
        view._trim()
        self.pump(0.5)
        self.assertLess(len(view.rows), before)
        self.assertIn(top, view.rows)
        self.assertLessEqual(abs(view._top(view.rows[top]) - sb.value() - y), 2)

    def test_media_filter_off_doesnt_build_everything(self):
        """A big lane filtered to the few posts with pictures, then the filter off: the
        hundreds back are not all built at once (it froze for seconds), only around the
        post on screen."""
        self.win.cfg["feed"]["build_at_once"] = 10
        pic = [{"id": "m", "type": "image", "url": "https://x/p.png",
                "preview_url": "https://x/p.png", "meta": {}}]
        for i in range(80):
            st = status(f"6{i:03d}", NEWS, minute=i % 60, text=f"пост {i}")
            if i in (41, 77):  # the first and the last have pictures: the old window
                st["media_attachments"] = pic  # then spans the whole lane
            self.world.add(st, home=True)
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.core.poll_once()
        self.win.select_lane("bots")
        lane = self.win.lane_widgets["bots"]
        self.pump(1.0)
        for kind in ("text", "gifv", "video", "audio"):
            lane.media_filter.actions[kind].setChecked(False)  # pictures only
        self.pump(0.3)
        self.assertLessEqual(len(lane.view.model), 2)
        lane.media_filter.reset()
        self.pump(0.3)
        self.assertGreaterEqual(len(lane.view.model), 40)  # a page of the lane is back
        self.assertLessEqual(len(lane.view.rows), 3 * 10)  # but not all built

    def test_posts_scrolled_past_count_as_read(self):
        """read.mark_read = on_scroll: a post that was on screen and that the reader went
        on past is read, even if it was never all on screen while the feed stood still —
        and in a window without focus too, as long as the reader scrolls it by hand."""
        for i in range(40):
            self.world.add(status(f"7{i:02d}", NEWS, minute=i % 60,
                                  text="пост " * 40 + str(i)), home=True)
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.core.poll_once()
        self.win.select_lane("bots")
        view = self.win.lane_widgets["bots"].view
        self.pump(until=lambda: len(view.unread_keys()) > 10)
        self.pump(2.0)  # the opening position settles
        view._drop_target()
        seen = []
        view.seen.connect(seen.extend)
        sb = view.verticalScrollBar()
        keys = [k for k in view.unread_keys() if view.rows[k].height() < view.viewport().height()]
        row = view.rows[keys[len(keys) // 2]]
        top = view._top(row)
        view._touched()
        sb.setValue(top + 10)  # its head already gone above: never all on screen
        view._emit_seen()
        self.assertNotIn(row.status_id, seen)
        sb.setValue(top + row.height() + 5)  # and on past it
        view._emit_seen()
        self.assertIn(row.status_id, seen)

        # a post that never was on screen (jumped over) stays unread
        far = view.rows[keys[-1]]
        if view._top(far) > sb.value() + view.viewport().height():
            self.assertNotIn(far.status_id, seen)

        # without focus and without the reader's hand: nothing counts
        view._touched_at = 0.0
        view._window_active = lambda: False
        seen.clear()
        sb.setValue(view._top(far) - 5)
        view._emit_seen()
        self.assertEqual(seen, [])
        view._touched()  # the wheel over the window: it's being read
        view._emit_seen()
        self.assertIn(far.status_id, seen)

    def test_hidden_lane_lets_its_cards_go(self):
        """ui.unload_hidden_minutes: a lane long out of sight drops its cards and draws
        them anew when opened; the lane in front never does."""
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.core.poll_once()
        self.win.select_lane("people")
        people = self.win.lane_widgets["people"]
        self.pump(until=lambda: len(people.view.rows) > 1)
        people._unload()  # in front: kept
        self.assertTrue(people.view.rows)
        self.win.select_lane("bots")
        self.pump(0.2)
        self.assertTrue(people._unload_timer.isActive())
        people._unload()
        self.assertEqual(people.view.rows, {})
        self.core.poll_once()  # updates while unloaded: still nothing drawn while hidden
        self.pump(0.2)
        self.assertEqual(people.view.rows, {})
        self.win.select_lane("people")
        self.pump(until=lambda: len(people.view.rows) > 1)
        self.assertFalse(people._unload_timer.isActive())

    def test_social_tabs_and_dialogs(self):
        """0.11: who liked (tab), quotes, trends, suggestions, about the server, the
        post menu entries, a boost shown inside a boost card; nothing falls over."""
        from PySide6.QtWidgets import QMenu

        from fedtail.frontends.qt.card import CardSpec, PostRow
        from fedtail.frontends.qt.social import (
            AccountsWidget,
            QuotesWidget,
            ServerInfoDialog,
            TrendsWidget,
        )
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.core.poll_once()
        st = self.core.store.get_status("011")
        self.world.reactions["011"] = {"favourited_by": [NEWS], "reblogged_by": []}
        st = dict(st, favourites_count=1)
        self.core.store.put_statuses([st])
        row = PostRow(CardSpec(key="011", status=st, unread=True), self.win.ctx)
        texts = [a.text() for m in row.findChildren(QMenu) for a in m.actions()]
        from fedtail.i18n import _
        self.assertIn(_("who_favourited_by_n", n=1), texts)
        self.assertIn(_("mark_one_read"), texts)
        self.win.on_link("fedtail:favourited_by/011")
        tab = self.win.tabs.currentWidget()
        self.assertIsInstance(tab, AccountsWidget)
        self.pump(until=lambda: tab.count == 1)
        self.win.on_link("fedtail:readone/011")
        self.assertNotIn("011", self.core.unread_ids([(None, st)]))
        # quotes of my post, trends, suggestions, the server
        mine = self.core.store.get_status("010")
        self.world.quotes["010"] = []
        self.win.open_quotes(mine)
        self.assertIsInstance(self.win.tabs.currentWidget(), QuotesWidget)
        self.world.trends = {"statuses": [], "tags": [{"name": "linux", "history": []}],
                             "links": []}
        self.win.open_trends()
        self.assertIsInstance(self.win.tabs.currentWidget(), TrendsWidget)
        self.world.suggested = [NEWS]
        self.win.open_suggestions()
        sugg = self.win.tabs.currentWidget()
        self.pump(until=lambda: sugg.count == 1)
        dlg = ServerInfoDialog(self.win, self.core.server_info().result())
        dlg.show()
        dlg.close()
        # a boost of the post shows the like/boost made on the post
        boost = {"id": "rb9", "account": ME, "reblog": st, "created_at": st["created_at"],
                 "content": "", "media_attachments": []}
        view = self.win.lane_widgets.get("people")
        if view is not None:
            view = view.view
            view.set_specs([CardSpec(key="rb9", status=boost)])
            self.win.on_event("status_updated", dict(st, reblogged=True))
            self.assertTrue(view.model[0].status["reblog"]["reblogged"])

    def test_terminal_theme(self):
        from fedtail.frontends.qt import theme as themes
        cfg, _ = config.validate({"ui": {"theme": "terminal"}})
        t = themes.apply(self.app, cfg)
        self.assertEqual(t.bg, "#000000")


if __name__ == "__main__":
    unittest.main()

    def test_announcements_banner(self):
        self.world.announcements = [
            {"id": "a1", "content": "<p>Обновление в полночь</p>", "read": False,
             "published_at": "2099-10-14T09:00:00.000Z"},
            {"id": "a2", "content": "<p>Новые правила</p>", "read": False,
             "published_at": "2099-10-14T10:00:00.000Z"},
            {"id": "a0", "content": "<p>старое</p>", "read": True}]
        self.win.start()
        bar = self.win.announce_bar
        self.pump(until=lambda: bar.isVisible())
        self.assertIn("полночь", bar.body.text())
        self.assertIn("ещё 1", bar.head.text())
        bar.ok.click()
        self.assertIn("правила", bar.body.text())
        self.pump(until=lambda: self.world.announcements[0]["read"])
        bar.ok.click()
        self.assertFalse(bar.isVisible())
        self.core.cfg["ui"]["announcements"] = "off"
        self.assertEqual(self.bridge_wait(self.core.announcements()), [])

    def test_filtered_notifications_dialog(self):
        self.world.policy = {"for_not_following": "accept", "for_not_followers": "accept",
                             "for_new_accounts": "filter", "for_private_mentions": "filter",
                             "for_limited_accounts": "filter"}
        self.world.held = [{"id": "r1", "account": BOB, "notifications_count": "3",
                            "last_status": {"content": "<p>здравствуйте</p>"}}]
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        dlg = self.win.show_filtered()
        self.pump(until=lambda: dlg.list.count() == 1)
        self.assertIn("здравствуйте", dlg.list.item(0).text())
        self.assertEqual(dlg.combos["for_new_accounts"].currentData(), "filter")
        dlg.combos["for_not_following"].setCurrentIndex(2)  # drop
        self.pump(until=lambda: self.world.policy["for_not_following"] == "drop")
        dlg.list.setCurrentRow(0)
        dlg.accept_btn.click()
        self.pump(until=lambda: self.world.answered == [("r1", True)])
        self.pump(until=lambda: dlg.list.count() == 0)
        dlg.close()
        self.world.policy = None
        dlg = self.win.show_filtered()
        self.pump(until=lambda: not dlg.accept_btn.isEnabled())
        dlg.close()
