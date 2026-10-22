"""The Android app's Python door (android/app/src/main/python/fedtail_android/bridge.py)
works on any Python: the core comes up in the folders it is given and says what it is."""

import importlib.util
import json
import os
import unittest
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
    def test_the_core_starts_in_the_apps_folders(self):
        bridge = load_bridge()
        files, cache = self.tmp / "files", self.tmp / "cache"
        files.mkdir()
        cache.mkdir()
        with mock.patch.dict(os.environ, {}, clear=False):
            got = json.loads(bridge.start(str(files), str(cache)))
            self.assertNotIn("error", got, got.get("trace"))
            self.assertTrue(got["version"])
            self.assertIn("statuses", got["store"])
            self.assertEqual(got["profiles"], ["default"])
            self.assertIn("started_ms", got)
            # everything the core wrote is inside the app's own folders
            self.assertTrue((files / "config" / "fedtail" / "default" / "config.toml").exists())
            self.assertTrue((files / "data" / "fedtail" / "default" / "state.db").exists())

    def test_a_broken_core_is_told_not_thrown(self):
        bridge = load_bridge()
        with mock.patch("fedtail.core.paths.resolve", side_effect=OSError("disk gone")):
            got = json.loads(bridge.info())
        self.assertEqual(got["error"], "OSError: disk gone")


if __name__ == "__main__":
    unittest.main()
