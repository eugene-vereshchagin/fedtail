"""Programs started from the one-file build get the environment from before it unpacked
itself (fedtail/sysenv.py); from the source, nothing changes."""

import os
import unittest
from unittest import mock

from fedtail import sysenv


class SysenvTest(unittest.TestCase):
    def test_from_the_source_nothing_changes(self):
        with mock.patch.object(sysenv, "FROZEN", False):
            self.assertIsNone(sysenv.child_env())
            self.assertFalse(sysenv.open_external("https://x.test"))

    def test_frozen_gives_back_the_old_environment(self):
        env = {"LD_LIBRARY_PATH": "/tmp/_MEI/lib", "LD_LIBRARY_PATH_ORIG": "/usr/lib",
               "DYLD_LIBRARY_PATH": "/tmp/_MEI", "QT_PLUGIN_PATH": "/tmp/_MEI/qt",
               "PYTHONHOME": "/tmp/_MEI", "HOME": "/home/me"}
        with mock.patch.object(sysenv, "FROZEN", True), mock.patch.dict(os.environ, env,
                                                                        clear=True):
            got = sysenv.child_env()
        self.assertEqual(got, {"LD_LIBRARY_PATH": "/usr/lib", "HOME": "/home/me"})

    def test_frozen_opens_with_the_desktops_opener(self):
        with mock.patch.object(sysenv, "FROZEN", True), \
                mock.patch.object(sysenv.sys, "platform", "linux"), \
                mock.patch.object(sysenv.subprocess, "Popen") as popen:
            for have, argv in (("xdg-open", ["/bin/xdg-open", "U"]),
                               ("gio", ["/bin/gio", "open", "U"])):
                with mock.patch.object(sysenv.shutil, "which",
                                       lambda n, have=have: f"/bin/{n}" if n == have
                                       else None):
                    self.assertTrue(sysenv.open_external("U"))
                self.assertEqual(popen.call_args[0][0], argv)
                self.assertTrue(popen.call_args[1]["start_new_session"])
            with mock.patch.object(sysenv.shutil, "which", return_value=None):
                self.assertFalse(sysenv.open_external("U"))  # no opener: Qt tries
        with mock.patch.object(sysenv, "FROZEN", True), \
                mock.patch.object(sysenv.sys, "platform", "win32"):
            self.assertFalse(sysenv.open_external("U"))


if __name__ == "__main__":
    unittest.main()


class OpenLinkTest(unittest.TestCase):
    """Qt that couldn't open a link: the desktop's opener is tried, and a failure is
    said, not taken for done (the bug report's "Open GitHub" opened nothing, 29.10)."""

    def test_falls_back_and_says(self):
        try:
            from fedtail.frontends.qt import opener
        except ImportError:
            self.skipTest("PySide6 not installed")
        asked = []

        def ext(url, always=False):
            asked.append(always)
            return always and url.endswith("ok")
        with mock.patch.object(opener.sysenv, "open_external", ext), \
                mock.patch.object(opener.QDesktopServices, "openUrl", lambda _u: False):
            self.assertTrue(opener.open_link("https://example.test/ok"))
            self.assertFalse(opener.open_link("https://example.test/no"))
        self.assertEqual(asked, [False, True, False, True])


class DesktopFontTest(unittest.TestCase):
    """A GTK desktop's font for Qt without the desktop's integration (the AppImage on
    Cinnamon came up in Noto Color Emoji's metrics, 28.11)."""

    def test_gtk_font_names(self):
        p = sysenv.parse_font_name
        self.assertEqual(p("'Ubuntu 11'\n"), ("Ubuntu", 11.0))
        self.assertEqual(p("'Noto Sans Bold Italic 10.5'"), ("Noto Sans", 10.5))
        self.assertEqual(p("'DejaVu Sans Book 9'"), ("DejaVu Sans", 9.0))
        for bad in ("", "''", "'Ubuntu'", "'Ubuntu big'", "'Sans 0'"):
            self.assertIsNone(p(bad), bad)

    def test_the_desktops_schema(self):
        asked = []

        def run(argv, **kw):
            asked.append(argv[2])
            return mock.Mock(returncode=0, stdout="'Cantarell 11'\n")

        with mock.patch.object(sysenv.sys, "platform", "linux"), \
                mock.patch.object(sysenv.shutil, "which", return_value="/bin/gsettings"):
            for desktop, schema in (("X-Cinnamon", "org.cinnamon.desktop.interface"),
                                    ("MATE", "org.mate.interface"),
                                    ("ubuntu:GNOME", "org.gnome.desktop.interface"),
                                    ("XFCE", "org.gnome.desktop.interface")):
                with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": desktop}):
                    self.assertEqual(sysenv.desktop_font(run), ("Cantarell", 11.0))
                self.assertEqual(asked[-1], schema)
            self.assertIsNone(sysenv.desktop_font(
                lambda *a, **k: mock.Mock(returncode=1, stdout="")))  # no such schema
            self.assertIsNone(sysenv.desktop_font(mock.Mock(side_effect=OSError)))
        with mock.patch.object(sysenv.sys, "platform", "linux"), \
                mock.patch.object(sysenv.shutil, "which", return_value=None):
            self.assertIsNone(sysenv.desktop_font(run))  # no gsettings

