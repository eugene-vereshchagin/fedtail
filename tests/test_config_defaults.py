"""A default changed since a profile's config was written (core/config_defaults.py): the
option still at the old default takes the new one at a start, once — one the person sets
back afterwards stays."""

import json

from fedtail.core import config, config_defaults, config_edit

from .test_core import TmpDir


class BroughtDefaultsTest(TmpDir):
    def setUp(self):
        super().setUp()
        self.path = self.tmp / "config.toml"
        self.path.write_text(config.example_text("en"), "utf-8")
        # written before 0.23.3: Drafts off, the tag click on the author (0.22.4)
        config_edit.save(self.path, {("post", "drafts_place"): False,
                                     ("feed", "tag_click"): "author",
                                     ("ui", "command_line"): False})  # chosen already

    def test_an_old_default_takes_the_new_one_once(self):
        """18.11: the author's config kept Drafts off after 0.23.3 turned them on."""
        cfg, _w = config.load(self.path)
        self.assertTrue(cfg["post"]["drafts_place"])
        self.assertEqual(cfg["feed"]["tag_click"], "menu")
        self.assertFalse(cfg["ui"]["command_line"])  # the new default already: as it was
        text = self.path.read_text("utf-8")
        self.assertIn("drafts_place = true", text)  # in the file, one line each
        self.assertTrue((self.tmp / "config.toml.bak").exists())
        seen = json.loads((self.tmp / config_defaults.SEEN).read_text("utf-8"))
        self.assertEqual(len(seen), len(config_defaults.CHANGED))
        # set back by the person: stays so, the change was looked at already
        config_edit.save(self.path, {("post", "drafts_place"): False})
        cfg, _w = config.load(self.path)
        self.assertFalse(cfg["post"]["drafts_place"])

    def test_a_value_the_person_chose_stays(self):
        config_edit.save(self.path, {("feed", "tag_click"): "everywhere"})
        cfg, _w = config.load(self.path)
        self.assertEqual(cfg["feed"]["tag_click"], "everywhere")

    def test_a_new_config_is_left_as_it_is(self):
        self.path.write_text(config.example_text("ru"), "utf-8")
        before = self.path.read_text("utf-8")
        config.load(self.path)
        self.assertEqual(self.path.read_text("utf-8"), before)
        self.assertTrue((self.tmp / config_defaults.SEEN).exists())

    def test_every_change_is_a_real_option_with_a_new_default(self):
        for section, key, old, since in config_defaults.CHANGED:
            self.assertIn(key, config.DEFAULTS[section], f"{section}.{key}")
            self.assertNotIn(config.DEFAULTS[section][key], old, f"{section}.{key}")
            self.assertRegex(since, r"^\d+\.\d+\.\d+$")
