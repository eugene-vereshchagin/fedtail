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
    """The GTK frontend draws the themes from palette.py, Qt from qt/theme.py: they
    must agree, or a theme looks different on the two."""

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def qpal(self, d):
        pal = QPalette()
        R = QPalette.ColorRole
        for role, c in [(R.Base, d.base), (R.Window, d.window), (R.Text, d.text),
                        (R.Highlight, d.highlight), (R.Link, d.link)]:
            pal.setColor(role, QColor(c.name()))
        return pal

    def test_all_themes_light_and_dark(self):
        from fedtail.frontends.qt.theme import Theme
        for name in sorted(p.stem for p in themefile.BUILTIN_DIR.glob("*.toml")):
            data, _w = themefile.load(name)
            for desk in (LIGHT, DARK):
                qt = Theme(data, self.qpal(desk)).c
                ours = palette.resolve(data["colors"], desk)
                for key, q in qt.items():
                    o = ours[key]
                    diff = max(abs(q.red() - o.r), abs(q.green() - o.g), abs(q.blue() - o.b),
                               abs(q.alpha() - o.a))
                    self.assertLessEqual(diff, 2, f"{name} {key}: Qt {q.name()} vs {o.css()}")


if __name__ == "__main__":
    unittest.main()
