"""Notifications from the terminal, as the windows': what a notification says and when
is notifytext.py's (notify.enabled, notify.privacy, notify.when_focused — the terminal
can't tell whether it is looked at, so a lane on screen counts as looked at); how it
goes out is the terminal's (termcaps.notifier): notify-send where a desktop is there,
else the terminal's own escape code (kitty, Ghostty, WezTerm, foot, iTerm2), else
nowhere — and the ≡ menu's test says so."""

from __future__ import annotations

import logging
import subprocess
import sys

from ... import sysenv
from ...i18n import _
from .. import notifytext
from . import termcaps

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, app, env=None, which=None, out=None):
        self.app = app
        self.cfg = app.core.cfg["notify"]
        self.backend, self.how = termcaps.notifier(termcaps.detect(env), which)
        self.out = out  # where an escape code is written (the terminal: sys.__stdout__)
        self.problem = _("notify_nothing") if self.backend == "none" else ""
        log.info("notifications: %s%s", self.backend,
                 f" — {self.problem}" if self.problem else "")

    def notify(self, items):
        """items: [(lane, a post, account or notification)] from the core."""
        for note in notifytext.due(self.app.core, items, self.cfg, self.on_screen,
                                   self.app.core.lane_title):
            self.show(note)

    def on_screen(self, lane):
        return self.app.lane == lane and self.app.screen is self.app.screen_stack[0]

    def test(self):
        """≡ → Debugging: a sample now; what it went through."""
        self.show(notifytext.Note("fedtail", _("notify_test_body"), "home"))
        return self.problem or _("debug_notify_sent", backend=self.backend)

    def show(self, note):
        if self.backend == "none":
            return
        log.info("notify: %s via %s", note.lane, self.backend)
        try:
            if self.backend == "notify-send":
                argv = notifytext.desktop_argv([self.how, "--app-name=FedTail"], note,
                                               float(self.cfg.get("seconds", 0) or 0))
                subprocess.Popen(argv, env=sysenv.child_env(), stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                out = self.out or sys.__stdout__
                out.write(termcaps.osc(self.how, note.title, note.body))
                out.flush()
        except (OSError, ValueError) as e:
            log.warning("notify: %s", e)
            self.app.notify(_("notify_failed", err=e), severity="warning")


__all__ = ["Notifier"]
