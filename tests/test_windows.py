"""Windows, held to on any machine: where a profile's files go, the Start menu shortcut
fedtail asks PowerShell for, the single-instance pipe's key, the sounds through
winsound. What can only be tried on Windows itself (the pipe, the .lnk) is in
test_core.py and test_i18n_cli.py, and tools/windows_check.py runs docs/en/dev/windows.md."""

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fedtail.core import config, instance, paths


class WindowsPathsTest(unittest.TestCase):
    def test_appdata_and_localappdata(self):
        env = {"APPDATA": r"C:\Users\v\AppData\Roaming",
               "LOCALAPPDATA": r"C:\Users\v\AppData\Local"}
        with mock.patch.object(paths, "WINDOWS", True), \
                mock.patch.dict(os.environ, env, clear=False):
            for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME"):
                os.environ.pop(var, None)
            self.assertEqual(paths.config_base(), Path(env["APPDATA"]) / "fedtail")
            self.assertEqual(paths.data_base(), Path(env["LOCALAPPDATA"]) / "fedtail")
            # XDG_* set by hand win there too (the tests, a portable setup)
            with mock.patch.dict(os.environ, {"XDG_DATA_HOME": "/x"}):
                self.assertEqual(paths.data_base(), Path("/x") / "fedtail")

    def test_no_appdata_at_all(self):
        with mock.patch.object(paths, "WINDOWS", True), \
                mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(Path, "home", lambda: Path("/home/v")):
            self.assertEqual(paths.config_base(), Path("/home/v/AppData/Roaming/fedtail"))
            self.assertEqual(paths.data_base(), Path("/home/v/AppData/Local/fedtail"))


class StartMenuTest(unittest.TestCase):
    """--install-desktop on Windows: one PowerShell call making the .lnk."""

    def run_install(self, profile, frozen=False, exe="/py/python.exe"):
        from fedtail import desktop
        calls = []
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"APPDATA": d}), \
                mock.patch.object(desktop.subprocess, "run",
                                  lambda argv, **kw: calls.append(argv)), \
                mock.patch.object(desktop, "main_profile", lambda: "default"), \
                mock.patch.object(desktop.sys, "executable", exe), \
                mock.patch.object(desktop.sys, "frozen", frozen, create=True):
            link, _icon = desktop._windows_install(profile)
            menu = Path(d) / "Microsoft/Windows/Start Menu/Programs"
            self.assertTrue(menu.is_dir())
            self.assertEqual(link.parent, menu)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:4], ["powershell", "-NoProfile", "-NonInteractive",
                                        "-Command"])
        return link, calls[0][4]

    def test_from_the_source(self):
        link, script = self.run_install("default")
        self.assertEqual(link.name, "FedTail.lnk")
        self.assertIn("$s.Arguments = '-m fedtail'", script)
        self.assertIn("WScript.Shell", script)
        self.assertIn("$s.Save()", script)

    def test_another_profile_and_quotes(self):
        link, script = self.run_install("work", exe="/o'neil/python.exe")
        self.assertEqual(link.name, "FedTail-work.lnk")
        self.assertIn("'-m fedtail --profile work'", script)
        self.assertIn("o''neil", script)  # PowerShell's own quoting: no way out of it

    def test_the_one_file_build(self):
        _link, script = self.run_install("default", frozen=True, exe="/app/fedtail.exe")
        self.assertIn("$s.TargetPath = '/app/fedtail.exe'", script)
        self.assertIn("$s.Arguments = ''", script)


class PipeKeyTest(unittest.TestCase):
    """The single-instance pipe (Windows): its name from the profile's path, its key a
    secret in the profile's own folder."""

    def test_name_and_key(self):
        with tempfile.TemporaryDirectory() as d:
            sock = Path(d) / "instance.sock"
            a = instance._pipe_name(sock)
            self.assertTrue(a.startswith(r"\\.\pipe\fedtail-"))
            self.assertEqual(a, instance._pipe_name(str(sock).upper()))  # paths: no case
            self.assertIsNone(instance._pipe_key(sock))  # none yet, none made
            key = instance._pipe_key(sock, make=True)
            self.assertEqual(len(key), 32)
            self.assertEqual(instance._pipe_key(sock), key)  # the same one next time
            f = Path(d) / "instance.key"
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)
            f.write_bytes(b"short")  # a broken key is made anew, not trusted
            self.assertIsNone(instance._pipe_key(sock))
            self.assertEqual(len(instance._pipe_key(sock, make=True)), 32)


class WindowsSoundTest(unittest.TestCase):
    """Windows plays WAV itself (winsound): the desktop's sound theme isn't there, so
    the "desktop" source plays fedtail's own quiet set."""

    def test_desktop_source_through_winsound(self):
        from fedtail.frontends import soundpack
        from fedtail.frontends.common.sound import Player
        cfg, _w = config.validate({"sound": {"enabled": "on"}})
        snd = soundpack.scheme("system", cfg).find("reply")
        argv = Player(cfg, which=lambda _n: None, platform="win32").command(snd)
        self.assertEqual(len(argv), 1)
        self.assertTrue(argv[0].startswith("winsound:"))
        self.assertTrue(argv[0].endswith(".wav"))
        self.assertTrue(Path(argv[0][len("winsound:"):]).is_file())

    @unittest.skipUnless(sys.platform == "win32", "winsound: Windows")
    def test_winsound_plays(self):
        from fedtail.frontends import soundpack
        from fedtail.frontends.common.sound import Player
        cfg, _w = config.validate({"sound": {"enabled": "on"}})
        snd = soundpack.scheme("qip-retro", cfg).find("message")
        try:
            Player._subprocess(Player(cfg, platform="win32").command(snd))  # no error
        except RuntimeError as e:  # no output device now (a locked night, a remote
            # session): Windows' own answer, not ours — the app keeps quiet then too
            self.skipTest(f"Windows can't play here: {e}")


if __name__ == "__main__":
    unittest.main()
