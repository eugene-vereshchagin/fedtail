"""Arrays of tables ([[lanes.custom]]) written by config_edit: the lane editor and the
sync of lanes put the user's lanes into config.toml through it."""

import tempfile
import tomllib
import unittest
from pathlib import Path

from fedtail.core import config_edit

TEXT = '''[ui]
theme = "paper"

[lanes]
preset = "fedtail"
custom = []

# my posts, the way I like them
[[lanes.custom]]
name = "posts"
any = [{ author = "me" }]

# a note about the next one
[[lanes.custom]]
name = "old"
any = [{}]

[feed]
page_size = 40
'''


class TablesTest(unittest.TestCase):
    def test_replaced_in_place(self):
        new = [{"name": "posts", "icon": "my_posts", "any": [{"author": "me"}]},
               {"name": "pics", "title": {"en": "Pictures"},
                "any": [{"has": "image"}, {"has": "video"}], "none": [{"author": "bot"}]}]
        text = config_edit.set_tables(TEXT, "lanes", "custom", new)
        got = tomllib.loads(text)
        self.assertEqual(got["lanes"]["custom"], new)
        self.assertEqual(got["feed"]["page_size"], 40)
        self.assertEqual(got["ui"]["theme"], "paper")
        self.assertIn("# my posts, the way I like them", text)
        self.assertLess(text.index("name = \"pics\""), text.index("[feed]"))
        self.assertIn("#custom = []", text)  # TOML won't have both

    def test_none_left(self):
        text = config_edit.set_tables(TEXT, "lanes", "custom", [])
        self.assertNotIn("[[lanes.custom]]", text)
        self.assertEqual(tomllib.loads(text)["feed"]["page_size"], 40)

    def test_into_a_file_without_any(self):
        text = config_edit.set_tables("[ui]\ntheme = \"paper\"\n", "lanes", "custom",
                                      [{"name": "x", "any": [{}]}])
        self.assertEqual(tomllib.loads(text)["lanes"]["custom"], [{"name": "x", "any": [{}]}])

    def test_save_checks_what_it_wrote(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "config.toml"
            f.write_text(TEXT, "utf-8")
            new = [{"name": "posts", "any": [{"author": "me"}]}]
            cfg, _w = config_edit.save(f, {("lanes", "custom"): new,
                                           ("lanes", "enabled"): ["home", "posts"]})
            self.assertEqual(cfg["lanes"]["enabled"], ["home", "posts"])
            self.assertEqual(tomllib.loads(f.read_text("utf-8"))["lanes"]["custom"], new)


if __name__ == "__main__":
    unittest.main()
