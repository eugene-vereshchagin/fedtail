"""fedtail's own button pictures: each built-in SVG well-formed with the theme's colours
to fill in, every picture the code asks for named in iconpack.NAMES (and so in every
pack, test_iconpack.py), Psi+'s with their licence."""

import re
import unittest
import xml.dom.minidom
from pathlib import Path

from fedtail.frontends import iconpack

PACKS = Path(__file__).resolve().parents[1] / "fedtail" / "data" / "icons" / "packs"
FRONTENDS = Path(__file__).resolve().parents[1] / "fedtail" / "frontends"


class IconsTest(unittest.TestCase):
    def test_each_parses_and_takes_colours(self):
        files = sorted(PACKS.glob("*/*.svg"))
        self.assertGreater(len(files), 10)
        for f in files:
            text = f.read_text(encoding="utf-8")
            self.assertIn("{c}", text, f.name)
            xml.dom.minidom.parseString(
                text.replace("{c}", "#000").replace("{l}", "#fff").replace("{d}", "#111"))

    def test_every_picture_asked_for_is_named(self):
        asked = set()
        for f in ("qt/dock.py", "qt/roster.py", "gtk/split.py"):
            src = (FRONTENDS / f).read_text(encoding="utf-8")
            asked |= set(re.findall(r'icons\.dress\(\s*[\w.]+,\s*"(\w+)"', src))
            asked |= set(re.findall(r'icons?\.(?:icon|image)\("(\w+)"', src))
        asked |= {"public", "unlisted", "private", "direct", "status", "talk", "thread",
                  "reply", "star", "star_full", "boost", "bookmark", "nobody"}
        self.assertTrue(asked)
        self.assertEqual(asked - set(iconpack.NAMES), set())
        self.assertEqual(set(iconpack.NAMES) - {f.stem for f in PACKS.glob("gloss/*.svg")},
                         set())  # the base pack has them all

    def test_psi_pictures_come_with_their_licence(self):
        psi = PACKS / "psi"
        self.assertTrue((psi / "LICENSE.txt").is_file())
        listed = (psi / "LICENSE.txt").read_text(encoding="utf-8")
        for f in psi.glob("*.png"):
            self.assertIn(f.name, listed)
