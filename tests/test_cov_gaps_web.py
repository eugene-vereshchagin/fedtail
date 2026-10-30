"""The web page's last untested turns (frontends/web): a name with its emoji, a page
opened before the core connected, slow mode's line, a profile's extras when some fail
(many familiar faces, a move), a profile's next page from their own server, "reply as"
not found, completion when the server can't be asked, the routes of the newest calls,
and a page that ended on another account's lock."""

import json
import threading
import urllib.error
import urllib.request
from concurrent.futures import Future
from unittest import mock

from fedtail import i18n
from fedtail.frontends.web import server as web
from fedtail.protocols.mastodon import adapter

from . import fakes, test_cli
from .test_core import TmpDir


def done(value):
    f = Future()
    f.set_result(value)
    return f


def failed(exc):
    f = Future()
    f.set_exception(exc)
    return f


class WebGapsTest(TmpDir):
    make = test_cli.CliTest.make

    def setUp(self):
        super().setUp()
        i18n.setup("en")
        self.core, self.w = self.make()
        self.web = web.Web(self.core, None)

    def test_a_name_with_its_emoji(self):
        raw = dict(fakes.BOB, display_name="Bob :blob:",
                   emojis=[{"shortcode": "blob", "url": "https://x/blob.png",
                            "static_url": "https://x/blob.png"}])
        got = web.account_json(adapter.account(raw))
        self.assertIn("blob.png", got["name_html"])

    def test_a_name_with_its_emoji_in_activity(self):
        """An event's row names people as a card does: :blob: as its picture, the
        rest of the name escaped; a name without a code goes as plain text (30.10)."""
        from types import SimpleNamespace
        bob = adapter.account(dict(fakes.BOB, display_name="<b>Bob</b> :blob:", emojis=[
            {"shortcode": "blob", "url": "https://x/blob.png",
             "static_url": "https://x/blob.png"}]))
        ann = adapter.account(dict(fakes.BOB, id="A", display_name="Ann"))
        row = SimpleNamespace(kind="favourite", people=[bob, ann], entries=[], post=None,
                              request=False, more=0, what="liked", notice="",
                              unread=False)
        got = web.event_json(SimpleNamespace(extra={"row": row}, unread=False))
        (_name, url), plain = got["people"]  # pairs, as the phone reads them
        html, none = got["people_html"]
        self.assertEqual(url, "fedtail:account/" + bob.id)
        self.assertIn("/pic?u=https%3A%2F%2Fx%2Fblob.png", html)
        self.assertIn("&lt;b&gt;Bob", html)  # the name's own markup stays text
        self.assertEqual((plain, none), (["Ann", "fedtail:account/A"], ""))

    def test_the_pages_picture_times_are_the_windows(self):
        """When a picture that didn't come is asked again: the windows' times, given to
        the page — it kept a copy of its own (30.10)."""
        from fedtail.frontends.common.images import Cache
        self.assertEqual(self.web.me()["picture_later"], list(Cache.LATER_TRIES))
        # and the reading rule's numbers (common/lane.reading_now): the windows'
        self.core.cfg["read"].update(dwell_ms=900, unfocused_seconds=0)
        me = self.web.me()
        self.assertEqual((me["dwell_ms"], me["unfocused_seconds"]), (900, 0))

    def test_a_quote_drawn_once(self):
        """The page draws the quote: the server's "RE: <link>" line is out of the text, as
        in the windows (it showed the quote twice)."""
        st = fakes.status("094", fakes.BOB, text="look")
        st["content"] += '<p class="quote-inline">RE: <a href="x">x</a></p>'
        st["quote"] = {"state": "accepted", "quoted_status": fakes.status("093", fakes.NEWS)}
        got = web.post_json(self.web.core, adapter.post(st))
        self.assertNotIn("RE:", got["html"])
        self.assertTrue(got["quote"])

    def test_a_boosters_emoji_beside_the_words(self):
        """words.boosted_html: the boost's line with the booster's :blob: as its picture
        (the phone draws it; the words stay the windows')."""
        from fedtail.frontends.common.lane import CardSpec
        blob = [{"shortcode": "blob", "url": "https://x/blob.png",
                 "static_url": "https://x/blob.png"}]
        raw = fakes.status("097", dict(fakes.BOB, display_name="Bob :blob:", emojis=blob))
        raw["reblog"] = fakes.status("096", fakes.NEWS, text="news")
        share = adapter.post(raw)  # a boost: a Share around the post
        got = web.words_json(self.web.core, CardSpec(key="097", entry=share), web.web_date)
        self.assertIn("/pic?u=https%3A%2F%2Fx%2Fblob.png", got["boosted_html"])
        self.assertIn(":blob:", got["boosted"]["text"])

    def test_a_page_before_the_core_connected(self):
        self.assertIsNone(self.core.me)
        me = self.web.me()  # logged in, not connected yet: connected now
        self.assertTrue(me["handle"])
        # polling began with the page: its first round under way (or done), no slow mode
        text = self.web.slow()["text"]
        self.assertNotIn("slow", text)
        self.assertTrue(text == "" or "updat" in text, text)

    def test_profile_extras(self):
        self.core.connect().result()
        acc = adapter.account(dict(fakes.BOB, moved=fakes.NEWS))
        people = [adapter.account(dict(fakes.BOB, id=f"P{i}", acct=f"p{i}@x.example"))
                  for i in range(7)]
        v = self.web.core
        with mock.patch.object(v, "pinned", return_value=failed(OSError("x"))), \
                mock.patch.object(v, "supports", return_value=True), \
                mock.patch.object(v, "familiar", return_value=done(people)):
            out = self.web._profile_extras(acc, False, "posts")
        self.assertEqual(out["pinned"], [])  # it failed: the profile shows without
        self.assertIn("@p0", out["familiar"])
        self.assertIn(i18n._("act_more", n=2), out["familiar"])
        self.assertEqual(out["moved"]["account"]["id"], "N")

    def test_next_page_from_their_server(self):
        self.core.connect().result()
        self.core.poll_once()
        got = self.web.account_more("B", "nonsense", "", "end")
        self.assertEqual((got["posts"], got["older"]), ([], None))
        st = fakes.status("501", fakes.BOB, minute=1, vis="public", text="old")
        self.w.add(st, home=True)
        self.core.poll_once()
        post = self.web.core.by_id("501")
        with mock.patch.object(self.web, "_remote_host", return_value="social.example"), \
                mock.patch.object(self.web.core, "older_from_origin",
                                  return_value=done(([post], None))):
            got = self.web.account_more("B", "all", "", "origin")
        self.assertEqual([p["sid"] for p in got["posts"]], ["501"])
        self.assertIn("social.example", got["said"])
        with mock.patch.object(self.web, "_remote_host", return_value="social.example"), \
                mock.patch.object(self.web.core, "older_from_origin",
                                  return_value=done(([], None))):
            got = self.web.account_more("B", "all", "", "next-cursor")
        self.assertEqual(got["said"], "")

    def test_reply_as_not_found(self):
        self.core.connect().result()
        self.core.poll_once()
        st = fakes.status("502", fakes.BOB, minute=2, vis="public", text="hi")
        self.w.add(st, home=True)
        self.core.poll_once()
        merged = mock.Mock()
        merged.others = {"w": object()}
        merged.act_as.return_value = done(None)
        with mock.patch.object(self.web, "merged_core", return_value=merged), \
                mock.patch.object(self.web.core, "act_as", merged.act_as, create=True):
            with self.assertRaises(ValueError):
                self.web.act_as("502", "w", "reply")

    def test_completion_without_the_server(self):
        self.core.connect().result()
        with mock.patch.object(self.web.core, "search_people",
                               return_value=failed(OSError("x"))):
            got = self.web.complete("hi @zz")
        self.assertEqual(got["word"], "@zz")
        self.assertEqual(got["items"], [])  # nothing worth offering


class RoutesTest(TmpDir):
    make = test_cli.CliTest.make

    def setUp(self):
        super().setUp()
        i18n.setup("en")
        self.core, self.w = self.make()
        self.core.connect().result()
        self.core.poll_once()
        self.key = web.load_key(self.core.paths.data_dir)
        self.srv = web.make_server(self.core, "127.0.0.1", 0, self.key)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def req(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, headers={
            "Cookie": f"{web.COOKIE}={self.key}", "X-Fedtail": "1",
            "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_the_pages_errors_reach_the_log(self):
        """An error of the page's script is said in fedtail's log, not only in a browser's
        console; an address loses its query, where the page's key may ride."""
        with self.assertLogs("fedtail.frontends.web.server", "WARNING") as got:
            code, _r = self.req("/api/client_error", {
                "kind": "error", "message": "x is undefined at http://127.0.0.1/?k=SECRET",
                "where": "renderPost@http://127.0.0.1/app.js?t=SECRET:12:5"})
        self.assertEqual(code, 200)
        said = "\n".join(got.output)
        self.assertIn("web page error: x is undefined", said)
        self.assertIn("renderPost@http://127.0.0.1/app.js:12:5", said)
        self.assertNotIn("SECRET", said)

    def test_a_reply_starts_as_the_core_says(self):
        """The page's editor takes a reply's start from the core (common/compose.start),
        as the windows and the phone: it narrowed and copied the warning by a rule of its
        own, deaf to post.reply_never_wider and post.reply_warning (30.10)."""
        st = fakes.status("050", fakes.BOB, minute=5, text="spoilers inside")
        st.update(visibility="public", spoiler_text="the end of the film")
        self.w.add(st, home=True)
        self.core.poll_once()
        code, got = self.req("/api/draft_start", {"reply_to": "050"})
        self.assertEqual((code, got["visibility"], got["cw"]),
                         (200, "followers", "the end of the film"))  # the defaults
        self.core.cfg["post"].update(reply_never_wider=False, default_visibility="unlisted",
                                     reply_warning="none")
        code, got = self.req("/api/draft_start", {"reply_to": "050"})
        self.assertEqual((got["visibility"], got["cw"]), ("unlisted", ""))

    def test_the_newest_routes(self):
        code, got = self.req("/api/account_more?id=B&show=all&max_id=&cursor=end")
        self.assertEqual((code, got["older"]), (200, None))
        with mock.patch.object(self.srv.web, "origin_list",
                               return_value={"uris": []}) as ol:
            code, _got = self.req("/api/origin_list", {"id": "B", "cursor": "origin"})
        self.assertEqual(code, 200)
        ol.assert_called_with("B", "origin")
        with mock.patch.object(self.srv.web, "origin_fetch",
                               return_value={"posts": []}) as of:
            self.req("/api/origin_fetch", {"id": "B", "uris": ["https://x/1"]})
        of.assert_called_with("B", ["https://x/1"], None)
        code, _got = self.req("/api/act_as", {"id": "1", "tag": "w", "action": "fav"})
        self.assertEqual(code, 400)  # not all accounts in one: refused


class SwitchTurnsTest(TmpDir):
    """switch_profile's refusals: the same profile, one open elsewhere, one that won't
    connect; and the lock held before let go of once over."""

    def setUp(self):
        super().setUp()
        import os

        from fedtail.core import auth, config, paths, profiles
        from fedtail.core.app import Core
        i18n.setup("en")
        for var, sub in (("XDG_CONFIG_HOME", "cfg"), ("XDG_DATA_HOME", "data")):
            old = os.environ.get(var)
            os.environ[var] = str(self.tmp / sub)
            self.addCleanup(lambda v=var, o=old: os.environ.__setitem__(v, o)
                            if o is not None else os.environ.pop(v, None))
        fakes.FakeApi.world = fakes.World()
        home = paths.resolve()
        home.ensure()
        auth.save(home.auth_file, {"server": "https://example.test", "token": "tok"})
        cfg, _w = config.load(home.config_file)
        self.core = Core(cfg, home, api_class=fakes.FakeApi)
        self.core._origin_json = lambda url: None
        self.core.connect().result()
        profiles.remember(home, {"acct": "mira"}, "https://example.test")
        work = paths.resolve("work")
        work.ensure()
        auth.save(work.auth_file, {"server": "https://example.test", "token": "t2"})
        self.web = web.Web(self.core, None)
        self.addCleanup(lambda: self.web.core.shutdown())

    def test_the_turns(self):
        self.assertIsNone(self.web.switch_profile("default"))  # this one already
        with mock.patch("fedtail.core.instance.SingleInstance.poke_existing",
                        return_value=True):
            with self.assertRaises(ValueError):
                self.web.switch_profile("work")
        with mock.patch("fedtail.core.app.Core.connect", side_effect=OSError("down")):
            with self.assertRaises(OSError):
                self.web.switch_profile("work")
        held = mock.Mock()
        self.web.instance = held
        self.web.switch_profile("work")
        held.close.assert_called_once()
        self.assertEqual(self.web.core.paths.profile, "work")
        self.addCleanup(lambda: self.web.instance.close())


class RunEndsOnAnotherAccountTest(TmpDir):
    def test_the_lock_of_the_account_it_ended_on_let_go(self):
        """The page went over to another profile meanwhile: its lock is closed at the end."""
        import io
        import types

        from fedtail.frontends import web as web_frontend
        core = mock.Mock(logged_in=False)
        core.cfg = {"web": {"host": "127.0.0.1", "port": 0, "open_browser": False}}
        other = mock.Mock()
        srv = mock.Mock(server_address=("127.0.0.1", 1))
        srv.web.login_link.return_value = "http://127.0.0.1:1/login"

        def serve():
            srv.web.instance = other  # Accounts → another profile, while serving
        srv.serve_forever = serve

        class Stop(threading.Event):
            def wait(self, timeout=None):
                return True
        fake = types.SimpleNamespace(Timer=threading.Timer, Event=Stop,
                                     Thread=threading.Thread)
        with mock.patch.object(web_frontend.signal, "signal", lambda *_a: None), \
                mock.patch.object(web_frontend, "threading", fake), \
                mock.patch("fedtail.frontends.web.server.load_key", return_value="k"), \
                mock.patch("fedtail.frontends.web.server.make_server", return_value=srv), \
                mock.patch("sys.stderr", io.StringIO()), mock.patch("sys.stdout", io.StringIO()):
            started = mock.Mock()
            self.assertEqual(web_frontend.run(core, started, []), 0)
        other.close.assert_called_once()
        started.close.assert_not_called()


if __name__ == "__main__":
    import unittest
    unittest.main()
