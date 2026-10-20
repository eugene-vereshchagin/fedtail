"""Federation status: the recorder (core.health), what Core hands the window, and the
page (frontends.fedstatus) — no Qt needed."""

import time
import unittest

from fedtail import i18n
from fedtail.core import health
from fedtail.frontends import fedstatus
from fedtail.protocols.mastodon.api import ApiError

from . import test_core
from .fakes import BOB, status


class ShapeTest(unittest.TestCase):
    def test_ids_folded_queries_dropped(self):
        for path, want in (
                ("/api/v1/lists/01M520G8TV8A258CRRYASEQSC6/accounts", "/api/v1/lists/:id/accounts"),
                ("/api/v1/statuses/110000000000000001/context?x=1", "/api/v1/statuses/:id/context"),
                ("/api/v1/domain_blocks", "/api/v1/domain_blocks"),
                ("/api/v1/tags/linux", "/api/v1/tags/:id"),
                ("/users/bob/statuses/123456/replies", "/users/:id/…"),
                ("/@bob/110000000000000001", "/@:name/:id"),
                ("", "/")):
            self.assertEqual(health.shape(path), want, path)


class RecorderTest(unittest.TestCase):
    def test_counts_failures_grouped_answers_timed(self):
        now = [1000.0]
        r = health.Recorder(clock=lambda: now[0])
        for _ in range(3):
            r.note("Srv.example", "POST", "/api/v1/lists/01M520G8TV8A258CRRYASEQSC6/accounts",
                   404)
            now[0] += 600
        r.note("srv.example", "GET", "/api/v1/timelines/home?limit=40", 200, 0.09)
        r.note("srv.example", "GET", "/api/v1/conversations", "timeout")
        r.note("far.example", "GET", "/users/x", 410, kind="remote")
        snap = r.snapshot()
        mine = snap["hosts"][0]
        self.assertEqual((mine["host"], mine["answers"], mine["failures"], mine["median_ms"]),
                         ("srv.example", 5, 4, 90))
        top = snap["problems"][0]
        self.assertEqual((top["path"], top["outcome"], top["count"]),
                         ("/api/v1/lists/:id/accounts", 404, 3))
        self.assertEqual(top["last"] - top["first"], 1200)
        self.assertEqual(snap["problems"][-1]["kind"], "remote")  # mine first
        self.assertFalse(any("?" in p["example"] for p in snap["problems"]))
        r.clear()
        self.assertEqual(r.snapshot()["problems"], [])

    def test_outcomes_named(self):
        import requests

        from fedtail.core import remote
        self.assertEqual(health.outcome_of(requests.ReadTimeout()), "timeout")
        self.assertEqual(health.outcome_of(requests.ConnectionError()), "no connection")
        self.assertEqual(health.outcome_of(remote.Refused("not a public address")),
                         "refused: not a public address")

    def test_remote_fetches_are_recorded(self):
        from fedtail.core import remote

        from .test_remote import Resp, Session
        health.REC.clear()
        self.assertIsNone(remote.get_json("https://93.184.216.34/users/gone",
                                          session=Session(Resp(410))))
        remote.get_json("https://127.0.0.1/x", session=Session())
        rows = {(p["host"], p["outcome"]) for p in health.REC.snapshot()["problems"]}
        self.assertIn(("93.184.216.34", 410), rows)
        self.assertIn(("127.0.0.1", "refused: 127.0.0.1: not a public address"), rows)


class StatusTest(test_core.TmpDir):
    make = test_core.CoreTest.make

    def test_core_snapshot_and_the_page(self):
        i18n.setup("ru")
        health.REC.clear()
        core, w = self.make()
        core.connect().result()
        w.add(status("010", BOB, minute=10), home=True)
        core.poll_once()
        x = core.create_list("Ждут").result()
        w.list_refuse.add("B")
        core.set_in_list(x["id"], "B", True).result()
        core.api.domain_blocks = lambda: (_ for _ in ()).throw(ApiError(404, "Not Found"))
        core._refresh_silence()
        health.REC.note("example.test", "POST", "/api/v1/lists/01M520G8TV8A258CRRYASEQSC6/"
                        "accounts", 404)
        health.REC.note("far.example", "GET", "/users/x", 401, kind="remote")
        data = core.federation_status().result()
        self.assertEqual(data["server"], "https://example.test")
        self.assertEqual(data["polls"]["count"], 1)
        self.assertIsNotNone(data["polls"]["last_ok"])
        self.assertIn("domain_blocks", data["unsupported"])
        self.assertEqual([(wt["account"], wt["list"], wt["state"])
                          for wt in data["list_waiting"]],
                         [("bob@social.example", "Ждут", "requested")])
        page = fedstatus.html(data)
        for bit in ("Моя нода", 'href="fedtail:account/B">@bob@social.example</a>',
                    "заявка на подписку ещё без ответа", "domain_blocks",
                    "/api/v1/lists/:id/accounts", "в список берут только тех",
                    "far.example", "authorized fetch"):
            self.assertIn(bit, page, bit)
        plain = fedstatus.text(data)
        self.assertIn("POST /api/v1/lists/:id/accounts -> 404", plain)
        self.assertNotIn("<", plain)

    def test_someone_with_no_post_here_is_named_by_my_server(self):
        i18n.setup("en")
        core, w = self.make()
        core.connect().result()
        x = core.create_list("Tits").result()
        w.list_refuse.add("Q")
        core.set_in_list(x["id"], "Q", True).result()
        w.list_refuse.discard("Q")  # refused since: not followed, not requested
        core.api.get = lambda path, params=None: (
            {"id": "Q", "acct": "birdhater@far.example", "display_name": "Ворона",
             "url": "https://far.example/@birdhater"} if path == "/api/v1/accounts/Q" else None)
        [row] = core.federation_status().result()["list_waiting"]
        self.assertEqual((row["account"], row["name"], row["state"]),
                         ("birdhater@far.example", "Ворона", "not_following"))
        page = fedstatus.html(core.federation_status().result())
        self.assertIn('Ворона <a href="fedtail:account/Q">@birdhater@far.example</a>', page)
        self.assertIn("refused or withdrawn", page)
        self.assertIn("https://far.example/@birdhater",
                      fedstatus.text(core.federation_status().result()))

    def test_hostile_server_text_is_escaped(self):
        i18n.setup("en")
        data = {"server": "https://x", "software": "", "version": "<img src=x>", "me": "",
                "polls": {"count": 0, "last_s": None, "last_ok": None, "failures": 0,
                          "last_error": "", "interval_s": 90},
                "stream": None, "stream_mode": "auto", "unsupported": [],
                "list_waiting": [{"id": '"><script>x', "account": "<img src=y>",
                                  "name": "<img src=z>", "url": "", "state": "unknown",
                                  "list": "<i>l</i>", "since": 0}],
                "since": time.time(),
                "hosts": [{"host": "<b>h</b>", "kind": "remote", "answers": 1,
                           "failures": 1, "median_ms": None, "p95_ms": None}],
                "problems": [{"host": "<b>h</b>", "method": "GET", "path": "/<script>",
                              "outcome": 404, "count": 1, "first": 0, "last": 0,
                              "example": "/<script>", "kind": "remote"}]}
        page = fedstatus.html(data)
        self.assertNotIn("<img", page)
        self.assertNotIn("<script", page)
        self.assertNotIn("<b>h</b>", page)
        self.assertNotIn("<i>l</i>", page)
        self.assertIn('href="fedtail:account/%22%3E%3Cscript%3Ex"', page)


if __name__ == "__main__":
    unittest.main()
