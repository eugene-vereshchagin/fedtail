"""The Qt editor's emoji picker and "New draft" button, offscreen."""

import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QPushButton
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

from fedtail import i18n  # noqa: E402
from fedtail.core import auth, config, paths  # noqa: E402
from fedtail.core.app import Core  # noqa: E402

from . import fakes  # noqa: E402
from .fakes import FakeApi  # noqa: E402


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class QtEmojiDraftsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from fedtail.frontends.qt import theme as themes
        from fedtail.frontends.qt.bridge import Bridge
        from fedtail.frontends.qt.window import MainWindow

        i18n.setup("en")
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        tmp = Path(self._tmp.name)
        FakeApi.world = fakes.World()
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False},
                                  "post": {"drafts_autosave": True}})
        p = paths.resolve("t", config=str(tmp / "c.toml"), data=str(tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        self.core = Core(cfg, p, api_class=FakeApi)
        self.core._origin_json = lambda url: None
        self.bridge = Bridge(self.core)
        self.theme = themes.apply(self.app, cfg)
        self.win = MainWindow(self.core, self.bridge, self.theme)
        self.win.images.get = lambda url, cb, *a, **k: None
        self.win.show()
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)

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
        return False

    def test_picker_inserts_standard_and_server_emoji(self):
        from fedtail.frontends.qt.compose import Compose
        dlg = Compose(self.win)
        dlg.text.setPlainText("hi ")
        dlg.text.moveCursor(dlg.text.textCursor().MoveOperation.End)
        dlg.pick_emoji()
        pk = dlg.emoji_picker
        self.assertTrue(pk.isVisible())
        self.pump(until=lambda: pk._server is not None)
        std = [b for b in pk.standard[0].findChildren(QPushButton) if b.toolTip()]
        self.assertTrue(std)
        std[0].click()
        self.assertTrue(dlg.text.toPlainText().startswith("hi " + std[0].text()))
        pk.search.setText("zzzqqqxx")
        pk.refresh()
        self.assertFalse([b for b in pk.standard[0].findChildren(QPushButton)])
        pk._got([{"shortcode": "blob", "url": "u", "static_url": "u", "category": "c"}])
        pk.search.setText("")
        pk.refresh()
        btns = pk.server[0].findChildren(QPushButton)
        self.assertEqual(len(btns), 1)
        btns[0].click()
        self.assertTrue(dlg.text.toPlainText().endswith(":blob: "))
        dlg.sent = True
        dlg.reject()

    def test_new_draft_sets_aside_and_clears(self):
        from fedtail.frontends.qt.compose import Compose
        dlg = Compose(self.win)
        self.assertFalse(dlg.shelve_btn.isHidden())
        dlg.text.setPlainText("first thoughts")
        dlg.shelve()
        self.assertEqual(dlg.text.toPlainText(), "")
        self.assertEqual(dlg.hint.text(), i18n._("draft_shelved"))
        self.assertIsNone(self.core.get_draft("new"))
        dlg.save_draft()  # the clean editor leaves nothing behind
        self.assertIsNone(self.core.get_draft("new"))
        dlg.sent = True
        dlg.reject()

    def test_no_button_when_drafts_place_is_off(self):
        from fedtail.frontends.qt.compose import Compose
        self.core.cfg["post"]["drafts_place"] = False
        dlg = Compose(self.win)
        self.assertTrue(dlg.shelve_btn.isHidden())
        dlg.sent = True
        dlg.reject()

    def test_open_draft_reloads_an_open_editor(self):
        from fedtail.frontends.qt.compose import Compose
        dlg = Compose(self.win)
        dlg.show()
        dlg.text.setPlainText("old text")
        self.core.store.save_draft("new", {"text": "from drafts", "cw": "",
                                           "visibility": "public", "media": []})
        self.win.compose(text="from drafts")
        self.assertEqual(dlg.text.toPlainText(), "from drafts")
        dlg.save_draft()
        self.assertEqual(self.core.get_draft("new")["text"], "from drafts")
        dlg.sent = True
        dlg.reject()


if __name__ == "__main__":
    unittest.main()
