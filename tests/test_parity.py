"""The four interfaces offer the same things (tools/parity.py): every word of the
interface one shows and another doesn't is explained in docs/src/parity.toml — a
function missing on purpose, or said in other words — and what the registry says an
interface has, it shows. A feature added to one interface only, or lost in one, stops
here until the registry (and so the docs' "Four interfaces" table) says so."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import parity  # noqa: E402


def cap(**kw):
    base = {"id": "x", "area": "app", "name": {"ru": "x", "en": "x"},
            "note": {"ru": "n", "en": "n"}, "keys": ["about"]}
    base.update(kw)
    return base


HAVE = {"qt": {"about", "close"}, "gtk": {"about", "close"}, "tui": {"close"},
        "web": {"close"}}


class ParityTest(unittest.TestCase):
    def test_the_interfaces_and_the_registry_agree(self):
        problems = parity.check()
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_every_area_is_known_to_the_docs(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import docs_build
        areas = {c["area"] for c in parity.registry()["capability"]}
        for lang in ("ru", "en"):
            self.assertLessEqual(areas, set(docs_build.L[lang]["parity_areas"]), lang)


class CheckLogicTest(unittest.TestCase):
    """check() itself, on a made-up registry and inventory."""

    def test_an_unexplained_gap(self):
        got = parity.check({"capability": [], "wording": []}, HAVE)
        self.assertTrue(any(p.startswith("about: qt, gtk show it, tui doesn't") for p in got))

    def test_explained_by_a_capability_or_a_wording(self):
        self.assertEqual(parity.check({"capability": [cap(tui="no", web="na")]}, HAVE), [])
        self.assertEqual(parity.check({"wording": [
            {"in": ["tui", "web"], "keys": ["about"], "why": {"ru": "r", "en": "e"}}]},
            HAVE), [])

    def test_has_must_show_its_words(self):
        got = parity.check({"capability": [cap(tui="no")]}, HAVE)
        self.assertTrue(any("web is marked \"has\" but doesn't show about" in p
                            for p in got))

    def test_no_but_done(self):
        have = dict(HAVE, tui={"about", "close"})
        got = parity.check({"capability": [cap(tui="no", web="no")]}, have)
        self.assertTrue(any("tui is marked \"no\" but shows every word" in p for p in got))

    def test_the_registry_itself(self):
        bad = cap(tui="maybe", web="na", keys=["about", "no_such_word_at_all"],
                  note={"ru": "только по-русски"}, name={"ru": "x"})
        got = parity.check({"capability": [bad, dict(bad)],
                            "wording": [{"in": ["mars"], "keys": ["nope_nope"],
                                         "why": {}}]}, HAVE)
        text = "\n".join(got)
        for want in ("the id is used twice", "no such word 'no_such_word_at_all'",
                     "tui = 'maybe'", "note.en", "name.en", "no interface 'mars'",
                     "wording: no such word 'nope_nope'", "why.ru"):
            self.assertIn(want, text)


if __name__ == "__main__":
    unittest.main()
