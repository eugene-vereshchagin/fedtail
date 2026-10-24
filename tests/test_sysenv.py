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
