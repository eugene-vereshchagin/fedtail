"""A click on a post's tag (feed.tag_click): as its author writes it — their posts with
the tag, as Point's tags are each blog's own — or everywhere; a right click offers both
and muting it."""

import types
import unittest
from unittest import mock

from fedtail import i18n
from fedtail.core import links as core_links
from fedtail.frontends.common import links
from fedtail.frontends.common.places import Places

from . import test_cli
from .fakes import BOB, NEWS, status
from .test_core import TmpDir


class TagLinkTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_the_link_names_the_author(self):
        html = '<a href="https://x.test/tags/cats" class="mention hashtag">#<span>cats</span></a>'
        st = {"id": "1", "account": {"id": "A1"}, "tags": [{"name": "cats"}]}
        got = core_links.in_app(html, st)
        self.assertIn('href="fedtail:tag/cats%20by%3AA1"', got)
        self.assertIn('href="fedtail:tag/cats"', core_links.in_app(html, {"tags": []},
                                                                   tags=["cats"]))

    def _open(self, url, click):
        host = mock.Mock()
        view = types.SimpleNamespace(cfg={"feed": {"tag_click": click}})
        links.Links(view, host).open(url)
        return host.open_tag.call_args.args[0]

    def test_a_click_goes_by_the_setting(self):
        url = core_links.tag_link("cats", "A1")
        self.assertEqual(self._open(url, "author"), "cats by:A1")
        self.assertEqual(self._open(url, "everywhere"), "cats")
        self.assertEqual(self._open(core_links.tag_link("cats"), "author"), "cats")

    def test_the_right_click_menu(self):
        menu = links.tag_menu(core_links.tag_link("cats", "A1"))
        self.assertEqual([w for w, _u in menu], [i18n._("tag_by_author", tag="cats"),
                                                 i18n._("tag_everywhere_n", tag="cats"),
                                                 i18n._("tag_mute_n", tag="cats")])
        self.assertEqual(self._open(menu[0][1], "everywhere"), "cats by:A1")
        self.assertEqual(self._open(menu[1][1], "author"), "cats")
        self.assertEqual(links.tag_menu("https://x.test/"), [])


class AuthorTagPlaceTest(TmpDir):
    make = test_cli.CliTest.make

    def test_the_place_of_a_tag_by_one_author(self):
        i18n.setup("en")
        core, w = self.make()
        for i, (who, tags) in enumerate([(BOB, ["cats"]), (BOB, ["dogs"]), (NEWS, ["cats"])]):
            st = status(f"00{i}", who, minute=i, text="#" + tags[0], vis="public")
            st["tags"] = [{"name": t} for t in tags]
            w.add(st, home=True)
        core.connect().result()
        from fedtail.core.view import View
        page = Places(View(core)).page("tag", f"cats by:{BOB['id']}")
        self.assertIn("cats", page.title)
        acts = [b.act for b in page.rows[0].buttons]
        self.assertIn(("tag", "open", "cats"), acts)  # the tag everywhere, on top
        self.assertEqual([r.key for r in page.rows if r.kind == "post"], ["000"])


if __name__ == "__main__":
    unittest.main()
