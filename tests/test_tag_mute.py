"""A hashtag muted in one click (28.10's request, Fedilab's way): "#tag" into one server
filter of muted hashtags; its posts leave the lanes at once, those stored before too;
the post's ⋯ menu, the tag's page and its link all do it."""

import tempfile
import unittest
from pathlib import Path

from fedtail import i18n
from fedtail.core import auth, config, paths
from fedtail.core.app import Core
from fedtail.core.view import View
from fedtail.frontends.common import actions, links
from fedtail.frontends.common.places import Places
from tests import fakes
from tests.fakes import BOB, FakeApi, status
from tests.test_event_lanes import Host


def tagged(sid, *tags, minute=1):
    st = status(sid, BOB, minute=minute, vis="public", text=" ".join("#" + t for t in tags))
    st["tags"] = [{"name": t, "url": f"https://example.test/tags/{t}"} for t in tags]
    return st


class TagMuteTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        FakeApi.world = self.w = fakes.World()
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False}})
        p = paths.resolve("t", config=str(Path(tmp.name) / "c.toml"),
                          data=str(Path(tmp.name) / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        self.core = Core(cfg, p, api_class=FakeApi)
        self.core._origin_json = lambda url: None
        self.addCleanup(self.core.shutdown)
        self.core.connect().result()
        self.w.add(tagged("010", "nft", "art"), home=True)
        self.w.add(tagged("011", "cats", minute=2), home=True)
        self.core.poll_once()

    def home(self):
        return [st["id"] for _i, st in self.core.lane_entries("home")]

    def test_one_filter_gathers_them_and_posts_go_at_once(self):
        self.assertIn("010", self.home())
        self.assertTrue(self.core.mute_tag("NFT").result())
        self.assertTrue(self.core.tag_muted("#nft"))
        self.assertNotIn("010", self.home())  # stored before: gone from the lane too
        self.assertIn("011", self.home())
        self.core.mute_tag("cats").result()
        mine = [f for f in self.w.filters.values() if f["title"] == Core.TAG_FILTER]
        self.assertEqual(len(mine), 1)  # one filter, both tags in it
        self.assertEqual({k["keyword"] for k in mine[0]["keywords"]}, {"#nft", "#cats"})
        self.assertEqual(mine[0]["filter_action"], "hide")
        self.core.mute_tag("nft").result()  # muted already: nothing twice
        self.assertEqual(len(mine[0]["keywords"]), 2)
        # shown again: out of the filter; the last one out — the filter goes
        self.core.mute_tag("nft", False).result()
        self.assertIn("010", self.home())
        self.core.mute_tag("cats", False).result()
        self.assertFalse([f for f in self.w.filters.values() if f["title"] == Core.TAG_FILTER])

    def test_a_tag_in_a_filter_of_my_own_counts_too(self):
        self.core.add_filter("noise", ["#art", "crypto"], action="hide").result()
        self.core._refresh_silence()
        self.assertTrue(self.core.tag_muted("art"))
        self.core.mute_tag("art", False).result()  # taken out of that one, the rest stays
        f = next(f for f in self.w.filters.values() if f["title"] == "noise")
        self.assertEqual([k["keyword"] for k in f["keywords"]], ["crypto"])

    def test_from_the_menu_the_link_and_the_tags_page(self):
        view = View(self.core)
        post = view.by_id("010")
        ctx = actions.Ctx(cfg=self.core.cfg, me_id="ME", supports=lambda _f: True)
        items = [i for i in actions.menu(post, ctx) if i.kind == "link"]
        mute = [i for i in items if i.url.startswith("fedtail:mutetag/")]
        self.assertEqual([i.label for i in mute], ["Mute #nft", "Mute #art"])
        self.core.cfg["feed"]["mute_tags_shown"] = 1  # feed.mute_tags_shown: the first only
        self.assertEqual([i.label for i in actions.menu(post, ctx)
                          if i.kind == "link" and i.url.startswith("fedtail:mutetag/")],
                         ["Mute #nft"])
        self.core.cfg["feed"]["mute_tags_shown"] = 3
        host = Host()
        links.Links(view, host).open(mute[0].url)
        self.assertEqual(host.errors, [])
        self.assertTrue(self.core.tag_muted("nft"))
        self.assertIn("#nft muted", host.said)
        page = Places(view).page("tag", "cats")
        btn = next(b for r in page.rows for b in r.buttons if b.act[1] in ("mute", "unmute"))
        self.assertEqual(btn.act[1], "mute")
        out = Places(view).act("tag", "mute", "cats")
        self.assertFalse(out.error, out.error)
        self.assertTrue(self.core.tag_muted("cats"))
        page = Places(view).page("tag", "cats")
        btn = next(b for r in page.rows for b in r.buttons if b.act[1] in ("mute", "unmute"))
        self.assertEqual(btn.act[1], "unmute")


if __name__ == "__main__":
    unittest.main()
