"""fedtail's own button pictures: each a well-formed SVG with the theme's colours to
fill in, and every one the code asks for is there."""

import re
import unittest
import xml.dom.minidom
from pathlib import Path

DIR = Path(__file__).resolve().parents[1] / "fedtail" / "data" / "icons" / "ui"
ROOT = Path(__file__).resolve().parents[1] / "fedtail" / "frontends" / "qt"


class IconsTest(unittest.TestCase):
    def test_each_parses_and_takes_colours(self):
        files = sorted(DIR.glob("*.svg"))
        self.assertGreater(len(files), 10)
        for f in files:
            text = f.read_text(encoding="utf-8")
            self.assertIn("{c}", text, f.name)
            xml.dom.minidom.parseString(
                text.replace("{c}", "#000").replace("{l}", "#fff").replace("{d}", "#111"))

    def test_every_picture_asked_for_exists(self):
        have = {f.stem for f in DIR.glob("*.svg")}
        asked = set()
        for f in ("dock.py", "roster.py"):
            src = (ROOT / f).read_text(encoding="utf-8")
            asked |= set(re.findall(r'icons\.dress\(\s*[\w.]+,\s*"(\w+)"', src))
            asked |= set(re.findall(r'icons?\.icon\("(\w+)"', src))
        asked |= {"public", "unlisted", "private", "direct", "status", "talk", "thread",
                  "reply", "star", "star_full", "boost", "bookmark", "nobody"}
        self.assertTrue(asked)
        self.assertEqual(asked - have, set())


    def test_psi_pictures_come_with_their_licence(self):
        psi = DIR.parent / "psi"
        self.assertTrue((psi / "LICENSE.txt").is_file())
        listed = (psi / "LICENSE.txt").read_text(encoding="utf-8")
        for f in psi.glob("*.png"):
            self.assertIn(f.name, listed)
