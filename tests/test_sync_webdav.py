"""Sync through a WebDAV folder spoken directly (core/sync/backends.py DavTree): the
journal's files, the pictures of drafts and packing the journal as in a folder; the
password asked once and kept in the data folder, never in the config; the place's
steps; a wrong password, a folder without a parent."""

import os
import stat

from fedtail.core.sync import backends, crypto, engine
from fedtail.core.view import View
from fedtail.frontends.common.places import Places

from .davserver import Dav
from .test_sync import Devices, need_crypto


class DavBackendTest(Devices):
    def setUp(self):
        super().setUp()
        (self.tmp / "dav").mkdir()
        self.dav = Dav(self.tmp / "dav")
        self.addCleanup(self.dav.close)

    def backend(self, folder="fed tail", password="secret"):
        return backends.WebDavBackend(self.dav.url + folder, "me", password)

    def test_the_journal_as_files(self):
        b = self.backend()
        a, other = "a" * 16, "b" * 16
        self.assertEqual([b.push(f"blob{i}".encode(), a) for i in range(3)], [1, 2, 3])
        self.assertTrue((self.tmp / "dav" / "fed tail" / a / "000000000003.fts").is_file())
        b.push(b"theirs", other)
        got, cursor, more = self.backend().pull(None, other)  # a new round: a new backend
        self.assertEqual((got, cursor, more), ([b"blob0", b"blob1", b"blob2"], {a: 3}, False))
        self.assertEqual(b.pull(cursor, other)[0], [])
        self.assertEqual(b.pull(None, a)[0], [b"theirs"])
        self.assertEqual(b.compact(a, 3), 2)  # its own older files go, the newest stays
        self.assertEqual(b.pull(None, other)[0], [b"blob2"])
        self.assertEqual(b.compact(a, 99), 0)  # never the last one
        name = "c" * 48
        self.assertIsNone(b.media_get(name))
        b.media_put(name, b"picture")
        b.media_put(name, b"picture")  # there already: not put again
        self.assertEqual(b.media_get(name), b"picture")
        b.media_delete(name)
        b.media_delete(name)
        self.assertIsNone(b.media_get(name))
        puts = [c for c in self.dav.calls if c[0] == "PUT" and "/media/" in c[1]]
        self.assertEqual(len(puts), 1)

    def test_no_dtd_in_an_answer(self):
        """Someone's server's XML: a DTD (the billion laughs, an entity to a file) is
        refused, not expanded."""
        from fedtail.core.sync.backends import _xml
        with self.assertRaises(ValueError):
            _xml(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>')
        self.assertEqual(_xml(b'<d:multistatus xmlns:d="DAV:"/>').tag, "{DAV:}multistatus")

    def test_refused_and_gone(self):
        with self.assertRaises(backends.BackendError) as e:
            self.backend(password="wrong").pull(None, "a" * 16)
        self.assertEqual(e.exception.kind, "auth")
        with self.assertRaises(backends.BackendError) as e:
            self.backend(folder="no/such/place").push(b"x", "a" * 16)
        self.assertEqual(e.exception.kind, "gone")
        self.dav.close()
        with self.assertRaises(backends.BackendError) as e:
            self.backend().pull(None, "a" * 16)
        self.assertEqual(e.exception.kind, "other")
        self.assertIn("WebDAV", str(e.exception))

    @need_crypto
    def test_two_devices_and_the_password_kept_apart(self):
        for core in (self.desk, self.phone):
            core.cfg["sync"]["folder"] = ""
            core.sync_setup(webdav=self.dav.url + "fedtail")
            self.assertIsNone(core.sync_now())  # no password yet: says so
            self.assertIn("WebDAV", core.sync_status()["last"]["error"])
            self.assertEqual(core.sync_status()["login"], "")
        self.assertIn("won't let in", self.desk.sync_webdav_login("me", "nope"))
        self.assertFalse(engine.webdav_path(self.desk.paths).exists())  # nothing kept
        self.assertIsNone(self.desk.sync_webdav_login("me", "secret"))
        f = engine.webdav_path(self.desk.paths)
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)
        text = self.desk.paths.config_file.read_text("utf-8")
        self.assertNotIn("secret", text)
        self.assertIn('webdav_user = "me"', text)
        self.assertEqual(self.desk.sync_status()["backend"], "webdav")
        self.assertEqual(self.desk.sync_status()["login"], "me")
        self.desk.mark_read(["101", "102"])
        self.assertEqual(self.desk.sync_now()[0], 1)
        self.phone.sync_webdav_login("me", "secret")
        self.phone.sync_join(self.desk.sync_key())
        self.phone.sync_now()
        self.assertEqual(self.phone.store.read_set(["101", "102"]), {"101", "102"})
        self.assertTrue(crypto.blob_key_id(next(
            (self.tmp / "dav" / "fedtail" / self.desk.sync.device).iterdir()).read_bytes()))

    @need_crypto
    def test_the_place_asks_the_user_and_password(self):
        core = self.desk
        core.cfg["sync"]["folder"] = ""
        p = Places(View(core))
        out = p.act("sync", "where", "", {"url": "", "folder": "",
                                           "webdav": self.dav.url + "fedtail"})
        self.assertFalse(out.error, out.error)
        page = p.page("sync")
        self.assertEqual(page.tab, "login")
        self.assertEqual([f.name for f in page.form], ["user", "password"])
        self.assertEqual(page.form[1].kind, "secret")
        self.assertIn("won't let in", p.act("sync", "dav", "", {"user": "me",
                                                                "password": "x"}).error)
        self.assertTrue(p.act("sync", "dav", "", {"user": "", "password": ""}).error)
        out = p.act("sync", "dav", "", {"user": "me", "password": "secret"})
        self.assertFalse(out.error, out.error)
        self.assertEqual(p.page("sync").tab, "key")  # on to the key, as a folder does
