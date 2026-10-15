"""Honest counters. Your server knows only the favourites and boosts that reached
it; the post's own server knows them all. Asked by a flag only: it is a request
to someone else's server, made without your token (and so without your name,
but with your IP address)."""

import re
from urllib.parse import urlparse

from .model import real

_URI_ID = re.compile(r"/statuses/([^/?#]+)/?$")      # Mastodon, GoToSocial, Akkoma uri
_URL_ID = re.compile(r"/@[^/]+/([^/?#]+)/?$")        # Mastodon web url


def origin_api_url(status, own_server):
    """The post's own server API address for it, or None (local, private, unknown)."""
    st = real(status)
    if st.get("visibility") not in ("public", "unlisted"):
        return None
    uri = st.get("uri") or ""
    host = urlparse(uri).hostname
    own = urlparse(own_server if "//" in own_server else "https://" + own_server).hostname
    if not host or host == own:
        return None
    m = _URI_ID.search(urlparse(uri).path) or _URL_ID.search(urlparse(st.get("url") or "").path)
    return f"https://{host}/api/v1/statuses/{m.group(1)}" if m else None


def merge(status, origin):
    """The status with the origin's counters, if the origin answered about the same post."""
    st = real(status)
    if not origin or origin.get("uri") != st.get("uri"):
        return None
    fields = ("replies_count", "favourites_count", "reblogs_count")
    if all(origin.get(f) == st.get(f) for f in fields):
        return None
    honest = dict(st, **{f: max(origin.get(f) or 0, st.get(f) or 0) for f in fields})
    return dict(status, reblog=honest) if status.get("reblog") else honest
