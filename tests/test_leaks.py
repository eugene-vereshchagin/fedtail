"""The leak watch (fedtail/leaks.py) and its place in diag: trends, census, tracemalloc."""

import gc
import logging
import tempfile
import tracemalloc
import unittest
from pathlib import Path

from fedtail import diag, leaks


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class TrendTest(unittest.TestCase):
    def feed(self, trend, clock, values, key="rss_mb", step_s=300):
        out = []
        for v in values:
            out += trend.add({key: v})
            clock.t += step_s
        return out

    def test_steady_growth_warns_once_then_on_doubling(self):
        clock = Clock()
        t = leaks.Trend(samples=6, warmup_s=0, clock=clock)
        # +10 MB every 5 minutes: 120 MB/h
        got = self.feed(t, clock, [100 + 10 * i for i in range(7)])
        self.assertEqual(len(got), 1)
        self.assertIn("rss_mb rose on each of the last 6 checks", got[0])
        self.assertIn("+120/h", got[0])
        # still growing, but not yet twice as much as when it warned: quiet
        self.assertEqual(self.feed(t, clock, [170, 180, 190]), [])
        # past twice the growth it warned at (+60 then): again
        again = self.feed(t, clock, [200 + 10 * i for i in range(4)])
        self.assertEqual(len(again), 1)

    def test_breathing_and_crumbs_and_warmup_say_nothing(self):
        clock = Clock()
        t = leaks.Trend(samples=6, warmup_s=0, clock=clock)
        # up and down: a cache that fills and empties
        self.assertEqual(self.feed(t, clock, [100, 140, 110, 150, 105, 160, 120, 170]), [])
        # up every time, by less than the noise floor (20 MB over the window)
        t2 = leaks.Trend(samples=6, warmup_s=0, clock=clock)
        self.assertEqual(self.feed(t2, clock, [100 + i for i in range(10)]), [])
        # the first half hour: lanes fill, no verdicts however it grows
        clock3 = Clock()
        t3 = leaks.Trend(samples=3, clock=clock3)
        self.assertEqual(self.feed(t3, clock3, [100 + 50 * i for i in range(6)]), [])

    def test_store_rows_are_summarised_not_judged(self):
        clock = Clock()
        t = leaks.Trend(samples=3, warmup_s=0, clock=clock)
        got = self.feed(t, clock, [1000 * i for i in range(1, 10)], key="core.statuses")
        self.assertEqual(got, [])
        self.assertIn("core.statuses", t.summary())

    def test_rate_ignores_one_spike(self):
        clock = Clock()
        t = leaks.Trend(samples=12, warmup_s=0, clock=clock)
        self.feed(t, clock, [100] * 6 + [400] + [100] * 6, step_s=600)
        self.assertLess(abs(t.rate("rss_mb")), 60)  # a spike, not +300 MB/h


class CensusTest(unittest.TestCase):
    def test_says_what_grew(self):
        c = leaks.Census("demo", top=3)
        self.assertIsNone(c.take({"dict": 10, "list": 5}))  # the baseline
        line = c.take({"dict": 10, "list": 9, "PostRow": 40})
        self.assertIn("PostRow +40", line)
        self.assertIn("list +4", line)
        self.assertNotIn("dict", line.split("since start")[0])  # unchanged: not a mover

    def test_python_objects_by_type(self):
        class Leaky:
            pass
        before = leaks.python_objects()
        held = [Leaky() for _ in range(500)]
        after = leaks.python_objects()
        name = f"{Leaky.__module__}.{Leaky.__qualname__}"
        self.assertEqual(after[name] - before.get(name, 0), 500)
        del held

    def test_gc_stats(self):
        s = leaks.gc_stats()
        self.assertEqual(set(s), {"uncollectable", "gen0", "gen1", "gen2", "collections_gen2"})


class TracingTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.folder = Path(self._tmp.name)
        self.was = tracemalloc.is_tracing()
        self.addCleanup(self._tmp.cleanup)

    def tearDown(self):
        if not self.was:
            leaks.stop_tracing()

    def test_snapshot_names_the_line_that_grew(self):
        leaks.stop_tracing()
        with self.assertRaises(RuntimeError):
            leaks.snapshot(self.folder)
        leaks.start_tracing()
        first = leaks.snapshot(self.folder)
        self.assertIn("the first snapshot", first.read_text("utf-8"))
        hoard = [bytes(1000) + bytes([i % 256]) for i in range(3000)]  # ~3 MB, this line
        second = leaks.snapshot(self.folder)
        text = second.read_text("utf-8")
        self.assertIn("grew most since the first snapshot", text)
        self.assertIn("test_leaks.py", text.split("grew most")[1])
        self.assertTrue(second.name.startswith("memory-"))
        self.assertIn("memory-*.txt", diag.OUR_LOGS)  # old ones go with the old logs
        del hoard


class StatsLoopTest(unittest.TestCase):
    def setUp(self):
        self.saved = dict(diag._state)
        self.addCleanup(lambda: (diag._state.clear(), diag._state.update(self.saved)))
        self.lines = []
        h = logging.Handler()
        h.emit = lambda r: self.lines.append(r.getMessage())
        for name in ("fedtail.diag", "fedtail.leaks"):
            lg = logging.getLogger(name)
            lg.addHandler(h)
            lg.setLevel(logging.DEBUG)
            self.addCleanup(lg.removeHandler, h)

    def test_check_now_logs_stats_trend_census_and_summary(self):
        diag._state["trend"] = leaks.Trend(samples=3)
        diag._state["census"] = {}
        s = diag.check_now(objects=True)
        self.assertIn("gc.uncollectable", s)
        diag.check_now(objects=True)
        text = "\n".join(self.lines)
        self.assertIn("stats {", text)
        self.assertIn("trend over", text)
        self.assertIn("census python", text)
        bits = diag.session_summary()
        self.assertIn("hours", bits)
        self.assertIn("session summary", "\n".join(self.lines))

    def test_census_off_by_default_costs_nothing(self):
        diag._state["trend"] = None
        diag._state["census_on"] = False
        diag._state["census"] = {}
        diag.check_now()
        self.assertEqual(diag._state["census"], {})
        gc.collect()


if __name__ == "__main__":
    unittest.main()
