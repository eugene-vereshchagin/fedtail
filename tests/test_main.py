"""The entry point (fedtail/__main__.py): every flag and the way a start goes — the config
made, reported or updated, the frontend loaded and run, an instance already running
poked instead, the terminal commands, the merged window — in folders of a test's own
(XDG_*), with the window replaced by a stand-in."""

import contextlib
import faulthandler
import io
import logging
import os
import runpy
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

import fedtail.__main__ as entry
from fedtail.core import auth, config, paths


class Frontend:
    """What frontends.load gives: run() notes what it was given."""

    def __init__(self, code=0):
        self.code = code
        self.ran = []

    def run(self, core, instance, argv):
        self.ran.append((core, instance, argv))
        core.shutdown()  # as a window does on its way out
        return self.code


class MainTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        env = {"XDG_CONFIG_HOME": str(self.tmp / "cfg"), "XDG_DATA_HOME": str(self.tmp / "data"),
               "XDG_STATE_HOME": str(self.tmp / "state"), "HOME": str(self.tmp / "home")}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        root = logging.getLogger()
        saved = (root.handlers[:], root.level, sys.excepthook, threading.excepthook)

        def restore():
            for h in root.handlers:
                if h not in saved[0]:
                    h.close()
            root.handlers[:], root.level = saved[0], saved[1]
            sys.excepthook, threading.excepthook = saved[2], saved[3]
            faulthandler.disable()
            from fedtail import diag
            crash = diag._state.get("crash")
            if crash is not None and not crash.closed:
                crash.close()
            from fedtail import i18n
            i18n.setup("en")
        self.addCleanup(restore)
        leave = mock.patch.object(entry, "_leave", side_effect=lambda code: code)
        leave.start()
        self.addCleanup(leave.stop)
        stats = mock.patch("fedtail.diag.start_stats")
        stats.start()
        self.addCleanup(stats.stop)

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = entry.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def where(self, profile="default"):
        return paths.resolve(profile)

    def login(self, profile="default"):
        w = self.where(profile)
        w.ensure()
        auth.save(w.auth_file, {"server": "https://example.test", "token": "tok"})
        return w

    # ---- flags that answer and leave -------------------------------------------------
    def test_version(self):
        with self.assertRaises(SystemExit) as e, contextlib.redirect_stdout(io.StringIO()):
            entry.parse_args(["-V"])
        self.assertEqual(e.exception.code, 0)

    def test_started_as_a_folder(self):
        """`python3 fedtail -V` (the folder, not -m): it finds its package and goes on."""
        argv = sys.argv
        sys.argv = ["fedtail", "-V"]
        try:
            with self.assertRaises(SystemExit) as e, contextlib.redirect_stdout(io.StringIO()):
                runpy.run_path(str(Path(entry.__file__)), run_name="__main__")
        finally:
            sys.argv = argv
        self.assertEqual(e.exception.code, 0)

    def test_started_as_a_module(self):
        """`python3 -m fedtail -V`."""
        argv = sys.argv
        sys.argv = ["fedtail", "-V"]
        try:
            with self.assertRaises(SystemExit) as e, contextlib.redirect_stdout(io.StringIO()):
                runpy.run_module("fedtail", run_name="__main__")
        finally:
            sys.argv = argv
        self.assertEqual(e.exception.code, 0)

    def test_profiles(self):
        self.login("default")
        self.where("other").ensure()
        self.where("other").config_file.write_text("[ui]\n", "utf-8")
        code, out, _err = self.run_main("--profiles")
        self.assertEqual(code, 0)
        self.assertIn("* default", out)
        self.assertIn("other", out)
        self.assertIn("(not logged in)", out)

    def test_install_desktop(self):
        with mock.patch("fedtail.desktop.install", return_value=("E", "I")) as inst:
            code, out, _err = self.run_main("--install-desktop", "-p", "work")
        self.assertEqual(code, 0)
        inst.assert_called_once_with("work")
        self.assertIn("menu entry E", out)

    def test_bad_profile_and_bad_config(self):
        code, _out, err = self.run_main("-p", "../escape")
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("fedtail: "))
        w = self.where()
        w.ensure()
        w.config_file.write_text("[ui\n", "utf-8")
        code, _out, err = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("config error", err)

    # ---- the config file ----------------------------------------------------------------
    def test_first_start_writes_the_config_and_the_references(self):
        fe = Frontend()
        with mock.patch("fedtail.frontends.load", return_value=fe):
            code, _out, err = self.run_main("--ui", "tui")
        self.assertEqual(code, 0)
        w = self.where()
        self.assertTrue(w.config_file.exists())
        for lang in config.EXAMPLE_LANGS:
            self.assertEqual(w.config_file.with_name(config.example_name(lang)).read_text(
                "utf-8"), config.example_text(lang))
        self.assertNotIn("doesn't mention", err)
        self.assertEqual(len(fe.ran), 1)

    def test_warnings_new_options_update_and_rebuild(self):
        w = self.where()
        w.ensure()
        w.config_file.write_text("# мой конфиг\n[ui]\ntheme = \"paper\"\nbutton_icons = \"on\"\n"
                                 "[nonsense]\nx = 1\n", "utf-8")
        w.config_file.with_name("config.example.toml").write_text("old", "utf-8")
        fe = Frontend()
        with mock.patch("fedtail.frontends.load", return_value=fe):
            code, _out, err = self.run_main("--ui", "tui")
        self.assertEqual(code, 0)
        self.assertIn("unknown section [nonsense]", err)
        self.assertIn("doesn't mention", err)
        self.assertFalse(w.config_file.with_name("config.example.toml").exists())
        self.assertTrue(fe.ran[0][0].new_options)

        code, out, _err = self.run_main("--update-config")
        self.assertEqual(code, 0)
        self.assertIn("updated", out)
        self.assertIn("added:", out)
        self.assertIn("renamed:", out)
        self.assertTrue(w.config_file.with_name("config.toml.bak").exists())
        code, out, _err = self.run_main("--update-config")
        self.assertIn("is up to date", out)

        code, out, _err = self.run_main("--rebuild-config")
        self.assertEqual(code, 0)
        self.assertIn("rebuilt", out)
        self.assertIn("ui.theme", out)
        self.assertIn("kept, though this version doesn't know them", out)
        self.assertIn('theme = "paper"', w.config_file.read_text("utf-8"))

    def test_references_that_cant_be_written_dont_stop_the_start(self):
        w = self.where()
        w.ensure()
        w.config_file.write_text(config.example_text("en"), "utf-8")
        real_write = Path.write_text

        def refuse(path, *a, **k):
            if "example" in path.name:
                raise OSError("read-only")
            return real_write(path, *a, **k)
        with mock.patch.object(Path, "write_text", refuse), \
                mock.patch.object(Path, "unlink", side_effect=OSError("no")), \
                mock.patch("fedtail.frontends.load", return_value=Frontend()):
            code, _out, _err = self.run_main("--ui", "tui")
        self.assertEqual(code, 0)

    def test_bug_report_sent_to_the_repository(self):
        w = self.where()
        w.ensure()
        w.config_file.write_text('[debug]\nreport_repo = "me/reports"\n', "utf-8")
        from fedtail import reportsend
        with mock.patch("fedtail.diag.bug_report", return_value=Path("/x/r.tar.gz")), \
                mock.patch.object(reportsend, "send_report", return_value="me/reports: r/x"):
            code, out, _err = self.run_main("--bug-report")
        self.assertEqual(code, 0)
        self.assertIn("sent to me/reports: r/x", out)
        with mock.patch("fedtail.diag.bug_report", return_value=Path("/x/r.tar.gz")), \
                mock.patch.object(reportsend, "send_report",
                                  side_effect=reportsend.SendError("Permission denied")):
            code, _out, err = self.run_main("--bug-report")
        self.assertEqual(code, 1)
        self.assertIn("not sent to me/reports: Permission denied", err)

    def test_bug_report(self):
        with mock.patch("fedtail.diag.bug_report", return_value=Path("/x/report.tar.gz")) \
                as rep:
            code, out, _err = self.run_main("--bug-report")
        self.assertEqual(code, 0)
        self.assertIn("/x/report.tar.gz", out)
        rep.assert_called_once()

    # ---- this run only -------------------------------------------------------------------
    def test_for_this_run(self):
        from fedtail.core import profiles
        cfg, _ = config.validate({})
        args = types.SimpleNamespace(ui="tui", layout="split", theme="paper")
        self.assertIsNone(entry.for_this_run(args, cfg))
        self.assertEqual((cfg["ui"]["layout"], cfg["ui"]["theme"]), ("split", "paper"))
        self.assertEqual(profiles.RUN_FLAGS, ["--ui", "tui", "--layout", "split",
                                              "--theme", "paper"])
        bad = entry.for_this_run(types.SimpleNamespace(theme="nope"), cfg)
        self.assertIn("no theme 'nope'", bad)
        entry.for_this_run(types.SimpleNamespace(), cfg)
        self.assertEqual(profiles.RUN_FLAGS, [])
        code, _out, err = self.run_main("--theme", "nope")
        self.assertEqual(code, 2)
        self.assertIn("no theme", err)

    # ---- the window ---------------------------------------------------------------------
    def test_already_running(self):
        with mock.patch.object(entry.SingleInstance, "poke_existing", return_value=True):
            code, _out, err = self.run_main()
            self.assertEqual(code, 0)
            self.assertIn("already running", err)
            code, _out, err = self.run_main("open", "https://x.test/@a/1")
            self.assertIn("opened in the running", err)

    def test_open_url(self):
        code, _out, err = self.run_main("open")
        self.assertEqual(code, 2)
        self.assertIn("open what?", err)
        fe = Frontend(3)
        with mock.patch("fedtail.frontends.load", return_value=fe):
            code, _out, _err = self.run_main("--ui", "tui", "open", "https://x.test/@a/1")
        self.assertEqual(code, 3)
        self.assertEqual(fe.ran[0][0].open_at_start, "https://x.test/@a/1")

    def test_a_window_toolkit_adds_the_menu_entry(self):
        w = self.where()
        w.ensure()
        w.config_file.write_text("[ui]\ndesktop_entry = true\n", "utf-8")
        with mock.patch("fedtail.frontends.load", return_value=Frontend()), \
                mock.patch("fedtail.desktop.ensure", return_value="made") as ens, \
                mock.patch.object(entry.sys, "frozen", True, create=True):
            code, _out, err = self.run_main("--ui", "qt", "--debug")
        self.assertEqual(code, 0)
        ens.assert_called_once()
        self.assertNotIn("logs in", err)  # a built one doesn't say where the logs are
        with mock.patch("fedtail.frontends.load", return_value=Frontend()), \
                mock.patch("fedtail.desktop.ensure", return_value=None):
            self.run_main("--ui", "gtk")

    # ---- the terminal ---------------------------------------------------------------------
    @staticmethod
    def cli(result):
        """cli.run that closes the core (the process would end there) and then returns
        or raises `result`."""
        def run(core, argv):
            core.shutdown()
            if isinstance(result, BaseException):
                raise result
            return result
        return mock.patch("fedtail.frontends.cli.run", side_effect=run)

    def test_terminal_commands(self):
        self.login()
        with self.cli(0) as run:
            code, _out, _err = self.run_main("lanes")
        self.assertEqual(code, 0)
        self.assertEqual(run.call_args[0][1], ["lanes"])
        for raised, want in ((SystemExit("bad lane"), 1), (SystemExit(4), 4),
                             (SystemExit(None), 0), (KeyboardInterrupt(), 130)):
            with self.cli(raised):
                code, _out, err = self.run_main("show", "home")
            self.assertEqual(code, want, raised)
            if want == 1:
                self.assertIn("fedtail: bad lane", err)
        w = self.where()
        w.config_file.write_text("[cli]\nenabled = false\n", "utf-8")
        code, _out, err = self.run_main("lanes")
        self.assertEqual(code, 2)
        self.assertIn("terminal commands are off", err)

    # ---- all accounts in one window -------------------------------------------------------
    def test_merge_accounts(self):
        from fedtail.core.app import Core
        from fedtail.core.merged import MergedCore
        for name in ("default", "work", "play"):
            self.login(name)
        self.where("broken").ensure()
        self.where("broken").config_file.write_text("[ui\n", "utf-8")
        cfg, _ = config.validate({})
        core = Core(cfg, self.where("default"))
        self.addCleanup(core.shutdown)
        self.assertEqual(entry.merge_accounts(core, "default"), (core, []))  # off

        cfg["ui"]["merge"] = ["work", "broken", "default"]
        with mock.patch.object(entry.SingleInstance, "poke_existing",
                               lambda self, *a: "work" in str(self.__dict__)):
            got, held = entry.merge_accounts(core, "default")
        self.assertIs(got, core)  # work runs on its own, broken can't be read: no one
        for h in held:
            h.close()

        cfg["ui"]["merge"] = ["all"]
        got, held = entry.merge_accounts(core, "default")
        try:
            self.assertIsInstance(got, MergedCore)
            self.assertEqual(sorted(got.others), ["play", "work"])
        finally:
            for h in held:
                h.close()
            for other in got.others.values():
                other.shutdown()

    def test_window_run_holds_and_lets_go_of_the_others(self):
        for name in ("default", "work"):
            self.login(name)
        w = self.where()
        w.config_file.write_text('[ui]\nmerge = ["all"]\n', "utf-8")
        fe = Frontend()
        with mock.patch("fedtail.frontends.load", return_value=fe):
            code, _out, _err = self.run_main("--ui", "tui")
        self.assertEqual(code, 0)
        from fedtail.core.merged import MergedCore
        core = fe.ran[0][0]
        self.assertIsInstance(core, MergedCore)


class LeaveTest(unittest.TestCase):
    def test_leave_exits_with_the_code_without_waiting(self):
        stop = threading.Event()
        t = threading.Thread(target=stop.wait, name="slow-download")
        t.start()
        self.addCleanup(lambda: (stop.set(), t.join()))
        flush = mock.Mock()  # the self-check's coverage hook, when it runs
        with mock.patch.object(entry.os, "_exit", side_effect=SystemExit) as ex, \
                mock.patch("logging.shutdown"), \
                mock.patch.object(entry.sys, "fedtail_coverage_flush", flush, create=True), \
                self.assertLogs("fedtail", "INFO") as logs:
            with self.assertRaises(SystemExit):
                entry._leave(5)
        ex.assert_called_once_with(5)
        flush.assert_called_once()
        self.assertTrue(any("slow-download" in x for x in logs.output))
        with mock.patch.object(entry.os, "_exit", side_effect=SystemExit) as ex, \
                mock.patch("logging.shutdown"), \
                mock.patch("fedtail.diag.session_summary", side_effect=RuntimeError):
            with self.assertRaises(SystemExit):
                entry._leave(None)
        ex.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
