"""core.view.View: any core method's answer comes back as the model, and the model goes
in as what the core takes."""

import unittest
from concurrent.futures import Future

from fedtail.core.view import View
from fedtail.model import Account, Activity, Post, Relationship, Share, ThreadItem
from fedtail.protocols.mastodon import adapter

from .fakes import BOB, ME, status


class _Store:
    def __init__(self, statuses):
        self.statuses = {s["id"]: s for s in statuses}

    def get_status(self, sid):
        return self.statuses.get(sid)


class _Paths:
    profile = "main"


class FakeCore:
    """Methods shaped like the core's, recording what they were given."""

    def __init__(self):
        self.store = _Store([status("1", BOB, text="one"), status("2", ME, text="two")])
        self.paths = _Paths()
        self.me = ME
        self.got = []

    def people(self, acc_id, which, max_id=None):
        f = Future()
        f.set_result(({"accounts": [BOB], "relations": {"B": {"id": "B", "following": True,
                                                                "followed_by": False}}}, "n2"))
        return f

    def pinned(self, acc_id):
        return [status("3", BOB, text="pinned")] + [dict(status("4", ME),
                                                          reblog=status("5", BOB))]

    def activity_entries(self, limit=300):
        return [{"id": "n1", "type": "favourite", "account": dict(BOB),
                 "status": status("2", ME), "sort": "2099|0001",
                 "created_at": "2099-10-14T10:00:00.000Z"},
                {"id": "n2", "type": "severed_relationships", "status": None,
                 "account": dict(BOB, _notice={"type": "domain_block",
                                               "target_name": "bad.example"}),
                 "sort": "2099|0002", "created_at": "2099-10-14T10:01:00.000Z"}]

    def followed_among(self, accounts):
        self.got.append(accounts)
        return [a for a in accounts if a["id"] == "B"]

    def subscribe(self, st):
        self.got.append(st)
        return "root"

    def thread(self, sid):
        from fedtail.core.threads import Node
        f = Future()
        f.set_result([Node(status("1", BOB), 0, 0), Node(status("2", ME, "1"), 1, 1)])
        return f

    def server_info(self):
        return {"title": "My node", "rules": ["be nice"]}  # nothing of the model: as it is


class ViewTest(unittest.TestCase):
    def setUp(self):
        self.core = FakeCore()
        self.v = View(self.core)

    def test_nested_answers_come_back_as_the_model(self):
        page, nxt = self.v.people("B", "followers").result()
        self.assertIsInstance(page["accounts"][0], Account)
        self.assertEqual(page["accounts"][0].ref.profile, "main")
        rel = page["relations"]["B"]
        self.assertIsInstance(rel, Relationship)
        self.assertTrue(rel.following)
        self.assertEqual(nxt, "n2")

    def test_statuses_and_boosts(self):
        got = self.v.pinned("B")
        self.assertIsInstance(got[0], Post)
        self.assertIsInstance(got[1], Share)
        self.assertEqual(got[1].post.id, "5")

    def test_activity_keeps_the_cores_order_and_notices(self):
        a, b = self.v.activity()
        self.assertIsInstance(a, Activity)
        self.assertEqual((a.kind, a.sort, a.post.id), ("like", "2099|0001", "2"))
        self.assertEqual((b.kind, b.notice), ("notice", "domain_block bad.example"))

    def test_the_model_goes_in_as_the_core_takes_it(self):
        bob = self.v.acc(BOB)
        got = self.v.followed_among([bob])
        self.assertIs(self.core.got[-1][0], BOB)  # the very dict it came from
        self.assertEqual(got[0].handle, "bob@social.example")
        post = self.v.entry(self.core.store.statuses["1"])
        self.v.subscribe(post)
        self.assertIs(self.core.got[-1], self.core.store.statuses["1"])
        stranger = adapter.account({"id": "S", "acct": "s@x.example", "username": "s"})
        self.v.followed_among([stranger])
        self.assertEqual(self.core.got[-1][0]["acct"], "s@x.example")  # rebuilt

    def test_thread_nodes(self):
        items = self.v.thread("1").result()
        self.assertTrue(all(isinstance(i, ThreadItem) for i in items))
        self.assertEqual([(i.post.id, i.depth, i.number) for i in items],
                         [("1", 0, 0), ("2", 1, 1)])

    def test_other_shapes_pass_and_the_store_stays_inside(self):
        self.assertEqual(self.v.server_info()["title"], "My node")
        with self.assertRaises(AttributeError):
            self.v.store  # noqa: B018
        with self.assertRaises(AttributeError):
            self.v.no_such_thing  # noqa: B018


if __name__ == "__main__":
    unittest.main()
