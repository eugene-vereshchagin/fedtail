"""Slow mode (poll.slow_minutes: the news in a batch every N minutes), a lane's own
"notify at most every N minutes" (calm), and "of them new" — what the last update
brought, still unread (the phone's tiles, the sidebars)."""

import tempfile
import threading
import time
import unittest
from unittest import mock

from fedtail.core import auth, config, paths
from fedtail.core.app import Core
from fedtail.core.view import View
from fedtail.frontends.common import sidebar
from fedtail.frontends.common.places import Places

from . import fakes
from .fakes import BOB, FakeApi, status


class Base(unittest.TestCase):
    def make(self, **over):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        FakeApi.world = fakes.World()
        user = {"feed": {"first_run_mark_read": False, "page_size": 3},
                "notify": {"lanes": ["home", "replies", "mentions"]},
                "sound": {"enabled": "on", "lanes": ["home"], "min_gap_seconds": 0}}
        for k, v in over.items():
            user.setdefault(k, {}).update(v)
        c, _ = config.validate(user)
        self.tmp = tmp.name
        p = paths.resolve("t", config=f"{tmp.name}/c.toml", data=f"{tmp.name}/d")
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(c, p, api_class=FakeApi)
        core._origin_json = lambda url: None
        self.events = []
        core.events.on("*", lambda n, pl: self.events.append((n, pl)))
        self.addCleanup(core.shutdown)
        core.connect().result()
        core.poll_once()  # the first round: history, not news
        return core, FakeApi.world

    def notified(self):
        return [st["id"] for n, pl in self.events if n == "notify" for _lane, st in pl]


class FreshTest(Base):
    def test_of_them_new_is_the_last_update(self):
        core, w = self.make()
        for i in range(3):
            w.add(status(f"03{i}", BOB, minute=i + 1), home=True)
        core.poll_once()
        self.assertEqual(core.unread_count("home"), 3)
        self.assertEqual(core.fresh_count("home"), 3)
        w.add(status("040", BOB, minute=9), home=True)
        core.poll_once()
        self.assertEqual(core.unread_count("home"), 4)
        self.assertEqual(core.fresh_count("home"), 1)  # what this update brought
        core.poll_once()  # a round with nothing: the last update stays the last
        self.assertEqual(core.fresh_count("home"), 1)
        core.mark_read(["040"])
        self.assertEqual(core.fresh_count("home"), 0)  # read: not new any more
        self.assertEqual(core.fresh_count("replies"), 0)
        view = View(core)
        self.assertEqual(sidebar.fresh(view, "home"), 0)
        self.assertEqual(sidebar.fresh_words(0), "")
        self.assertIn("56", sidebar.fresh_words(56))

    def test_requests_and_activity(self):
        core, w = self.make()
        core._fresh = {"requests": {"r1", "r2"}, "activity": {"a1", "a2", "a3"}}
        core.follow_requests = [{"id": "r1"}]
        self.assertEqual(core.fresh_count("requests"), 1)
        with mock.patch.object(core, "activity_unread", return_value=2):
            self.assertEqual(core.fresh_count("activity"), 2)

    def test_a_lane_it_cant_count_says_nothing(self):
        view = mock.Mock()
        view.me = None
        self.assertEqual(sidebar.fresh(view, "home"), 0)
        view.me = {"id": "1"}
        view.lane_by_name = {}
        view.fresh_count.side_effect = RuntimeError("no")
        self.assertEqual(sidebar.fresh(view, "home"), 0)


class CalmTest(Base):
    def test_a_lane_notifies_at_most_every_n_minutes(self):
        core, w = self.make()
        now = [1000.0]
        core.set_calm("home", 30)
        self.assertEqual(core.calm("home"), 30)
        with mock.patch("fedtail.core.app.time.time", lambda: now[0]):
            w.add(status("050", BOB, minute=1), home=True)
            core.poll_once()
            self.assertEqual(self.notified(), ["050"])  # quiet for long: at once
            w.add(status("051", BOB, minute=2), home=True)
            w.add(status("052", BOB, minute=3), home=True)
            core.poll_once()
            self.assertEqual(self.notified(), ["050"])  # held: within its minutes
            self.assertEqual(core.unread_count("home"), 3)  # the lane itself updated
            core.mark_read(["051"])
            now[0] += 31 * 60
            core.poll_once()  # nothing new — the held ones come out, the read one not
            self.assertEqual(self.notified(), ["050", "052"])
            self.assertIn(("sound", "message"), self.events)
        core.set_calm("home", 0)
        self.assertEqual(core.calm("home"), 0)
        w.add(status("053", BOB, minute=4), home=True)
        core.poll_once()
        self.assertEqual(self.notified()[-1], "053")

    def test_bad_state_reads_as_none(self):
        core, _w = self.make()
        core.set_state("calm.home", "lots")
        self.assertEqual(core.calm("home"), 0)


class SlowTest(Base):
    def test_minutes_and_due(self):
        core, _w = self.make(poll={"slow_minutes": 10})
        self.assertEqual(core.slow_minutes(), 10)
        self.assertFalse(core.slow_due())  # a round just now
        core._last_poll_ok -= 11 * 60
        self.assertTrue(core.slow_due())
        core.set_slow(0)
        self.assertEqual(core.slow_minutes(), 0)
        self.assertTrue(core.slow_due())
        self.assertIsNone(core.next_round())
        core.cfg["poll"]["slow_minutes"] = "x"
        self.assertEqual(core.slow_minutes(), 0)

    def test_the_stream_wakes_nothing(self):
        core, _w = self.make(poll={"slow_minutes": 5})
        core._wake.clear()
        core._poll_soon()
        self.assertFalse(core._wake.is_set())
        core.set_slow(0)
        core._wake.clear()
        core._poll_soon()
        self.assertTrue(core._wake.is_set())

    def test_the_wait(self):
        core, _w = self.make(poll={"slow_minutes": 5})
        done = time.monotonic()
        t = threading.Thread(target=core._slow_wait, args=(done,), daemon=True)
        t.start()
        for _ in range(100):
            if core._next_round:
                break
            time.sleep(0.01)
        self.assertGreater(core.next_round(), time.time() + 4 * 60)
        core._wake.set()  # the stream or a change: not the end of the wait
        time.sleep(0.05)
        self.assertTrue(t.is_alive())
        core.poll_now()  # Refresh: at once
        t.join(2)
        self.assertFalse(t.is_alive())
        self.assertFalse(core._urgent)
        # slow mode turned off meanwhile: the wait ends
        t = threading.Thread(target=core._slow_wait, args=(time.monotonic(),), daemon=True)
        t.start()
        time.sleep(0.05)
        core.set_slow(0)
        t.join(2)
        self.assertFalse(t.is_alive())
        core.cfg["poll"]["slow_minutes"] = 1
        core._slow_wait(time.monotonic() - 120)  # due already: no wait at all


class PlaceTest(Base):
    def test_the_place(self):
        core, _w = self.make(poll={"slow_minutes": 15})
        core._next_round = time.time() + 600
        view = View(core)
        places = Places(view)
        self.assertIn("slow", [n for n, _t in places.menu()])
        page = places.page("slow")
        names = [f.name for f in page.form]
        self.assertEqual(names[0], "slow")
        self.assertIn("calm.home", names)  # notifies: "at most every" means something
        self.assertNotIn("calm.local", names)
        self.assertEqual(len(page.rows), 1)  # when the next batch comes
        with mock.patch("fedtail.frontends.common.settings.save") as save:
            out = places.act("slow", "save", values={"slow": "60", "calm.home": "30",
                                                     "calm.bad": "x", "other": "1"})
        save.assert_called_once()
        self.assertEqual(core.slow_minutes(), 60)
        self.assertEqual(core.calm("home"), 30)
        self.assertTrue(out.refresh)
        self.assertIn("60", out.message)
        out = places.act("slow", "save", values={"slow": "60", "calm.home": "30"})
        self.assertEqual(out.message, "")  # nothing changed
        with mock.patch("fedtail.frontends.common.settings.save",
                        side_effect=OSError("ro")):
            out = places.act("slow", "save", values={"slow": "0", "calm.home": "0"})
        self.assertEqual(core.slow_minutes(), 0)  # this run has it anyway
        self.assertEqual(core.calm("home"), 0)
        out = places.act("slow", "save", values={"slow": "nope"})
        self.assertFalse(out.error)

    def test_no_lane_notifies(self):
        core, _w = self.make(notify={"lanes": []}, sound={"lanes": []})
        page = Places(View(core)).page("slow")
        self.assertEqual([f.name for f in page.form], ["slow"])
        self.assertTrue(page.rows)  # says why there's nothing more


class MergedTest(unittest.TestCase):
    def test_every_account(self):
        from fedtail.core.merged import MergedCore
        a, b = mock.Mock(), mock.Mock()
        a.lane_by_name = {"home": 1}
        b.lane_by_name = {"home": 1}
        a.fresh_count.return_value = 2
        b.fresh_count.return_value = 3
        a.calm.return_value = 10
        m = MergedCore.__new__(MergedCore)
        m.primary, m.others = a, {"w": b}
        m._own_lane = lambda name: [(a, None, name), (b, "w", name)]
        self.assertEqual(m.fresh_count("home"), 5)
        self.assertEqual(m.calm("home"), 10)
        m.set_calm("home", 5)
        a.set_calm.assert_called_with("home", 5)
        b.set_calm.assert_called_with("home", 5)
        m.set_slow(30)
        a.set_slow.assert_called_with(30)
        b.set_slow.assert_called_with(30)


class BridgeTest(unittest.TestCase):
    def test_slow_words(self):
        import sys
        sys.path.insert(0, "android/app/src/main/python")
        from fedtail_android import bridge
        core = mock.Mock()
        core.slow_minutes.return_value = 0
        self.assertEqual(bridge._slow_words(core), "")
        core.slow_minutes.return_value = 10
        core.next_round.return_value = time.time() + 300
        self.assertIn(":", bridge._slow_words(core))
        core.slow_minutes.side_effect = RuntimeError
        self.assertEqual(bridge._slow_words(core), "")


if __name__ == "__main__":
    unittest.main()
