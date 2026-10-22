"""desktop.py: the app id, the menu entry made and mended at start, old names gone."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fedtail import desktop

OLD = ("[Desktop Entry]\nName=fedtail\nExec=fedtail\n"
       "Keywords=mastodon;gotosocial;fediverse;point;juick;bnw;\n")


class AppIdTest(unittest.TestCase):
    def test_valid_ids(self):
        try:  # GLib's own check, where PyGObject is
            from fedtail.frontends.gtk.gi_setup import Gio
        except ImportError:
            self.skipTest("no PyGObject")
        for prof in ("work", "my profile", "2nd", "-x", "кот", "a.b"):
            with self.subTest(prof=prof):
                self.assertTrue(Gio.Application.id_is_valid(desktop.desktop_id(prof)))

    def test_ids_by_hand(self):
        with mock.patch.object(desktop, "main_profile", return_value="main"):
            self.assertEqual(desktop.desktop_id("main"), "online.dmesg.fedtail")
            self.assertEqual(desktop.desktop_id("my profile"), "online.dmesg.fedtail.my_profile")
            self.assertEqual(desktop.desktop_id("2nd"), "online.dmesg.fedtail.p2nd")


class GtkActionTest(unittest.TestCase):
    def test_gtk_is_an_action_of_the_entry(self):
        text = desktop.entry_text("main", icon="fedtail")
        head, action = text.split("\n[Desktop Action gtk]\n")
        self.assertIn("Actions=gtk;", head)
        self.assertIn("--ui gtk", action)
        self.assertNotIn("Path=", action)  # not a key of an action

    def test_the_link_handler_has_no_action(self):
        text = desktop.handler_text(desktop.entry_text("main", icon="fedtail"))
        self.assertNotIn("Desktop Action", text)
        self.assertNotIn("Actions=", text)
        self.assertEqual(text.count("Exec="), 1)
        self.assertIn(" open %u", text)


@unittest.skipIf(os.name == "nt", "a .desktop entry: Linux and the like")
class EnsureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.data = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(self.data),
                                                "XDG_DATA_DIRS": str(self.data / "sys")})
        self.env.start()
        # no desktop tools here: nothing outside the temp folder is touched
        self.which = mock.patch.object(desktop.shutil, "which", return_value=None)
        self.which.start()
        self.main = mock.patch.object(desktop, "main_profile", return_value="main")
        self.main.start()
        self.apps = self.data / "applications"

    def tearDown(self):
        for p in (self.main, self.which, self.env):
            p.stop()
        self.tmp.cleanup()

    def test_made_then_left_alone(self):
        self.assertTrue(desktop.ensure("main"))
        entry = self.apps / "online.dmesg.fedtail.desktop"
        self.assertIn("Icon=" + str(self.data / "icons/hicolor/512x512/apps/fedtail.png"),
                      entry.read_text())
        self.assertTrue((self.apps / "online.dmesg.fedtail-open.desktop").is_file())
        before = entry.stat().st_mtime_ns
        self.assertIsNone(desktop.ensure("main"))  # all in place: nothing written
        self.assertEqual(entry.stat().st_mtime_ns, before)

    def test_mended_when_it_points_elsewhere(self):
        desktop.ensure("main")
        entry = self.apps / "online.dmesg.fedtail.desktop"
        entry.write_text(entry.read_text().replace("Exec=", "Exec=/moved/away "))
        self.assertTrue(desktop.ensure("main"))
        self.assertNotIn("/moved/away", entry.read_text())

    def test_old_names_go_but_not_hand_written(self):
        self.apps.mkdir(parents=True)
        (self.apps / "fedtail.desktop").write_text(OLD)
        (self.apps / "fedtail-work.desktop").write_text("[Desktop Entry]\nName=mine\n")
        desktop.ensure("main")
        self.assertFalse((self.apps / "fedtail.desktop").exists())
        desktop.ensure("work")
        self.assertTrue((self.apps / "fedtail-work.desktop").exists())  # not ours
        self.assertTrue((self.apps / "online.dmesg.fedtail.work.desktop").exists())

    def test_package_entry_wins(self):
        sys_apps = self.data / "sys" / "applications"
        sys_apps.mkdir(parents=True)
        (sys_apps / "online.dmesg.fedtail.desktop").write_text(OLD)
        self.apps.mkdir(parents=True)
        (self.apps / "online.dmesg.fedtail.desktop").write_text(OLD)
        (self.apps / "fedtail.desktop").write_text(OLD)
        with mock.patch.object(desktop, "source_dir", return_value=None):
            desktop.ensure("main")
        self.assertFalse((self.apps / "online.dmesg.fedtail.desktop").exists())
        self.assertFalse((self.apps / "fedtail.desktop").exists())

    def test_never_raises(self):
        with mock.patch.object(desktop, "_files", side_effect=OSError("disk full")):
            self.assertIsNone(desktop.ensure("main"))


if __name__ == "__main__":
    unittest.main()
