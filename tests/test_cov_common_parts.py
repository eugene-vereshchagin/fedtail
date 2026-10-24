"""More of frontends/common, the corners the windows' own tests don't reach: my server's
page and probe table, a post's buttons and ⋯ menu in their rarer states, the split
layout's input line and private talks, the roster's rows and groups, and the columns a
window starts with."""

import dataclasses
import types
import unittest
from datetime import datetime

from fedtail import i18n
from fedtail.frontends.common import actions, columns, roster, server, split
from fedtail.model import (
    Account,
    Counts,
    Feature,
    Mention,
    MyProfile,
    Policy,
    Probe,
    Quote,
    Ref,
    ServerInfo,
    Share,
)
from fedtail.protocols.mastodon.adapter import post as to_post

from .fakes import BOB, ME, status


def acc(i, handle):
    return Account(Ref("m", "", i), handle, handle.split("@")[0])


def post(i="1", author=BOB, **kw):
    return dataclasses.replace(to_post(status(i, author, vis="public")), **kw)


CFG = {"ui": {"bookmark_button": True, "arts_mode": False}, "read": {"read_button": True},
       "post": {"quote_action": True, "invite": True}}


class ServerTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_server_page(self):
        info = ServerInfo(title="", domain="x.test", description="plain <b>words</b>",
                          contact=acc("A", "admin@x.test"), email="a@x.test",
                          about="<p>long</p>", rules=(("be nice", ""), ("no spam", "really")),
                          privacy="<p>we keep nothing</p>")
        html = server.server_html(info, clean=lambda h: "[" + h + "]")
        self.assertIn("<h2>x.test</h2>", html)
        self.assertIn("[plain <b>words</b>]", html)  # HTML: made safe by the toolkit
        self.assertIn("@admin@x.test, a@x.test", html)
        self.assertIn("<small>really</small>", html)
        self.assertIn("[<p>we keep nothing</p>]", html)
        plain = server.server_html(ServerInfo(title="T", description="no tags"), str)
        self.assertIn("<p>no tags</p>", plain)

    def test_probe_rows(self):
        self.assertEqual(server.probe_rows(None, str), (i18n._("probe_never"), []))
        p = Probe(datetime(2026, 1, 1), "gotosocial", "0.20", (
            Feature("max_characters", "info", "5000"), Feature("translate", "yes", "known"),
            Feature("lists", "no", "404"), Feature("weird_thing", "odd")))
        note, rows = server.probe_rows(p, lambda d: d.strftime("%Y"))
        self.assertIn("2026", note)
        self.assertIn("gotosocial 0.20", note)
        self.assertTrue(rows[0][1].startswith("✗"))  # the worst first
        self.assertIn("(404)", rows[0][1])
        self.assertEqual(rows[-1][0], "weird_thing")  # no words for it: its key
        self.assertTrue(rows[-1][1].startswith("?"))
        known = next(r for r in rows if r[2])
        self.assertNotIn("known", known[1])
        self.assertIn("?", server.probe_rows(Probe(None), str)[0])
        md = server.probe_markdown("x.test", note, [(w, a) for w, a, _k in rows])
        self.assertTrue(md.startswith("x.test — "))

    def test_profile_changes(self):
        me = dataclasses.replace(acc("ME", "me"), name="Me", locked=False, bot=False,
                                 discoverable=None)
        prof = MyProfile(me, "bio", (("site", "x"),))
        self.assertEqual(server.profile_changes(prof, "Me", "bio", [("site", "x")], {}), {})
        got = server.profile_changes(prof, "New", "new bio", [(" a ", " b "), ("", "")],
                                     {"locked": True, "bot": False}, "/a.png", "/h.png")
        self.assertEqual(got, {"name": "New", "bio": "new bio", "fields": [("a", "b")],
                               "locked": True, "avatar": "/a.png", "header": "/h.png"})


class ActionsTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_pictures(self):
        self.assertEqual(actions.action_picture("fav", True), "star_full")
        self.assertEqual(actions.action_picture("fav"), "star")
        self.assertIsNone(actions.action_picture("nothing"))
        self.assertEqual(actions.vis_picture("followers"), "private")
        self.assertEqual(actions.vis_picture("direct"), "direct")

    def test_read_button(self):
        ctx = actions.Ctx(cfg=CFG, me_id="ME")
        got = [b.action for b in actions.buttons(post(), ctx, unread=True)]
        self.assertEqual(got[-1], "readone")

    def test_a_rare_menu(self):
        me = to_post(status("9", ME)).author
        mine_quoted = post("9", ME)
        p = post("1", BOB, policy=Policy(can_quote="manual"), lang="ka", text="<p>x</p>",
                 counts=Counts(likes=2), quote=Quote(post=mine_quoted))
        boost = Share(Ref("m", "", "b1"), acc("R", "relay@x.test"), p, None, "1")
        ctx = actions.Ctx(cfg=CFG, me_id=me.id, supports=lambda _w: True, lists=True,
                          act_as=lambda _e: [("work", "@w@y.test")], translate=True)
        items = actions.menu(boost, ctx)
        labels = [i.label for i in items]
        self.assertIn(i18n._("add_to_list_booster", acct="@relay@x.test"), labels)
        self.assertIn(i18n._("quote_ask"), labels)
        act = next(i for i in items if i.kind == "act_as")
        self.assertEqual([d[3] for d in act.data], ["fav", "boost", "reply"])
        self.assertIn(i18n._("translate"), labels)
        self.assertIn(i18n._("who_favourited_by_n", n=2), labels)
        self.assertIn(i18n._("revoke_quote"), labels)  # my post in their quote
        self.assertIn(i18n._("report"), labels)
        ctx2 = actions.Ctx(cfg=CFG, me_id=me.id, act_as=lambda _e: [])
        self.assertNotIn("act_as", [i.kind for i in actions.menu(
            dataclasses.replace(p, policy=Policy(can_quote="automatic")), ctx2)])
        self.assertIn(i18n._("quote"), [i.label for i in actions.menu(
            dataclasses.replace(p, policy=Policy(can_quote="automatic")), ctx2)])


class SplitTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_a_new_post(self):
        view = types.SimpleNamespace(me=None, reply_visibility=lambda _p: "public")
        s = split.reply_start(view, None)
        self.assertEqual((s.prefill, s.visibility, s.about), ("", "public", i18n._("dock_new")))

    def test_faces(self):
        self.assertEqual(split.faces_mode({"ui": {"faces": False}}, {"faces": "agent"}),
                         "none")
        self.assertEqual(split.faces_mode({"ui": {}}, {}), "qip")
        a, me = acc("A", "a@x"), acc("ME", "me")
        self.assertIsNone(split.face("none", a, me))
        self.assertIsNone(split.face("qip", me, me))  # my own post: nobody
        self.assertIs(split.face("qip", a, me), a)

    def test_talk_with_one_person(self):
        view = types.SimpleNamespace(me=to_post(status("0", ME)).author)
        bob = acc("B", "bob@social.example")
        to_bob = post("1", ME, mentions=(Mention(Ref("m", "", "B"), "bob@social.example"),))
        from_bob = post("2", BOB)
        three = post("3", BOB, mentions=(Mention(Ref("m", "", "C"), "cat@x"),))
        entries = [("1", to_bob), ("2", from_bob), ("3", three)]
        self.assertEqual([i for i, _e in split.talk_with(view, entries, bob.handle)],
                         ["1", "2"])
        nobody = types.SimpleNamespace(me=None)
        self.assertEqual(len(split.talk_with(nobody, [("2", from_bob)], bob.handle)), 1)


class RosterTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def item(self, **kw):
        base = dict(kind="lane", key="home", title="Home", last=None, who=None, unread=0,
                    total=0, ids=())
        base.update(kw)
        return types.SimpleNamespace(**base)

    def test_lines_with_faces(self):
        bob = dataclasses.replace(acc("B", "bob@x"), avatar_static="b.png")
        last = post("1", BOB, text="<p>hello there</p>")
        line, _tip, st = roster.lines(self.item(kind="person", who=bob, last=last), True)
        self.assertEqual(st, "@bob@x")
        self.assertIn("hello", line)
        self.assertEqual(roster.lines(self.item(), True), ("", "", ""))
        self.assertEqual(roster.lines(self.item(total=4), True)[2],
                         i18n._("roster_total", n=4))
        self.assertEqual(roster.face_url(self.item(who=bob)), "b.png")
        self.assertEqual(roster.face_url(self.item(last=last)), last.author.avatar_static)
        self.assertEqual(roster.face_url(self.item()), "")
        self.assertIn(i18n._("roster_unread", n=2), roster.tip(self.item(unread=2)))

    def test_read_ids_folded_and_groups(self):
        view = types.SimpleNamespace(entries=lambda key: [("i", types.SimpleNamespace(
            id="7"))], get_state=lambda k, d: ["lists"] if k == "roster_folded" else d)
        self.assertEqual(roster.read_ids(view, "home", None), ["7"])
        self.assertEqual(roster.read_ids(view, "x", self.item(kind="thread", ids=("1",))),
                         ["1"])
        self.assertEqual(roster.folded(view), {"lists"})
        g = types.SimpleNamespace(name="lists", items=[self.item(unread=1), self.item()])
        self.assertEqual(roster.group_counts(g), (i18n._("lists_header"), 1, 2))
        g = types.SimpleNamespace(name="standard", items=[])
        self.assertEqual(roster.group_counts(g)[0], i18n._("grp_standard"))
        self.assertIn("{lit}", roster.group_word({}, True))
        self.assertNotIn("{lit}", roster.group_word({}, False))
        self.assertEqual(roster.group_word({"roster_group": "X"}, True), "X")


class ColumnsTest(unittest.TestCase):
    def test_start_names(self):
        cfg = {"ui": {"columns": ["local", "nope"]}}
        known = ["home", "replies", "local", "list:7"]
        self.assertEqual(columns.start_names(cfg, ["list:Friends", "home", "home"], known,
                                             {"Friends": "list:7"}), ["list:7", "home"])
        self.assertEqual(columns.start_names(cfg, None, known), ["local"])
        self.assertEqual(columns.start_names({"ui": {}}, [], known), ["home", "replies"])
        self.assertEqual(columns.start_names({"ui": {}}, [], ["bots"]), ["bots"])


if __name__ == "__main__":
    unittest.main()
