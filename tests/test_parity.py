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

    def test_the_editor_is_whole_wherever_it_is_drawn(self):
        """One editor in seven places (the Qt window, the GTK panel, the split layout's
        input line in each, the terminal, the page, the phone): a part one of them lacks
        is said in parity.toml ([[editor]]) with its reason, or it is a gap nobody chose
        — the split line had no formatting buttons while the window had, and the check
        by words, taking a toolkit whole, saw nothing (24.11)."""
        problems = parity.check_editors()
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_a_lanes_and_a_threads_head_in_every_interface(self):
        """What stands over a lane and over a thread, part by part, in the Qt window,
        the GTK window, the terminal, the page and the phone — each words them its own
        way, so the check by words can't follow; a part one lacks is said in
        parity.toml ([[lane_head]], [[thread_head]]) or stops here."""
        for thing in ("lane_head", "thread_head"):
            with self.subTest(thing=thing):
                problems = parity.check_things(thing)
                self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_the_editors_check_itself(self):
        have = {p: set(parity.EDITOR_PARTS) for p in parity.EDITOR_PLACES}
        have["qt-line"] = set(parity.EDITOR_PARTS) - {"spell"}
        said = {"editor": []}
        self.assertEqual(parity.check_editors(said, have),
                         ["editor qt-line: no spell — add it, or say why in "
                          "docs/src/parity.toml ([[editor]])"])
        said = {"editor": [{"place": "qt-line", "lacks": ["spell", "poll"],
                            "note": {"ru": "почему", "en": "why"}}]}
        self.assertEqual(parity.check_editors(said, have),
                         ["editor qt-line: said to lack poll, but has it — done? take it "
                          "out of lacks"])
        # "via": handed to the full editor — the place needs the hand-over for it
        via = {"editor": [{"place": "tui", "via": ["poll"],
                           "note": {"ru": "почему", "en": "why"}}]}
        got = parity.check_editors(via, {p: set(parity.EDITOR_PARTS) - {"poll"}
                                         if p == "tui" else set(parity.EDITOR_PARTS)
                                         for p in parity.EDITOR_PLACES})
        self.assertEqual(len(got), 1)  # the terminal's editor has no to_editor
        self.assertIn("no way there", got[0])
        bad = {"editor": [{"place": "nowhere", "lacks": []},
                          {"place": "tui", "lacks": ["wings"], "note": {"ru": "x"}}]}
        got = parity.check_editors(bad, {p: set(parity.EDITOR_PARTS)
                                         for p in parity.EDITOR_PLACES})
        self.assertEqual(len(got), 3)  # no such place, no such part, no English reason

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

    def test_the_phone_is_said_everywhere(self):
        """Android has its own screens and words: its column is said by hand, for every
        capability and every feature the desktop has — and why, when it isn't "has"."""
        problems = parity.check_android()
        self.assertEqual(problems, [], "\n" + "\n".join(problems))
        got = parity.check_android(
            {"capability": [cap(), cap(id="y", android="maybe"),
                            cap(id="z", android="no", android_note={"ru": "нет"})]},
            [("01.toml", {"id": "f1", "status": "has"}),
             ("01.toml", {"id": "f2", "status": "planned"}),
             ("01.toml", {"id": "f3", "status": "partly", "android": "na",
                          "android_note": {"en": "no"}})])
        text = "\n".join(got)
        for want in ("x: android — say", "y: android = 'maybe'", "z: android_note.en",
                     "01.toml: f1: android — say", "01.toml: f3: android_note.ru"):
            self.assertIn(want, text)
        self.assertNotIn("f2", text)  # planned: nothing to say yet

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
