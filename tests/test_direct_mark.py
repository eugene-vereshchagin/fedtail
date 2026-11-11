"""A private message among posts stands out, as in Fedilab (ui.direct_highlight, the
theme's [shape] direct; common/cardtext.direct_mark): a frame, a fill, a plate or nothing —
and nothing in a lane that holds private messages only (Core.only_private), where every
card would carry it."""

import unittest

from fedtail import i18n
from fedtail.frontends.common import lane
from fedtail.frontends.common.cardtext import direct_mark

from . import test_cli
from .test_core import TmpDir
from .test_cov_common_lane import View, post


def cfg(want="theme"):
    return {"ui": {"direct_highlight": want}}


class DirectMarkTest(unittest.TestCase):
    def test_the_option_the_theme_and_the_terminal(self):
        dm, public = post("1", visibility="direct"), post("2", visibility="public")
        self.assertEqual(direct_mark(cfg(), {"direct": "frame"}, dm), "frame")
        self.assertEqual(direct_mark(cfg(), {"direct": "badge"}, dm), "badge")  # bnw
        self.assertEqual(direct_mark(cfg(), {}, dm), "frame")  # a theme without the key
        self.assertEqual(direct_mark(cfg(), None, dm), "badge")  # no themes: the terminal
        self.assertEqual(direct_mark(cfg("fill"), {"direct": "badge"}, dm), "fill")
        self.assertEqual(direct_mark(cfg("none"), {"direct": "frame"}, dm), "none")
        self.assertEqual(direct_mark(cfg("frame"), None, public), "none")
        self.assertEqual(direct_mark(cfg("odd"), None, dm), "frame")
        self.assertEqual(direct_mark(cfg("fill"), None, dm, lane_private=True), "none")


class OnlyPrivateThreadTest(unittest.TestCase):
    """A thread of private messages only: none marked out, as in such a lane (11.11: the
    frame on every card of a private talk)."""

    def test_the_rule(self):
        from fedtail.model import ThreadItem, only_private
        dm, dm2, public = (post("1", visibility="direct"), post("2", visibility="direct"),
                           post("3", visibility="public"))
        self.assertTrue(only_private([ThreadItem(dm, 0, 0), ThreadItem(dm2, 1, 1)]))
        self.assertFalse(only_private([ThreadItem(public, 0, 0), ThreadItem(dm, 1, 1)]))
        self.assertTrue(only_private([dm]))
        self.assertFalse(only_private([]))


class OnlyPrivateTest(TmpDir):
    """"Private messages" takes nothing else: no frame there; "To me" takes replies and
    mentions too: a private one among them is marked."""
    make = test_cli.CliTest.make

    def test_by_the_rule(self):
        core, _w = self.make()
        self.assertTrue(core.only_private("direct"))
        self.assertFalse(core.only_private("to_me"))
        self.assertFalse(core.only_private("home"))
        self.assertFalse(core.only_private("no such lane"))
        self.assertEqual(core.only_private_lanes(), ["direct"])


class LaneSpecTest(unittest.TestCase):
    """The lane's cards say it (CardSpec.extra["lane_private"]), every interface reads it."""

    def setUp(self):
        i18n.setup("en")

    def built(self, private):
        v = View([("i1", post("1", visibility="direct"))], name="direct")
        if private:
            v.only_private = lambda name: name == "direct"
        return lane.LaneModel(v, "direct").build(positioned=False).specs

    def test_marked_only_where_not_all_are(self):
        self.assertTrue(self.built(True)[0].extra.get("lane_private"))
        self.assertFalse(self.built(False)[0].extra.get("lane_private", False))


if __name__ == "__main__":
    unittest.main()
