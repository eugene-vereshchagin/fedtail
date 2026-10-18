"""Server HTML → the safe rich-text subset fedtail shows (QLabel in the window, a
page in the web interface). No Qt here."""

import html
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

_INVISIBLE = re.compile(r'<span class="invisible">.*?</span>', re.S)
_ELLIPSIS = re.compile(r'<span class="ellipsis">(.*?)</span>', re.S)
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


# What a post may contain on screen. QLabel runs no scripts (it's not a browser), but
# whatever is not on these lists goes anyway: no forms, tables, headings, fonts,
# pictures from paths, and no links but to the web — a post must not be able to hold
# a link to fedtail's own actions (fedtail:delete/…) or to a local file; links that
# only go somewhere inside (a profile, a tag, a thread) stay.
ALLOWED_TAGS = {"p", "br", "a", "span", "b", "strong", "i", "em", "u", "s", "del",
                "code", "pre", "blockquote", "ul", "ol", "li", "small"}
VOID_TAGS = {"br"}
DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "template", "noscript",
                     "svg", "math", "head", "title", "textarea", "select"}
AS_PARAGRAPH = {"h1", "h2", "h3", "h4", "h5", "h6", "div", "section", "article", "header",
                "footer", "aside", "table", "figure", "figcaption", "details", "summary"}
AS_BREAK = {"tr", "hr", "dt", "dd"}
AS_SPACE = {"td", "th"}
SAFE_SCHEMES = ("http://", "https://", "mailto:", "xmpp:", "gemini://", "magnet:",
                # links.in_app's own: going somewhere inside is fine, doing things is not
                "fedtail:account/", "fedtail:tag/", "fedtail:resolve/", "fedtail:thread/")


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in DROP_WITH_CONTENT:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in AS_PARAGRAPH:  # a heading or a box: text of its own, the plain way
            self.out.append("<p>")
            return
        if tag in AS_BREAK:
            self.out.append("<br>")
            return
        if tag in AS_SPACE:
            self.out.append(" ")
            return
        if tag not in ALLOWED_TAGS:
            return
        if tag == "a":
            href = (dict(attrs).get("href") or "").strip()
            if href.lower().startswith(SAFE_SCHEMES):
                self.out.append(f'<a href="{esc(html.unescape(href))}">')
            else:
                self.out.append("<a>")
            return
        self.out.append(f"<{tag}>")

    def handle_startendtag(self, tag, attrs):
        if self.skip:
            return
        if tag in VOID_TAGS or tag in AS_BREAK:
            self.out.append("<br>")

    def handle_endtag(self, tag):
        if tag in DROP_WITH_CONTENT:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in AS_PARAGRAPH:
            self.out.append("</p>")
        elif tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(esc(data))

    def handle_entityref(self, name):
        if not self.skip:
            self.out.append(esc(html.unescape(f"&{name};")))

    def handle_charref(self, name):
        if not self.skip:
            self.out.append(esc(html.unescape(f"&#{name};")))


def sanitize(h):
    """Rebuild server HTML from the allowed tags only, attributes dropped but a
    web link's href."""
    p = _Sanitizer()
    p.feed(h or "")
    p.close()
    return "".join(p.out)


def esc(s):
    return html.escape(s or "", quote=True)


_STRIKE = re.compile(r"(?<![~\w])~~(?=\S)([^~]+?)(?<=\S)~~(?![~\w])")
_RAW = {"a", "code", "pre"}


def strike_tildes(h):
    """~~text~~ typed in a client with no Markdown, on a server with none (Mastodon):
    struck out, as the writer meant. Not inside links or code; not across tags."""
    if "~~" not in h:
        return h
    out, raw = [], 0
    for part in _TAG.split(h):
        if part.startswith("<"):
            name = part[1:].lstrip("/").split(None, 1)[0].rstrip(">/").lower() if \
                len(part) > 2 else ""
            if name in _RAW and not part.endswith("/>"):
                raw = max(0, raw + (-1 if part.startswith("</") else 1))
            out.append(part)
        elif raw or "~~" not in part:
            out.append(part)
        else:
            out.append(_STRIKE.sub(r"<s>\1</s>", part))
    return "".join(out)


def clean(content, link_color=None, markup=False):
    """markup: ~~text~~ struck out too (feed.text_markup)."""
    h = _SCRIPTY.sub("", content or "")
    h = _INVISIBLE.sub("", h)
    h = _ELLIPSIS.sub(r"\1…", h)
    h = _IMG.sub(lambda m: esc(m.group(1) or ""), h)  # custom emoji → :shortcode:
    h = sanitize(h)
    if markup:
        h = strike_tildes(h)
    h = _fit_text(h)
    style = "text-decoration:none;" + (f"color:{link_color};" if link_color else "")
    return h.replace("<a ", f'<a style="{style}" ')


_TAG_SPLIT = re.compile(r"(<[^>]+>)")
_SHORTCODE = re.compile(r":([A-Za-z0-9_]{2,}):")


def emojify(h, emojis, px, local):
    """:shortcode: in the text (never inside a tag) becomes the server's picture, when
    that picture is already on disk; local(url) -> path or None. Our own <img>, after
    sanitizing, pointing only at our own cache. Returns (html, urls still missing)."""
    table = {e["shortcode"]: e.get("static_url") or e.get("url")
             for e in emojis or () if e.get("shortcode") and (e.get("static_url") or e.get("url"))}
    if not table or ":" not in h:
        return h, []
    missing = []

    def sub(m):
        url = table.get(m.group(1))
        path = local(url) if url else None
        if not path:
            if url:
                missing.append(url)
            return m.group(0)
        src = esc(Path(path).resolve().as_uri())
        return (f'<img src="{src}" width="{px}" height="{px}" align="middle" '
                f'title=":{esc(m.group(1))}:">')
    parts = _TAG_SPLIT.split(h)
    for i in range(0, len(parts), 2):
        parts[i] = _SHORTCODE.sub(sub, parts[i])
    return "".join(parts), missing


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
