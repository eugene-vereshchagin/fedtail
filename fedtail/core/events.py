"""Tiny event bus. Handlers are called in the emitting (worker) thread:
a GUI frontend must hop to its own thread itself."""

import logging
import threading

log = logging.getLogger(__name__)


class Events:
    def __init__(self):
        self._handlers = {}
        self._lock = threading.Lock()

    def on(self, name, handler):
        with self._lock:
            self._handlers.setdefault(name, []).append(handler)

    def off(self, name, handler):
        with self._lock:
            if handler in self._handlers.get(name, []):
                self._handlers[name].remove(handler)

    def emit(self, name, payload=None):
        with self._lock:
            handlers = list(self._handlers.get(name, [])) + list(self._handlers.get("*", []))
        for h in handlers:
            try:
                h(name, payload)
            except Exception:  # a broken handler must not kill the poller
                log.exception("event handler failed for %s", name)
