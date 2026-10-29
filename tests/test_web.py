"""The web interface's server: the key, the page, the API — over real HTTP on localhost."""

import json
import os
import stat
import threading
import time
import unittest
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

    def test_pictures_come_through_the_page_s_own_server(self):
        """The page's pictures are /pic: the windows' disk cache, fetched into it the
        checked way when missing — some servers give pictures to no other site, and the
        browser had asked them itself (grey avatars, 29.10)."""
        import io

        from PIL import Image

        from fedtail.frontends.common import images as pictures
        url = "https://pics.example/avatar.png"
        self.assertEqual(web._pic(url), "/pic?u=https%3A%2F%2Fpics.example%2Favatar.png")
        self.assertEqual(web._pic("http://pics.example/a.png"), "")  # never plain http
        buf = io.BytesIO()
        Image.new("RGB", (4, 4), (200, 10, 10)).save(buf, "PNG")
        p = pictures.picture_path(self.core.paths.cache_dir, url)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(buf.getvalue())
        r = urllib.request.Request(self.base + web._pic(url),
                                   headers={"Cookie": f"{web.COOKIE}={self.key}"})
        with urllib.request.urlopen(r, timeout=30) as resp:
            self.assertEqual(resp.headers["Content-Type"], "image/png")
            self.assertEqual(resp.read(), buf.getvalue())
        # not in the cache and nowhere to get it from (the tests are offline): 404
        self.assertEqual(self.req(web._pic("https://nowhere.example/x.png"))[0], 404)
        self.assertEqual(self.req("/pic?u=" + url, cookie=False)[0], 403)
        self.assertNotIn("https:", web.CSP.split("img-src")[1].split(";")[0])

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

    def upload(self, data, name):
        r = urllib.request.Request(self.base + "/api/upload", data=data, headers={
            "Cookie": f"{web.COOKIE}={self.key}", "X-Fedtail": "1",
            "X-Name": urllib.parse.quote(name), "Content-Type": "application/octet-stream"})
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_editor_media_poll_schedule_and_lane_choices(self):
        """The editor as the windows': a picture with its description, a poll, later;
        a lane's choices (common/lane.py): posts only, the media funnel."""
        me = json.loads(self.req("/api/me")[2])
        self.assertEqual(me["editor"]["limit"], self.core.caps.max_characters)
        self.assertEqual(me["editor"]["languages"][0][0], "")
        code, got = self.upload(b"\x89PNG fake", "кот.png")
        self.assertEqual(code, 200)
        token = got["token"]
        self.assertTrue(token.endswith(".png"))
        stored = self.core.paths.data_dir / "web-uploads" / token
        self.assertTrue(stored.is_file())
        code, _h, body = self.req("/api/post", {"text": "смотрите", "visibility": "public",
                                                "media": [{"token": token, "alt": "кот"}],
                                                "sensitive": True})
        self.assertEqual(code, 200, body)
        self.assertEqual(self.w.uploads[-1][1], "кот")
        self.assertTrue(self.w.extras[-1]["sensitive"])
        self.assertFalse(stored.exists())  # sent: the copy gone
        self.assertEqual(self.req("/api/post", {"text": "x", "media": [{"token": "../x"}]})[0],
                         400)
        self.assertEqual(self.upload(b"", "x.png")[0], 413)
        self.req("/api/post", {"text": "что выбрать?", "visibility": "public",
                               "poll": {"options": ["а", "б", ""], "expires_in": 3600}})
        self.assertEqual(self.w.extras[-1]["poll"],
                         {"options": ["а", "б"], "expires_in": 3600, "multiple": False})
        r = json.loads(self.req("/api/post", {"text": "утром", "visibility": "public",
                                              "scheduled_at": "2099-10-15T09:30"})[2])
        self.assertTrue(r["scheduled"])
        self.assertTrue(self.w.scheduled[-1]["scheduled_at"].endswith("Z"))
        # the lane's choices: posts only hides replies
        lane = json.loads(self.req("/api/lane?name=home")[2])
        self.assertEqual([f[0] for f in lane["filters"]],
                         ["all", "posts", "chip:1", "chip:2", "chip:3", "unread"])
        self.req("/api/lane_set", {"name": "home", "filter": "posts"})
        lane = json.loads(self.req("/api/lane?name=home")[2])
        self.assertEqual(lane["filter"], "posts")
        self.assertFalse(any(p["reply_to"] for p in lane["posts"]))
        self.req("/api/lane_set", {"name": "home", "filter": "all"})
        self.req("/api/lane_set", {"name": "home", "media": "text", "on": False})
        lane = json.loads(self.req("/api/lane?name=home")[2])
        self.assertTrue(lane["media"]["active"])
        self.assertTrue(all(p["media"] for p in lane["posts"]))
        self.req("/api/lane_set", {"name": "home", "media": "reset"})
        lane = json.loads(self.req("/api/lane?name=home")[2])
        self.assertFalse(lane["media"]["active"])
        words = lane["posts"][0]["words"]
        self.assertEqual(words["meta"][0]["kind"], "time")

    def test_page_script_parses(self):
        """app.js is valid JavaScript (node --check, where node is): a slip shows here,
        not as a blank page."""
        import shutil
        import subprocess
        from pathlib import Path
        node = shutil.which("node")
        if not node:
            self.skipTest("no node")
        js = Path(web.__file__).resolve().parent.parent.parent / "data" / "web" / "app.js"
        r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True,
                           timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

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

    def test_themes(self):
        """≡ → Try a theme: the windows' themes as the page's colours, for this run."""
        self.assertIn("/theme.css", self.req("/")[2])
        code, headers, css = self.req("/theme.css")
        self.assertEqual((code, css), (200, ""))  # system: the browser's light or dark
        self.assertTrue(headers["Content-Type"].startswith("text/css"))
        t = json.loads(self.req("/api/themes")[2])
        names = [x["name"] for x in t["themes"]]
        self.assertIn("night", names)
        self.assertEqual((t["current"], t["configured"]), ("system", "system"))
        self.assertIn(i18n._("theme_in_config"),
                      next(x["label"] for x in t["themes"] if x["name"] == "system"))
        r = json.loads(self.req("/api/theme", {"name": "night"})[2])
        self.assertIn("night", r["message"])
        css = self.req("/theme.css")[2]
        self.assertIn("--bg: #", css)
        self.assertIn("color-scheme: only dark", css)
        self.assertIn("font-family:", css)
        self.assertTrue(json.loads(self.req("/api/themes")[2])["themes"][names.index("night")]
                        ["on"])
        self.req("/api/theme", {"name": "juick"})
        self.assertIn("only light", self.req("/theme.css")[2])
        self.assertEqual(self.req("/api/theme", {"name": "../etc"})[0], 400)
        self.assertEqual(self.core.cfg["ui"]["theme"], "system")  # the config stays
        webs = self.srv.web
        webs.theme = "no-such-theme"
        self.assertEqual(webs.theme_css(), "")  # won't load: the page's own colours

    def test_merge_switch(self):
        me = json.loads(self.req("/api/me")[2])
        self.assertFalse(me["merged"])
        self.assertIn("accounts_merge_tip", me["words"])
        r = json.loads(self.req("/api/merge", {})[2])
        self.assertTrue(r["merged"])
        self.assertTrue(r["message"].startswith("☑ "))
        self.assertEqual(self.core.get_state("merge"), ["all"])
        self.assertFalse(json.loads(self.req("/api/merge", {})[2])["merged"])

    def test_web_push(self):
        """The page subscribes the browser at the user's server; fedtail hands it over."""
        code, headers, js = self.req("/sw.js")
        self.assertEqual(code, 200)
        self.assertIn("javascript", headers["Content-Type"])
        self.assertIn("showNotification", js)
        st = json.loads(self.req("/api/push")[2])
        self.assertEqual((st["key"], st["endpoint"]), ("", ""))  # no Web Push there
        self.assertIn("web_push_insecure", st["words"])
        self.w.vapid = "BKEY"
        self.assertEqual(json.loads(self.req("/api/push")[2])["key"], "BKEY")
        bad = {"endpoint": "http://push.example/x", "keys": {"p256dh": "P", "auth": "A"}}
        self.assertEqual(self.req("/api/push_on", bad)[0], 400)
        self.assertEqual(self.req("/api/push_on", {"endpoint": "https://p.example/x"})[0], 400)
        good = {"endpoint": "https://push.example/x", "keys": {"p256dh": "P", "auth": "A"}}
        r = json.loads(self.req("/api/push_on", good)[2])
        self.assertEqual(r["message"], i18n._("web_push_on"))
        self.assertEqual(self.w.push["endpoint"], "https://push.example/x")
        self.assertTrue(self.w.push["alerts"]["mention"])
        self.assertEqual(json.loads(self.req("/api/push")[2])["endpoint"],
                         "https://push.example/x")
        self.req("/api/push_off", {})
        self.assertIsNone(self.w.push)

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
        self.req("/api/thread?id=002")  # the thread open beside, as the page has it
        _c, _h, body = self.req("/api/post", {"text": "an answer", "reply_to": "002"})
        self.assertEqual(len(self.w.posted), before + 1)
        self.assertEqual(self.w.posted[-1][2], "002")
        # drawn again after sending (the page does): my answer is in it at once
        mine_id = json.loads(body)["id"]
        _c, _h, th = self.req("/api/thread?id=002")
        self.assertIn(mine_id, [p["sid"] for p in json.loads(th)["posts"]])
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
        self.assertIn('<img class="emoji" src="/pic?u=https%3A%2F%2Fx.example%2Fb.png" '
                      'alt=":blob:"', post["html"])
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

    def test_the_lane_says_where_reading_starts(self):
        """The lane's own start (LaneModel.start: feed.start_at, "new below"): the page
        and the phone stand there instead of counting it again."""
        web = self.srv.web
        self.core.cfg["feed"]["start_at"] = "first_unread"
        got = web.lane("home")
        unread = [p["id"] for p in got["posts"] if p["unread"]]
        self.assertTrue(unread)
        self.assertEqual(got["start"], unread[0])
        self.core.cfg["feed"]["start_at"] = "newest"
        self.assertIsNone(web.lane("home")["start"])  # the newest end

    def test_read_up_to_here_is_the_cores_count(self):
        """⋯ → "Read up to here": counted on the server over the cards the page shows,
        by time (common/lane.read_up_to) — the page had its own count by place; what was
        marked comes back for the page to paint."""
        self.w.add(status("003", BOB, minute=3, text="third", vis="public"), home=True)
        self.w.add(status("004", BOB, minute=4, text="fourth", vis="public"), home=True)
        self.core.poll_once()
        shown = ["004", "002", "003", "001"]  # in whatever order the page has them
        got = json.loads(self.req("/api/link", {"url": "fedtail:readupto/003",
                                                "shown": shown})[2])
        self.assertEqual(sorted(got["read"]), ["001", "002", "003"])
        self.assertEqual(self.core.store.read_set(["001", "002", "003", "004"]),
                         {"001", "002", "003"})
        got = json.loads(self.req("/api/link", {"url": "fedtail:readupto/004"})[2])
        self.assertEqual(got["read"], ["004"])  # nothing shown said: that post alone

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
        self.assertEqual(got["open"], {"thread": "002", "at": "post"})
        self.assertEqual(self.req("/api/link", {"url": "fedtail:boom/002"})[0], 200)
        # how long a mute lasts: asked, then done with the pick ("3600" as a string too)
        got = json.loads(self.req("/api/link", {"url": "fedtail:mute/002"})[2])
        self.assertIn("choose", got)
        got = json.loads(self.req("/api/link", {"url": "fedtail:mute/002",
                                                "chosen": {"key": "3600"}})[2])
        self.assertIn("message", got)
        self.assertEqual(self.w.mute_terms["B"], {"duration": 3600, "notifications": True})
        odd = json.loads(self.req("/api/link", {"url": "fedtail:mute/002",
                                                "chosen": {"key": "7"}})[2])
        self.assertIn("choose", odd)  # not one of the answers: asked again
        # hide this one post: in the menu, asked first, then a server filter has it
        self.assertIn("fedtail:hidepost/002",
                      [i["url"] for i in json.loads(self.req("/api/post_menu?id=002")[2])
                       ["items"]])
        got = json.loads(self.req("/api/link", {"url": "fedtail:hidepost/002"})[2])
        self.assertIn("confirm", got)
        got = json.loads(self.req("/api/link", {"url": "fedtail:hidepost/002",
                                                "confirmed": True})[2])
        self.assertEqual(got["message"], i18n._("post_hidden"))
        self.assertIn("002", self.core.hidden_posts)
        host = _WebHost(view, False)
        host.error("x")
        self.assertEqual(host.out, {"error": "x"})

    def test_profile_buttons_are_the_windows(self):
        """A profile's buttons (common/profile.py), done through the server: mute
        asks how long first, a note asked for first, Mention opens the editor."""
        got = json.loads(self.req("/api/account?id=B")[2])
        keys = [a["key"] for a in got["actions"]]
        for k in ("follow", "mention", "mute", "block", "note", "copy_handle"):
            self.assertIn(k, keys)
        r = json.loads(self.req("/api/profile_act", {"id": "B", "key": "mute"})[2])
        self.assertEqual([o["key"] for o in r["choose"]["options"]],
                         [0, 3600, 86400, 604800, 2592000])
        self.assertEqual(r["choose"]["check"], i18n._("mute_posts_only"))
        self.assertNotIn("B", self.w.muted)  # nothing yet: the page asks
        r = json.loads(self.req("/api/profile_act", {"id": "B", "key": "mute",
                                                     "chosen": {"key": 86400,
                                                                "ticked": True}})[2])
        self.assertTrue(r.get("refresh"))
        self.assertEqual(self.w.mute_terms["B"], {"duration": 86400, "notifications": False})
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

    def test_profile_shows_posts_replies_media(self):
        self.w.add(status("010", BOB, minute=10, text="own"))
        pic = self.w.add(status("011", BOB, minute=11, text="pic"))
        pic["media_attachments"] = [{"id": "m1", "type": "image", "url": "https://x/p.png"}]
        got = json.loads(self.req("/api/account?id=B")[2])  # feed.profile_show: posts
        self.assertEqual([s["key"] for s in got["shows"] if s["on"]], ["posts"])
        self.assertEqual([s["label"] for s in got["shows"]],
                         [i18n._("profile_show_posts"), i18n._("profile_show_all"),
                          i18n._("profile_show_media")])
        self.assertEqual(got["show_tip"], i18n._("profile_show_tip"))
        ids = lambda g: sorted(p["id"] for p in g["posts"])  # noqa: E731
        self.assertNotIn("002", ids(got))  # a reply to someone else
        every = json.loads(self.req("/api/account?id=B&show=all")[2])
        self.assertIn("002", ids(every))
        media = json.loads(self.req("/api/account?id=B&show=media")[2])
        self.assertEqual(ids(media), ["011"])
        odd = json.loads(self.req("/api/account?id=B&show=boom")[2])
        self.assertEqual([s["key"] for s in odd["shows"] if s["on"]], ["posts"])
        js = self.req("/app.js")[2]
        for wanted in ("function profileShows", "function chooseDlg", "r.choose"):
            self.assertIn(wanted, js)

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
        badge = {x["name"]: x["badge"] for x in lanes}  # the colour, by the lane's rule
        self.assertEqual((badge["home"], badge["replies"]), ("normal", "hot"))
        self.req("/api/lane?name=comments")
        self.req("/api/active", {"name": "comments"})  # what the page does after it
        _c, _h, body = self.req("/api/lanes")
        self.assertEqual([x["name"] for x in json.loads(body) if x["start"]], ["replies"])

    def test_the_curtain_and_where_a_lane_opens(self):
        """ui.start_lane = "none": no lane to start with — the page shows the curtain
        (its words the windows' and the terminal's) and Enter opens the lane of last
        time; the last card seen whole goes to /api/stood, where the lane opens next
        time in every interface (LaneModel.stood), on top or at the bottom."""
        self.core.cfg["ui"]["start_lane"] = "none"
        _c, _h, body = self.req("/api/lanes")
        self.assertEqual([x["name"] for x in json.loads(body) if x["start"]], [])
        _c, _h, body = self.req("/api/curtain")
        got = json.loads(body)
        self.assertEqual(got["title"], i18n._("curtain_title"))
        self.assertEqual(got["last"], "home")
        posts = [s for s in self.w.statuses]
        self.assertTrue(posts)
        self.req("/api/stood", {"lane": "home", "key": posts[0]})
        self.assertEqual(self.core.get_state("stood.home"), posts[0])
        _c, _h, body = self.req("/api/lane?name=home")
        self.assertEqual(json.loads(body)["start"], posts[0])
        self.assertIn(json.loads(body)["start_where"], ("top", "bottom"))

    def test_the_highlight_is_said_to_the_page(self):
        """ui.additional_highlight: the page lights the post under the mouse (body.lit)."""
        _c, _h, body = self.req("/api/me")
        self.assertIs(json.loads(body)["highlight"], True)
        self.core.cfg["ui"]["additional_highlight"] = False
        _c, _h, body = self.req("/api/me")
        self.assertIs(json.loads(body)["highlight"], False)

    def test_registered_as_a_frontend(self):
        from fedtail import frontends
        self.assertTrue(hasattr(frontends.load("web"), "run"))


class CssTest(unittest.TestCase):
    def test_card_lines_are_blocks(self):
        """The card's lines made of links (common/cardtext Bits: "in reply to…", the
        conversation, new in a thread) are blocks: a link stays inline, its nowrap
        then widened the lane past a phone's screen (27.10)."""
        import re
        from pathlib import Path
        css = (Path(web.__file__).parents[2] / "data" / "web" / "app.css").read_text("utf-8")
        rule = re.search(r"\.post \.ctx \{([^}]*)\}", css).group(1)
        self.assertIn("display: block", rule)

