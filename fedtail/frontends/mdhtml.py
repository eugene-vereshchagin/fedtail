"""The help's Markdown as HTML, for the web page (the windows have their own: Qt's
setMarkdown, GTK's pango.markdown; the terminal has Textual's Markdown widget). No
toolkit, no library: the help is ours and uses a small part of Markdown — headings,
paragraphs, lists, tables, code, quotes, links, **bold**, *italic*, `code`.

Everything taken from the text is escaped; links are only what ``href(link)`` gives
(the help's own pages as fedtail:help/…, the web as https:). Headings get the anchors
helpdocs.slug gives, so a link to "#section" lands.
"""

from __future__ import annotations

import re
from html import escape

from .helpdocs import slug

_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITAL = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")
_SAFE = re.compile(r"^(https?:|mailto:|fedtail:|#)", re.I)


def inline(text, href):
    """One line's inline marks: code first (nothing inside it is markup), then links,
    bold and italic. text is raw; the result is HTML."""
    out, pos = [], 0
    for m in _CODE.finditer(text):
        out.append(_marks(text[pos:m.start()], href))
        out.append("<code>" + escape(m.group(1)) + "</code>")
        pos = m.end()
    out.append(_marks(text[pos:], href))
    return "".join(out)


def _marks(text, href):
    out, pos = [], 0
    for m in _LINK.finditer(text):
        out.append(_emph(escape(text[pos:m.start()])))
        target = href(m.group(2)) if href else m.group(2)
        label = _emph(escape(m.group(1)))
        if target and _SAFE.match(target):
            out.append(f'<a href="{escape(target, quote=True)}">{label}</a>')
        else:
            out.append(label)
        pos = m.end()
    out.append(_emph(escape(text[pos:])))
    return "".join(out)


def _emph(html):
    html = _BOLD.sub(r"<b>\1</b>", html)
    return _ITAL.sub(r"<i>\1</i>", html)


def _cells(line):
    line = line.strip().strip("|")
    return [c.strip() for c in line.split("|")]


def markdown_html(md, href=None):
    """The page as HTML. href(link) → where a link goes (None: as written)."""
    lines = md.replace("\r\n", "\n").split("\n")
    out, para, i = [], [], 0

    def flush():
        if para:
            out.append("<p>" + inline(" ".join(para), href) + "</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith("```"):
            flush()
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            out.append("<pre><code>" + escape("\n".join(code)) + "</code></pre>")
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush()
            n = len(m.group(1))
            out.append(f'<h{n} id="{escape(slug(m.group(2)), quote=True)}">'
                       f"{inline(m.group(2), href)}</h{n}>")
            i += 1
            continue
        if s.startswith("|") and i + 1 < len(lines) and \
                re.match(r"^\|?\s*:?-{2,}", lines[i + 1].strip()):
            flush()
            head = _cells(s)
            rows = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            t = ["<table><thead><tr>" + "".join(f"<th>{inline(c, href)}</th>" for c in head)
                 + "</tr></thead><tbody>"]
            for r in rows:
                t.append("<tr>" + "".join(f"<td>{inline(c, href)}</td>" for c in r) + "</tr>")
            out.append("".join(t) + "</tbody></table>")
            continue
        if re.match(r"^([-*+]|\d+\.)\s+", s):
            flush()
            ordered = bool(re.match(r"^\d+\.", s))
            items = []
            while i < len(lines) and re.match(r"^\s*([-*+]|\d+\.)\s+", lines[i]):
                item = re.sub(r"^\s*([-*+]|\d+\.)\s+", "", lines[i])
                i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip() \
                        and not re.match(r"^\s*([-*+]|\d+\.)\s+", lines[i]):
                    item += " " + lines[i].strip()
                    i += 1
                items.append("<li>" + inline(item, href) + "</li>")
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue
        if s.startswith(">"):
            flush()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append("<blockquote>" + inline(" ".join(quote), href) + "</blockquote>")
            continue
        if not s:
            flush()
        elif not s.startswith("<"):  # the include markers and other HTML comments: gone
            para.append(s)
        i += 1
    flush()
    return "\n".join(out)
