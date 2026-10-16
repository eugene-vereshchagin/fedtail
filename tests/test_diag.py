import faulthandler
import logging
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from pathlib import Path

from fedtail import diag
from fedtail.core import config, paths


class DiagTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.paths = paths.resolve("t", config=str(tmp / "c.toml"), data=str(tmp / "d"))
        self.paths.ensure()
        self.paths.config_file.write_text("[ui]\n", "utf-8")
        self.paths.auth_file.write_text('{"token": "SECRET"}', "utf-8")
        self.cfg, _ = config.validate({})
        root = logging.getLogger()
        self._saved = (root.handlers[:], root.level, sys.excepthook, threading.excepthook)

    def tearDown(self):
        root = logging.getLogger()
        for h in root.handlers:
            h.close()
        root.handlers[:], root.level = self._saved[0], self._saved[1]
        sys.excepthook, threading.excepthook = self._saved[2], self._saved[3]
        faulthandler.disable()
        for f in ("crash", "stacks"):
            if diag._state[f]:
                diag._state[f].close()
                diag._state[f] = None
        self._tmp.cleanup()

    def test_log_stats_watchdog_report(self):
        folder = diag.setup(self.paths, self.cfg)
        diag.session_header("t")
        diag.add_stats("demo", lambda: {"things": 3})
        s = diag.log_stats()
        self.assertGreater(s["rss_mb"], 0)
        self.assertEqual(s["demo.things"], 3)

        dog = diag.Watchdog(0.2)
        dog.start()
        time.sleep(1.6)  # no beats: the GUI "hangs"
        dog.beat()
        dog.stop()
        for h in logging.getLogger().handlers:
            h.flush()
        text = (folder / "fedtail.log").read_text("utf-8")
        self.assertIn("session start", text)
        self.assertIn('"demo.things": 3', text)
        self.assertIn("hasn't answered", text)
        self.assertIn("responsive again", text)
        self.assertIn("thread MainThread", text)

        try:
            raise ValueError("boom")
        except ValueError:
            diag._excepthook(*sys.exc_info())
        for h in logging.getLogger().handlers:
            h.flush()
        self.assertIn("ValueError: boom", (folder / "fedtail.log").read_text("utf-8"))

        out = diag.bug_report(self.paths, self.paths.data_dir)
        with tarfile.open(out) as tar:
            names = tar.getnames()
            everything = b"".join(tar.extractfile(m).read() for m in tar.getmembers()
                                  if m.isfile())
        self.assertIn("logs/fedtail.log", names)
        self.assertIn("system.txt", names)
        self.assertIn("config.toml", names)
        self.assertNotIn(b"SECRET", everything)  # the token never goes in

    def test_timed(self):
        with self.assertLogs("fedtail.diag", level="WARNING") as got:
            with diag.timed("slow thing", warn_s=0.01):
                time.sleep(0.05)
        self.assertIn("slow thing took", got.output[0])


if __name__ == "__main__":
    unittest.main()
