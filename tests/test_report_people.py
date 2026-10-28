"""People from the competitors' report: my own names for them (feed.aliases), "Not in
Home" (feed.home_hide), both carried by sync.people; why a post is in Home (a followed
tag, card.why_home) and the post's JSON (debug.raw_json)."""

import json

from fedtail import i18n
from fedtail.core import config
from fedtail.core.view import View
from fedtail.frontends.common import profile
from fedtail.model import Relationship
from tests.fakes import BOB, status

from .test_custom import FreeBase
from .test_sync import Devices, need_crypto


class AliasTest(FreeBase):
    def setUp(self):
        super().setUp()
        i18n.setup("en")

    def test_my_name_for_them(self):
        core, w = self.make([])
        w.add(status("001", BOB, minute=1, vis="public"), home=True)
        core.connect().result()
        core.poll_once()
        view = View(core)
        raw = core.store.get_status("001")
        theirs = view.entry(raw).author.name
        core.set_alias(BOB["id"], "  Bobby the builder ").result()
        self.assertEqual(core.people_aliases(), {BOB["id"]: "Bobby the builder"})
        self.assertEqual(view.entry(raw).author.name, theirs)  # off: their own name
        core.cfg["feed"]["aliases"] = True
        self.assertEqual(view.entry(raw).author.name, "Bobby the builder")
        self.assertEqual(view.acc(raw["account"]).name, "Bobby the builder")
        core.set_alias(BOB["id"], "").result()
        self.assertEqual(view.entry(raw).author.name, theirs)
        self.assertIn("lanes_updated", [n for n, _p in self.events])

    def test_the_profile_button_only_when_on(self):
        cfg, _w = config.validate({})
        self.assertFalse(cfg["feed"]["aliases"])

        from fedtail.protocols.mastodon import adapter
        who = adapter.account(dict(BOB), None)
        keys = lambda c: [a.key for a in profile.actions(who, Relationship(), False, c,  # noqa: E731
                                                         lambda *_a: True)]
        self.assertNotIn("alias", keys(cfg))
        cfg["feed"]["aliases"] = True
        self.assertIn("alias", keys(cfg))
        self.assertNotIn("alias", [a.key for a in profile.actions(who, Relationship(), True,
                                                                   cfg, lambda *_a: True)])


class WhyHomeTest(FreeBase):
    def test_a_followed_tag_says_why(self):
        core, w = self.make([])
        core.connect().result()
        st = status("001", BOB, minute=1, vis="public")
        st["tags"] = [{"name": "Linux"}]
        core._following = set()
        core._followed_tag_names = {"linux"}
        self.assertEqual(core.came_by_tag(st), "Linux")
        core._following = {BOB["id"]}
        self.assertEqual(core.came_by_tag(st), "")  # followed anyway: nothing to say
        cfg, _w = config.validate({})
        self.assertFalse(cfg["feed"]["why_home"])


class RawJsonTest(FreeBase):
    def test_the_post_as_the_server_gave_it(self):
        core, w = self.make([])
        w.add(status("001", BOB, minute=1, vis="public"), home=True)
        core.connect().result()
        core.poll_once()
        got = json.loads(core.raw_json("001"))
        self.assertEqual(got["id"], "001")
        self.assertEqual(core.raw_json("nope"), "")
        cfg, _w = config.validate({})
        self.assertFalse(cfg["debug"]["raw_json"])


@need_crypto
class PeopleSyncTest(Devices):
    def test_names_and_home_travel(self):
        desk = self.device("desk2", self.world, people=True)
        phone = self.device("phone2", self.world, people=True)
        desk.set_alias("B", "Bobby").result()
        desk.hide_from_home("B").result()
        desk.sync_now()
        phone.sync_join(desk.sync_key())
        phone.sync_now()
        self.assertEqual(phone.people_aliases(), {"B": "Bobby"})
        self.assertEqual(phone.hidden_home(), {"B"})

    def test_off_by_default(self):
        self.desk.set_alias("B", "Bobby").result()
        self.desk.hide_from_home("B").result()
        self.assertEqual(self.desk.store.sync_pending_count(), 0)
        cfg, _w = config.validate({})
        self.assertFalse(cfg["sync"]["people"])


if __name__ == "__main__":
    import unittest
    unittest.main()


class NickColorTest(FreeBase):
    def setUp(self):
        super().setUp()
        i18n.setup("en")

    def test_their_name_in_my_colour(self):
        core, w = self.make([])
        w.add(status("001", BOB, minute=1, vis="public"), home=True)
        core.connect().result()
        core.poll_once()
        view = View(core)
        raw = core.store.get_status("001")
        core.set_nick_color(BOB["id"], "green").result()
        self.assertEqual(core.people_colors(), {BOB["id"]: "#2e7d32"})
        self.assertEqual(view.entry(raw).author.color, "")  # off: as before
        core.cfg["feed"]["nick_colors"] = True
        self.assertEqual(view.entry(raw).author.color, "#2e7d32")
        core.set_nick_color(BOB["id"], "#AABBCC".lower()).result()
        self.assertEqual(view.acc(raw["account"]).color, "#aabbcc")
        with self.assertRaises(ValueError):
            core.set_nick_color(BOB["id"], "sort of blue")
        core.set_nick_color(BOB["id"], "").result()
        self.assertEqual(view.entry(raw).author.color, "")
        cfg, _w = config.validate({})
        self.assertFalse(cfg["feed"]["nick_colors"])
        from fedtail.protocols.mastodon import adapter
        who = adapter.account(dict(BOB), None)
        cfg["feed"]["nick_colors"] = True
        self.assertIn("nick_color", [a.key for a in profile.actions(
            who, Relationship(), False, cfg, lambda *_a: True)])

    def test_the_interfaces_draw_it(self):
        try:
            from fedtail.frontends.tui.app import render
        except ImportError:  # the CI's Debian job has no Textual
            self.skipTest("needs textual")
        from fedtail.frontends.tui.model import Shown
        from fedtail.frontends.web.server import account_json
        from fedtail.protocols.mastodon import adapter
        who = adapter.account(dict(BOB, _fedtail_color="#123456"), None)
        self.assertEqual(account_json(who)["color"], "#123456")
        shown = Shown(head=[("who", "@bob")], colors={"who": "#123456"})
        self.assertEqual(str(render(shown).spans[0].style), "bold #123456")
