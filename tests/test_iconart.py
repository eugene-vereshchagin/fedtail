import unittest
from importlib import resources

from fedtail.frontends import iconart, themefile


class IconTest(unittest.TestCase):
    def test_every_builtin_theme_draws_an_icon(self):
        for name in themefile.available():
            data, _w = themefile.load(name)
            text = iconart.svg(iconart.colors(data.get("icon"), "#2a86c4", "#e8702a"))
            self.assertTrue(text.startswith("<svg"), name)
            self.assertNotIn("auto", text, name)
            self.assertNotIn("{", text, name)

    def test_auto_follows_the_accent(self):
        c = iconart.colors({"bg_top": "auto", "accent": "auto"}, "#000080", "#ff0000")
        self.assertEqual(c["accent"], "#ff0000")
        self.assertNotEqual(c["bg_top"], iconart.DEFAULT["bg_top"])

    def test_installed_icon_is_the_default_drawing(self):
        shipped = resources.files("fedtail").joinpath("data/icons/fedtail.svg").read_text("utf-8")
        self.assertEqual(shipped, iconart.svg(iconart.colors({})))


if __name__ == "__main__":
    unittest.main()
