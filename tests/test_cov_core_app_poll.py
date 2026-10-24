"""The core's connect and poll (core/app.py) when parts of the server fail: each failing
part is said once and the rest of the round still happens; a refused token stops the
round; the poller never dies; markers, garbage collection and the live stream's address
fail softly."""

import threading
import time
import unittest
from concurrent.futures import Future
from unittest import mock

from fedtail.core import auth, config, paths
from fedtail.core.app import Core, Pool
from fedtail.protocols.base import Budget, Capabilities, RateLimited
from fedtail.protocols.mastodon.api import ApiError

from . import fakes
from .fakes import BOB, FakeApi, status
from .test_core import TmpDir

T = 10


def boom(exc=None):
    def fn(*_a, **_k):
        raise exc or RuntimeError("boom")
    return fn


class CoreCase(TmpDir):
    """A core connected to a fake server; `user` is the config to start from."""
    user = {}
    server = "https://example.test"

    def setUp(self):
        super().setUp()
        FakeApi.world = self.w = fakes.World()
        self.w.add(status("010", BOB, minute=10, text="пост"), home=True)
        user = {"feed": {"first_run_mark_read": False, "complete_threads": False}}
        for k, v in self.user.items():
            user.setdefault(k, {}).update(v)
        cfg, _ = config.validate(user)
        p = paths.resolve("t", config=str(self.tmp / "c.toml"), data=str(self.tmp / "d"))
        auth.save(p.auth_file, {"server": self.server, "token": "tok"})
        self.core = Core(cfg, p, api_class=FakeApi)
        self.core._origin_json = lambda url: None  # never another server
        self.core._origin_get = lambda url: None
        self.addCleanup(self.core.shutdown)
        self.events = []
        self.core.events.on("*", lambda n, pl: self.events.append((n, pl)))

    def connect(self):
        self.core.connect().result(timeout=T)
        return self.core

    def errors(self):
        return [str(p) for n, p in self.events if n == "error"]


class PoolTest(unittest.TestCase):
    def test_a_pool_refuses_only_when_shut_down(self):
        p = Pool(max_workers=1)
        p.shutdown()
        self.assertTrue(p.submit(lambda: 1).cancelled())
        p = Pool(max_workers=1)
        self.addCleanup(p.shutdown)
        with mock.patch("concurrent.futures.ThreadPoolExecutor.submit",
                        side_effect=RuntimeError("other")):
            with self.assertRaisesRegex(RuntimeError, "other"):
                p.submit(lambda: 1)


class ConnectTest(CoreCase):
    def test_call_api_before_connecting_and_repeated_errors(self):
        c = self.core
        with self.assertRaisesRegex(ApiError, "."):
            c.call_api("me").result(timeout=T)
        with mock.patch.object(type(c), "ERROR_QUIET_S", 600):
            for i in range(205):
                c.emit("error", f"e{i}")
        self.assertEqual(len(c._errors_seen), 4)  # cleared past 200

    def test_revoke_that_fails_is_only_logged(self):
        with mock.patch.object(FakeApi, "revoke", side_effect=OSError("offline")), \
                self.assertLogs("fedtail.core.app", "WARNING"):
            self.core._revoke({"server": "https://example.test", "token": "t"}, wait=True)

    def test_own_software_from_nodeinfo(self):
        c = self.core
        caps = Capabilities(software="mastodon", version="0.20.1", software_sure=False)
        bad = Future()
        bad.set_exception(OSError("down"))
        with mock.patch.object(c, "server_software", return_value=bad):
            c._own_software(caps)
        self.assertFalse(caps.software_sure)
        good = Future()
        good.set_result("GoToSocial 0.20.1")
        with mock.patch.object(c, "server_software", return_value=good):
            c._own_software(caps)
        self.assertEqual((caps.software, caps.software_sure), ("gotosocial", True))

    def test_connect_with_a_bad_instance_and_failing_lists(self):
        c = self.core
        c.store.kv_set("tag_groups", [{"any": ["a", "b"]}])
        with mock.patch.object(FakeApi, "instance", side_effect=OSError("no")), \
                mock.patch.object(c, "_refresh_lists", side_effect=OSError("lists down")), \
                self.assertLogs("fedtail.core.app", "WARNING") as logs:
            self.connect()
        self.assertTrue(any("lists" in x for x in logs.output))
        self.assertTrue(any(lane.name.startswith("tags:") for lane in c.lanes))
        self.assertIn("ready", [n for n, _p in self.events])

    def test_start_polling_once_and_sync(self):
        c = self.connect()
        c.sync = mock.Mock()
        with mock.patch.object(c, "_poll_loop"):
            c.start_polling()
            first = c._poller
            c.start_polling()
        self.assertIs(c._poller, first)
        c.sync.start.assert_called_once()


class HttpServerTest(CoreCase):
    server = "http://fedi.example.com"

    def test_plain_http_is_warned_and_has_no_stream(self):
        with self.assertLogs("fedtail.core.app", "WARNING") as logs:
            c = self.connect()
            c.api.has_stream = True
            c._start_stream()
        self.assertTrue(any("plain http" in x for x in logs.output))
        self.assertTrue(any("not https" in x for x in logs.output))
        self.assertIsNone(getattr(c, "_stream", None))


class PollLoopTest(CoreCase):
    def run_loop(self, c, rounds):
        """The loop with poll_once replaced by `rounds` (functions), stopped after them."""
        it = iter(rounds)

        def one():
            fn = next(it, None)
            if fn is None:
                c._stop.set()
                c._wake.set()
                return
            fn()
        c.cfg["poll"]["stream_gap_seconds"] = 0
        c.cfg["poll"]["interval_seconds"] = 0
        with mock.patch.object(c, "poll_once", one):
            t = threading.Thread(target=c._poll_loop)
            t.start()
            t.join(10)
        self.assertFalse(t.is_alive())

    def test_the_poller_survives_errors(self):
        c = self.connect()
        self.run_loop(c, [boom(RateLimited("slow", time.time() + 1)), boom(OSError("x")),
                          lambda: None])
        self.assertEqual(c._poll_failures, 1)
        self.assertIn("x", self.errors())

    def test_an_error_while_stopping_is_quiet(self):
        c = self.connect()

        def stopping():
            c._stop.set()
            raise OSError("closing")
        self.run_loop(c, [stopping])
        self.assertEqual(c._poll_failures, 0)

    def test_quiet_when_the_budget_is_spent(self):
        c = self.connect()
        paces = iter([0.01, 0])
        with mock.patch.object(c, "_pace", lambda: next(paces, 0)):
            self.run_loop(c, [lambda: None, lambda: None])

    def test_pace(self):
        c = self.connect()
        c.api.budget = Budget(300, 5, time.time() + 100)
        self.assertGreater(c._pace(), 90)
        self.assertIn("rate_limited", [n for n, _p in self.events])
        c.api.budget = Budget(300, 250, time.time() + 100)
        self.assertEqual(c._pace(), 0)


class PollErrorsTest(CoreCase):
    user = {"lanes": {"enabled": ["home", "local", "subs", "requests", "activity",
                                  "mentions", "direct"]}}

    def test_every_part_failing_leaves_the_rest(self):
        c = self.connect()
        c.poll_once()
        c._silence_checked = c._lists_checked = None
        c.set_active_lane("local")
        api = c.api
        with mock.patch.object(c, "_refresh_silence", boom()), \
                mock.patch.object(c, "_refresh_lists", boom(OSError("lists"))), \
                mock.patch("fedtail.core.subs.check", boom(OSError("subs"))), \
                mock.patch.object(c.sources["local"], "fetch", boom(OSError("local down"))), \
                mock.patch.object(api, "follow_requests", boom(OSError("req"))), \
                mock.patch.object(c, "_poll_activity", boom(OSError("act"))), \
                mock.patch.object(c.sources["home"], "fetch", boom(OSError("home down"))):
            c.poll_once()
        errs = " | ".join(self.errors())
        for part in ("home: home down", "lists: lists", "subs: subs", "local: local down",
                     "requests: req", "activity: act"):
            self.assertIn(part, errs)

    def test_a_refused_token_stops_the_round(self):
        c = self.connect()
        with mock.patch.object(c.sources["home"], "fetch", boom(ApiError(401, "token"))):
            c.poll_once()
        self.assertIn("auth_failed", [n for n, _p in self.events])
        with mock.patch.object(c.sources["home"], "fetch", boom(ApiError(500, "oops"))):
            c.poll_once()
        self.assertTrue(any("home" in e and "oops" in e for e in self.errors()))

    def test_an_empty_browse_lane_says_so(self):
        c = self.connect()
        c.set_active_lane("local")
        self.w.local = []
        c.poll_once()
        self.assertIn("local", c.browse_empty)
        self.assertIn(("lanes_updated", {"local": []}), self.events)

    def test_gc_failing_is_only_logged(self):
        c = self.connect()
        with mock.patch.object(c.store, "gc", boom()), \
                self.assertLogs("fedtail.core.app", "WARNING"):
            c.collect_garbage()


class MarkersTest(CoreCase):
    def test_markers_failing(self):
        c = self.connect()
        c.poll_once()
        c.cfg["read"]["sync_markers"] = False
        self.assertEqual(c._unread_by_marker([]), set())
        c._sync_markers()
        c.cfg["read"]["sync_markers"] = True
        with mock.patch.object(c.api, "markers", boom()):
            self.assertEqual(c._unread_by_marker([]), set())
            c._sync_markers()
        self.w.markers = {}
        self.assertEqual(c._unread_by_marker([]), set())  # no marker yet
        c.store.mark_read(["010"])
        with mock.patch.object(c.api, "set_markers", boom()), \
                self.assertLogs("fedtail.core.app", "INFO") as logs:
            c._sync_markers()
        self.assertTrue(any("can't set" in x for x in logs.output))


if __name__ == "__main__":
    unittest.main()
