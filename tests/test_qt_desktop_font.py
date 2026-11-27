"""Qt without the desktop's integration gives the application a bare "Sans": the theme
puts a real family first (the desktop's, or what fontconfig makes of "Sans"), or the
colour emoji fonts after it win and every letter takes their metrics (the AppImage on
Cinnamon, 28.11)."""

import copy
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtGui import QFont, QFontDatabase, QFontInfo
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class DesktopFontTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from fedtail.frontends.qt import theme
        self.theme = theme
        self.saved = (QFont(self.app.font()), theme._desktop)
        theme._desktop = None  # as at the start: the desktop's font is taken anew

    def tearDown(self):
        self.app.setFont(self.saved[0])
        self.theme._desktop = self.saved[1]

    def apply(self):
        from fedtail import sysenv
        from fedtail.core import config
        cfg = copy.deepcopy(config.DEFAULTS)
        with mock.patch.object(sysenv, "desktop_font", return_value=None):
            self.theme.apply(self.app, cfg)
        return self.app.font()

    def test_bare_sans_becomes_a_real_family(self):
        self.app.setFont(QFont("Sans", 10))
        f = self.apply()
        have = {x.lower() for x in QFontDatabase.families()}
        self.assertIn(f.families()[0].lower(), have)
        self.assertNotIn(QFontInfo(f).family(), self.theme.EMOJI_FONTS)
        self.assertEqual(f.pointSizeF(), 10)

    def test_the_desktops_own_font_when_it_says(self):
        real = QFontDatabase.families()[0]
        self.app.setFont(QFont("Sans", 10))
        from fedtail import sysenv
        with mock.patch.object(sysenv, "desktop_font", return_value=(real, 12.0)):
            self.assertIn(real, self.theme._real_desktop_font(self.app))
        self.assertEqual(self.app.font().families(), [real])
        self.assertEqual(self.app.font().pointSizeF(), 12)

    def test_a_real_font_is_left_alone(self):
        real = QFontDatabase.families()[0]
        self.app.setFont(QFont(real, 11))
        self.assertEqual(self.theme._real_desktop_font(self.app), "")
        self.assertEqual(self.app.font().family(), real)


if __name__ == "__main__":
    unittest.main()
