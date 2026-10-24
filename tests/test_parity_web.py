"""The web page as the windows (docs/src/parity.toml): the sidebar's sections, a thread's
head, find deeper and in every lane, a poll's results, the editor's extras (preview,
another language, the chain and #CamelCase line, a picture's focus, the alt reminder),
"received by" and the viewer's Save — the server's side, offline."""

import json
import shutil
import subprocess
import threading
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest import mock

from fedtail import i18n
from fedtail.frontends.web import server as web

from . import test_web
from .fakes import BOB, ME, status
from .test_core import TmpDir

ROOT = Path(__file__).resolve().parent.parent


def done(value):
    f = Future()
    f.set_result(value)
    return f


class ParityWebTest(TmpDir):
    make = test_web.WebTest.make
    req = test_web.WebTest.req

    def setUp(self):  # test_web.WebTest's world, without running its tests again
        super().setUp()
        i18n.setup("en")
        self.core, self.w = self.make()
        self.w.add(status("001", ME, minute=1, text="my <b>post</b>", vis="public"), home=True)
        self.w.add(status("002", BOB, "001", "ME", minute=2, text="hi"), home=True,
                   mention=True)
        self.core.connect().result()
        self.core.poll_once()
        self.key = web.load_key(self.core.paths.data_dir)
        self.srv = web.make_server(self.core, "127.0.0.1", 0, self.key)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def get(self, path):
        code, _h, text = self.req(path)
        self.assertEqual(code, 200, text)
        return json.loads(text)

    def post(self, path, body):
        code, _h, text = self.req(path, body)
        return code, json.loads(text or "{}")

    # ---- the sidebar ----------------------------------------------------------------
    def test_sections_fold(self):
        lanes = self.get("/api/lanes")
        heads = [x for x in lanes if x["group"]]
        self.assertTrue(heads)  # the windows' sections come with their titles
        section = heads[0]["section"]
        self.assertFalse(heads[0]["folded"])
        code, got = self.post("/api/fold", {"group": section})
        self.assertEqual((code, got["folded"]), (200, True))
        again = [x for x in self.get("/api/lanes") if x["section"] == section]
        self.assertTrue(all(x["folded"] for x in again))
        self.assertEqual(self.post("/api/fold", {"group": 3})[0], 400)
        self.assertTrue(any(x["tip"] for x in lanes))  # the windows' tips

    # ---- a thread ------------------------------------------------------------------
    def test_thread_head_and_came_from(self):
        got = self.get("/api/thread?id=002")
        head = got["head"]
        self.assertEqual(head["sid"], "001")
        self.assertIn(i18n._("thread_info", n=1), head["info"])
        self.assertFalse(head["subscribed"])
        marked = [p for p in got["posts"] if p.get("came_from")]
        self.assertEqual([p["sid"] for p in marked], ["002"])
        self.assertIsNone(self.srv.web.thread_head([], {}))

    def test_thread_head_says_why_it_comes(self):
        webs = self.srv.web
        posts = [p for p in (webs.core.by_id("001"), webs.core.by_id("002")) if p]
        people = [posts[1].author] * 5
        with mock.patch.object(webs.core, "followed_among", return_value=done(people)):
            head = webs.thread_head(posts, {})
        self.assertIn("@" + BOB["acct"].split("@")[0], head["via"])
        self.assertIn(i18n._("and_more", n=2), head["via"])
        self.assertTrue(head["via_tip"])
        boom = Future()
        boom.set_exception(OSError("down"))
        with mock.patch.object(webs.core, "followed_among", return_value=boom):
            self.assertEqual(webs.thread_head(posts, {})["via"], "")

    # ---- find --------------------------------------------------------------------
    def test_find_deeper_and_everywhere(self):
        self.assertEqual(self.get("/api/find_deeper?lane=home&q=")["total"], 0)
        got = self.get("/api/find_deeper?lane=home&q=nothing-like-it")
        self.assertEqual((got["more"], got["text"]), (False, i18n._("find_archive_none")))
        got = self.get("/api/find_deeper?lane=home&q=post")
        self.assertGreaterEqual(got["total"], 1)
        self.assertEqual(self.get("/api/find_everywhere?q=")["hits"], [])
        got = self.get("/api/find_everywhere?q=post")
        self.assertTrue(got["hits"])
        hit = got["hits"][0]
        self.assertTrue(hit["title"] and hit["lane"])
        self.assertTrue(got["text"])
        code, r = self.post("/api/reveal", {"lane": hit["lane"], "index": hit["index"]})
        self.assertEqual(code, 200)
        self.assertIn("grew", r)
        self.assertEqual(self.post("/api/reveal", {"lane": "nope", "index": 0})[0], 400)

    # ---- a poll ------------------------------------------------------------------
    def test_poll_people_and_refresh(self):
        st = status("060", BOB, minute=10, text="which?")
        st["poll"] = {"id": "p1", "expires_at": None, "expired": False, "multiple": False,
                      "votes_count": 3, "voters_count": 2, "voted": False, "own_votes": [],
                      "options": [{"title": "a", "votes_count": 2},
                                  {"title": "b", "votes_count": 1}], "emojis": []}
        self.w.add(st, home=True)
        self.core.poll_once()
        code, got = self.post("/api/poll_refresh", {"id": "060"})
        self.assertEqual(code, 200)
        self.assertIn(i18n._("poll_people", n=2), got["poll"]["summary"])

    # ---- the editor --------------------------------------------------------------
    def test_editor_facts(self):
        ed = self.get("/api/me")["editor"]
        self.assertEqual(ed["languages"][-1][0], "\x00other")
        self.assertTrue(ed["preview"])
        words = self.get("/api/me")["words"]
        for key in ("preview", "discard_q", "lang_other_ask", "focus_tip", "edit_media_kept"):
            self.assertIn(key, words)

    def test_another_language(self):
        code, got = self.post("/api/add_language", {"code": " EO "})
        self.assertEqual((code, got["code"]), (200, "eo"))
        codes = [c for c, _l in self.get("/api/me")["editor"]["languages"]]
        self.assertIn("eo", codes)
        self.post("/api/add_language", {"code": "eo"})  # twice: kept once
        self.assertEqual(self.core.get_state("languages_added", []).count("eo"), 1)
        code, got = self.post("/api/add_language", {"code": "not a code!"})
        self.assertEqual(code, 400)

    def test_compose_check(self):
        _c, got = self.post("/api/compose_check", {"text": "hi #camelcase"})
        self.assertEqual((got["chain"], got["camel"]), ("", i18n._(
            "camel_hint", tags="#camelcase")))
        self.assertFalse(got["over"])
        long = "\n\n".join(["word " * 90] * 3)
        _c, got = self.post("/api/compose_check", {"text": long, "cw": "x"})
        if got["parts"] > 1:  # post.chain: one long text, several posts
            self.assertEqual(got["chain"], i18n._("chain_count", n=got["parts"]))

    def test_preview(self):
        _c, got = self.post("/api/preview", {"text": "a <b>c</b>", "cw": "w", "media": 2,
                                             "visibility_words": "Public"})
        self.assertEqual(got["title"], i18n._("preview"))
        self.assertIn("Public", got["head"])
        self.assertIn(i18n._("preview_media", n=2), got["head"])
        self.assertEqual(got["cw"], "w")
        self.assertNotIn("<b>", "".join(got["parts"]))  # escaped, not run
        webs = self.srv.web
        with mock.patch("fedtail.core.app.Core.markdown", new_callable=mock.PropertyMock,
                        return_value=True):
            got = webs.preview({"text": "**bold** [x](javascript:alert(1))"})
        self.assertIn("<b>bold</b>", got["parts"][0])
        self.assertNotIn("javascript", got["parts"][0])
        self.assertIn(i18n._("preview_md"), got["head"])
        webs.core.cfg["post"]["chain"] = False  # post.chain off: one part, however long
        self.assertEqual(len(webs.preview({"text": "a\n\n---\n\nb"})["parts"]), 1)

    def test_alt_reminder_and_focus(self):
        webs = self.srv.web
        tok = webs.upload(b"\x89PNG\r\n\x1a\nxx", "a.png")["token"]
        body = {"text": "look", "media": [{"token": tok, "alt": "", "focus": [0.5, -2]}]}
        got = webs.post(dict(body))
        self.assertEqual(got["ask_alt"]["text"], i18n._("alt_missing", n=1))
        self.assertTrue(webs.upload_path(tok).exists())  # nothing sent, the copy kept
        sent = []
        real_post = webs.core.post

        def spy(*a, **k):
            sent.append(k["media"])
            return real_post(*a, **k)

        with mock.patch.object(webs.core, "post", side_effect=spy):
            got = webs.post(dict(body, alt_ok=True))
        self.assertTrue(got["id"])
        self.assertEqual(sent[0][0][2], (0.5, -1.0))  # clamped to the picture
        self.assertEqual(web._focus("x"), None)
        self.assertEqual(web._focus(["a", 1]), None)
        self.assertEqual(web._focus([float("nan"), 0]), None)

    def test_alt_reminder_off(self):
        webs = self.srv.web
        webs.core.cfg["post"]["alt_reminder"] = False
        tok = webs.upload(b"\x89PNG\r\n\x1a\nxx", "a.png")["token"]
        got = webs.post({"text": "look", "media": [{"token": tok, "alt": ""}]})
        self.assertNotIn("ask_alt", got)

    # ---- "received by", the viewer's Save -----------------------------------------------
    def test_via_mark(self):
        webs = self.srv.web
        entry = webs.core.by_id("002")
        with mock.patch.object(webs.core, "via", return_value="work@example.test",
                               create=True):
            got = web.post_json(webs.core, entry)
        self.assertEqual(got["via"]["text"], "→ work@example.test")
        self.assertIn("work@example.test", got["via"]["tip"])

    def test_save_original(self):
        self.assertEqual(self.post("/api/save", {"url": "http://plain/x.png"})[0], 400)
        webs = self.srv.web
        with mock.patch("fedtail.frontends.common.images.Cache.save",
                        return_value=done(Path("/tmp/x.png"))):
            code, got = self.post("/api/save", {"url": "https://far/x.png"})
        self.assertEqual(code, 200, got)
        self.assertEqual(got["message"], i18n._("saved_to", path=str(Path("/tmp/x.png"))))
        self.assertIsNotNone(webs._saver)


class PageTest(unittest.TestCase):
    def test_app_js_parses(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("no node")
        r = subprocess.run([node, "--check", str(ROOT / "fedtail/data/web/app.js")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_page_has_the_controls(self):
        html = (ROOT / "fedtail/data/web/index.html").read_text(encoding="utf-8")
        for el in ("preview", "discard", "compose-hint", "preview-dlg", "viewer-save"):
            self.assertIn(f'id="{el}"', html)
        js = (ROOT / "fedtail/data/web/app.js").read_text(encoding="utf-8")
        for call in ("/api/preview", "/api/add_language", "/api/compose_check", "/api/fold",
                     "/api/find_deeper", "/api/find_everywhere", "/api/poll_refresh",
                     "/api/save", "ask_alt", "alt_ok"):
            self.assertIn(call, js)

