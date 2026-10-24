"""0.20: the rest of the Mastodon client API — filters edited, media described anew,
reports by rule, profile flags, the link timeline, the server's blocks, terms and
translator, featured tag suggestions, Web Push — through the core and the View."""

import unittest

from fedtail import i18n
from fedtail.core.view import View
from fedtail.frontends.common import actions

from . import test_cli
from .fakes import BOB, ME, status
from .test_core import TmpDir


class MoreApiTest(TmpDir):
    make = test_cli.CliTest.make

    def setUp(self):
        super().setUp()
        i18n.setup("en")
        self.core, self.w = self.make()
        self.core.connect().result()
        self.view = View(self.core)

    def test_edit_a_filter(self):
        f = self.core.add_filter("шум", ["крипта", "nft"], "warn").result()
        self.core.edit_filter(f["id"], title="шумы", words=["nft", "web3", " nft "],
                              action="hide", contexts=["home", "public"],
                              expires_in=3600).result()
        got = self.w.filters[f["id"]]
        self.assertEqual(sorted(k["keyword"] for k in got["keywords"]), ["nft", "web3"])
        self.assertEqual((got["title"], got["filter_action"], got["context"]),
                         ("шумы", "hide", ["home", "public"]))
        wf = next(x for x in self.view.filters().result() if x.id == f["id"])
        self.assertEqual(wf.contexts, ("home", "public"))
        self.assertIsNotNone(wf.expires)
        self.core.edit_filter(f["id"], expires_in=0).result()  # for good again
        self.assertIsNone(self.w.filters[f["id"]]["expires_at"])
        with self.assertRaises(LookupError):
            self.core.edit_filter("nope", words=["x"]).result()

    def test_media_words_and_cover(self):
        self.core.post("с видео", "public", media=[("/tmp/v.mp4", "кот", None, "/tmp/c.jpg")]
                       ).result()
        self.assertEqual(self.w.uploads[-1], ("/tmp/v.mp4", "кот", None, "/tmp/c.jpg"))
        mine = self.w.add(status("200", ME, text="pic"), home=True)
        mine["media_attachments"] = [{"id": "m9", "type": "image", "url": "u",
                                      "description": "old"}]
        st = self.core.edit(mine, "pic", media={"m9": ("new words", (0.5, -0.5)),
                                                "other": ("x", None)}).result()
        self.assertEqual(st["media_attachments"][0]["description"], "new words")

    def test_report_by_rule(self):
        st = self.w.add(status("201", BOB, text="bad"), home=True)
        self.core.report(st, "spam", rule_ids=["1"]).result()
        self.assertEqual(self.w.reports[-1][4:], ("violation", ["1"]))
        self.core.report(st, "spam").result()
        self.assertEqual(self.w.reports[-1][4], "other")
        info = self.view.server_info().result()
        self.assertEqual(info.rule_ids, ("1",))
        self.assertEqual(info.blocks, (("bad.example", "suspend", "spam"),))
        self.assertIn("terms", info.terms)
        self.assertIn(("en", ("ru", "de")), info.translates)

    def test_profile_flags(self):
        self.view.update_profile(hide_collections=True, indexable=False,
                                 attribution_domains=["blog.example"]).result()
        prof = self.view.my_profile().result()
        self.assertEqual((prof.hide_collections, prof.indexable, prof.attribution_domains),
                         (True, False, ("blog.example",)))

    def test_link_timeline_and_tag_suggestions(self):
        st = self.w.add(status("202", BOB, text="look"))
        st["card"] = {"url": "https://news.example/a"}
        got = self.view.link_timeline("https://news.example/a").result()
        self.assertEqual([p.id for p in got], ["202"])
        self.assertEqual([t.name for t in self.view.featured_tag_suggestions().result()],
                         ["fedi"])

    def test_web_push(self):
        self.assertEqual(self.core.vapid_key().result(), "")
        self.w.vapid = "BKEY"
        self.assertEqual(self.core.vapid_key().result(), "BKEY")
        self.assertIsNone(self.core.push_subscription().result())
        self.core.push_subscribe("https://push.example/x", "P", "A",
                                 {"mention": True}, "followed").result()
        self.assertEqual(self.core.push_subscription().result()["policy"], "followed")
        self.core.push_unsubscribe().result()
        self.assertIsNone(self.core.push_subscription().result())

    def test_translate_only_where_the_server_can(self):
        tr = {"en": ["ru", "de"], "ja": ["en"]}
        self.assertTrue(actions.can_translate(tr, "en", "ru"))
        self.assertFalse(actions.can_translate(tr, "ja", "ru"))
        self.assertTrue(actions.can_translate(None, "ja", "ru"))  # not said: try
        self.assertTrue(actions.can_translate(tr, "", "ru"))     # language unknown
        self.assertTrue(actions.can_translate(tr, "en", "ru-RU"))


if __name__ == "__main__":
    unittest.main()
