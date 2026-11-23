"""A connect that failed, as every interface says it and does about it: a token the
server no longer takes — log in anew; anything else (a server slow to answer, no network)
— said, and tried again in a while. The phone showed "the core didn't start" for one slow
answer and stayed there (23.11); the windows tried again in 20 s — server.retry_seconds
now."""

from __future__ import annotations

from ...i18n import _

AGAIN_SECONDS = 20


def trouble(err, cfg=None):
    """What a failed Core.connect() means. err: the exception or its text; cfg: the
    config (server.retry_seconds — how long till the next try; without it AGAIN_SECONDS).

    Returns:
        {"relogin": True, "text": …} — the token is refused (Core.token_refused asked
        again and again): the login from scratch; or {"relogin": False, "text": …,
        "again": seconds} — said, and connected again after that many seconds.
    """
    err = str(err)
    if "HTTP 401" in err:
        return {"relogin": True, "text": _("auth_failed"), "again": 0}
    again = ((cfg or {}).get("net") or {}).get("retry_seconds", AGAIN_SECONDS)
    # (the config's check keeps it at 5 s and more: core/config.py MINIMUM)
    return {"relogin": False, "text": _("server_down", err=err),
            "again": again or AGAIN_SECONDS}
