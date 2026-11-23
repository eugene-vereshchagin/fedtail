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

    def test_a_post_answered_is_read_unless_told_otherwise(self):
        """reading.replied_is_read: the post I answer counts as read (it was nailed in);
        false — it stays unread."""
        c = self.connect()
        self.w.add(status("050", BOB, minute=1, vis="public"), home=True)
        self.w.add(status("051", BOB, minute=2, vis="public"), home=True)
        c.poll_once()
        self.assertEqual(c.store.read_set(["050", "051"]), set())
        c.post("ответ", "public", reply_to="050").settled.result(timeout=T)
        self.assertEqual(c.store.read_set(["050", "051"]), {"050"})
        c.cfg["read"]["replied_is_read"] = False
        c.post("и тут", "public", reply_to="051").settled.result(timeout=T)
        self.assertEqual(c.store.read_set(["050", "051"]), {"050"})

    def test_a_scheduled_post_goes_with_its_key(self):
        """An answer lost and the post scheduled again made two waiting on the server:
        it goes with an Idempotency-Key, the same at the retry — and a new one once the
        first was cancelled."""
        c = self.connect()
        when = "2030-01-01T00:00:00Z"
        self.w.send_timeouts = 1
        with self.assertRaises(Exception) as e:
            c.post("позже", "public", scheduled_at=when).result(timeout=T)
        self.assertTrue(getattr(e.exception, "maybe_sent", False))
        st = c.post("позже", "public", scheduled_at=when).result(timeout=T)
        again = c.post("позже", "public", scheduled_at=when).result(timeout=T)
        keys = self.w.send_keys[-2:]
        self.assertTrue(keys[0])
        self.assertEqual(keys[0], keys[1])
        c.cancel_scheduled(st["id"]).result(timeout=T)
        c.post("позже", "public", scheduled_at=when).result(timeout=T)
        self.assertNotEqual(self.w.send_keys[-1], keys[0])
        self.assertTrue(again["scheduled"])

    def test_bookkeeping_failing_never_fails_the_post(self):
        c = self.connect()
        with mock.patch.object(c, "mark_read", boom()), \
                self.assertLogs("fedtail.core.app", "ERROR"):
            fut = c.post("вышло", "public")
            st = fut.result(timeout=T)
            fut.settled.result(timeout=T)
        self.assertEqual(self.w.posted[-1][0], "вышло")
        self.assertTrue(st["id"])

    def test_the_window_hears_before_the_bookkeeping(self):
        # 16.11: the editor stood open 3 s and more over a post already in the lanes —
        # the read marks and every lane counted anew went before the answer
        import threading
        c = self.connect()
        go = threading.Event()
        with mock.patch.object(c, "mark_read", lambda ids: go.wait(T)):
            fut = c.post("сразу", "public", draft_key="new")
            st = fut.result(timeout=T)
            self.assertFalse(fut.settled.done())
            self.assertEqual(c.store.get_status(st["id"])["id"], st["id"])
            go.set()
            self.assertEqual(fut.settled.result(timeout=T)["id"], st["id"])

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


class LaggingAnswerTest(CoreCase):
    """A server answering a boost or a like with its cached copy (GoToSocial: not yet
    "reblogged", the old count): the phone's ♻ stayed grey and the count stood, as if the
    tap did nothing (NOTES, 15.11). The core sets my mark and moves the count by one."""

    def test_boost_and_like_on_a_lagging_server(self):
        c = self.connect()
        w = self.w
        w.statuses["010"] = dict(w.statuses["010"], visibility="public",
                                 reblogs_count=3, favourites_count=2)
        c.store.put_statuses([w.statuses["010"]])
        stale = dict(w.statuses["010"])
        c.api.reblog = lambda sid, on=True: {"id": "rb", "reblog": dict(stale), "account": ME}
        c.api.favourite = lambda sid, on=True: dict(stale)
        got = c.boost(c.store.get_status("010")).result(timeout=T)
        self.assertTrue(got["reblogged"])
        self.assertEqual(got["reblogs_count"], 4)
        self.assertEqual(c.store.get_status("010")["reblogs_count"], 4)
        stale.update(reblogged=True, reblogs_count=4)  # the server lags the other way now
        got = c.boost(c.store.get_status("010")).result(timeout=T)
        self.assertFalse(got["reblogged"])
        self.assertEqual(got["reblogs_count"], 3)
        got = c.favourite(c.store.get_status("010")).result(timeout=T)
        self.assertTrue(got["favourited"])
        self.assertEqual(got["favourites_count"], 3)

    def test_a_server_that_counted_already(self):
        c = self.connect()
        c.store.put_statuses([dict(self.w.statuses["010"], reblogs_count=3)])
        fresh = dict(self.w.statuses["010"], reblogged=True, reblogs_count=4)
        c.api.reblog = lambda sid, on=True: {"id": "rb", "reblog": fresh, "account": ME}
        got = c.boost(c.store.get_status("010")).result(timeout=T)
        self.assertEqual(got["reblogs_count"], 4)  # not 5
