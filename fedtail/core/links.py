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

_A = re.compile(r'<a\s([^>]*?)href="([^"]+)"([^>]*)>(.*?)</a>', re.I | re.S)
_TAG_PATH = re.compile(r"/tags?/([^/?#]+)/?$", re.I)
_TAG_QUERY = re.compile(r"(?:^|&)tag=([^&#]+)", re.I)  # Friendica: /search?tag=x
_HASH_TEXT = re.compile(r"^\s*#\s*([^\s#<]+)\s*$")
_MARKUP = re.compile(r"<[^>]+>")
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


def _tag_of(href):
    """The tag a tag page's address names (Mastodon, GoToSocial, Misskey: /tags/x;
    Pleroma, Akkoma: /tag/x; Friendica: ?tag=x), or None."""
    try:
        u = urlparse(href)
    except ValueError:
        return None
    m = _TAG_PATH.search(u.path or "") or _TAG_QUERY.search(u.query or "")
    return unquote(m.group(1)) if m else None


def in_app(html, status=None, mentions=None, tags=None):
    """Rewrite hrefs of mentions, hashtags and fediverse-looking links. mentions:
    {profile url: account id} instead of a status's own (a model Post's); tags: the
    post's hashtags (names) instead of its own.

    A hashtag is known by any of: the post's own list of tags, rel="tag", the class
    "hashtag" (or "mention" on a tag page's address), or its words being "#name" with
    an address of a tag page — every server marks them its own way, and one not
    recognised went to that server's web page asking to log in (29.10)."""
    st = real(status) if status else {}
    if mentions is not None:
        mentions = {u.rstrip("/"): i for u, i in mentions.items()}
    else:
        mentions = {}
        for m in st.get("mentions") or []:
            for key in ("url", "uri"):
                if m.get(key):
                    mentions[m[key].rstrip("/")] = m["id"]
    if tags is None:
        tags = [t.get("name") for t in st.get("tags") or () if isinstance(t, dict)]
    known = {str(t).lower() for t in tags if t}

    def fix(match):
        before, href, after, inner = match.groups()
        attrs = (before + after).lower()
        target = href
        tag = _tag_of(href)
        said = _HASH_TEXT.match(_MARKUP.sub("", inner))
        said = unquote(said.group(1)) if said else None
        if href.rstrip("/") in mentions:
            target = f"fedtail:account/{mentions[href.rstrip('/')]}"
        elif tag and ("hashtag" in attrs or "mention" in attrs or 'rel="tag"' in attrs
                      or tag.lower() in known or (said and said.lower() == tag.lower())):
            target = f"fedtail:tag/{quote(tag, safe='')}"
        elif said and (said.lower() in known or 'rel="tag"' in attrs
                       or "hashtag" in attrs):
            target = f"fedtail:tag/{quote(said, safe='')}"  # its address says nothing
        elif href.startswith(("http://", "https://")) and ("mention" in attrs or
                                                            looks_fediverse(href)):
            target = f"fedtail:resolve/{quote(href, safe='')}"
        if target == href:
            return match.group(0)
        # keep the real address as a tooltip-able title
        return f'<a {before}href="{target}" title="{href}"{after}>{inner}</a>'
    return _A.sub(fix, html or "")
