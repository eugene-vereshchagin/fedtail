"""core/atoms.py: every atom of docs/en/dev/feeds.md §2 from a stored status, and the rules
of free lanes (§4) — parsing, strict checks, matching, explaining."""

import unittest
from datetime import UTC, datetime, timedelta

from fedtail.core.atoms import (
    Condition,
    Facts,
    Rule,
    World,
    event_facts,
    handle,
    never,
    post_facts,
)

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
ME = {"id": "1", "acct": "veresk", "url": "https://home.example/@veresk"}
FRIEND = {"id": "2", "acct": "friend@far.example", "url": "https://far.example/@friend"}
FAN = {"id": "3", "acct": "fan", "url": "https://home.example/@fan"}
STRANGER = {"id": "4", "acct": "who@else.example", "url": "https://else.example/@who",
            "created_at": "2026-10-20T00:00:00Z"}
BOT = {"id": "5", "acct": "news@bots.example", "bot": True}


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def st(sid, account, **kw):
    d = {"id": sid, "account": account, "content": kw.pop("content", "<p>hi</p>"),
         "visibility": "public", "created_at": iso(NOW - timedelta(hours=1)),
         "mentions": [], "tags": [], "media_attachments": []}
    d.update(kw)
    return d


def world(**kw):
    base = dict(me_id="1", my_host="home.example", following={"2", "5"}, followers={"2", "3"},
                now=NOW)
    base.update(kw)
    return World(**base)


def facts(status, **kw):
    source = kw.pop("source", None)
    return post_facts(status, world(**kw), source)


def cond(**kw):
    return Condition.parse(kw)


class AuthorTest(unittest.TestCase):
    def test_relationships(self):
        self.assertTrue({"me", "local", "@veresk@home.example"} <= facts(st("a", ME)).author)
        f = facts(st("b", FRIEND)).author
        self.assertTrue({"followed", "follower", "mutual", "remote", "@friend@far.example",
                         "domain:far.example"} <= f)
        self.assertNotIn("stranger", f)
        f = facts(st("c", FAN)).author
        self.assertTrue({"follower", "stranger", "local"} <= f)
        f = facts(st("d", STRANGER)).author
        self.assertTrue({"stranger", "not_follower", "new", "remote"} <= f)
        self.assertIn("bot", facts(st("e", BOT)).author)

    def test_extras(self):
        f = facts(st("x", dict(FAN, limited=True)), new_followers={"3"}, bell={"3"},
                  boosts_off={"3"}, in_lists={"3"}).author
        self.assertTrue({"limited", "new_follower", "bell", "boosts_off", "in_list"} <= f)
        self.assertIn("bot", facts(st("y", FAN), extra_bots=("fan",)).author)

    def test_handle(self):
        self.assertEqual(handle({"acct": "Me"}, "h.example"), "me@h.example")
        self.assertEqual(handle({"acct": "me", "url": "https://www.x.example/@me"}), "me@x.example")
        self.assertEqual(handle({"acct": "a@b"}), "a@b")
        self.assertEqual(handle({"acct": "solo"}), "solo")
        self.assertEqual(handle({"acct": "x", "url": "http://[bad"}), "x")
        self.assertEqual(handle({}), "")

    def test_no_world(self):
        f = post_facts(st("a", FRIEND))
        self.assertTrue({"stranger", "not_follower", "remote"} <= f.author)
        self.assertEqual(f.state, {"unread"})


class KindVisibilityTest(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(facts(st("a", FRIEND)).kind, {"post"})
        r = facts(st("b", FRIEND, in_reply_to_id="z", in_reply_to_account_id="4"))
        self.assertEqual(r.kind, {"reply"})
        sr = facts(st("c", FRIEND, in_reply_to_id="z", in_reply_to_account_id="2"))
        self.assertEqual(sr.kind, {"reply", "self_reply"})
        b = facts(st("d", FAN, reblog=st("e", FRIEND)))
        self.assertEqual(b.kind, {"boost", "post"} - {"post"})
        self.assertEqual(b.id, {"d", "e"})
        sb = facts(st("f", FRIEND, reblog=st("g", FRIEND)))
        self.assertIn("self_boost", sb.kind)
        q = facts(st("h", FRIEND, quote={"state": "accepted", "quoted_status": st("i", ME)},
                     poll={"options": [{"title": "да"}]}, edited_at="2026-10-27T11:30:00Z"))
        self.assertTrue({"post", "quote", "poll", "edited"} <= q.kind)
        self.assertIn("quote_of_mine", q.me)
        q2 = facts(st("j", FRIEND, quote=st("k", FAN)))
        self.assertIn("quote", q2.kind)
        self.assertNotIn("quote_of_mine", q2.me)

    def test_visibility(self):
        for raw, ours in (("private", "followers"), ("direct", "direct"),
                          ("unlisted", "unlisted"), ("mutuals_only", "mutuals"),
                          ("local", "local_only"), ("weird", "public")):
            self.assertEqual(facts(st("a", FRIEND, visibility=raw)).visibility, {ours})
        self.assertEqual(facts(st("a", FRIEND, local_only=True)).visibility,
                         {"public", "local_only"})
        self.assertEqual(facts(st("a", FRIEND, visibility=None)).visibility, {"public"})


class MeParentTest(unittest.TestCase):
    def test_replies_to_me(self):
        to_post = st("r", FRIEND, in_reply_to_id="p", in_reply_to_account_id="1")
        f = facts(to_post, parents={"p": st("p", ME)})
        self.assertEqual(f.me, {"reply", "reply_to_post"})
        self.assertEqual(f.parent, {"mine"})
        self.assertFalse(f.unsure)
        f = facts(to_post, parents={"p": st("p", ME, in_reply_to_id="q")})
        self.assertEqual(f.me, {"reply", "reply_to_comment"})
        f = facts(to_post, parents={"p": "missing"})
        self.assertEqual(f.me, {"reply"})
        self.assertEqual(f.unsure, {"me"})

    def test_mentions_direct_threads(self):
        m = facts(st("m", FRIEND, mentions=[{"id": "1"}]))
        self.assertEqual(m.me, {"mention"})
        d = facts(st("d", FRIEND, visibility="direct", mentions=[{"id": "1"}]))
        self.assertEqual(d.me, {"mention", "direct"})
        mine = facts(st("e", ME, visibility="direct", mentions=[{"id": "2"}]))
        self.assertEqual(mine.me, {"direct"})
        t = facts(st("t", STRANGER, in_reply_to_id="x", in_reply_to_account_id="2"),
                  my_threads={"t"})
        self.assertIn("in_my_thread", t.me)
        self.assertEqual(t.parent, {"followed"})
        self.assertEqual(facts(st("u", ME), my_threads={"u"}).me, set())

    def test_boost_atoms(self):
        mine_boosted = facts(st("b", FRIEND, reblog=st("o", ME)))
        self.assertIn("boost_of_mine", mine_boosted.me)
        my_boost = facts(st("b", ME, reblog=st("o", FRIEND)))
        self.assertIn("my_boost", my_boost.me)

    def test_parent(self):
        self.assertEqual(facts(st("a", FRIEND, in_reply_to_id="p",
                                  in_reply_to_account_id="4")).parent, {"stranger"})
        self.assertEqual(facts(st("a", FRIEND, in_reply_to_id="p")).parent, {"unknown"})
        self.assertEqual(facts(st("a", FRIEND, in_reply_to_id="p"),
                               parents={"p": st("p", STRANGER)}).parent, {"stranger"})
        self.assertEqual(facts(st("a", FRIEND)).parent, set())


class TargetTest(unittest.TestCase):
    """What a boost is about: my post, my comment, someone's post — seen or read already."""

    def test_boosts(self):
        self.assertEqual(facts(st("b", FRIEND, reblog=st("o", ME))).target, {"my_post"})
        self.assertEqual(facts(st("b", FRIEND, reblog=st("o", ME, in_reply_to_id="x"))).target,
                         {"my_comment"})
        self.assertEqual(facts(st("b", FRIEND, reblog=st("o", FAN))).target, {"post"})
        f = facts(st("b", FRIEND, reblog=st("o", FAN, in_reply_to_id="x")),
                  seen_before={"o"}, read={"o"})
        self.assertEqual(f.target, {"comment", "seen", "read"})
        self.assertEqual(facts(st("a", FRIEND)).target, set())

    def test_events(self):
        like = event_facts({"id": "n1", "type": "favourite", "account": FRIEND,
                            "status": st("o", ME, in_reply_to_id="x"),
                            "created_at": "2026-10-27T11:00:00Z"}, world())
        self.assertEqual(like.event, {"favourite"})
        self.assertEqual(like.target, {"my_comment"})
        self.assertIn("followed", like.author)
        self.assertEqual(like.kind, set())
        self.assertIn("n1", like.id)
        self.assertEqual(like.created, datetime(2026, 10, 27, 11, tzinfo=UTC))


class HasLangStateViaTest(unittest.TestCase):
    def test_has(self):
        s = st("a", FRIEND, spoiler_text="cw", sensitive=True, poll={"options": []},
               media_attachments=[{"type": "image", "description": "a cat"},
                                  {"type": "gifv"}, {"type": "audio", "description": " "},
                                  {"type": "unknown", "description": "x"}],
               tags=[{"name": "Georgia"}, {}],
               content='<p><a href="https://far.example/@x" class="u-url mention">@x</a> '
                       '<a href="https://far.example/tags/georgia" class="mention hashtag">#g</a>'
                       ' <a href="https://www.blog.example/post">blog</a></p>',
               card={"url": "https://news.example/a"})
        f = facts(s, followed_tags={"georgia"})
        self.assertTrue({"media", "image", "video", "audio", "alt_missing", "cw", "sensitive",
                         "poll", "tag:georgia", "followed_tag", "link", "link:blog.example",
                         "link:news.example"} <= f.has)
        self.assertNotIn("link:far.example", f.has)
        plain = facts(st("b", FRIEND))
        self.assertEqual(plain.has, set())
        self.assertNotIn("alt_missing", facts(st("c", FRIEND, media_attachments=[
            {"type": "image", "description": "ok"}])).has)

    def test_lang_texts_counts_times(self):
        s = st("a", FRIEND, language="RU", spoiler_text="Внимание",
               media_attachments=[{"type": "image", "description": "кот"}],
               poll={"options": [{"title": "да"}, {}]}, favourites_count=7, reblogs_count=None)
        f = facts(s)
        self.assertEqual(f.lang, {"ru"})
        self.assertEqual(facts(st("b", FRIEND)).lang, {"unknown"})
        self.assertEqual(f.texts["text"].strip(), "hi")
        self.assertEqual((f.texts["cw"], f.texts["alt"], f.texts["poll"]),
                         ("Внимание", "кот", "да\n"))
        self.assertEqual(f.counts, {"likes": 7, "boosts": 0, "replies": 0})
        b = facts(st("w", FAN, created_at="2026-10-27T11:00:00Z",
                     reblog=st("o", FRIEND, created_at="2026-10-01T00:00:00Z")))
        self.assertEqual(b.created, datetime(2026, 10, 27, 11, tzinfo=UTC))
        self.assertEqual(b.original_created, datetime(2026, 10, 1, tzinfo=UTC))
        self.assertIsNone(facts(st("x", FRIEND, created_at="nonsense")).created)
        self.assertIsNone(facts(st("x", FRIEND, created_at="")).created)
        self.assertEqual(facts(st("x", FRIEND, created_at="2026-10-01T00:00:00")).created,
                         datetime(2026, 10, 1, tzinfo=UTC))

    def test_state(self):
        s = st("a", FRIEND, bookmarked=True, favourited=True, reblogged=True, muted=True)
        f = facts(s, read={"a"}, replied={"a"}, subscribed={"a"}, in_lists={"2"},
                  filtered_warn={"a"})
        self.assertEqual(f.state, {"read", "bookmarked", "liked", "boosted", "replied",
                                   "subscribed", "in_list", "muted_thread", "filtered_warn"})
        self.assertIn("muted_thread", facts(st("b", FRIEND), muted_threads={"b"}).state)
        self.assertEqual(facts(st("c", FRIEND)).state, {"unread"})

    def test_via(self):
        self.assertEqual(facts(st("a", ME)).via, {"mine"})
        self.assertEqual(facts(st("b", FAN, reblog=st("c", STRANGER))).via, set())
        self.assertEqual(facts(st("b", FRIEND, reblog=st("c", STRANGER))).via, {"boost"})
        self.assertEqual(facts(st("d", FRIEND), in_lists={"2"}).via, {"followed", "list"})
        self.assertEqual(facts(st("e", STRANGER, tags=[{"name": "go"}]),
                               followed_tags={"go"}).via, {"tag"})

    def test_source(self):
        self.assertEqual(facts(st("a", FRIEND), source="home").source, {"home"})
        self.assertEqual(facts(st("a", FRIEND), source=["home", "local"]).source,
                         {"home", "local"})


class ConditionTest(unittest.TestCase):
    def test_and_or(self):
        f = facts(st("a", FRIEND), source="home")
        self.assertTrue(cond(author="followed", kind="post").matches(f))
        self.assertTrue(cond(author=["stranger", "mutual"]).matches(f))
        self.assertFalse(cond(author="followed", kind="reply").matches(f))
        self.assertTrue(cond(source="home").matches(f))
        self.assertTrue(cond(id="a").matches(f))
        self.assertTrue(cond(lang="UNKNOWN").matches(f))

    def test_authors_by_name_and_domain(self):
        f = facts(st("a", FRIEND))
        self.assertTrue(cond(author="@Friend@far.example").matches(f))
        self.assertTrue(cond(author="friend@far.example").matches(f))
        self.assertTrue(cond(author="domain:FAR.example").matches(f))
        self.assertTrue(cond(author="domain:{x.example, far.example}").matches(f))
        self.assertFalse(cond(author="domain:{x.example,y.example}").matches(f))

    def test_counts_and_age(self):
        f = facts(st("a", FRIEND, favourites_count=12, replies_count=3,
                     created_at=iso(NOW - timedelta(days=3))))
        self.assertTrue(cond(likes=">10").matches(f))
        self.assertTrue(cond(likes="12").matches(f))   # no sign: at least
        self.assertTrue(cond(replies="=3", boosts="<1").matches(f))
        self.assertFalse(cond(likes=">=13").matches(f))
        self.assertTrue(cond(age=">2d").matches(f, NOW))
        self.assertFalse(cond(age="<1d").matches(f, NOW))
        self.assertTrue(cond(age="<= 4d").matches(f, NOW))
        self.assertTrue(cond(age=">1w").matches(f, NOW + timedelta(days=5)))
        self.assertTrue(cond(age="<90m").matches(facts(st("b", FRIEND)), NOW))
        self.assertTrue(cond(age=">0.5h").matches(facts(st("b", FRIEND)), NOW))
        self.assertTrue(cond(age=">1d").matches(f))  # now: the real clock
        no_time = facts(st("c", FRIEND, created_at=""))
        self.assertFalse(cond(age="<1d").matches(no_time, NOW))

    def test_old_boost_by_original(self):
        old = facts(st("w", FAN, reblog=st("o", FRIEND, created_at="2026-10-01T00:00:00Z")))
        c = cond(kind="boost", age=">2d", age_of="original")
        self.assertTrue(c.matches(old, NOW))
        self.assertFalse(cond(kind="boost", age=">2d").matches(old, NOW))

    def test_text(self):
        s = st("a", FRIEND, content="<p>Тбилиси и Батуми</p>", spoiler_text="Поездка",
               media_attachments=[{"type": "image", "description": "Море"}],
               poll={"options": [{"title": "Да"}]})
        f = facts(s)
        self.assertTrue(cond(text=[["тбилиси", "батуми"]]).matches(f))
        self.assertTrue(cond(text=[["кутаиси"], ["поездка"]]).matches(f))
        self.assertFalse(cond(text=[["тбилиси", "кутаиси"]]).matches(f))
        self.assertTrue(cond(text="батуми").matches(f))
        self.assertTrue(cond(has="word:Тбилиси").matches(f))
        self.assertFalse(cond(text="море").matches(f))
        self.assertTrue(cond(text="море", text_in=["alt"]).matches(f))
        self.assertTrue(cond(text="да", text_in="poll").matches(f))
        self.assertFalse(cond(text="тбилиси", text_case=True).matches(f))
        self.assertTrue(cond(text="Тбилиси", text_case=True).matches(f))
        self.assertTrue(cond(text=r"Тбил\w+", text_regex=True).matches(f))
        self.assertTrue(cond(text=r"тбил", text_regex=True).matches(f))
        self.assertFalse(cond(text=r"тбил", text_regex=True, text_case=True).matches(f))

    def test_show_keys(self):
        c = cond(kind="reply", switch="Комменты", shown=False, priority=2)
        self.assertEqual((c.switch, c.shown, c.priority, c.broken), ("Комменты", False, 2, False))

    def test_errors_mark_and_never_match(self):
        f = facts(st("a", FRIEND))
        for bad in ({"me": "replys"}, {"colour": "red"}, {"author": ""}, {"author": 5},
                    {"source": "list:"}, {"has": "tag:"}, {"likes": "many"},
                    {"age": "old"}, {"age_of": "boost"}, {"text": [["ok"], [""]]},
                    {"text": 5}, {"text": []}, {"text_in": ["body"]}, {"text_in": []},
                    {"text_case": "yes"}, {"switch": ""}, {"priority": True},
                    {"priority": "1"}, {"text": "(", "text_regex": True}):
            with self.subTest(bad=bad):
                warnings = []
                c = Condition.parse(bad, warnings)
                self.assertTrue(c.broken)
                self.assertTrue(warnings)
                self.assertFalse(c.matches(f))
                self.assertEqual(c.why_not(f), "the condition has an error")
        c = Condition.parse(["not", "a", "table"])
        self.assertTrue(c.broken)

    def test_good_parametric_values(self):
        for good in ({"source": "list:7"}, {"source": "tags:any=a,b"}, {"source": "remote:x.org"},
                     {"source": "link:https://a.example/x"}, {"source": "quotes:9"},
                     {"source": "account:2"}, {"has": "link:a.example"},
                     {"author": "domain:{a,b}"}, {"event": "unfollow"}, {"target": "seen"}):
            with self.subTest(good=good):
                self.assertFalse(cond(**good).broken)

    def test_why_not(self):
        f = facts(st("a", FRIEND, favourites_count=1))
        self.assertEqual(cond(author="followed", kind="reply").why_not(f), "kind")
        self.assertEqual(cond(likes=">5").why_not(f), "likes")
        self.assertEqual(cond(age=">5d").why_not(f, NOW), "age")
        self.assertEqual(cond(text="nope").why_not(f), "text")
        self.assertEqual(cond(author="followed").why_not(f), "")


class RuleTest(unittest.TestCase):
    FEED = {"name": "feed", "title": "Лента", "any": [
        {"author": "local", "kind": "post"}, {"me": "reply"}, {"author": "me"}]}

    def test_authors_feed(self):
        r = Rule.parse(self.FEED)
        self.assertEqual((r.name, r.title, r.warnings), ("feed", "Лента", []))
        self.assertTrue(r.takes(facts(st("a", FAN))))         # my server's post
        self.assertTrue(r.takes(facts(st("b", ME))))          # mine
        self.assertTrue(r.takes(facts(st("c", STRANGER, in_reply_to_id="p",
                                         in_reply_to_account_id="1"))))   # a reply to me
        self.assertFalse(r.takes(facts(st("d", FRIEND))))     # someone far away

    def test_none_source_priority(self):
        r = Rule.parse({"name": "posts", "source": "home", "any": [
            {"author": "me"}, {"kind": "boost", "priority": 5}],
            "none": {"kind": "boost", "age": ">2d", "age_of": "original"}})
        old = facts(st("w", FAN, reblog=st("o", ME, created_at="2026-10-01T00:00:00Z")),
                    source="home")
        self.assertFalse(r.takes(old, NOW))
        fresh = facts(st("w", FAN, reblog=st("o", ME)), source="home")
        self.assertEqual(r.taken_by(fresh, NOW).priority, 5)
        self.assertFalse(r.takes(facts(st("x", ME), source="local")))
        verdicts = r.explain(facts(st("x", ME), source="local"))
        self.assertEqual(verdicts[0], ("source", -1, "source"))
        self.assertEqual([v[0] for v in r.explain(old, NOW)], ["none", "any", "any"])

    def test_lane_keys(self):
        r = Rule.parse({"name": "c", "any": [{"source": "home"}], "mode": "catch_up",
                        "sort": "likes", "read": "browse", "group": "моё",
                        "filter_context": "home"})
        self.assertEqual((r.mode, r.sort, r.read, r.group, r.filter_context, r.title),
                         ("catch_up", "likes", "browse", "моё", "home", "c"))
        self.assertEqual(r.window, timedelta(hours=12))
        self.assertEqual(Rule.parse({"name": "w", "any": [{}], "window": "2d"}).window,
                         timedelta(days=2))

    def test_rule_warnings(self):
        def warned(table):
            return Rule.parse(table).warnings
        self.assertTrue(warned({"any": [{}]}))                       # no name
        self.assertTrue(warned({"name": "x"}))                       # takes nothing
        self.assertTrue(warned({"name": "x", "any": [{}], "colour": 1}))
        self.assertTrue(warned({"name": "x", "any": "home"}))
        self.assertTrue(warned({"name": "x", "any": [{}], "sort": "random"}))
        self.assertTrue(warned({"name": "x", "any": [{}], "window": "soon"}))
        self.assertTrue(warned({"name": "x", "any": [{}], "source": "nowhere"}))
        self.assertTrue(warned(["not a table"]))
        self.assertTrue(warned({"name": "x", "any": [
            {"author": "stranger", "visibility": "followers"}]}))

    def test_never(self):
        self.assertIn("followers-only", never(cond(author="stranger", visibility="followers")))
        self.assertIn("home", never(cond(source="home", kind="reply", parent="stranger",
                                         author="followed")))
        self.assertIn("public", never(cond(source="federated", visibility="unlisted")))
        self.assertEqual(never(cond(source="home")), "")

    def test_facts_default(self):
        self.assertEqual(Facts().source, set())


if __name__ == "__main__":
    unittest.main()
