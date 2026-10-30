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


def rate_text(payload):
    """The server asks to wait (the "rate_limited" event): the line for the status bar,
    with when it allows again."""
    import time

    from ...i18n import _
    until = (payload or {}).get("until") if isinstance(payload, dict) else None
    when = time.strftime("%H:%M", time.localtime(until or time.time()))
    return _("rate_limited", until=when)


def refresh_text(result):
    """How a Refresh went (Core.refresh_by_hand, the "refreshed" event), for the status
    bar: "Updated: 3 new" / "Updated: nothing new" / "Not updated: …" / "The server asks
    to wait till 14:20"."""
    import time

    from ...i18n import _
    r = result if isinstance(result, dict) else {}
    if r.get("wait_until"):
        return _("refreshed_wait",
                 until=time.strftime("%H:%M", time.localtime(r["wait_until"])))
    if r.get("error"):
        return _("refreshed_failed", why=r["error"])
    n = int(r.get("new") or 0)
    return _("refreshed_new", n=n) if n else _("refreshed_none")
