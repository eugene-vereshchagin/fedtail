"""A network failure in words a person can act on: "no such server name" (a typo in the
address, or no DNS), "refused", "no answer in time", "its certificate is wrong" — instead
of the exception's class name ("ConnectionError"). Shared by whoever reaches a server
that isn't the fediverse account's own (the sync server first; see core/sync/backends.py).

    words(e, "fedsync.example.org")   # 'cannot find the server "fedsync.example.org" …'
"""

from __future__ import annotations

import requests

from ..i18n import _

# what the resolver says, as urllib3 / the OS put it (Linux, macOS, Windows)
_NO_NAME = ("NameResolutionError", "Name or service not known", "nodename nor servname",
            "getaddrinfo failed", "Temporary failure in name resolution",
            "No address associated with hostname", "Failed to resolve")
_REFUSED = ("Connection refused", "ConnectionRefusedError", "actively refused")


def kind(exc):
    """"no_name", "refused", "timeout", "tls", "down" (any other way of not getting
    through) — or "" when it isn't a network failure at all."""
    if isinstance(exc, requests.exceptions.SSLError):
        return "tls"
    if isinstance(exc, requests.Timeout):
        return "timeout"
    if isinstance(exc, (requests.ConnectionError, ConnectionError, OSError)):
        text = _chain_text(exc)
        if any(w in text for w in _NO_NAME):
            return "no_name"
        if any(w in text for w in _REFUSED):
            return "refused"
        if "timed out" in text.lower():
            return "timeout"
        return "down"
    return ""


def words(exc, host):
    """The failure for a person: what happened with `host`, and what to check."""
    k = kind(exc) or "down"
    return _("net_" + k, host=host)


def _chain_text(exc):
    """The exception and everything it was raised from, as text: requests wraps
    urllib3's error, which wraps the socket's."""
    parts, seen = [], set()
    e = exc
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        parts.append(f"{e.__class__.__name__}: {e}")
        e = e.__cause__ or e.__context__
    return " | ".join(parts)
