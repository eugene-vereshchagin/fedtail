"""The web interface's server: the key, the page, the API — over real HTTP on localhost."""

import json
import os
import stat
import threading
import time
import urllib.error
import urllib.request

from fedtail import i18n
from fedtail.frontends.web import server as web

from . import test_cli
from .fakes import BOB, ME, status
from .test_core import TmpDir


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class WebTest(TmpDir):
    make = test_cli.CliTest.make

    def setUp(self):
        super().setUp()
        i18n.setup("en")
        self.core, self.w = self.make()
        self.w.add(status("001", ME, minute=1, text="my <b>post</b>", vis="public"), home=True)
        hostile = status("002", BOB, "001", "ME", minute=2,
                         text='hi <script>alert(1)</script><a href="javascript:x()">x</a>')
        self.w.add(hostile, home=True, mention=True)
        self.core.connect().result()
        self.core.poll_once()
        self.key = web.load_key(self.core.paths.data_dir)
        self.srv = web.make_server(self.core, "127.0.0.1", 0, self.key)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def req(self, path, body=None, cookie=True, header=True):
        headers = {}
        if cookie:
            headers["Cookie"] = f"{web.COOKIE}={self.key}"
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
            if header:
                headers["X-Fedtail"] = "1"
        r = urllib.request.Request(self.base + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                return resp.status, resp.headers, resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read().decode()

    def test_key_file_and_login_link(self):
        path = self.core.paths.data_dir / "web.key"
        self.assertEqual(web.load_key(self.core.paths.data_dir), self.key)  # kept
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        opener = urllib.request.build_opener(NoRedirect)
        try:
            opener.open(self.base + "/?k=" + self.key, timeout=10)
            self.fail("expected a redirect")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 303)
            cookie = e.headers["Set-Cookie"]
            self.assertIn(f"{web.COOKIE}={self.key}", cookie)
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Strict", cookie)
        code, _h, _b = self.req("/?k=wrong", cookie=False)
        self.assertEqual(code, 403)

    def test_no_key_no_entry(self):
        for path in ("/", "/app.js", "/api/lanes", "/api/lane?name=people"):
            self.assertEqual(self.req(path, cookie=False)[0], 403, path)
        # a POST without the header: refused even with the cookie (a form elsewhere)
        self.assertEqual(self.req("/api/read", {"ids": ["001"]}, header=False)[0], 403)

    def test_page_and_headers(self):
        code, headers, body = self.req("/")
        self.assertEqual(code, 200)
        self.assertIn("/app.js", body)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.req("/app.js")[0], 200)
        self.assertEqual(self.req("/app.css")[0], 200)

    def test_lanes_and_posts_cleaned(self):
        _c, _h, body = self.req("/api/lanes")
        lanes = {x["name"]: x for x in json.loads(body)}
        self.assertEqual(lanes["comments"]["unread"], 1)
        _c, _h, body = self.req("/api/lane?name=comments")
        data = json.loads(body)
        post = data["posts"][0]
        self.assertEqual(post["account"]["acct"], "bob@social.example")
        self.assertNotIn("<script", post["html"])
        self.assertNotIn("javascript:", post["html"])
        self.assertTrue(post["unread"])
        self.assertEqual(post["context"]["acct"], "mira")  # what it answers
        self.assertEqual(self.req("/api/lane?name=nosuch")[0], 400)

    def test_read_act_post_command(self):
        code, _h, _b = self.req("/api/read", {"ids": ["002"]})
        self.assertEqual(code, 200)
        self.assertEqual(self.core.unread_count("comments"), 0)
        _c, _h, body = self.req("/api/act", {"action": "fav", "id": "002"})
        self.assertTrue(json.loads(body)["favourited"])
        before = len(self.w.posted)
        _c, _h, body = self.req("/api/post", {"text": "an answer", "reply_to": "002"})
        self.assertEqual(len(self.w.posted), before + 1)
        self.assertEqual(self.w.posted[-1][2], "002")
        self.assertEqual(self.req("/api/post", {"text": "  "})[0], 400)
        self.assertEqual(self.req("/api/post", {"text": "x", "visibility": "everyone"})[0], 400)
        alias = self.core.short_ids([self.core.store.get_status("002")])["002"]
        _c, _h, body = self.req("/api/command", {"line": f"#{alias}"})
        self.assertEqual(json.loads(body)["open"], {"thread": "002"})
        _c, _h, body = self.req("/api/command", {"line": "#zzz9 hi"})
        self.assertFalse(json.loads(body)["ok"])

    def test_thread_and_account(self):
        _c, _h, body = self.req("/api/thread?id=002")
        nodes = json.loads(body)["posts"]
        self.assertEqual([p["number"] for p in nodes], [0, 1])
        self.assertEqual(nodes[1]["depth"], 1)
        code, _h, body = self.req("/api/account?id=B")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["account"]["acct"], "bob@social.example")

    def test_wait_answers_on_change(self):
        _c, _h, body = self.req("/api/wait?v=-1")
        v = json.loads(body)["v"]
        got = {}

        def waiter():
            got["v"] = json.loads(self.req(f"/api/wait?v={v}")[2])["v"]
        t = threading.Thread(target=waiter)
        t.start()
        time.sleep(0.3)
        self.core.mark_read(["001"])
        t.join(10)
        self.assertGreater(got["v"], v)

    def test_key_not_in_the_log(self):
        import logging
        seen = []

        class Catch(logging.Handler):
            def emit(self, record):
                seen.append(record.getMessage())
        h = Catch(level=logging.DEBUG)
        log = logging.getLogger("fedtail.frontends.web.server")
        log.addHandler(h)
        old = log.level
        log.setLevel(logging.DEBUG)
        try:
            self.req("/?k=" + self.key, cookie=False)
            self.req("/api/lanes")
        finally:
            log.removeHandler(h)
            log.setLevel(old)
        self.assertTrue(seen)
        self.assertFalse(any(self.key in m for m in seen))

    def test_lanes_in_sidebar_order_with_a_start(self):
        _c, _h, body = self.req("/api/lanes")
        lanes = json.loads(body)
        self.assertTrue(lanes[0]["group"])  # a section title over the first lane
        self.assertEqual([x["name"] for x in lanes if x["start"]], ["people"])
        self.req("/api/lane?name=comments")
        _c, _h, body = self.req("/api/lanes")
        self.assertEqual([x["name"] for x in json.loads(body) if x["start"]], ["comments"])

    def test_registered_as_a_frontend(self):
        from fedtail import frontends
        self.assertTrue(hasattr(frontends.load("web"), "run"))
