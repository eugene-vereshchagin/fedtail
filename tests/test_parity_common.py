"""The places the web page and the terminal got for parity with the windows
(common/places.py, common/placesmore.py, common/profile.py): what the server can do,
its announcements, the notification policy, a profile's details and its older posts
from its own server, a tag on my profile and the lanes of tags, the order of the lists,
copying (Out.copy) the About, the federation's state and the probe, a new avatar."""

import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest import mock

from fedtail import i18n
from fedtail.core.view import View
from fedtail.frontends.common import placesmore
from fedtail.frontends.common import profile as prof
from fedtail.frontends.common.places import PLACES, Places, picture_file

from . import scenario
from .fakes import BOB, FakeApi, acct, status

_ = i18n._


def done(value=None, error=None):
    f = Future()
    if error is not None:
        f.set_exception(error)
    else:
        f.set_result(value)
    return f


class PlacesCase(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.core, self.w = scenario.make_core(self._tmp.name)
        self.addCleanup(self.core.shutdown)
        self.view = View(self.core)
        self.pl = Places(self.view)

    def act(self, place, key, data="", values=None):
        out = self.pl.act(place, key, data, values)
        self.assertEqual(out.error, "", (place, key))
        return out

    def buttons(self, page):
        return {b.label: b for r in page.rows for b in r.buttons}


class ProbeAndFederationTest(PlacesCase):
    def test_probe(self):
        page = self.pl.page("probe")
        self.assertEqual(page.title, _("probe_tab"))
        self.assertIn(_("probe_run"), self.buttons(page))  # never checked: one button
        self.assertIn("probe", dict(self.pl.menu()))
        self.act("probe", "run")
        page = self.pl.page("probe")
        b = self.buttons(page)
        self.assertIn(_("probe_again"), b)
        self.assertEqual(b[_("probe_copy")].tip, _("probe_copy_tip"))
        self.assertTrue(any(r.line.endswith("*") for r in page.rows))  # known, not asked
        self.assertIn("* " + _("probe_known_tip"), [r.title for r in page.rows])
        out = self.act("probe", "copy")
        self.assertIn("| " + _("probe_what"), out.copy)
        self.assertEqual(out.message, _("probe_copied"))
        self.core.cfg["ui"]["save_dir"] = self._tmp.name
        out = self.act("probe", "save")
        saved = list(Path(self._tmp.name).glob("fedtail-*-features.md"))
        self.assertEqual(len(saved), 1)
        self.assertIn(str(saved[0]), out.message)
        with mock.patch.object(self.core, "probe_server",
                               return_value=done(error=RuntimeError("down"))):
            out = self.pl.act("probe", "run")
        self.assertEqual(out.error, _("probe_failed", err="down"))
        with mock.patch.object(self.core, "auth", {}):
            self.assertEqual(self.pl._domain(), "server")

    def test_federation_tools(self):
        page = self.pl.page("federation")
        self.assertEqual(page.hint, _("info_head"))
        self.assertEqual(set(self.buttons(page)),
                         {_("fed_refresh"), _("fed_copy"), _("fed_reset")})
        self.assertTrue(self.act("federation", "refresh").refresh)
        out = self.act("federation", "copy")
        self.assertTrue(out.copy)
        self.assertEqual(out.message, _("fed_copied"))
        from fedtail.core import health
        with mock.patch.object(health.REC, "clear") as clear:
            self.assertTrue(self.act("federation", "reset").refresh)
        clear.assert_called_once()

    def test_about_copy(self):
        page = self.pl.page("about")
        self.assertIn(_("made_by"), [r.title for r in page.rows])
        out = self.act("about", "copy")
        self.assertTrue(out.copy.startswith("FedTail "))
        self.assertEqual(out.message, _("about_copied"))


class AnnouncementsTest(PlacesCase):
    def test_list_dismiss_react(self):
        self.w.announcements = [
            {"id": "a1", "content": "<p>first</p>", "published_at": "2099-10-14T10:00:00Z",
             "reactions": [{"name": "👍", "count": 2, "me": True},
                           {"name": ":blobcat:", "count": 0, "me": False}]},
            {"id": "a2", "content": "<p>second</p>", "reactions": []}]
        names = dict(self.pl.menu())
        self.assertIn("announcements", names)
        page = self.pl.page("announcements")
        self.assertEqual(page.hint, _("announce_more", n=1))
        b = self.buttons(page)
        self.assertEqual(b[_("announce_ok")].tip, _("tip_announce_ok"))
        self.assertIn("👍 2", b)  # mine: pressing takes it back
        self.assertEqual(b["👍 2"].act[2], "a1 0 👍")
        self.assertNotIn(":blobcat:", b)  # a custom one nobody used: not offered
        self.assertEqual(b["❤️"].tip, _("announce_react_tip"))
        self.act("announcements", "react", "a1 1 ❤️")
        self.assertEqual(self.w.reacted, [("a1", "❤️", True)])
        self.act("announcements", "dismiss", "a1")
        self.assertTrue(self.w.announcements[0]["read"])
        self.w.missing.add("announcement_reactions")
        self.core.unsupported.add("announcement_reactions") \
            if hasattr(self.core, "unsupported") else None
        with mock.patch.object(self.core, "supports", lambda f: f != "announcement_reactions"):
            page = self.pl.page("announcements")
        self.assertEqual(set(self.buttons(page)), {_("announce_ok")})
        self.core.cfg["ui"]["announcements"] = "off"
        self.assertNotIn("announcements", dict(self.pl.menu()))


class PolicyAndListsTest(PlacesCase):
    def test_notification_policy(self):
        self.w.policy = {"for_not_following": "accept", "for_not_followers": "filter",
                         "for_new_accounts": "drop", "for_private_mentions": "filter",
                         "for_limited_accounts": "filter"}
        page = self.pl.page("filtered")
        fields = {f.name: f for f in page.form}
        self.assertEqual(fields["for_new_accounts"].value, "drop")
        self.assertEqual(fields["for_not_following"].label, _("filtered_for_not_following"))
        self.assertEqual([c for c, _w in fields["for_new_accounts"].choices],
                         ["accept", "filter", "drop"])
        self.assertEqual(page.submit.act, ("filtered", "policy", ""))
        out = self.act("filtered", "policy", "", {"for_new_accounts": "accept",
                                                  "nonsense": "drop",
                                                  "for_not_followers": "maybe"})
        self.assertEqual(self.w.policy["for_new_accounts"], "accept")
        self.assertEqual(self.w.policy["for_not_followers"], "filter")
        self.assertTrue(out.message)
        self.assertEqual(self.act("filtered", "policy", "", {}).message, "")

    def test_lists_order_and_adding(self):
        self.w.lists = {"L1": {"title": "One", "exclusive": False, "members": set()},
                        "L2": {"title": "Two", "exclusive": False, "members": set()}}
        self.core._refresh_lists()
        page = self.pl.page("lists")
        b = page.rows[0].buttons
        self.assertEqual(b[-1].act, ("lists", "move", f"{page.rows[0].key} 1"))
        first = page.rows[0].key
        self.act("lists", "move", f"{first} 1")
        self.assertEqual(self.pl.page("lists").rows[1].key, first)
        # someone I don't follow: the server won't take them yet — said, and it waits
        page = self.pl.page("list_of", "B")
        self.assertIn(_("list_follow_first"), page.hint)
        with mock.patch.object(self.core, "set_in_list", return_value=done("pending")):
            out = self.act("list_of", "toggle", f"{first} B 0")
        self.assertEqual(out.message, _("list_pending"))
        with mock.patch.object(self.core, "relationship",
                               return_value=done(error=RuntimeError("x"))):
            self.assertIn(_("list_checking"), self.pl.page("list_of", "B").hint)

    def test_arts_mode_note(self):
        self.core.cfg["ui"]["arts_mode"] = True
        self.assertTrue(self.pl.page("silence").hint.startswith(_("tender_arts") + " · "))
        self.assertEqual(self.pl.page("silence", tab="muted").hint, _("tender_arts"))
        self.core.cfg["ui"]["arts_mode"] = False
        self.assertNotIn(_("tender_arts"), self.pl.page("silence").hint)


class TagsAndHelpTest(PlacesCase):
    def test_tag_on_my_profile_and_lanes_of_tags(self):
        page = self.pl.page("tag", "fediverse")
        b = self.buttons(page)
        self.assertEqual(b[_("tag_feature")].tip, _("tag_feature_tip"))
        self.act("tag", "feature", "1 fediverse")
        self.assertIn("fediverse", self.w.my_tags)
        self.assertIn(_("tag_unfeature"), self.buttons(self.pl.page("tag", "fediverse")))
        self.act("tag", "feature", "0 fediverse")
        self.assertNotIn("fediverse", self.w.my_tags)
        with mock.patch.object(self.core, "featured_tag_names",
                               return_value=done(error=RuntimeError("x"))):
            self.assertNotIn(_("tag_feature"), self.buttons(self.pl.page("tag", "x")))
        self.w.missing.add("featured_tags")
        with mock.patch.object(self.core, "supports", lambda f: f != "featured_tags"):
            self.assertNotIn(_("tag_feature"), self.buttons(self.pl.page("tag", "x")))
        # lanes of tags: a saved one goes from here, the config's stays there
        self.core.cfg["lanes"]["tag_groups"] = [{"name": "Cfg", "any": ["a", "b"]}]
        self.core.save_tag_group({"any": ["tbilisi", "georgia"]}, "Mine").result(timeout=10)
        page = self.pl.page("taglanes", "x")
        self.assertIn(_("tags_info"), [r.title for r in page.rows])
        save = next(b for r in page.rows for b in r.buttons if b.act[1] == "add")
        self.assertEqual(save.tip, _("tags_save_tip"))
        rows = {r.title: r for r in page.rows}
        self.assertEqual(rows["Cfg"].line, _("tags_in_config"))
        self.assertEqual(rows["Cfg"].buttons, ())
        drop = rows["Mine"].buttons[0]
        self.assertEqual(drop.label, _("tags_drop"))
        self.act(*drop.act)
        self.assertNotIn("Mine", [r.title for r in self.pl.page("taglanes", "x").rows])

    def test_help_search(self):
        page = self.pl.page("help")
        self.assertEqual(page.form[0].label, _("help_search"))
        out = self.act("help", "search", "", {"q": "theme"})
        self.assertEqual(out.open, {"page": "help", "arg": "?theme"})
        self.assertEqual(self.act("help", "search", "", {"q": " "}).open["arg"], "index")
        found = self.pl.page("help", "?theme")
        self.assertTrue(found.hint.startswith(_("help_found", n=1).split("1")[0]))
        self.assertIn(_("help_deep"), [r.title for r in found.rows])  # the deep dive too
        name = next(r.key for r in found.rows if r.kind == "item")
        self.assertEqual(self.act("help", "open", name).open, {"page": "help", "arg": name})
        self.assertEqual(self.pl.page("help", "?qqqzzznothing").hint, _("help_none"))


class ProfileInfoTest(PlacesCase):
    def account(self, **extra):
        a = dict(BOB, created_at="2020-01-02T00:00:00Z", statuses_count=7,
                 followers_count=3, following_count=2, **extra)
        return mock.patch.object(FakeApi, "get", lambda _s, path, params=None, timeout=30: a)

    def test_the_head(self):
        self.w.familiar["B"] = [acct(f"F{i}", f"f{i}@x.test") for i in range(7)]
        self.w.featured["B"] = {"tags": [{"name": "art", "url": "https://x/tags/art"}],
                                "people": [acct("P", "pal@x.test")]}
        pin = status("070", BOB, minute=7, text="pinned one", vis="public")
        self.w.add(pin)
        moved = acct("M", "bob@new.example")
        with self.account(moved=moved), \
                mock.patch.object(FakeApi, "pinned", lambda _s, _a: [pin]), \
                mock.patch.object(self.core, "relationship", return_value=done(
                    {"id": "B", "following": True})):
            page = self.pl.page("profile_info", "B")
        texts = [r.title for r in page.rows]
        self.assertIn(_("card_counts", posts=7, followers=3, following=2), texts)
        self.assertTrue(any(t.startswith(_("card_since", when="")[:5]) for t in texts))
        self.assertIn("✓ " + _("following_them"), texts)
        moved_row = next(r for r in page.rows if r.key == "moved")
        self.assertIn("bob@new.example", moved_row.title)
        self.assertEqual([b.act[1] for b in moved_row.buttons], ["open", "follow"])
        fam = next(r for r in page.rows if r.key == "familiar").title
        self.assertIn(_("and_more", n=2), fam)
        self.assertIn(_("featured_tags") + " #art", texts)
        self.assertIn(_("featured_people"), texts)
        self.assertIn("📌 " + _("pinned"), texts)
        self.assertIn("pin:070", [r.key for r in page.rows])
        self.assertIn(_("profile_posts"), texts)
        self.assertEqual(page.more.act, ("profile_info", "origin", "B"))
        host = page.more.tip[len(_("older_from_origin_tip", host="")):]  # their server
        self.assertTrue(host)
        self.assertEqual(page.more.label, _("older_from_origin", host=host))

    def test_nothing_breaks_when_parts_fail(self):
        err = done(error=RuntimeError("x"))
        with mock.patch.object(self.core, "relationship", return_value=err), \
                mock.patch.object(self.core, "familiar", return_value=err), \
                mock.patch.object(self.core, "featured", return_value=err), \
                mock.patch.object(self.core, "pinned", return_value=err):
            page = self.pl.page("profile_info", "B")
        self.assertEqual([r.key for r in page.rows][:1], ["counts"])
        local = acct("L", "local")
        with self.account(**local), mock.patch.object(self.core, "supports",
                                                      lambda f: f != "familiar"):
            page = self.pl.page("profile_info", "L")
        self.assertIsNone(page.more)  # one of my server's: nothing older elsewhere

    def test_older_posts_from_their_server(self):
        out = self.act("profile_info", "origin", "B")
        self.assertEqual(out.open, {"page": "profile_info", "arg": "B", "cursor": "start"})
        old = status("090", BOB, minute=1, text="old", vis="public")
        with mock.patch.object(self.core, "older_from_origin",
                               return_value=done(([old], "NEXT"))) as older:
            page = self.pl.page("profile_info", "B", cursor="start")
        self.assertIsNone(older.call_args[0][1])
        self.assertIn(_("older_from_origin_note"), page.hint)
        self.assertEqual([r.key for r in page.rows], ["090"])
        self.assertEqual(page.more.act, ("profile_info", "origin", "B NEXT"))
        self.assertEqual(self.act(*page.more.act).open["cursor"], "NEXT")
        with mock.patch.object(self.core, "older_from_origin", return_value=done(([], None))):
            page = self.pl.page("profile_info", "B", cursor="NEXT")
        self.assertIsNone(page.more)
        self.assertEqual(page.empty, _("no_older"))

    def test_the_profile_button(self):
        acc = self.view.account("B").result(timeout=10)
        acts = [a.key for a in prof.actions(acc, None, False, self.core.cfg,
                                            self.core.supports, details=True)]
        self.assertEqual(acts[-1], "details")
        self.assertNotIn("details", [a.key for a in prof.actions(
            acc, None, False, self.core.cfg, self.core.supports)])
        host = mock.Mock()
        prof.do("details", acc, None, self.view, host, lambda _r: None)
        host._place.assert_called_once_with("profile_info", "B")
        self.assertIn("profile_info", PLACES)


class PicturesTest(PlacesCase):
    def test_a_new_avatar(self):
        page = self.pl.page("profile_edit")
        kinds = {f.name: f.kind for f in page.form}
        self.assertEqual((kinds["avatar"], kinds["header"]), ("file", "file"))
        header = next(f for f in page.form if f.name == "header")
        self.assertIn(_("no_header"), header.label)
        pic = Path(self._tmp.name) / "me.png"
        pic.write_bytes(b"\x89PNG")
        values = {f.name: f.value for f in page.form}
        values["avatar"] = str(pic)
        with mock.patch.object(FakeApi, "update_credentials", create=True,
                               side_effect=lambda **kw: dict(BOB, **{"id": "ME"})) as upd:
            self.act("profile_edit", "save", "", values)
        self.assertEqual(upd.call_args.kwargs["avatar"], str(pic))
        self.assertNotIn("header", upd.call_args.kwargs)
        values["avatar"] = "/no/such/picture.png"
        self.assertTrue(self.pl.act("profile_edit", "save", "", values).error)

    def test_picture_file(self):
        self.assertIsNone(picture_file(""))
        self.assertIsNone(picture_file("   "))
        self.assertIsNone(picture_file(None))
        with self.assertRaises(ValueError):
            picture_file("/nowhere/x.png")
        self.assertEqual(picture_file(__file__), __file__)


class HelpersTest(unittest.TestCase):
    def test_host(self):
        self.assertEqual(placesmore._host("https://Example.Test/x"), "example.test")
        self.assertEqual(placesmore._host(None), "")


if __name__ == "__main__":
    unittest.main()


class WebHandlersTest(unittest.TestCase):
    """The web page's side: Out.copy reaches the page; a file field's upload token
    becomes the file's path for the place."""

    def setUp(self):
        from fedtail.frontends.web import server as web
        i18n.setup("en")
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.core, self.w = scenario.make_core(self._tmp.name)
        self.addCleanup(self.core.shutdown)
        srv = web.make_server(self.core, "127.0.0.1", 0, web.load_key(
            self.core.paths.data_dir))
        self.addCleanup(srv.server_close)
        self.web = srv.web

    def test_copy_and_a_picture(self):
        got = self.web.place_act({"act": ["about", "copy", ""]})
        self.assertTrue(got["copy"].startswith("FedTail "))
        token = self.web.upload(b"\x89PNG", "me.png")["token"]
        seen = {}

        def save(_self, _d, values, _c, _a):
            seen.update(values)
            from fedtail.frontends.common.places import Out
            return Out()
        with mock.patch.object(Places, "_a_profile_edit_save", save):
            self.web.place_act({"act": ["profile_edit", "save", ""],
                                "values": {"avatar": {"upload": token}, "name": "x"}})
        self.assertEqual(seen["avatar"], str(self.web.upload_path(token)))
        self.assertEqual(seen["name"], "x")
        acc = self.web.account("B")
        self.assertEqual(acc["actions"][-1]["key"], "details")
        out = self.web.profile_act("B", "details")
        self.assertEqual(out["open"], {"page": "profile_info", "arg": "B", "tab": ""})


try:
    import textual  # noqa: F401
    HAVE_TEXTUAL = True
except ImportError:
    HAVE_TEXTUAL = False


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class TuiCopyTest(unittest.IsolatedAsyncioTestCase):
    async def test_copy_from_a_place(self):
        from fedtail.frontends.tui.app import FedtailApp
        from fedtail.frontends.tui.screens import PlaceScreen
        i18n.setup("en")
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        core, _w = scenario.make_core(tmp.name)
        self.addCleanup(core.shutdown)
        app = FedtailApp(core)
        copied = []
        async with app.run_test(size=(120, 40)) as pilot:
            app.copy_to_clipboard = copied.append
            app.open_thing({"page": "about"})
            for _i in range(100):
                await pilot.pause(0.05)
                if isinstance(app.screen, PlaceScreen) and app.screen.page is not None:
                    break
            btn = next(b for r in app.screen.page.rows for b in r.buttons
                       if b.act[:2] == ("about", "copy"))
            await app.screen.act(btn)
            self.assertTrue(copied and copied[0].startswith("FedTail "))
            app.copy_to_clipboard = None  # a terminal without a clipboard: still fine
            await app.screen.act(btn)
            await pilot.pause(0.05)
