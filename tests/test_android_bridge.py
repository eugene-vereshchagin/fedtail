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
