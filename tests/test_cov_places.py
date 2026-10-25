"""The places (frontends/common/places.py) beyond tests/test_places.py: every button's
action and every page's odd case — an empty field, a list not there, a search with tags
and posts, a tag's "more", a follow request said no to, activity with a request in it,
a long-form post with all its parts, a server's contact, held-back notifications —
against a stand-in view, so each answer the view gives can be chosen."""

import unittest
from concurrent.futures import Future
from types import SimpleNamespace as NS

from fedtail import i18n
from fedtail.frontends.common import places
from fedtail.frontends.common.places import Out, Places
from fedtail.model import Account, Ref

_ = i18n._


def done(value=None):
    f = Future()
    f.set_result(value)
    return f


def acc(i, name="bob"):
    return Account(Ref("mastodon", "", i), name + "@x", name, name=name.title())


class View:
    """A view whose every call is noted (name, args) and answers what `answers` says
    (a done future of it; None by default)."""

    def __init__(self, **answers):
        self.calls = []
        self.answers = answers
        self.me = acc("ME", "me")
        self.lists = []
        self.cfg = {"feed": {"page_size": 2, "order": "oldest_first"}}

    def supports(self, what):
        return what not in self.answers.get("unsupported", ())

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def call(*a, **k):
            self.calls.append((name, a, k))
            got = self.answers.get(name)
            if callable(got):
                got = got(*a, **k)
            if isinstance(got, BaseException):
                f = Future()
                f.set_exception(got)
                return f
            return got if name in self.plain else done(got)
        return call

    plain = {"lists_of", "follow_requests", "activity", "activity_seen", "can_dismiss_one",
             "by_id", "lane_title", "mark_activity_seen"}

    def called(self, name):
        return [c for c in self.calls if c[0] == name]


class PlacesUnitTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_menu_leaves_out_what_the_server_lacks(self):
        v = View(unsupported={"filtered", "trends", "suggestions", "directory"})
        names = [n for n, _w in Places(v).menu()]
        for gone in ("filtered", "trends", "suggestions", "directory"):
            self.assertNotIn(gone, names)
        self.assertIn("search", names)
        with self.assertRaises(KeyError):
            Places(v).page("nope")
        with self.assertRaises(KeyError):
            Places(v).act("nope", "x")

    def test_a_failing_action_says_what_failed(self):
        v = View(mute=RuntimeError("server says no"))
        out = Places(v).act("silence", "unmute", "B")
        self.assertEqual(out.error, "server says no")
        v = View(mute=RuntimeError())
        self.assertEqual(Places(v).act("silence", "unmute", "B").error, "RuntimeError")

    def test_silence_actions(self):
        v = View()
        pl = Places(v)
        self.assertEqual(pl.act("silence", "filter_add", values={"words": " , "}).error,
                         _("filter_words"))
        pl.act("silence", "filter_add", values={"words": "a, b", "action": "hide",
                                                "contexts": ["home", 3]})
        self.assertEqual(v.called("add_filter")[0][1], ("a, b", ["a", "b"], "hide", ["home"]))
        pl.act("silence", "filter_add", values={"words": "c"})
        self.assertEqual(v.called("add_filter")[1][1][2:], ("warn", ["home"]))
        pl.act("silence", "unblock", "B")
        self.assertEqual(v.called("block")[0][1], ("B", False))

    def test_lists(self):
        v = View()
        v.lists = [NS(id="L", title="Friends", exclusive=False)]
        pl = Places(v)
        self.assertEqual(pl.act("lists", "new", values={"title": " "}).error,
                         _("list_name_q"))
        pl.act("lists", "exclusive", "L")
        self.assertEqual(v.called("update_list")[0][1], ("L", "Friends", True))
        self.assertEqual(pl.act("lists", "people", "L").open,
                         {"page": "list_people", "arg": "L"})
        self.assertEqual(pl.act("lists", "rename", "nope").error, "'nope'")
        self.assertEqual(pl.act("list_of", "new", "B", {"title": ""}).error,
                         _("list_name_q"))
        out = pl.act("list_of", "new", "B", {"title": "Work"})
        self.assertEqual(out.message, _("list_created", title="Work"))
        self.assertEqual(v.called("create_list")[0][2], {"add": "B"})

    def test_search_with_people_tags_and_posts(self):
        tag = NS(name="fedi", following=False, people=3)
        post = NS(id="P")
        v = View(search={"accounts": [acc("B")], "hashtags": [tag], "statuses": [post],
                         "relations": {}})
        pg = Places(v).page("search", "fedi")
        kinds = [r.kind for r in pg.rows]
        self.assertEqual(kinds, ["heading", "account", "heading", "tag", "heading", "post"])
        self.assertEqual(pg.rows[3].line, _("tag_people", n=3))
        empty = Places(View()).page("search", "  ")  # nothing typed: the box, no search
        self.assertEqual((empty.rows, len(empty.form)), ([], 1))
        self.assertEqual(Places(v).act("search", "go", values={"q": " x "}).open,
                         {"page": "search", "arg": "x"})

    def test_people_buttons(self):
        v = View(follow=NS(following=True), account=acc("B"))
        pl = Places(v)
        self.assertEqual(pl.act("person", "open", "B").open, {"account": "B"})
        self.assertEqual(pl.act("person", "follow", "B").message,
                         _("followed_now", acct="@bob@x"))
        v.answers["follow"] = NS(following=False)
        self.assertEqual(pl.act("person", "follow", "B").message, _("follow_asked_list"))
        pl.act("person", "unfollow", "B")
        self.assertEqual(v.called("follow")[-1][1], ("B", False))
        me_row = pl._person(v.me)
        self.assertEqual(len(me_row.buttons), 1)  # no follow button for me

    def test_tags(self):
        t = NS(name="fedi", following=True)
        posts = [NS(id="1"), NS(id="2")]
        v = View(followed_tags=[t], tag_info=RuntimeError("404"), tag_timeline=posts)
        pl = Places(v)
        self.assertEqual(pl.page("tags").rows[0].buttons[1].act[1], "unfollow")
        pg = pl.page("tag", "#fedi")
        self.assertEqual([r.kind for r in pg.rows], ["post", "post"])  # info failed
        self.assertEqual(pg.more.act, ("tag", "more", "fedi 2"))
        self.assertEqual(pl.act("tag", "open", "fedi").open, {"page": "tag", "arg": "fedi"})
        self.assertEqual(pl.act("tag", "more", "fedi 2").open,
                         {"page": "tag", "arg": "fedi", "cursor": "2"})
        self.assertEqual(pl.act("tag", "lanes", "fedi").open,
                         {"page": "taglanes", "arg": "fedi"})
        pl.act("tag", "follow", "fedi")
        pl.act("tag", "unfollow", "fedi")
        self.assertEqual([c[1] for c in v.called("follow_tag")],
                         [("fedi", True), ("fedi", False)])

    def test_tag_lanes(self):
        from fedtail.frontends.common import taglanes
        v = View()
        v.lane_title = lambda lane: "Tags A"
        pl = Places(v)
        orig = taglanes.apply
        taglanes.apply = lambda view, key, name: done("tags:a")
        try:
            out = pl.act("taglane", "add", f"{taglanes.OWN} fedi")
            self.assertEqual(out.message, _("tags_saved", tags="#fedi"))
            out = pl.act("taglane", "add", "tags:a fedi")
            self.assertEqual(out.message, _("tags_added", tag="fedi", lane="Tags A"))
        finally:
            taglanes.apply = orig

    def test_settings_errors(self):
        from fedtail.frontends.common import settings
        v = View()
        pl = Places(v)
        orig_model, orig_changes, orig_save = (settings.model, settings.changes_of,
                                               settings.save)
        try:
            settings.model = lambda view: []
            settings.changes_of = lambda chapters, values: {}
            self.assertEqual(pl.act("settings", "save").refresh, True)
            settings.save = lambda view, ch: (_ for _ in ()).throw(settings.SaveError("bad"))
            self.assertEqual(pl.act("settings", "reset", "ui.theme").error, "bad")
        finally:
            settings.model, settings.changes_of, settings.save = (orig_model, orig_changes,
                                                                  orig_save)

    def test_requests_and_activity(self):
        v = View()
        pl = Places(v)
        self.assertEqual(pl.act("requests", "no", "B").message, _("rejected"))
        from fedtail.frontends.common import activity as act
        post = NS(id="P")
        e1, e2 = NS(id="n1"), NS(id="n2")
        rows = [NS(notice="moderation", people=[], more=0, what="w", when="", post=None,
                   request=False, entries=[e1], unread=True, newest_sort="2"),
                NS(notice="", people=[acc("B")], more=4, what="liked", when="today",
                   post=post, request=True, entries=[e2], unread=False, newest_sort="1")]
        v.answers.update(activity=[e1, e2], activity_seen=0, can_dismiss_one=True)
        orig = act.rows
        act.rows = lambda entries, seen, date, oldest: rows
        from fedtail.model import text as mtext
        orig_snip = mtext.snippet
        mtext.snippet = lambda p, n: "quoted"
        try:
            pg = pl.page("activity")
        finally:
            act.rows = orig
            mtext.snippet = orig_snip
        self.assertTrue(pg.rows[0].title.startswith("● ⚠ moderation"))
        self.assertIn(_("act_more", n=4), pg.rows[1].title)
        keys = [b.act[1] for b in pg.rows[1].buttons]
        self.assertEqual(keys, ["approve", "refuse", "thread", "open", "dismiss"])
        v.answers["answer_interaction"] = True
        self.assertEqual(pl.act("activity", "approve", "n2").message, _("approved"))
        v.answers["answer_interaction"] = False
        self.assertEqual(pl.act("activity", "approve", "n2").message, _("approval_gone"))
        self.assertEqual(pl.act("activity", "refuse", "n2").message, _("approval_gone"))
        v.answers["answer_interaction"] = True
        self.assertEqual(pl.act("activity", "refuse", "n2").message, _("rejected"))
        self.assertTrue(pl.act("activity", "approve", "gone").error)
        pl.act("activity", "dismiss", "n1 n2")
        self.assertEqual([c[1] for c in v.called("dismiss_activity")], [("n1",), ("n2",)])
        self.assertEqual(pl.act("activity", "clear").confirm, _("activity_clear_q"))
        pl.act("activity", "clear", confirmed=True)
        self.assertTrue(v.called("clear_activity"))
        self.assertEqual(pl.act("post", "thread", "P").open, {"thread": "P"})

    def test_people_more_and_missing_posts(self):
        v = View(people=({"accounts": [acc("B")], "relations": {}}, "C9"))
        pl = Places(v)
        pg = pl.page("people", "B", "followers")
        self.assertEqual(pg.more.act, ("people", "more", "B followers C9"))
        self.assertEqual(pl.act("people", "more", "B followers C9").open,
                         {"page": "people", "arg": "B", "tab": "followers", "cursor": "C9"})
        with self.assertRaises(KeyError):
            pl.page("quotes", "nope")

    def test_people_further_from_their_server(self):
        """Someone of another server: my server's list ends with "more — from x", which
        reads the rest from theirs (feed.remote_people); none for my server's own."""
        v = View(people=({"accounts": [acc("B")], "relations": {}}, None), account=acc("B"),
                 people_from_origin=({"accounts": [acc("C", "cat")], "relations": {},
                                      "total": 7}, None))
        pl = Places(v)
        pg = pl.page("people", "B", "followers")
        self.assertEqual(pg.more.act, ("people", "more", "B followers origin"))
        self.assertEqual(pg.more.label, _("people_more_from", host="x"))
        pg = pl.page("people", "B", "followers", "origin")
        self.assertEqual([r.data.id for r in pg.rows if r.data], ["C"])
        self.assertEqual(pg.hint, _("people_origin_total", n=7))
        self.assertIsNone(pg.more)
        v.answers["account"] = Account(Ref("mastodon", "", "L"), "local", "local")
        self.assertIsNone(Places(v).page("people", "L", "followers").more)
        v.cfg["feed"]["remote_people"] = False
        v.answers["account"] = acc("B")
        self.assertIsNone(Places(v).page("people", "B", "followers").more)

    def test_long_form(self):
        v = View(long_form={"name": "Meetup", "start": "10:00", "end": "12:00",
                            "location": "Tbilisi", "summary": "<p>s</p>",
                            "content": "<script>x</script><p>c</p>", "url": "https://e"})
        v.by_id = lambda sid: NS(id=sid)
        v.plain = View.plain
        pg = Places(v).page("long_form", "P")
        self.assertEqual([r.kind for r in pg.rows],
                         ["heading", "text", "html", "html", "item"])
        self.assertEqual(pg.rows[1].title, "10:00 — 12:00")
        self.assertNotIn("script", pg.rows[3].title)
        v.answers["long_form"] = {"location": "only"}
        self.assertEqual([r.kind for r in Places(v).page("long_form", "P").rows], ["text"])

    def test_scheduled_trends_suggestions_directory(self):
        s = NS(id="S", at=None, text="later")
        v = View(scheduled=[s], suggestions=({"accounts": [acc("B")], "relations": {}}, None),
                 directory=({"accounts": [acc("B")], "relations": {}}, 40))
        pl = Places(v)
        self.assertEqual(pl.page("scheduled").rows[0].buttons[0].act,
                         ("scheduled", "cancel", "S"))
        pl.act("scheduled", "cancel", "S")
        self.assertTrue(v.called("cancel_scheduled"))
        v.answers["trends"] = {"tags": [NS(name="t", following=False)],
                               "statuses": [NS(id="P")],
                               "links": [{"url": "https://a", "title": "A"},
                                         NS(url="https://b", title="")]}
        self.assertEqual(pl.page("trends").rows[0].kind, "tag")
        self.assertEqual(pl.page("trends", tab="posts").rows[0].kind, "post")
        links = pl.page("trends", tab="links").rows
        self.assertEqual([r.title for r in links], ["A", "https://b"])
        self.assertEqual(pl.act("url", "open", "https://a").open, {"url": "https://a"})
        sug = pl.page("suggestions").rows[0]
        self.assertEqual(sug.buttons[-1].act, ("suggestions", "dismiss", "B"))
        pl.act("suggestions", "dismiss", "B")
        pg = pl.page("directory", tab="local", cursor="40")
        self.assertEqual(v.called("directory")[-1][2], {"local": True})
        self.assertEqual(v.called("directory")[-1][1], (40,))
        self.assertEqual(pg.more.act, ("directory", "more", "local 40"))
        self.assertEqual(pl.act("directory", "more", "local 40").open,
                         {"page": "directory", "tab": "local", "cursor": "40"})

    def test_server_and_filtered(self):
        info = NS(title="", domain="x.test", description="<p>d</p>", contact=acc("A"),
                  email="a@x", rules=[], about="", privacy="", terms="",
                  blocks=(("bad.x", "silence", ""), ("odd.x", "noop", "why")),
                  translates=())
        v = View(server_info=info)
        pg = Places(v).page("server")
        self.assertEqual(pg.title, "x.test")
        self.assertEqual(pg.rows[1].line, "Bob @bob@x · a@x")
        lines = {r.title: r.line for r in pg.rows}
        self.assertEqual(lines["bad.x"], _("server_block_silence"))
        self.assertEqual(lines["odd.x"], "noop · why")  # a word it doesn't know: as said
        self.assertIn(_("server_translates_none"), lines)
        info.contact = None
        self.assertEqual(Places(v).page("server").rows[1].line, "a@x")
        r1 = NS(id="R1", who=acc("B"), count=3)
        r2 = NS(id="R2", who=acc("C"), count=0)
        v.answers["filtered"] = {"requests": [r1, r2]}
        pg = Places(v).page("filtered")
        self.assertEqual([r.line for r in pg.rows], [_("filtered_count", n=3), ""])
        pl = Places(v)
        pl.act("filtered", "yes", "R1")
        pl.act("filtered", "no", "R2")
        self.assertEqual([c[1] for c in v.called("answer_filtered")],
                         [("R1", True), ("R2", False)])

    def test_help_odd_cases(self):
        pg = Places(View()).page("help", "no-such-page")
        self.assertEqual(pg.empty, _("help_missing"))
        pl = Places(View())
        out = pl.help_target("https://example.org/x")
        self.assertEqual(out.open, {"url": "https://example.org/x"})
        out = pl.help_target("keys.md", "index")
        self.assertEqual(out.open["page"], "help")

    def test_for_post(self):
        self.assertEqual(places.for_post(NS(id="P"))["report"], ("report", "P"))
        from fedtail.protocols.mastodon import adapter

        from .fakes import BOB, status
        share = adapter.post(dict(status("S", BOB), reblog=status("P", BOB)))
        self.assertEqual(places.for_post(share)["history"], ("history", "P"))  # the post

    def test_acc_id(self):
        self.assertEqual(places._acc_id(acc("B")), "B")
        self.assertEqual(places._acc_id(7), "7")


class OutTest(unittest.TestCase):
    def test_out_defaults(self):
        o = Out()
        self.assertEqual((o.message, o.error, o.refresh), ("", "", False))


if __name__ == "__main__":
    unittest.main()
