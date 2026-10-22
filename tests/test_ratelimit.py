"""The server's rate limit: read from its answers, kept to — no request while it is
spent, the poller quiet until its window starts anew, and one word about it instead of
an error per lane."""

import json
import time
import unittest

from fedtail.protocols.base import Budget, RateLimited
from fedtail.protocols.mastodon.api import Api

from .fakes import FakeApi
from .test_roster import RosterTest


class _Resp:
    def __init__(self, status, headers, body=b"{}"):
        self.status_code, self.headers, self.content = status, headers, body
        self.text = body.decode()

    def json(self):
        return json.loads(self.content)


class _Session:
    headers = {}

    def __init__(self, answers):
        self.answers, self.asked = list(answers), 0

    def request(self, method, url, **kw):
        self.asked += 1
        return self.answers.pop(0)


def _limit(left, reset):
    return {"X-RateLimit-Limit": "300", "X-RateLimit-Remaining": str(left),
            "X-RateLimit-Reset": reset}


class BudgetTest(unittest.TestCase):
    def test_read_kept_and_429(self):
        soon = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 120))
        s = _Session([_Resp(200, _limit(5, soon)),
                      _Resp(429, _limit(0, soon), b'{"error": "rate limit reached"}')])
        api = Api("https://srv.example", "tok", session=s)
        api.get("/api/v1/timelines/home")
        self.assertEqual((api.budget.limit, api.budget.remaining), (300, 5))
        self.assertAlmostEqual(api.budget.reset, time.time() + 120, delta=5)
        with self.assertRaises(RateLimited) as e:
            api.get("/api/v1/timelines/home")
        self.assertAlmostEqual(e.exception.until, time.time() + 120, delta=5)
        with self.assertRaises(RateLimited):  # spent: the server isn't even asked
            api.get("/api/v1/timelines/home")
        self.assertEqual(s.asked, 2)
        self.assertEqual(api.requests, 2)

    def test_reset_forms(self):
        from fedtail.protocols.mastodon.api import _when_reset
        self.assertAlmostEqual(_when_reset("30"), time.time() + 30, delta=2)
        self.assertEqual(_when_reset("1900000000"), 1900000000)
        self.assertAlmostEqual(_when_reset(""), time.time() + 60, delta=2)
        b = Budget(300, 10, time.time() + 60)
        self.assertTrue(b.low(20))
        self.assertFalse(b.spent())
        self.assertFalse(Budget().low(20))  # the server didn't say: never "low"


class PaceTest(RosterTest):
    def test_quiet_until_the_window_and_said_once(self):
        core, _w = self.make()
        said, errors = [], []
        core.events.on("rate_limited", lambda _n, p: said.append(p))
        core.events.on("error", lambda _n, p: errors.append(p))
        self.assertEqual(core._pace(), 0)  # a fake server says nothing of a limit
        core.api.budget = Budget(300, 15, time.time() + 90)
        core._round_costs = [12]
        wait = core._pace()
        self.assertGreater(wait, 80)
        core._pace()
        self.assertEqual(len(said), 1)  # once a window
        core.emit("error", "home: HTTP 429: rate limit reached")
        self.assertEqual(errors, [])  # not lane by lane
        core.api.budget = Budget(300, 250, time.time() + 90)
        self.assertEqual(core._pace(), 0)

    def test_a_round_cut_by_a_429_doesnt_make_the_next_look_cheap(self):
        """The night of 22.10: a round cut short cost 1, the next started with 9 left
        and earned a 429 again. The dearest of the last rounds counts."""
        core, _w = self.make()
        core._round_costs = [42, 41, 1]
        core.api.budget = Budget(300, 60, time.time() + 90)
        self.assertGreater(core._pace(), 80)  # 60 < 2 × 42 + 20: wait
        core._round_costs = [1, 1, 1]
        self.assertEqual(core._pace(), 0)

    def test_a_429_cuts_the_round_quietly(self):
        from fedtail.protocols.base import RateLimited
        core, _w = self.make()
        errors = []
        core.events.on("error", lambda _n, p: errors.append(p))

        def once():
            core._stop.set()
            raise RateLimited("too many", time.time() + 60)
        core.poll_once = once
        core.cfg["poll"]["interval_seconds"] = 0.01
        core.cfg["poll"]["stream_gap_seconds"] = 0
        with self.assertNoLogs("fedtail.core.app", level="ERROR"):
            core._poll_loop()
        self.assertEqual(errors, [])
        self.assertEqual(getattr(core, "_poll_failures", 0), 0)


class FakeHasNoBudget(unittest.TestCase):
    def test_fake_api_paces_nothing(self):
        self.assertFalse(hasattr(FakeApi, "budget"))
