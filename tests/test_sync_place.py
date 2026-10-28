"""≡ → Sync (common/syncplace.py): the whole setup without a terminal — where the
devices meet (used at once), the key shown, pasted, kept in the journal under a password
and taken from there with the password alone, or made anew."""

from fedtail.core.sync import crypto
from fedtail.core.view import View
from fedtail.frontends.common.places import Places

from .test_sync import Devices, need_crypto


@need_crypto
class SyncPlaceTest(Devices):
    def place(self, core):
        return Places(View(core))

    def test_where_is_set_from_the_window(self):
        core = self.device("fresh", self.world)
        core.paths.config_file.write_text("", "utf-8")
        core.cfg["sync"]["folder"] = ""
        self.assertFalse(core.sync_setup())  # nowhere: off
        p = self.place(core)
        self.assertIn("Off", [r.title for r in p.page("sync", "", "where").rows])
        out = p.act("sync", "where", "", {"url": "", "folder": str(self.tmp / "meet")})
        self.assertEqual(out.message, "Sync is on")
        self.assertIsNotNone(core.sync)
        self.assertIn(str(self.tmp / "meet"), core.paths.config_file.read_text("utf-8"))
        page = p.page("sync", "", "where")
        self.assertIn("folder", " ".join(r.line for r in page.rows))
        self.assertTrue(p.act("sync", "now", "").message.startswith("sent"))

    def test_the_key_by_password_without_the_other_device(self):
        self.desk.mark_read(["101"])
        self.desk.sync_now()  # the desk's journal, its key made there
        p_desk = self.place(self.desk)
        self.assertTrue(p_desk.act("sync", "show", "").confirm)
        shown = p_desk.act("sync", "show", "", confirmed=True)
        self.assertEqual(shown.copy, self.desk.sync_key())
        self.assertIn("short", p_desk.act("sync", "escrow", "",
                                          {"password": "abc", "password2": "abc"}).error)
        self.assertIn("differ", p_desk.act("sync", "escrow", "", {
            "password": "correct horse", "password2": "correct hors"}).error)
        p_desk.act("sync", "escrow", "", {"password": "correct horse battery",
                                          "password2": "correct horse battery"})
        # the phone: no key, only the password
        self.phone.sync_now()
        p_phone = self.place(self.phone)
        page = p_phone.page("sync", "", "key")
        self.assertIn("password", [f.name for f in page.form])
        self.assertEqual(next(f for f in page.form if f.name == "password").kind, "secret")
        self.assertIn("doesn't fit", p_phone.act("sync", "take", "",
                                                 {"password": "wrong one!"}).error)
        out = p_phone.act("sync", "take", "", {"password": "correct horse battery"})
        self.assertIn("key saved", out.message)
        self.assertEqual(self.phone.sync_key(), self.desk.sync_key())
        self.phone.sync_now()
        self.assertEqual(self.phone.store.read_set(["101"]), {"101"})

    def test_the_key_pasted_and_made_anew(self):
        self.desk.mark_read(["101"])
        self.desk.sync_now()
        p_phone = self.place(self.phone)
        self.assertIn("not a sync key", p_phone.act("sync", "take", "", {"key": "nope"}).error)
        p_phone.act("sync", "take", "", {"key": self.desk.sync_key()})
        self.assertEqual(self.phone.sync_key(), self.desk.sync_key())
        # the laptop in the office: the old key not at hand, a new one
        laptop = self.device("laptop", self.world)
        p = self.place(laptop)
        self.assertTrue(p.act("sync", "fresh", "").confirm)
        p.act("sync", "fresh", "", confirmed=True)
        self.assertNotEqual(laptop.sync_key(), self.desk.sync_key())
        laptop.sync_now()
        self.assertNotIn("another key", (laptop.sync_status()["last"] or {}).get("error", ""))
        old = crypto.key_id(crypto.key_from_text(self.desk.sync_key())).hex()
        self.assertIn(old, laptop.store.kv_get("sync.left_keys"))

    def test_login_tab_with_a_folder(self):
        page = self.place(self.desk).page("sync", "", "login")
        self.assertIn("no login", page.rows[0].title)
