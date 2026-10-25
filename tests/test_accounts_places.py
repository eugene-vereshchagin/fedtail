"""Accounts in the web page and the terminal (common/placesmore.py AccountPlaces): the
profiles listed, one added through a login (server, the page's address, the code),
made main, logged out of, logged in to again; the web page going over to another
account in place."""

import json
import os
import threading
import unittest
import urllib.request

from fedtail import i18n
from fedtail.core import auth, config, paths, profiles
from fedtail.core.app import Core
from fedtail.frontends.common import placesmore
from fedtail.frontends.common.places import Places
from fedtail.frontends.web import server as web

from . import fakes
from .fakes import FakeApi, status
from .test_core import TmpDir


class AccountsTest(TmpDir):
    def setUp(self):
        super().setUp()
        i18n.setup("en")
        for var, sub in (("XDG_CONFIG_HOME", "cfg"), ("XDG_DATA_HOME", "data")):
            old = os.environ.get(var)
            os.environ[var] = str(self.tmp / sub)
            self.addCleanup(lambda v=var, o=old: os.environ.__setitem__(v, o) if o is not None
                            else os.environ.pop(v, None))
        FakeApi.world = self.w = fakes.World()
        self.w.add(status("001", fakes.BOB, minute=1, text="hi"), home=True)
        home = paths.resolve()
        home.ensure()
        auth.save(home.auth_file, {"server": "https://example.test", "token": "tok",
                                   "client_id": "cid", "client_secret": "sec",
                                   "acct": "mira"})
        cfg, _w = config.load(home.config_file)
        self.core = Core(cfg, home, api_class=FakeApi)
        self.core._origin_json = lambda url: None
        self.addCleanup(lambda: self.core.shutdown())
        self.core.connect().result()
        profiles.remember(home, {"acct": "mira"}, "https://example.test")
        self.pl = Places(self.core)
        placesmore._LOGINS.clear()
        self.addCleanup(placesmore._LOGINS.clear)

    def names(self):
        return [r.key for r in self.pl.page("accounts").rows]

    def test_add_an_account_through_a_login(self):
        self.assertIn(("accounts", i18n._("accounts")), self.pl.menu())
        self.assertEqual(self.names(), ["default"])
        page = self.pl.page("accounts")
        self.assertEqual(page.more.act, ("accounts", "add", ""))
        self.assertTrue(self.pl.act("accounts", "add").ask)  # a name, first
        for bad in ("default", "themes", "no spaces", ""):
            self.assertTrue(self.pl.act("accounts", "add", answer=bad).error, bad)
        out = self.pl.act("accounts", "add", answer="work")
        self.assertEqual(out.open, {"page": "login", "arg": "work"})
        login = self.pl.page("login", "work")
        self.assertEqual([f.name for f in login.form], ["server"])
        self.assertTrue(self.pl.act("login", "begin", "work", {"server": ""}).error)
        out = self.pl.act("login", "begin", "work", {"server": "example.test"})
        self.assertIn("/oauth/authorize", out.open["url"])
        login = self.pl.page("login", "work")
        self.assertEqual([f.name for f in login.form], ["code"])
        self.assertIn("/oauth/authorize", login.rows[0].title)
        self.assertTrue(self.pl.act("login", "finish", "work", {"code": "bad"}).error)
        out = self.pl.act("login", "finish", "work", {"code": "good"})
        self.assertEqual(out.open, {"profile": "work"})
        self.assertIn("@", out.message)
        self.assertTrue(paths.resolve("work").auth_file.exists())
        listed = {p["name"]: p for p in profiles.listing()}
        self.assertTrue(listed["work"]["logged_in"])
        page = self.pl.page("accounts")
        row = next(r for r in page.rows if r.key == "work")
        self.assertEqual(row.buttons[0].act, ("accounts", "switch", "work"))
        self.assertEqual(self.pl.act("accounts", "switch", "work").open, {"profile": "work"})

    def test_main_relogin_logout(self):
        other = paths.resolve("work")
        other.ensure()
        auth.save(other.auth_file, {"server": "https://example.test", "token": "t2"})
        paths.set_main("work")
        me = next(r for r in self.pl.page("accounts").rows if r.key == "default")
        acts = [b.act[1] for b in me.buttons]
        self.assertEqual(acts, ["main", "relogin", "logout"])
        self.pl.act("accounts", "main")
        self.assertEqual(paths.main_profile(), "default")
        # log in again: asked, then the same account only
        self.assertTrue(self.pl.act("accounts", "relogin").confirm)
        out = self.pl.act("accounts", "relogin", confirmed=True)
        self.assertEqual(out.open, {"page": "login", "arg": "default"})
        login = self.pl.page("login", "default")
        self.assertEqual(login.form[0].value, "example.test")  # the server prefilled
        self.pl.act("login", "begin", "default", {"server": "example.test"})
        out = self.pl.act("login", "finish", "default", {"code": "good"})
        self.assertEqual(out.open, {"page": "accounts"})  # this same one, reconnected
        self.w.me = dict(self.w.me, acct="someone_else")
        self.pl.act("login", "begin", "default", {"server": "example.test"})
        out = self.pl.act("login", "finish", "default", {"code": "good"})
        self.assertIn("someone_else", out.error)  # another account: nothing saved
        # log out: asked (★ moves on, the page goes over), then done
        ask = self.pl.act("accounts", "logout")
        self.assertIn(profiles.label({"name": "work", "acct": "", "server": ""}), ask.confirm)
        self.assertNotIn("<br>", ask.confirm)
        out = self.pl.act("accounts", "logout", confirmed=True)
        self.assertEqual(out.open, {"profile": "work"})
        self.assertFalse(paths.resolve("default").auth_file.exists())
        self.assertEqual(paths.main_profile(), "work")

    def test_the_web_editor_spell_checks_by_the_option(self):
        """The page leaves spelling to the browser: on, unless post.spellcheck = false."""
        page = web.Web(self.core, "k")
        self.assertTrue(page.editor_facts()["spellcheck"])
        self.core.cfg["post"]["spellcheck"] = False
        self.assertFalse(page.editor_facts()["spellcheck"])

    def test_the_last_one_logged_out_goes_to_the_login(self):
        self.assertIn(i18n._("logout_last"), self.pl.act("accounts", "logout").confirm)
        out = self.pl.act("accounts", "logout", confirmed=True)
        self.assertEqual(out.open, {"page": "login", "arg": "default"})

    def test_the_web_page_goes_over_to_another_account(self):
        work = paths.resolve("work")
        work.ensure()
        auth.save(work.auth_file, {"server": "https://example.test", "token": "t2"})
        key = web.load_key(self.core.paths.data_dir)
        srv = web.make_server(self.core, "127.0.0.1", 0, key)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = f"http://127.0.0.1:{srv.server_address[1]}"

        def post(path, body):
            r = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={
                "Cookie": f"{web.COOKIE}={key}", "X-Fedtail": "1",
                "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(r, timeout=30) as resp:
                    return resp.status, json.loads(resp.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")
        old = srv.web.core
        code, got = post("/api/place", {"act": ["accounts", "switch", "work"]})
        self.assertEqual((code, got.get("reload")), (200, True))
        self.assertIsNot(srv.web.core, old)
        self.assertEqual(srv.web.core.paths.profile, "work")
        self.addCleanup(lambda: srv.web.core.shutdown())
        self.assertIsNotNone(srv.web.instance)
        self.addCleanup(lambda: srv.web.instance.close())
        code, _got = post("/api/place", {"act": ["accounts", "switch", "nobody"]})
        self.assertEqual(code, 400)  # not logged in there


if __name__ == "__main__":
    unittest.main()
