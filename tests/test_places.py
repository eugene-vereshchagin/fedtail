"""The places the web page and the terminal draw (frontends/common/places.py): each one
opens on the fake server, and its buttons do what the windows' do."""

import re
import tempfile
import unittest
from pathlib import Path

from fedtail import i18n
from fedtail.core.view import View
from fedtail.frontends import mdhtml
from fedtail.frontends.common import places
from fedtail.frontends.common.places import PLACES, Out, Places

from . import scenario
from .fakes import BOB

ROOT = Path(__file__).resolve().parent.parent


class PlacesTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.core, self.w = scenario.make_core(self._tmp.name)
        self.addCleanup(self.core.shutdown)
        self.view = View(self.core)
        self.pl = Places(self.view)

    def page(self, name, arg="", tab=""):
        return self.pl.page(name, arg, tab)

    def press(self, page, label=None, key=None, values=None, confirmed=True, answer=None):
        for b in [b for r in page.rows for b in r.buttons] + \
                [x for x in (page.submit, page.more) if x]:
            if (label is None or b.label == label) and (key is None or b.act[1] == key):
                out = self.pl.act(*b.act, values=values, confirmed=confirmed, answer=answer)
                self.assertIsInstance(out, Out)
                self.assertEqual(out.error, "", b)
                return out
        self.fail(f"no button {label or key} in {page.name}")

    def test_every_place_opens(self):
        args = {"tag": "fediverse", "people": "B", "list_of": "B", "reactions": "010",
                "quotes": "030", "history": "010", "report": "010", "long_form": "010",
                "translate": "010", "search": "bob"}
        self.w.lists["L1"] = {"title": "Friends", "exclusive": False, "members": {"B"}}
        self.core._refresh_lists()
        args["list_people"] = self.view.lists[0].id
        for name in PLACES:
            with self.subTest(place=name):
                try:
                    p = self.page(name, args.get(name, ""))
                except places.__dict__.get("NotSupported", ()) as e:  # noqa: B030
                    self.skipTest(str(e))
                self.assertTrue(p.title)
                for t, _w in p.tabs:
                    self.page(name, args.get(name, ""), t)

    def test_silence(self):
        self.w.muted.add("B")
        self.view.block_domain("bad.example", True).result(timeout=10)
        p = self.page("silence")
        self.press(p, key="filter_add", values={"words": "crypto, nft", "action": "hide",
                                               "contexts": ["home"]})
        p = self.page("silence")
        self.assertEqual([r.title for r in p.rows], ["crypto, nft"])
        self.press(p, key="filter_delete")
        self.assertEqual(self.page("silence").rows, [])
        p = self.page("silence", tab="muted")
        self.assertEqual([r.key for r in p.rows], ["B"])
        self.press(p, key="unmute")
        self.assertNotIn("B", self.w.muted)
        p = self.page("silence", tab="domains")
        self.press(p, key="undo_domain")
        self.assertNotIn("bad.example", self.w.blocked_domains)

    def test_filter_for_a_while(self):
        p = self.page("silence")
        f = {x.name: x for x in p.form}["expires"]
        self.assertEqual([c[0] for c in f.choices], ["0", "3600", "86400", "604800", "2592000"])
        self.assertEqual((f.label, f.tip), (i18n._("filter_for"), i18n._("filter_for_q")))
        self.press(p, key="filter_add", values={"words": "spoilers", "expires": "86400"})
        made = list(self.w.filters.values())[-1]
        self.assertEqual(made["expires_in"], 86400)
        row = self.page("silence").rows[0]
        self.assertIn(i18n._("filter_until", until="")[:3], row.line)
        self.press(self.page("silence"), key="filter_delete")
        self.press(self.page("silence"), key="filter_add",
                   values={"words": "x", "expires": "never"})  # unreadable: for good
        self.assertIsNone(list(self.w.filters.values())[-1]["expires_in"])
        self.view.hide_post("010").result(timeout=10)  # a filter of single posts: counted
        lines = [r.line for r in self.page("silence").rows]
        self.assertTrue(any(i18n._("posts_n", n=1) in x for x in lines), lines)

    def test_lists_replies_policy(self):
        p = self.page("lists")
        f = {x.name: x for x in p.form}["replies"]
        self.assertEqual([c[0] for c in f.choices], ["list", "followed", "none"])
        self.press(p, key="new", values={"title": "Friends", "replies": "followed"})
        lid = self.view.lists[0].id
        self.assertEqual(self.w.lists[lid]["replies_policy"], "followed")
        row = self.page("lists").rows[0]
        self.assertIn(i18n._("replies_policy_followed"), row.line)
        out = self.pl.act("lists", "replies", lid)  # followed → none
        self.assertIn(i18n._("replies_policy_none"), out.message)
        self.assertEqual(self.w.lists[lid]["replies_policy"], "none")
        self.pl.act("lists", "replies", lid)  # none → list
        self.assertEqual(self.w.lists[lid]["replies_policy"], "list")
        self.press(self.page("lists"), key="new", values={"title": "Other", "replies": "odd"})
        other = [x for x in self.view.lists if x.title == "Other"][0]
        self.assertEqual(self.w.lists[other.id]["replies_policy"], "list")  # the default

    def test_lists(self):
        p = self.page("lists")
        out = self.press(p, key="new", values={"title": "Friends", "exclusive": True})
        self.assertTrue(out.refresh)
        p = self.page("lists")
        self.assertEqual([r.title for r in p.rows], ["Friends"])
        lid = p.rows[0].key
        out = self.pl.act("lists", "rename", lid)  # first: a line to type
        self.assertTrue(out.ask)
        self.pl.act("lists", "rename", lid, answer="Mates")
        self.assertEqual(self.view.lists[0].title, "Mates")
        p = self.page("list_of", "B")
        self.press(p, key="toggle")
        self.assertIn(lid, self.view.lists_of("B"))
        p = self.page("list_people", lid)
        self.assertEqual([r.key for r in p.rows], ["B"])
        self.press(p, key="out")
        self.assertNotIn(lid, self.view.lists_of("B"))
        out = self.pl.act("lists", "delete", lid)  # "sure?" first
        self.assertTrue(out.confirm)
        self.pl.act("lists", "delete", lid, confirmed=True)
        self.assertEqual(self.view.lists, [])

    def test_search_requests_people(self):
        p = self.page("search", "bob")
        self.assertIn("account", [r.kind for r in p.rows])
        self.press(p, key="follow")
        self.assertIn("B", self.w.following)
        self.w.requests = [BOB]
        self.core.poll_once()
        p = self.page("requests")
        self.assertEqual([r.key for r in p.rows], ["B"])
        self.press(p, key="yes")

    def test_activity(self):
        st = self.w.statuses["030"]
        self.w.act("a1", "favourite", BOB, st, minute=1)
        self.w.act("a2", "favourite", scenario.ALICE, st, minute=2)
        self.core.poll_once()
        p = self.page("activity")
        self.assertEqual(len(p.rows), 1)  # two likes of one post: one row
        self.assertIn("alice", p.rows[0].title.lower() + p.rows[0].title)
        self.press(p, key="seen")

    def test_report_and_profile(self):
        p = self.page("report", "010")
        self.press(p, key="send", values={"category": "spam", "comment": "ads",
                                          "forward": True})
        self.assertEqual(len(self.w.reports), 1)
        p = self.page("profile_edit")
        vals = {f.name: f.value for f in p.form}
        vals.update(name="Мира Н.", bio="hello", field0_name="site", field0_value="x.example")
        out = self.press(p, key="save", values=vals)
        self.assertEqual(out.message, i18n._("profile_saved"))

    def test_help_pages(self):
        p = self.page("help")
        html = p.rows[0].title
        self.assertIn("<h1", html)
        self.assertNotIn("<script", html)
        for href in re.findall(r'href="([^"]+)"', html):
            self.assertRegex(href, r"^(fedtail:help/|https?:|mailto:|#)")
        self.assertIn("<h1", self.page("news").rows[0].title)

    def test_markdown(self):
        h = mdhtml.markdown_html("# T\n\na **b** `<x>` [l](https://e.x) [bad](javascript:x)\n\n"
                                 "- one\n- two\n\n| a | b |\n|---|---|\n| 1 | 2 |\n",
                                 href=lambda u: u)
        self.assertIn("<b>b</b>", h)
        self.assertIn("<code>&lt;x&gt;</code>", h)
        self.assertIn('<a href="https://e.x">l</a>', h)
        self.assertNotIn("javascript", h)
        self.assertIn("<li>two</li>", h)
        self.assertIn("<td>2</td>", h)

    def test_words_exist(self):
        src = (ROOT / "fedtail/frontends/common/places.py").read_text("utf-8")
        d = i18n._STRINGS["en"]
        keys = {k for k in re.findall(r'_\(\s*"([a-z0-9_.]+)"', src) if not k.endswith("_")}
        self.assertEqual(sorted(k for k in keys if k not in d), [])
        self.assertEqual([v for v in PLACES.values() if v not in d], [])


if __name__ == "__main__":
    unittest.main()


class ReadUpToTest(unittest.TestCase):
    """⋯ → "Read up to here", the same in Qt and GTK: by time, whichever way round."""

    def test_by_time_either_order(self):
        from fedtail.frontends.common.lane import read_up_to
        from fedtail.protocols.mastodon import adapter

        from .fakes import BOB, status
        posts = [adapter.post(status(i, BOB, minute=m, vis="public"), "t")
                 for i, m in (("010", 10), ("012", 12), ("020", 20))]
        self.assertEqual(sorted(read_up_to(posts, "012")), ["010", "012"])
        self.assertEqual(sorted(read_up_to(posts[::-1], "012")), ["010", "012"])
        self.assertEqual(read_up_to(posts, "999"), ["999"])
