"""Writing from the competitors' report, every bit behind post.* and off by default: the
language check before sending, a post's link becoming a quote, the editor closing at once
(the post going in the background), a scheduled post back to the editor, and Drafts."""

import time
import unittest

from fedtail import i18n
from fedtail.core import config
from fedtail.core.view import View
from fedtail.frontends.common import compose as cc
from fedtail.frontends.common.places import Places
from tests.fakes import BOB, status

from . import test_parity_web
from .test_custom import FreeBase
from .test_sync import TmpDir

GEORGIAN = "გამარჯობა მეგობრებო, დღეს თბილისში ძალიან ლამაზი ამინდია და ქალაქი სავსეა"


class OffByDefaultTest(unittest.TestCase):
    def test_every_key_is_off(self):
        cfg, _w = config.validate({})
        for key in ("lang_check", "link_quote", "send_in_background", "scheduled_to_draft"):
            self.assertIs(cfg["post"][key], False, key)
        self.assertIs(cfg["post"]["drafts_place"], True)  # on since the users looked for it


class LangCheckTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")
        self.cfg, _w = config.validate({"post": {"lang_check": True, "language": "en"}})

    def test_another_script_is_told(self):
        self.assertEqual(cc.lang_mismatch(self.cfg, GEORGIAN, "en"), "ka")
        self.assertEqual(cc.lang_mismatch(self.cfg, GEORGIAN, ""), "ka")  # "as in settings"
        self.assertIsNone(cc.lang_mismatch(self.cfg, GEORGIAN, "ka"))
        self.assertIsNone(cc.lang_mismatch(self.cfg, "hello there", "en"))  # unsure
        title, text, switch, anyway = cc.lang_question("ka", "en")
        self.assertIn("(ka)", text)
        self.assertIn("(en)", text)
        self.assertIn("(ka)", switch)
        self.cfg["post"]["lang_check"] = False
        self.assertIsNone(cc.lang_mismatch(self.cfg, GEORGIAN, "en"))

    def test_links_and_names_are_not_words(self):
        text = "@bob@social.example #tbilisi https://example.test/გამარჯობა-მეგობრებო ok"
        self.assertIsNone(cc.lang_mismatch(self.cfg, text, "en"))


class LinkQuoteTest(FreeBase):
    def test_a_post_link_at_the_end(self):
        core, w = self.make([])
        theirs = w.add(status("050", BOB, minute=1, vis="public"))
        theirs["quote_approval"] = {"current_user": "automatic"}
        core.connect().result()
        url = theirs["url"]
        core.post("look at this " + url, "public").result()
        self.assertEqual(w.extras[-1]["quote"], None)  # off: a link stays a link
        core.cfg["post"]["link_quote"] = True
        core.post("look at this " + url, "public").result()
        self.assertEqual(w.extras[-1]["quote"], "050")
        self.assertEqual(w.posted[-1][0], "look at this")
        theirs["quote_approval"] = {"current_user": "denied"}
        core.post("and again " + url, "public").result()
        self.assertEqual(w.extras[-1]["quote"], None)  # the author says no: a link
        self.assertIn(url, w.posted[-1][0])


class PlacesTest(FreeBase):
    def setUp(self):
        super().setUp()
        i18n.setup("en")

    def test_scheduled_back_to_the_editor(self):
        core, w = self.make([])
        core.connect().result()
        core.post("later, please", "public", scheduled_at="2099-12-01T10:00:00.000Z").result()
        places = Places(View(core))
        row = places.page("scheduled").rows[0]
        self.assertEqual([b.act[1] for b in row.buttons], ["cancel"])  # off: as before
        core.cfg["post"]["scheduled_to_draft"] = True
        row = places.page("scheduled").rows[0]
        self.assertEqual([b.act[1] for b in row.buttons], ["edit", "cancel"])
        out = places.act("scheduled", "edit", row.key)
        self.assertEqual(out.compose, {"text": "later, please"})
        self.assertEqual(w.scheduled, [])  # off the schedule

    def test_drafts(self):
        core, w = self.make([])
        core.connect().result()
        places = Places(View(core))
        self.assertIn("drafts", [n for n, _t in places.menu()])
        core.cfg["post"]["drafts_place"] = False
        self.assertNotIn("drafts", [n for n, _t in places.menu()])
        core.cfg["post"]["drafts_place"] = True
        core.save_draft("new", {"text": "a new one"})
        time.sleep(0.01)
        core.save_draft("reply:002", {"text": "an answer"})
        page = places.page("drafts")
        self.assertEqual([r.key for r in page.rows], ["reply:002", "new"])
        self.assertEqual(places.act("drafts", "open", "new").compose, {"text": "a new one"})
        self.assertEqual(places.act("drafts", "open", "reply:002").open, {"thread": "002"})
        self.assertTrue(places.act("drafts", "delete", "new").confirm)
        places.act("drafts", "delete", "new", confirmed=True)
        self.assertIsNone(core.get_draft("new"))

    def test_several_new_drafts(self):
        """"New draft" sets the new post's draft aside; Drafts → Open brings one back and
        sets aside what the editor held."""
        core, w = self.make([])
        core.connect().result()
        places = Places(View(core))
        self.assertIsNone(core.shelve_draft("new"))  # nothing to keep
        core.save_draft("new", {"text": "first", "cw": "", "media": []})
        first = core.shelve_draft("new")
        self.assertTrue(first.startswith("new:"))
        self.assertIsNone(core.get_draft("new"))
        self.assertIsNone(core.shelve_draft("reply:002"))  # a reply's stays its post's
        self.assertFalse(core.shelvable("reply:002"))
        time.sleep(0.01)
        core.save_draft("new", {"text": "second", "cw": "", "media": []})
        out = places.act("drafts", "open", first)
        self.assertEqual(out.compose, {"text": "first"})
        self.assertEqual(core.get_draft("new")["text"], "first")
        kept = {k: d["text"] for k, d, _u in core.drafts()}
        self.assertEqual(sorted(kept.values()), ["first", "second"])
        self.assertNotIn(first, kept)
        rows = places.page("drafts").rows
        self.assertEqual({r.title for r in rows}, {i18n._("draft_new")})  # both new posts


class WebWritingTest(TmpDir):
    make = test_parity_web.ParityWebTest.make  # its world, not its tests
    req = test_parity_web.ParityWebTest.req

    def setUp(self):
        import threading

        from fedtail.frontends.web import server as web
        super().setUp()
        i18n.setup("en")
        self.core, self.w = self.make()
        self.w.add(status("001", BOB, minute=1, vis="public"), home=True)
        self.core.connect().result()
        self.core.poll_once()
        self.key = web.load_key(self.core.paths.data_dir)
        self.srv = web.make_server(self.core, "127.0.0.1", 0, self.key)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def test_the_page_is_asked_about_the_language(self):
        webs = self.srv.web
        webs.core.cfg["post"]["lang_check"] = True
        got = webs.post({"text": GEORGIAN, "lang": "en"})
        self.assertEqual(got["ask_lang"]["lang"], "ka")
        self.assertTrue(webs.post({"text": GEORGIAN, "lang": "en", "lang_ok": True})["id"])

    def test_sent_in_the_background(self):
        webs = self.srv.web
        webs.core.cfg["post"]["send_in_background"] = True
        got = webs.post({"text": "off it goes"})
        self.assertTrue(got["background"])
        for _i in range(100):
            if any(p[0] == "off it goes" for p in self.w.posted):
                break
            time.sleep(0.02)
        self.assertIn("off it goes", [p[0] for p in self.w.posted])
        for _i in range(100):  # sent: the draft kept meanwhile is gone
            if webs.core.get_draft("new") is None:
                break
            time.sleep(0.02)
        self.assertIsNone(webs.core.get_draft("new"))

    def test_my_name_for_them_from_the_page(self):
        """The profile's "My name for them" and "Name colour" (feed.aliases,
        feed.nick_colors) on the page and the phone: not let through before (21.11)."""
        webs = self.srv.web
        webs.core.cfg["feed"].update(aliases=True, nick_colors=True)
        bob = BOB["id"]
        keys = [a["key"] for a in webs.account(bob)["actions"]]
        self.assertIn("alias", keys)
        self.assertIn("nick_color", keys)
        self.assertIn("ask", webs.profile_act(bob, "alias"))  # a line to type first
        webs.profile_act(bob, "alias", answer="Bobby")
        self.assertEqual(webs.core.people_aliases().get(bob), "Bobby")
        webs.profile_act(bob, "nick_color", answer="#ff0000")

    def test_pinned_under_media_by_one_rule(self):
        """A profile's "Media": the pinned posts with pictures on top — the windows put
        every pinned post there, the page none (21.11)."""
        webs = self.srv.web
        bob = BOB["id"]
        plain = self.w.add(status("060", BOB, minute=2, vis="public", text="words"))
        pic = self.w.add(status("061", BOB, minute=3, vis="public", text="a picture"))
        pic["media_attachments"] = [{"id": "m1", "type": "image", "url": "https://x.test/a.png",
                                     "preview_url": "https://x.test/a.png"}]
        plain["pinned"] = pic["pinned"] = True
        pinned = lambda show: [p["id"] for p in webs.account(bob, show)["posts"]  # noqa: E731
                               if p.get("pinned")]
        self.assertEqual(sorted(pinned("posts")), ["060", "061"])
        self.assertEqual(pinned("media"), ["061"])

    def test_read_as_it_opens_the_core_says_what(self):
        """read.mark_read = "on_open": the page and the phone take what to read from the
        core — the phone read only on scrolling (21.11)."""
        webs = self.srv.web
        self.w.add(status("070", BOB, minute=7, vis="public", text="new one"), home=True)
        self.core.poll_once()
        webs.core.cfg["read"]["mark_read"] = "on_scroll"
        self.assertEqual(webs.lane("home")["read_on_open"], [])
        webs.core.cfg["read"]["mark_read"] = "on_open"
        self.assertIn("070", webs.lane("home")["read_on_open"])
        self.assertEqual(webs.lane("home", keep=True)["read_on_open"], [])  # standing there

    def test_no_reply_context_when_switched_off(self):
        """feed.show_reply_context = false: no "in reply to" line over a reply on the
        page or the phone either (they drew it always: 21.11)."""
        webs = self.srv.web
        self.w.add(status("080", BOB, "001", BOB["id"], minute=8, vis="public",
                          text="an answer"), home=True)
        self.core.poll_once()
        reply = lambda: next(p for p in webs.lane("unsorted")["posts"]  # noqa: E731
                             if p["id"] == "080")
        for _i in range(100):  # its parent asked and stored
            if "context" in reply():
                break
            time.sleep(0.02)
        self.assertIn("context", reply())
        webs.core.cfg["feed"]["show_reply_context"] = False
        self.assertNotIn("context", reply())

    def test_jump_to_the_newest_the_core_says_when(self):
        """feed.on_new = "jump_to_newest": the page and the phone are told to go to the
        newest end when new cards came (Qt alone went: 21.11)."""
        webs = self.srv.web
        webs.core.cfg["feed"]["on_new"] = "jump_to_newest"
        self.assertFalse(webs.lane("home")["jump"])  # opened: where reading starts
        self.assertFalse(webs.lane("home", keep=True)["jump"])  # nothing new
        self.w.add(status("090", BOB, minute=9, vis="public", text="newer"), home=True)
        self.core.poll_once()
        self.assertTrue(webs.lane("home", keep=True)["jump"])
        webs.core.cfg["feed"]["on_new"] = "keep_position"
        self.w.add(status("091", BOB, minute=10, vis="public", text="newest"), home=True)
        self.core.poll_once()
        self.assertFalse(webs.lane("home", keep=True)["jump"])

    def test_the_editor_draft_is_the_cores(self):
        """The page keeps its editor as a draft of the core's (post.drafts_autosave,
        post.autosave_ms), the whole of it, gone once the post is out; "⏰ Later" by
        post.schedule — the page kept the text alone in the browser (21.11)."""
        webs = self.srv.web
        facts = webs.editor_facts()
        self.assertTrue(facts["schedule"])
        self.assertEqual(facts["autosave_ms"], 700)
        webs.core.cfg["post"].update(schedule=False, autosave_ms=50)
        facts = webs.editor_facts()
        self.assertFalse(facts["schedule"])
        self.assertEqual(facts["autosave_ms"], 100)  # never less: a draft a key
        st = webs.draft_start()
        self.assertEqual(st["key"], "new")
        webs.draft_save("new", {"text": "half", "cw": "careful", "visibility": "public",
                                "language": "en"})
        again = webs.draft_start()
        self.assertTrue(again["restored"])
        self.assertEqual((again["text"], again["cw"], again["language"]),
                         ("half", "careful", "en"))
        webs.post({"text": "half and done", "cw": "careful"})
        self.assertIsNone(webs.core.get_draft("new"))  # out: no draft left
        webs.draft_save("new", {"text": "another"})
        webs.draft_drop("new")  # "Discard"
        self.assertIsNone(webs.core.get_draft("new"))

    def test_the_page_takes_the_font_settings(self):
        """ui.fonts, ui.font, ui.mono_font, ui.font_size on the page as in the windows
        (it took the theme's family whatever they said: 21.11)."""
        webs = self.srv.web
        ui = webs.core.cfg["ui"]
        ui.update(fonts="custom", font="Inter, Noto Sans", mono_font="Courier", font_size=13)
        css = webs.theme_css()
        self.assertIn("font-family: Inter, Noto Sans;", css)
        self.assertIn("font-family: Courier, ui-monospace", css)
        self.assertIn(".post .body { font-size: 13pt; }", css)
        ui.update(fonts="system", font_size=0)
        css = webs.theme_css()
        self.assertNotIn("Inter", css)
        self.assertNotIn("font-size", css)
        ui.update(font="x; } body { color: red")  # a font name, nothing else
        ui["fonts"] = "custom"
        self.assertNotIn("color: red", webs.theme_css())

    def test_web_push_says_what_privacy_lets(self):
        """notify.privacy reaches Web Push: the service worker is told it (it showed the
        server's whole text whatever the setting said: 21.11)."""
        webs = self.srv.web
        js = self.req("/sw.js")[2]
        self.assertTrue(js.startswith('const PRIVACY = "full";'))
        webs.core.cfg["notify"]["privacy"] = "count"
        js = self.req("/sw.js")[2]
        self.assertTrue(js.startswith('const PRIVACY = "count";'))
        self.assertIn('privacy === "full" ? String(n.body', js)

    def test_the_page_is_told_the_window_switches(self):
        """ui.image_viewer = "browser" and ui.merge set in the config reach the page: it
        opened its own viewer, and offered a merge switch that changed nothing (21.11)."""
        webs = self.srv.web
        me = webs.me()
        self.assertEqual((me["image_viewer"], me["merge_pinned"]), ("internal", False))
        webs.core.cfg["ui"].update(image_viewer="browser", merge=["all"])
        me = webs.me()
        self.assertEqual((me["image_viewer"], me["merge_pinned"]), ("browser", True))

    def test_a_failure_in_the_background_keeps_the_text(self):
        """The editor is gone at once: with post.drafts_autosave off, the draft meant to
        hold the text was never written, and a failure lost it (21.11)."""
        webs = self.srv.web
        webs.core.cfg["post"].update(send_in_background=True, drafts_autosave=False)
        from unittest import mock

        from fedtail.protocols.mastodon.api import ApiError

        from .fakes import FakeApi
        with mock.patch.object(FakeApi, "post_status", side_effect=ApiError(422, "no")):
            self.assertTrue(webs.post({"text": "not lost"})["background"])
            for _i in range(200):  # failed: said on the page
                if any(n.get("title") == i18n._("send_failed") for _s, n in webs.note_log):
                    break
                time.sleep(0.02)
            else:
                self.fail("no failure said")
        self.assertEqual((webs.core.get_draft("new") or {}).get("text"), "not lost")


if __name__ == "__main__":
    unittest.main()
