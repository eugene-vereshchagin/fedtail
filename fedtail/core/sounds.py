"""Which sound, and whether now: the core's half of the sound scheme. Plain Python.

The core knows what happened (news in a lane, connected, a post sent); the theme knows
what it sounds like (frontends/soundpack.py) and the frontend plays it. So the core
only names an *event* and emits ``sound`` with it; every frontend reacts the same way.

A batch of news chimes once, with the weightiest event of the batch (a private message
over a reply over a mention… over a plain "message"), and never more often than
``sound.min_gap_seconds``.
"""

from __future__ import annotations

import time

from . import lanes as lanes_mod

# the weightiest first: a batch chimes with the first of these it has
EVENTS = ("direct", "reply", "mention", "thread", "request", "activity", "message",
          "online", "sent")
LANE_EVENT = {"direct": "direct", "replies": "reply", "mentions": "mention",
              "subs": "thread", "requests": "request", "activity": "activity"}


def event_for_lane(name):
    """The sound a lane's news makes: its own, or "message" (home, lists, bots…)."""
    return LANE_EVENT.get(name, "message")


def weightiest(events):
    """The first of EVENTS among these, or None."""
    got = set(events)
    for e in EVENTS:
        if e in got:
            return e
    return None


class Chime:
    """Decides what to sound and holds the gap between sounds.

    Args:
        cfg: the whole config dict (its ``sound`` section is read every time, so a
            config re-read takes effect at once).
        chosen: ``(lane, wanted, never) -> bool`` — lanes.chosen with lists' titles
            (Core.lane_chosen); the plain ``lanes.chosen`` when None.
        clock: monotonic seconds (tests pass their own).
    """

    def __init__(self, cfg, chosen=None, clock=time.monotonic):
        self.cfg = cfg
        self.chosen = chosen or (lambda n, w, x=(): lanes_mod.chosen(n, w, x))
        self.clock = clock
        self._last = None

    @property
    def on(self):
        s = self.cfg.get("sound") or {}
        return bool(s.get("enabled", True)) and s.get("scheme", "theme") != "none"

    def lane_wanted(self, name):
        s = self.cfg["sound"]
        return self.chosen(name, s["lanes"], s.get("except") or ())

    def for_news(self, lanes_with_news):
        """The event for a batch of news (lane names that got unread posts), or None:
        sounds off, no lane asked for, or too soon after the last one."""
        if not self.on:
            return None
        event = weightiest(event_for_lane(n) for n in lanes_with_news if self.lane_wanted(n))
        return self._pass(event)

    def for_moment(self, event):
        """"online" or "sent", if the config wants it (and the gap allows)."""
        if not self.on or event not in ("online", "sent") or not self.cfg["sound"].get(event):
            return None
        return self._pass(event)

    def _pass(self, event):
        if event is None:
            return None
        now = self.clock()
        gap = max(0, self.cfg["sound"].get("min_gap_seconds", 3))
        if self._last is not None and now - self._last < gap:
            return None
        self._last = now
        return event
