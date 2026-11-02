"""Is a newer fedtail out (core/updates.py): asked once a day, with nothing but the
version, the interface and the system; a newer one is a row of Activity and a line in
About; updates.check = false — never asked."""

import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from fedtail.core import updates
from fedtail.core.view import View
from fedtail.frontends.common import activity
from fedtail.frontends.common.places import Places

from .test_sync import Devices


class VersionsTest(unittest.TestCase):
    def test_made_up_worlds_dont_ask(self):
        """The demo (example.test), the tools' and screenshots' worlds: never counted."""
        for host in ("example.test", "a.example", "example.org", "x.example.com",
                     "localhost.localhost"):
            self.assertTrue(updates._made_up({host}), host)
        for host in ("mastodon.social", "dmesg.online", "myexample.org"):
            self.assertFalse(updates._made_up({host}), host)

    def test_newer(self):
        self.assertTrue(updates.newer("0.22.4", "0.22.3"))
        self.assertTrue(updates.newer("0.22.4", "0.22.4.dev0"))  # a dev build: before it
        self.assertFalse(updates.newer("0.22.4", "0.22.4"))
        self.assertFalse(updates.newer("0.22.3", "0.22.4.dev2"))
        self.assertTrue(updates.newer("0.23.0", "0.22.10"))  # numbers, not text
        self.assertFalse(updates.newer("nonsense", "0.22.4"))
        self.assertFalse(updates.newer("", "0.22.4"))


class CheckTest(Devices):
    def asked(self, answer, version="0.22.3"):
        calls = []

        def get_json(url, **kw):
            calls.append((url, kw))
            return answer
        with mock.patch("fedtail.core.remote.get_json", get_json), \
                mock.patch.object(updates, "__version__", version):
            got = self.desk.check_updates()
        return got, calls

    def rows(self):
        return [e for e in self.desk.activity_entries() if e.get("type") == "fedtail.release"]

    def test_a_newer_one_is_said_once(self):
        got, calls = self.asked({"version": "0.22.4"})
        self.assertEqual(got, "0.22.4")
        url, kw = calls[0]
        self.assertTrue(url.startswith("https://fedtail.dmesg.online/update?"))
        self.assertEqual(set(parse_qs(urlsplit(url).query)), {"v", "ui", "os"})
        self.assertEqual(parse_qs(urlsplit(url).query)["v"], ["0.22.3"])
        self.assertEqual(set(kw["headers"]), {"User-Agent"})  # no token, nothing else
        self.assertEqual(len(self.rows()), 1)
        self.asked({"version": "0.22.4"})  # asked again: the same release, not again
        self.assertEqual(len(self.rows()), 1)
        row = next(r for r in activity.rows(View(self.desk).activity(), "", str)
                   if r.kind == "release")
        self.assertEqual(activity.who_link(row.people[0]),
                         "https://github.com/eugene-vereshchagin/fedtail/releases/tag/v0.22.4")
        with mock.patch.object(updates, "__version__", "0.22.3"):
            page = Places(View(self.desk)).page("about")
        self.assertIn("update", [r.key for r in page.rows])

    def test_the_newest_already_or_no_answer(self):
        self.assertIsNone(self.asked({"version": "0.22.3"})[0])
        self.assertIsNone(self.asked(None)[0])
        self.assertIsNone(self.asked({"version": 7})[0])
        self.assertEqual(self.rows(), [])
        with mock.patch.object(updates, "__version__", "0.22.3"):
            page = Places(View(self.desk)).page("about")
        self.assertNotIn("update", [r.key for r in page.rows])

    def test_once_a_day_and_the_switch(self):
        self.desk.store.kv_set("updates.at", None)
        self.assertFalse(self.desk.updates_due())  # example.test: a made-up world, quiet
        self.desk._own_hosts = lambda: {"social.real-server.org"}
        self.assertTrue(self.desk.updates_due())
        self.asked({"version": "0.22.3"})
        self.assertFalse(self.desk.updates_due())  # asked: tomorrow again
        self.desk.store.kv_set("updates.at", 0)
        self.desk.cfg["updates"]["check"] = False
        self.assertFalse(self.desk.updates_due())
        self.desk.cfg["updates"]["check"] = True
        self.desk.cfg["updates"]["url"] = "http://plain.example/update"  # never in clear
        self.assertFalse(self.desk.updates_due())


if __name__ == "__main__":
    unittest.main()
