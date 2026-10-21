"""A lane on screen: its header, the posts as cards in a scrolled list, "Older".

Nothing jumps (docs/DESIGN.md): rows are kept by key and never rebuilt while on screen.
New posts in an oldest-first lane only ever join at the bottom; older ones loaded at
the top push the view down by exactly their height, so what you read stays put. Posts
seen whole while the window is active are marked read; the decision is `seen()`, a
plain function the Qt frontend's rule (qt/feed.py _emit_seen) is going to share.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from ...i18n import _
from ...model import Share, real
from .card import Card, Separator
from .gi_setup import GLib, Gtk

log = logging.getLogger(__name__)

SEEN_DELAY_MS = 400


def seen(top, bottom, vtop, vbottom):
    """A card from top to bottom (in the list's coordinates) is read in a viewport from
    vtop to vbottom when it is on screen whole, or — taller than the screen — when its
    end has come into view."""
    if bottom - top > vbottom - vtop:
        return top < vbottom and bottom <= vbottom
    return top >= vtop and bottom <= vbottom


class LaneView(Gtk.Box):
    def __init__(self, ctx, name, title):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.ctx, self.name = ctx, name
        lane = ctx.view.lane_by_name.get(name)
        self.lazy = bool(getattr(lane, "lazy", False))
        self.newest_first = ctx.cfg["feed"]["order"] == "newest_first"
        self.rows = {}           # key -> Card
        self.order = []          # keys on screen, top to bottom
        self.separator = None    # key of the first unread when the lane opened
        self.positioned = False
        self._seen_timer = 0
        self._compensate = None  # (upper before) when rows went in above the view

        header = Gtk.Box(spacing=8)
        header.add_css_class("ft-lane-header")
        self.title = Gtk.Label(label=ctx.theme.word("lane_title", title), xalign=0)
        self.title.add_css_class("ft-lane-title")
        self.title.set_hexpand(True)
        header.append(self.title)
        self.pill = Gtk.Label()
        self.pill.add_css_class("ft-new-pill")
        self.pill.set_visible(False)
        header.append(self.pill)
        read = Gtk.Button(label=_("mark_all_read"))
        read.add_css_class("flat")
        read.connect("clicked", lambda _b: self.mark_all_read())
        read.set_visible(not self.lazy)
        header.append(read)
        self.append(header)

        self.older = Gtk.Button(label=_("older_down") if self.newest_first else _("older_up"))
        self.older.add_css_class("flat")
        self.older.connect("clicked", lambda _b: self.load_older())

        self.list = Gtk.ListBox()
        self.list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list.add_css_class("ft-feed")
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        column.set_margin_start(8)
        column.set_margin_end(8)
        if not self.newest_first:
            column.append(self.older)
        column.append(self.list)
        if self.newest_first:
            column.append(self.older)
        clamp = Gtk.Box()
        clamp.append(column)
        column.set_hexpand(True)
        column.set_size_request(-1, -1)
        max_width = int(ctx.cfg["ui"].get("max_width") or 0)
        if max_width:
            column.set_halign(Gtk.Align.CENTER)
            column.set_size_request(min(max_width, 4000), -1)

        self.scroll = Gtk.ScrolledWindow()
        self.scroll.add_css_class("ft-view")
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_vexpand(True)
        self.scroll.set_child(clamp)
        self.adj = self.scroll.get_vadjustment()
        self.adj.connect("value-changed", lambda _a: self._schedule_seen())
        self.adj.connect("changed", lambda _a: self._adjusted())
        self.append(self.scroll)

    # ---- filling -------------------------------------------------------------------
    def refresh(self):
        """Bring the rows in step with the lane: new rows go in where they belong, gone
        ones go, the rest only get their unread mark set."""
        view = self.ctx.view
        entries = view.entries(self.name)
        unread = set() if self.lazy else view.unread(entries)
        posts = [e for _, e in entries]
        parents = view.parents(posts)
        short = view.short_ids(posts)
        unknown = [e for e in posts if parents.get(e.id) is None and real(e).reply_to]
        if unknown:
            view.ensure_parents(unknown)
        if self.separator is None and not self.positioned:
            first = next((k for k, e in entries if e.id in unread), None)
            if first is not None and any(e.id not in unread for _, e in entries):
                self.separator = first
        keys = [k for k, _ in entries]
        if self.newest_first:
            keys.reverse()
        by_key = dict(entries)
        for k in list(self.rows):
            if k not in by_key:
                self._remove(k)
        top_key = self._first_visible()
        upper = self.adj.get_upper()
        above = False
        for i, k in enumerate(keys):
            e = by_key[k]
            if k in self.rows:
                self.rows[k].set_unread(e.id in unread)
                continue
            card = Card(self.ctx, k, e, parent=parents.get(e.id), unread=e.id in unread,
                        short_id=short.get(real(e).id))
            pos = self._insert_at(keys, i)
            if self.separator == k:
                sep = Separator(self.ctx.theme.word("separator", _("new_below"),
                                                    n=len(unread)))
                self.list.insert(sep, pos)
                pos += 1
            self.list.insert(card, pos)
            self.rows[k] = card
            self.order.insert(self._order_index(keys, i), k)
            if top_key is not None and self._before(k, top_key):
                above = True
        if above and self.positioned:
            self._compensate = upper
        self._pill(len(unread))
        if not self.positioned and self.get_mapped():
            GLib.idle_add(self._position)

    def _pill(self, n):
        self.pill.set_visible(n > 0)
        if n:
            self.pill.set_text(_("unread_n", n=n))

    def _order_index(self, keys, i):
        """Where keys[i] goes among the rows on screen (in self.order)."""
        before = set(keys[:i])
        return sum(1 for k in self.order if k in before)

    def _insert_at(self, keys, i):
        """The ListBox position for keys[i]: after every row that comes before it."""
        idx = self._order_index(keys, i)
        pos = 0
        child = self.list.get_first_child()
        seen_cards = 0
        while child is not None and seen_cards < idx:
            inner = child.get_child() if isinstance(child, Gtk.ListBoxRow) else child
            pos += 1
            if isinstance(inner, Card):
                seen_cards += 1
            child = child.get_next_sibling()
        return pos

    def _before(self, a, b):
        return self.order.index(a) < self.order.index(b)

    def _remove(self, key):
        card = self.rows.pop(key)
        row = card.get_parent()
        if row is not None:
            self.list.remove(row)
        if key in self.order:
            self.order.remove(key)

    def _adjusted(self):
        """Rows went in above what's being read: move the view down by their height."""
        if self._compensate is None:
            return
        grown = self.adj.get_upper() - self._compensate
        self._compensate = None
        if grown > 0:
            self.adj.set_value(self.adj.get_value() + grown)

    def update_post(self, post):
        for card in self.rows.values():
            if real(card.entry).id == post.id:
                card.update(replace(card.entry, post=post) if isinstance(card.entry, Share)
                            else post)

    # ---- position and reading ------------------------------------------------------
    def _position(self):
        """Opened: the first unread at the top (or the newest end when all is read)."""
        if self.positioned:
            return GLib.SOURCE_REMOVE
        target = next((k for k in self.order if self.rows[k].unread), None)
        if target is not None:
            y = self._y(self.rows[target])
            if y is not None:
                self.adj.set_value(max(0, y - 40))
        elif self.newest_first:
            self.adj.set_value(0)
        else:
            self.adj.set_value(self.adj.get_upper() - self.adj.get_page_size())
        self.positioned = True
        self._schedule_seen()
        return GLib.SOURCE_REMOVE

    def _y(self, widget):
        return y_in(widget, self.list)

    def _first_visible(self):
        top = self.adj.get_value()
        for k in self.order:
            y = self._y(self.rows[k])
            if y is not None and y + self.rows[k].get_height() > top:
                return k
        return None

    def _schedule_seen(self):
        if self._seen_timer or self.lazy:
            return
        self._seen_timer = GLib.timeout_add(SEEN_DELAY_MS, self._mark_seen)

    def _mark_seen(self):
        self._seen_timer = 0
        root = self.get_root()
        if not self.positioned or root is None or not root.is_active() or \
                not self.get_mapped():
            return GLib.SOURCE_REMOVE
        vtop = self.adj.get_value()
        vbot = vtop + self.adj.get_page_size()
        ids = []
        for k in self.order:
            card = self.rows[k]
            if not card.unread:
                continue
            y = self._y(card)
            if y is not None and seen(y, y + card.get_height(), vtop, vbot):
                ids.append(card.entry.id)
                card.set_unread(False)
        if ids:
            self.ctx.view.mark_read(ids)
        return GLib.SOURCE_REMOVE

    def window_activated(self):
        self._schedule_seen()

    def mark_all_read(self):
        self.ctx.view.mark_lane_read(self.name)
        for card in self.rows.values():
            card.set_unread(False)
        self._pill(0)

    def load_older(self):
        self.older.set_sensitive(False)

        def done(n):
            self.older.set_sensitive(True)
            if not n:
                self.older.set_label(_("no_older"))
        self.ctx.bridge.call(self.ctx.view.load_older(self.name), done,
                             lambda err: (self.older.set_sensitive(True),
                                          self.ctx.status(_("error", err=err))))


def y_in(widget, ancestor):
    """widget's top in ancestor's coordinates, or None (not laid out yet)."""
    if hasattr(widget, "compute_point"):  # GTK 4.12+
        from gi.repository import Graphene
        ok, pt = widget.compute_point(ancestor, Graphene.Point().init(0, 0))
        return pt.y if ok else None
    res = widget.translate_coordinates(ancestor, 0, 0)
    return res[1] if res else None
