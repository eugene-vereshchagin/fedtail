"""A post's text as one Pango layout: what a Gtk.Label with wrapping does, at a quarter
of the cost.

A wrapping Gtk.Label lays its text out several times to answer how wide and how tall it
wants to be (the narrowest it could go, its natural width, the height at a width) — for a
post of a few hundred characters that was ~7 ms on a plain desktop, nine tenths of what a
card cost to lay out, and opening a lane lays out dozens of cards. Here the text is laid
out once per width the lane gives it, and remembered: the height at a width is all a list
of cards asks.

What it keeps of a label: Pango markup (what frontends/pango.py makes of a post's HTML),
links (<a href>: drawn in the link colour, the pointer a hand over them, a click goes to
on_link), the colour and font from the theme's CSS. What it doesn't: selecting text (the
post labels never allowed it), the label's accessible text is set once, not on every
change."""

from __future__ import annotations

import html
import re

from .gi_setup import Gdk, Gtk, Pango

_TAG = re.compile(r"<(/?)a\b([^>]*)>|<[^>]*>|&[^;]+;|[^<&]+", re.S)
_HREF = re.compile(r'href="([^"]*)"')
MIN_W = 120     # px: the narrowest it asks to be (a label's width-chars, roughly)
NAT_W = 480     # px: what it would like (the lane decides the width anyway)


def links_of(markup, color):
    """(markup with <a href> made a coloured <span>, [(start byte, end byte, url)] in the
    text Pango will lay out)."""
    out, links, pos, open_at, url = [], [], 0, None, ""
    for m in _TAG.finditer(markup):
        tok = m.group(0)
        if m.group(2) is not None or (m.group(1) == "/" and tok.startswith("</a")):
            if m.group(1):  # </a>
                if open_at is not None:
                    links.append((open_at, pos, url))
                    open_at = None
                out.append("</span>")
            else:  # <a href="…">
                h = _HREF.search(m.group(2) or "")
                url = html.unescape(h.group(1)) if h else ""
                open_at = pos
                out.append(f'<span foreground="{color}" underline="none">')
            continue
        out.append(tok)
        if tok.startswith("<"):
            continue
        text = html.unescape(tok) if tok.startswith("&") else tok
        pos += len(text.encode("utf-8"))
    return "".join(out), links


class TextBlock(Gtk.Widget):
    """markup: Pango markup with <a href> links; link_color: "#rrggbb";
    on_link(url): a link clicked."""

    def __init__(self, markup, link_color="#3584e4", on_link=None, css=()):
        super().__init__()
        for c in css:
            self.add_css_class(c)
        self.on_link = on_link
        shown, self.links = links_of(markup or "", link_color)
        self.layout = self.create_pango_layout(None)
        self.layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        try:
            self.layout.set_markup(shown, -1)
        except Exception:  # noqa: BLE001 — markup Pango won't take: the text as it is
            self.layout.set_text(re.sub(r"<[^>]*>", "", shown), -1)
        self._width = None
        self._heights = {}  # width → height: lists ask for a few widths over and over
        self._serial = None
        self._over_link = False
        if self.links:
            click = Gtk.GestureClick()
            click.connect("released", self._clicked)
            self.add_controller(click)
            motion = Gtk.EventControllerMotion()
            motion.connect("motion", self._moved)
            motion.connect("leave", lambda *_a: self._hover(False))
            self.add_controller(motion)

    # ---- the layout ----------------------------------------------------------------------
    def text(self):
        return self.layout.get_text()

    def _fresh(self):
        """The theme's font changed (another theme, ui.font_size): lay out anew."""
        serial = self.get_pango_context().get_serial()
        if serial != self._serial:
            self._serial = serial
            self.layout.context_changed()
            self._width = None
            self._heights = {}

    def _at(self, width):
        self._fresh()
        width = max(1, int(width))
        if width != self._width:
            self.layout.set_width(width * Pango.SCALE)
            self._width = width
        return self.layout.get_pixel_size()

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            return MIN_W, NAT_W, -1, -1
        self._fresh()
        width = max(1, int(for_size if for_size > 0 else NAT_W))
        h = self._heights.get(width)
        if h is None:
            h = self._at(width)[1]
            if len(self._heights) > 8:
                self._heights.clear()
            self._heights[width] = h
        return h, h, -1, -1

    def do_snapshot(self, snapshot):
        self._at(self.get_width())
        snapshot.append_layout(self.layout, self.get_color())

    # ---- links ---------------------------------------------------------------------------
    def link_at(self, x, y):
        """The url under (x, y), or None."""
        if not self.links:
            return None
        inside, index, _trailing = self.layout.xy_to_index(int(x * Pango.SCALE),
                                                           int(y * Pango.SCALE))
        if not inside:
            return None
        for start, end, url in self.links:
            if start <= index < end:
                return url
        return None

    def _moved(self, _c, x, y):
        self._hover(self.link_at(x, y) is not None)

    def _hover(self, on):
        if on != self._over_link:
            self._over_link = on
            self.set_cursor(Gdk.Cursor.new_from_name("pointer", None) if on else None)

    def _clicked(self, gesture, n, x, y):
        url = self.link_at(x, y)
        if url and self.on_link is not None and n == 1:
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self.on_link(url)
