"""Threads beyond the happy path: replies read from other servers when those servers
misbehave (core/replies.py), and followed threads (core/subs.py) when the server is gone,
offline, refusing or out of budget."""

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from fedtail.core import replies, subs
from fedtail.core.store import Store
from fedtail.protocols.base import Budget
from fedtail.protocols.mastodon.api import ApiError

B = "https://far.example/"


class Docs(dict):
    """get_json over a dict; a value that is an exception is raised."""

    def __call__(self, url):
        v = self[url]
        if isinstance(v, Exception):
            raise v
        return v


class RepliesTest(unittest.TestCase):
    def test_collection_pages_by_address_and_bad_pages(self):
        docs = Docs({B + "c": {"first": B + "p1"},
                     B + "p1": {"items": [B + "1", {"id": B + "2"}, 5, "mailto:x"],
                                "next": B + "p2"},
                     B + "p2": "not a page"})
        self.assertEqual(replies.collection_items(docs, B + "c"), [B + "1", B + "2"])
        self.assertEqual(replies.collection_items(docs, {"items": []}), [])

    def test_reply_walk_survives_broken_servers(self):
        docs = Docs({
            B + "root": {"replies": {"items": [B + "a", B + "b", B + "c", B + "d"]}},
            B + "a": RuntimeError("down"),           # its server is down
            B + "b": {"replies": B + "bad-coll"},     # its collection is broken
            B + "bad-coll": ValueError("garbage"),
            B + "c": "not an object",
            B + "d": {"replies": {"items": [B + "root", B + "e"]}},
            B + "e": {}})
        got = replies.reply_uris(docs, B + "root")
        self.assertEqual(got, [B + "a", B + "b", B + "c", B + "d", B + "e"])
        self.assertEqual(replies.reply_uris(docs, B + "root", limit=2), [B + "a", B + "b"])

    def test_context_collection_failures(self):
        docs = Docs({B + "x": OSError("down")})
        self.assertEqual(replies.context_uris(docs, B + "x"), [])
        docs = Docs({B + "y": {"context": B + "ctx"}, B + "ctx": OSError("down")})
        self.assertEqual(replies.context_uris(docs, B + "y"), [])
        docs = Docs({B + "z": {"context": B + "ctx"},
                     B + "ctx": {"type": "OrderedCollection",
                                 "orderedItems": [{"type": "Create", "object": B + "1"}],
                                 "first": B + "p1"},
                     B + "p1": OSError("timeout")})
        self.assertEqual(replies.context_uris(docs, B + "z"), [B + "1"])  # what it got
        docs = Docs({B + "w": {"context": {"type": "Collection", "items": [B + "2"],
                                           "first": 42}}})
        self.assertEqual(replies.context_uris(docs, B + "w"), [B + "2"])


def st(i, minute=0, parent=None, acc="A"):
    return {"id": i, "in_reply_to_id": parent, "account": {"id": acc},
            "created_at": f"2026-01-01T00:{minute:02d}:00.000Z", "content": i}


class Api:
    def __init__(self, contexts=None, error=None, budget=None):
        self.contexts = contexts or {}
        self.error = error
        self.asked = []
        if budget is not None:
            self.budget = budget

    def context(self, sid):
        self.asked.append(sid)
        if self.error is not None:
            raise self.error
        return self.contexts.get(sid, {"ancestors": [], "descendants": []})


class SubsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.store = Store(Path(self._tmp.name) / "s.db")
        self.addCleanup(self.store.close)

    def test_unsubscribe_by_a_member(self):
        root, reply = st("r"), st("x", 1, "r")
        root_id = subs.subscribe(self.store, Api({"x": {"ancestors": [root],
                                                        "descendants": []}}), reply)
        self.assertEqual(root_id, "r")
        self.assertEqual(subs.unsubscribe(self.store, "x"), "r")
        self.assertIsNone(self.store.sub_root_of("x"))

    def test_leave_offline_goes_by_what_it_knows(self):
        post = st("p", 1, "q")
        root = subs.leave(self.store, Api(error=OSError("offline")), post, quiet=True)
        self.assertEqual(root, "p")
        self.assertIn("p", self.store.quiet_roots(False))

    def test_silenced_asks_the_server_where_the_chain_breaks(self):
        self.store.quiet_set("root")
        self.store.left_add("root", ["root"])
        mention = st("m", 5, "gap")
        api = Api({"m": {"ancestors": [st("root"), st("gap", 1, "root")]}})
        self.assertEqual(subs.silenced(self.store, api, mention, False), "root")
        # the chain breaks on a parent that is itself the root
        self.assertEqual(subs.silenced(self.store, Api(), st("n", 6, "root"), False), "root")
        # the server can't say: not silenced
        lone = st("k", 7, "unknown")
        self.assertIsNone(subs.silenced(self.store, Api(error=OSError("x")), lone, False))
        # a parent whose id names a left thread's root without being stored
        self.store.quiet_set("other")
        self.assertEqual(subs.silenced(self.store, Api(), st("j", 8, "other"), False),
                         "other")

    def test_every_and_naive_times(self):
        now = datetime(2026, 1, 3, tzinfo=UTC)
        self.assertEqual(subs.every("2026-01-01T00:00:00", now, 5), timedelta(minutes=60))
        self.assertEqual(subs.every("garbage", now, 5), timedelta(minutes=5))

    def follow(self, root="r"):
        old = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        self.store.put_statuses([st(root)])
        self.store.sub_add(root, "", old, False, [root])
        self.store.sub_checked(root, old, "", [])

    def test_check_when_the_budget_is_spent(self):
        self.follow()
        api = Api(budget=Budget(300, 3, datetime.now(UTC).timestamp() + 600))
        self.assertEqual(subs.check(self.store, api, "ME", 5, 30, 10), [])
        self.assertEqual(api.asked, [])

    def test_check_errors(self):
        self.follow("gone")
        self.assertEqual(subs.check(self.store, Api(error=ApiError(404, "gone")), "ME", 5,
                                    30, 10), [])
        self.assertIsNone(self.store.sub_root_of("gone"))
        self.follow("refused")
        with self.assertRaises(ApiError):
            subs.check(self.store, Api(error=ApiError(429, "slow down")), "ME", 5, 30, 10)
        api = Api(error=ApiError(500, "oops"))
        self.assertEqual(subs.check(self.store, api, "ME", 5, 30, 10), [])
        self.assertEqual(api.asked, ["refused"])
        # marked checked: not asked again at once
        api = Api(error=ApiError(500, "oops"))
        subs.check(self.store, api, "ME", 5, 30, 10)
        self.assertEqual(api.asked, [])

    def test_budget_share(self):
        api = SimpleNamespace(budget=Budget(300, 100, 1.0))
        self.assertEqual(subs.budget_share(api, 10, now=2.0), 10)  # the window is over


if __name__ == "__main__":
    unittest.main()
