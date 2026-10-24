"""The settings window's ground (core/config_edit.py, frontends/common/settings.py, the
"settings" place): config.toml stays the one place the settings live, and a change
touches that one line and nothing else."""

import tempfile
import tomllib
import unittest
from pathlib import Path
from types import SimpleNamespace

from fedtail import i18n
from fedtail.core import config
from fedtail.core import config_edit as ce
from fedtail.frontends.common import settings
from fedtail.frontends.common.places import Places

USER = """# my own notes up here
[ui]
# the theme I like
theme = "nord"   # nord, really
columns = [
    "home",
    "local",  # two of them
]
#font_size = 0

[feed]
order = "oldest_first"
"""


def changed_lines(a, b):
    import difflib
    return [x for x in difflib.unified_diff(a.splitlines(), b.splitlines(), n=0, lineterm="")
            if x[:1] in "+-" and not x.startswith(("+++", "---"))]


class EditTest(unittest.TestCase):
    def setUp(self):
        self.ex = config.example_text("en")

    def test_a_set_line_changes_and_nothing_else(self):
        out = ce.set_value(USER, "ui", "theme", "paper")
        self.assertEqual(changed_lines(USER, out), ['-theme = "nord"   # nord, really',
                                                    '+theme = "paper"'])

    def test_a_list_over_several_lines_becomes_one(self):
        out = ce.set_value(USER, "ui", "columns", ["home"])
        self.assertEqual(tomllib.loads(out)["ui"]["columns"], ["home"])
        self.assertNotIn("two of them", out)
        self.assertIn("[feed]", out)
        self.assertEqual(tomllib.loads(out)["feed"]["order"], "oldest_first")

    def test_commented_out_is_switched_on_in_place(self):
        out = ce.set_value(USER, "ui", "font_size", 12)
        self.assertEqual(changed_lines(USER, out), ["-#font_size = 0", "+font_size = 12"])

    def test_not_mentioned_goes_into_its_section_with_the_explanation(self):
        out = ce.set_value(USER, "ui", "esc", "tray", self.ex)
        data = tomllib.loads(out)
        self.assertEqual(data["ui"]["esc"], "tray")
        ui_part = out.split("[feed]")[0]
        self.assertIn('esc = "tray"', ui_part)
        self.assertIn('"curtain"', ui_part)  # what the choices mean came along

    def test_a_section_the_file_lacks_is_added(self):
        out = ce.set_value(USER, "sound", "enabled", "off", self.ex)
        self.assertEqual(tomllib.loads(out)["sound"]["enabled"], "off")
        self.assertTrue(out.rstrip().endswith('enabled = "off"'))

    def test_unset_comments_the_line_out(self):
        out = ce.unset(USER, "ui", "theme", "system")
        self.assertNotIn("theme", tomllib.loads(out)["ui"])
        self.assertIn('#theme = "system"', out)
        self.assertIn("# the theme I like", out)
        self.assertEqual(ce.unset(out, "ui", "theme"), out)  # once is enough

    def test_strings_are_written_so_they_read_back(self):
        for s in ('a "quoted" one', "back\\slash", "кириллица", "tab\there", ""):
            out = ce.set_value(USER, "ui", "font", s)
            self.assertEqual(tomllib.loads(out)["ui"]["font"], s)

    def test_the_reference_takes_every_default_back(self):
        """Every option of the reference set to its own default: the file reads the same,
        and the result passes validate."""
        text = self.ex
        for section, values in config.DEFAULTS.items():
            for key, value in values.items():
                if ce.is_set(text, section, key):
                    text = ce.set_value(text, section, key, value, self.ex)
        self.assertEqual(tomllib.loads(text), tomllib.loads(self.ex))
        config.validate(tomllib.loads(text))

    def test_save_keeps_a_copy_and_refuses_what_wouldnt_read(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "config.toml"
            f.write_text(USER, "utf-8")
            ce.save(f, {("ui", "theme"): "paper"}, self.ex)
            self.assertEqual(Path(str(f) + ".bak").read_text("utf-8"), USER)
            self.assertEqual(tomllib.loads(f.read_text("utf-8"))["ui"]["theme"], "paper")
            before = f.read_text("utf-8")
            with self.assertRaises(ce.SaveError):
                ce.save(f, {("ui", "font_size"): "big"}, self.ex)  # must be a number
            self.assertEqual(f.read_text("utf-8"), before)
            self.assertFalse(Path(str(f) + ".tmp").exists())


def _view(path):
    return SimpleNamespace(paths=SimpleNamespace(config_file=path),
                           supports=lambda _x: True, lane_title=lambda _n: None)


class ModelTest(unittest.TestCase):
    def test_every_option_is_in_the_window_in_both_languages(self):
        want = {f"{s}.{k}" for s, v in config.DEFAULTS.items() for k in v}
        for lang in config.EXAMPLE_LANGS:
            with self.subTest(lang=lang):
                chapters = settings.model(_view(Path("/nowhere")), lang=lang, text="")
                have = {o.name for c in chapters for o in c.options}
                missing = want - have
                # those the reference leaves out on purpose are the ones it doesn't list
                listed = {f"{s}.{k}" for s, opts in __import__(
                    "fedtail.core.config_update", fromlist=["x"]).parse_example(
                    config.example_text(lang)).items() for k, _b in opts}
                self.assertEqual(missing & listed, set())
                for c in chapters:
                    self.assertTrue(c.title)
                    for o in c.options:
                        self.assertTrue(o.title, o.name)
                        self.assertLessEqual(len(o.title), 64, o.name)
                        if o.kind == "choice":
                            known = config.CHOICES.get((o.section, o.key), set())
                            self.assertLessEqual(known, {v for v, _w in o.choices}, o.name)
                            self.assertIn(o.value, [v for v, _w in o.choices], o.name)

    def test_values_come_from_the_file(self):
        chapters = settings.model(_view(Path("/nowhere")), lang="en", text=USER)
        theme = settings.option(chapters, "ui.theme")
        self.assertEqual(theme.value, "nord")
        self.assertTrue(theme.changed)
        size = settings.option(chapters, "ui.font_size")
        self.assertFalse(size.in_file)
        self.assertEqual(settings.option(chapters, "ui.columns").value, ["home", "local"])
        self.assertTrue(settings.find(chapters, "font"))
        self.assertEqual(settings.find(chapters, "no such thing at all"), [])

    def test_typed_values(self):
        chapters = settings.model(_view(Path("/nowhere")), lang="en", text="")
        poll = settings.option(chapters, "poll.interval_seconds")
        self.assertEqual(poll.parse(" 60 "), 60)
        with self.assertRaises(ValueError):
            poll.parse("10")  # under the minimum
        with self.assertRaises(ValueError):
            poll.parse("often")
        langs = settings.option(chapters, "post.languages")
        self.assertEqual(langs.parse("ru, en"), ["ru", "en"])


class PlaceTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.file = Path(self._tmp.name) / "config.toml"
        self.file.write_text(USER, "utf-8")
        self.pl = Places(_view(self.file))

    def test_save_writes_only_what_changed(self):
        page = self.pl.page("settings")
        self.assertEqual(page.tab, "ui")
        values = {f.name: f.value for f in page.form}
        values["ui.font_size"] = "13"
        out = self.pl.act("settings", "save", "", values)
        self.assertEqual(out.error, "")
        self.assertIn("ui.font_size", out.message)
        text = self.file.read_text("utf-8")
        self.assertEqual(changed_lines(USER, text), ["-#font_size = 0", "+font_size = 13"])

    def test_reset_and_a_bad_number(self):
        page = self.pl.page("settings")
        self.assertIn("ui.theme", [r.key for r in page.rows])  # set to other than default
        out = self.pl.act("settings", "reset", "ui.theme")
        self.assertEqual(out.error, "")
        self.assertNotIn("theme", tomllib.loads(self.file.read_text("utf-8"))["ui"])
        values = {f.name: f.value for f in self.pl.page("settings").form}
        values["ui.font_size"] = "-5"
        out = self.pl.act("settings", "save", "", values)
        self.assertTrue(out.error)

    def test_search_and_chapters(self):
        page = self.pl.page("settings", "sound")
        self.assertTrue(page.form)
        self.assertTrue(all("sound" in (f.name + f.label + f.tip).lower() for f in page.form))
        for key, _words in page.tabs:
            self.assertTrue(self.pl.page("settings", "", key).form, key)

    def test_the_windows_extras(self):
        """Find…, Open the file, and "default: …" in the tips, as the settings windows."""
        tools = self.pl.page("settings").rows[0]
        self.assertEqual(tools.key, "_tools")
        self.assertEqual([b.act[1] for b in tools.buttons], ["find", "file"])
        out = self.pl.act("settings", "find", "")
        self.assertEqual(out.ask[1], i18n._("settings_search"))
        out = self.pl.act("settings", "find", "", answer=" sound ")
        self.assertEqual(out.open, {"page": "settings", "arg": "sound"})
        self.assertIn("🔍 sound", self.pl.page("settings", "sound").rows[0].title)
        self.assertEqual(self.pl.act("settings", "file").open, {"file": str(self.file)})
        tips = [f.tip for f in self.pl.page("settings").form]
        self.assertTrue(any(i18n._("settings_default", value="").rstrip() in t for t in tips))


if __name__ == "__main__":
    unittest.main()
