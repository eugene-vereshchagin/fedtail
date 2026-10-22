"""The debugging corner: Qt's and GTK's say the same fields in the same order."""

import unittest

from fedtail import i18n
from fedtail.frontends.common import corner


class CornerTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_same_fields_both_toolkits(self):
        qt = corner.text("point", "Qt 6.8.2", "", "Open Sans 10pt", "xcb", 1.25)
        gtk = corner.text("point", "GTK 4.18.6", "libadwaita", "Open Sans 10pt", "X11", 1)
        self.assertEqual(qt, "theme point · Qt 6.8.2 · Open Sans 10pt · x11 · 125% · source")
        self.assertEqual(gtk, "theme point · GTK 4.18.6 · libadwaita · Open Sans 10pt · x11 "
                              "· 100% · source")
        self.assertNotIn("·  ·", qt)  # an empty field is left out, not "· ·"
        self.assertEqual(corner.display_word("Wayland"), "wayland")
