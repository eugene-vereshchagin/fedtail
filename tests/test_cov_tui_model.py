"""The terminal's text side (frontends/tui/model.py) beyond tests/test_tui_model.py: a
card's words from the lane (who boosted, edited, the folded warning, the quote,
reactions, "you replied", the conversation), a boost or a direct post without them, a
poll, the activity rows of every kind, a request's note, lanes without groups. No
Textual needed."""

import types
from datetime import UTC, datetime
from unittest import mock

from fedtail import i18n
from fedtail.core.view import View
from fedtail.frontends.common.cardtext import Bit, CardWords
from fedtail.frontends.tui import model
from fedtail.protocols.mastodon.adapter import account, activity
from fedtail.protocols.mastodon.adapter import post as to_post

from . import test_cli
from .fakes import BOB, ME, NEWS, status
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
        title, _n = model.lane_label(self.view, "replies", width=4)
        self.assertTrue(title.endswith("…"))

        class Old:
            lane_by_name = {}

            def lane_title(self, _n):
                return "Activity"

            def activity_unread(self):
                raise AttributeError("not in this core")

            def follow_requests(self):
                return None
        self.assertEqual(model.lane_label(Old(), "activity"), ("Activity", 0))
        self.assertEqual(model.lane_label(Old(), "requests")[1], 0)

    def test_activity_rows_of_every_kind(self):
        def act(kind, **kw):
            base = {"id": "a", "type": kind, "account": BOB,
                    "created_at": "2099-10-14T11:00:00.000Z"}
            base.update(kw)
            return activity(base)
        r = act("pleroma:emoji_reaction", emoji="🔥",
                status=status("001", ME, minute=1, text="mine"))
        if r.kind == "reaction":
            self.assertIn("🔥", dict(model.show_activity(r).head)["boost"])
        a = act("follow")
        notice = a.__class__(**{**{f: getattr(a, f) for f in a.__dataclass_fields__},
                                "kind": "notice", "notice": "The server says hi"})
        self.assertEqual(dict(model.show_activity(notice).head)["boost"], "The server says hi")
        bare = a.__class__(**{**{f: getattr(a, f) for f in a.__dataclass_fields__},
                              "kind": "notice", "notice": ""})
        self.assertEqual(dict(model.show_activity(bare).head)["boost"], i18n._("act_other"))
        emoji = a.__class__(**{**{f: getattr(a, f) for f in a.__dataclass_fields__},
                               "kind": "reaction", "emoji": "🎉"})
        self.assertEqual(dict(model.show_activity(emoji).head)["boost"],
                         "🎉 " + i18n._("act_reaction"))
        odd = a.__class__(**{**{f: getattr(a, f) for f in a.__dataclass_fields__},
                             "kind": "something_new"})
        self.assertEqual(dict(model.show_activity(odd).head)["boost"], i18n._("act_other"))
        many = a.__class__(**{**{f: getattr(a, f) for f in a.__dataclass_fields__},
                              "count": 300})
        self.assertIn(("time", i18n._("act_more", n=299)), model.show_activity(many).head)
        named = model.show_activity(act("follow", account=dict(BOB, display_name="Bob B")))
        self.assertIn(("name", "Bob B"), named.head)
        nobody = a.__class__(**{**{f: getattr(a, f) for f in a.__dataclass_fields__},
                                "who": None})
        self.assertNotIn("who", dict(model.show_activity(nobody).head))

    def test_a_request_with_a_note(self):
        acc = account(dict(BOB, display_name="Bob B", note="<p>" + "word " * 60 + "</p>"))
        shown = model.show_request(acc, width=30)
        self.assertIn(("name", "Bob B"), shown.head)
        self.assertEqual(len(shown.body), 3)  # three lines at most

    def test_lanes_without_groups(self):
        self.view.cfg["ui"]["sidebar_groups"] = False
        got = model.ordered_lanes(self.view)
        self.assertEqual(len(got), 1)
        self.assertIsNone(got[0][0])
        self.assertIn("home", got[0][1])
        self.view.cfg["ui"]["sidebar_groups"] = True
        self.assertTrue(all(title for title, _n in model.ordered_lanes(self.view)))

    def test_start_lane(self):
        self.assertIsNone(model.start_lane(self.view, []))
        self.assertEqual(model.start_lane(self.view, ["local", "home"]), "home")
        self.assertEqual(model.start_lane(self.view, ["local"]), "local")
        self.view.set_state("lane", "local")
        self.assertEqual(model.start_lane(self.view, ["home", "local"]), "local")
