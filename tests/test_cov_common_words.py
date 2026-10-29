"""The words and links of a card, and the command line (frontends/common: links.py,
cardtext.py, commands.py), against stand-ins that note what they are asked: every
fedtail: link a card can hold does its one thing, every line under a post says what it
should, every command reaches the core it should."""

import dataclasses
import types
import unittest
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest import mock

from fedtail import i18n
from fedtail.frontends.common import cardtext, commands, lane, links
from fedtail.model import Media, Mine, Quote, Reaction, Ref, Share
from fedtail.protocols.mastodon.adapter import post as to_post

from .fakes import BOB, ME, status


def post(i="1", author=BOB, **kw):
    p = to_post(status(i, author, vis="public", text="hello there"))
    return dataclasses.replace(p, **kw) if kw else p


def done(value=None):
    f = Future()
    f.set_result(value)
    return f


class Host:
    """The window: notes each call; confirm() says yes; call() hands back None."""

    def __init__(self, without=()):
        self.done = []
        self.without = set(without)

    def __getattr__(self, name):
        if name in self.without or name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: self.done.append((name, a, k))

    def call(self, fut, ok=None, fail=None):
        self.done.append(("call", fut))
        if ok:
            ok(None)

    def choose(self, title, text, options, done, check=None):
        """How long and the like: the first choice, the box unticked."""
        self.done.append(("choose", title))
        done(options[0][0], False)

    def confirm(self, title, text, then):
        self.done.append(("confirm", title, text))
        then()


class View:
    def __init__(self, posts, me=True):
        self.posts = {p.id: p for p in posts}
        self.me = types.SimpleNamespace(handle="mira") if me else None
        self.read = []

    def by_id(self, sid):
        return self.posts.get(sid)

    def mark_read(self, ids):
        self.read += ids

    def __getattr__(self, name):
        return lambda *a, **k: (name, a)


class LinksTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")
        mine = post("9", ME)
        self.p = post("1", quote=Quote(post=mine), media=(Media(Ref("m", "", "m")),))
        self.view = View([self.p, post("2", dict(BOB, acct="local"))])

    def open(self, url, host=None, view=None):
        host = host or Host()
        links.Links(view or self.view, host).open(url)
        return host.done

    def test_the_outside_and_the_places(self):
        self.assertEqual(self.open("https://x.test/a")[0][0], "open_url")
        self.assertEqual(self.open("fedtail:alias/a3f")[0], ("put_alias", ("a3f",), {}))
        self.assertEqual(self.open("fedtail:resolve/https%3A%2F%2Fx")[0][1], ("https://x",))
        self.assertEqual(self.open("fedtail:tag/caf%C3%A9")[0][1], ("café",))
        self.assertEqual(self.open("fedtail:account/7")[0][0], "open_account")
        self.assertEqual(self.open("fedtail:nothing/404")[0][0], "error")  # not cached
        lacking = Host(without={"put_alias"})
        self.open("fedtail:alias/a3f", lacking)
        self.assertEqual(lacking.done[0], ("status", (i18n._("gtk_not_yet"),), {}))

    def test_post_actions(self):
        cases = {
            "poll": "call", "edit": "compose", "history": "show_history", "open": "open_url",
            "quote": "compose", "readupto": "read_up_to", "favourited_by": "open_reactions",
            "quotes": "open_quotes", "report": "report",
        }
        for action, first in cases.items():
            self.assertEqual(self.open(f"fedtail:{action}/1")[0][0], first, action)
        got = self.open("fedtail:invite/1")
        self.assertEqual(got[0], ("compose", (), {"reply_to": self.p, "invite": True}))
        self.assertEqual(self.open("fedtail:invite/1", view=View([self.p], me=False)), [])
        self.open("fedtail:readone/1")
        self.assertEqual(self.view.read, ["1"])
        got = self.open("fedtail:mute/1")  # how long first, then the call
        self.assertEqual([g[0] for g in got[:2]], ["choose", "call"])
        for action, said in (("fav", None), ("boost", None),
                             ("sub", "subbed"), ("unsub", "unsubbed"),
                             ("mutethread", "thread_muted"), ("unmutethread", "thread_unmuted"),
                             ("pin", "pinned_msg"), ("unpin", "unpinned_msg")):
            got = self.open(f"fedtail:{action}/1")
            self.assertEqual(got[0][0], "call", action)
            if said:
                self.assertEqual(got[-1][1][0].split(" ")[0],
                                 i18n._(said, acct="bob@social.example").split(" ")[0])
        got = self.open("fedtail:bookmark/1")
        self.assertEqual(got[0][1], ("bookmark", (self.p, True)))
        self.assertEqual(got[1], ("status", (i18n._("bookmarked"),), {}))
        marked = dataclasses.replace(self.p, mine=Mine(bookmarked=True))
        got = self.open("fedtail:bookmark/1", view=View([marked]))
        self.assertEqual(got[1], ("status", (i18n._("unbookmarked"),), {}))

    def test_the_ones_that_ask_first(self):
        for action in ("block", "blockdomain", "revokequote", "delete", "redraft"):
            got = self.open(f"fedtail:{action}/1")
            self.assertEqual(got[0][0], "confirm", action)
            self.assertEqual(got[1][0], "call", action)
        self.assertIn(i18n._("redraft_media", n=1), self.open("fedtail:redraft/1")[0][2])
        # nothing to do: a local account has no domain; no quote of mine to revoke
        self.assertEqual(self.open("fedtail:blockdomain/2"), [])
        self.assertEqual(self.open("fedtail:revokequote/2"), [])

    def test_unknown_action(self):
        with self.assertLogs("fedtail.frontends.common.links", "WARNING"):
            self.assertEqual(self.open("fedtail:frobnicate/1"), [])


class CardWordsTest(unittest.TestCase):
    CFG = {"feed": {"old_days": 30, "show_reply_context": True, "emoji": True,
                    "quotes": "card"}, "ui": {"arts_mode": False}}

    def setUp(self):
        i18n.setup("en")

    def words(self, entry, **kw):
        spec = lane.CardSpec("k", entry, **kw)
        return cardtext.card_words(spec, self.CFG, lambda d: d.strftime("%H:%M"))

    def test_a_boost_edited_old_and_folded(self):
        now = datetime.now(UTC)
        p = post("1", created=now - timedelta(days=100), edited=now,
                 filtered=("politics",), warning="spoilers", reply_to="0",
                 reactions=(Reaction("👍", 3), Reaction("blobcat", 2), Reaction("x", 0)))
        boost = Share(Ref("m", "", "b"), post("8").author, p, now, "b")
        w = self.words(boost, parent="missing")
        self.assertTrue(w.boosted.text.startswith("♻ "))
        self.assertIn("·", w.boosted.text)
        self.assertEqual([b.kind for b in w.meta], ["time", "vis", "edited", "old"])
        self.assertEqual(w.context.text, i18n._("ctx_missing"))
        self.assertTrue(w.folded)
        self.assertIn("⚠ spoilers", w.warning)
        self.assertEqual(w.reactions, "👍 3 :blobcat: 2")
        loading = self.words(post("2", reply_to="0"))
        self.assertEqual(loading.context.text, i18n._("ctx_loading"))
        no_time = Share(Ref("m", "", "b2"), post("8").author, post("3"), None, "b2")
        self.assertNotIn("·", self.words(no_time).boosted.text)

    def test_conversation_line(self):
        top, last = post("1"), post("3")
        w = self.words(top, extra={"conversation": {"members": ["1", "2", "3"], "unread": 1,
                                                     "last": last}})
        self.assertTrue(w.conversation.text.startswith("💬 "))
        self.assertEqual(w.conversation.link, "fedtail:thread/3")

    def test_quotes(self):
        self.assertIsNone(cardtext.quote_bit(None))
        self.assertIsNone(cardtext.quote_bit(Quote(id="5"), "off"))
        blocked = cardtext.quote_bit(Quote(state="blocked_account", id="5"))
        self.assertIn(i18n._("quote_show_anyway"), blocked.text)
        self.assertEqual(blocked.link, "fedtail:thread/5")
        odd = cardtext.quote_bit(Quote(state="some_new_state"))
        self.assertEqual(odd.text, "❝ " + i18n._("quote_unavailable"))
        self.assertEqual(odd.link, "")
        self.assertEqual(cardtext.quote_bit(Quote(id="5")).text, "❝ " + i18n._("quote_open"))
        pics = post("6", media=(Media(Ref("m", "", "m")),))
        self.assertIn(i18n._("quote_media", n=1), cardtext.quote_bit(Quote(post=pics)).text)
        warned = cardtext.quote_bit(Quote(post=post("7", warning="cw")))
        self.assertIn("⚠ cw", warned.text)
        self.assertEqual(cardtext.name_of(None), "?")


class Core:
    """What Commands asks: aliases, people, and doings — each noted."""

    def __init__(self, plain_posts=True):
        self.cfg = {"post": {"plain_posts": plain_posts}}
        self.me = types.SimpleNamespace(handle="mira")
        self.did = []
        self.bg = ThreadPoolExecutor(1)
        self.p = post("1")

    def by_alias(self, alias):
        return self.p if alias == "abc" else None

    def target(self, alias, number):
        return done(self.p if number == 0 else None)

    def find_user(self, user):
        return done(None if user == "nobody" else self.p.author)

    def default_visibility(self):
        return "public"

    def reply_visibility(self, _p):
        return "unlisted"

    def __getattr__(self, name):
        def doing(*a, **k):
            self.did.append((name, a))
            return done(None)
        return doing


class CommandsTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")
        self.core = Core()
        self.addCleanup(self.core.bg.shutdown)
        self.c = commands.Commands(self.core)

    def run_line(self, line, **kw):
        fut, msg = self.c.run(line, **kw)
        return (fut.result(timeout=5) if fut is not None else None), msg

    def test_preview(self):
        core = self.core
        self.assertEqual(commands.preview(core, "  "), "")
        self.assertIn("@bob", commands.preview(core, "S @bob"))
        self.assertTrue(commands.preview(core, "plain words"))
        self.assertEqual(commands.preview(core, "?"), i18n._("cmd_do_help"))
        self.assertEqual(commands.preview(core, "S nonsense"), i18n._("cmd_unknown"))
        self.assertIn(i18n._("cmd_as_post"), commands.preview(core, "#zzz hi"))
        self.assertIn("#abc/2", commands.preview(core, "#abc/2 hi"))
        self.assertEqual(commands.preview(Core(plain_posts=False), "words"),
                         i18n._("cmd_unknown"))

    def test_history(self):
        h = commands.History()
        self.assertIsNone(h.up())
        self.assertIsNone(h.down())
        for line in ("a", "a", " ", "b"):
            h.add(line)
        self.assertEqual((h.up(), h.up(), h.up()), ("b", "a", "a"))
        self.assertEqual((h.down(), h.down()), ("b", ""))

    def test_lines_that_do_nothing(self):
        self.assertEqual(self.c.run("S nonsense"), (None, i18n._("cmd_unknown")))
        self.assertEqual(self.c.run("?"), (None, i18n._("cmd_help")))
        no_plain = commands.Commands(Core(plain_posts=False))
        self.assertEqual(no_plain.run("words")[1], i18n._("cmd_unknown"))
        self.assertEqual(self.c.run("! #zzz")[1], i18n._("cmd_no_post", alias="zzz"))

    def test_people(self):
        self.assertIsInstance(self.run_line("@nobody")[0], commands.Failed)
        self.assertEqual(self.run_line("@bob hi there")[0], i18n._("sent"))
        self.assertEqual(self.core.did[-1], ("post", ("@bob hi there", "direct")))
        kind, acc = self.run_line("@bob")[0]
        self.assertEqual(kind, "profile")
        self.assertIn("bob", self.run_line("S @bob")[0])
        self.assertEqual(self.core.did[-1][1][1], True)
        self.run_line("U @bob")
        self.assertEqual(self.core.did[-1][1][1], False)

    def test_posts(self):
        self.assertIsInstance(self.run_line("#abc/3")[0], commands.Failed)
        self.assertEqual(self.run_line("#abc")[0], ("thread", "1"))
        self.assertEqual(self.run_line("#abc hi")[0], i18n._("sent"))
        self.assertEqual(self.core.did[-1][1][1:], ("unlisted", self.core.p))
        self.assertEqual(self.run_line("S #abc")[0], i18n._("subbed"))
        self.assertEqual(self.run_line("U #abc")[0], i18n._("unsubbed"))
        self.assertEqual(self.run_line("! #abc")[0], i18n._("cmd_boosted"))
        self.assertEqual(self.run_line("~ #abc")[0], i18n._("bookmarked"))
        self.core.p = dataclasses.replace(self.core.p, mine=Mine(bookmarked=True))
        self.assertEqual(self.run_line("~ #abc")[0], i18n._("unbookmarked"))
        self.assertEqual(self.run_line("D #abc")[0], ("delete", self.core.p))
        self.assertEqual(self.run_line("plain words")[1], i18n._("sent"))
        self.assertEqual(self.run_line("#zzz as a post", unknown_as_post=True)[1],
                         i18n._("sent"))

    def test_an_unknown_kind_on_a_post_does_nothing(self):
        from fedtail.core.commands import Command
        with mock.patch.object(commands, "parse",
                                        return_value=Command("weird", "abc")):
            self.assertIsNone(self.run_line("whatever")[0])


if __name__ == "__main__":
    unittest.main()


class OnlyCountsTest(unittest.TestCase):
    """A refresh with new likes and boosts: only the row of buttons is made again."""

    def test_only_counts_differ(self):
        from fedtail.model import Counts
        from tests.fakes import BOB, status
        p = to_post(status("1", BOB, text="hi"))
        liked = dataclasses.replace(p, counts=Counts(likes=3),
                                    mine=dataclasses.replace(p.mine, liked=True))
        edited = dataclasses.replace(p, text="<p>other</p>")
        self.assertTrue(cardtext.only_counts_differ(p, liked))
        self.assertFalse(cardtext.only_counts_differ(p, p))
        self.assertFalse(cardtext.only_counts_differ(p, edited))
        self.assertFalse(cardtext.only_counts_differ(
            p, dataclasses.replace(edited, counts=Counts(likes=3))))
        share = Share(Ref("mastodon", "t", "s1"), p.author, p, None, "1")
        self.assertTrue(cardtext.only_counts_differ(share, dataclasses.replace(share,
                                                                               post=liked)))
        self.assertFalse(cardtext.only_counts_differ(share, liked))
        self.assertFalse(cardtext.only_counts_differ(
            share, Share(Ref("mastodon", "t", "s2"), p.author, liked, None, "1")))
