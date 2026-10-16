import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fedtail.core import config, saving


class SavingTest(unittest.TestCase):
    def test_names(self):
        self.assertEqual(saving.file_name("https://x.org/media/a%20b.png?x=1"), "a_b.png")
        self.assertEqual(saving.file_name("https://x.org/m/abc", "image/webp; q"), "abc.webp")
        self.assertEqual(saving.file_name("https://x.org/"), "picture.jpg")

    def test_never_overwrites(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            p = saving.free_path(d, "cat.png")
            p.write_bytes(b"1")
            self.assertEqual(saving.free_path(d, "cat.png").name, "cat-1.png")

    def test_where(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            (Path(d) / "user-dirs.dirs").write_text('XDG_DOWNLOAD_DIR="$HOME/Загрузки"\n')
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": d, "HOME": "/home/u"}):
                self.assertEqual(saving.downloads_dir(), Path("/home/u/Загрузки"))
                cfg, _ = config.validate({})
                self.assertEqual(saving.save_dir(cfg), Path("/home/u/Загрузки"))
                cfg, _ = config.validate({"ui": {"save_dir": "~/Pics"}})
                self.assertEqual(saving.save_dir(cfg), Path("/home/u/Pics"))
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d, \
                mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": d, "HOME": "/home/u"}):
            self.assertEqual(saving.downloads_dir(), Path("/home/u/Downloads"))


if __name__ == "__main__":
    unittest.main()
