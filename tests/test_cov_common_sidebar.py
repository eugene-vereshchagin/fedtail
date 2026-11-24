"""The sidebar without a toolkit (frontends/common/sidebar.py): its sections, the count
beside each lane (the core's number for every lane, a lane of events too; a lane browsed
rather than counted), the icon's total, the badge's words and the folded groups kept in
the profile's state."""

import types
import unittest

from fedtail.core import lanes as lanes_mod
from fedtail.frontends.common import sidebar


def lane(name, lazy=False):
    return types.SimpleNamespace(name=name, lazy=lazy)


class View:
    def __init__(self):
        self.lanes = [lane("home"), lane("replies"), lane("local", lazy=True),
                      lane("requests"), lane("activity"), lane("list:7")]
        self.lane_by_name = {x.name: x for x in self.lanes}
        self.me = {"id": "ME"}
        self.state = {}

    def unread_count(self, name):
        if name == "replies":
            raise KeyError(name)  # a lane the core doesn't count
        return {"requests": 2, "activity": 5}.get(name, 3)  # events not seen: the core's

    def lane_chosen(self, name, chosen, except_, _mark=None):
        return name in chosen and name not in except_

    def get_state(self, key):
        return self.state.get(key)

    def set_state(self, key, value):
        self.state[key] = value


class SidebarTest(unittest.TestCase):
    def test_groups(self):
        v = View()
        plain = {"ui": {"sidebar_groups": False}, "lists": {"enabled": True}}
        self.assertEqual(sidebar.groups(v, plain),
                         [(None, ["home", "replies", "local", "requests", "activity"]),
                          ("lists", ["list:7"])])
        no_lists = {"ui": {"sidebar_groups": False}, "lists": {"enabled": False}}
        self.assertEqual([g for g, _n in sidebar.groups(v, no_lists)], [None])
        grouped = {"ui": {"sidebar_groups": True}, "lists": {"enabled": True}}
        self.assertEqual(sidebar.groups(v, grouped), lanes_mod.grouped(v.lanes))

    def test_counts_and_the_icon(self):
        v = View()
        got = sidebar.counts(v, ["home", "replies", "local", "requests", "activity"])
        self.assertEqual(got, {"home": 3, "replies": 0, "local": 0, "requests": 2,
                               "activity": 5})
        v.me = None
        self.assertEqual(sidebar.count(v, "home"), 0)  # not logged in yet
        cfg = {"ui": {"icon_count": ["home", "activity"], "icon_count_except": ["activity"]}}
        self.assertEqual(sidebar.icon_total(View(), cfg, got), 3)
        self.assertEqual(sidebar.badge_text(7), "7")
        self.assertEqual(sidebar.badge_text(1234), "999+")

    def test_folding_is_remembered(self):
        v = View()
        self.assertEqual(sidebar.folded(v), set())
        self.assertTrue(sidebar.fold(v, "lists"))
        self.assertEqual(v.state["folded_groups"], ["lists"])
        self.assertFalse(sidebar.fold(v, "lists"))  # again: open
        self.assertTrue(sidebar.fold(v, "tags", on=True))
        self.assertTrue(sidebar.fold(v, "tags", on=True))
        self.assertEqual(sidebar.folded(v), {"tags"})


if __name__ == "__main__":
    unittest.main()


class LaneTipTest(unittest.TestCase):
    """A lane row's tooltip, one for every window: Qt said "Alt+N" whatever
    ui.number_keys was, GTK named neither the key nor the config's word (23.11)."""

    def test_the_keys_follow_number_keys(self):
        tip = sidebar.lane_tip("home", 2, {"ui": {"number_keys": "ctrl"}})
        self.assertIn("(Ctrl+2)", tip)
        self.assertNotIn("Alt", tip)
        both = sidebar.lane_tip("home", 2, {"ui": {"number_keys": "both"}})
        self.assertIn("(Alt+2, Ctrl+2)", both)
        self.assertIn("(Alt+2)", sidebar.lane_tip("home", 2, {}))

    def test_no_key_past_nine_or_without_a_number(self):
        self.assertNotIn("+", sidebar.lane_tip("home", 10, {}))
        self.assertNotIn("+", sidebar.lane_tip("home"))

    def test_a_built_in_lane_says_its_config_word_a_list_does_not(self):
        self.assertIn("home", sidebar.lane_tip("home").splitlines()[-1])
        self.assertEqual(sidebar.lane_tip("list:7"), "")
        self.assertEqual(sidebar.lane_tip("list:7", 3, {}), "(Alt+3)")


class SectionsByRuleTest(unittest.TestCase):
    def test_a_lane_in_its_rules_section_once(self):
        """The section is the rule's `group`, never the lane's name: a lane called
        "home" put among the personal ones is there, and only there (it stood in both)."""
        from fedtail.core import lanes
        made = [lanes.Lane("home", "home", lanes._all, group="personal"),
                lanes.Lane("direct", "mentions", lanes._all, group="standard"),
                lanes.Lane("feed", "home", lanes._all, group="personal"),
                lanes.Lane("unsorted", "unsorted", lanes._all),
                lanes.Lane("list:7", "list:7", lanes._all)]
        got = dict(lanes.grouped(made))
        # a lane that names no section: the sets' own one (presets.toml [sections] own)
        self.assertEqual(got["personal"], ["home", "feed", "unsorted"])
        self.assertEqual(got["standard"], ["direct"])
        self.assertEqual(got["lists"], ["list:7"])
        self.assertNotIn("tags", got)
        every = [n for names in got.values() for n in names]
        self.assertEqual(len(every), len(set(every)))

    def test_sections_of_ones_own_in_ones_order(self):
        """A lane's `group` is any word: it makes a section called that (the docs said
        so, the code put such a lane into Personal — 24.11). The order: lanes.sections,
        then the sets' file's, then one's own by their first lane. No section is named
        in the code or in the interface's strings."""
        from fedtail import i18n
        from fedtail.core import lanes, presets
        made = [lanes.Lane("work", "home", lanes._all, group="Работа"),
                lanes.Lane("home", "home", lanes._all, group="standard"),
                lanes.Lane("mine", "mine", lanes._all, group="personal"),
                lanes.Lane("list:7", "list:7", lanes._all),
                lanes.Lane("more", "home", lanes._all, group="Работа"),
                lanes.Lane("tags:cats", "tags:cats", lanes._all)]
        self.assertEqual(lanes.grouped(made), [
            ("standard", ["home"]), ("personal", ["mine"]), ("lists", ["list:7"]),
            ("tags", ["tags:cats"]), ("Работа", ["work", "more"])])
        mine = lanes.grouped(made, ["tags", "Работа", "nothing-here", "personal"])
        self.assertEqual([g for g, _n in mine],
                         ["tags", "Работа", "personal", "standard", "lists"])
        # only the sections that hold a lane — and the lists' always (a list is made there)
        self.assertEqual(lanes.grouped(made[:1]), [("lists", []), ("Работа", ["work"])])
        v = types.SimpleNamespace(lanes=made)
        cfg = {"ui": {"sidebar_groups": True}, "lists": {"enabled": True},
               "lanes": {"sections": ["Работа"]}}
        self.assertEqual(sidebar.groups(v, cfg)[0], ("Работа", ["work", "more"]))
        i18n.setup("en")
        self.assertEqual(sidebar.group_title("standard"), "Timelines")
        self.assertEqual(sidebar.group_title("lists"), "Lists")
        self.assertEqual(sidebar.group_title("Работа"), "Работа")  # as its lanes say
        self.assertEqual(sidebar.group_title("people"), i18n._("grp_people"))  # a roster's
        self.assertIsNone(sidebar.group_title(None))
        self.assertEqual(presets.sections(), ["standard", "personal", "lists", "tags"])
        self.assertEqual(presets.own_section(), "personal")
        for word in ("grp_standard", "grp_personal", "grp_tags"):
            self.assertNotIn(word, i18n.strings("en"))
        self.assertNotIn("sections", presets.names())
        # the lane editor: a section there is, or a new one by its name
        from fedtail.frontends.common import lanesplace
        old = {"name": "x", "any": [{}]}
        table = lambda **v: lanesplace._table_of("x", old, v)  # noqa: E731
        self.assertNotIn("group", table(group="personal"))  # the own one: nothing to say
        self.assertEqual(table(group="standard")["group"], "standard")
        self.assertEqual(table(group="personal", group_new=" Работа ")["group"], "Работа")
        ed = types.SimpleNamespace(tables={"a": {"group": "Чтение"}, "b": {}})
        self.assertEqual(lanesplace._sections(ed, cfg, "Игры"),
                         ["Работа", "standard", "personal", "Чтение", "Игры"])
