"""GTK on X11 takes the desktop's 125 % as a text DPI when it has none of its own."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from fedtail.frontends.gtk import scale
    HAVE = True
except ImportError:
    HAVE = False


@unittest.skipUnless(HAVE, "no GTK 4")
class ScaleTest(unittest.TestCase):
    def test_kdeglobals(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "kdeglobals").write_text("[KScreen]\nScaleFactor=1.25\n")
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": d}):
                self.assertEqual(scale._kde_dpi(), 120.0)
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": d + "/none"}):
                self.assertIsNone(scale._kde_dpi())

    def test_xrdb_first(self):
        with mock.patch.object(scale, "_xrdb_dpi", return_value=144.0), \
                mock.patch.object(scale, "_kde_dpi", return_value=120.0):
            self.assertEqual(scale.desktop_dpi(), 144.0)
        with mock.patch.object(scale, "_xrdb_dpi", return_value=None), \
                mock.patch.object(scale, "_kde_dpi", return_value=120.0):
            self.assertEqual(scale.desktop_dpi(), 120.0)
