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
    # every kind of line break a toolkit hands over is a line: Qt's selected text breaks
    # a <br> with U+2028, and only the first line of each paragraph got its ">" — the
    # rest went as plain text, out of the quote (31.10)
    text = re.sub(r"\r\n|[\r\u2028\u2029\x0b\x85]", "\n", text or "").strip()
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
# each server's way of it: Mastodon's paragraph, Misskey's and Sharkey's span (after line
# breaks, inside the last paragraph), Mitra's and others' plain last paragraph "RE: <a>"
_QUOTE_FALLBACK = (
    re.compile(r'<p class="quote-inline">.*?</p>', re.S | re.I),
    re.compile(r'(?:<br\s*/?>\s*)*<span class="quote-inline">.*?</span>', re.S | re.I),
    re.compile(r'<p>\s*RE:\s*<a\b[^>]*>.*?</a>\s*</p>\s*$', re.S | re.I),
)


def without_quote_fallback(content):
    """The "RE: <link>" line servers add for clients that can't show quotes: gone when
    fedtail shows the quote itself — else the quote is said twice."""
    content = content or ""
    for pattern in _QUOTE_FALLBACK:
        content = pattern.sub("", content)
    return content.replace("<p></p>", "")


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


_BLOCK_PART = re.compile(r"(<(p|blockquote|pre|ul|ol|h[1-6])\b[^>]*>.*?</\2>)", re.S | re.I)


def fold_long(content, limit):
    """A long post's beginning (feed.fold_chars): None when its text has at most limit
    characters (or limit is 0); else (the HTML of its first paragraphs — about half of
    limit's characters, whole paragraphs or lines where they fit, the first cut at a word
    otherwise — and how many characters the whole text has)."""
    total = len(html_to_text(content))
    if limit <= 0 or total <= limit:
        return None
    keep = max(1, limit // 2)
    pieces = [x for x in _BLOCK_PART.split(content or "") if x and x.strip()
              and not re.fullmatch(r"p|blockquote|pre|ul|ol|h[1-6]", x, re.I)]
    out, got = [], 0
    for part in pieces:
        n = len(html_to_text(part))
        if got + n > keep:
            break
        out.append(part)
        got += n
    if not out:  # the first paragraph alone is longer: its lines, or its words
        first = pieces[0] if pieces else ""
        lines = _H2T_BR.split(first)
        for line in lines:
            n = len(html_to_text(line)) + 1  # and its line break
            if got + n > keep:
                break
            out.append(line)
            got += n
        if out:
            shown = "<br>".join(out)
            if not shown.lstrip().lower().startswith("<p"):
                shown = "<p>" + shown
            return shown + ("" if shown.rstrip().lower().endswith("</p>") else "</p>"), total
        words = html_to_text(first)[:keep].rsplit(" ", 1)[0].rstrip(" ,.;:—-")
        return f"<p>{html.escape(words)}…</p>", total
    return "".join(out), total


# a file attached that is no picture, video or sound (servers that take any file: Akkoma,
# Misskey, GoToSocial…) — these are text, read in fedtail itself
TEXT_FILE_EXT = (".txt", ".md", ".markdown", ".log", ".csv", ".tsv", ".json", ".xml",
                 ".yaml", ".yml", ".ini", ".conf", ".toml", ".srt", ".vtt", ".rst", ".org",
                 ".tex", ".diff", ".patch")


def attachment_name(m):
    """A file attachment's name, from its address ("notes.txt"); "" — none there."""
    from urllib.parse import unquote, urlsplit
    path = urlsplit(m.url or m.remote_url or "").path
    return unquote(path.rsplit("/", 1)[-1])


def is_text_attachment(m):
    """An attachment of no known kind (Media.kind "unknown") whose name says text."""
    return m.kind == "unknown" and attachment_name(m).lower().endswith(TEXT_FILE_EXT)


def is_bot(account, extra_bots=()):
    """A bot: says so itself, or is one of feed's lanes.extra_bots."""
    return account.bot or norm_handle(account.handle) in {norm_handle(b) for b in extra_bots}


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


_CHAIN = re.compile(r"(?m)^[ \t]*---[ \t]*$")


def chain_parts(text):
    """A post written as a chain: parts split by a line of just "---" (post.chain)."""
    return [p.strip() for p in _CHAIN.split(text or "") if p.strip()]
