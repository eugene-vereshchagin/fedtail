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
