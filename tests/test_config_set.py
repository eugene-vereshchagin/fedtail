"""One option written into the user's config file, the rest of it untouched
(config_update.set_option — the phone's settings page)."""

import tomllib
import unittest

from fedtail.core.config_update import set_option

TEXT = """# my notes
[ui]
# the theme
theme = "system"
#font_size = 0

[feed]
order = "oldest_first"
"""


class SetOptionTest(unittest.TestCase):
    def test_a_set_option_is_rewritten_in_place(self):
        out = set_option(TEXT, "ui", "theme", "point")
        self.assertIn('theme = "point"', out)
        self.assertIn("# my notes", out)
        self.assertIn("# the theme", out)
        self.assertEqual(tomllib.loads(out)["feed"]["order"], "oldest_first")

    def test_a_commented_option_gets_a_line_under_it(self):
        out = set_option(TEXT, "ui", "font_size", 14)
        self.assertIn("#font_size = 0\nfont_size = 14", out)
        self.assertEqual(tomllib.loads(out)["ui"]["font_size"], 14)

    def test_a_new_option_goes_to_the_end_of_its_section(self):
        out = set_option(TEXT, "ui", "command_line", False)
        self.assertEqual(tomllib.loads(out)["ui"]["command_line"], False)
        self.assertLess(out.index("command_line"), out.index("[feed]"))

    def test_a_missing_section_is_added(self):
        out = set_option(TEXT, "phone", "pinned", ["home", "list:Новости"])
        self.assertEqual(tomllib.loads(out)["phone"]["pinned"], ["home", "list:Новости"])
        self.assertEqual(tomllib.loads(out)["ui"]["theme"], "system")

    def test_the_same_key_in_another_section_is_left_alone(self):
        out = set_option(TEXT + "\n[tui]\ntheme = \"nord\"\n", "ui", "theme", "point")
        got = tomllib.loads(out)
        self.assertEqual((got["ui"]["theme"], got["tui"]["theme"]), ("point", "nord"))


if __name__ == "__main__":
    unittest.main()
