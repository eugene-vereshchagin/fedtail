"""core/spell.py's other ways: pyenchant when it's there, libenchant's "no such
dictionary" and "no suggestions", no Enchant at all, and the dictionaries or my own
word list failing in every way they can — never more than a word unchecked."""

import ctypes
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fedtail.core import spell


class FakeEnchant:
    """pyenchant's face: a module with list_languages, dict_exists and Dict."""

    class Dict:
        def __init__(self, tag):
            self.tag = tag

        def check(self, word):
            return word == "hello"

        def suggest(self, word):
            return ("hello",)

    @staticmethod
    def list_languages():
        return ["en_US"]

    @staticmethod
    def dict_exists(tag):
        return tag == "en_US"


class Broken:
    """A backend whose every call fails."""

    def languages(self):
        raise RuntimeError("broken")

    def open(self, tag):
        raise RuntimeError("broken")

    def check(self, d, word):
        raise RuntimeError("broken")

    def suggest(self, d, word):
        raise RuntimeError("broken")


class Chokes(Broken):
    """Opens its dictionaries, then chokes on the words."""

    def languages(self):
        return ["en_US"]

    def open(self, tag):
        return tag


class BackendsTest(unittest.TestCase):
    def test_pyenchant(self):
        b = spell._PyEnchant(FakeEnchant)
        self.assertEqual(b.languages(), ["en_US"])
        d = b.open("en_US")
        self.assertIsNone(b.open("xx"))
        self.assertTrue(b.check(d, "hello"))
        self.assertEqual(b.suggest(d, "helo"), ["hello"])
        with mock.patch.dict(sys.modules, {"enchant": FakeEnchant}):
            self.assertIsInstance(spell._find(), spell._PyEnchant)

    def test_libenchant_says_no(self):
        lib = mock.Mock()
        lib.enchant_broker_dict_exists.return_value = 0
        lib.enchant_dict_suggest.return_value = None
        b = spell._LibEnchant(lib)
        self.assertIsNone(b.open("xx_XX"))
        self.assertEqual(b.suggest(object(), "word"), [])

    def test_no_enchant_at_all(self):
        with mock.patch.dict(sys.modules, {"enchant": None}), \
                mock.patch.object(ctypes.util, "find_library", return_value=None), \
                mock.patch.object(ctypes, "CDLL", side_effect=OSError("no lib")):
            self.assertIsNone(spell._find())


class FailuresTest(unittest.TestCase):
    def setUp(self):
        spell._checkers.clear()
        self.addCleanup(spell._checkers.clear)

    def use(self, backend):
        p = mock.patch.object(spell, "_backend", backend)
        p.start()
        self.addCleanup(p.stop)

    def test_a_backend_that_fails(self):
        self.use(Broken())
        self.assertEqual(spell.languages(), [])
        self.assertEqual(spell.pick(["", "en"], ["en_US"]), ["en_US"])
        self.use(Chokes())
        c = spell.Checker(["en"])
        self.assertTrue(c.working)
        self.assertTrue(c.ok("anything"))  # a word it chokes on: taken as fine
        self.assertEqual(c.suggest("anything"), [])

    def test_a_dictionary_that_wont_open(self):
        broken = Broken()
        broken.languages = lambda: ["en_US"]
        self.use(broken)
        self.assertFalse(spell.Checker(["en"]).working)

    def test_my_own_words_where_they_cant_be(self):
        self.use(Chokes())
        with tempfile.TemporaryDirectory() as d:
            c = spell.Checker(["en"], Path(d))  # a folder, not a file: read nothing
            self.assertEqual(c.own, set())
            blocker = Path(d) / "file"
            blocker.write_text("x")
            c = spell.Checker(["en"], blocker / "words.txt")
            c.add("fedtail")  # its folder is a file: kept for this run only
            self.assertIn("fedtail", c.own)
        c = spell.Checker(["en"])
        c.add("fedtail")
        c.add("fedtail")  # again: nothing more
        self.assertIn("fedtail", c.own)


if __name__ == "__main__":
    unittest.main()
