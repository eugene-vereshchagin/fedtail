"""Budgets as tests (docs/en/dev/memory.md, step 8): the bench of step 0 with ceilings of
memory and time, so lightness doesn't creep back with new features. Slow (minutes): run
when FEDTAIL_BUDGETS is set — CI's budgets job, a release waits for it; by hand:

    FEDTAIL_BUDGETS=1 python3 -m unittest tests.test_budgets -v

The ceilings are about a quarter over what the bench says now (28.10: 2000 posts, 20 lanes,
an hour of polling): over one — the test fails and says by how much; lower numbers after a
step of the plan move them down here, never up without a reason in memory.md."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = bool(os.environ.get("FEDTAIL_BUDGETS"))

# what the bench says the scenario holds (USS, MB) and takes (ms), at most
CORE = {"memory": {"after.uss_mb": 90},
        "time": {"open every lane (19)": 2000, "lanes' rules applied anew (all of them)": 2500}}
QT = {"memory": {"after.uss_mb": 480, "after_malloc_trim.uss_mb": 340},
      "time": {"Qt window up, Home drawn": 6000, "open every lane (19)": 25000,
               "Home scrolled through 1000 posts": 1500},
      "counts": {"qt.widgets": 3000, "qt.images_mb": 66}}


def bench(*args):
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "r.json"
        subprocess.run([sys.executable, str(ROOT / "tools" / "membench.py"), "--posts", "2000",
                        "--hours", "1", "--json", str(out), *args], check=True, timeout=1500,
                       env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                       stdout=subprocess.DEVNULL)
        return json.loads(out.read_text("utf-8"))


def over(result, budget):
    """[what is over its ceiling, in words]."""
    bad = []
    for name, most in budget.get("memory", {}).items():
        state, key = name.split(".")
        got = result["memory"].get(state, {}).get(key)
        if got is not None and got > most:
            bad.append(f"memory {name}: {got} MB, the ceiling {most}")
    times = {k.strip(): v for k, v in result["time"]}
    for name, most in budget.get("time", {}).items():
        if times.get(name, 0) > most:
            bad.append(f"time {name}: {times[name]} ms, the ceiling {most}")
    for name, most in budget.get("counts", {}).items():
        got = result["counts"].get(name)
        if got is not None and got > most:
            bad.append(f"{name}: {got}, the ceiling {most}")
    return bad


class OverTest(unittest.TestCase):
    """The check itself, quick: always run."""

    def test_says_what_is_over(self):
        r = {"memory": {"after": {"uss_mb": 100}}, "time": [("  open every lane (19)", 10)],
             "counts": {"qt.widgets": 5}}
        self.assertEqual(over(r, CORE), ["memory after.uss_mb: 100 MB, the ceiling 90"])
        self.assertEqual(over(r, {"counts": {"qt.widgets": 4}}), ["qt.widgets: 5, the ceiling 4"])
        self.assertEqual(over(r, {"time": {"open every lane (19)": 5}}),
                         ["time open every lane (19): 10 ms, the ceiling 5"])


@unittest.skipUnless(RUN, "slow: set FEDTAIL_BUDGETS=1")
class BudgetTest(unittest.TestCase):
    def test_the_core(self):
        self.assertEqual(over(bench(), CORE), [])

    def test_the_qt_window(self):
        try:
            import PySide6  # noqa: F401
        except ImportError:
            self.skipTest("no PySide6")
        self.assertEqual(over(bench("--ui", "qt"), QT), [])


if __name__ == "__main__":
    unittest.main()
