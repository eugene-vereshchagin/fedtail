"""The pictures' and videos' cache lives in $XDG_CACHE_HOME/fedtail/<profile>, the
user's only (0700), not in ~/.local/share (11.11: caches cleaned by cron missed it); the
old one in the data folder moves there."""

import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from fedtail.core import paths


class CacheDirTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        env = {"XDG_CONFIG_HOME": str(self.tmp / "c"), "XDG_DATA_HOME": str(self.tmp / "d"),
               "XDG_CACHE_HOME": str(self.tmp / "k")}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_in_the_xdg_cache(self):
        p = paths.resolve("work")
        self.assertEqual(p.cache_dir, self.tmp / "k" / "fedtail" / "work")
        p.ensure()
        self.assertTrue(p.cache_dir.is_dir())
        if sys.platform != "win32":
            for d in (p.cache_dir, p.cache_dir.parent):
                self.assertEqual(stat.S_IMODE(d.stat().st_mode), 0o700, d)

    def test_the_old_one_moves(self):
        p = paths.resolve("work")
        old = p.data_dir / "cache"
        old.mkdir(parents=True)
        (old / "pic").write_text("x")
        p.ensure()
        self.assertFalse(old.exists())
        self.assertEqual((p.cache_dir / "pic").read_text(), "x")

    def test_both_there_the_old_goes(self):
        p = paths.resolve("work")
        old = p.data_dir / "cache"
        old.mkdir(parents=True)
        p.cache_dir.mkdir(parents=True)
        p.ensure()
        for _ in range(100):
            if not old.exists():
                break
            time.sleep(0.02)
        self.assertFalse(old.exists())

    def test_a_data_folder_given_keeps_it(self):
        p = paths.resolve("t", config=str(self.tmp / "x.toml"), data=str(self.tmp / "mine"))
        self.assertEqual(p.cache_dir, self.tmp / "mine" / "cache")

    def test_windows_without_xdg_keeps_it_in_localappdata(self):
        with mock.patch.object(paths, "WINDOWS", True), \
                mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.tmp / "L")}):
            os.environ.pop("XDG_CACHE_HOME")
            os.environ.pop("XDG_DATA_HOME")
            p = paths.resolve("work")
        self.assertEqual(p.cache_dir, self.tmp / "L" / "fedtail" / "work" / "cache")


if __name__ == "__main__":
    unittest.main()
