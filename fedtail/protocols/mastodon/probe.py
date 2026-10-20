"""What my server can do, asked of it: ≡ → Server info → "Check what it can do".

Each check is a harmless GET with limit=1 (nothing is changed on the server); what
can't be asked without changing something is told from what the server says it runs.
The answers also tell the core which features to offer (Core.unsupported), and the last
round is kept, so the dialog shows it at once next time.

The paths are Mastodon's API (GoToSocial, Akkoma and others speak it).
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from .api import ApiError

log = logging.getLogger(__name__)

UNSUPPORTED = (404, 405, 410, 501)
TIMEOUT = 15
KV = "server_probe"

# (key — also the i18n word probe_<key>, the path, params, the core's feature name or "")
CHECKS = [
    ("home", "/api/v1/timelines/home", {}, ""),
    ("local", "/api/v1/timelines/public", {"local": "true"}, ""),
    ("federated", "/api/v1/timelines/public", {}, ""),
    ("bookmarks", "/api/v1/bookmarks", {}, ""),
    ("lists", "/api/v1/lists", None, ""),
    ("filters", "/api/v2/filters", None, ""),
    ("followed_tags", "/api/v1/followed_tags", {}, ""),
    ("featured_tags", "/api/v1/featured_tags", None, "featured_tags"),
    ("endorse", "/api/v1/endorsements", {}, "endorse"),
    ("conversations", "/api/v1/conversations", {}, "conversations"),
    ("markers", "/api/v1/markers", {"timeline[]": "home"}, ""),
    ("scheduled", "/api/v1/scheduled_statuses", {}, ""),
    ("announcements", "/api/v1/announcements", None, ""),
    ("preferences", "/api/v1/preferences", None, "preferences"),
    ("domain_blocks", "/api/v1/domain_blocks", {}, "domain_blocks"),
    ("directory", "/api/v1/directory", {}, "directory"),
    ("suggestions", "/api/v2/suggestions", {}, "suggestions"),
    ("trends_tags", "/api/v1/trends/tags", {}, "trends_tags"),
    ("trends_statuses", "/api/v1/trends/statuses", {}, "trends_statuses"),
    ("trends_links", "/api/v1/trends/links", {}, "trends_links"),
    ("grouped", "/api/v2/notifications", {}, ""),
    ("notification_policy", "/api/v2/notifications/policy", None, "notification_policy"),
    ("interactions", "/api/v1/interaction_requests", {}, "interactions"),
]


def _ask(api, key, path, params):
    """One check: ("yes" | "no" | "error", detail)."""
    if params is not None:
        params = dict(params, limit=1)
    t = time.monotonic()
    try:
        api.get(path, params=params, timeout=TIMEOUT)
        return "yes", ""
    except ApiError as e:
        if e.status in UNSUPPORTED:
            return "no", f"HTTP {e.status}"
        if e.status in (401, 403):  # there, but not for me (off on the server, scopes)
            return "closed", f"HTTP {e.status}"
        return "error", f"HTTP {e.status}"
    except Exception as e:  # noqa: BLE001 — a timeout, no network: said, not raised
        log.debug("probe %s: %s after %.1f s", key, e.__class__.__name__,
                  time.monotonic() - t)
        return "error", e.__class__.__name__


def known(caps):
    """What the server's own description tells, without asking: [(key, state, detail)]."""
    sw = (caps.software or "").lower()
    gts = sw == "gotosocial"
    out = [
        ("markdown", "yes" if caps.markdown else "no", ""),
        ("translation", "yes" if caps.translation else "no", ""),
        ("streaming", "yes" if caps.streaming else "no", ""),
        ("max_characters", "info", str(caps.max_characters)),
        ("max_media", "info", str(caps.max_media)),
        ("max_poll_options", "info", str(caps.max_poll_options)),
        # what can't be asked without changing something
        ("dismiss_one", "no" if gts else "yes", "known"),
        ("mute_thread", "self" if gts else "yes", "known"),
    ]
    return out


def run(api, caps, workers=6):
    """Every check, a few at a time: {"checked": unix time, "software", "version",
    "items": [[key, state, detail]]} — states: yes, no, closed (there, but not open to
    me), error (no clear answer), info (a number), self (fedtail does it itself)."""
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="probe") as pool:
        futs = [(key, pool.submit(_ask, api, key, path, params))
                for key, path, params, _feat in CHECKS]
        asked = [(key, *f.result()) for key, f in futs]
    items = [list(x) for x in asked + known(caps)]
    log.info("probe: %s", " ".join(f"{k}={s}" for k, s, _d in items if s != "info"))
    return {"checked": time.time(), "software": caps.software, "version": caps.version,
            "items": items}


def features(result):
    """{core feature name: True (there) / False (not)} from a round's answers."""
    feat = {key: name for key, _p, _q, name in CHECKS if name}
    out = {}
    for key, state, _d in result.get("items") or ():
        if key in feat and state in ("yes", "no"):
            out[feat[key]] = state == "yes"
    return out
