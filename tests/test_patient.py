"""common/patient.py: asked again when the answer fails, is wrong or doesn't come."""

import unittest
from concurrent.futures import Future

from fedtail.frontends.common.patient import Patient


class Harness:
    def __init__(self):
        self.futs, self.timers, self.said, self.got, self.gave = [], [], [], [], []

    def ask(self):
        f = Future()
        self.futs.append(f)
        return f

    def call(self, fut, ok, fail):
        fut.add_done_callback(lambda f: fail(f.exception()) if f.exception() else ok(f.result()))

    def later(self, s, fn):
        self.timers.append((s, fn))

    def fire(self):
        timers, self.timers = self.timers, []
        for _s, fn in timers:
            fn()

    def patient(self, **kw):
        return Patient(self.ask, self.call, self.later, ok=self.got.append,
                       say=self.said.append, give_up=self.gave.append, what="t", **kw)


class PatientTest(unittest.TestCase):
    def test_comes_at_once(self):
        h = Harness()
        h.patient().start()
        h.futs[0].set_result("acc")
        self.assertEqual(h.got, ["acc"])
        h.fire()  # its waiting timer: nothing more
        self.assertEqual(len(h.futs), 1)

    def test_fails_then_comes(self):
        h = Harness()
        h.patient().start()
        h.futs[0].set_exception(OSError("down"))
        self.assertEqual(len(h.said), 1)
        h.fire()  # the wait timer of the first, the pause: asked again
        self.assertEqual(len(h.futs), 2)
        h.futs[1].set_result("acc")
        self.assertEqual(h.got, ["acc"])
        self.assertEqual(h.gave, [])

    def test_wrong_and_late_answers_then_gives_up(self):
        h = Harness()
        p = h.patient(good=lambda x: bool(x))
        p.start()
        h.futs[0].set_result({})          # an odd answer
        h.fire()
        h.fire()                           # the second never answers: late
        h.fire()
        h.futs[2].set_exception(OSError("x"))
        self.assertEqual(len(h.gave), 1)
        self.assertEqual(h.got, [])
        h.futs[1].set_result("late")       # too late: nobody listens
        self.assertEqual(h.got, [])
        p.again()                          # Retry
        h.futs[-1].set_result("acc")
        self.assertEqual(h.got, ["acc"])


if __name__ == "__main__":
    unittest.main()
