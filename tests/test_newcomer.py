"""Someone new in a private talk: on a received post (cardtext) and in an answer being
written (compose.count) — the banner of docs/en/dev/feeds.md §11 #5."""

import unittest

from fedtail.core import config
from fedtail.frontends.common import cardtext
from fedtail.frontends.common import compose as cc
from fedtail.frontends.common.lane import CardSpec
from fedtail.protocols.mastodon import adapter
from tests.fakes import status

ME = {"id": "ME", "acct": "me", "username": "me", "url": "https://my.example/@me"}
BOB = {"id": "B", "acct": "bob@far.example", "username": "bob",
       "url": "https://far.example/@bob"}
EVE = {"id": "E", "acct": "eve@else.example", "username": "eve",
       "url": "https://else.example/@eve"}
ANN = {"id": "A", "acct": "ann", "username": "ann", "url": "https://my.example/@ann"}


def mention(acc):
    return {"id": acc["id"], "acct": acc["acct"], "username": acc["username"],
            "url": acc["url"]}


def post(i, author, mentions=(), vis="direct", reply_to=None):
    st = status(i, author, reply_to=reply_to, vis=vis)
    st["mentions"] = [mention(m) for m in mentions]
    return adapter.post(st)


class ReceivedTest(unittest.TestCase):
    def test_someone_new(self):
        first = post("1", BOB, [ME])
        answer = post("2", BOB, [ME, EVE], reply_to="1")
        self.assertEqual(cardtext.newcomers(answer, first), ["eve@else.example"])
        bit = cardtext.newcomer_bit(answer, first)
        self.assertIn("@eve@else.example", bit.text)
        self.assertEqual(bit.link, "fedtail:account/E")

    def test_new_author(self):
        """Eve answers a private talk of Bob and me she wasn't in."""
        first = post("1", BOB, [ME])
        answer = post("2", EVE, [ME, BOB], reply_to="1")
        self.assertEqual(cardtext.newcomers(answer, first), ["eve@else.example"])

    def test_nobody_new_or_not_private(self):
        first = post("1", BOB, [ME, EVE])
        self.assertEqual(cardtext.newcomers(post("2", EVE, [ME, BOB], reply_to="1"), first),
                         [])
        self.assertEqual(cardtext.newcomers(post("2", BOB, [EVE], vis="public"), first), [])
        public = post("1", BOB, [ME], vis="public")
        self.assertEqual(cardtext.newcomers(post("2", BOB, [EVE]), public), [])
        self.assertEqual(cardtext.newcomers(post("2", BOB, [EVE]), None), [])
        self.assertEqual(cardtext.newcomers(post("2", BOB, [EVE]), "missing"), [])

    def test_on_the_card(self):
        cfg, _ = config.validate({})
        first = post("1", BOB, [ME])
        answer = post("2", BOB, [ME, EVE], reply_to="1")
        w = cardtext.card_words(CardSpec(key="2", entry=answer, parent=first), cfg,
                                lambda d: "")
        self.assertIsNotNone(w.newcomer)
        w = cardtext.card_words(CardSpec(key="1", entry=first), cfg, lambda d: "")
        self.assertIsNone(w.newcomer)


class WritingTest(unittest.TestCase):
    def setUp(self):
        self.cfg, _ = config.validate({})
        self.dm = post("1", BOB, [ME, ANN])

    def count(self, text, vis="direct", reply_to="dm"):
        return cc.count(text, "", 500, self.cfg, reply_to=self.dm if reply_to else None,
                        visibility=vis, me=adapter.account(ME)).newcomers

    def test_typed_someone_new(self):
        self.assertEqual(self.count("@bob@far.example @ann hi @eve@else.example"),
                         ("@eve@else.example",))

    def test_local_with_or_without_host(self):
        self.assertEqual(self.count("@ann@my.example @me@my.example @bob@far.example ok"), ())
        self.assertEqual(self.count("@zed hi"), ("@zed",))

    def test_not_private_or_no_reply(self):
        self.assertEqual(self.count("@eve@else.example", vis="public"), ())
        self.assertEqual(self.count("@eve@else.example", reply_to=None), ())

    def test_email_isnt_a_mention(self):
        self.assertEqual(self.count("write to eve@else.example. Ok?"), ())

    def test_me_isnt_new(self):
        self.assertEqual(self.count("@me hi"), ())


class ThreadNewsTest(unittest.TestCase):
    """feed.thread_news: "🔔 N new in the thread" under a post whose followed thread has
    new replies."""

    def test_bit(self):
        cfg, _ = config.validate({})
        root = post("1", ME, vis="public")
        spec = CardSpec(key="1", entry=root, extra={"thread_news": 3})
        w = cardtext.card_words(spec, cfg, lambda d: "")
        self.assertIn("3", w.thread_news.text)
        self.assertEqual(w.thread_news.link, "fedtail:thread/1")
        self.assertIsNone(cardtext.card_words(CardSpec(key="1", entry=root), cfg,
                                              lambda d: "").thread_news)


if __name__ == "__main__":
    unittest.main()
