"""Brings core events and futures into the Qt GUI thread."""

import logging

from PySide6.QtCore import QObject, Signal

from ... import diag
from ..common import results
from ..common.results import EXPECTED  # noqa: F401  (Qt's name for it)

log = logging.getLogger(__name__)


def _gone(e):
    """The widget waiting for this result is already gone."""
    return isinstance(e, RuntimeError) and "already deleted" in str(e)


class Bridge(QObject):
    event = Signal(str, object)          # core events, already in the GUI thread
    raise_requested = Signal()           # another instance asked us to show up
    open_requested = Signal(str)         # …or to open a link (`fedtail open URL`)
    _done = Signal(object, object, object)

    def __init__(self, core):
        super().__init__()
        self.core = core
        self.on_error = None
        self._done.connect(self._finish)
        core.events.on("*", lambda name, payload: self.event.emit(name, payload))

    def call(self, future, ok=None, fail=None):
        """Run ok(result) / fail(message) in the GUI thread when the future is done."""
        future.add_done_callback(lambda f: self._done.emit(f, ok, fail))
        return future

    def _finish(self, future, ok, fail):
        if future.cancelled():
            return
        with diag.busy("result " + getattr(ok or fail, "__qualname__", "?")):
            self._handle(future, ok, fail)

    def _handle(self, future, ok, fail):
        results.handle(future, ok, fail, self.on_error, gone=_gone)

    def _report(self, e):
        log.exception("result handler failed")
        if self.on_error:
            self.on_error(f"{type(e).__name__}: {e}")
