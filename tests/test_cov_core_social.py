"""core/social.py when the server answers badly: relationships, mutuals, people found
on the post's own server, muting a thread, conversations, notifications and
interaction requests — an error in one part leaves the rest done, and only the
answers that mean "no such thing here" mark a feature unsupported."""

import time
import unittest
from unittest import mock

from fedtail.core import auth, config, paths
from fedtail.core.app import Core
from fedtail.core.social import NotSupported
from fedtail.protocols.mastodon.api import ApiError

from . import fakes
from .fakes import BOB, FakeApi, status
from .test_core import TmpDir

T = 10


def boom(status=500):
    def fn(*_a, **_k):
        raise ApiError(status, "boom")
    return fn


def wait_for(cond, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


class SocialErrorsTest(TmpDir):
    def setUp(self):
        super().setUp()
        FakeApi.world = self.w = fakes.World()
        self.w.add(status("010", BOB, minute=10, text="пост"), home=True)
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False,
                                           "complete_threads": False}})
        p = paths.resolve("t", config=str(self.tmp / "c.toml"), data=str(self.tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        self.core = Core(cfg, p, api_class=FakeApi)
        self.core._origin_json = lambda url: None
        self.addCleanup(self.core.shutdown)
        self.core.connect().result(timeout=T)
        self.core.poll_once()
        self.events = []
        self.core.events.on("*", lambda n, pl: self.events.append(n))
        self.core.sync = mock.Mock()

    def test_api_errors_that_dont_mean_unsupported(self):
        c = self.core
        with self.assertRaises(ApiError):
            c._api("trends_tags", boom(500))
        self.assertTrue(c.supports("trends_tags"))
        with self.assertRaises(NotSupported):
            c._api("trends_tags", boom(404))
        self.assertFalse(c.supports("trends_tags"))
        self.assertIn("unsupported", self.events)

    def test_relationships_failing_leave_the_people(self):
        self.core.api.relationships = boom()
        got = self.core._with_relations([BOB])
        self.assertEqual(got, {"accounts": [BOB], "relations": {}})

    def test_mutuals_without_me_and_with_a_failing_page(self):
        c = self.core
        with mock.patch.object(c, "me", None):
            self.assertEqual(c.refresh_mutuals().result(timeout=T), [])
        c.api.following = lambda me, max_id=None: ([BOB], None)
        c.api.relationships = boom()
        self.assertEqual(c.refresh_mutuals(force=True).result(timeout=T), [])

    def test_people_on_the_posts_own_server(self):
        c = self.core
        st = dict(status("020", BOB, minute=20), uri="https://social.example/statuses/20",
                  url="https://social.example/@bob/20", visibility="public")
        c._origin_get = lambda url: [{"acct": "ann"}, {"acct": "cid@far.test"}]
        found = []

        def search(q, **_k):
            found.append(q)
            if q == "@ann@social.example":
                raise ApiError(500, "boom")
            return {"accounts": [dict(BOB, id="C", acct="cid@far.test")]}
        c.api.search = search
        res, _n = c.who_reacted_from_origin(st, "favourited_by").result(timeout=T)
        self.assertEqual(found, ["@ann@social.example", "@cid@far.test"])
        self.assertEqual([a["id"] for a in res["accounts"]], ["C"])
        self.assertEqual(res["total"], 2)

    def test_mute_thread_when_the_server_refuses(self):
        c = self.core
        c.api.mute_conversation = boom(403)
        st = c.mute_thread(c.store.get_status("010")).result(timeout=T)
        self.assertTrue(st["muted"])  # muted here all the same
        c.sync.record_thread.assert_called_with("010", "muted")
        c.mute_thread(c.store.get_status("010"), False).result(timeout=T)
        c.sync.record_thread.assert_called_with("010", "left")

    def test_conversations(self):
        c = self.core
        c.caps.learn("conversations", False)
        c.api.conversations = lambda *_a: self.fail("asked a server without them")
        c.sync_conversations()
        c.caps.learn("conversations", True)
        asked = []

        def read(cid):
            asked.append(cid)
            raise ApiError(500, "boom")
        c.api.read_conversation = read
        c._conv_of = {"5": ("c1", True), "6": ("c2", False)}
        c._read_conversations(["5", "6", "7"])
        self.assertTrue(wait_for(lambda: asked == ["c1"]))
        self.assertEqual(c._conv_of["5"], ("c1", False))

    def test_dismissing(self):
        c = self.core
        c.store.activity_put([{"id": "n1", "type": "favourite", "account": BOB,
                               "created_at": "2026-01-01T00:00:00Z",
                               "_group": {"key": "g1", "count": 3, "accounts": []}},
                              {"id": "n2", "type": "follow", "account": BOB,
                               "created_at": "2026-01-01T00:00:01Z"}])
        c.caps.learn("grouped", True)
        c.api.dismiss_notification_group = boom()
        c.dismiss_activity("n1").result(timeout=T)
        c.api.dismiss_notification = boom(404)
        c.dismiss_activity("n2").result(timeout=T)  # can't, on the server: here it goes
        self.assertFalse(c.supports("dismiss_one"))
        self.assertEqual(c.sync.record_activity.call_count, 2)
        with c.store.lock:
            left = c.store.db.execute("SELECT COUNT(*) FROM activity").fetchone()[0]
        self.assertEqual(left, 0)

    def test_answering_an_interaction(self):
        c = self.core
        entry = {"id": "n9", "type": "pending.reply", "account": BOB,
                 "status": {"id": "r1"}}
        self.w.interactions = [{"id": "q1", "account": BOB, "reply": {"id": "r1"}}]
        c.api.answer_interaction = boom(404)  # answered elsewhere already
        c.api.dismiss_notification = boom(500)
        self.assertFalse(c.answer_interaction(entry, True).result(timeout=T))
        c.sync.record_activity.assert_called()
        c.api.answer_interaction = boom(500)
        with self.assertRaises(ApiError):
            c.answer_interaction(entry, True).result(timeout=T)

    def test_server_info_with_a_missing_page(self):
        c = self.core
        c.api.instance_rules = boom()
        c.api.instance_page = boom(404)
        got = c.server_info().result(timeout=T)
        self.assertEqual((got["rules"], got["about"], got["privacy"]), ([], "", ""))

    def test_probe(self):
        c = self.core
        self.assertIsNone(c.last_probe())
        with mock.patch("fedtail.protocols.mastodon.probe.run",
                        return_value={"x": 1}), \
                mock.patch("fedtail.protocols.mastodon.probe.features",
                           return_value={"trends_links": False}):
            self.assertEqual(c.probe_server().result(timeout=T), {"x": 1})
        self.assertEqual(c.last_probe(), {"x": 1})
        self.assertFalse(c.supports("trends_links"))


if __name__ == "__main__":
    unittest.main()
