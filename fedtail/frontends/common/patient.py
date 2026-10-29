"""Asking the core again when an answer doesn't come, without a toolkit: who a profile
is (a tab stayed "@…" until a restart when the one request failed, 27.10).

The asking goes: a failure, a wrong answer or no answer within `wait_s` is said —
"didn't come (…) — asking again…" — and asked again, `tries` times in all; then said
for good, and the window offers "Retry" (again()). The toolkit gives its own way to
wait on a future (call) and its timer (later); the rest is decided here, the same in
every window.
"""

from __future__ import annotations

import logging

from ...i18n import _

log = logging.getLogger(__name__)


class Patient:
    TRIES = 3
    WAIT_S = 20     # no answer by then: said, and asked again
    AGAIN_S = 3     # the pause before asking again

    def __init__(self, ask, call, later, *, ok, say, give_up, good=None, what=""):
        """ask() → a future; call(fut, ok, fail): the toolkit's bridge; later(seconds,
        fn): its timer. ok(answer) once a good one comes (good(answer), else any not
        None); say(text) while trying; give_up(text) after the last try."""
        self.ask, self.call, self.later = ask, call, later
        self.ok, self.say, self.give_up = ok, say, give_up
        self.good = good or (lambda x: x is not None)
        self.what = what
        self.done = False
        self._asked = 0  # which asking is the current one (an old one's answer is late)

    def start(self, tries=None):
        self.left = self.TRIES if tries is None else tries
        self.done = False
        self._ask()

    again = start  # "Retry": the same, from the start

    def _ask(self):
        self._asked += 1
        n = self._asked
        self.call(self.ask(), lambda x: self._answer(n, x), lambda e: self._failed(n, e))
        self.later(self.WAIT_S, lambda: self._late(n))

    def _answer(self, n, x):
        if self.done or n != self._asked:
            return
        if not self.good(x):  # not what was asked for (an empty or odd answer): said
            self._failed(n, _("profile_bad_answer"))
            return
        self.done = True
        self.ok(x)

    def _late(self, n):
        if self.done or n != self._asked:
            return
        log.warning("%s: no answer after %d s", self.what, self.WAIT_S)
        self._failed(n, _("profile_slow"))

    def _failed(self, n, err):
        if self.done or n != self._asked:
            return
        log.warning("%s: %s", self.what, err)
        self.left -= 1
        if self.left > 0:
            self.say(_("profile_retrying", err=err))
            self._asked += 1  # the one that failed: its answer, if it comes, is late
            nxt = self._asked
            self.later(self.AGAIN_S, lambda: self._again(nxt))
            return
        self.done = True
        self.give_up("⚠ " + _("profile_failed", err=err))

    def _again(self, n):
        if not self.done and n == self._asked:
            self._ask()
