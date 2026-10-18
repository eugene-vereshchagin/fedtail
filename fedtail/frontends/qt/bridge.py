"""Brings core events and futures into the Qt GUI thread."""

import logging

import requests
from PySide6.QtCore import QObject, Signal

from ... import diag
from ...core.api import ApiError

log = logging.getLogger(__name__)

# The network or the server said no: one line is the whole story (the request is
# logged by api.py with its timing). Anything else gets its traceback.
EXPECTED = (requests.RequestException, ApiError, TimeoutError, ConnectionError)


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
        exc = future.exception()
        try:
            if exc is not None:
                if isinstance(exc, EXPECTED):
                    # the request is in the log already; a caller with its own fail
                    # handler deals with it, so only say it twice when debugging
                    (log.debug if fail else log.warning)(
                        "call failed: %s: %s", type(exc).__name__, exc)
                else:
                    log.warning("call failed: %s", exc, exc_info=exc)
                handler = fail or self.on_error
                if handler:
                    handler(str(exc))
            elif ok:
                ok(future.result())
        except RuntimeError as e:
            # the widget waiting for this result is already gone
            if "already deleted" in str(e):
                return
            self._report(e)
        except Exception as e:  # a bug in a handler: show it, don't swallow it
            self._report(e)

    def _report(self, e):
        log.exception("result handler failed")
        if self.on_error:
            self.on_error(f"{type(e).__name__}: {e}")
