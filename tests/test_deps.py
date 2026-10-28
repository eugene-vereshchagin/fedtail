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
        self.assertIn("pip install --user 'textual>=0.86'", err.getvalue())

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

    def test_the_package_takes_the_same_list(self):
        depends, recommends, suggests = deps.deb_fields()
        self.assertIn("python3-requests", depends)
        self.assertIn("python3-pyside6.qtwidgets", depends)
        self.assertIn("python3-cryptography", recommends)
        self.assertIn("python3-textual", suggests)
        both = (depends + ", " + recommends + ", " + suggests).split(", ")
        self.assertEqual(len(both), len(set(both)))  # none twice

    def test_every_word_is_there(self):
        for n in deps.NEEDS:
            self.assertNotEqual(i18n._(n.what), n.what, n.key)
        for g in deps.GROUPS:
            self.assertNotEqual(i18n._(deps.GROUP_WORDS[g]), deps.GROUP_WORDS[g])


if __name__ == "__main__":
    unittest.main()
