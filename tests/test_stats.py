"""The READMEs' numbers (docs/src/stats.toml, tools/stats.py) are near the code's: a part
grown or shrunk by more than a sixth since they were counted fails — count anew."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _stats():
    spec = importlib.util.spec_from_file_location("stats", ROOT / "tools" / "stats.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class StatsTest(unittest.TestCase):
    def test_the_stored_numbers_are_near(self):
        st = _stats()
        stored = st.load()
        lines, tests = st.count()
        self.assertEqual(sorted(stored["lines"]), sorted(lines))
        for part, n in lines.items():
            was = stored["lines"][part]
            self.assertLess(abs(n - was), max(was, 1) / 6,
                            f"{part}: {was} stored, {n} now — python3 tools/stats.py --write")
        # what ran (with the classes made in loops) against the `def test`s now
        self.assertLess(abs(stored["tests"] - tests), stored["tests"] / 6)
        self.assertGreater(stored.get("coverage", 0), 0)

    def test_coverage_read_from_a_run(self):
        import tempfile
        st = _stats()
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "notes.txt").write_text(
                "- total: **87.7 %** (53544 of 61082 lines)\n- tests: 1968 run, 0 failed\n",
                "utf-8")
            self.assertEqual(st.coverage_of(d), (87.7, 1968))
            self.assertEqual(st.coverage_of(Path(d) / "none"), (None, None))


if __name__ == "__main__":
    unittest.main()
