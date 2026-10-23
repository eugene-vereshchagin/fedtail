"""The Android app's Python door (android/app/src/main/python/fedtail_android/bridge.py)
works on any Python: the core comes up in the folders it is given, logs in with the
code coming back to the app, and gives a lane's cards — no phone needed."""

import importlib.util
import json
import os
from pathlib import Path
from unittest import mock

from .test_core import TmpDir

BRIDGE = (Path(__file__).resolve().parent.parent / "android" / "app" / "src" / "main"
          / "python" / "fedtail_android" / "bridge.py")


def load_bridge():
    spec = importlib.util.spec_from_file_location("fedtail_android_bridge", BRIDGE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class BridgeTest(TmpDir):
    def setUp(self):
        super().setUp()
        self.files, self.cache = self.tmp / "files", self.tmp / "cache"
        self.files.mkdir()
        self.cache.mkdir()
        env = mock.patch.dict(os.environ, {}, clear=False)  # XDG_*, LANG come back after
        env.start()
        self.addCleanup(env.stop)
        from fedtail import i18n
        self.addCleanup(i18n.setup, i18n.current_language())
        self.bridge = load_bridge()
        self.addCleanup(lambda: self.bridge._s["core"] and self.bridge._s["core"].shutdown())

    def call(self, name, *args):
        got = json.loads(getattr(self.bridge, name)(*args))
        if isinstance(got, dict):
            self.assertNotIn("error", got, got.get("trace") or got.get("error"))
        return got

    def test_the_core_starts_in_the_apps_folders(self):
        got = json.loads(self.bridge.start(str(self.files), str(self.cache), "en", False))
        self.assertNotIn("error", got, got.get("trace"))
        self.assertTrue(got["version"])
        self.assertIn("statuses", got["store"])
        self.assertEqual(got["profiles"], ["default"])
        self.assertIn("started_ms", got)
        # everything the core wrote is inside the app's own folders
        self.assertTrue((self.files / "config" / "fedtail" / "default" / "config.toml").exists())
        self.assertTrue((self.files / "data" / "fedtail" / "default" / "state.db").exists())
        self.assertEqual(self.call("state")["logged_in"], False)

    def test_a_broken_core_is_told_not_thrown(self):
        self.bridge.start(str(self.files), str(self.cache), "en", False)
        with mock.patch("fedtail.core.paths.data_base", side_effect=OSError("disk gone")):
            got = json.loads(self.bridge.info())
        self.assertEqual(got["error"], "OSError: disk gone")
        self.assertIn("error", json.loads(self.bridge.lane("nowhere")))

    def test_login_comes_back_to_the_app(self):
        from fedtail.core import config, paths
        from fedtail.core.app import Core

        from . import fakes
        self.bridge.start(str(self.files), str(self.cache), "en", False)
        fakes.FakeApi.world = fakes.World()
        self.bridge._s["core"].shutdown()
        cfg, _ = config.validate({})
        self.bridge._s["core"] = Core(cfg, paths.resolve(None), api_class=fakes.FakeApi)
        got = self.call("login_begin", "https://example.test")
        self.assertTrue(got["redirect"])
        self.assertIn("redirect_uri=fedtail://oauth", got["url"])
        self.assertEqual(fakes.FakeApi.world.redirects, ["fedtail://oauth"])
        self.assertEqual(self.call("login_finish", "good\n")["acct"], "mira")
        self.assertTrue(self.call("state")["logged_in"])
        self.assertIn("error", json.loads(self.bridge.login_begin("  ")))

    def test_demo_world_lanes_and_marks(self):
        got = json.loads(self.bridge.start(str(self.files), str(self.cache), "ru", True))
        self.assertNotIn("error", got, got.get("trace"))
        self.assertTrue(got["demo"])
        opened = self.call("open")
        self.assertEqual(opened["me"]["handle"], "mira")
        names = [x["name"] for x in opened["lanes"]]
        self.assertIn("home", names)
        lane = self.call("lane", "home", False)
        self.assertTrue(lane["posts"])
        first = lane["posts"][0]
        for key in ("id", "alias", "account", "created", "text", "unread"):
            self.assertIn(key, first)
        self.assertNotIn("<p>", first["text"])  # words, not HTML
        unread = [p["id"] for p in lane["posts"] if p["unread"]]
        self.assertTrue(unread)
        v = self.bridge.wait(-1, 0.1)  # something changed since "never"
        self.assertEqual(self.call("read", json.dumps(unread[:1])), {"ok": True})
        self.assertNotEqual(self.bridge.wait(v, 2), v)
        again = self.call("lane", "home", True)
        self.assertFalse(next(p for p in again["posts"] if p["id"] == unread[0])["unread"])
        self.assertEqual(self.call("pause", True), {"ok": True})
        self.assertEqual(self.call("pause", False), {"ok": True})
        self.assertEqual(self.call("refresh"), {"ok": True})
        self.assertTrue((self.files / "data" / "fedtail" / "demo" / "state.db").exists())

    def demo(self):
        got = json.loads(self.bridge.start(str(self.files), str(self.cache), "en", True))
        self.assertNotIn("error", got, got.get("trace"))
        self.call("open")

    def test_thread_and_writing(self):
        self.demo()
        th = self.call("thread", "101")
        ids = [p["sid"] for p in th["posts"]]
        self.assertEqual(ids[0], "100")  # from the root, whatever was opened
        self.assertIn("103", ids)
        self.assertTrue(all("depth" in p and "number" in p and "text" in p for p in th["posts"]))
        self.assertGreater(max(p["depth"] for p in th["posts"]), 0)
        sent = self.call("post", json.dumps({"text": "a reply from the phone",
                                             "reply_to": "103"}))
        self.assertTrue(sent["id"])
        from tests import fakes
        self.assertEqual(fakes.FakeApi.world.posted[-1][2], "103")
        liked = self.call("act", "like", "106")
        self.assertIn("text", liked)
        self.assertIn("error", json.loads(self.bridge.post(json.dumps({"text": "  "}))))

    def test_config_is_edited_in_the_app(self):
        self.demo()
        text = self.call("config_text")["text"]
        self.assertIn("[sync]", text)
        bad = json.loads(self.bridge.config_save(text + "\n[feed]\norder = \"sideways\"\n"))
        self.assertIn("error", bad)
        self.assertEqual(self.call("config_text")["text"], text)  # nothing landed
        self.assertIn("error", json.loads(self.bridge.config_save("this = is = not toml")))
        old_core = self.bridge._s["core"]
        mine = text.replace('[sync]\n', '[sync]\n# mine\n')
        self.assertEqual(self.call("config_save", mine), {"ok": True})
        self.assertIsNot(self.bridge._s["core"], old_core)  # made anew with it
        self.assertIn("# mine", self.call("config_text")["text"])

    def test_sync_from_the_phone(self):
        from fedtail.core.sync import crypto
        if not crypto.available():
            self.skipTest("needs cryptography")
        self.demo()
        self.assertEqual(self.call("sync_status"), {"enabled": False, "key": False})
        meet = self.tmp / "meet"
        meet.mkdir()
        text = self.call("config_text")["text"]
        head, _, sync = text.partition("[sync]\n")
        sync = sync.replace("enabled = false", "enabled = true", 1)
        sync = sync.replace('backend = "server"', 'backend = "folder"', 1)
        sync = sync.replace('folder = ""', f'folder = "{meet.as_posix()}"', 1)
        on = head + "[sync]\n" + sync
        self.assertEqual(self.call("config_save", on), {"ok": True})
        self.call("open")
        st = self.call("sync_status")
        self.assertTrue(st["enabled"])
        self.assertEqual(st["backend"], "folder")
        self.assertEqual(self.call("sync_now"), {"sent": 0, "got": 0})
        key = self.call("sync_key")["key"]
        self.assertTrue(key)
        other = crypto.key_text(crypto.new_key())
        self.assertTrue(self.call("sync_join", other)["kid"])
        self.assertEqual(self.call("sync_key")["key"], other)
        self.assertIn("error", json.loads(self.bridge.sync_join("nonsense")))

    def test_the_overview_of_lanes(self):
        self.demo()
        hub = self.call("hub")
        kinds = {s["key"]: [x["name"] for x in s["lanes"]] for s in hub["sections"]}
        self.assertEqual(list(kinds)[0], "you")  # what is addressed to you comes first
        self.assertIn("replies", kinds["you"])
        self.assertIn("home", kinds["reading"])
        self.assertIn("federated", kinds["browse"])  # no counts: only browsed
        lanes = {x["name"]: x for s in hub["sections"] for x in s["lanes"]}
        self.assertEqual(lanes["federated"]["unread"], 0)
        self.assertTrue(lanes["home"]["unread"])
        self.assertIn(":", lanes["home"]["peek"])  # who: what
        # reading in a row: only lanes with news, yours first
        self.assertEqual(hub["order"], [x for x in hub["order"] if lanes[x]["unread"]])
        self.assertLess(hub["order"].index("replies"), hub["order"].index("home"))
        self.assertEqual(hub["unread"], sum(lanes[x]["unread"] for x in hub["order"]))

    def test_the_command_line_is_off_on_the_phone_unless_asked(self):
        self.demo()
        self.assertFalse(self.call("open")["me"]["command_line"])
        text = self.call("config_text")["text"]
        self.assertEqual(self.call("config_save", text + "\n"), {"ok": True})
        self.assertFalse(self.call("open")["me"]["command_line"])  # the file didn't say
        self.assertIn("command_line = false", text)  # written into the file, once
        on = text.replace("command_line = false", "command_line = true", 1)
        self.assertEqual(self.call("config_save", on), {"ok": True})
        self.assertTrue(self.call("open")["me"]["command_line"])
        alias = self.call("lane", "home", False)["posts"][0]["alias"]
        self.assertIn(alias, self.call("command_preview", f"#{alias} hello")["text"])
        got = self.call("command", f"#{alias}", False)
        self.assertTrue(got["ok"])
        self.assertIn("thread", got["open"])

    def test_a_cards_menu_and_links(self):
        self.demo()
        got = self.call("open")
        self.assertEqual(got["me"]["overview"], "tiles")
        self.assertEqual(got["me"]["layout"], "auto")
        m = self.call("menu", "103")
        self.assertIn("subscribed", m)
        self.assertIn("url", m)
        self.assertTrue(self.call("thread_act", "sub", "103")["message"])
        self.assertTrue(self.call("menu", "103")["subscribed"])
        self.assertIn("found", self.call("resolve", "https://nowhere.example/@x/1"))
        self.assertIn("error", json.loads(self.bridge.thread_act("sideways", "103")))

    def test_pinned_lanes_come_as_tiles_in_their_order(self):
        self.demo()
        self.assertEqual(self.call("hub")["pinned"], [])  # none: every counted lane
        text = self.call("config_text")["text"]
        mine = text.replace("pinned = []", 'pinned = ["home", "list:новости", "replies"]', 1)
        self.assertEqual(self.call("config_save", mine), {"ok": True})
        self.call("open")
        self.assertEqual(self.call("hub")["pinned"], ["home", "list:L1", "replies"])
        bad = text.replace("pinned = []", 'pinned = ["sideways"]', 1)
        self.assertIn("phone.pinned", json.loads(self.bridge.config_save(bad))["error"])

    def test_the_settings_page(self):
        self.demo()
        got = self.call("settings")
        titles = [c["title"] for c in got["chapters"]]
        self.assertTrue(titles)
        opts = {(o["section"], o["key"]): o for c in got["chapters"] for o in c["options"]}
        self.assertNotIn(("web", "port"), opts)  # the desktop's browser: not here
        order = opts[("feed", "order")]
        self.assertEqual(order["type"], "str")
        self.assertIn("newest_first", order["choices"])
        self.assertTrue(order["help"])
        self.assertEqual(opts[("ui", "command_line")]["value"], False)  # the phone's
        self.assertEqual(opts[("phone", "pinned")]["type"], "list")
        before = self.bridge._s["core"]
        self.assertEqual(self.call("setting_set", "feed", "order", '"newest_first"')["value"],
                         "newest_first")
        self.assertIn('order = "newest_first"', self.call("config_text")["text"])
        bad = json.loads(self.bridge.setting_set("feed", "order", '"sideways"'))
        self.assertIn("error", bad)
        self.assertIn('order = "newest_first"', self.call("config_text")["text"])  # kept
        self.assertEqual(self.call("setting_set", "phone", "pinned", '["home"]')["value"],
                         ["home"])
        self.assertIs(self.bridge._s["core"], before)  # not remade at every tap…
        self.assertEqual(self.call("settings_apply"), {"restarted": True})  # …but on leaving
        self.assertIsNot(self.bridge._s["core"], before)
        self.assertEqual(self.call("settings_apply"), {"restarted": False})
