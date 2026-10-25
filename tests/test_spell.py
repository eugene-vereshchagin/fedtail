"""core/spell.py: which words are checked, what looks wrong, my own dictionary, the
languages picked — with a made-up dictionary (runs everywhere) and the system's (where
Enchant is)."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fedtail.core import spell


class FakeBackend:
    """Two tiny dictionaries: what they know, and a suggestion for a known slip."""
    KNOWN = {"en_US": {"hello", "world", "this", "is", "a", "test", "don't", "of", "and"},
             "ru_RU": {"привет", "мир", "кто-то", "и"}}

    def languages(self):
        return sorted(self.KNOWN)

    def open(self, tag):
        return tag if tag in self.KNOWN else None

    def check(self, d, word):
        return word.lower() in self.KNOWN[d]

    def suggest(self, d, word):
        return {"wrold": ["world"], "привт": ["привет"]}.get(word.lower(), [])


class SpellTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(spell, "_backend", FakeBackend())
        p.start()
        self.addCleanup(p.stop)
        spell._checkers.clear()
        self.addCleanup(spell._checkers.clear)

    def test_what_is_a_word_to_check(self):
        text = ("Hello https://x.org/wrold @bob@x.org #wrold :wrold: `wrold` 4k mp3 "
                "me@mail.example кто-то don't")
        self.assertEqual([w for _s, _e, w in spell.words(text)],
                         ["Hello", "кто-то", "don't"])
        s, e, w = spell.words("ab привет")[1]
        self.assertEqual("ab привет"[s:e], w)

    def test_any_language_will_do(self):
        c = spell.Checker(["ru", "en"])
        self.assertEqual(c.tags, ["ru_RU", "en_US"])
        self.assertEqual([w for _s, _e, w in c.wrong("Привет wrold и мир, привт")],
                         ["wrold", "привт"])
        self.assertEqual(c.suggest("wrold"), ["world"])
        self.assertEqual(c.wrong("NASA I"), [])  # acronyms and one letter pass

    def test_my_own_dictionary(self):
        with tempfile.TemporaryDirectory() as d:
            own = Path(d) / "spelling.txt"
            c = spell.Checker(["en"], own)
            self.assertEqual(len(c.wrong("fedtail rocks")), 2)
            c.add("fedtail")
            c.add("fedtail")  # once
            self.assertEqual(own.read_text("utf-8"), "fedtail\n")
            self.assertEqual([w for *_x, w in c.wrong("fedtail rocks")], ["rocks"])
            self.assertTrue(spell.Checker(["en"], own).ok("fedtail"))  # next time too

    def test_languages_picked(self):
        inst = ["de_DE", "en_GB", "en_US", "ru_RU"]
        self.assertEqual(spell.pick(["ru", "en", "xx", "en-GB"], inst),
                         ["ru_RU", "en_US", "en_GB"])
        self.assertEqual(spell.wanted_languages({"post": {}}, "uk", "ru"), ["uk", "ru", "en"])
        self.assertEqual(spell.wanted_languages({"post": {}}, "", "en"), ["en"])
        self.assertEqual(spell.wanted_languages({"post": {"spell_languages": ["de"]}}, "ru"),
                         ["de"])

    def test_for_post(self):
        cfg = {"post": {"spellcheck": True}}
        a = spell.for_post(cfg, None, "ru", "en")
        self.assertIs(spell.for_post(cfg, None, "ru", "en"), a)  # kept
        self.assertEqual(a.tags, ["ru_RU", "en_US"])
        self.assertIsNone(spell.for_post({"post": {"spellcheck": False}}, None))
        # no dictionary for any of the languages: no checker
        self.assertIsNone(spell.for_post({"post": {"spell_languages": ["xx"]}}, None))

    def test_without_enchant_nothing_breaks(self):
        with mock.patch.object(spell, "_backend", False):
            self.assertFalse(spell.available())
            self.assertEqual(spell.languages(), [])
            c = spell.Checker(["en"])
            self.assertFalse(c.working)
            self.assertEqual(c.wrong("wrold"), [])
            self.assertIsNone(spell.for_post({"post": {}}, None))


class SystemDictionaryTest(unittest.TestCase):
    """The real thing: libenchant-2 (ctypes) or pyenchant, where installed."""

    def test_english(self):
        spell._backend = None  # found anew
        try:
            if not spell.available() or not spell.pick(["en"], spell.languages()):
                self.skipTest("no Enchant with an English dictionary here")
            c = spell.Checker(["en"])
            self.assertEqual([w for *_x, w in c.wrong("Helo wrold, this is fine")],
                             ["Helo", "wrold"])
            self.assertIn("world", c.suggest("wrold"))
        finally:
            spell._backend = None


if __name__ == "__main__":
    unittest.main()
