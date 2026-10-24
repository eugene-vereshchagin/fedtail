"""Small toolkit-free modules of the frontends, case by case: the federation page's
words (fedstatus), what a theme file may say (themefile), the HTML the cards get
(richtext), Markdown for the help (mdhtml), the icons' styles (iconpack), colours and
dates (palette)."""

import time
import unittest
from datetime import UTC, datetime

from fedtail import i18n
from fedtail.frontends import fedstatus

_ = i18n._


class FedStatusTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_ago(self):
        now = 1_000_000
        self.assertEqual(fedstatus.ago(None, now), "—")
        self.assertEqual(fedstatus.ago(now - 30, now), _("fed_ago_s", n=30))
        self.assertEqual(fedstatus.ago(now - 600, now), _("fed_ago_m", n=10))
        self.assertEqual(fedstatus.ago(now - 7200, now), _("fed_ago_h", n=2))
        self.assertEqual(fedstatus.ago(now - 3 * 86400, now), _("fed_ago_d", n=3))

    def test_hints(self):
        def h(o, path="/api/v1/x", kind="theirs"):
            return fedstatus.hint({"outcome": o, "path": path, "kind": kind})
        self.assertEqual(h("refused (x)"), _("fed_hint_refused"))
        self.assertEqual(h("timeout"), _("fed_hint_timeout"))
        self.assertEqual(h("timeout", kind="mine"), _("fed_hint_timeout_mine"))
        self.assertEqual(h("no connection"), _("fed_hint_noconn"))
        self.assertEqual(h("no connection", kind="mine"), _("fed_hint_noconn_mine"))
        self.assertEqual(h("TLS error"), _("fed_hint_tls"))
        self.assertEqual(h("something else"), "")
        self.assertEqual(h(404, "/api/v1/lists/:id/accounts", "mine"),
                         _("fed_hint_list_not_followed"))
        self.assertEqual(h(501, "/api/v1/trends", "mine"), _("fed_hint_missing"))
        self.assertEqual(h(404, "/api/v1/statuses/:id", "mine"), _("fed_hint_gone_mine"))
        self.assertEqual(h(403, "/api/v1/statuses/:id", "mine"), _("fed_hint_auth_mine"))
        self.assertEqual(h(422, "/api/v1/statuses/:id", "mine"),
                         _("fed_hint_refused_by_server"))
        self.assertEqual(h(410), _("fed_hint_gone"))
        self.assertEqual(h(401), _("fed_hint_auth"))
        self.assertEqual(h(429), _("fed_hint_rate"))
        self.assertEqual(h(503), _("fed_hint_down"))
        self.assertEqual(h(503, "/api/v1/statuses/:id", "mine"), _("fed_hint_down_mine"))
        self.assertEqual(h(500), _("fed_hint_server_error"))
        self.assertEqual(h(301), "")

    def test_facts_with_failed_polls_and_a_stream(self):
        now = time.time()
        data = {"server": "x.test", "hosts": [], "since": now - 60, "me": "",
                "polls": {"count": 3, "interval_s": 90, "last_ok": now - 10, "last_s": None,
                          "failures": 2, "last_error": "timeout"},
                "stream": {"open": True, "since": now - 100, "last_event": now - 5,
                           "drops": 1, "last_error": "closed"}}
        got = dict(fedstatus.facts(data, now))
        self.assertIn(_("fed_polls_failed", n=2, last="timeout"), got[_("fed_polls")])
        stream = got[_("fed_stream")]
        self.assertIn(_("fed_stream_drops", n=1, why="closed"), stream)
        self.assertTrue(stream.startswith(_("fed_stream_open", since=_("fed_ago_m", n=2))))
        data["stream"] = {"open": False, "since": None, "last_event": None, "drops": 0,
                          "last_error": ""}
        self.assertEqual(dict(fedstatus.facts(data, now))[_("fed_stream")],
                         _("fed_stream_down"))


class PaletteTest(unittest.TestCase):
    def test_colour_corners(self):
        from fedtail.frontends.palette import Color
        c = Color(100, 120, 130)
        self.assertEqual(c.with_alpha(300).a, 255)
        self.assertEqual(c.with_alpha(-5).a, 0)
        self.assertIs(c.darker(0), c)
        self.assertIs(c.lighter(0), c)
        self.assertEqual(c.darker(50), c.lighter(200))  # below 100: the other way
        self.assertEqual(c.lighter(50), c.darker(200))

    def test_dates(self):
        from fedtail.frontends import palette
        i18n.setup("en")
        words = {"date": "{day} {mon} {time}"}
        now = datetime.now(UTC)
        self.assertEqual(palette.date(words, "garbage"), "")
        self.assertEqual(palette.date(words, None), "")
        self.assertIn(f"{now.astimezone():%H:%M}", palette.date(words, now))
        self.assertTrue(palette.date(words, "2001-02-03T12:05:06Z").endswith("2001"))
        self.assertEqual(palette.date(words, "2001-02-03T12:05:06Z", "{dd}.{mm}.{yy}"),
                         "03.02.01")


if __name__ == "__main__":
    unittest.main()
