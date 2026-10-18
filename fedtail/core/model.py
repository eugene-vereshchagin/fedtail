"""Small helpers over Mastodon status/account dicts. No I/O."""

import html
import re

# from most open to most closed
VISIBILITIES = ["public", "unlisted", "private", "direct"]


def real(st):
    """The status itself, or the one it boosts."""
    return st.get("reblog") or st


def html_to_text(h):
    h = re.sub(r"<br\s*/?>", "\n", h or "", flags=re.I)
    h = re.sub(r"</p>\s*<p[^>]*>", "\n\n", h, flags=re.I)
    # other blocks (a quote, a list) are lines of their own too — not glued to the next
    h = re.sub(r"</?(p|blockquote|li|ul|ol|div|pre|h[1-6])\b[^>]*>", "\n", h, flags=re.I)
    h = re.sub(r"<[^>]+>", "", h)
    return html.unescape(h).strip()


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
