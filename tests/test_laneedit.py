"""The lane editor (common/laneedit.py) and its place (common/lanesplace.py): the lanes
of config.toml changed — order, shown, a lane's form — written back and taken at once."""

import tomllib
import unittest

from fedtail import i18n
from fedtail.frontends.common import laneedit
from fedtail.frontends.common.places import Places

from .test_custom import FreeBase


class LineTest(unittest.TestCase):
    def test_round_trip(self):
        for cond in ({"author": "me"}, {"author": ["me", "followed"], "kind": "post"},
                     {"text": [["грузия", "тбилиси"], ["georgia"]], "text_case": True},
                     {"likes": ">10", "age": "<1d"}):
            self.assertEqual(laneedit.parse_line(laneedit.cond_line(cond)), cond)
        self.assertEqual(laneedit.cond_line({"author": "me", "switch": "mine", "shown": False}),
                         "author: me")

    def test_mistakes_said(self):
        i18n.setup("en")
        with self.assertRaises(ValueError):
            laneedit.parse_line("author me")
        with self.assertRaises(ValueError):
            laneedit.parse_line("colour: red")
        with self.assertRaises(ValueError):
            laneedit.parse_line("author:")
        self.assertEqual(laneedit.parse_line(""), {})


class EditorTest(unittest.TestCase):
    TEXT = '[lanes]\npreset = "fedtail"\n'

    def test_order_and_shown(self):
        ed = laneedit.Editor(self.TEXT)
        first = [n for n in ed.order if n in ed.shown][:3]
        self.assertEqual(first, ["federated", "home", "local"])
        ed.move("home", -1)
        self.assertEqual([n for n in ed.order if n in ed.shown][:2], ["home", "federated"])
        ed.toggle("local", False)
        ch = ed.changes()
        self.assertNotIn("local", ch[("lanes", "enabled")])
        self.assertEqual(ch[("lanes", "enabled")][:2], ["home", "federated"])
        self.assertEqual(ch[("lanes", "custom")], [])

    def test_untouched_stays_unset(self):
        ch = laneedit.Editor(self.TEXT).changes()
        self.assertIs(ch[("lanes", "enabled")], laneedit.config_edit.UNSET)

    def test_set_lane_changed_and_back(self):
        ed = laneedit.Editor(self.TEXT)
        t = dict(ed.tables["bots"], icon="star_full")
        ed.put("bots", t)
        self.assertTrue(ed.changed("bots"))
        self.assertEqual(ed.changes()[("lanes", "custom")][0]["icon"], "star_full")
        ed.reset("bots")
        self.assertFalse(ed.changed("bots"))
        self.assertEqual(ed.changes()[("lanes", "custom")], [])

    def test_every_set_lane_reads_back_as_it_was(self):
        """A form saved untouched changes no lane of any set (the lines, `*`, switches)."""
        from fedtail.core import presets
        from fedtail.frontends.common import lanesplace
        for preset in presets.names():
            ed = laneedit.Editor(f'[lanes]\npreset = "{preset}"\n')
            for n in ed.order:
                t = ed.tables.get(n)
                if not t or ed.kind(n) != "rule":
                    continue
                vals = {"title": ed.title(n),
                        "icon": t.get("icon", ""), "group": t.get("group", "personal"),
                        "source": lanesplace._words(t.get("source")),
                        "read": t.get("read", "through"), "sort": t.get("sort", "arrival")}
                for part in ("any", "none"):
                    for i, c in enumerate(t.get(part) or []):
                        vals[f"{part}.{i}"] = laneedit.cond_line(c)
                        if part == "any":
                            vals[f"{part}.{i}.switch"] = c.get("switch", "")
                            vals[f"{part}.{i}.hidden"] = c.get("shown") is False
                with self.subTest(preset=preset, lane=n):
                    self.assertEqual(lanesplace._table_of(n, t, vals), t)

    def test_new_and_delete(self):
        i18n.setup("en")
        ed = laneedit.Editor(self.TEXT)
        ed.new("pics")
        self.assertIn("pics", ed.shown)
        with self.assertRaises(ValueError):
            ed.new("pics")
        with self.assertRaises(ValueError):
            ed.new("два слова")
        ed.delete("pics")
        self.assertNotIn("pics", ed.tables)
        ed.delete("bots")  # a set's lane: only hidden
        self.assertIn("bots", ed.tables)
        self.assertNotIn("bots", ed.shown)


class PlaceTest(FreeBase):
    def setUp(self):
        super().setUp()
        i18n.setup("en")
        self.core, _w = self.make([])
        self.core.paths.config_file.write_text('[lanes]\npreset = "fedtail"\n', "utf-8")
        from fedtail.core.view import View
        self.places = Places(View(self.core))

    def file(self):
        return tomllib.loads(self.core.paths.config_file.read_text("utf-8"))

    def test_list_and_moves(self):
        page = self.places.page("lanes")
        keys = [r.key for r in page.rows if r.key]
        self.assertEqual(keys[:4], ["set:fedtail", "set:mastodon", "set:tusky", "set:phanpy"])
        i = keys.index("_new")
        self.assertEqual(keys[i:i + 3], ["_new", "federated", "home"])
        out = self.places.act("lanes", "up", "home")
        self.assertFalse(out.error, out.error)
        self.assertEqual(self.file()["lanes"]["enabled"][:2], ["home", "federated"])
        self.assertEqual([x.name for x in self.core.lanes][:2], ["home", "federated"])
        self.places.act("lanes", "toggle", "bots")
        self.assertNotIn("bots", self.core.lane_by_name)

    def test_new_lane_through_the_form(self):
        out = self.places.act("lanes", "new", answer="pics")
        self.assertEqual(out.open, {"page": "lane", "arg": "pics"})
        page = self.places.page("lane", "pics")
        names = [f.name for f in page.form]
        self.assertIn("any.0", names)
        self.assertIn("any.new", names)
        values = {f.name: f.value for f in page.form}
        values.update({"title": "Pictures", "icon": "list", "any.0": "has: image, video",
                       "any.0.switch": "pics", "any.new": "author: me; kind: post",
                       "none.new": "author: bot"})
        out = self.places.act("lane", "save", "pics", values)
        self.assertFalse(out.error, out.error)
        lane = next(t for t in self.file()["lanes"]["custom"] if t["name"] == "pics")
        self.assertEqual(lane["title"], "Pictures")
        self.assertEqual(lane["any"][0], {"has": ["image", "video"], "switch": "pics"})
        self.assertEqual(lane["any"][1], {"author": "me", "kind": "post"})
        self.assertEqual(lane["none"], [{"author": "bot"}])
        self.assertIn("pics", self.core.lane_by_name)
        self.assertEqual(self.core.lane_title("pics"), "Pictures")

    def test_bad_line_saves_nothing(self):
        before = self.core.paths.config_file.read_text("utf-8")
        values = {f.name: f.value for f in self.places.page("lane", "bots").form}
        values["any.new"] = "colour: red"
        out = self.places.act("lane", "save", "bots", values)
        self.assertTrue(out.error)
        values["any.new"] = "author: nobody_word"
        self.assertTrue(self.places.act("lane", "save", "bots", values).error)
        self.assertEqual(self.core.paths.config_file.read_text("utf-8"), before)

    def test_untouched_form_changes_nothing(self):
        values = {f.name: f.value for f in self.places.page("lane", "home").form}
        out = self.places.act("lane", "save", "home", values)
        self.assertEqual(out.message, i18n._("le_same"))
        self.assertNotIn("custom", self.file().get("lanes", {}))

    def test_another_set_and_back_to_it_as_is(self):
        self.places.act("lanes", "up", "home")
        out = self.places.act("lanes", "preset", "mastodon")
        self.assertTrue(out.confirm)
        out = self.places.act("lanes", "preset", "mastodon", confirmed=True)
        self.assertFalse(out.error, out.error)
        self.assertEqual(self.file()["lanes"]["preset"], "mastodon")
        self.assertNotIn("enabled", self.file()["lanes"])  # the set's own order
        self.assertIn("mentions", self.core.lane_by_name)
        self.places.act("lanes", "new", answer="pics")
        page = self.places.page("lanes")
        self.assertIn("_own", [r.key for r in page.rows])
        out = self.places.act("lanes", "clean", confirmed=True)
        self.assertFalse(out.error, out.error)
        self.assertNotIn("pics", self.core.lane_by_name)
        self.assertNotIn("_own", [r.key for r in self.places.page("lanes").rows])

    def test_media_funnel_kept_only_with_the_tick(self):
        from fedtail.core.view import View
        from fedtail.frontends.common.lane import LaneModel
        m = LaneModel(View(self.core), "home")
        m.media.toggle("text", False)
        m.build(False)
        self.assertIsNone(self.core.store.kv_get("ui.media.home"))  # this run only
        self.assertTrue(LaneModel(View(self.core), "home").media.active())  # …in it
        self.core.cfg["feed"]["remember_choices"] = True
        m.media.boosts = False
        m.build(False)
        self.assertEqual(self.core.store.kv_get("ui.media.home")["boosts"], False)

    def test_a_lane_that_never_fills_is_marked(self):
        from fedtail.core import config_edit
        config_edit.save(self.core.paths.config_file, {("lanes", "custom"): [
            {"name": "never", "any": [{"visibility": "followers", "author": "stranger"}]}]})
        row = next(r for r in self.places.page("lanes").rows if r.key == "never")
        self.assertIn("⚠", row.line)

    def test_in_the_menu(self):
        self.assertIn("lanes", [n for n, _w in self.places.menu()])

    def test_tag_lane_in_home_or_not(self):
        """A saved lane of tags: its posts in Home too, or not — a button of the place
        (and the windows' sidebar menu)."""
        self.core.save_tag_group({"any": ["linux"]}).result()
        lane = next(n for n in self.core.lane_by_name if n.startswith("tags:"))
        page = self.places.page("taglanes", "linux")
        row = next(r for r in page.rows if r.key == "lane:" + lane)
        self.assertEqual(row.buttons[0].act, ("taglane", "home", lane))
        self.assertFalse(self.places.act("taglane", "home", lane).error)
        self.assertTrue(next(g for g in self.core.tag_groups
                             if g.get("saved"))["not_in_home"])
        self.assertIn("linux", self.core._ctx().home_hidden_tags)
        self.places.act("taglane", "home", lane)
        self.assertFalse(next(g for g in self.core.tag_groups
                              if g.get("saved"))["not_in_home"])


if __name__ == "__main__":
    unittest.main()
