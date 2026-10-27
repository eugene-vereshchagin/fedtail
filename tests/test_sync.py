"""Sync between an account's devices (core/sync) and the fedtail-sync server."""

import io
import json
import threading
import unittest
import urllib.request

from fedtail.core import auth, config, paths
from fedtail.core.app import Core
from fedtail.core.sync import backends, crypto, engine
from fedtail.frontends import cli

from . import fakes
from .fakes import BOB, FakeApi, status
from .test_core import TmpDir

try:
    import cryptography  # noqa: F401
    HAVE_CRYPTO = True
except ImportError:
    HAVE_CRYPTO = False
need_crypto = unittest.skipUnless(HAVE_CRYPTO, "needs the cryptography package")


def load_server():
    """syncserver/fedtail_sync.py: a file of its own, outside the package."""
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "syncserver" / "fedtail_sync.py"
    spec = importlib.util.spec_from_file_location("fedtail_sync", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@need_crypto
class CryptoTest(unittest.TestCase):
    def test_sealed_opens_only_with_its_key(self):
        key, other = crypto.new_key(), crypto.new_key()
        blob = crypto.seal(key, {"ops": [{"r": ["1", "2"]}]})
        self.assertEqual(crypto.unseal(key, blob), {"ops": [{"r": ["1", "2"]}]})
        self.assertEqual(crypto.blob_key_id(blob), crypto.key_id(key))
        self.assertNotIn(b'"r"', blob)  # nothing readable inside
        with self.assertRaises(crypto.BadBlob):
            crypto.unseal(other, blob)
        broken = blob[:-1] + bytes([blob[-1] ^ 1])
        with self.assertRaises(crypto.BadBlob):
            crypto.unseal(key, broken)
        with self.assertRaises(crypto.BadBlob):
            crypto.blob_key_id(b"hello")

    def test_key_text_survives_a_person(self):
        key = crypto.new_key()
        text = crypto.key_text(key)
        self.assertEqual(crypto.key_from_text(text), key)
        self.assertEqual(crypto.key_from_text(" " + text.lower().replace("-", " ") + "\n"), key)
        with self.assertRaises(ValueError):
            crypto.key_from_text("not a key")
        with self.assertRaises(ValueError):
            crypto.key_from_text(text[:-4])


class Devices(TmpDir):
    """Two devices of one account (same fake server), meeting in a folder."""

    def device(self, name, world, **sync):
        FakeApi.world = world
        user = {"feed": {"first_run_mark_read": False}, "ui": {"language": "en"},
                "sync": {"folder": str(self.tmp / "meet"), **sync}}
        cfg, _ = config.validate(user)
        p = paths.resolve(name, config=str(self.tmp / f"{name}.toml"),
                          data=str(self.tmp / name))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(cfg, p, api_class=FakeApi)
        core._origin_json = lambda url: None
        core.events_seen = []
        core.events.on("*", lambda name, payload: core.events_seen.append((name, payload)))
        self.addCleanup(core.shutdown)
        core.connect().result()
        return core

    def setUp(self):
        super().setUp()
        from fedtail import i18n
        was = i18n.current_language()
        i18n.setup("en")  # the texts checked below are the English ones
        self.addCleanup(i18n.setup, was)
        (self.tmp / "meet").mkdir()
        self.world = fakes.World()
        self.desk = self.device("desk", self.world)
        self.phone = self.device("phone", self.world)


@need_crypto
class FolderSyncTest(Devices):
    def test_read_marks_travel(self):
        self.desk.mark_read(["101", "102"])
        self.assertEqual(self.desk.sync_now(), (1, 0))
        self.assertIsNotNone(self.phone.sync_join(self.desk.sync_key()))
        self.assertEqual(self.phone.sync_now(), (0, 2))
        self.assertEqual(self.phone.store.read_set(["101", "102", "103"]), {"101", "102"})
        self.assertIn(("read_changed", ["101", "102"]),
                      [(n, sorted(p)) for n, p in self.phone.events_seen if n == "read_changed"])
        # and back
        self.phone.mark_read(["103"])
        self.phone.sync_now()
        self.desk.sync_now()
        self.assertEqual(self.desk.store.read_set(["103"]), {"103"})

    def test_own_marks_dont_come_back_and_automatic_ones_stay_home(self):
        self.desk.store.mark_read(["900"])  # fedtail's own (first run, older history)
        self.desk.mark_read(["901"])
        self.desk.sync_now()
        self.phone.sync_join(self.desk.sync_key())
        self.phone.sync_now()
        self.assertEqual(self.phone.store.read_set(["900", "901"]), {"901"})
        self.assertEqual(self.desk.sync_now(), (0, 0))  # its own journal isn't news to it

    def test_a_device_without_the_key_waits_for_it(self):
        self.desk.mark_read(["1"])
        self.desk.sync_now()
        self.assertIsNone(self.phone.sync_now())  # someone's journal is there: no new key
        self.assertIn("sync join", self.phone.sync_status()["last"]["error"])
        self.assertTrue(any(n == "error" for n, _ in self.phone.events_seen))
        self.assertIsNone(self.phone.sync_key())

    def test_another_key_is_told_not_merged(self):
        self.desk.mark_read(["1"])
        self.desk.sync_now()
        self.phone.sync_join(crypto.key_text(crypto.new_key()))  # the wrong one
        self.assertEqual(self.phone.sync_now(), (0, 0))
        self.assertEqual(self.phone.store.read_set(["1"]), set())
        self.assertIn("sync join", self.phone.sync_status()["last"]["error"])
        self.assertTrue(self.phone.sync_status()["key"])

    def test_thread_states_newest_wins(self):
        root = self.world.add(status("500", fakes.ME, minute=1))
        self.world.add(status("501", BOB, reply_to="500", reply_acc="ME", minute=2))
        self.desk.subscribe(root).result()
        self.desk.sync_now()
        self.phone.sync_join(self.desk.sync_key())
        self.phone.sync_now()
        self.assertTrue(self.phone.subscribed(root))
        self.phone.unsubscribe(root).result()  # left there later
        self.phone.sync_now()
        self.desk.sync_now()
        self.assertFalse(self.desk.subscribed(root))
        # a stale "sub" from long ago changes nothing
        self.assertFalse(self.desk.store.sync_newer("t:500", 1, "zz", "sub"))

    def test_the_thread_sends_by_itself_and_at_exit(self):
        import time
        self.desk.mark_read(["5"])
        self.desk.sync.start()
        deadline = time.monotonic() + 5
        while self.desk.store.sync_pending_count() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(self.desk.store.sync_pending_count(), 0)
        self.desk.mark_read(["6"])
        self.desk.sync.stop()  # its last round sends what came just now
        self.assertEqual(self.desk.store.sync_pending_count(), 0)

    def test_nothing_recorded_when_not_wanted(self):
        core = self.device("quiet", self.world, read=False)
        core.mark_read(["7"])
        self.assertEqual(core.store.sync_pending_count(), 0)

    def test_list_order_and_saved_tag_lanes_travel(self):
        for core in (self.desk, self.phone):  # the same account: the same lists
            core._apply_lists([{"id": "L1", "title": "one", "exclusive": False},
                               {"id": "L2", "title": "two", "exclusive": False},
                               {"id": "L3", "title": "three", "exclusive": False}], {})
        self.desk.move_list("L3", -1)
        self.desk.move_list("L3", -1)
        self.desk.save_tag_group({"any": ["tbilisi", "georgia"]}, "Georgia").result()
        self.desk.sync_now()
        self.phone.sync_join(self.desk.sync_key())
        self.phone.events_seen.clear()
        self.phone.sync_now()
        self.assertEqual([x["id"] for x in self.phone.lists], ["L3", "L1", "L2"])
        self.assertEqual([g["name"] for g in self.phone.tag_groups if g["saved"]], ["Georgia"])
        self.assertTrue(any(n == "lists_changed" for n, _ in self.phone.events_seen))
        # moved on the phone later: the desk follows; nothing comes back as an echo
        self.phone.move_list("L2", -1)
        self.phone.sync_now()
        self.desk.sync_now()
        self.assertEqual([x["id"] for x in self.desk.lists], ["L3", "L2", "L1"])
        self.assertEqual(self.desk.store.sync_pending_count(), 0)
        # an old order from long ago changes nothing; a strange shape is not taken
        self.assertFalse(self.desk.store.sync_newer("k:list_order", 1, "zz", "[]"))
        self.assertEqual(self.desk.sync.apply(
            {"d": "zz", "ops": [{"k": "list_order", "v": "L1", "at": 2 ** 50}]}), 0)
        self.assertEqual([x["id"] for x in self.desk.lists], ["L3", "L2", "L1"])

    def test_lanes_stay_home_when_not_wanted(self):
        core = self.device("quiet", self.world, lanes=False)
        core._apply_lists([{"id": "L1", "title": "a", "exclusive": False},
                           {"id": "L2", "title": "b", "exclusive": False}], {})
        core.move_list("L2", -1)
        self.assertEqual(core.store.sync_pending_count(), 0)

    def test_drafts_travel_without_their_pictures_and_go_when_sent(self):
        self.desk.save_draft("reply:77", {"text": "half a thought", "cw": "", "media":
                                          [["/home/me/cat.jpg", "a cat"]],
                                          "visibility": "public"})
        self.desk.save_draft("reply:77", {"text": "a whole thought", "cw": "", "media":
                                          [["/home/me/cat.jpg", "a cat"]],
                                          "visibility": "public"})
        self.desk.save_draft("new", {"text": "", "cw": "", "media": [["/x.png", ""]]})
        self.desk.sync_now()
        self.phone.sync_join(self.desk.sync_key())
        self.phone.store.save_draft("reply:77", {"text": "old", "media": [["/sd/dog.jpg", ""]]})
        self.phone.sync_now()
        got = self.phone.get_draft("reply:77")
        self.assertEqual(got["text"], "a whole thought")  # the last version only
        self.assertEqual(got["media"], [["/sd/dog.jpg", ""]])  # its own pictures stay
        self.assertIsNone(self.phone.get_draft("new"))  # pictures only: nothing to carry
        self.assertTrue(any(n == "drafts_changed" for n, _ in self.phone.events_seen))
        self.phone.delete_draft("reply:77")  # sent from the phone
        self.phone.sync_now()
        self.desk.sync_now()
        self.assertIsNone(self.desk.get_draft("reply:77"))

    def test_dismissed_activity_goes_everywhere(self):
        for core in (self.desk, self.phone):
            core.store.activity_put([
                {"id": "n1", "type": "favourite", "created_at": "2026-10-01T10:00:00Z",
                 "account": {"id": "9", "acct": "bob"}},
                {"id": "n2", "type": "favourite", "created_at": "2026-10-01T11:00:00Z",
                 "account": {"id": "9", "acct": "bob"}}])
        self.desk.dismiss_activity("n1").result()
        self.desk.sync_now()
        self.phone.sync_join(self.desk.sync_key())
        self.phone.events_seen.clear()
        self.phone.sync_now()
        left = [e["id"] for e in self.phone.activity_entries()]
        self.assertEqual(left, ["n2"])
        self.assertIn("n1", self.phone.store.kv_get("activity_hidden"))
        self.assertTrue(any(n == "activity_updated" for n, _ in self.phone.events_seen))

    def test_pinned_tiles_travel(self):
        self.desk.set_pinned_tiles(["home", "mentions", "list:L1"])
        self.desk.sync_now()
        self.phone.sync_join(self.desk.sync_key())
        self.phone.sync_now()
        self.assertEqual(self.phone.pinned_tiles(), ["home", "mentions", "list:L1"])
        self.assertIn(("tiles_changed", ["home", "mentions", "list:L1"]),
                      self.phone.events_seen)

    def test_each_switch_keeps_its_thing_home(self):
        core = self.device("quiet", self.world, drafts=False, activity=False, tiles=False)
        core.save_draft("new", {"text": "x"})
        core.set_pinned_tiles(["home"])
        core.sync._flush_drafts()
        self.assertEqual(core.store.sync_pending_count(), 0)

    def test_folder_backend_pages_and_skips_its_own(self):
        b = backends.FolderBackend(self.tmp / "meet")
        for i in range(backends.PAGE + 5):
            b.push(f"blob{i}".encode(), "aaaaaaaaaaaaaaaa")
        b.push(b"mine", "bbbbbbbbbbbbbbbb")
        got, cur, more = b.pull(None, "bbbbbbbbbbbbbbbb")
        self.assertEqual((len(got), more), (backends.PAGE, True))
        got2, cur, more = b.pull(cur, "bbbbbbbbbbbbbbbb")
        self.assertEqual((len(got2), more), (5, False))
        self.assertNotIn(b"mine", got + got2)
        self.assertEqual(b.pull(cur, "bbbbbbbbbbbbbbbb")[0], [])


class SyncOffTest(TmpDir):
    def test_off_records_nothing_and_says_so(self):
        FakeApi.world = fakes.World()
        cfg, _ = config.validate({"ui": {"language": "en"}})
        p = paths.resolve("o", config=str(self.tmp / "o.toml"), data=str(self.tmp / "o"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(cfg, p, api_class=FakeApi)
        self.addCleanup(core.shutdown)
        core.mark_read(["1"])
        self.assertIsNone(core.sync)
        self.assertEqual(core.store.sync_pending_count(), 0)
        out = io.StringIO()
        with self.assertRaises(SystemExit) as e:
            cli.run(core, ["sync", "status"], stream=out)
        self.assertIn("sync.url", str(e.exception.code))

    def test_off_without_an_address_and_the_old_switch_is_told(self):
        cfg, warns = config.validate({"sync": {"enabled": True, "backend": "server"}})
        self.assertFalse(engine.wanted(cfg))
        self.assertTrue(any("sync.enabled is gone" in w for w in warns))
        self.assertTrue(engine.wanted(config.validate(
            {"sync": {"url": "https://sync.example"}})[0]))
        self.assertTrue(engine.wanted(config.validate({"sync": {"folder": "~/meet"}})[0]))

    def test_the_old_what_list_becomes_switches(self):
        cfg, warns = config.validate({"sync": {"what": ["read"], "drafts": True}})
        self.assertEqual({k: cfg["sync"][k] for k in config.SYNC_WHAT},
                         {"read": True, "threads": False, "lanes": False, "drafts": True,
                          "activity": False, "tiles": False, "lane_rules": False,
                          "people": False})
        self.assertTrue(any("sync.what is now" in w for w in warns))

    def test_config_is_checked(self):
        with self.assertRaises(config.ConfigError):
            config.validate({"sync": {"read": "yes"}})
        with self.assertRaises(config.ConfigError):
            config.validate({"sync": {"url": "http://sync.example"}})
        with self.assertRaises(config.ConfigError):
            config.validate({"sync": {"url": "https://sync.example", "folder": "~/meet"}})
        cfg, _ = config.validate({"sync": {"url": "https://sync.example"}})
        self.assertEqual(cfg["sync"]["interval_seconds"], 60)


class SyncLineTest(Devices):
    """The status bar's word and About's row (frontends/common/syncline.py)."""

    def test_off_waiting_done_and_trouble(self):
        from fedtail.frontends.common import about, syncline
        off = self.device("off", self.world, folder="")
        self.assertEqual(syncline.bar(off)[0], "⇅ off")
        self.assertIn("sync.url", syncline.bar(off)[1])
        self.assertIn("sync.url", dict(about.facts(off).rows)["Sync"])
        self.assertEqual(syncline.bar(self.desk)[0], "⇅ …")
        if HAVE_CRYPTO:
            self.desk.mark_read(["1"])
            self.desk.sync_now()
            text, tip = syncline.bar(self.desk)
            self.assertRegex(text, r"^⇅ \d\d:\d\d$")
            self.assertIn("sent 1", tip)
            self.assertTrue(any(n == "sync_changed" for n, _ in self.desk.events_seen))
            self.assertIsNone(self.phone.sync_now())  # no key here yet
            self.assertEqual(syncline.bar(self.phone)[0], "⇅ !")
            self.assertIn("sync join", syncline.bar(self.phone)[1])
        self.assertIn(str(self.tmp / "meet"), syncline.about(self.desk))


# ---- the client against the real server (the server's own tests: syncserver/tests/) -------

class ClientServerTest(TmpDir):
    TOKENS = {("me.example", "t-me"): "1", ("me.example", "t-me2"): "1",
              ("me.example", "t-you"): "2"}

    def setUp(self):
        super().setUp()
        syncserver = load_server()
        self.mod = syncserver
        self.app = syncserver.Server(
            {"db": str(self.tmp / "s.db"), "instances": ["me.example"], "quota_mb": 1,
             "listen": "127.0.0.1:0",
             "max_blob_kb": 64},
            verify=lambda host, token: self.TOKENS.get((host, token)))
        self.httpd = syncserver.make_http_server(self.app)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        t.start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def call(self, method, path, token=None, body=None, instance="https://me.example",
             device=""):
        req = urllib.request.Request(self.url + path, data=body, method=method)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("X-Fedtail-Instance", instance)
        if device:
            req.add_header("X-Fedtail-Device", device)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    @need_crypto
    def test_two_devices_through_the_server(self):
        b1 = backends.HttpBackend(self.url, "https://me.example", "t-me")
        b2 = backends.HttpBackend(self.url, "https://me.example", "t-me2")
        key = crypto.new_key()
        b1.push(crypto.seal(key, {"d": "a", "ops": [{"r": ["9"]}]}), "a" * 16)
        got, cur, more = b2.pull(None, "b" * 16)
        self.assertEqual(crypto.unseal(key, got[0])["ops"], [{"r": ["9"]}])
        self.assertEqual((cur, more), (1, False))
        self.assertEqual(b1.pull(None, "a" * 16)[0], [])  # its own: skipped
        with self.assertRaises(backends.BackendError) as e:
            backends.HttpBackend(self.url, "https://me.example", "bad").pull(None, "c" * 16)
        self.assertEqual(e.exception.kind, "auth")


class CliSyncTest(Devices):
    def run_cli(self, name, *argv):
        """A command on that device, as from a terminal: a Core of its own, shut after."""
        out = io.StringIO()
        cli.run(self.device(name, self.world), list(argv), stream=out)
        return out.getvalue()

    @need_crypto
    def test_key_join_now_status(self):
        self.assertIn("fedtail sync join", self.run_cli("desk", "sync", "key"))  # none yet
        self.desk.mark_read(["42"])
        self.assertIn("sent 1", self.run_cli("desk", "sync", "now"))
        shown = self.run_cli("desk", "sync", "key").strip().splitlines()[-1]
        self.assertEqual(crypto.key_text(crypto.key_from_text(shown)), shown)
        self.assertIn("(id ", self.run_cli("phone", "sync", "join", shown))
        self.run_cli("phone", "sync", "now")
        # the command's own Core wrote the marks; this one has its read set in memory
        # already (the lanes are counted after every background event): read it anew
        self.phone.store._read = None
        self.assertEqual(self.phone.store.read_set(["42"]), {"42"})
        status = self.run_cli("phone", "sync", "status")
        self.assertIn("folder", status)
        self.assertIn(crypto.key_id(crypto.key_from_text(shown)).hex(), status)
        with self.assertRaises(SystemExit):
            self.run_cli("phone", "sync", "join", "nonsense")


class LoginTest(Devices):
    def test_the_sync_token_is_a_narrow_one(self):
        out = io.StringIO()
        cli.run(self.device("desk", self.world), ["sync", "login", "good"], stream=out)
        self.assertIn("scope=read:accounts", out.getvalue())
        self.assertIn(("fedtail sync", "read:accounts"), self.world.apps)
        saved = engine.load_auth(engine.auth_path(self.desk.paths))
        self.assertEqual(saved["token"], "tok-read-accounts")
        self.assertNotEqual(saved["token"], auth.load(self.desk.paths.auth_file)["token"])


if __name__ == "__main__":
    unittest.main()


@need_crypto
class LaneRulesSyncTest(Devices):
    """sync.lane_rules: the lanes themselves, written into the other device's config.toml."""

    def setUp(self):
        TmpDir.setUp(self)
        from fedtail import i18n
        was = i18n.current_language()
        i18n.setup("en")
        self.addCleanup(i18n.setup, was)
        (self.tmp / "meet").mkdir()
        self.world = fakes.World()
        self.desk = self.device("desk", self.world, lane_rules=True)
        self.phone = self.device("phone", self.world, lane_rules=True)

    def test_the_lanes_travel(self):
        import tomllib
        self.assertEqual(self.desk.sync_now()[0], 0)  # a start sends nothing of its own
        self.phone.sync_join(self.desk.sync_key())
        mine = [{"name": "pics", "icon": "list", "any": [{"has": "image"}]}]
        from fedtail.core import config_edit
        cfg, _w = config_edit.save(self.desk.paths.config_file,
                                   {("lanes", "custom"): mine,
                                    ("lanes", "enabled"): ["home", "pics"]})
        self.desk.lanes_saved(cfg)
        self.assertIn("pics", self.desk.lane_by_name)
        self.assertEqual(self.desk.sync_now()[0], 1)
        self.phone.sync_now()
        got = tomllib.loads(self.phone.paths.config_file.read_text("utf-8"))
        self.assertEqual(got["lanes"]["custom"], mine)
        self.assertEqual(got["lanes"]["enabled"], ["home", "pics"])
        self.assertIn("pics", self.phone.lane_by_name)
        self.assertEqual(self.phone.sync_now(), (0, 0))  # nothing goes back

    def test_off_by_default(self):
        cfg, _ = config.validate({})
        self.assertFalse(cfg["sync"]["lane_rules"])
