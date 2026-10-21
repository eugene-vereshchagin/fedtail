"""frontends/palette.py: theme colours without a toolkit — and the same as Qt's."""

import unittest

from fedtail.frontends import palette, themefile
from fedtail.frontends.palette import Color, Desktop

try:
    from PySide6.QtGui import QColor, QGuiApplication, QPalette
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

LIGHT = Desktop(base=Color.parse("#ffffff"), window=Color.parse("#eff0f1"),
                text=Color.parse("#232629"), highlight=Color.parse("#3daee9"),
                link=Color.parse("#2980b9"))
DARK = Desktop(base=Color.parse("#1b1e20"), window=Color.parse("#202326"),
               text=Color.parse("#fcfcfc"), highlight=Color.parse("#3daee9"),
               link=Color.parse("#1d99f3"))


class ColorTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(Color.parse("#abc"), Color(0xaa, 0xbb, 0xcc))
        self.assertEqual(Color.parse("#11223380"), Color(0x11, 0x22, 0x33, 0x80))
        self.assertEqual(Color.parse("rgba(1, 2, 3, 0.5)").a, 128)
        self.assertEqual(Color.parse("rgba(1,2,3,200)").a, 200)
        self.assertEqual(Color.parse("rgb(9,8,7)"), Color(9, 8, 7))
        with self.assertRaises(ValueError):
            Color.parse("red")

    def test_css(self):
        self.assertEqual(Color(255, 0, 16).css(), "#ff0010")
        self.assertTrue(Color(1, 2, 3, 128).css().startswith("rgba(1,2,3,0.5"))

    def test_lighter_darker(self):
        grey = Color(100, 100, 100)
        self.assertEqual(grey.lighter(150), Color(150, 150, 150))
        self.assertEqual(grey.darker(200), Color(50, 50, 50))
        # past the top: saturation goes instead
        self.assertEqual(Color(255, 0, 0).lighter(150).r, 255)
        self.assertGreater(Color(255, 0, 0).lighter(150).g, 0)
        self.assertEqual(Color(10, 20, 30).lightness(), 20)
        self.assertEqual(Color(165, 77, 202).lightness(), 140)  # .5 goes up, as in Qt

    def test_readable_and_mix(self):
        self.assertEqual(palette.readable_on(Color(255, 255, 255)).name(), "#111111")
        self.assertEqual(palette.readable_on(Color(0, 0, 0)).name(), "#ffffff")
        self.assertEqual(palette.mix(Color(0, 0, 0), Color(200, 100, 50), 0.5),
                         Color(100, 50, 25))


class ResolveTest(unittest.TestCase):
    def test_every_builtin_theme_resolves(self):
        for name in sorted(p.stem for p in themefile.BUILTIN_DIR.glob("*.toml")):
            data, _w = themefile.load(name)
            for desk in (LIGHT, DARK):
                c = palette.resolve(data["colors"], desk)
                self.assertEqual(set(c), set(data["colors"]), name)
                self.assertTrue(all(isinstance(v, Color) for v in c.values()), name)

    def test_follows_and_tints(self):
        c = palette.resolve({"text": "#010203", "sidebar_text": "auto", "view": "#000000",
                             "accent": "#ffffff", "header": "auto", "header_end": "auto"},
                            LIGHT)
        self.assertEqual(c["sidebar_text"], Color(1, 2, 3))
        self.assertEqual(c["header"], palette.mix(c["view"], c["accent"], 0.16))
        self.assertEqual(c["header_end"], c["header"])

    def test_words(self):
        self.assertEqual(palette.word({"lowercase": True, "t": "== {text} =="}, "t", "Home"),
                         "== home ==")


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class SameAsQtTest(unittest.TestCase):
    """palette.py copies QColor's arithmetic (both windows draw a theme from it, and
    themes were made by looking at Qt): lightness, lighter, darker agree with QColor."""

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def test_arithmetic(self):
        import random
        rnd = random.Random(7)
        for _ in range(400):
            c = Color(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
            q = QColor(c.r, c.g, c.b)
            self.assertEqual(c.lightness(), q.lightness(), c)
            for f in (104, 112, 115, 130, 135, 145, 150, 170, 108):
                for ours, theirs in ((c.lighter(f), q.lighter(f)), (c.darker(f), q.darker(f))):
                    diff = max(abs(ours.r - theirs.red()), abs(ours.g - theirs.green()),
                               abs(ours.b - theirs.blue()))
                    self.assertLessEqual(diff, 2, f"{c} {f}: {ours.css()} vs {theirs.name()}")

    def test_qt_theme_takes_every_builtin(self):
        from fedtail.frontends.qt.theme import Theme
        pal = QPalette()
        for name in sorted(p.stem for p in themefile.BUILTIN_DIR.glob("*.toml")):
            data, _w = themefile.load(name)
            c = Theme(data, pal).c
            self.assertEqual(set(c), set(data["colors"]), name)


if __name__ == "__main__":
    unittest.main()
