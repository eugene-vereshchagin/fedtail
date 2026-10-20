"""Small helpers over Mastodon status/account dicts. No I/O."""

import re

from ..model.text import html_to_text  # noqa: F401 — lives with the model now

# from most open to most closed
VISIBILITIES = ["public", "unlisted", "private", "direct"]


def real(st):
    """The status itself, or the one it boosts."""
    return st.get("reblog") or st


QUOTE_SHOWN = {"accepted"}
_QUOTE_FALLBACK = re.compile(r'<p class="quote-inline">.*?</p>', re.S | re.I)


def quoted(st):
    """The post this one quotes: (state, quoted status or None, its id or None).
    Mastodon 4.5+ gives {"state", "quoted_status"} or, nested deeper, just
    {"state", "quoted_status_id"}; Akkoma and Fedibird put the whole status in
    "quote" (or pleroma.quote). None when it quotes nothing."""
    q = st.get("quote")
    if not q:
        q = (st.get("pleroma") or {}).get("quote")
    if not isinstance(q, dict):
        if st.get("quote_id"):
            return "accepted", None, st["quote_id"]
        return None
    if "account" in q and "content" in q:  # a whole status (Akkoma, Fedibird)
        return "accepted", q, q.get("id")
    inner = q.get("quoted_status")
    qid = (inner or {}).get("id") or q.get("quoted_status_id")
    return q.get("state") or "accepted", inner, qid


def without_quote_fallback(content):
    """Mastodon adds "RE: <link>" for clients that don't show quotes; we do."""
    return _QUOTE_FALLBACK.sub("", content or "")


def id_after(a, b):
    """Is id a newer than id b? Mastodon ids are numbers in text, GoToSocial's are ULIDs
    of one length: both compare as numbers or as text of equal length."""
    if a.isdigit() and b.isdigit():
        return int(a) > int(b)
    if len(a) != len(b):
        return len(a) > len(b)
    return a > b


_WHO = {"everyone": ["public"], "followers": ["author", "followers", "mentioned"],
        "following": ["author", "following", "mentioned"], "mentioned": ["author", "mentioned"],
        "me": ["author"]}


def interaction_policy(post_cfg):
    """GoToSocial's interaction policy for a new post from post.who_can_reply / _boost /
    _like; None when all three are left to the account's settings."""
    out = {}
    for key, field in (("who_can_reply", "can_reply"), ("who_can_boost", "can_reblog"),
                       ("who_can_like", "can_favourite")):
        who = post_cfg.get(key) or ""
        if who in _WHO:
            out[field] = {"always": list(_WHO[who]), "with_approval": []}
    return out or None


def snippet(st, n=160):
    st = real(st)
    t = re.sub(r"\s+", " ", html_to_text(st.get("content", "")))
    if not t and st.get("spoiler_text"):
        t = st["spoiler_text"]
    if not t and st.get("media_attachments"):
        t = f"[{len(st['media_attachments'])} × media]"
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def full_handle(acct, server=""):
    """'@user@server' — the address that works from anywhere. My own server gives its
    people as a bare 'user': my server's name goes after it."""
    from urllib.parse import urlsplit
    acct = (acct or "").strip().lstrip("@")
    if not acct:
        return ""
    if "@" not in acct:
        host = urlsplit(server if "://" in (server or "") else "https://" + (server or ""))
        if host.hostname:
            acct += "@" + host.hostname
    return "@" + acct


def norm_acct(acct):
    return (acct or "").lower().lstrip("@")


def is_bot(account, extra_bots=()):
    if account.get("bot"):
        return True
    return norm_acct(account.get("acct")) in {norm_acct(b) for b in extra_bots}


def is_comment_to_me(st, me_id):
    """A reply to my post or my comment, written by somebody else."""
    return bool(st) and st.get("in_reply_to_account_id") == me_id \
        and st["account"]["id"] != me_id


def narrower(a, b):
    """The more restrictive of two visibilities."""
    ia = VISIBILITIES.index(a) if a in VISIBILITIES else 2
    ib = VISIBILITIES.index(b) if b in VISIBILITIES else 2
    return VISIBILITIES[max(ia, ib)]


def reply_mentions(parent, my_acct):
    """'@author @others ' prefix for a reply: no me, no duplicates."""
    me = norm_acct(my_acct)
    seen, out = set(), []
    accts = [parent["account"]["acct"]] + [m["acct"] for m in parent.get("mentions", [])]
    for acct in accts:
        a = norm_acct(acct)
        if a == me or a in seen:
            continue
        seen.add(a)
        out.append("@" + acct)
    return " ".join(out) + " " if out else ""


# Since when I follow someone: servers don't keep it, so fedtail writes it at the end of
# my private note on that person — a line of its own, readable in any client.
FOLLOWED_RE = re.compile(r"\n*\[fedtail followed (\d{4}-\d{2}-\d{2})\]\s*$")


def note_followed(note):
    """The follow date written in a private note (YYYY-MM-DD), or None."""
    m = FOLLOWED_RE.search(note or "")
    return m.group(1) if m else None


def note_text(note):
    """The note as I wrote it, without fedtail's line."""
    return FOLLOWED_RE.sub("", note or "").rstrip()


def note_with_followed(text, day):
    """My text with fedtail's line at the end (day None: without it)."""
    text = note_text(text)
    if not day:
        return text
    return (text + "\n\n" if text else "") + f"[fedtail followed {day}]"


_PARA = re.compile(r"<p>(.*?)</p>", re.S)
_ANCHOR = re.compile(r"<a\b[^>]*>.*?</a>", re.S)


def collapse_tag_stuffing(content, keep=3, full=False):
    """A paragraph of nothing but hashtags (more than keep): in a lane the first few and
    "… +N", small (feed.collapse_tags); in a thread (full) all of them, small. Tags
    inside the text are left alone."""
    def one(m):
        inner = m.group(1)
        words = html_to_text(inner).split()
        if len(words) <= keep or not all(w.startswith("#") for w in words):
            return m.group(0)
        tags = _ANCHOR.findall(inner)
        if len(tags) != len(words):
            return m.group(0)  # some written without a link: not touched
        if full:
            return f"<p><small>{' '.join(tags)}</small></p>"
        return f"<p><small>{' '.join(tags[:keep])} … +{len(tags) - keep}</small></p>"
    return _PARA.sub(one, content or "")


_CHAIN = re.compile(r"(?m)^[ \t]*---[ \t]*$")


def chain_parts(text):
    """A post written as a chain: parts split by a line of just "---" (post.chain)."""
    return [p.strip() for p in _CHAIN.split(text or "") if p.strip()]


LONG_TYPES = ("Article", "Page", "Event", "Note", "Question", "Video")


def long_form_of(obj):
    """The whole of an ActivityPub object as its server keeps it (an Article, a Page, an
    Event): {"type", "name", "summary", "content", "url", "start", "end", "location"},
    or None when it isn't one. Your server may show only a title and a link of it."""
    if not isinstance(obj, dict):
        return None
    if obj.get("type") in ("Create", "Update") and isinstance(obj.get("object"), dict):
        obj = obj["object"]
    kind = obj.get("type")
    if isinstance(kind, list):
        kind = next((k for k in kind if k in LONG_TYPES), kind[0] if kind else None)
    if kind not in LONG_TYPES:
        return None

    def text(key):
        v = obj.get(key)
        if not v and isinstance(obj.get(key + "Map"), dict):
            v = next(iter(obj[key + "Map"].values()), "")
        return v if isinstance(v, str) else ""

    url = obj.get("url")
    if isinstance(url, list):
        url = next((u.get("href") if isinstance(u, dict) else u for u in url
                    if (u.get("mediaType", "text/html") if isinstance(u, dict) else True)
                    == "text/html"), None) or (url[0] if url else None)
    if isinstance(url, dict):
        url = url.get("href")
    place = obj.get("location")
    if isinstance(place, list):
        place = place[0] if place else None
    where = ""
    if isinstance(place, dict):
        addr = place.get("address")
        if isinstance(addr, dict):
            addr = ", ".join(str(addr[k]) for k in ("streetAddress", "postalCode",
                                                    "addressLocality", "addressCountry")
                             if addr.get(k))
        where = ", ".join(x for x in (place.get("name"), addr) if isinstance(x, str) and x)
    elif isinstance(place, str):
        where = place
    return {"type": kind, "name": text("name"), "summary": text("summary"),
            "content": text("content"), "url": url or obj.get("id") or "",
            "start": obj.get("startTime") or "", "end": obj.get("endTime") or "",
            "location": where}


def send_key(me_id, text, reply_to, visibility, spoiler):
    """The Idempotency-Key of a post: the same words to the same place give the same key,
    so sending them again after a lost answer gives back the post already made (Mastodon
    keeps keys for an hour) rather than a second one. Pictures aren't part of it: they
    are uploaded anew, with new ids, on every try."""
    import hashlib
    raw = "\x1f".join(str(x or "") for x in (me_id, reply_to, visibility, spoiler, text))
    return "fedtail-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


_WORD = re.compile(r"\w{3,}")


def looks_sent(status, text, reply_to, since, slack_s=120):
    """Is this (one of my latest posts) the one I just tried to send: the same parent,
    made since then (give or take the clocks), with the words of the text? The server
    turns markdown and mentions into HTML, so words are compared, not the text."""
    from datetime import datetime
    st = status or {}
    if st.get("reblog") or (st.get("in_reply_to_id") or None) != (reply_to or None):
        return False
    try:
        made = datetime.fromisoformat(st.get("created_at", "").replace("Z", "+00:00"))
    except ValueError:
        return False
    if made.timestamp() < since - slack_s:
        return False
    fold = lambda s: (s or "").casefold().replace("ё", "е")  # noqa: E731
    hay = fold(html_to_text(st.get("content", "")))
    words = [w for w in _WORD.findall(fold(re.sub(r"(@\S+|https?://\S+)", " ", text)))]
    if not words:
        return fold(text).strip() in hay or not hay.strip()
    return sum(w in hay for w in words) >= max(1, round(len(words) * 0.8))
