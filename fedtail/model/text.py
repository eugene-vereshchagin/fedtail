"""Text helpers over the model: HTML to plain text, a one-line snippet, the mentions a
reply starts with, a quote to answer piece by piece. Nothing here knows a protocol."""

import html
import re

_H2T_BR = re.compile(r"<br\s*/?>", re.I)
_H2T_PARA = re.compile(r"</p>\s*<p[^>]*>", re.I)
# other blocks (a quote, a list) are lines of their own too — not glued to the next
_H2T_BLOCK = re.compile(r"</?(p|blockquote|li|ul|ol|div|pre|h[1-6])\b[^>]*>", re.I)
_H2T_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def html_to_text(h):
    """Called for every post Ctrl+F looks through: the patterns are compiled once."""
    if not h:
        return ""
    if "<" not in h:
        return html.unescape(h).strip() if "&" in h else h.strip()
    h = _H2T_BR.sub("\n", h)
    h = _H2T_PARA.sub("\n\n", h)
    h = _H2T_BLOCK.sub("\n", h)
    h = _H2T_TAG.sub("", h)
    return html.unescape(h).strip()


def snippet(post, n=160):
    """The post in a line of at most n characters: its text, else its warning, else
    how many pictures it has."""
    t = _SPACE.sub(" ", html_to_text(post.text))
    if not t and post.warning:
        t = post.warning
    if not t and post.media:
        t = f"[{len(post.media)} × media]"
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def snippet_html(html, n=160):
    """Some HTML (a bio) in a line of at most n characters."""
    t = _SPACE.sub(" ", html_to_text(html))
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def norm_handle(handle):
    return (handle or "").lower().lstrip("@")


def reply_mentions(parent, my_handle):
    """'@author @others ' for the start of a reply: not me, no one twice."""
    me = norm_handle(my_handle)
    seen, out = set(), []
    for h in [parent.author.handle] + [m.handle for m in parent.mentions]:
        k = norm_handle(h)
        if not k or k == me or k in seen:
            continue
        seen.add(k)
        out.append("@" + h)
    return " ".join(out) + " " if out else ""


_LEADING_MENTIONS = re.compile(r"^(?:@[\w.-]+(?:@[\w.-]+)?[\s,]*)+")


def quote_lines(text, prefix="> ", strip_mentions=False):
    """Text to answer piece by piece: every line under `prefix` (Markdown's "> "),
    empty lines kept as a bare ">", the leading @mentions of a whole post dropped
    (strip_mentions) — the reply has its own. Ends in an empty line: without it the
    answer typed next would be read as part of the quote. "" for nothing to quote."""
    text = (text or "").replace("\u2029", "\n").replace("\r\n", "\n").strip()
    if strip_mentions:
        text = _LEADING_MENTIONS.sub("", text).strip()
    if not text:
        return ""
    bare = prefix.rstrip()
    return "\n".join(prefix + line if line.strip() else bare
                     for line in text.split("\n")) + "\n\n"


def join_quote(before, quote):
    """What goes between the text up to the cursor and a quote put in there: nothing at
    the start, a line break after a line of @mentions, an empty line after your own
    words (a Markdown quote needs it to begin). Returns the separator."""
    if not before.strip():
        return ""
    if "\n" not in before.strip() and _LEADING_MENTIONS.fullmatch(before.strip() + " "):
        return "" if before.endswith("\n") else "\n"
    tail = len(before) - len(before.rstrip("\n"))
    return "\n" * max(0, 2 - tail)


# ---- what Ctrl+F looks through -------------------------------------------------------
def fold(s):
    """Case- and ё-insensitive, so «ежик» finds «Ёжик»."""
    return (s or "").casefold().replace("ё", "е")


def haystack(entry, short_id=None):
    """Everything a reader would recognise a post by: text, warning, picture
    descriptions, author (name and @address), who boosted it, its #id."""
    from . import Share
    p = entry.post if isinstance(entry, Share) else entry
    parts = [html_to_text(p.text), p.warning] + [m.alt for m in p.media]
    people = [p.author] + ([entry.by] if isinstance(entry, Share) else [])
    for acc in people:
        parts += [acc.name, "@" + acc.handle]
    if short_id:
        parts.append("#" + short_id)
    return fold("\n".join(x for x in parts if x))


def matches(query, hay):
    """Every word of the query is somewhere in the post, in any order."""
    words = fold(query).split()
    return bool(words) and all(w in hay for w in words)


# ---- shaping a post's HTML -----------------------------------------------------------
_QUOTE_FALLBACK = re.compile(r'<p class="quote-inline">.*?</p>', re.S | re.I)


def without_quote_fallback(content):
    """The "RE: <link>" paragraph servers add for clients that can't show quotes: gone
    when fedtail shows the quote itself."""
    return _QUOTE_FALLBACK.sub("", content or "")


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


def is_bot(account, extra_bots=()):
    """A bot: says so itself, or is one of feed's lanes.extra_bots."""
    return account.bot or norm_handle(account.handle) in {norm_handle(b) for b in extra_bots}
