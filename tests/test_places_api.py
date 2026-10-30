"""0.20 places on the rest of the Mastodon client API, as the web page and the terminal
draw them (common/places.py): a filter edited, a report by the server's rules, the
profile's flags and tag suggestions, who else shared a link, the server's terms, blocks
and translator."""

import tempfile
import unittest

from fedtail import i18n
from fedtail.core.view import View
from fedtail.frontends.common.places import Places

from . import scenario
from .fakes import BOB, status


class PlacesApiTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.core, self.w = scenario.make_core(self._tmp.name)
        self.addCleanup(self.core.shutdown)
        self.view = View(self.core)
        self.pl = Places(self.view)

    def buttons(self, page):
        return {b.act[1]: b for r in page.rows for b in r.buttons}

    def test_filter_edit(self):
        f = self.core.add_filter("noise", ["nft", "crypto"], "warn").result()
        page = self.pl.page("silence", tab="filters")
        b = self.buttons(page)["filter_edit"]
        out = self.pl.act(*b.act)
        self.assertEqual(out.open, {"page": "filter", "arg": f["id"]})
        form = {x.name: x for x in self.pl.page("filter", f["id"]).form}
        self.assertEqual(form["words"].value, "nft, crypto")
        self.assertEqual(form["expires"].value, "")  # as it is
        values = {"title": "noise 2", "words": "nft, web3", "action": "hide",
                  "contexts": ["home", "thread"], "expires": "3600"}
        out = self.pl.act("filter", "save", f["id"], values)
        self.assertEqual(out.message, i18n._("filter_saved"))
        got = self.w.filters[f["id"]]
        self.assertEqual(sorted(k["keyword"] for k in got["keywords"]), ["nft", "web3"])
        self.assertEqual((got["title"], got["filter_action"], got["context"]),
                         ("noise 2", "hide", ["home", "thread"]))
        self.assertIsNotNone(got["expires_at"])
        out = self.pl.act("filter", "save", f["id"], dict(values, words=" , "))
        self.assertEqual(out.error, i18n._("filter_words"))

    def test_report_by_rules(self):
        self.w.add(status("300", BOB, text="bad"), home=True)
        self.core.poll_once()
        page = self.pl.page("report", "300")
        rules = next(x for x in page.form if x.name == "rules")
        self.assertEqual(rules.choices, (("1", "Be kind"),))
        out = self.pl.act("report", "send", "300", {"category": "violation", "rules": []})
        self.assertEqual(out.error, i18n._("report_rules_need"))
        out = self.pl.act("report", "send", "300", {"category": "violation", "rules": ["1"],
                                                    "comment": "x"})
        self.assertEqual(out.error, "")
        self.assertEqual(self.w.reports[-1][4:], ("violation", ["1"]))
        self.pl.act("report", "send", "300", {"category": "spam", "rules": ["1"]})
        self.assertEqual(self.w.reports[-1][4], "spam")  # rules only with "violation"

    def test_profile_flags_and_tag_suggestions(self):
        page = self.pl.page("profile_edit")
        form = {x.name: x.value for x in page.form}
        self.assertFalse(form["hide_collections"])
        self.assertEqual(form["attribution_domains"], "")
        self.assertIn(i18n._("featured_suggest"), [r.title for r in page.rows])
        self.assertIn("feature", self.buttons(page))
        values = dict(form, hide_collections=True, attribution_domains="blog.example news.x")
        self.pl.act("profile_edit", "save", "", values)
        sent = self.w.profile_updates[-1]
        self.assertEqual(sent["hide_collections"], True)
        self.assertEqual(sent["attribution_domains"], ["blog.example", "news.x"])
        self.assertNotIn("indexable", sent)  # unchanged: not sent
        again = {x.name: x.value for x in self.pl.page("profile_edit").form}
        self.pl.act("profile_edit", "save", "", again)
        self.assertNotIn("hide_collections", self.w.profile_updates[-1])

    def test_as_many_profile_fields_as_the_server_takes(self):
        """GoToSocial, Akkoma say how many fields a profile may have: the editor shows
        them all — it cut them at Mastodon's 4, and the fifth was gone once saved."""
        self.core.caps.max_profile_fields = 6
        page = self.pl.page("profile_edit")
        names = [x.name for x in page.form if x.name.endswith("_name")
                 and x.name.startswith("field")]
        self.assertEqual(len(names), 6)
        values = {x.name: x.value for x in page.form}
        for i in range(6):
            values[f"field{i}_name"], values[f"field{i}_value"] = f"k{i}", f"v{i}"
        self.pl.act("profile_edit", "save", "", values)
        sent = self.w.profile_updates[-1]
        self.assertEqual(len(sent.get("fields") or sent.get("fields_attributes") or []), 6,
                         sent)

    def test_link_posts(self):
        st = self.w.add(status("301", BOB, text="look"))
        st["card"] = {"url": "https://news.example/a"}
        page = self.pl.page("link", "https://news.example/a")
        self.assertIn("news.example", page.title)
        self.assertEqual([r.data.id for r in page.rows if r.kind == "post"], ["301"])
        self.assertEqual(page.empty, i18n._("link_posts_none"))
        out = self.pl.act("link", "more", "301 https://news.example/a")
        self.assertEqual(out.open, {"page": "link", "arg": "https://news.example/a",
                                    "cursor": "301"})

    def test_server_terms_blocks_translator(self):
        page = self.pl.page("server")
        titles = [r.title for r in page.rows]
        for key in ("server_terms", "server_blocks"):
            self.assertIn(i18n._(key), titles)
        block = next(r for r in page.rows if r.title == "bad.example")
        self.assertIn(i18n._("server_block_suspend"), block.line)
        self.assertTrue(any("en → ru, de" in r.title for r in page.rows))


if __name__ == "__main__":
    unittest.main()
