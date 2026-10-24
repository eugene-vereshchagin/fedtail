"""The diagnostics (fedtail/diag.py) beyond tests/test_diag.py: what happens when a file
can't be removed, linked or written, the Windows memory counters (with a stand-in
kernel32), the stats and trim loops, freezes inside the toolkit, the toolkits a report
names, and a system without the resource module."""

import ctypes
import faulthandler
import importlib
import logging
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

from fedtail import diag
from fedtail.core import config, paths


class Stop(Exception):
    pass


class DiagMoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        root = logging.getLogger()
        saved = (root.handlers[:], root.level, sys.excepthook, threading.excepthook,
                 dict(diag._state))

        def restore():
            for h in root.handlers:
                if h not in saved[0]:
                    h.close()
            root.handlers[:], root.level = saved[0], saved[1]
            sys.excepthook, threading.excepthook = saved[2], saved[3]
            faulthandler.disable()
            for f in ("crash", "stacks"):
                if diag._state.get(f) and diag._state[f] is not saved[4].get(f):
                    diag._state[f].close()
            diag._state.clear()
            diag._state.update(saved[4])
        self.addCleanup(restore)

    # ---- files that won't go ---------------------------------------------------------
    def test_remove_ours_survives_what_it_cant_delete(self):
        d = self.tmp / "logs"
        d.mkdir()
        (d / "latest.log").write_text("x")
        (d / "mine.txt").write_text("not ours")
        with mock.patch.object(Path, "unlink", side_effect=OSError):
            diag._remove_ours(d)
        self.assertTrue((d / "latest.log").exists())
        diag._remove_ours(d)
        self.assertFalse((d / "latest.log").exists())
        self.assertTrue((d / "mine.txt").exists())  # not ours: stays, and so the folder

    def test_forget_old_logs(self):
        folder = self.tmp / "logs"
        folder.mkdir()
        p = paths.resolve("t", config=str(self.tmp / "c.toml"), data=str(self.tmp / "d"))
        old_root = self.tmp / "fedtail-logs"
        (old_root / "t").mkdir(parents=True)
        (old_root / "t" / "latest.log").write_text("x")
        (old_root / "other").mkdir()  # another profile's: ~/fedtail-logs stays
        with mock.patch.object(diag, "OLD_LOG_DIR", str(old_root)), \
                mock.patch.object(Path, "write_text", side_effect=OSError):
            diag._forget_old_logs(p, folder)
        self.assertFalse((folder / "version").exists())  # couldn't write: fine
        self.assertFalse((old_root / "t").exists())
        self.assertTrue(old_root.exists())

    def test_latest_link_when_links_fail(self):
        d = self.tmp / "logs"
        d.mkdir()
        h = diag.SessionLog(d)
        self.addCleanup(h.close)
        with mock.patch.object(Path, "unlink", side_effect=OSError):
            h._link_latest()  # held open elsewhere: the old one stays
        with mock.patch.object(Path, "symlink_to", side_effect=OSError), \
                mock.patch.object(diag.os, "link", side_effect=OSError):
            (d / "latest.log").unlink()
            h._link_latest()
        self.assertFalse((d / "latest.log").exists())
        with mock.patch.object(Path, "symlink_to", side_effect=OSError):
            h._link_latest()  # a hard link instead
        self.assertTrue((d / "latest.log").exists())
        self.assertFalse((d / "latest.log").is_symlink())

    def test_prune_and_emit_failures(self):
        d = self.tmp / "logs"
        d.mkdir()
        h = diag.SessionLog(d, keep_mb=0.001)
        self.addCleanup(h.close)
        for i in range(3):
            (d / f"2020-01-0{i + 1}_00-00-00.log").write_text("x" * 2048)
        with mock.patch.object(Path, "unlink", side_effect=OSError):
            h._prune()
        self.assertEqual(len(list(d.glob("2020-*.log"))), 3)
        h.stream.close()  # writing now fails: handled, not raised
        with mock.patch.object(h, "handleError") as he:
            h.emit(logging.LogRecord("x", logging.INFO, "f", 1, "m", None, None))
        he.assert_called_once()

    def test_setup_off_the_main_thread_and_thread_crashes(self):
        cfg, _ = config.validate({"debug": {"mode": "on", "log_dir": str(self.tmp / "l")}})
        p = paths.resolve("t", config=str(self.tmp / "c.toml"), data=str(self.tmp / "d"))
        with mock.patch.object(faulthandler, "register", side_effect=RuntimeError):
            self.assertTrue(diag.setup(p, cfg))  # SIGUSR1 refused (a thread): no matter
        with self.assertLogs("fedtail.crash", "CRITICAL") as logs:
            try:
                raise ValueError("boom")
            except ValueError as e:
                diag._thread_excepthook(types.SimpleNamespace(
                    thread=None, exc_type=ValueError, exc_value=e,
                    exc_traceback=e.__traceback__))
        self.assertIn("thread ?", logs.output[0])

    # ---- memory -------------------------------------------------------------------------
    def test_windows_memory_with_a_stand_in_kernel32(self):
        def get(_handle, ref, _cb):
            ref._obj.WorkingSetSize = 4096 * 1024
            ref._obj.PeakWorkingSetSize = 8192 * 1024
            return 1
        k32 = types.SimpleNamespace(GetCurrentProcess=types.SimpleNamespace(),
                                    K32GetProcessMemoryInfo=get)
        k32.GetCurrentProcess = mock.Mock(return_value=0)
        with mock.patch.object(ctypes, "windll", types.SimpleNamespace(kernel32=k32),
                               create=True):
            self.assertEqual(diag._windows_memory(), {"VmRSS": 4096, "VmHWM": 8192})
            k32.K32GetProcessMemoryInfo = lambda *a: 0
            self.assertEqual(diag._windows_memory(), {})

    def test_proc_status_on_windows_and_without_proc(self):
        with mock.patch.object(diag, "os", types.SimpleNamespace(name="nt")):
            with mock.patch.object(diag, "_windows_memory", return_value={"VmRSS": 1}):
                self.assertEqual(diag._proc_status(), {"VmRSS": 1})
            with mock.patch.object(diag, "_windows_memory", side_effect=OSError):
                self.assertEqual(diag._proc_status(), {})
        with mock.patch.object(Path, "read_text", side_effect=OSError):
            self.assertEqual(diag._proc_status(), {})

    def test_trim_memory_without_glibc(self):
        with mock.patch.object(ctypes, "CDLL", side_effect=OSError):
            self.assertIsNone(diag.trim_memory())

    def test_stats_without_proc_fd(self):
        real_listdir = diag.os.listdir

        def listdir(p):
            if "fd" in str(p):
                raise OSError
            return real_listdir(p)
        with mock.patch.object(diag.os, "listdir", listdir):
            s = diag.stats()
        self.assertNotIn("fds", s)

    def test_log_stats_warns_once_per_doubling(self):
        diag._state["rss_warned"] = 0
        with mock.patch.object(diag, "stats", return_value={"rss_mb": 2000}), \
                self.assertLogs("fedtail.diag", "WARNING") as logs:
            diag.log_stats(1500)
            diag.log_stats(1500)  # not twice as big: quiet
        self.assertEqual(len([x for x in logs.output if "WARNING" in x]), 1)

    def test_session_summary_carries_the_freezes(self):
        diag._state["last_stats"] = {"freezes.count": 3, "core.polls": 9}
        diag._state["trend"] = None
        bits = diag.session_summary()
        self.assertEqual((bits["freezes.count"], bits["core.polls"]), (3, 9))

    # ---- the loops ------------------------------------------------------------------------
    def run_loop(self, cfg_debug, sleeps=2, trim=None, check=None):
        started = []

        class T:
            def __init__(self, target, name, daemon):
                started.append((name, target))

            def start(self):
                pass
        calls = {"n": 0}

        def sleep(_s):
            calls["n"] += 1
            if calls["n"] > sleeps:
                raise Stop
        diag._state["stats_thread"] = None
        diag._state["on"] = True
        with mock.patch.object(diag.threading, "Thread", T), \
                mock.patch.object(diag.time, "sleep", sleep), \
                mock.patch.object(diag, "trim_memory", trim or (lambda: 2.0)), \
                mock.patch.object(diag, "check_now", check or (lambda mb: None)), \
                mock.patch("fedtail.leaks.start_tracing") as tracing:
            diag.start_stats({"debug": cfg_debug})
            diag.start_stats({"debug": cfg_debug})  # once: a second call does nothing
            self.assertEqual(len(started), 1)
            with self.assertRaises(Stop):
                started[0][1]()
        diag._state["stats_thread"] = None
        return started[0][0], tracing

    def test_stats_loop(self):
        with self.assertLogs("fedtail.diag", "INFO") as logs:
            name, tracing = self.run_loop({"stats_minutes": 1, "tracemalloc": True})
        self.assertEqual(name, "fedtail-stats")
        tracing.assert_called_once()
        self.assertTrue(any("given back" in x for x in logs.output))
        with self.assertLogs("fedtail.diag", "ERROR"):
            self.run_loop({"stats_minutes": 1},
                          check=lambda mb: (_ for _ in ()).throw(RuntimeError))

    def test_trim_loop_when_stats_are_off(self):
        name, _t = self.run_loop({"stats_minutes": 0, "trim_memory": True},
                                 trim=lambda: (_ for _ in ()).throw(RuntimeError))
        self.assertEqual(name, "fedtail-trim")
        diag._state["stats_thread"] = None
        with mock.patch.object(diag.threading, "Thread") as T:
            diag.start_stats({"debug": {"stats_minutes": 0, "trim_memory": False}})
        T.assert_not_called()
        diag._state["stats_thread"] = None

    # ---- freezes -------------------------------------------------------------------------
    def test_watchers_that_are_off_dont_start(self):
        with mock.patch.object(diag.threading, "Thread") as T:
            diag.Watchdog(0).start()
            diag.StallMeter(0).start()
        T.assert_not_called()

    def test_a_freeze_inside_the_toolkit(self):
        m = diag.StallMeter(50)
        m.last -= 1.0
        m.samples = [([], ["fedtail/frontends/qt/__init__.py:10 run"])]
        with self.assertLogs("fedtail.diag", "WARNING") as logs:
            m.tick()
        self.assertIn("the toolkit itself", logs.output[0])

    # ---- what a report says ----------------------------------------------------------------
    def test_toolkits_named(self):
        qt = types.ModuleType("PySide6.QtCore")
        qt.qVersion = lambda: "6.9.0"
        gtk = types.SimpleNamespace(get_major_version=lambda: 4, get_minor_version=lambda: 18,
                                    get_micro_version=lambda: 1)
        adw = types.SimpleNamespace(get_major_version=lambda: 1, get_minor_version=lambda: 7)
        mods = {"PySide6": types.ModuleType("PySide6"), "PySide6.QtCore": qt,
                "gi.repository.Gtk": gtk, "gi.repository.Adw": adw}
        mods["textual"] = types.SimpleNamespace(__version__="8.2.8")
        with mock.patch.dict(sys.modules, mods):
            got = diag._toolkits()
        self.assertIn("textual 8.2.8", got)
        self.assertIn("Qt 6.9.0", got)
        self.assertIn("GTK 4.18.1", got)
        self.assertIn("libadwaita 1.7", got)
        with mock.patch.dict(sys.modules, {"gi.repository.Gtk": gtk,
                                           "gi.repository.Adw": None}):
            self.assertIn("libadwaita not used", diag._toolkits())
        broken = types.ModuleType("PySide6.QtCore")  # no qVersion: left out
        bad_gtk = types.SimpleNamespace()
        with mock.patch.dict(sys.modules, {"PySide6.QtCore": broken,
                                           "gi.repository.Gtk": bad_gtk}):
            got = diag._toolkits()
        self.assertFalse([x for x in got if x.startswith(("Qt", "GTK"))])

    def test_changed_options_and_the_config_unreadable(self):
        self.assertEqual(diag.changed_options({"ui": "not a section", "nope": {"x": 1}}), {})
        p = paths.resolve("t", config=str(self.tmp / "missing.toml"),
                          data=str(self.tmp / "d"))
        diag._state["on"] = True
        with mock.patch.object(diag, "is_on", return_value=True), \
                mock.patch.object(diag, "_system_summary", return_value="sys\n"), \
                self.assertLogs("fedtail.diag", "INFO") as logs:
            diag.debug_context(p, {}, "qt")
        self.assertFalse(any("config file" in x for x in logs.output))
        with mock.patch.object(diag, "is_on", return_value=False), \
                mock.patch.object(diag, "_system_summary") as summary:
            diag.debug_context(p, {}, "qt")  # not the debugging mode: nothing
        summary.assert_not_called()

    def test_summary_without_disk_figures(self):
        p = paths.resolve("t", config=str(self.tmp / "c.toml"), data=str(self.tmp / "d"))
        with mock.patch.object(diag.shutil, "disk_usage", side_effect=OSError):
            text = diag._system_summary(p)
        self.assertNotIn("disk free", text)
        self.assertNotIn("state.db", text)  # no database yet

    def test_trend_rates(self):
        from fedtail import leaks
        t = leaks.Trend(3)
        self.assertEqual(t.rate("rss_mb"), 0.0)
        t.history["x"] = []
        t.start["x"] = 1
        self.assertNotIn("x", t.summary())  # nothing measured yet
        self.assertIsInstance(leaks.tracing(), bool)

    def test_without_the_resource_module(self):
        """Windows has no `resource`: the stats go by what /proc (or nothing) says."""
        state = dict(diag._state)
        try:
            with mock.patch.dict(sys.modules, {"resource": None}):
                importlib.reload(diag)
                self.assertIsNone(diag.resource)
                self.assertIn("rss_mb", diag.stats())
        finally:
            importlib.reload(diag)
            diag._state.clear()
            diag._state.update(state)
        self.assertIsNotNone(diag.resource)


if __name__ == "__main__":
    unittest.main()
