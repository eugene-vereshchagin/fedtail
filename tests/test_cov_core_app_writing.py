"""Writing in the core (core/app.py) when the server stumbles: a chain whose second part
fails, a post out but its bookkeeping failing, a lost answer that can't be checked,
sources and pins the server can't give, a redraft without its source — and the
federation status and the exit."""

import unittest
from unittest import mock

import requests

from fedtail.core.writing import MaybeSent
from fedtail.protocols.mastodon.api import ApiError

from .fakes import BOB, ME, status
from .test_cov_core_app_poll import CoreCase, boom

T = 10


class PostTest(CoreCase):
    user = {"post": {"quote_policy": "followers"}}

    def test_chain_with_a_failing_part(self):
        c = self.connect()
        real_post = c.api.post_status
        calls = []

        def post_status(text, *a, **k):
            calls.append(text)
            if len(calls) == 2:
                raise ApiError(422, "too fast")
            return real_post(text, *a, **k)
        c.api.post_status = post_status
        st = c.post("первый\n---\nвторой\n---\nтретий", "public").result(timeout=T)
        self.assertEqual(st["chain"], 1)
        self.assertEqual(calls, ["первый", "второй"])
        self.assertTrue(any("1 / 3" in str(p) for n, p in self.events if n == "error"))
        self.assertEqual(self.w.extras[0]["quote_policy"], "followers")

    def test_scheduled_drops_its_draft(self):
        c = self.connect()
        c.store.save_draft("new", {"text": "позже"})
        st = c.post("позже", "public", draft_key="new",
                    scheduled_at="2030-01-01T00:00:00Z").result(timeout=T)
        self.assertTrue(st["scheduled"])
        self.assertIsNone(c.store.get_draft("new"))

    def test_bookkeeping_failing_never_fails_the_post(self):
        c = self.connect()
        with mock.patch.object(c, "mark_read", boom()), \
                self.assertLogs("fedtail.core.app", "ERROR"):
            st = c.post("вышло", "public").result(timeout=T)
        self.assertEqual(self.w.posted[-1][0], "вышло")
        self.assertTrue(st["id"])

    def test_a_lost_answer_that_cant_be_checked(self):
        c = self.connect()
        self.w.send_timeouts, self.w.send_lands = 1, False
        c.api.account_statuses = boom(requests.ConnectionError("down"))
        with self.assertRaises(MaybeSent):
            c.post("потерялось", "public").result(timeout=T)
        with mock.patch.object(c, "me", None):
            self.assertIsNone(c._find_sent("x", None, 0))


class PostsTest(CoreCase):
    def test_source_vote_pins_redraft_follow(self):
        c = self.connect()
        c.poll_once()
        mine = c.post("мой", "public").result(timeout=T)
        c.api.status_source = boom(ApiError(404, "no source"))
        src = c.source(mine).result(timeout=T)
        self.assertEqual(src["text"], "мой")
        with self.assertRaises(ValueError):
            c.vote(mine, [0])
        st = c.redraft(mine).result(timeout=T)
        self.assertEqual(st["text"], "мой")
        c.follow_requests = [BOB]
        c.answer_follow("B", False).result(timeout=T)
        self.assertEqual(c.follow_requests, [])

    def test_pins_from_their_server(self):
        c = self.connect()
        c.api.account = boom(ApiError(404, "gone"))
        self.assertEqual(c._pinned_from_origin("X"), [])
        far = dict(BOB, acct="far@far.test", uri="https://far.test/users/far")
        c.api.account = lambda acc_id: far
        c._origin_json = boom()
        self.assertEqual(c._pinned_from_origin("X"), [])
        c._origin_json = lambda url: {"featured": {"items": ["https://far.test/p1",
                                                             "https://far.test/p2"]}}
        c.api.search = lambda q, **k: (_ for _ in ()).throw(ApiError(500, "x")) \
            if q.endswith("p1") else {"statuses": [dict(status("070", BOB), uri=q)]}
        got = c._pinned_from_origin("X")
        self.assertEqual([(s["id"], s["pinned"]) for s in got], [("070", True)])


class StatusAndExitTest(CoreCase):
    def test_federation_status_with_waiting_people_and_a_stream(self):
        c = self.connect()
        import time
        c.store.kv_set("list_pending", [["L1", "Q", time.time()]])
        c.api.relationships = boom()
        c.api.account = boom()
        stream = mock.Mock(opened_at=1, last_event_at=2, drops=0, last_error="")
        stream.connected.is_set.return_value = True
        c._stream = stream
        got = c.federation_status().result(timeout=T)
        self.assertEqual(got["list_waiting"][0]["state"], "unknown")
        self.assertTrue(got["stream"]["open"])
        c._stream = None

    def test_filtered_without_a_policy(self):
        c = self.connect()
        c.caps.learn("notification_policy", False)
        self.assertIsNone(c.filtered().result(timeout=T))

    def test_exit_with_a_poll_still_running(self):
        c = self.connect()
        lock = c._poll_lock
        c._poll_lock = mock.Mock(acquire=mock.Mock(return_value=False))  # a poll holds it
        try:
            with self.assertLogs("fedtail.core.app", "INFO") as logs:
                c.shutdown()
        finally:
            c._poll_lock = lock
            c.store.close()
        self.assertTrue(any("not waited for" in x for x in logs.output))


class MeTest(CoreCase):
    def test_my_own_post_by_alias(self):
        c = self.connect()
        self.w.add(status("080", ME, minute=8), home=True)
        c.poll_once()
        alias = c.short_ids([c.store.get_status("080")])["080"]
        self.assertEqual(c.by_alias(alias)["id"], "080")


if __name__ == "__main__":
    unittest.main()
