"""A lane's quick filters count before its window (28.10: "only video" showed the few
videos among the newest posts, none of the many further down, and Older fetched from the
server while the store had them): the window is the newest posts the funnel lets through,
and Older first looks deeper into the store, then asks the server."""

import unittest

from fedtail.core import app as core_app
from fedtail.core.view import View
from fedtail.frontends.common.lane import LaneModel
from tests.fakes import BOB, status
from tests import test_tag_mute


def video(sid, minute):
    st = status(sid, BOB, minute=minute, vis="public", text="a clip")
    st["media_attachments"] = [{"id": "m" + sid, "type": "video",
                                "url": f"https://x.test/{sid}.mp4", "preview_url": ""}]
    return st


class FunnelTest(unittest.TestCase):
    def setUp(self):
        t = test_tag_mute.TagMuteTest("test_one_filter_gathers_them_and_posts_go_at_once")
        t.setUp()
        self.addCleanup(t.doCleanups)
        self.core = core = t.core
        core.cfg["feed"]["render_limit"] = 20
        old = [(st["id"], st, st["created_at"]) for st in (video("%03d" % i, 1)
                                                           for i in range(30))]
        new = [(st["id"], st, st["created_at"]) for st in (
            status("%03d" % (100 + i), BOB, minute=2, text="words") for i in range(60))]
        core.store.put_items("home", old)
        core.store.put_items("home", new)  # newer: on top
        core._lane_cache.clear()

    def shown(self, model):
        return [s.key for s in model.build(False).specs if s.entry is not None]

    def test_the_window_is_of_what_the_funnel_lets_through(self):
        model = LaneModel(View(self.core), "home")
        self.assertFalse(any(int(k) < 100 for k in self.shown(model)))  # 20 newest: text
        model.media.wanted = {"video"}
        got = self.shown(model)
        self.assertEqual(len(got), 20)
        self.assertTrue(all(int(k) < 100 for k in got))

    def test_older_looks_deeper_into_the_store_first(self):
        from unittest import mock
        with mock.patch.object(core_app, "FILTER_WINDOW", 40):
            model = LaneModel(View(self.core), "home")
            model.media.wanted = {"video"}
            self.assertEqual(self.shown(model), [])  # 40 looked through: all text
            asked = []
            with mock.patch("fedtail.core.sources.fetch_older",
                            lambda *a, **k: asked.append(1) or []):
                self.assertTrue(self.core.load_older("home").result())
                got = self.shown(model)
                self.assertEqual(len(got), 20)  # from the store, the server not asked
                self.assertEqual(asked, [])
                while self.core._lane_deep.get("home"):
                    self.core.load_older("home").result()
                self.assertEqual(len(self.shown(model)), 30)
                self.core.load_older("home").result()  # the store's end: now the server
                self.assertEqual(asked, [1])


if __name__ == "__main__":
    unittest.main()
