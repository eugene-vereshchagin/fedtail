"""A night in a few seconds: many poll cycles with new posts coming in, and nothing
may pile up — store rows past the prune limit, caches, in-flight maps, worker
threads, events handlers, Python objects — and a poll must stay quick.

These are the core's numbers; the window's (cards built, widgets, pictures) are in
test_qt_smoke. The bounds are generous: they catch "grows with every cycle", not
a few percent."""

import gc
import tempfile
import threading
import time
import unittest
from pathlib import Path

from fedtail.core import app as app_module
from fedtail.core import auth, config, paths
from fedtail.core.app import Core

from . import fakes
from .fakes import BOB, NEWS, FakeApi, status

KEEP = 60  # the prune limit for these tests (3000 in real life)


class LongRunTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        floor = app_module.KEEP_FLOOR
        app_module.KEEP_FLOOR = KEEP
        self.addCleanup(setattr, app_module, "KEEP_FLOOR", floor)
        self.n = 0

    def make(self, **over):
        FakeApi.world = fakes.World()
        user = {"feed": {"first_run_mark_read": False, "page_size": 20},
                "subs": {"enabled": False}, "storage": {"keep_per_lane": KEEP}}
        for k, v in over.items():
            user.setdefault(k, {}).update(v)
        cfg, _ = config.validate(user)
        p = paths.resolve("t", config=str(self.tmp / "c.toml"), data=str(self.tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(cfg, p, api_class=FakeApi)
        core._origin_json = lambda url: None
        self.addCleanup(core.shutdown)
        core.connect().result()
        return core, FakeApi.world

    def cycle(self, core, w, new=15):
        for _ in range(new):
            self.n += 1
            who = BOB if self.n % 3 else NEWS
            w.add(status(f"{self.n:07d}", who, minute=self.n % 60,
                         text="пост " * 40 + str(self.n)), home=True)
        t = time.monotonic()
        core.poll_once()
        took = time.monotonic() - t
        # the fake server forgets old posts, as a timeline page would: what stays in
        # memory is then fedtail's, not the test's
        old = w.home[:-40]
        del w.home[:-40]
        for st in old:
            w.statuses.pop(st["id"], None)
        return took

    def test_a_night_of_polls_stays_bounded(self):
        core, w = self.make()
        for _ in range(10):  # warm up: lanes, caches, the first pages
            self.cycle(core, w)
        gc.collect()
        objects0 = len(gc.get_objects())
        threads0 = threading.active_count()
        times = [self.cycle(core, w) for _ in range(60)]  # 900 more posts
        gc.collect()
        counts = core.store.diag_counts()
        d = core.diag_stats()

        # the lane keeps what the prune limit says, not everything that came
        self.assertLessEqual(counts["items"], KEEP * 3, counts)
        self.assertLessEqual(len(core.lane_entries("home")), KEEP, d)
        # nothing waiting or in flight once the polls are done
        self.assertEqual((d["pool_queue"], d["bg_queue"]), (0, 0), d)
        self.assertEqual((d["parents_inflight"], d["replies_inflight"]), (0, 0), d)
        self.assertLessEqual(d["lane_cache"], len(core.lanes) * 2, d)
        # no thread per poll, and the Python heap doesn't grow with the posts
        self.assertLessEqual(threading.active_count(), threads0 + 2)
        grown = len(gc.get_objects()) - objects0
        # (900 posts went by: a dict per post kept would be +900 at least)
        self.assertLess(grown, 600, f"{grown} more Python objects after 60 polls")
        # a poll stays quick however many posts went by. Generous, and by the 90th
        # percentile: CI machines (Windows above all) stall a poll now and then for
        # seconds on things that aren't ours — the disk, the antivirus, the collector
        ordered = sorted(times)
        self.assertLess(ordered[int(len(ordered) * 0.9)], 0.5, times)
        self.assertLess(max(times), 15.0, times)
        early, late = sorted(times[:20])[10], sorted(times[-20:])[10]  # medians
        self.assertLess(late, 3 * early + 0.05, times)  # not slower as posts pile up

    def test_the_store_stays_within_its_budget(self):
        # 0 MB: always over budget — every gc cuts the lanes, down to the floor (KEEP)
        core, w = self.make(storage={"keep_per_lane": KEEP * 3, "max_mb": 0,
                                     "grace_hours": 0, "keep_activity": 5})
        for _ in range(10):
            self.cycle(core, w)
        core.collect_garbage()
        self.assertEqual(core.keep_per_lane(), KEEP)
        counts = core.store.diag_counts()
        self.assertLessEqual(len(core.lane_entries("home")), KEEP)
        # posts no lane points at are gone: no more than the lanes hold, their
        # boosted posts and parents
        self.assertLessEqual(counts["statuses"], counts["items"] * 3, counts)
        # room again: the lanes may grow back towards what the config wants
        core.cfg["storage"]["max_mb"] = 1024
        core.collect_garbage()
        self.assertGreater(core.keep_per_lane(), KEEP)

    def test_a_slow_poll_says_where_the_time_went(self):
        import logging
        core, w = self.make(debug={"slow_request_seconds": 1})
        lines = []
        h = logging.Handler()
        h.emit = lambda r: lines.append(r.getMessage())
        lg = logging.getLogger("fedtail.core.app")
        lg.addHandler(h)
        old_level = lg.level
        lg.setLevel(logging.INFO)
        self.addCleanup(lambda: (lg.removeHandler(h), lg.setLevel(old_level)))
        slow_markers = core.api.markers

        def markers(*a, **k):
            time.sleep(1.05)
            return slow_markers(*a, **k)
        self.cycle(core, w)  # the first poll marks nothing: no markers yet
        core.api.markers = markers
        self.cycle(core, w)
        said = [x for x in lines if x.startswith("poll #")]
        self.assertTrue(said and "markers" in said[-1], said)
        self.assertGreaterEqual(core.diag_stats()["max_poll_s"], 1.0)
        self.assertEqual(core.diag_stats()["max_poll_s"], 0.0)  # since the last stats line

    def test_event_handlers_do_not_pile_up(self):
        core, w = self.make()
        before = sum(len(v) for v in core.events._handlers.values()) \
            if hasattr(core.events, "_handlers") else None
        for _ in range(20):
            self.cycle(core, w, new=5)
        if before is not None:
            after = sum(len(v) for v in core.events._handlers.values())
            self.assertEqual(after, before)

    def test_reading_marks_stay_cheap(self):
        """Marking read is what the window does all day: hundreds of ids at once,
        over and over, must stay fast and not grow anything but the read table."""
        core, w = self.make()
        for _ in range(20):
            self.cycle(core, w)
        ids = [st["id"] for _, st in core.lane_entries("home")]
        t = time.monotonic()
        for _ in range(50):
            core.mark_read(ids)
        self.assertLess(time.monotonic() - t, 3.0)
        self.assertEqual(core.unread_ids(core.lane_entries("home")), set())


if __name__ == "__main__":
    unittest.main()
