"""protocols/mastodon/probe.py: asking the server what it can do — with GETs only."""

import unittest

from fedtail.protocols.mastodon import probe
from fedtail.protocols.mastodon.api import ApiError, Capabilities


class _Api:
    def __init__(self, missing=(), closed=()):
        self.missing, self.closed, self.asked = set(missing), set(closed), []

    def get(self, path, params=None, timeout=30):
        self.asked.append(path)
        if path in self.missing:
            raise ApiError(404, "Not Found")
        if path in self.closed:
            raise ApiError(401, "no")
        if path == "/api/v1/markers":
            raise TimeoutError("slow")
        return []

    def post(self, *a, **kw):  # never: a probe changes nothing
        raise AssertionError("a probe posted")


class ProbeTest(unittest.TestCase):
    def test_answers_and_what_is_known(self):
        api = _Api(missing={"/api/v1/directory", "/api/v1/trends/links"},
                   closed={"/api/v1/timelines/public"})
        got = probe.run(api, Capabilities(software="gotosocial", version="0.20",
                                          markdown=True))
        states = {k: s for k, s, _d in got["items"]}
        self.assertEqual(states["directory"], "no")
        self.assertEqual(states["local"], "closed")
        self.assertEqual(states["markers"], "error")
        self.assertEqual(states["lists"], "yes")
        self.assertEqual(states["markdown"], "yes")
        self.assertEqual(states["dismiss_one"], "no")  # GoToSocial: known, not asked
        self.assertEqual(states["mute_thread"], "self")
        self.assertEqual(len(api.asked), len(probe.CHECKS))
        feats = probe.features(got)
        self.assertFalse(feats["directory"])
        self.assertFalse(feats["trends_links"])
        self.assertTrue(feats["suggestions"])
        self.assertNotIn("local", feats)  # no feature of the core behind it

    def test_mastodon_dismisses_one(self):
        got = probe.run(_Api(), Capabilities(software="mastodon"))
        self.assertIn(["dismiss_one", "yes", "known"], got["items"])


if __name__ == "__main__":
    unittest.main()
