"""Behaviours that were numbers in the code and are options now (30.10): each does what its
config key says — how far whom I follow is read, how many search results, for how long
an opened thread is asked again, how many posts another server's lane gives a round, how
much of an RSS feed is taken."""

import time
import unittest
from unittest import mock

from fedtail.core import rss

from . import test_cli
from .test_core import TmpDir


class CoreOptionsTest(TmpDir):
    make = test_cli.CliTest.make

    def test_whom_i_follow_read_as_far_as_following_max(self):
        core, _w = self.make(feed={"following_max": 80})
        core.connect().result()
        pages = []

        def following(acc_id, max_id=None):
            pages.append(max_id)
            return [{"id": f"p{len(pages)}"}], f"m{len(pages)}"  # always one more page
        core._following_at = 0
        with mock.patch.object(core.api, "following", following), \
                mock.patch.object(core.api, "followed_tags", return_value=[]):
            core._refresh_following()
        self.assertEqual(len(pages), 2)  # 80 people, 40 a page

    def test_search_asks_for_search_limit(self):
        core, _w = self.make(feed={"search_limit": 33})
        core.connect().result()
        with mock.patch.object(core.api, "search", return_value={}) as s:
            core.search("bob").result()
        self.assertEqual(s.call_args.kwargs["limit"], 33)

    def test_an_opened_thread_is_asked_again_for_its_minutes(self):
        core, _w = self.make(feed={"thread_recheck_minutes": 1,
                                   "thread_recheck_for_minutes": 60})
        core.connect().result()
        core._opened_threads = {"010": time.monotonic() - 40 * 60}
        with mock.patch.object(core.api, "context", return_value={"descendants": []}):
            core.recheck_threads()
        self.assertIn("010", core._opened_threads)  # 40 min of 60: still followed
        core.cfg["feed"]["thread_recheck_for_minutes"] = 30
        core.recheck_threads()
        self.assertNotIn("010", core._opened_threads)

    def test_another_servers_lane_gives_extra_posts_a_round(self):
        core, _w = self.make(lanes={"extra_posts": 2})
        core.connect().result()
        page = [{"uri": f"https://x.example/{i}", "visibility": "public"} for i in range(9)]
        asked = []
        with mock.patch.object(core, "_origin_get", return_value=page), \
                mock.patch.object(core, "_resolve_statuses",
                                  side_effect=lambda uris: asked.extend(uris) or []):
            core.wider._one("public", "x.example", "federated", None)
        self.assertEqual(len(asked), 2)


class RssOptionsTest(TmpDir):
    FEED = ("<rss><channel><title>t</title>"
            + "".join(f"<item><title>i{i}</title><link>https://f.example/{i}</link>"
                      f"<description>{'word ' * 400}</description></item>" for i in range(9))
            + "</channel></rss>")

    def test_rss_items_and_summary_chars(self):
        got = rss.parse(self.FEED, "https://f.example/feed", items_max=3, summary_max=200)
        self.assertEqual(len(got), 3)
        self.assertLess(len(got[0]["content"]), 300)
        self.assertEqual(len(rss.parse(self.FEED, "https://f.example/feed")), 9)


class CommonOptionsTest(unittest.TestCase):
    def test_how_deep_a_thread_indents(self):
        from fedtail.frontends.common.cardtext import indent_of
        self.assertEqual([indent_of({}, d) for d in (0, 3, 20)], [0, 3, 8])
        self.assertEqual(indent_of({"feed": {"thread_indent_max": 2}}, 5), 2)

    def test_how_much_of_the_answered_post(self):
        from fedtail.frontends.common.cardtext import context_chars
        self.assertEqual(context_chars({}), 160)
        self.assertEqual(context_chars({"feed": {"reply_context_chars": 60}}), 60)

    def test_a_notification_lists_max_lines_and_stays_seconds(self):
        from fedtail.frontends import notifytext
        note = notifytext.Note("t", "b", "home")
        argv = notifytext.desktop_argv(["notify-send"], note, 12)
        self.assertIn("--expire-time=12000", argv)
        self.assertLess(argv.index("--expire-time=12000"), argv.index("--"))
        self.assertFalse(any(a.startswith("--expire") for a in
                             notifytext.desktop_argv(["notify-send"], note)))

    def test_default_columns(self):
        from types import SimpleNamespace

        from fedtail.frontends.common import columns
        view = SimpleNamespace(cfg={"ui": {"default_columns": 1}}, lane_by_name={},
                               lane_rank=lambda n: 1)
        with mock.patch("fedtail.frontends.common.sidebar.start_lane", return_value="home"):
            got = columns.default_names(view, ["home", "replies", "mentions"])
        self.assertEqual(got, ["home"])


class ReadingRuleTest(unittest.TestCase):
    """One reading rule for the windows and the web page (common/lane): Qt counted a
    window out of focus for 5 s after a hand's scroll, GTK never, the web page always."""

    def test_in_focus_or_for_a_while_after_the_hand(self):
        from fedtail.frontends.common.lane import dwell_ms, reading_now
        cfg = {"read": {"unfocused_seconds": 5, "dwell_ms": 500}}
        self.assertTrue(reading_now(cfg, True, 0, 100))
        self.assertTrue(reading_now(cfg, False, 97, 100))
        self.assertFalse(reading_now(cfg, False, 90, 100))
        self.assertFalse(reading_now({"read": {"unfocused_seconds": 0}}, False, 100, 100))
        self.assertEqual(dwell_ms(cfg), 500)
        self.assertEqual(dwell_ms({}), 350)
