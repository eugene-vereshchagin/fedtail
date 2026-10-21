"""A lane on screen: its header, the posts as cards in a scrolled list, "Older".

A lane may hold thousands of posts; a GTK card costs a few milliseconds to build and
lay out, so only a window of them is on screen (as qt/feed.py does): WINDOW cards
around where reading starts, built in small batches between frames so the window never
stops answering, more joining as the view nears an end, the far end trimmed past
MAX_ROWS.

Nothing jumps (docs/DESIGN.md): rows are kept by key and never rebuilt while on screen;
when rows go in or out above what is being read, the view moves by exactly the height
they added or took away. Posts seen whole while the window is active are marked read;
the decision is `seen()`, a plain function the Qt rule (qt/feed.py _emit_seen) is
going to share.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace

from ... import diag
from ...i18n import _
from ...model import Share, real
from .card import Card, Separator
from .gi_setup import GLib, Gtk

log = logging.getLogger(__name__)

SEEN_DELAY_MS = 400
WINDOW = 40         # cards built when a lane opens: a few above where reading starts
BACK = 8            # …of them above it
STEP = 20           # cards added when the view nears an end
MAX_ROWS = 240      # more than this on screen: the far end goes
BATCH_MS = 25       # building cards for at most this long at a time, then a frame
HOLD_MS = 250       # the view held still this long after rows changed above it


def seen(top, bottom, vtop, vbottom):
    """A card from top to bottom (in the list's coordinates) is read in a viewport from
    vtop to vbottom when it is on screen whole, or — taller than the screen — when its
    end has come into view."""
    if bottom - top > vbottom - vtop:
        return top < vbottom and bottom <= vbottom
    return top >= vtop and bottom <= vbottom


def window_around(n, anchor, size=WINDOW, back=BACK):
    """[lo, hi) of n keys to show first: `back` above anchor and the rest below it,
    shifted to fit."""
    if n <= size:
        return 0, n
    lo = max(0, anchor - back)
    hi = min(n, lo + size)
    return max(0, hi - size), hi


class LaneView(Gtk.Box):
    def __init__(self, ctx, name, title):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.ctx, self.name = ctx, name
        lane = ctx.view.lane_by_name.get(name)
        self.lazy = bool(getattr(lane, "lazy", False))
        self.newest_first = ctx.cfg["feed"]["order"] == "newest_first"
        self.keys = []           # every key of the lane, top to bottom
        self.index = {}          # key -> its place in self.keys
        self.entries = {}        # key -> Post | Share
        self.unread = set()      # unread post ids
        self.rows = {}           # key -> Card on screen
        self.order = []          # keys on screen, top to bottom: a run of self.keys
        self.separator = None    # key of the first unread when the lane opened
        self.positioned = False
        self.dirty = True        # the lane changed while not on screen
        self.stopped = False     # the window closed: no more work queued
        self._queue = []         # (side, [keys]) waiting to be built: side "end" | "start"
        self._building = 0
        self._seen_timer = 0
        # while rows go in or out above what's being read: the height of the content
        # last seen, and until when to hold the view still (see _hold)
        self._held_upper = None
        self._hold_timer = 0
        self._anchor = None      # (key, its offset from the top of the view) while held
        self._ticking = 0

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
        self.older.set_visible(False)  # only once the oldest stored post is on screen

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
        column.set_hexpand(True)
        max_width = int(ctx.cfg["ui"].get("max_width") or 0)
        if max_width:
            column.set_halign(Gtk.Align.CENTER)
            column.set_size_request(min(max_width, 4000), -1)

        self.scroll = Gtk.ScrolledWindow()
        self.scroll.add_css_class("ft-view")
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_vexpand(True)
        self.scroll.set_child(column)
        viewport = self.scroll.get_child()
        if isinstance(viewport, Gtk.Viewport):
            # the view is ours to place (never jump): a focused button in a card must
            # not drag it along when rows come in above
            viewport.set_scroll_to_focus(False)
        self.adj = self.scroll.get_vadjustment()
        self.adj.connect("value-changed", lambda _a: self._scrolled())
        self.adj.connect("changed", lambda _a: self._adjusted())
        self.append(self.scroll)

    # ---- the lane's contents ---------------------------------------------------------
    def refresh(self):
        """Bring the rows in step with the lane. Cheap when nothing changed; the cards
        themselves are built later, in batches."""
        with diag.busy(f"gtk lane {self.name}: refresh"):
            self._refresh()

    def _refresh(self):
        self.dirty = False
        view = self.ctx.view
        entries = view.entries(self.name)
        self.unread = set() if self.lazy else view.unread(entries)
        keys = [k for k, _ in entries]
        if self.newest_first:
            keys.reverse()
        old_keys = self.keys
        self.keys, self.entries = keys, dict(entries)
        self.index = index = {k: i for i, k in enumerate(keys)}
        if self.separator is None and not self.positioned:
            first = next((k for k, e in entries if e.id in self.unread), None)
            if first is not None and any(e.id not in self.unread for _, e in entries):
                self.separator = first
        for k in [k for k in self.order if k not in index]:
            self._remove(k)
        self._queue = [(side, [k for k in ks if k in index and k not in self.rows])
                       for side, ks in self._queue]
        if not self.order and not self._pending():
            self._open(index)
        else:
            self._take_new(old_keys, index)
        for k in self.order:
            self.rows[k].set_unread(self.entries[k].id in self.unread)
        if self.order:  # "you replied" under what's on screen: a reply just sent shows
            shown = [self.entries[k] for k in self.order]
            answers = view.my_replies(shown)
            for k in self.order:
                self.rows[k].set_my_replies(answers.get(real(self.entries[k]).id, ()))
        self._pill(len(self.unread))
        self._older_visible()
        self._build_soon()

    def _open(self, index):
        """The first window: around the first unread, or at the end to read from."""
        if not self.keys:
            self.positioned = True
            return
        target = next((i for i, k in enumerate(self.keys)
                       if self.entries[k].id in self.unread), None)
        if target is None:
            target = 0 if self.newest_first else len(self.keys) - 1
        lo, hi = window_around(len(self.keys), target)
        # from the target down first, then what's above it: reading starts at once
        self._queue = [("end", self.keys[target:hi]), ("start", self.keys[lo:target][::-1])]

    def _take_new(self, old_keys, index):
        """New keys inside the run on screen go in at their place; past its ends they
        join only when that end was the lane's end (the reader is there), a STEP at most:
        the rest comes as the view nears it."""
        if not self.order:
            return
        lo, hi = index[self.order[0]], index[self.order[-1]] + 1
        inside = [k for k in self.keys[lo:hi] if k not in self.rows]
        if inside:
            self._queue.append(("inside", inside))
        old_last = old_keys[-1] if old_keys else None
        if old_last in self.rows and hi < len(self.keys):
            self._queue.append(("end", self.keys[hi:hi + STEP]))
        old_first = old_keys[0] if old_keys else None
        if old_first in self.rows and lo > 0 and self.newest_first:
            self._queue.append(("start", self.keys[max(0, lo - STEP):lo][::-1]))

    def _pending(self):
        return any(ks for _side, ks in self._queue)

    # ---- building in batches ---------------------------------------------------------
    def _build_soon(self):
        if self._building or not self._pending():
            return
        self._building = GLib.idle_add(self._build_batch, priority=GLib.PRIORITY_LOW)

    def _build_batch(self):
        """Build cards for BATCH_MS, all on one side (so the view can be held still),
        then give the window a frame."""
        self._building = 0
        if self.stopped or self.get_root() is None:  # the window is gone: nothing more
            self._queue = []
            return GLib.SOURCE_REMOVE
        while self._queue and not self._queue[0][1]:
            self._queue.pop(0)
        if not self._queue:
            self._done_building()
            return GLib.SOURCE_REMOVE
        side, keys = self._queue[0]
        start = time.monotonic()
        first = self._first_visible() if self.positioned else None
        if side == "start":
            above = self.positioned
        elif side == "inside" and first is not None:
            # this batch: only keys on the same side of the view as the first one
            above = self.index[keys[0]] < self.index[first]
        else:
            above = False
        if not above and self._held_upper is not None:
            # rows below change the height too: wait till the view is let go
            self._building = GLib.timeout_add(HOLD_MS, self._build_batch)
            return GLib.SOURCE_REMOVE
        if above:
            self._hold()
        with diag.busy(f"gtk lane {self.name}: build"):
            while keys and (time.monotonic() - start) * 1000 < BATCH_MS:
                take = []
                while keys and len(take) < 4:
                    if side == "inside" and first is not None and \
                            (self.index[keys[0]] < self.index[first]) != above:
                        break
                    take.append(keys.pop(0))
                if not take:  # the rest is on the view's other side: a batch of its own
                    break
                self._make(take)
        self._build_soon_after()
        return GLib.SOURCE_REMOVE

    def _build_soon_after(self):
        if self._pending():
            self._building = GLib.idle_add(self._build_batch, priority=GLib.PRIORITY_LOW)
        else:
            self._done_building()

    def _done_building(self):
        self._older_visible()
        self._schedule_seen()  # new cards may be on screen already
        if not self.positioned and self.get_mapped():
            GLib.idle_add(self._position, priority=GLib.PRIORITY_LOW)
        self._trim()

    def _make(self, keys):
        view = self.ctx.view
        posts = [self.entries[k] for k in keys]
        parents = view.parents(posts)
        short = view.short_ids(posts)
        answers = view.my_replies(posts)  # {post id: [my replies to it]}
        unknown = [e for e in posts if parents.get(e.id) is None and real(e).reply_to]
        if unknown:
            view.ensure_parents(unknown)
        for k in keys:
            e = self.entries[k]
            card = Card(self.ctx, k, e, parent=parents.get(e.id), unread=e.id in self.unread,
                        short_id=short.get(real(e).id),
                        my_replies=answers.get(real(e).id, ()))
            row = Gtk.ListBoxRow(activatable=False, selectable=False)
            if k == self.separator:
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
                box.append(Separator(self.ctx.theme.word("separator", _("new_below"),
                                                         n=len(self.unread))))
                box.append(card)
                row.set_child(box)
            else:
                row.set_child(card)
            pos = self._position_for(k)
            self.list.insert(row, pos)
            self.order.insert(pos, k)
            self.rows[k] = card

    def _position_for(self, key):
        """Where key goes among the rows on screen (they follow self.keys): a bisect."""
        i = self.index[key]
        lo, hi = 0, len(self.order)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.index.get(self.order[mid], -1) < i:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def _first_visible(self):
        top = self.adj.get_value()
        for k in self.order:
            card = self.rows[k]
            y = self._y(card)
            if y is not None and y + card.get_height() > top:
                return k
        return None

    def _remove(self, key):
        card = self.rows.pop(key, None)
        if key in self.order:
            self.order.remove(key)
        if card is None:
            return
        row = card.get_parent()
        while row is not None and not isinstance(row, Gtk.ListBoxRow):
            row = row.get_parent()
        if row is not None:
            self.list.remove(row)

    def _trim(self):
        """More rows than MAX_ROWS: the end farther from the view goes."""
        extra = len(self.order) - MAX_ROWS
        if extra <= 0 or not self.positioned:
            return
        top = self.adj.get_value()
        bottom_gap = self.adj.get_upper() - (top + self.adj.get_page_size())
        if top > bottom_gap:  # reading near the bottom: the top goes, the view held still
            self._hold()
            for k in self.order[:extra]:
                self._remove(k)
        else:
            for k in self.order[-extra:]:
                self._remove(k)
        self._older_visible()

    def _hold(self):
        """Rows go in or out above what's being read: from now until HOLD_MS after the
        last such change the view stays still. Two ways at once: every change of the
        content's height moves the view by as much, in the same frame (_adjusted); and
        on each frame the post that was at the top is put back where it was on screen,
        which mends what the first misses (cards elsewhere wrapping their text anew)."""
        if self._held_upper is None:
            self._held_upper = self.adj.get_upper()
            key = self._first_visible()
            y = self._y(self.rows[key]) if key is not None else None
            self._anchor = (key, y - self.adj.get_value()) if y is not None else None
            self._ticking = self.list.add_tick_callback(self._keep_anchor)
        if self._hold_timer:
            GLib.source_remove(self._hold_timer)
        self._hold_timer = GLib.timeout_add(HOLD_MS, self._let_go)

    def _keep_anchor(self, _widget, _clock):
        if self._anchor is None:
            return GLib.SOURCE_CONTINUE
        key, offset = self._anchor
        card = self.rows.get(key)
        y = self._y(card) if card is not None else None
        if y is None:
            return GLib.SOURCE_CONTINUE
        want = max(0, y - offset)
        if abs(want - self.adj.get_value()) > 0.5:
            self.adj.set_value(want)
        return GLib.SOURCE_CONTINUE

    def _let_go(self):
        self._hold_timer = 0
        self._keep_anchor(None, None)
        if self._ticking:
            self.list.remove_tick_callback(self._ticking)
            self._ticking = 0
        self._held_upper = None
        self._anchor = None
        return GLib.SOURCE_REMOVE

    def _adjusted(self):
        if self._held_upper is None:
            return
        upper = self.adj.get_upper()
        moved, self._held_upper = upper - self._held_upper, upper
        if moved:
            self.adj.set_value(max(0, self.adj.get_value() + moved))

    def _older_visible(self):
        """'Earlier' only when the oldest post stored is on screen (or nothing is)."""
        if not self.keys:
            self.older.set_visible(not self.lazy)
            return
        oldest = self.keys[-1] if self.newest_first else self.keys[0]
        self.older.set_visible(oldest in self.rows and not self._pending())

    def _grow(self):
        """The view nears an end of what's built: STEP more from the lane there."""
        if self._pending() or not self.order or not self.positioned:
            return
        lo, hi = self.index[self.order[0]], self.index[self.order[-1]] + 1
        value, page, upper = (self.adj.get_value(), self.adj.get_page_size(),
                              self.adj.get_upper())
        if value + page * 2.5 >= upper and hi < len(self.keys):
            self._queue.append(("end", self.keys[hi:hi + STEP]))
        elif value <= page * 1.5 and lo > 0:
            self._queue.append(("start", self.keys[max(0, lo - STEP):lo][::-1]))
        self._build_soon()

    def _pill(self, n):
        self.pill.set_visible(n > 0)
        if n:
            self.pill.set_text(_("unread_n", n=n))

    def update_post(self, post):
        for card in self.rows.values():
            if real(card.entry).id == post.id:
                card.update(replace(card.entry, post=post) if isinstance(card.entry, Share)
                            else post)

    # ---- position and reading --------------------------------------------------------
    def shown(self):
        """The lane came on screen: catch up if it changed meanwhile, place it."""
        if self.dirty:
            self.refresh()
        elif not self.positioned and not self._pending():
            GLib.idle_add(self._position, priority=GLib.PRIORITY_LOW)

    def _position(self):
        """Opened: the first unread at the top (or the newest end when all is read)."""
        if self.positioned or self._pending() or self.get_root() is None:
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

    def _scrolled(self):
        self._schedule_seen()
        self._grow()

    def _schedule_seen(self):
        if self._seen_timer or self.lazy:
            return
        self._seen_timer = GLib.timeout_add(SEEN_DELAY_MS, self._mark_seen)

    def _mark_seen(self):
        self._seen_timer = 0
        if self.stopped:
            return GLib.SOURCE_REMOVE
        root = self.get_root()
        if not self.positioned or root is None or not root.is_active() or \
                not self.get_mapped():
            return GLib.SOURCE_REMOVE
        vtop = self.adj.get_value()
        vbot = vtop + self.adj.get_page_size()
        ids, unplaced = [], False
        for k in self.order:
            card = self.rows[k]
            if not card.unread:
                continue
            y = self._y(card)
            if y is None or card.get_height() <= 0:
                unplaced = True  # not laid out yet: look again in a moment
                continue
            if seen(y, y + card.get_height(), vtop, vbot):
                ids.append(card.entry.id)
                card.set_unread(False)
        if unplaced:
            self._schedule_seen()
        if ids:
            self.unread -= set(ids)
            self.ctx.view.mark_read(ids)
            self._pill(len(self.unread))
        return GLib.SOURCE_REMOVE

    def stop(self):
        """The window closes: whatever is queued is dropped (the core may close too)."""
        self.stopped = True
        self._queue = []
        for attr in ("_building", "_seen_timer", "_hold_timer"):
            src = getattr(self, attr, 0)
            if src:
                GLib.source_remove(src)
                setattr(self, attr, 0)

    def window_activated(self):
        self._schedule_seen()

    def mark_all_read(self):
        self.ctx.view.mark_lane_read(self.name)
        for card in self.rows.values():
            card.set_unread(False)
        self.unread = set()
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
