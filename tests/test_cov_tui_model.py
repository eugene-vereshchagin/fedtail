"""The terminal's text side (frontends/tui/model.py) beyond tests/test_tui_model.py: a
card's words from the lane (who boosted, edited, the folded warning, the quote,
reactions, "you replied", the conversation), a boost or a direct post without them, a
poll, an event's row of every shape, lanes without groups. No
Textual needed."""

import types
from datetime import UTC, datetime
from unittest import mock

from fedtail import i18n
from fedtail.core.view import View
from fedtail.frontends.common import sidebar
from fedtail.frontends.common.cardtext import Bit, CardWords
from fedtail.frontends.tui import model
from fedtail.protocols.mastodon.adapter import post as to_post

from . import test_cli
from .fakes import BOB, NEWS, status
from .test_core import TmpDir


def with_media(st):
    st["media_attachments"] = [{"type": "image", "url": "https://x/a.png"}]
    return st


class TuiModelCornersTest(TmpDir):
    make = test_cli.CliTest.make

    def setUp(self):
        super().setUp()
        i18n.setup("en")
        core, _w = self.make()
        self.view = View(core)

    def test_when(self):
        self.assertEqual(model.when(None), "")
        self.assertRegex(model.when(datetime(2020, 1, 2, tzinfo=UTC)),
                         r"^\d\d\.\d\d \d\d:\d\d$")

    def test_card_words_from_the_lane(self):
        st = to_post(status("002", BOB, "001", "ME", minute=2, text="text<br><br>"))
        words = CardWords(boosted=Bit("♻ Bob boosted"), meta=[Bit("edited", kind="edited"),
                                                             Bit("14:00", kind="time")],
                          warning="Folded by filter «x»", folded=True,
                          quote=Bit("❝ a quote"), reactions="👍 3",
                          my_replies=[Bit("↳ you replied")],
                          conversation=Bit("💬 3 in the conversation"))
        spec = types.SimpleNamespace(entry=st)
        with mock.patch("fedtail.frontends.common.cardtext.card_words", return_value=words):
            shown = model.show_post(self.view, st, spec=spec)
        self.assertEqual(shown.above, [("boost", "♻ Bob boosted")])
        self.assertIn(("muted", "edited"), shown.head)
        self.assertNotIn(("muted", "14:00"), shown.head)  # only edited / old there
        self.assertEqual(shown.cw, "Folded by filter «x»")
        self.assertEqual(shown.body, [])  # folded by a filter: closed, whatever expand_cw
        self.assertEqual(shown.below, [("quote", "❝ a quote"), ("muted", "👍 3"),
                                       ("myreply", "↳ you replied"),
                                       ("conv", "💬 3 in the conversation")])
        self.assertEqual(shown.context, "↳ …")  # a reply whose parent isn't at hand

    def test_boost_direct_followers_poll_and_trailing_blank_lines(self):
        inner = status("001", BOB, minute=1, vis="direct", text="hi<br><br>")
        inner["poll"] = {"id": "P", "options": [{"title": "a", "votes_count": 0}],
                         "multiple": False, "expired": False, "votes_count": 0}
        boost = status("002", NEWS, minute=2, text="")
        boost["reblog"] = inner
        shown = model.show_post(self.view, to_post(boost))
        self.assertIn(("boost", "♻ @georgia_news"), shown.head)
        self.assertIn(("direct", "✉"), shown.head)
        self.assertEqual(shown.body, ["hi"])  # the blank lines at the end dropped
        self.assertIn("📊", shown.foot)
        locked = model.show_post(self.view, to_post(status("003", BOB, vis="private")))
        self.assertIn(("muted", "🔒"), locked.head)
        nobody = dict(status("004", NEWS), account=dict(NEWS, acct="", username=""))
        nobody_boost = dict(status("005", nobody["account"]), reblog=status("006", BOB))
        self.assertIn(("boost", "♻ @?"), model.show_post(self.view,
                                                         to_post(nobody_boost)).head)

    def test_a_post_without_words_has_no_body(self):
        pic = with_media(status("007", BOB, minute=7, text=""))
        self.assertEqual(model.show_post(self.view, to_post(pic)).body, [])

    def test_lane_label_truncates_and_survives_an_old_core(self):
        title, _n = sidebar.lane_label(self.view, "replies", width=4)
        self.assertTrue(title.endswith("…"))

        class Old:  # a core that can't count: no number, nothing breaks
            lane_by_name = {}
            me = object()

            def lane_title(self, _n):
                return "Activity"

            def unread_count(self, _n):
                raise AttributeError("not in this core")
        self.assertEqual(sidebar.lane_label(Old(), "activity"), ("Activity", 0))

    def test_event_lines_of_every_shape(self):
        """A server's notice says itself (no names); many people: "and N more"; no post,
        no time: no line for them."""
        from fedtail.frontends.common.activity import EventParts
        parts = EventParts(kind="severed_relationships", people=[], more="", what="lost",
                           when="", notice="The server says hi", post="", post_link="",
                           hide="fedtail:eventhide/n1", hide_tip="", answers=[], tip="",
                           unread=False)
        lines = model.event_lines(parts)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0][0], ("notice", "⚠ The server says hi", None))
        self.assertNotIn("unread", [k for k, _t, _l in lines[0]])
        many = EventParts(kind="favourite", people=[("A", "fedtail:account/1"),
                                                    ("B", "fedtail:account/2")],
                          more="and 5 more", what="liked", when="11:00", notice="",
                          post="«x»", post_link="fedtail:thread/9",
                          hide="fedtail:eventhide/1,2", hide_tip="", answers=[], tip="",
                          unread=True)
        top = model.event_lines(many)[0]
        self.assertEqual([t for k, t, _l in top if k == "who"], ["A", "B"])
        self.assertIn(("muted", ", ", None), top)
        self.assertIn(("name", " and 5 more", None), top)
        self.assertIn(("muted", " — liked · 11:00", None), top)

    def test_lanes_without_groups(self):
        """The terminal's sections are the windows' (common/sidebar.groups): plain, the
        lanes and then the lists; with groups, each section titled."""
        self.view.cfg["ui"]["sidebar_groups"] = False
        got = sidebar.groups(self.view, self.view.cfg)
        self.assertIsNone(got[0][0])
        self.assertIn("home", got[0][1])
        self.assertIsNone(sidebar.group_title(got[0][0]))
        self.view.cfg["ui"]["sidebar_groups"] = True
        self.assertTrue(all(sidebar.group_title(g) for g, _n in
                            sidebar.groups(self.view, self.view.cfg)))

    def test_start_lane(self):
        """ui.start_lane, one rule for every interface: none — closed (or, where every
        lane can't be closed, the last); last; a lane by name; a lane not there — the
        set's own start lane (its rule's `start`), not one by its name."""
        cfg = self.view.cfg["ui"]
        cfg["start_lane"] = "none"
        self.assertIsNone(sidebar.start_lane(self.view, ["local", "home"]))  # none
        self.assertIsNone(sidebar.start_lane(self.view, [], closable=False))
        first = next(x.name for x in self.view.lanes if x.start)  # the set's: Home
        self.assertEqual(first, "home")
        self.assertEqual(sidebar.start_lane(self.view, ["local", first], closable=False),
                         first)
        self.assertEqual(sidebar.start_lane(self.view, ["local"], closable=False), "local")
        self.view.set_state("lane", "local")
        self.assertEqual(sidebar.start_lane(self.view, [first, "local"], closable=False),
                         "local")
        cfg["start_lane"] = "last"
        self.assertEqual(sidebar.start_lane(self.view, [first, "local"]), "local")
        cfg["start_lane"] = first
        self.assertEqual(sidebar.start_lane(self.view, [first, "local"]), first)
        cfg["start_lane"] = "none"
