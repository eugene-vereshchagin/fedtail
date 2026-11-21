"""The Qt window driven as a person drives it: the real pointer drags a file from another
window, the real keyboard types (xdotool under Xvfb, Qt on xcb). The smoke tests send
events to the widgets themselves, so a shortcut of the window that takes the key first,
or a text field that takes a drop as its text, is never seen: Ctrl+K in the editor went
to the search box, a picture dropped on the input line went in as "file:///…" (21.11).

Runs where Qt is on X11 (QT_QPA_PLATFORM=xcb) with xdotool — CI runs it so, a step of its
own (the offscreen smoke tests share their process); elsewhere it is skipped, unless
FEDTAIL_BY_HAND is set: then a skip would hide exactly this, so it fails instead.
"""

import os
import shutil
import struct
import subprocess
import tempfile
import time
import unittest
import zlib
from pathlib import Path

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

from fedtail import i18n
from fedtail.core import auth, config, paths
from fedtail.core.app import Core

from . import fakes
from .fakes import BOB, FakeApi, status

MUST = bool(os.environ.get("FEDTAIL_BY_HAND"))


def _can():
    if not (HAVE_QT and os.environ.get("QT_QPA_PLATFORM") == "xcb" and
            os.environ.get("DISPLAY") and shutil.which("xdotool")):
        return False
    app = QApplication.instance()
    return app is None or app.platformName() == "xcb"


def _png(path):
    def chunk(k, d):
        return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(
        ">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(
            b"\x00\x10\x20\x30")) + chunk(b"IEND", b""))
    return path


def pump(until=None, timeout=1.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QApplication.processEvents()
        if until is not None and until():
            return True
        time.sleep(0.01)
    return until() if until is not None else True


class QtByHandTest(unittest.TestCase):
    UI = {}

    @classmethod
    def setUpClass(cls):
        if not _can():
            if MUST:
                raise AssertionError("Qt on xcb, an X display and xdotool are needed here")
            raise unittest.SkipTest("not Qt on X11 with xdotool")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from fedtail.frontends.qt import theme as themes
        from fedtail.frontends.qt.bridge import Bridge
        from fedtail.frontends.qt.window import MainWindow
        i18n.setup("ru")
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        tmp = Path(self._tmp.name)
        FakeApi.world = self.world = fakes.World()
        st = status("011", BOB, minute=11, text="#georgia")
        st["tags"] = [{"name": "georgia"}]
        self.world.add(st, home=True)
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False},
                                  "account": {"markdown": "on"},
                                  "ui": {"arts_mode": False, **self.UI},
                                  "lanes": {"enabled": list(fakes.CLASSIC_LANES)}})
        p = paths.resolve("t", config=str(tmp / "c.toml"), data=str(tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        self.core = Core(cfg, p, api_class=FakeApi)
        self.core._origin_json = lambda url: None
        self.bridge = Bridge(self.core)
        self.win = MainWindow(self.core, self.bridge, themes.apply(self.app, cfg))
        self.win.images.get = lambda url, cb, *a, **k: None
        self.win.resize(900, 700)
        self.win.move(200, 0)
        self.win.show()
        self.win.start()
        pump(lambda: self.core.me is not None, 5)
        self.core.poll_once()
        if self.win.dock is not None:  # split: the roster comes first; the messages
            self.win.show_raise()      # window with its input line, a lane open
            self.win.select_lane("home")
            pump(timeout=1.0)  # the start lane opened (the curtain lowered meanwhile)
            self.win.right_stack.setCurrentIndex(0)  # out from under the curtain
            pump(lambda: self.win.dock.text.isVisible(), 3)
        self.pic = _png(tmp / "drop.png")
        self.src = self._source()

    def tearDown(self):
        self.src.close()
        if getattr(self.win, "roster", None) is not None:
            self.win.roster.close()
        self.win.quitting = True
        self.win.tray = None
        self.win.hide()
        self.win.deleteLater()
        self.core.shutdown()
        pump(timeout=0.1)
        self._tmp.cleanup()

    def _source(self):
        """A window to drag from: a file manager's file, as its address list and as
        text (which a text field takes)."""
        from PySide6.QtCore import QMimeData, Qt, QUrl
        from PySide6.QtGui import QDrag
        from PySide6.QtWidgets import QLabel
        pic = self.pic

        class Source(QLabel):
            def mousePressEvent(self, e):
                self._at = e.position()

            def mouseMoveEvent(self, e):
                if not e.buttons() & Qt.MouseButton.LeftButton:
                    return
                mime = QMimeData()
                mime.setUrls([QUrl.fromLocalFile(str(pic))])
                mime.setText(QUrl.fromLocalFile(str(pic)).toString())
                drag = QDrag(self)
                drag.setMimeData(mime)
                drag.exec(Qt.DropAction.CopyAction)

        src = Source("drag me")
        src.resize(120, 120)
        src.move(0, 0)
        src.show()
        pump(lambda: src.isVisible(), 2)
        pump(timeout=0.3)
        return src

    @staticmethod
    def _at(widget, dx=10, dy=10):
        from PySide6.QtCore import QPoint
        p = widget.mapToGlobal(QPoint(dx, dy))
        return p.x(), p.y()

    def xdo(self, *chain, timeout=15):
        """One xdotool run, events pumped meanwhile (a drag runs a loop of its own in
        the middle of it)."""
        proc = subprocess.Popen(["xdotool", *map(str, chain)])
        pump(lambda: proc.poll() is not None, timeout)
        if proc.poll() is None:
            proc.kill()
        pump(timeout=0.3)

    def drag_to(self, widget, dx=10, dy=10):
        x0, y0 = self._at(self.src, 5, 5)
        x1, y1 = self._at(widget, dx, dy)
        chain = ["mousemove", x0, y0, "mousedown", 1]
        for i in range(1, 25):
            chain += ["sleep", 0.03, "mousemove", x0 + (x1 - x0) * i // 24,
                      y0 + (y1 - y0) * i // 24]
        self.xdo(*chain, "sleep", 0.3, "mouseup", 1)
        pump(timeout=0.5)

    def type_into(self, widget, text, *keys):
        widget.window().activateWindow()
        widget.setFocus()
        pump(lambda: widget.hasFocus(), 2)
        if text:  # "type" takes every word after it as text: a run of its own
            self.xdo("type", "--delay", 30, text)
        for k in keys:
            self.xdo("key", k)

    # ---- the editor ---------------------------------------------------------------
    def editor(self):
        self.win.compose()
        dlg = self.win.composer if getattr(self.win, "composer", None) else None
        if dlg is None:
            from fedtail.frontends.qt.compose import Compose
            dlg = next(w for w in self.win.findChildren(Compose) if w.isVisible())
        pump(lambda: dlg.text.isVisible(), 3)
        return dlg

    def test_ctrl_k_in_the_editor_makes_a_link(self):
        """The editor inside the window: its Ctrl+K and the window's (search) both live —
        Qt ran neither, the focus went to the search box (21.11)."""
        dlg = self.editor()
        self.assertIsNotNone(dlg.format_bar)
        self.type_into(dlg.text, "hi", "ctrl+a", "ctrl+k")
        self.assertEqual(dlg.text.toPlainText(), "[hi](https://)")
        self.assertTrue(dlg.text.hasFocus())

    def test_ctrl_enter_sends(self):
        dlg = self.editor()
        self.type_into(dlg.text, "hello", "ctrl+Return")
        self.assertTrue(pump(lambda: self.world.posted, 5), "not sent")
        self.assertEqual(self.world.posted[-1][0], "hello")

    def test_tab_completes_a_tag(self):
        dlg = self.editor()
        self.assertTrue(pump(lambda: self.core.store.tag_counts(compute=False), 3))
        self.type_into(dlg.text, "hi #geo")
        pump(timeout=0.5)
        self.type_into(dlg.text, "", "Tab")
        self.assertEqual(dlg.text.toPlainText(), "hi #georgia ")

    def test_a_picture_dropped_on_the_editors_text_is_attached(self):
        dlg = self.editor()
        self.drag_to(dlg.text)
        self.assertTrue(pump(lambda: [m[0] for m in dlg._media_list()] == [str(self.pic)], 3),
                        f"not attached; the text has {dlg.text.toPlainText()!r}")
        self.assertNotIn("file://", dlg.text.toPlainText())


class QtSplitByHandTest(QtByHandTest):
    UI = {"layout": "split"}

    def test_a_picture_dropped_on_the_input_line_is_attached(self):
        dock = self.win.dock
        self.assertTrue(dock.text.isVisible())
        self.drag_to(dock.text)
        self.assertEqual([p for p, _d in dock.media], [str(self.pic)],
                         f"the text has {dock.text.toPlainText()!r}")
        self.assertNotIn("file://", dock.text.toPlainText())

    def test_ctrl_k_in_the_input_line_makes_a_link(self):
        dock = self.win.dock
        self.assertTrue(dock.text.isVisible())
        self.type_into(dock.text, "hi", "ctrl+a", "ctrl+k")
        self.assertEqual(dock.text.toPlainText(), "[hi](https://)")

    # the editor's own tests: the split layout writes in its input line
    test_ctrl_k_in_the_editor_makes_a_link = None
    test_ctrl_enter_sends = None
    test_tab_completes_a_tag = None
    test_a_picture_dropped_on_the_editors_text_is_attached = None


if __name__ == "__main__":
    unittest.main()
