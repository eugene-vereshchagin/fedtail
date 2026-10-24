"""common/timed.py: how long, which posts, whose replies — and muting through the host."""

import time
import unittest

from fedtail import i18n
from fedtail.frontends.common import timed


class Acc:
    id, handle = "B", "bob@x.test"


class View:
    def __init__(self):
        self.calls = []

    def mute(self, acc_id, on, **kw):
        self.calls.append((acc_id, on, kw))
        return "fut"


class Host:
    def __init__(self, pick=None):
        self.pick, self.done = pick, []
        if pick is not None:
            self.choose = self._choose

    def _choose(self, title, text, options, done, check=None):
        self.done.append(("choose", title, text, [k for k, _l in options], check))
        done(*self.pick)

    def call(self, fut, ok=None, fail=None):
        self.done.append(("call", fut))
        ok("rel")

    def status(self, text):
        self.done.append(("status", text))


class TimedTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_choices(self):
        self.assertEqual([s for s, _l in timed.spans()], [0, 3600, 86400, 604800, 2592000])
        self.assertEqual(timed.spans()[0][1], i18n._("span_ever"))
        self.assertEqual([k for k, _l in timed.profile_shows()], ["posts", "all", "media"])
        self.assertEqual([k for k, _l in timed.replies_policies()], ["list", "followed", "none"])
        self.assertEqual(timed.profile_show({"feed": {"profile_show": "media"}}), "media")
        self.assertEqual(timed.profile_show({"feed": {"profile_show": "odd"}}), "posts")
        self.assertEqual(timed.profile_show(None), "posts")

    def test_until(self):
        self.assertEqual(timed.until(0), "")
        now = time.mktime((2030, 5, 6, 7, 8, 0, 0, 0, -1))
        self.assertEqual(timed.until(3600, now), "06.05 08:08")

    def test_mute_asks_how_long(self):
        v, h, got = View(), Host(pick=(3600, True)), []
        timed.mute(v, h, Acc(), got.append)
        self.assertEqual(v.calls, [("B", True, {"duration": 3600, "notifications": False})])
        self.assertEqual(h.done[0][3], [0, 3600, 86400, 604800, 2592000])
        self.assertEqual(h.done[0][4], i18n._("mute_posts_only"))
        self.assertTrue(h.done[-1][1].startswith("@bob@x.test"))
        self.assertIn(timed.until(3600)[:5], h.done[-1][1])
        self.assertEqual(got, ["rel"])

    def test_mute_for_good(self):
        v, h = View(), Host(pick=("0", False))
        timed.mute(v, h, Acc())
        self.assertEqual(v.calls, [("B", True, {"duration": 0, "notifications": True})])
        self.assertEqual(h.done[-1], ("status", i18n._("muted_msg", acct="bob@x.test")))

    def test_a_host_that_cannot_ask_mutes_for_good(self):
        v, h = View(), Host()
        timed.mute(v, h, Acc())
        self.assertEqual(v.calls, [("B", True, {"duration": 0, "notifications": True})])
        self.assertEqual(h.done[0], ("call", "fut"))


class Bits(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_filter_bits(self):
        from datetime import UTC, datetime

        from fedtail.model import WordFilter
        self.assertEqual(timed.filter_extra(WordFilter("F")), "")
        f = WordFilter("F", posts=2, expires=datetime(2030, 1, 2, 3, 4, tzinfo=UTC))
        bits = timed.filter_bits(f)
        self.assertEqual(bits[0], i18n._("posts_n", n=2))
        self.assertIn("2030", bits[1])
        self.assertEqual(timed.filter_extra(f), " · " + " · ".join(bits))

    def test_keeps(self):
        from types import SimpleNamespace as NS

        from fedtail.model import Share
        own = NS(reply_to="", reply_to_author="", media=())
        to_me = NS(reply_to="9", reply_to_author="B", media=())
        to_other = NS(reply_to="9", reply_to_author="N", media=())
        pic = NS(reply_to="", reply_to_author="", media=("m",))
        import fedtail.frontends.common.timed as t
        real_was = t.real
        t.real = lambda e: e
        try:
            self.assertTrue(all(t.keeps(e, "all", "B") for e in (own, to_other)))
            self.assertEqual([t.keeps(e, "posts", "B") for e in (own, to_me, to_other)],
                             [True, True, False])
            self.assertEqual([t.keeps(e, "media", "B") for e in (own, pic)], [False, True])
            boost = Share.__new__(Share)
            t.real = lambda e: pic
            self.assertFalse(t.keeps(boost, "media", "B"))
        finally:
            t.real = real_was


if __name__ == "__main__":
    unittest.main()


class SharedEditsTest(unittest.TestCase):
    """What the windows' new editors hand on — shared, so the four agree."""

    def setUp(self):
        i18n.setup("en")

    def test_filter_changes(self):
        got = timed.filter_changes(" t ", "a, , b", "hide", [], timed.KEEP)
        self.assertEqual(got, {"title": "t", "words": ["a", "b"], "action": "hide",
                               "contexts": ["home"], "expires_in": None})
        self.assertEqual(timed.filter_changes("", "a", "warn", ["thread"], 0)["expires_in"], 0)
        self.assertIsNone(timed.filter_changes("  ", "a", "warn", [], 3600)["title"])

    def test_flag_changes_and_server_extras(self):
        from types import SimpleNamespace as NS

        from fedtail.frontends.common import server
        prof = NS(hide_collections=False, indexable=None, attribution_domains=("a.example",))
        self.assertEqual(server.flag_changes(prof, False, False, "a.example"), {})
        self.assertEqual(server.flag_changes(prof, True, True, "a.example; b.example"),
                         {"hide_collections": True, "indexable": True,
                          "attribution_domains": ["a.example", "b.example"]})
        info = NS(terms="<p>t</p>", blocks=(("bad.example", "suspend", "spam & co"),),
                  translates=(("en", ("ru",)),))
        page = server.server_more_html(info, lambda h: h)
        self.assertIn(i18n._("server_block_suspend"), page)
        self.assertIn("spam &amp; co", page)
        self.assertIn("en → ru", page)
        empty = server.server_more_html(NS(terms="", blocks=(), translates=()), lambda h: h)
        self.assertIn(i18n._("server_blocks_none").replace("'", "&#x27;"), empty)
        self.assertIn(i18n._("server_translates_none"), empty)
