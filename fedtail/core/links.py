"""Links in a post that should stay inside fedtail.

Servers render @mentions and #hashtags as ordinary web links (to the person's
or the tag's page on some server). fedtail turns them into in-app links:

    @mention of a known account  -> fedtail:account/<id>      (a profile tab)
    #hashtag                     -> fedtail:tag/<name>        (a tag timeline tab)
    a link that looks like a fediverse profile or post
                                 -> fedtail:resolve/<quoted url>
                                    (looked up through your own server; the
                                     browser only if that finds nothing)

Everything else stays a web link. No Qt here: tested on its own.
"""

import re
from urllib.parse import quote, unquote, urlparse

from .model import real

_A = re.compile(r'<a\s([^>]*?)href="([^"]+)"([^>]*)>', re.I | re.S)
_TAG_PATH = re.compile(r"/tags?/([^/?#]+)/?$", re.I)
# shapes of profile and post addresses on Mastodon, GoToSocial, Akkoma/Pleroma, Misskey
_FEDI_PATHS = [
    re.compile(p) for p in (
        r"^/@[\w.\-]+(@[\w.\-]+)?/?$",                 # /@user
        r"^/@[\w.\-]+/(statuses/)?[\w\-]+/?$",         # /@user/123, /@user/statuses/ULID
        r"^/users/[\w.\-]+/?$",                        # /users/user
        r"^/users/[\w.\-]+/statuses/[\w\-]+/?$",       # /users/user/statuses/123
        r"^/notice/[\w\-]+/?$",                        # Pleroma/Akkoma
        r"^/objects/[\w\-]+/?$",                       # Akkoma
        r"^/notes/[\w\-]+/?$",                         # Misskey
    )
]


def looks_fediverse(url):
    try:
        u = urlparse(url)
    except ValueError:
        return False
    return u.scheme in ("http", "https") and any(p.match(u.path) for p in _FEDI_PATHS)


def in_app(html, status=None):
    """Rewrite hrefs of mentions, hashtags and fediverse-looking links."""
    st = real(status) if status else {}
    mentions = {}
    for m in st.get("mentions") or []:
        for key in ("url", "uri"):
            if m.get(key):
                mentions[m[key].rstrip("/")] = m["id"]

    def fix(match):
        before, href, after = match.groups()
        attrs = (before + after).lower()
        target = href
        if href.rstrip("/") in mentions:
            target = f"fedtail:account/{mentions[href.rstrip('/')]}"
        elif "hashtag" in attrs or (_TAG_PATH.search(urlparse(href).path or "") and
                                     "mention" in attrs):
            tag = _TAG_PATH.search(urlparse(href).path or "")
            if tag:
                target = f"fedtail:tag/{quote(unquote(tag.group(1)), safe='')}"
        elif href.startswith(("http://", "https://")) and ("mention" in attrs or
                                                            looks_fediverse(href)):
            target = f"fedtail:resolve/{quote(href, safe='')}"
        if target == href:
            return match.group(0)
        # keep the real address as a tooltip-able title
        return f'<a {before}href="{target}" title="{href}"{after}>'
    return _A.sub(fix, html or "")
