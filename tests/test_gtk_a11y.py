"""ui.accessibility: GTK's accessibility bus only while a screen reader is on (auto),
always (on), never (off) — GTK_A11Y set before the first widget; set by hand, kept."""

import os
import unittest
from unittest import mock

try:
    from fedtail.frontends import gtk
    HAVE = True
except ImportError:
    HAVE = False


@unittest.skipUnless(HAVE, "no GTK 4")
class AccessibilityTest(unittest.TestCase):
    def run_with(self, mode, reader=False, env=None):
        with mock.patch.dict(os.environ, env or {}, clear=False):
            if not env:
                os.environ.pop("GTK_A11Y", None)
            with mock.patch.object(gtk, "screen_reader_on", return_value=reader):
                on = gtk.accessibility(mode)
                return on, os.environ.get("GTK_A11Y")

    def test_modes(self):
        self.assertEqual(self.run_with("auto"), (False, "none"))
        self.assertEqual(self.run_with("auto", reader=True), (True, None))
        self.assertEqual(self.run_with("on"), (True, None))
        self.assertEqual(self.run_with("off", reader=True), (False, "none"))
        self.assertEqual(self.run_with("off", env={"GTK_A11Y": "atspi"}), (True, "atspi"))
