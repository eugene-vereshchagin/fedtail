"""Server HTML → the rich-text subset QLabel understands."""

import html
import re
from datetime import UTC, datetime

_INVISIBLE = re.compile(r'<span class="invisible">.*?</span>', re.S)
_ELLIPSIS = re.compile(r'<span class="ellipsis">(.*?)</span>', re.S)
_ATTRS = re.compile(r'\s(class|rel|target|translate|data-[\w-]+)="[^"]*"')
_IMG = re.compile(r'<img[^>]*?alt="([^"]*)"[^>]*>|<img[^>]*>', re.S)
_SCRIPTY = re.compile(r"<(script|style|iframe)[^>]*>.*?</\1>", re.S | re.I)
_TAG = re.compile(r"(<[^>]*>)")
_LONG_WORD = re.compile(r"\S{28,}")
LINK_TEXT = 40   # a bare URL shown longer than this is shortened, Mastodon-style
ZWSP = "\u200b"  # an invisible place where Qt may wrap a line


def _short_url(text):
    t = re.sub(r"^https?://(www\.)?", "", text)
    return t if len(t) <= LINK_TEXT else t[:LINK_TEXT - 1] + "…"


def _breakable(text):
    """Hashes, keys and the like have no spaces; let them wrap instead of
    running off the card."""
    return _LONG_WORD.sub(lambda m: ZWSP.join(m.group(0)[i:i + 20]
                                            for i in range(0, len(m.group(0)), 20)), text)


def _fit_text(h):
    """Shorten URLs shown as link text, make long words wrappable. Only text
    between tags is touched; hrefs stay whole."""
    out, in_link = [], False
    for part in _TAG.split(h):
        if part.startswith("<"):
            low = part[:3].lower()
            if low.startswith("<a ") or low == "<a>":
                in_link = True
            elif low.startswith("</a"):
                in_link = False
            out.append(part)
            continue
        text = html.unescape(part)
        if in_link and re.match(r"^\s*https?://", text):
            text = _short_url(text.strip())  # short enough now; keep it unbroken
        else:
            text = _breakable(text)
        out.append(esc(text).replace("&#x27;", "'"))
    return "".join(out)


def esc(s):
    return html.escape(s or "", quote=True)


def clean(content, link_color=None):
    h = _SCRIPTY.sub("", content or "")
    h = _INVISIBLE.sub("", h)
    h = _ELLIPSIS.sub(r"\1…", h)
    h = _IMG.sub(lambda m: esc(m.group(1) or ""), h)  # custom emoji → :shortcode:
    h = _ATTRS.sub("", h)
    h = re.sub(r"\sstyle=\"[^\"]*\"", "", h)
    h = _fit_text(h)
    style = "text-decoration:none;" + (f"color:{link_color};" if link_color else "")
    return h.replace("<a ", f'<a style="{style}" ')


def display_name(account):
    return esc(account.get("display_name") or account.get("username") or account.get("acct"))


def when(iso, months):
    """'14 Oct 10:05' this year, '14 Oct 2024' before."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    except (ValueError, AttributeError):
        return ""
    now = datetime.now(UTC).astimezone()
    mon = months[dt.month - 1]
    if dt.year != now.year:
        return f"{dt.day} {mon} {dt.year}"
    return f"{dt.day} {mon} {dt:%H:%M}"


def link(action, arg, label, color=None, bold=False):
    """An in-app link. QLabel ignores stylesheets for links, so style goes inline."""
    style = "text-decoration:none;"
    if color:
        style += f"color:{color};"
    if bold:
        style += "font-weight:700;"
    return f'<a href="fedtail:{action}/{esc(str(arg))}" style="{style}">{label}</a>'
