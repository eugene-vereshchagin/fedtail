"""A future's result handed to the window (each bridge brings it into its main loop
first): ok(result) or fail(message), and how a failure is logged — the network or the
server saying no is one line (the request is in the log already, with its timing),
anything else gets its traceback; a bug in a handler is shown, not swallowed."""

from __future__ import annotations

import logging

import requests

from ...protocols.base import ServerError

log = logging.getLogger(__name__)

EXPECTED = (requests.RequestException, ServerError, TimeoutError, ConnectionError)


def handle(future, ok, fail, on_error=None, gone=lambda _e: False):
    """future is done: ok(result), or fail(message) (on_error(message) when no fail
    was given). gone(exc): the handler's widget was already gone — nothing to say."""
    exc = future.exception()
    try:
        if exc is not None:
            if isinstance(exc, EXPECTED):
                # a caller with its own fail handler deals with it, so only say it
                # twice when debugging
                (log.debug if fail else log.warning)(
                    "call failed: %s: %s", type(exc).__name__, exc)
            else:
                log.warning("call failed: %s", exc, exc_info=exc)
            handler = fail or on_error
            if handler:
                handler(str(exc))
        elif ok:
            ok(future.result())
    except Exception as e:  # noqa: BLE001 — a bug in a handler: shown
        if gone(e):
            return
        report(e, on_error)


def report(e, on_error=None):
    log.exception("result handler failed", exc_info=e)
    if on_error:
        on_error(f"{type(e).__name__}: {e}")
