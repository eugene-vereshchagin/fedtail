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
        self.assertEqual(marks(page), ["▶", "·", "·"])
        self.assertTrue(p.act("sync", "where", "", {}).error)  # nothing named
        out = p.act("sync", "where", "", {"url": "", "folder": str(self.tmp / "meet")})
        self.assertEqual(out.open, {"page": "sync"})
        import tomllib  # as TOML reads it (Windows' backslashes are escaped in the file)
        written = tomllib.loads(core.paths.config_file.read_text("utf-8"))
        self.assertEqual(written["sync"]["folder"], str(self.tmp / "meet"))
        page = p.page("sync")  # a folder: no login — on to the key, the fork
        self.assertEqual(page.tab, "key")
        self.assertEqual(marks(page), ["✓", "✓", "▶"])
        self.assertEqual([r.key for r in page.rows if not r.key.startswith("step:")][:2],
                         ["first", "join"])  # nothing in the store: the first one first
        self.assertEqual(p.page("sync", "", "first").submit.act[1], "first")
        out = p.act("sync", "first", "")
        self.assertIn("key is ready", out.message)
        page = p.page("sync")
        self.assertEqual(page.tab, "done")
        self.assertEqual(marks(page), ["✓", "✓", "✓"])

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
        self.assertEqual([r.key for r in page.rows if not r.key.startswith("step:")][:2],
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
