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

    def lane_chosen(self, name, chosen, except_):
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
        self.assertEqual(got["personal"], ["home", "feed"])
        self.assertEqual(got["standard"], ["direct", "unsorted"])
        self.assertEqual(got["lists"], ["list:7"])
        self.assertNotIn("tags", got)
        every = [n for names in got.values() for n in names]
        self.assertEqual(len(every), len(set(every)))
