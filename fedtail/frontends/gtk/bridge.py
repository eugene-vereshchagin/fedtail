"""Brings core events and futures into the GTK main loop (GLib.idle_add — what Qt's
queued signals are to the Qt frontend). Results are handled as in Qt (common/results.py)."""

import logging

from ... import diag
from ..common import results
from .gi_setup import GLib

log = logging.getLogger(__name__)


class Bridge:
    def __init__(self, view):
        """view: core.view.View — events come with model payloads (View.on)."""
        self.view = view
        self.on_error = None      # fn(text): the window's status line
        self.on_event = None      # fn(name, payload), in the main loop
        view.on("*", self._event)

    def _event(self, name, payload):
        GLib.idle_add(self._deliver, name, payload)

    def _deliver(self, name, payload):
        if self.on_event:
            try:
                with diag.busy("event " + name):
                    self.on_event(name, payload)
            except Exception as e:  # a bug in a handler: shown, not swallowed
                self._report(e)
        return GLib.SOURCE_REMOVE

    def call(self, future, ok=None, fail=None):
        """Run ok(result) / fail(message) in the main loop when the future is done."""
        future.add_done_callback(lambda f: GLib.idle_add(self._finish, f, ok, fail))
        return future

    def later(self, fn, *args):
        """fn(*args) in the main loop (from any thread)."""
        GLib.idle_add(lambda: (fn(*args), GLib.SOURCE_REMOVE)[1])

    def _finish(self, future, ok, fail):
        if not future.cancelled():
            with diag.busy("result " + getattr(ok or fail, "__qualname__", "?")):
                self._handle(future, ok, fail)
        return GLib.SOURCE_REMOVE

    def _handle(self, future, ok, fail):
        results.handle(future, ok, fail, self.on_error)

    def _report(self, e):
        log.exception("handler failed")
        if self.on_error:
            self.on_error(f"{type(e).__name__}: {e}")
