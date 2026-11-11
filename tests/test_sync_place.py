"""≡ → Sync (common/syncplace.py), step by step: where the devices meet, the login, then
the fork — the first device (its key made here) or one more (the key pasted from another
device, or taken out of the journal with its password) — and then how it goes."""

from fedtail.core.sync import crypto
from fedtail.core.view import View
from fedtail.frontends.common.places import Places

from .test_sync import Devices, need_crypto


def marks(page):
    return [r.title[:1] for r in page.rows if r.key.startswith("step:")]


@need_crypto
class SyncPlaceTest(Devices):
    def place(self, core):
        return Places(View(core))

    def test_first_device_step_by_step(self):
        core = self.device("fresh", self.world)
        core.paths.config_file.write_text("", "utf-8")
        core.cfg["sync"]["folder"] = ""
        core.sync_setup()
        p = self.place(core)
        page = p.page("sync")
        self.assertEqual(page.tab, "where")  # step 1 first
        self.assertEqual(marks(page), ["▶", "·"])  # login: a WebDAV folder's step only
        # the folder's field: the phone offers its picker beside it (SafTree.kt, 11.11)
        self.assertEqual([f.name for f in page.form if f.folder], ["folder"])
        self.assertTrue(p.act("sync", "where", "", {}).error)  # nothing named
        out = p.act("sync", "where", "", {"url": "", "folder": str(self.tmp / "meet")})
        self.assertEqual(out.open, {"page": "sync"})
        import tomllib  # as TOML reads it (Windows' backslashes are escaped in the file)
        written = tomllib.loads(core.paths.config_file.read_text("utf-8"))
        self.assertEqual(written["sync"]["folder"], str(self.tmp / "meet"))
        page = p.page("sync")  # a folder: no login — on to the key, the fork
        self.assertEqual(page.tab, "key")
        self.assertEqual(marks(page), ["✓", "▶"])
        rows = [r.key for r in page.rows if not r.key.startswith("step:")]
        self.assertEqual(rows[0], "not_yet")  # said plainly: nothing syncs yet (02.11)
        self.assertEqual(rows[1:3], ["first", "join"])  # nothing in the store: the first one first
        self.assertEqual(p.page("sync", "", "first").submit.act[1], "first")
        out = p.act("sync", "first", "")
        self.assertIn("key is ready", out.message)
        page = p.page("sync")
        self.assertEqual(page.tab, "done")
        self.assertEqual(marks(page), ["✓", "✓"])
        self.assertNotIn("not_yet", [r.key for r in page.rows])

    def test_one_more_device_by_password(self):
        self.desk.mark_read(["101"])
        self.desk.sync_now()  # the desk: its journal, its key
        p_desk = self.place(self.desk)
        self.assertTrue(p_desk.act("sync", "show", "").confirm)  # "sure?" first
        shown = p_desk.act("sync", "show", "", confirmed=True)
        self.assertEqual(shown.open, {"page": "sync_key"})
        page = p_desk.page("sync_key")  # its QR code to scan, its text to copy
        from fedtail.frontends.common import qr
        self.assertEqual(next(r for r in page.rows if r.kind == "qr").data,
                         qr.rows(qr.matrix(self.desk.sync_key())))
        self.assertEqual(next(r for r in page.rows if r.kind == "pre").title,
                         self.desk.sync_key())
        self.assertEqual(p_desk.act("sync", "copykey", "").copy, self.desk.sync_key())
        from fedtail.frontends.web.server import Web  # the web page and the phone: JSON
        got = Web(View(self.desk), None).page("sync_key")
        row = next(r for r in got["rows"] if r.get("qr"))
        self.assertIn("<svg", row["html"])
        self.assertEqual(row["qr"], qr.rows(qr.matrix(self.desk.sync_key())))
        join = Web(View(self.phone), None).page("sync", "", "join")
        self.assertTrue(next(f for f in join["form"] if f["name"] == "key")["scan"])
        page = p_desk.page("sync")  # done: the password is a row of its own, not a form
        self.assertFalse(page.form)
        row = next(r for r in page.rows if r.key == "escrow")
        self.assertIn("Not set", row.line)
        page = p_desk.page("sync", "", "escrow")
        self.assertEqual(page.tab, "escrow")
        self.assertIn("NOT your account", page.hint)
        self.assertEqual([f.name for f in page.form], ["password", "password2"])
        self.assertIn("short", p_desk.act("sync", "escrow", "",
                                          {"password": "abc", "password2": "abc"}).error)
        p_desk.act("sync", "escrow", "", {"password": "correct horse battery",
                                          "password2": "correct horse battery"})
        row = next(r for r in p_desk.page("sync").rows if r.key == "escrow")
        self.assertIn("Set:", row.line)
        p_phone = self.place(self.phone)
        page = p_phone.page("sync")
        self.assertEqual(page.tab, "key")
        # a journal there already: "add to those set up" first, and said why
        self.assertEqual([r.key for r in page.rows
                          if not r.key.startswith("step:") and r.key != "not_yet"][:2],
                         ["join", "first"])
        self.assertTrue(p_phone.act("sync", "first", "").error)  # not the first device
        page = p_phone.page("sync", "", "join")
        pw = next(f for f in page.form if f.name == "password")
        self.assertEqual(pw.kind, "secret")
        self.assertIn("doesn't fit", p_phone.act("sync", "take", "",
                                                 {"password": "wrong one!"}).error)
        out = p_phone.act("sync", "take", "", {"password": "correct horse battery"})
        self.assertIn("key saved", out.message)
        self.assertEqual(self.phone.sync_key(), self.desk.sync_key())
        self.assertEqual(self.phone.store.read_set(["101"]), {"101"})  # synced at once

    def test_one_more_device_by_the_key_and_starting_over(self):
        self.desk.mark_read(["101"])
        self.desk.sync_now()
        p_phone = self.place(self.phone)
        self.assertIn("not a sync key", p_phone.act("sync", "take", "", {"key": "nope"}).error)
        p_phone.act("sync", "take", "", {"key": self.desk.sync_key()})
        self.assertEqual(self.phone.sync_key(), self.desk.sync_key())
        laptop = self.device("laptop", self.world)
        p = self.place(laptop)
        self.assertTrue(p.act("sync", "fresh", "").confirm)
        p.act("sync", "fresh", "", confirmed=True)
        self.assertNotEqual(laptop.sync_key(), self.desk.sync_key())
        laptop.sync_now()
        self.assertNotIn("another key", (laptop.sync_status()["last"] or {}).get("error", ""))
        old = crypto.key_id(crypto.key_from_text(self.desk.sync_key())).hex()
        self.assertIn(old, laptop.store.kv_get("sync.left_keys"))

    def test_turned_off(self):
        p = self.place(self.desk)
        self.assertTrue(p.act("sync", "off", "").confirm)
        p.act("sync", "off", "", confirmed=True)
        self.assertIsNone(self.desk.sync)
        self.assertEqual(p.page("sync").tab, "where")


@need_crypto
class KeyWithTheServerTest(Devices):
    """The key's QR code carries the sync server's address: a fresh device scanning it
    needs nothing typed — no step 1 (02.11: "put the address into the QR too")."""

    def setUp(self):
        super().setUp()
        import threading

        from .test_sync import load_server, server_file
        if server_file() is None:
            self.skipTest("fedtail-syncserver is not checked out here")
        mod = load_server()
        self.app = mod.Server({"db": str(self.tmp / "s.db"), "quota_mb": 1,
                               "listen": "127.0.0.1:0", "max_blob_kb": 64})
        code = self.app.invite_add("tests")
        httpd = mod.make_http_server(self.app)
        self.url = f"http://127.0.0.1:{httpd.server_address[1]}"
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        self.addCleanup(self.app.db.close)
        self.desk = self.device("desk", self.world, folder="")
        self.place(self.desk).act("sync", "where", "", {"url": self.url, "invite": code})
        self.place(self.desk).act("sync", "first", "")

    def place(self, core):
        return Places(View(core))

    def test_the_qr_brings_the_address(self):
        from urllib.parse import quote
        link = self.desk.sync_key_link()
        self.assertTrue(link.startswith(crypto.LINK))
        self.assertIn(quote(self.url, safe=""), link)
        self.assertEqual(crypto.read_key_link(link), (self.desk.sync_key(), self.url))
        page = self.place(self.desk).page("sync_key")
        self.assertIn("server", next(r for r in page.rows if r.key == "qr").line)
        # a fresh phone: nothing set up; from step 1 straight to the scan
        phone = self.device("phone", self.world, folder="")
        p = self.place(phone)
        page = p.page("sync")
        self.assertEqual(page.tab, "where")
        self.assertIn("scan", [r.key for r in page.rows])
        out = p.act("sync", "take", "", {"key": link})
        self.assertFalse(out.error)
        self.assertEqual(phone.cfg["sync"]["url"], self.url)
        self.assertEqual(phone.sync_key(), self.desk.sync_key())
        self.assertEqual(p.page("sync").tab, "done")

    def test_a_step_one_without_a_key_does_not_say_on(self):
        phone = self.device("phone2", self.world, folder="")
        out = self.place(phone).act("sync", "where", "", {"url": self.url})
        self.assertEqual(out.message, "The address is saved. Sync starts once this device "
                                      "has the key — the next step")
        page = self.place(phone).page("sync")
        self.assertEqual(marks(page), ["✓", "▶"])  # no "✓ login: none needed"
        self.assertIn("not_yet", [r.key for r in page.rows])

    def test_a_bad_link_changes_nothing(self):
        phone = self.device("phone3", self.world, folder="")
        out = self.place(phone).act("sync", "take", "",
                                    {"key": crypto.LINK + "NOPE?server=https%3A%2F%2Fx.test"})
        self.assertTrue(out.error)
        self.assertEqual(phone.cfg["sync"]["url"], "")
