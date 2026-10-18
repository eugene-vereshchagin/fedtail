import faulthandler
import logging
import os
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
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        tmp = Path(self._tmp.name)
        self.paths = paths.resolve("t", config=str(tmp / "c.toml"), data=str(tmp / "d"))
        self.paths.ensure()
        self.paths.config_file.write_text("[ui]\n", "utf-8")
        self.paths.auth_file.write_text('{"token": "SECRET"}', "utf-8")
        self.cfg, _ = config.validate({"debug": {"mode": "on", "log_dir": str(tmp / "logs")}})
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
        self.assertEqual(folder, tmp_logs := Path(self._tmp.name) / "logs" / "t")
        # the watchdog's own thread writes its dump: on a slow machine that may still be
        # going on when the beat comes
        end = time.time() + 10
        while True:
            for h in logging.getLogger().handlers:
                h.flush()
            text = (tmp_logs / "latest.log").read_text("utf-8")
            if "hasn't answered" in text or time.time() > end:
                break
            time.sleep(0.05)
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
        self.assertIn("ValueError: boom", (folder / "latest.log").read_text("utf-8"))

        out = diag.bug_report(self.paths, self.paths.data_dir, cfg=self.cfg)
        with tarfile.open(out) as tar:
            names = tar.getnames()
            everything = b"".join(tar.extractfile(m).read() for m in tar.getmembers()
                                  if m.isfile())
        self.assertTrue(any(n.startswith("logs/20") and n.endswith(".log") for n in names))
        self.assertNotIn("logs/latest.log", names)  # the link, not a second copy
        self.assertIn("system.txt", names)
        self.assertIn("config.toml", names)
        self.assertNotIn(b"SECRET", everything)  # the token never goes in

    def test_debug_mode_switch(self):
        import fedtail
        self.assertTrue(diag.enabled({"debug": {"mode": "on"}}))
        self.assertFalse(diag.enabled({"debug": {"mode": "off"}}))
        self.assertTrue(diag.enabled({"debug": {"mode": "off"}}, forced=True))  # --debug
        keep = fedtail.__version__
        try:
            fedtail.__version__ = "1.2.0"
            self.assertFalse(diag.enabled({"debug": {"mode": "auto"}}))  # a release: quiet
            fedtail.__version__ = "1.3.0.dev4"
            self.assertTrue(diag.enabled({"debug": {"mode": "auto"}}))
            fedtail.__version__ = "0.9.0"
            self.assertFalse(diag.enabled({"debug": {"mode": "auto"}}))  # a release: quiet
        finally:
            fedtail.__version__ = keep
        cfg, _ = config.validate({"debug": {"mode": "off",
                                            "log_dir": str(Path(self._tmp.name) / "logs")}})
        folder = diag.setup(self.paths, cfg)
        self.assertEqual(folder, self.paths.data_dir / "logs")  # not the debugging folder
        self.assertFalse(diag.is_on())
        logging.getLogger("fedtail.x").info("chatter")
        logging.getLogger("fedtail.x").warning("trouble")
        for h in logging.getLogger().handlers:
            h.flush()
        text = (folder / "latest.log").read_text("utf-8")
        self.assertIn("trouble", text)
        self.assertNotIn("chatter", text)
        diag._state["dir"] = None
        diag._state["on"] = True

    def test_old_logs_go(self):
        """A new version starts with a clean log folder; the logs the old default put in
        the home folder go too; the log goes to the data folder unless told otherwise."""
        from fedtail import version
        tmp = Path(self._tmp.name)
        keep = diag.OLD_LOG_DIR
        diag.OLD_LOG_DIR = str(tmp / "home-logs")
        try:
            old_home = tmp / "home-logs" / "t"
            old_home.mkdir(parents=True)
            (old_home / "2026-10-01_10-00-00.log").write_text("old", "utf-8")
            (old_home / "crash.log").write_text("old", "utf-8")
            # the old default in a config means the new default
            cfg, _ = config.validate({"debug": {"mode": "on", "log_dir": diag.OLD_LOG_DIR}})
            folder = self.paths.data_dir / "logs"
            folder.mkdir(parents=True)
            (folder / "version").write_text("0.0.1.dev1+gold\n", "utf-8")
            (folder / "2026-10-02_10-00-00.log").write_text("old", "utf-8")
            (folder / "fedtail.log").write_text("first versions' one file", "utf-8")
            (folder / "fedtail.log.1").write_text("old", "utf-8")
            (folder / "notes.txt").write_text("not ours", "utf-8")
            self.assertEqual(diag.setup(self.paths, cfg), folder)
            self.assertFalse(old_home.exists())  # and ~/fedtail-logs itself, empty now
            self.assertFalse((tmp / "home-logs").exists())
            self.assertFalse((folder / "2026-10-02_10-00-00.log").exists())
            self.assertEqual(list(folder.glob("fedtail.log*")), [])
            self.assertTrue((folder / "notes.txt").exists())  # not ours: left alone
            now = version.info()["version"].replace(" (dirty)", "")
            self.assertEqual((folder / "version").read_text("utf-8").strip(), now)
            # the same version again: this run's log stays
            for h in logging.getLogger().handlers:
                h.close()
            diag._state["dir"] = None
            for f in ("crash", "stacks"):
                diag._state[f].close()
                diag._state[f] = None
            ours = sorted(folder.glob("2*.log"))
            self.assertTrue(ours)
            diag.setup(self.paths, cfg)
            self.assertTrue(all(f.exists() for f in ours))
            # the terminal interface owns the screen: no log lines printed over it
            diag.quiet_console()
            self.assertFalse(any(getattr(h, "stream", None) is sys.stderr
                                 for h in logging.getLogger().handlers))
        finally:
            diag.OLD_LOG_DIR = keep
            diag._state["dir"] = None

    def test_stall_meter_says_where_the_gui_froze(self):
        meter = diag.StallMeter(100, interval=0.02)
        meter.start()
        try:
            meter.tick()
            with self.assertLogs("fedtail.diag", "WARNING") as caught:
                with diag.busy("lane home: draw"):
                    time.sleep(0.5)  # the "GUI thread" (this one) is stuck in our code
                meter.tick()
            line = caught.output[0]
            self.assertIn("GUI froze", line)
            self.assertIn("lane home: draw", line)
            self.assertIn("test_diag.py", line)  # where in the code it was
            self.assertEqual(meter.counts()["count"], 1)
            meter.tick()  # quick ticks: nothing more said
            self.assertEqual(meter.counts()["count"], 1)
        finally:
            meter.stop()

    def test_session_files_split_and_capped(self):
        folder = Path(self._tmp.name) / "split"
        folder.mkdir()
        old = folder / "2020-01-01_00-00-00.log"
        old.write_text("x" * 3 * 1024 * 1024, encoding="utf-8")
        keep = folder / "crash.log"
        keep.write_text("crash", encoding="utf-8")
        h = diag.SessionLog(folder, max_mb=0.001, keep_mb=1)
        self.assertFalse(old.exists())  # over the cap: the oldest goes
        self.assertTrue(keep.exists())  # never crash.log
        rec = logging.LogRecord("x", logging.INFO, "", 0, "y" * 300, None, None)
        first = h.path
        for _ in range(10):
            h.emit(rec)
        self.assertNotEqual(h.path, first)  # over log_mb: the next file
        self.assertEqual((folder / "latest.log").resolve(), h.path.resolve())
        h.hour = "1999010100"  # a new hour: a new file too
        before = h.path
        h.emit(rec)
        self.assertNotEqual(h.path, before)
        h.close()

    def test_memory_back_and_files_by_kind(self):
        freed = diag.trim_memory()
        self.assertTrue(freed is None or isinstance(freed, float))  # not glibc: None
        if os.path.isdir("/proc/self/fd"):
            with open(__file__, encoding="utf-8"):
                kinds = diag._fd_kinds()
            self.assertGreaterEqual(kinds.get("file", 0), 1)
            self.assertIn("fds_by_kind", diag.stats())

    def test_timed(self):
        with self.assertLogs("fedtail.diag", level="WARNING") as got:
            with diag.timed("slow thing", warn_s=0.01):
                time.sleep(0.05)
        self.assertIn("slow thing took", got.output[0])


if __name__ == "__main__":
    unittest.main()
