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
        for key in ("lang_check", "link_quote", "send_in_background", "scheduled_to_draft",
                    "drafts_place"):
            self.assertIs(cfg["post"][key], False, key)


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
        self.assertNotIn("drafts", [n for n, _t in places.menu()])
        core.cfg["post"]["drafts_place"] = True
        self.assertIn("drafts", [n for n, _t in places.menu()])
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
        self.srv = web.make_server(self.core, "127.0.0.1", 0,
                                   web.load_key(self.core.paths.data_dir))
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


if __name__ == "__main__":
    unittest.main()
