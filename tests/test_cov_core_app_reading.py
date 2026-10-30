"""Reading in the core (core/app.py) at its edges: finding in a lane and everywhere,
parents and my replies when the server stumbles, threads completed from other servers,
nodeinfo, honest counters and my other accounts — someone else's server failing never
breaks the reading here."""

import time
import unittest
from unittest import mock

from fedtail.core import auth, paths
from fedtail.protocols.mastodon.api import ApiError

from .fakes import BOB, ME, NEWS, status
from .test_cov_core_app_poll import CoreCase, boom

T = 10


class FindTest(CoreCase):
    user = {"lanes": {"posts_only": ["home"]}}

    def test_deep_find(self):
        c = self.connect()
        self.w.add(status("011", BOB, "010", "B", minute=11, text="найди меня"), home=True)
        self.w.add(status("012", NEWS, minute=12, text="найди бота"), home=True)
        c.poll_once()
        self.assertEqual(c.deep_find("nope", "x").result(timeout=T),
                         {"total": 0, "more": False})
        got = c.deep_find("home", "найди").result(timeout=T)
        self.assertEqual(got["total"], 0)  # the reply: posts only; the bot: not home's

    def test_find_everywhere_skips_the_silenced_and_old_boosts(self):
        c = self.connect()
        self.w.add(status("013", BOB, minute=13, text="тихо"), home=True)
        c.poll_once()
        with mock.patch.object(c, "silenced", lambda st: st["id"] == "013"):
            got = c.find_everywhere("тихо").result(timeout=T)
        self.assertEqual(got, [])
        rows = [(str(i), {"id": str(i), "reblog": {"id": "R"}}) for i in range(3)]
        with mock.patch.object(c.store, "first_seen", return_value={"R": "0"}):
            kept = list(c._without_repeats("home", rows, chunk=2))
        self.assertEqual([i for i, _s in kept], ["0"])


class ParentsTest(CoreCase):
    def test_lookups_and_failures(self):
        c = self.connect()
        c.poll_once()
        self.assertIsNone(c.parent_of({"id": "x", "in_reply_to_id": "unknown"}))
        self.assertEqual(c.parents_for([{"id": "x", "in_reply_to_id": "unknown"}]),
                         {"x": None})
        self.assertIsNone(c.resolve_alias("zzz"))
        with mock.patch.object(c, "me", None):
            self.assertEqual(c.my_replies([{"id": "010"}]), {})
        c.api.context = boom()
        c._check_my_replies([("010", 3)])  # tried again next time
        self.assertIsNone(c.store.kv_get("replies_checked:010"))
        c.api.status = boom(OSError("hiccup"))
        c._fetch_parents([{"id": "y", "in_reply_to_id": "p"}])
        self.assertFalse(c.store.is_missing("p"))  # not marked missing: tried again later
        self.assertEqual(c.load_older("activity").result(timeout=T), 0)  # no source

    def test_older_ahead_is_the_cores_call(self):
        """reading.older_ahead: the end of a lane in sight asks the core; it fetches only
        with the setting on, one page at a time, and stops after a page brought nothing."""
        from concurrent.futures import Future
        c = self.connect()
        c.poll_once()
        self.assertIsNone(c.older_ahead("home"))  # off by default
        c.cfg["feed"]["older_ahead"] = True
        self.assertIsNone(c.older_ahead("no such lane"))
        waiting = Future()
        with mock.patch.object(c, "load_older", return_value=waiting) as asked:
            self.assertIs(c.older_ahead("home"), waiting)
            self.assertIsNone(c.older_ahead("home"))  # one on its way already
            waiting.set_result(5)
            self.assertIsNotNone(c.older_ahead("home"))  # done, more came: on
            self.assertEqual(asked.call_count, 2)
        empty = Future()
        with mock.patch.object(c, "load_older", return_value=empty):
            self.assertIs(c.older_ahead("home"), empty)
            empty.set_result(0)  # nothing older
            self.assertIsNone(c.older_ahead("home"))  # asked no more
        self.assertIsInstance(c.load_older("home").result(timeout=T), int)  # the button may

    def test_warm_lanes_survives_a_lane(self):
        c = self.connect()
        with mock.patch.object(c, "unread_count", boom()):
            c._warm_lanes()

    def test_a_background_event_after_a_change_counts_the_lanes_first(self):
        # 26.10: a thread loaded in the background changed the stored posts, and the
        # window recounted every lane itself on the next event (freezes of 300–600 ms)
        import threading
        c = self.connect()
        c.poll_once()
        warmed = []
        with mock.patch.object(c, "_warm_lanes", lambda: warmed.append(1)):
            c.emit("lanes_updated", {})           # nothing changed since the poll
            self.assertEqual(warmed, [])
            c.store.status_version += 1           # a thread came in
            c.emit("nothing_here", None)          # the window's own act: not here
            self.assertEqual(warmed, [])
            t = threading.Thread(target=c.emit, args=("thread_loaded", None))
            t.start()
            t.join()
            self.assertEqual(warmed, [1])

    def test_target_by_number(self):
        c = self.connect()
        self.w.add(status("020", BOB, minute=20), home=True)
        self.w.add(status("021", NEWS, "020", "B", minute=21, text="первый"), home=True)
        c.poll_once()
        alias = c.short_ids([c.store.get_status("020")])["020"]
        got = c.target(alias, 1).result(timeout=T)
        self.assertEqual(got["id"], "021")
        self.assertIsNone(c.target(alias, 9).result(timeout=T))


class CompletingTest(CoreCase):
    def test_async_refresh_and_resolving_fail_quietly(self):
        c = self.connect()
        c.api.async_refresh = boom()
        c._stop.wait = lambda s: False
        c._await_refresh("010", "R", 1, budget=5)
        root = dict(status("030", BOB, minute=30), uri="https://far.test/1",
                    visibility="public")
        c._origin_json = lambda url: {"replies": {"items": ["https://far.test/2"]}} \
            if url.endswith("/1") else {}
        c.api.search = boom()
        c._complete_thread(root, {"https://far.test/1"})

    def test_origin_requests_go_without_the_token(self):
        c = self.connect()
        with mock.patch("fedtail.core.remote.get_json", return_value={"ok": 1}) as get:
            type(c)._origin_json(c, "https://far.test/x")
            type(c)._origin_get(c, "https://far.test/y")
        for call in get.call_args_list:
            self.assertNotIn("Authorization", call.kwargs["headers"])
            self.assertEqual(call.kwargs["own_hosts"], {"example.test"})
        self.assertIn("activity+json", get.call_args_list[0].kwargs["headers"]["Accept"])


class NodeinfoTest(CoreCase):
    def test_failure_and_the_cache_cap(self):
        c = self.connect()
        with mock.patch.object(c, "_origin_get", boom()):
            self.assertEqual(c.server_software("down.test").result(timeout=T), "")
        old = {f"h{i}.test": (i, "x") for i in range(2001)}
        c.store.kv_set("nodeinfo", old)
        with mock.patch.object(c, "_origin_get", return_value={}):
            c.server_software("new.test").result(timeout=T)
        self.assertEqual(len(c.store.kv_get("nodeinfo")), 1000)


class CountersTest(CoreCase):
    def test_honest_counts_edges(self):
        c = self.connect()
        mine_here = dict(status("040", BOB, minute=40), uri="https://example.test/s/40",
                         visibility="public")
        far = dict(status("041", BOB, minute=41), uri="https://far.test/users/b/statuses/41",
                   visibility="public")
        with mock.patch.object(c, "_origin_get", boom()), \
                mock.patch.object(c, "_counts_via_accounts", return_value=None) as via:
            c._honest_counts([mine_here, far])
        via.assert_called_once()  # only the post from elsewhere is asked about

    def test_other_accounts(self):
        import os
        env = {"XDG_CONFIG_HOME": str(self.tmp / "cfg"), "XDG_DATA_HOME": str(self.tmp / "data")}
        with mock.patch.dict(os.environ, env):
            for name, token in (("work", "T2"), ("blank", "")):
                w = paths.resolve(name)
                w.ensure()
                auth.save(w.auth_file, {"server": "https://work.test/", "token": token})
            lone = paths.resolve("lone")  # a profile never logged in
            lone.ensure()
            lone.config_file.write_text("[ui]\n", "utf-8")
            c = self.connect()
            self.assertEqual(c._other_accounts(), [("https://work.test", "T2")])
            with mock.patch("fedtail.core.profiles.listing", boom()):
                self.assertEqual(c._other_accounts(), [("https://work.test", "T2")])  # kept
                c._others_cache = (time.monotonic() - 700, [])
                self.assertEqual(c._other_accounts(), [])

    def test_counts_via_accounts_errors(self):
        """My other accounts' servers, asked through the protocol's client — each token
        to its own server: one down, one that has another post — nothing taken; one with
        the very post — its counts."""
        import requests
        c = self.connect()
        st = dict(status("042", BOB, minute=42), uri="https://far.test/users/b/statuses/42")
        c._other_accounts = lambda: [("https://far.test", "T1"), ("https://other.test", "T2")]
        made = []

        class Client:
            def __init__(self, server, token):
                made.append((server, token))
                self.server = server

            def status(self, sid):
                assert sid == "42"
                raise requests.ConnectionError("down")

            def search_statuses(self, q, limit=40):
                return [{"uri": "else"}]
        c.api_class = Client  # how the core makes its clients (tests give their own)
        self.assertIsNone(c._counts_via_accounts(st, "https://far.test/api/v1/statuses/42"))
        self.assertEqual(made, [("https://far.test", "T1"), ("https://other.test", "T2")])
        Client.search_statuses = lambda self, q, limit=40: [
            {"uri": q, "favourites_count": 7, "reblogs_count": 1}]
        got = c._counts_via_accounts(st, "https://far.test/api/v1/statuses/42")
        self.assertEqual(got["favourites_count"], 7)


class MoreTest(CoreCase):
    def test_marks_then_the_counts_made_in_the_core(self):
        """30.10: each read mark had the window count every lane itself (330 ms). The
        cards hear at once (read_changed); the numbers once the core made them anew
        in its read thread (counts_ready) — found made, then."""
        c = self.connect()
        c.mark_read(["010"])
        self.assertIn(("read_changed", ["010"]), self.events)  # the cards: at once
        c.reads.submit(lambda: None).result(timeout=T)  # its thread done
        self.assertIn(("counts_ready", None), self.events)
        warmed = c.__dict__.get("_unread_cache", {})
        self.assertTrue(warmed)  # made already: the window only reads them

    def test_me_my_replies_found_marks_read(self):
        c = self.connect()
        mine = status("051", ME, "050", "B", minute=51, text="мой ответ")
        c.api.context = lambda sid: {"descendants": [mine]}
        c._check_my_replies([("050", 1)])
        self.assertIn(("read_changed", ["050"]), self.events)
        c.api.status = boom(ApiError(404, "gone"))
        c._fetch_parents([{"id": "y", "in_reply_to_id": "p2"}])
        self.assertTrue(c.store.is_missing("p2"))


if __name__ == "__main__":
    unittest.main()
