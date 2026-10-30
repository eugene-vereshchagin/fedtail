"""Budgets as tests (docs/en/dev/memory.md, step 8): the bench of step 0 with ceilings of
memory and time, so lightness doesn't creep back with new features. Slow (minutes): run
when FEDTAIL_BUDGETS is set — CI's budgets job, a release waits for it; by hand:

    FEDTAIL_BUDGETS=1 python3 -m unittest tests.test_budgets -v

The ceilings are about a quarter over what the bench says now (29.10: 2000 posts, 20 lanes,
an hour of polling; the times more, for a slower runner): over one — the test fails and
says by how much; lower numbers after a step of the plan move them down here, never up
without a reason in memory.md."""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = bool(os.environ.get("FEDTAIL_BUDGETS"))

# what the bench says the scenario holds (USS, MB) and takes (ms), at most
# a new lane's fill linking stored posts instead of writing them anew (29.10): 90 → 75;
# langdetect loaded only when a rule or the filter asks (52 MB at 30.10): 75 → 65
CORE = {"memory": {"after.uss_mb": 65},
        "time": {"open every lane (19)": 2000, "lanes' rules applied anew (all of them)": 2500}}
# step 5 (only the cards near the screen: 29.10) took these down from 480 / 340 MB,
# 6000 / 25 000 ms and 3000 widgets
# the bench deleting what a running loop deletes, and the core above: 280 / 270 → 250 / 240,
# 1600 → 1300 widgets
QT = {"memory": {"after.uss_mb": 250, "after_malloc_trim.uss_mb": 240},
      "time": {"Qt window up, Home drawn": 2500, "open every lane (19)": 8000,
               "Home scrolled through 1000 posts": 1500},
      "counts": {"qt.widgets": 1300, "qt.images_mb": 66}}


# the GTK window (tools/gtk_bench.py, single layout, 2000 posts): a turn of its loop at
# most this long on any step — the freezes a reader feels — and these steps this long at
# most (30.10: the worst turn 136 ms at the start, the lanes 25 ms, a theme 1.0 s)
GTK = {"worst_ms": 250,
       "time": {"start: window, connected": 2500, "open lane federated": 500,
                "open lane local": 500, "open lane bots": 500, "try theme nord": 2500}}
STEP = re.compile(r"^\s+(.+?)\s+(\d+) ms\s+worst\s+(\d+) ms", re.M)


def gtk_bench():
    """gtk_bench.py's steps: [(name, ms, worst ms)], on a screen of its own (xvfb)."""
    env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
    out = subprocess.run(["xvfb-run", "-a", sys.executable, str(ROOT / "tools" / "gtk_bench.py"),
                          "--layout", "single", "--theme", "system", "--posts", "2000"],
                         check=True, timeout=1500, env=env, capture_output=True, text=True)
    return [(m[1].strip(), int(m[2]), int(m[3])) for m in STEP.finditer(out.stdout)]


def gtk_over(steps, budget):
    """[what is over its ceiling, in words] — a step's worst turn, a step's time."""
    bad = [f"{name}: a turn of {worst} ms, the ceiling {budget['worst_ms']}"
           for name, _ms, worst in steps if worst > budget["worst_ms"]]
    times = {name: ms for name, ms, _w in steps}
    bad += [f"time {name}: {times[name]} ms, the ceiling {most}"
            for name, most in budget["time"].items() if times.get(name, 0) > most]
    return bad


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
        self.assertEqual(over(r, {"memory": {"after.uss_mb": 90}}),
                         ["memory after.uss_mb: 100 MB, the ceiling 90"])
        self.assertEqual(over(r, {"counts": {"qt.widgets": 4}}), ["qt.widgets: 5, the ceiling 4"])
        self.assertEqual(over(r, {"time": {"open every lane (19)": 5}}),
                         ["time open every lane (19): 10 ms, the ceiling 5"])
        steps = [("start: window, connected", 300, 120), ("scroll", 900, 400)]
        self.assertEqual(gtk_over(steps, {"worst_ms": 250, "time": {"start: window, "
                                                                    "connected": 200}}),
                         ["scroll: a turn of 400 ms, the ceiling 250",
                          "time start: window, connected: 300 ms, the ceiling 200"])
        self.assertEqual(STEP.findall("  open lane bots    23 ms   worst     13 ms   slow"),
                         [("open lane bots", "23", "13")])


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

    def test_the_gtk_window(self):
        """GTK as fast as Qt, kept so: no step's turn a freeze, the start and the lanes
        quick (docs/en/dev/gtk.md's "not slower than KDE")."""
        import shutil
        try:
            import gi
            gi.require_version("Gtk", "4.0")
        except (ImportError, ValueError):
            self.skipTest("no GTK 4")
        if not shutil.which("xvfb-run"):
            self.skipTest("no xvfb-run")
        steps = gtk_bench()
        self.assertTrue(steps, "gtk_bench said nothing")
        self.assertEqual(gtk_over(steps, GTK), [])


if __name__ == "__main__":
    unittest.main()
