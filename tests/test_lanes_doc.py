"""The guide to writing lanes (docs/<lang>/lanes.md) says what every word means: each key of
a lane and of a condition, and each word the core knows for them (core/atoms.py), in both
languages — a word added to the core without its line here fails; a line for a word the
core no longer has fails too."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _docs_build():
    spec = importlib.util.spec_from_file_location("docs_build", ROOT / "tools" / "docs_build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LaneWordsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = _docs_build()
        cls.d = cls.db.load_lane_words()

    def _both(self, entry, where):
        self.assertIsInstance(entry, dict, where)
        for lang in ("ru", "en"):
            self.assertTrue(str(entry.get(lang) or "").strip(), f"{where}: no {lang}")

    def test_every_key_explained(self):
        rule, cond = self.db.lane_keys()
        for where, keys in (("rule", rule), ("condition", cond)):
            got = self.d.get(where, {})
            self.assertEqual(sorted(got), sorted(keys), f"[{where}.*] against the core")
            for k in keys:
                self._both(got[k], f"{where}.{k}")

    def test_every_word_explained(self):
        words = self.db.lane_words()
        got = self.d.get("word", {})
        self.assertEqual(sorted(got), sorted(words), "[word.<key>] against the core")
        for key, ws in words.items():
            self.assertEqual(sorted(got[key]), sorted(ws), f"[word.{key}] against the core")
            for w in ws:
                self._both(got[key][w], f"word.{key}.{w}")


if __name__ == "__main__":
    unittest.main()
