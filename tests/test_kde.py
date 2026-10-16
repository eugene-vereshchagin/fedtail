"""KDE's look taken from kdeglobals when Qt can't load KDE's integration."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class KdeGlobalsTest(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        Path(self._tmp.name, "kdeglobals").write_text(
            "[General]\nfont=Noto Sans,11,-1,5,400,0,0,0,0,0,0,0,0,0,0,1\n\n"
            "[Colors:View]\nBackgroundNormal=20,22,24\nForegroundNormal=230,231,232\n\n"
            "[Colors:Selection]\nBackgroundNormal=200,50,60\n", "utf-8")

    def test_palette_and_font_from_kdeglobals(self):
        from PySide6.QtGui import QPalette

        from fedtail.frontends.qt import kde
        keep_pal, keep_font, keep_style = self.app.palette(), self.app.font(), \
            self.app.style().name()
        self.addCleanup(lambda: (self.app.setPalette(keep_pal), self.app.setFont(keep_font),
                                 self.app.setStyle(keep_style)))
        env = {"XDG_CONFIG_HOME": self._tmp.name, "XDG_CURRENT_DESKTOP": "KDE"}
        with mock.patch.dict(os.environ, env), mock.patch.object(kde.sys, "platform", "linux"):
            done = kde.adopt(self.app)
        self.assertIn("KDE colours", done)
        pal = self.app.palette()
        R = QPalette.ColorRole
        self.assertEqual(pal.color(R.Base).getRgb()[:3], (20, 22, 24))
        self.assertEqual(pal.color(R.Text).getRgb()[:3], (230, 231, 232))
        self.assertEqual(pal.color(R.Highlight).getRgb()[:3], (200, 50, 60))
        self.assertEqual(pal.color(R.Window).getRgb()[:3], (239, 240, 241))  # Breeze default
        self.assertEqual(self.app.font().pointSize(), 11)

    def test_nothing_outside_kde(self):
        from fedtail.frontends.qt import kde
        with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "GNOME"}):
            self.assertEqual(kde.adopt(self.app), "")


if __name__ == "__main__":
    unittest.main()
