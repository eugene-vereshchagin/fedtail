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
        keep = app_module.KEEP_PER_SOURCE
        app_module.KEEP_PER_SOURCE = KEEP
        self.addCleanup(setattr, app_module, "KEEP_PER_SOURCE", keep)
        self.n = 0

    def make(self, **over):
        FakeApi.world = fakes.World()
        user = {"feed": {"first_run_mark_read": False, "page_size": 20},
                "subs": {"enabled": False}}
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
        self.assertLessEqual(len(core.lane_entries("people")), KEEP, d)
        # nothing waiting or in flight once the polls are done
        self.assertEqual((d["pool_queue"], d["bg_queue"]), (0, 0), d)
        self.assertEqual((d["parents_inflight"], d["replies_inflight"]), (0, 0), d)
        self.assertLessEqual(d["lane_cache"], len(core.lanes) * 2, d)
        # no thread per poll, and the Python heap doesn't grow with the posts
        self.assertLessEqual(threading.active_count(), threads0 + 2)
        grown = len(gc.get_objects()) - objects0
        # (900 posts went by: a dict per post kept would be +900 at least)
        self.assertLess(grown, 600, f"{grown} more Python objects after 60 polls")
        # a poll stays quick however many posts went by (generous: CI machines vary)
        self.assertLess(max(times), 2.0, times)
        self.assertLess(sum(times[-10:]) / 10, 3 * (sum(times[:10]) / 10) + 0.05, times)

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
        ids = [st["id"] for _, st in core.lane_entries("people")]
        t = time.monotonic()
        for _ in range(50):
            core.mark_read(ids)
        self.assertLess(time.monotonic() - t, 3.0)
        self.assertEqual(core.unread_ids(core.lane_entries("people")), set())


if __name__ == "__main__":
    unittest.main()
