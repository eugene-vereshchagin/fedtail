import os
import tempfile
import unittest

from fedtail.frontends import themefile


class ThemeFileTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._tmp.name
        self.dir = themefile.user_dir()
        self.dir.mkdir(parents=True)

    def tearDown(self):
        if self.old is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self.old
        self._tmp.cleanup()

    def write(self, name, text):
        (self.dir / f"{name}.toml").write_text(text, "utf-8")

    def test_builtins_are_complete_and_valid(self):
        ref = themefile.reference()
        for name in ("system", "terminal"):
            theme, warnings = themefile.load(name)
            self.assertEqual(warnings, [], name)
            for section in ("font", "colors", "shape", "words"):
                self.assertEqual(set(theme[section]), set(ref[section]), name)

    def test_inherit_and_override(self):
        self.write("mine", 'name = "Mine"\ninherit = "terminal"\n[colors]\ntext = "#a8ff60"\n')
        theme, _ = themefile.load("mine")
        self.assertEqual(theme["colors"]["text"], "#a8ff60")
        self.assertEqual(theme["shape"]["card_style"], "rule")      # from terminal
        self.assertEqual(theme["words"]["date"], "{dd}.{mm} {time}")
        self.assertIn("mine", themefile.available())

    def test_user_file_wins_over_builtin(self):
        self.write("terminal", 'inherit = "system"\n[colors]\ntext = "#123456"\n')
        theme, _ = themefile.load("terminal")
        self.assertEqual(theme["colors"]["text"], "#123456")

    def test_errors(self):
        self.write("bad", 'inherit = "system"\n[colors]\ntext = "green"\n'
                          '[shape]\ncard_style = "blob"\nradius = "big"\n')
        with self.assertRaises(themefile.ThemeError) as e:
            themefile.load("bad")
        for word in ("colors.text", "card_style", "radius"):
            self.assertIn(word, str(e.exception))
        self.write("loop1", 'inherit = "loop2"\n')
        self.write("loop2", 'inherit = "loop1"\n')
        with self.assertRaises(themefile.ThemeError):
            themefile.load("loop1")
        with self.assertRaises(themefile.ThemeError):
            themefile.load("nope")
        self.write("odd", 'inherit = "system"\n[colors]\nsparkle = "#ffffff"\n')
        _, warnings = themefile.load("odd")
        self.assertEqual(warnings, ["unknown key colors.sparkle"])

    def test_debug_theme_marks_every_state(self):
        merged, warnings = themefile.load("debug")
        self.assertEqual(warnings, [])
        self.assertIs(merged["shape"]["debug"], True)
        self.assertIs(themefile.load("nord")[0]["shape"]["debug"], False)

    def test_point_looks_like_point(self):
        merged, warnings = themefile.load("point")
        self.assertEqual(warnings, [])
        shape, colors = merged["shape"], merged["colors"]
        self.assertEqual((shape["avatar_shape"], shape["card_header"], shape["short_id"],
                          shape["actions_align"], shape["card_style"]),
                         ("square", "stacked", "footer", "right", "rule"))
        self.assertEqual(colors["primary"], "#3c3c3c")  # the dark "Create" button
        system = themefile.load("system")[0]["shape"]
        self.assertEqual((system["avatar_shape"], system["short_id"]), ("circle", "header"))
        self.assertEqual((shape["rule"], shape["header_stripes"]), ("solid", True))
        self.assertEqual((system["rule"], system["header_stripes"]), ("dashed", False))

    def test_install_copies(self):
        themefile.install_copies()
        self.assertTrue((self.dir / "builtin" / "terminal.toml").exists())
        self.assertTrue((self.dir / "README.txt").exists())
        # copies in builtin/ are not themes of their own
        self.assertEqual(themefile.available(),
                         ["bnw", "contrast", "debug", "juick", "juick-classic", "night", "nord",
                          "paper", "pink", "point", "solarized", "system", "terminal"])


try:
    import PySide6.QtGui  # noqa: F401
except ImportError:
    PySide6 = None


@unittest.skipIf(PySide6 is None, "PySide6 is not installed")
class StripesTest(unittest.TestCase):
    def test_tile_is_drawn_once_in_the_header_colour(self):
        from PySide6.QtGui import QColor, QGuiApplication, QImage
        QGuiApplication.instance() or QGuiApplication([])
        from fedtail.frontends.qt.theme import stripe_tile
        path = stripe_tile(QColor("#efefef"))
        img = QImage(path)
        self.assertEqual((img.width(), img.height()), (10, 10))
        colors = {img.pixelColor(x, y).name() for x in range(10) for y in range(10)}
        self.assertIn("#efefef", colors)  # the band itself
        self.assertGreater(len(colors), 1)  # and the stripes on it
        self.assertEqual(stripe_tile(QColor("#efefef")), path)  # not drawn again


if __name__ == "__main__":
    unittest.main()
