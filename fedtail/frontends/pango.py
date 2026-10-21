"""Post HTML (what richtext.sanitize leaves) as Pango markup, for GTK labels.

A Gtk.Label understands Pango's markup only: <b> <i> <u> <s> <tt> <small> <span> and
<a href>; no paragraphs, line breaks, quotes or lists. So paragraphs become a blank
line, <br> a newline, a quote a "▎ " in front of each of its lines (in italics), a list
"• " or "1. " items, <code>/<pre> monospace. Text is escaped, whitespace collapsed as a
browser would (but kept inside <pre>). Links keep their href: the label hands them to
its "activate-link" handler, which goes through the same openable()/fedtail: rules as
Qt. Nothing here imports GTK, so it is tested on its own.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from .richtext import safe_href, sanitize

QUOTE_MARK = "▎ "
_WS = re.compile(r"[ \t\r\n\f]+")
SIMPLE = {"b": "b", "strong": "b", "i": "i", "em": "i", "u": "u", "s": "s", "del": "s",
          "code": "tt", "small": "small"}


def esc(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        # a stack of blocks: each a list of lines being built; a quote gets its own,
        # prefixed when it closes
        self.out = [[]]
        self.open = []         # Pango tags open now (to close them at a block's end)
        self.pre = 0
        self.lists = []        # ["ul"] or ["ol", n] per open list
        self.owed = []         # blank lines owed outside each open quote
        self.pending_break = 0  # blank lines owed before the next text

    # ---- text --------------------------------------------------------------------
    def _put(self, s):
        if not s:
            return
        buf = self.out[-1]
        if self.pending_break and "".join(buf).strip():
            buf.append("\n" * self.pending_break)
        self.pending_break = 0
        buf.append(s)

    def _block(self, n=2):
        """End of a paragraph-like thing: n newlines before whatever comes next."""
        self.pending_break = max(self.pending_break, n)

    def handle_data(self, data):
        if not self.pre:
            data = _WS.sub(" ", data)
            buf = "".join(self.out[-1])
            if (not buf or buf.endswith(("\n", " "))) or self.pending_break:
                data = data.lstrip(" ")
        self._put(esc(data))

    # ---- tags --------------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "br":
            self.out[-1].append("\n")
            self.pending_break = 0
        elif tag == "p":
            self._block()
        elif tag == "a":
            href = safe_href(a.get("href") or "")
            if href:
                self._put(f'<a href="{esc(href)}">')
                self.open.append("a")
            else:
                self.open.append("")
        elif tag in SIMPLE:
            self._put(f"<{SIMPLE[tag]}>")
            self.open.append(SIMPLE[tag])
        elif tag == "pre":
            self._block()
            self.pre += 1
            self._put("<tt>")
            self.open.append("tt")
        elif tag == "blockquote":
            self._block()
            self.owed.append(self.pending_break)
            self.pending_break = 0
            self.out.append([])
        elif tag in ("ul", "ol"):
            self._block(1 if self.lists else 2)
            self.lists.append(["ul"] if tag == "ul" else ["ol", 0])
        elif tag == "li":
            self._block(1)
            indent = "  " * max(0, len(self.lists) - 1)
            if self.lists and self.lists[-1][0] == "ol":
                self.lists[-1][1] += 1
                mark = f"{self.lists[-1][1]}. "
            else:
                mark = "• "
            self._put(indent + mark)
        # span and anything else sanitize let through: text only

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "p":
            self._block()
        elif tag == "a" or tag in SIMPLE:
            self._close_one()
        elif tag == "pre":
            self._close_one()
            self.pre = max(0, self.pre - 1)
            self._block()
        elif tag == "blockquote" and len(self.out) > 1:
            inner = "".join(self.out.pop()).strip("\n")
            self.pending_break = self.owed.pop() if self.owed else 0
            # one <i> round the whole quote: a tag inside may span its lines
            lines = inner.split("\n")
            self._put("<i>" + "\n".join(QUOTE_MARK + ln if ln.strip() else
                                        QUOTE_MARK.rstrip() for ln in lines) + "</i>")
            self._block()
        elif tag in ("ul", "ol") and self.lists:
            self.lists.pop()
            self._block(1 if self.lists else 2)
        elif tag == "li":
            self._block(1)

    def _close_one(self):
        if self.open:
            t = self.open.pop()
            if t:
                self.out[-1].append(f"</{t}>")

    def result(self):
        while self.open:
            self._close_one()
        while len(self.out) > 1:
            self.handle_endtag("blockquote")
        return "".join(self.out[0]).strip()


def markup(html, sanitized=False):
    """A post's HTML as Pango markup. sanitized: html has been through sanitize()
    (or richtext.clean) already."""
    b = _Builder()
    b.feed(html if sanitized else sanitize(html or ""))
    b.close()
    return re.sub(r"[ \t]+\n", "\n", b.result())  # no spaces left dangling at line ends
