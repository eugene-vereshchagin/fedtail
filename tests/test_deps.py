"""What fedtail needs from the system (fedtail/deps.py): `fedtail --check`, the check at
start that says what is missing with the command instead of a traceback, and the deb
package's Depends taken from the same table."""

import io
import unittest
from dataclasses import replace
from unittest import mock

from fedtail import deps, i18n


def table(gone=()):
    """NEEDS with these keys missing and everything else there."""
    return tuple(replace(n, check=(lambda: False) if n.key in gone else (lambda: True))
                 for n in deps.NEEDS)


class DepsTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_all_there(self):
        out = io.StringIO()
        with mock.patch.object(deps, "NEEDS", table()):
            self.assertEqual(deps.report(out), 0)
        self.assertIn("Everything is there.", out.getvalue())
        self.assertIn("Will run: qt, gtk, tui, web", out.getvalue())

    def test_a_must_have_missing_is_said_with_the_command(self):
        err = io.StringIO()
        with mock.patch.object(deps, "NEEDS", table({"requests"})), \
                mock.patch.object(deps, "debian_like", return_value=True), \
                mock.patch.dict("os.environ", {"FEDTAIL_NO_DEPCHECK": ""}):
            self.assertFalse(deps.at_start("qt", err))
            self.assertFalse(deps.at_start(None, quiet=True))
            out = io.StringIO()
            self.assertEqual(deps.report(out), 3)
        self.assertIn("requests", err.getvalue())
        self.assertIn("sudo apt install python3-requests", err.getvalue())
        self.assertIn("fedtail --check", err.getvalue())

    def test_the_interface_and_pip_elsewhere(self):
        err = io.StringIO()
        with mock.patch.object(deps, "NEEDS", table({"textual"})), \
                mock.patch.object(deps, "debian_like", return_value=False), \
                mock.patch.dict("os.environ", {"FEDTAIL_NO_DEPCHECK": ""}):
            self.assertTrue(deps.at_start("qt", err))  # not the terminal: fine
            self.assertFalse(deps.at_start("tui", err))
        self.assertIn('pip install --user "textual>=0.86"', err.getvalue())  # cmd takes "…"

    def test_the_nice_to_haves_said_once(self):
        err = io.StringIO()
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(deps, "NEEDS", table({"PySide6 QtMultimedia"})), \
                mock.patch.object(deps, "debian_like", return_value=True), \
                mock.patch.dict("os.environ", {"FEDTAIL_NO_DEPCHECK": "",
                                               "XDG_CACHE_HOME": tmp}):
            self.assertTrue(deps.at_start("qt", err))
            self.assertIn("python3-pyside6.qtmultimedia", err.getvalue())
            again = io.StringIO()
            self.assertTrue(deps.at_start("qt", again))
            self.assertEqual(again.getvalue(), "")  # the same set: not again

    def test_the_packages_take_the_same_list(self):
        """Each piece in one package, once: the program's own in fedtail-common, each
        toolkit's in its interface's package — none pulls another's toolkit."""
        got = {pkg: deps.deb_fields(pkg) for pkg in deps.DEB_PACKAGES}
        depends, recommends, suggests = got["common"]
        self.assertIn("python3-requests", depends)
        self.assertIn("python3-cryptography", recommends)
        self.assertIn("libnotify-bin", suggests)
        self.assertIn("python3-pyside6.qtwidgets", got["qt"][0])
        self.assertIn("python3-pyside6.qtmultimedia", got["qt"][1])
        self.assertIn("gir1.2-gtk-4.0", got["gtk"][0])
        self.assertIn("python3-textual", got["tui"][0])
        every = [p for fields in got.values() for f in fields for p in f.split(", ") if p]
        self.assertEqual(len(every), len(set(every)))  # none twice
        pkgs = {p for n in deps.NEEDS for p in n.deb.split()} - {"python3", "libsqlite3-0"}
        self.assertEqual(pkgs, set(every) - {"python3 (>= 3.11)"})  # none left out
        for toolkit in ("PySide6", "pyside6", "gtk", "textual"):
            self.assertNotIn(toolkit, ", ".join(got["common"]))

    def test_auto_takes_the_window_installed(self):
        with mock.patch.object(deps, "can_run", lambda g: g == "gtk"):
            self.assertEqual(deps.auto_frontend(), "gtk")
        with mock.patch.object(deps, "can_run", lambda g: g in ("qt", "gtk")):
            self.assertEqual(deps.auto_frontend(), "qt")
        with mock.patch.object(deps, "can_run", lambda g: g == "tui"):
            self.assertEqual(deps.auto_frontend(terminal=True), "tui")
            self.assertEqual(deps.auto_frontend(terminal=False), "web")

    def test_every_word_is_there(self):
        for n in deps.NEEDS:
            self.assertNotEqual(i18n._(n.what), n.what, n.key)
        for g in deps.GROUPS:
            self.assertNotEqual(i18n._(deps.GROUP_WORDS[g]), deps.GROUP_WORDS[g])



class ReadmeTest(unittest.TestCase):
    def test_everything_at_once_names_every_package(self):
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        pkgs = {p for n in deps.NEEDS for p in n.deb.split()} - {"python3", "libsqlite3-0"}
        for name in ("README.md", "README.ru.md"):
            text = (root / name).read_text("utf-8")
            self.assertIn("python3 -m fedtail --check", text)
            missing = sorted(p for p in pkgs if p not in text)
            self.assertEqual(missing, [], f"{name}: the apt line lacks these")


class ServerAddressTest(unittest.TestCase):
    """The login's "Server address": the usual slips forgiven, nonsense told in words."""

    def test_slips(self):
        from fedtail.protocols.mastodon.api import server_address as addr
        self.assertEqual(addr("dmesg,online"), "https://dmesg.online")  # the other layout
        self.assertEqual(addr("  social.example. "), "https://social.example")
        self.assertEqual(addr("@me@mastodon.social"), "https://mastodon.social")
        self.assertEqual(addr("https://social.example/@me/123"), "https://social.example")
        self.assertEqual(addr("http://192.168.1.5:8080"), "http://192.168.1.5:8080")
        for bad in ("dmesg", "x_y.example", "", "http://"):
            with self.assertRaises(ValueError):
                addr(bad)

    def test_said_in_words(self):
        import requests

        from fedtail.core.app import Core

        from .test_custom import FreeBase
        i18n.setup("en")
        base = FreeBase()
        base.setUp()
        self.addCleanup(base.doCleanups)
        core, _w = base.make([])
        with self.assertRaises(ValueError) as e:
            core.begin_login("dmesg").result()
        self.assertIn("doesn't look like a server's address", str(e.exception))
        with mock.patch.object(core, "api_class") as api:
            api.return_value.register_app.side_effect = requests.ConnectionError("boom")
            with self.assertRaises(ValueError) as e:
                core.begin_login("dmesg,online").result()
            api.assert_called_with("https://dmesg.online")
        self.assertIn("Couldn't reach dmesg.online", str(e.exception))
        self.assertTrue(Core)


class AddonsPinnedTest(unittest.TestCase):
    def test_video_asked_for_at_the_installed_version(self):
        """Video in the window needs PySide6-Addons of the very version of the Essentials
        there (28.10: Windows opened every video in the browser)."""
        from unittest import mock
        need = [n for n in deps.NEEDS if n.key == "PySide6 QtMultimedia"]
        with mock.patch.object(deps, "debian_like", lambda: False), \
                mock.patch("importlib.metadata.version", lambda name: "6.8.1"):
            self.assertTrue(deps.install_line(need).endswith('"PySide6-Addons==6.8.1"'))


if __name__ == "__main__":
    unittest.main()
