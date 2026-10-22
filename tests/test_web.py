"""The web interface's server: the key, the page, the API — over real HTTP on localhost."""

import json
import os
import stat
import threading
import time
import urllib.error
import urllib.parse
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

    def test_notifications_and_places(self):
        """What the windows notify about comes to the page with the news (the browser
        shows it); the places of the ≡ menu open and their buttons work."""
        webs = self.srv.web
        self.assertEqual(webs.notes_since(-1), ([], 0))  # a page that just opened: nothing
        self.w.add(status("050", BOB, "001", "ME", minute=50, text="ping"), mention=True)
        self.core.poll_once()
        got = json.loads(self.req("/api/wait?v=-5&s=0&n=0")[2])
        self.assertTrue(got["notes"])
        self.assertIn("ping", got["notes"][0]["body"])
        names = [x["name"] for x in json.loads(self.req("/api/places")[2])]
        for n in ("search", "lists", "silence", "help"):
            self.assertIn(n, names)
        page = json.loads(self.req("/api/page?name=lists")[2])
        self.assertEqual(page["submit"]["act"], ["lists", "new", ""])
        r = json.loads(self.req("/api/place", {"act": ["lists", "new", ""],
                                               "values": {"title": "Друзья"}})[2])
        self.assertTrue(r.get("refresh"))
        page = json.loads(self.req("/api/page?name=lists")[2])
        self.assertEqual([x["title"] for x in page["rows"]], ["Друзья"])
        self.assertEqual(self.req("/api/place", {"act": ["lists", "boom", ""]})[0], 400)
        self.assertEqual(self.req("/api/page?name=nope")[0], 400)
        help_page = json.loads(self.req("/api/page?name=help")[2])
        self.assertIn("<h1", help_page["rows"][0]["html"])

    def test_a_page_that_hangs_up_is_no_error(self):
        # a reload or a closed tab while /api/wait waits: the answer has nowhere to go —
        # no traceback on the terminal (it was two BrokenPipeErrors), the server goes on
        import contextlib
        import io
        import socket
        import struct
        from unittest import mock
        err = io.StringIO()
        with contextlib.redirect_stderr(err), mock.patch.object(web, "WAIT_SECONDS", 0.5):
            for _ in range(3):
                s = socket.create_connection(self.srv.server_address[:2])
                s.sendall(f"GET /api/wait?v=0 HTTP/1.1\r\nHost: x\r\n"
                          f"Cookie: {web.COOKIE}={self.key}\r\n\r\n".encode())
                # close at once with a reset: the answer's write fails
                s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                s.close()
            time.sleep(1.2)
        self.assertNotIn("Traceback", err.getvalue())
        self.assertNotIn("BrokenPipe", err.getvalue())
        self.assertEqual(self.req("/api/me")[0], 200)

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

    def test_one_time_link(self):
        # what fedtail prints: a link that logs in once, with no key in it
        link = self.srv.web.login_link(self.base)
        self.assertNotIn(self.key, link)
        opener = urllib.request.build_opener(NoRedirect)
        path = link[len(self.base):]
        with self.assertRaises(urllib.error.HTTPError) as e:
            opener.open(self.base + path, timeout=10)
        self.assertEqual(e.exception.code, 303)
        self.assertIn(f"{web.COOKIE}={self.key}", e.exception.headers["Set-Cookie"])
        self.assertEqual(self.req(path, cookie=False)[0], 403)  # used: dead
        old = self.srv.web.login_link(self.base)
        token = old.split("t=")[1]
        self.srv.web.links[token] = time.monotonic() - 1  # a quarter of an hour later
        self.assertEqual(self.req(old[len(self.base):], cookie=False)[0], 403)

    def test_reading_changes_nothing_and_ids_are_ids(self):
        self.core.set_state("lane", "replies")
        self.assertEqual(self.req("/api/lane?name=home")[0], 200)
        self.assertEqual(self.core.get_state("lane"), "replies")  # a GET only reads
        self.assertEqual(self.req("/api/active", {"name": "home"})[0], 200)
        self.assertEqual(self.core.get_state("lane"), "home")
        self.assertEqual(self.req("/api/resolve?url=https%3A%2F%2Fx.example%2F1")[0], 404)
        for bad in ("1/../../statuses/2/reblog", "..", "a?b", ""):
            self.assertEqual(self.req("/api/follow", {"id": bad, "on": True})[0], 400, bad)
            self.assertEqual(self.req("/api/account?id=" + urllib.parse.quote(bad))[0], 400)

    def test_connections_are_capped(self):
        import socket
        import threading as th
        self.srv.slots = th.BoundedSemaphore(1)
        held = socket.create_connection(self.srv.server_address[:2], timeout=5)
        self.addCleanup(held.close)
        time.sleep(0.2)  # the server has taken it (and waits for its request)
        extra = socket.create_connection(self.srv.server_address[:2], timeout=5)
        extra.sendall(b"GET / HTTP/1.0\r\n\r\n")
        try:
            got = extra.recv(100)
        except (ConnectionResetError, ConnectionAbortedError):  # Windows: closed with a reset
            got = b""
        self.assertEqual(got, b"")  # closed at the door
        extra.close()

    def test_no_key_no_entry(self):
        for path in ("/", "/app.js", "/api/lanes", "/api/lane?name=people"):
            self.assertEqual(self.req(path, cookie=False)[0], 403, path)
        # a POST without the header: refused even with the cookie (a form elsewhere)
        self.assertEqual(self.req("/api/read", {"ids": ["001"]}, header=False)[0], 403)

    def test_negative_length_is_refused_not_read_to_the_end(self):
        # read(-1) reads until the client closes: the 1 MB limit would be gone
        import http.client
        port = self.srv.server_address[1]
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.putrequest("POST", "/api/read")
        c.putheader("Cookie", f"{web.COOKIE}={self.key}")
        c.putheader("X-Fedtail", "1")
        c.putheader("Content-Length", "-1")
        c.endheaders()
        c.send(b'{"ids": ["001"]}')  # and the connection stays open
        r = c.getresponse()
        self.assertEqual(r.status, 400)
        c.close()

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
        self.assertEqual(lanes["replies"]["unread"], 1)
        _c, _h, body = self.req("/api/lane?name=comments")
        data = json.loads(body)
        post = data["posts"][0]
        self.assertEqual(post["account"]["handle"], "bob@social.example")
        self.assertNotIn("<script", post["html"])
        self.assertNotIn("javascript:", post["html"])
        self.assertTrue(post["unread"])
        self.assertEqual(post["context"]["handle"], "mira")  # what it answers
        self.assertIn(data["posts"][0]["visibility"], ("public", "unlisted", "followers",
                                                       "direct"))  # our words, not the API's
        self.assertEqual(self.req("/api/lane?name=nosuch")[0], 400)

    def test_read_act_post_command(self):
        code, _h, _b = self.req("/api/read", {"ids": ["002"]})
        self.assertEqual(code, 200)
        self.assertEqual(self.core.unread_count("replies"), 0)
        _c, _h, body = self.req("/api/act", {"action": "like", "id": "002"})
        self.assertTrue(json.loads(body)["mine"]["liked"])
        self.assertEqual(self.req("/api/act", {"action": "fav", "id": "002"})[0], 400)
        before = len(self.w.posted)
        _c, _h, body = self.req("/api/post", {"text": "an answer", "reply_to": "002"})
        self.assertEqual(len(self.w.posted), before + 1)
        self.assertEqual(self.w.posted[-1][2], "002")
        self.assertEqual(self.req("/api/post", {"text": "  "})[0], 400)
        self.assertEqual(self.req("/api/post", {"text": "x", "visibility": "everyone"})[0], 400)
        self.req("/api/post", {"text": "to friends", "visibility": "followers"})
        self.assertEqual(self.w.posted[-1][1], "private")  # the API's word goes out
        alias = self.core.short_ids([self.core.store.get_status("002")])["002"]
        _c, _h, body = self.req("/api/command", {"line": f"#{alias}"})
        self.assertEqual(json.loads(body)["open"], {"thread": "002"})
        _c, _h, body = self.req("/api/command", {"line": "#zzz9 hi"})
        self.assertFalse(json.loads(body)["ok"])
        # D #id: asked first ("sure?" on the page), deleted only on the second request
        mine = self.core.short_ids([self.core.store.get_status("001")])["001"]
        _c, _h, body = self.req("/api/command", {"line": f"D #{mine}"})
        got = json.loads(body)
        self.assertFalse(got["ok"])
        self.assertIn("my post", got["confirm"])
        self.assertIn("001", self.w.statuses)  # still there
        _c, _h, body = self.req("/api/command", {"line": f"D #{mine}", "confirm": "yes"})
        self.assertIn("001", self.w.statuses)  # only true is a yes
        _c, _h, body = self.req("/api/command", {"line": f"D #{mine}", "confirm": True})
        self.assertTrue(json.loads(body)["ok"])
        self.assertNotIn("001", self.w.statuses)

    def test_poll_vote_older_and_emojis(self):
        st = status("003", BOB, minute=3, vis="public", text="pick :blob: <b>one</b>")
        st["poll"] = {"id": "P1", "options": [{"title": "a", "votes_count": 1},
                                              {"title": "b", "votes_count": 3}],
                      "votes_count": 4, "multiple": False, "expired": False, "voted": False,
                      "own_votes": [], "expires_at": None, "emojis": []}
        st["emojis"] = [{"shortcode": "blob", "url": "https://x.example/b.png",
                         "static_url": "https://x.example/b.png"},
                        {"shortcode": "evil", "url": "javascript:alert(1)"}]
        self.w.add(st, home=True)
        self.core.poll_once()
        _c, _h, body = self.req("/api/lane?name=home")
        post = next(p for p in json.loads(body)["posts"] if p["sid"] == "003")
        self.assertIn('<img class="emoji" src="https://x.example/b.png" alt=":blob:"',
                      post["html"])
        self.assertEqual([o["share"] for o in post["poll"]["options"]], [25, 75])
        self.assertIn("4", post["poll"]["summary"])
        code, _h, body = self.req("/api/vote", {"id": "003", "choices": [1]})
        self.assertEqual(code, 200, body)
        self.assertEqual(self.req("/api/vote", {"id": "../x", "choices": [1]})[0], 400)
        code, _h, body = self.req("/api/older", {"name": "home"})
        self.assertEqual(code, 200, body)
        self.assertIn("n", json.loads(body))
        self.assertEqual(self.req("/api/older", {"name": "nosuch"})[0], 400)

    def test_emojis_stay_out_of_tags(self):
        from fedtail.model import Emoji
        html = '<a href="https://h.example/:blob:" title=":blob:">:blob:</a>'
        got = web.with_emojis(html, (Emoji("blob", "https://x.example/b.png"),))
        self.assertTrue(got.startswith('<a href="https://h.example/:blob:" title=":blob:">'))
        self.assertIn('<img class="emoji"', got)
        self.assertEqual(web.with_emojis(":x:", (Emoji("x", "http://plain.example"),)), ":x:")

    def test_page_words_exist_in_both_languages(self):
        for lang in ("ru", "en"):
            missing = [k for k in web.WORDS if k not in i18n._STRINGS[lang]]
            self.assertEqual(missing, [], lang)

    def test_menus_threads_delete(self):
        """What the page's ≡ and ⋯ menus need: the help, a post's thread state; follow,
        leave and mute a thread (muting works where the server can't); delete only my
        own post."""
        _c, _h, body = self.req("/api/me")
        me = json.loads(body)
        self.assertTrue(me["help_url"].endswith("/fedtail/data/help/en/index.md"))
        self.assertEqual(me["quote_prefix"], "> ")
        self.assertEqual(me["words"]["reply_quote"], "Reply with quote")
        _c, _h, body = self.req("/api/post_menu?id=002")
        got = json.loads(body)
        self.assertEqual({k: got[k] for k in ("subscribed", "muted", "own")},
                         {"subscribed": False, "muted": False, "own": False})
        self.assertEqual(self.req("/api/post_menu?id=../x")[0], 400)
        self.assertEqual(self.req("/api/thread_act", {"action": "sub", "id": "002"})[0], 200)
        self.assertTrue(json.loads(self.req("/api/post_menu?id=002")[2])["subscribed"])
        self.w.missing = {"mute_thread"}  # GoToSocial
        self.assertEqual(self.req("/api/thread_act", {"action": "mute", "id": "002"})[0], 200)
        got = json.loads(self.req("/api/post_menu?id=002")[2])
        self.assertTrue(got["muted"])
        self.assertFalse(got["subscribed"])  # muting leaves the thread
        self.assertEqual(self.req("/api/thread_act", {"action": "boom", "id": "002"})[0], 400)
        self.assertEqual(self.req("/api/delete", {"id": "002"})[0], 400)  # not mine
        self.assertIn("002", self.w.statuses)
        self.assertTrue(json.loads(self.req("/api/post_menu?id=001")[2])["own"])
        self.assertEqual(self.req("/api/delete", {"id": "001"})[0], 200)
        self.assertNotIn("001", self.w.statuses)

    def test_post_menu_is_the_windows_menu(self):
        """The ⋯ menu: the very items of the Qt and GTK windows (common/actions), and
        its fedtail: links done the way they do them, the page told what's left."""
        from fedtail.frontends.common import actions
        from fedtail.frontends.web.server import _WebHost
        items = json.loads(self.req("/api/post_menu?id=002")[2])["items"]
        view = self.srv.web.core
        p = view.by_id("002")
        ctx = actions.Ctx(cfg=view.cfg, me_id=view.me.id, supports=view.supports,
                          subscribed=view.subscribed, thread_quiet=view.thread_quiet,
                          lists=True, long_form=True, quote_reply=True)
        want = [it.label for it in actions.menu(p, ctx, view.short_ids([p]).get(p.id),
                                                 p.id in view.unread([p]))
                if it.kind != "act_as"]  # all but "as another account": one a page
        while want and not want[0]:  # (a separator first is dropped)
            want.pop(0)
        self.assertEqual([i["label"] for i in items], want)
        self.assertTrue(any(i["url"].startswith("fedtail:") for i in items))
        mine = json.loads(self.req("/api/post_menu?id=001")[2])["items"]
        urls = [i["url"] for i in mine]
        self.assertIn("fedtail:edit/001", urls)
        self.assertIn("fedtail:redraft/001", urls)
        # a link: a question first, done when confirmed
        code, _h, body = self.req("/api/link", {"url": "fedtail:delete/001"})
        self.assertEqual(code, 200)
        self.assertIn("confirm", json.loads(body))
        self.assertIn("001", self.w.statuses)
        got = json.loads(self.req("/api/link", {"url": "fedtail:delete/001",
                                                "confirmed": True})[2])
        self.assertTrue(got.get("refresh"))
        self.assertNotIn("001", self.w.statuses)
        # the editor and the clipboard: for the page to do
        got = json.loads(self.req("/api/link", {"url": "fedtail:invite/002"})[2])
        self.assertEqual(got["compose"], {"reply_to": "002", "invite": True, "text": "@"})
        got = json.loads(self.req("/api/link", {"url": "fedtail:copyhandle/bob%40x.example"})[2])
        self.assertEqual(got["copy"], "@bob@x.example")
        got = json.loads(self.req("/api/link", {"url": "fedtail:thread/002"})[2])
        self.assertEqual(got["open"], {"thread": "002"})
        self.assertEqual(self.req("/api/link", {"url": "fedtail:boom/002"})[0], 200)
        host = _WebHost(view, False)
        host.error("x")
        self.assertEqual(host.out, {"error": "x"})

    def test_profile_buttons_are_the_windows(self):
        """A profile's buttons (common/profile.py), done through the server: mute at
        once, a note asked for first, Mention opens the editor."""
        got = json.loads(self.req("/api/account?id=B")[2])
        keys = [a["key"] for a in got["actions"]]
        for k in ("follow", "mention", "mute", "block", "note", "copy_handle"):
            self.assertIn(k, keys)
        r = json.loads(self.req("/api/profile_act", {"id": "B", "key": "mute"})[2])
        self.assertTrue(r.get("refresh"))
        got = json.loads(self.req("/api/account?id=B")[2])
        self.assertIn(i18n._("unmute"), [a["label"] for a in got["actions"]])
        r = json.loads(self.req("/api/profile_act", {"id": "B", "key": "note"})[2])
        self.assertIn("ask", r)
        r = json.loads(self.req("/api/profile_act", {"id": "B", "key": "mention"})[2])
        self.assertEqual(r["compose"], {"text": "@bob@social.example "})
        r = json.loads(self.req("/api/profile_act", {"id": "B", "key": "block"})[2])
        self.assertIn("confirm", r)
        # the lists: a place the page opens (common/places.py)
        r = json.loads(self.req("/api/profile_act", {"id": "B", "key": "lists"})[2])
        self.assertEqual(r["open"], {"page": "list_of", "arg": "B", "tab": ""})
        self.assertEqual(self.req("/api/profile_act", {"id": "B", "key": "boom"})[0], 400)

    def test_page_has_the_menus(self):
        body = self.req("/")[2]
        for wanted in ('id="more"', 'id="pop"', 'id="quote-sel"', 'id="viewer-next"'):
            self.assertIn(wanted, body)
        js = self.req("/app.js")[2]
        for wanted in ("function postMenu", "function mainMenu", "function insertQuote",
                       "function stepViewer"):
            self.assertIn(wanted, js)

    def test_thread_and_account(self):
        _c, _h, body = self.req("/api/thread?id=002")
        nodes = json.loads(body)["posts"]
        self.assertEqual([p["number"] for p in nodes], [0, 1])
        self.assertEqual(nodes[1]["depth"], 1)
        code, _h, body = self.req("/api/account?id=B")
        self.assertEqual(code, 200)
        got = json.loads(body)
        self.assertEqual(got["account"]["handle"], "bob@social.example")
        self.assertIn("following", got["relation"])

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
        self.assertEqual([x["name"] for x in lanes if x["start"]], ["home"])
        self.req("/api/lane?name=comments")
        self.req("/api/active", {"name": "comments"})  # what the page does after it
        _c, _h, body = self.req("/api/lanes")
        self.assertEqual([x["name"] for x in json.loads(body) if x["start"]], ["replies"])

    def test_registered_as_a_frontend(self):
        from fedtail import frontends
        self.assertTrue(hasattr(frontends.load("web"), "run"))
