"""A lane on screen: its header, the posts as cards in a scrolled list, "Older".

A lane may hold thousands of posts; a GTK card costs a few milliseconds to build and
lay out, so only a window of them is on screen (as qt/feed.py does): WINDOW cards
around where reading starts, built in small batches between frames so the window never
stops answering, more joining as the view nears an end, the far end trimmed past
MAX_ROWS.

Nothing jumps (docs/DESIGN.md): rows are kept by key and never rebuilt while on screen;
when rows go in or out above what is being read, the view moves by exactly the height
they added or took away. Posts seen while the window is active are marked read.

What the lane shows — the cards, the filters, conversations, the media funnel, the
divider, where reading starts, what counts as read — is common/lane.py's, the same as
in the Qt window; this file only puts it on screen.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace

from ... import diag
from ...i18n import _
from ...model import Share, real
from ..common.lane import MEDIA_KINDS, SEPARATOR, LaneModel, conversation_line, seen
from .card import Card, Separator
from .gi_setup import GLib, Gtk, Pango, clamp, set_clamp, side_by_side, tip, wrap_box

log = logging.getLogger(__name__)

SEEN_DELAY_MS = 400
WINDOW = 30         # cards built when a lane opens: a few above where reading starts
BACK = 8            # …of them above it
STEP = 20           # cards added when the view nears an end
MAX_ROWS = 120      # more than this on screen: the far end goes (every row is laid out
                    # again at each scroll step: a long list costs on every frame)
BATCH_MS = 25       # building cards for at most this long at a time, then a frame
FRAME_MS = 40       # what laying a batch out may take: the number per batch follows it
PER_BATCH = (2, 4, 12)  # cards a batch: at least, to start with, at most
HOLD_MS = 250       # the view held still this long after rows changed above it


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
        self.lm = LaneModel(ctx.view, name, lambda n: ctx.theme.word(
            "separator", _("new_below"), n=n))
        self.lazy = self.lm.lazy
        self.newest_first = self.lm.newest_first
        self.keys = []           # every key of the lane, top to bottom (no divider)
        self.index = {}          # key -> its place in self.keys
        self.specs = {}          # key -> CardSpec (common/lane.py)
        self.unread = set()      # keys of the unread cards
        self.rows = {}           # key -> Card on screen
        self.order = []          # keys on screen, top to bottom: a run of self.keys
        self.sep_above = None    # the key the "new below" line sits above
        self._glimpsed = set()   # unread cards seen in part (common/lane.py seen())
        self.positioned = False
        self.dirty = True        # the lane changed while not on screen
        self.stopped = False     # the window closed: no more work queued
        self._queue = []         # (side, [keys]) waiting to be built: side "end" | "start"
        self._building = 0
        self._tick = 0           # a batch waiting for the next frame
        self._seen_timer = 0
        # while rows go in or out above what's being read: the height of the content
        # last seen, and until when to hold the view still (see _hold)
        self._held_upper = None
        self._hold_timer = 0
        self._anchor = None      # (key, its offset from the top of the view) while held
        self._ticking = 0

        words = Gtk.Box(spacing=8)  # the title, "N new", what's shown; the buttons beside
        self.title = Gtk.Label(label=ctx.theme.word("lane_title", title), xalign=0)
        self.title.add_css_class("ft-lane-title")
        self.title.set_hexpand(True)
        self.title.set_ellipsize(Pango.EllipsizeMode.END)  # never wider than the window
        self.title.set_valign(Gtk.Align.CENTER)
        words.append(self.title)
        self.pill = Gtk.Label()
        self.pill.add_css_class("ft-new-pill")
        self.pill.set_visible(False)
        self.pill.set_valign(Gtk.Align.CENTER)  # the header two rows high: still a pill
        words.append(self.pill)
        self.info = Gtk.Label(xalign=1)
        self.info.add_css_class("ft-muted")
        self.info.set_ellipsize(Pango.EllipsizeMode.END)
        self.info.set_valign(Gtk.Align.CENTER)
        words.append(self.info)
        # as Qt's header: All | Posts only | New, conversations, ↓ To new, Mark all
        # read, ▾ Show, Refresh (F5)
        # one row at the right where there's room, wrapping to more in a narrow window
        # (a scroller cut the last ones at the edge, unseen)
        tools = wrap_box(spacing=6, row_spacing=4, align_end=True)
        tools.set_valign(Gtk.Align.CENTER)
        tools.set_hexpand(False)
        header = side_by_side(words, tools, 8)  # not a box: GTK 4.18 (gi_setup.py)
        header.add_css_class("ft-lane-header")
        self._filter_buttons = {}
        if len(self.lm.filters) > 1:
            group, words = None, {"all": ("show_all", "show_all_tip"),
                                  "posts": ("posts_only", "posts_only_tip"),
                                  "unread": ("unread_only", "unread_only_tip")}
            seg = Gtk.Box()
            seg.add_css_class("linked")
            now = self.lm.current_filter()
            for which in self.lm.filters:
                b = Gtk.ToggleButton(label=_(words[which][0]))
                tip(b, _(words[which][1]))
                if group is not None:
                    b.set_group(group)
                group = group or b
                b.set_active(which == now)
                b.connect("toggled", lambda b, w=which: b.get_active() and self.set_filter(w))
                self._filter_buttons[which] = b
                seg.append(b)
            tools.append(seg)
        if self.lm.conversations_offered():  # as Qt's: Feed | Conversations
            seg = Gtk.Box()
            seg.add_css_class("linked")
            feed = Gtk.ToggleButton(label=_("view_feed"))
            tip(feed, _("view_feed_tip"))
            conv = Gtk.ToggleButton(label=_("conv_mode"), group=feed)
            tip(conv, _("conv_mode_tip"))
            (conv if self.lm.conversations() else feed).set_active(True)
            conv.connect("toggled", lambda b: self.set_conversations(b.get_active()))
            seg.append(feed)
            seg.append(conv)
            tools.append(seg)
        self.to_new = Gtk.Button(label="↓ " + _("to_new"))
        tip(self.to_new, _("to_new_tip"))
        self.to_new.connect("clicked", lambda _b: self.jump_first_unread())
        tools.append(self.to_new)
        read = Gtk.Button(label=_("mark_all_read"))
        read.connect("clicked", lambda _b: self.mark_all_read())
        if not self.lazy:
            tools.append(read)
        tools.append(self._media_button())
        refresh = Gtk.Button(label=_("refresh") + " (F5)")
        refresh.connect("clicked", lambda _b: ctx.view.poll_now())
        tools.append(refresh)
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
        self.empty_note = Gtk.Label(label=_("browse_empty"), wrap=True,
                                    justify=Gtk.Justification.CENTER)
        self.empty_note.add_css_class("ft-muted")
        self.empty_note.add_css_class("title-4")
        for m in ("start", "end"):
            getattr(self.empty_note, "set_margin_" + m)(24)
        self.empty_note.set_margin_top(48)
        self.empty_note.set_visible(False)
        column.append(self.empty_note)
        if not self.newest_first:
            column.append(self.older)
        column.append(self.list)
        if self.newest_first:
            column.append(self.older)
        column.set_hexpand(True)
        # a column at most ui.max_width wide — narrower with the window; 0: the whole
        # width (↔ in the sidebar changes it while running)
        self.clamp = column = clamp(column, _width(ctx.cfg))

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
        built = self.lm.build(self.positioned)
        self.info.set_text(built.info)
        # a live lane the server gives empty (mastodon.social and the like keep them
        # for their own): said in the lane, big, as Qt does
        self.empty_note.set_visible(bool(getattr(built, "empty", False)))
        specs = built.specs
        self.sep_above = None
        keys, sep = [], False
        for sp in specs:
            if sp.key == SEPARATOR:
                sep = sp
                continue
            if sep:
                self.sep_above, sep = (sp.key, sep.extra["separator"]), False
            keys.append(sp.key)
        old_keys = self.keys
        self.keys, self.specs = keys, {sp.key: sp for sp in specs if sp.key != SEPARATOR}
        self.unread = {k for k in keys if self.specs[k].unread}
        self.index = index = {k: i for i, k in enumerate(keys)}
        for k in [k for k in self.order if k not in index]:
            self._remove(k)
        self._queue = [(side, [k for k in ks if k in index and k not in self.rows])
                       for side, ks in self._queue]
        if not self.order and not self._pending():
            self._open(specs)
        else:
            self._take_new(old_keys, index)
        for k in self.order:  # "you replied" under what's on screen: a reply just sent
            self.rows[k].set_unread(k in self.unread)
            self.rows[k].set_my_replies(self.specs[k].extra.get("my_replies", ()))
        self._pill(len(self.unread))
        self._older_visible()
        self._build_soon()

    def apply_read(self, ids):
        """Posts marked read (here as they were seen, or anywhere else): their marks
        go, nothing is rebuilt — a whole refresh for every few posts seen while
        scrolling was most of what a long lane cost (as Qt's apply_read)."""
        ids = set(ids)
        gone = [k for k in self.unread if self.specs.get(k) is not None
                and (self.specs[k].entry.id in ids or real(self.specs[k].entry).id in ids)]
        if not gone:
            return
        for k in gone:
            self.unread.discard(k)
            self.specs[k] = replace(self.specs[k], unread=False)
            card = self.rows.get(k)
            if card is not None:
                card.set_unread(False)
        self._pill(len(self.unread))

    def _reset(self):
        """Another filter or view: the lane anew, placed anew."""
        for k in list(self.order):
            self._remove(k)
        self._queue = []
        self.keys, self.index = [], {}
        self.positioned = False
        self._glimpsed = set()
        self.refresh()

    def set_filter(self, which):
        """"all", "posts" (no replies) or "unread"."""
        if which == self.lm.current_filter() and self.positioned:
            return
        self.lm.set_filter(which)
        self._reset()

    def set_conversations(self, on):
        self.lm.set_conversations(on)
        self._reset()

    def _media_button(self):
        """The funnel: posts with pictures, gifs, video… only, boosts or not."""
        button = Gtk.MenuButton(label="▾ " + _("media_filter"))
        tip(button, _("media_filter_tip"))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        checks, quiet = {}, []

        def changed():
            (button.add_css_class if self.lm.media.active() else
             button.remove_css_class)("ft-active")
            self._reset()

        def toggled(kind, on):
            if quiet:
                return
            if kind == "boosts":
                self.lm.media.boosts = on
            else:
                self.lm.media.toggle(kind, on)
            changed()

        for kind in (*MEDIA_KINDS, "boosts"):
            c = Gtk.CheckButton(label=_("filter_" + kind), active=True)
            c.connect("toggled", lambda c, k=kind: toggled(k, c.get_active()))
            checks[kind] = c
            box.append(c)

        def everything(_b):
            quiet.append(True)
            for c in checks.values():
                c.set_active(True)
            quiet.clear()
            self.lm.media.reset()
            changed()
        reset = Gtk.Button(label=_("filter_all"))
        reset.add_css_class("flat")
        reset.connect("clicked", everything)
        box.append(reset)
        pop = Gtk.Popover()
        pop.set_child(box)
        button.set_popover(pop)
        self.media_checks = checks
        return button

    def _open(self, specs):
        """The first window: around where reading starts (common/lane.py start())."""
        if not self.keys:
            self.positioned = True
            return
        key, _where = self.lm.start(specs)
        if key == SEPARATOR:
            key = self.sep_above[0] if self.sep_above else None
        if key in self.index:
            target = self.index[key]
        else:
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
        if self._building or self._tick or not self._pending():
            return
        self._next_batch()

    def _next_batch(self):
        """A batch a frame: on screen, at the next frame (so each batch is laid out
        before the next is made — idle callbacks ran several between two frames, and
        one frame then laid out them all); out of sight, when the loop is idle."""
        if self.get_mapped():
            self._tick = self.add_tick_callback(self._on_tick)
        else:
            self._building = GLib.idle_add(self._build_batch, priority=GLib.PRIORITY_LOW)

    def _on_tick(self, *_a):
        self._tick = 0
        self._build_batch()
        return GLib.SOURCE_REMOVE

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
        self._fit_batch(start)
        made = 0
        # the reader waiting at the edge of what's built (nothing on screen moves): a
        # bigger batch — a long frame then costs less than more frames of waiting
        at_edge = self.positioned and side == "end" and \
            self.adj.get_value() + self.adj.get_page_size() >= self.adj.get_upper() - 2
        limit, budget = (self._per_batch * 2, BATCH_MS * 2) if at_edge else \
            (self._per_batch, BATCH_MS)
        with diag.busy(f"gtk lane {self.name}: build"):
            while keys and (time.monotonic() - start) * 1000 < budget and \
                    made < limit:
                take = []
                while keys and len(take) < min(4, limit - made):
                    if side == "inside" and first is not None and \
                            (self.index[keys[0]] < self.index[first]) != above:
                        break
                    take.append(keys.pop(0))
                if not take:  # the rest is on the view's other side: a batch of its own
                    break
                self._make(take)
                made += len(take)
        self._batch_end = time.monotonic()
        self._build_soon_after()
        return GLib.SOURCE_REMOVE

    def _fit_batch(self, now):
        """Building a card is the cheap part: laying it out (its text shaped, wrapped,
        measured) costs ten times more, and all of a batch is laid out in the next frame.
        So the number of cards a batch follows how long the last batch's frame took:
        fewer when it held the window, more when there was room."""
        if not hasattr(self, "_per_batch"):
            self._per_batch, self._batch_end = PER_BATCH[1], None
        if self._batch_end is None:
            return
        took = (now - self._batch_end) * 1000
        lo, _start, hi = PER_BATCH
        if took > FRAME_MS * 3:
            self._per_batch = max(lo, self._per_batch // 2)
        elif took < FRAME_MS:
            self._per_batch = min(hi, self._per_batch + 2)

    def _build_soon_after(self):
        if self._pending():
            self._next_batch()
        else:
            self._done_building()

    def _done_building(self):
        if getattr(self, "_wanted", None) is not None:
            GLib.idle_add(self._bring_wanted, priority=GLib.PRIORITY_LOW)
        elif self.positioned:
            # still near an end (the reader held there, waiting): more at once — no
            # scroll event comes while the view stands at the edge
            GLib.idle_add(self._grow_idle, priority=GLib.PRIORITY_LOW)
        self._older_visible()
        self._schedule_seen()  # new cards may be on screen already
        if not self.positioned and self.get_mapped():
            GLib.idle_add(self._position, priority=GLib.PRIORITY_LOW)
        self._trim()

    def _make(self, keys):
        for k in keys:
            sp = self.specs[k]
            card = Card(self.ctx, k, sp.entry, parent=sp.parent, unread=sp.unread,
                        short_id=sp.extra.get("short_id"),
                        my_replies=sp.extra.get("my_replies", ()))
            line = conversation_line(sp)
            if line:
                card.add_conversation(*line)
            row = Gtk.ListBoxRow(activatable=False, selectable=False)
            if self.sep_above and k == self.sep_above[0]:
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
                box.append(Separator(self.sep_above[1]))
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
        """The first row reaching below the view's top: a bisection (the rows are in
        order down the list) — looking at every row on every scroll step was a good part
        of what scrolling a long lane cost; one not laid out yet: row by row."""
        top = self.adj.get_value()
        order, lo, hi = self.order, 0, len(self.order)
        while lo < hi:
            mid = (lo + hi) // 2
            card = self.rows[order[mid]]
            y = self._y(card)
            if y is None:
                break
            if y + card.get_height() > top:
                hi = mid
            else:
                lo = mid + 1
        else:
            return order[lo] if lo < len(order) else None
        for k in order:
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
        if not self.stopped and self.get_mapped() and \
                any(c.get_height() <= 0 for c in self.rows.values()):
            # cards made but not laid out yet (a slow frame): their height is still to
            # come, so the view is held on until it has
            self._hold_timer = GLib.timeout_add(HOLD_MS // 2, self._let_go)
            return GLib.SOURCE_REMOVE
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
        """The view nears an end of what's built: more from the lane there — STEP, and
        twice as many each time the reader comes back to that end soon after (scrolling
        fast, a fling: the cards must stay ahead, not be waited for at the edge)."""
        if self._pending() or not self.order or not self.positioned:
            return
        lo, hi = self.index[self.order[0]], self.index[self.order[-1]] + 1
        value, page, upper = (self.adj.get_value(), self.adj.get_page_size(),
                              self.adj.get_upper())
        side = None
        if value + page * 3 >= upper and hi < len(self.keys):
            side = "end"
        elif value <= page * 2 and lo > 0:
            side = "start"
        if side is None:
            return
        now = time.monotonic()
        last_side, last_at, step = getattr(self, "_last_grow", (None, 0.0, STEP))
        step = min(MAX_ROWS // 2, step * 2) if side == last_side and now - last_at < 1.0 \
            else STEP
        self._last_grow = (side, now, step)
        if side == "end":
            self._queue.append(("end", self.keys[hi:hi + step]))
        else:
            self._queue.append(("start", self.keys[max(0, lo - step):lo][::-1]))
        self._build_soon()

    def _grow_idle(self):
        if not self.stopped and self.get_root() is not None:
            self._grow()
        return GLib.SOURCE_REMOVE

    def _pill(self, n):
        self.pill.set_visible(n > 0)
        if n:
            self.pill.set_text(_("new_n", n=n))
        # nothing new: it still works — to the newest end of the lane (as Qt says)
        tip(self.to_new, _("to_new_tip") if n else _("to_end_tip"))

    def update_post(self, post):
        for card in self.rows.values():
            if real(card.entry).id == post.id:
                card.update(replace(card.entry, post=post) if isinstance(card.entry, Share)
                            else post)

    # ---- position and reading --------------------------------------------------------
    def shown(self):
        """The lane came on screen: catch up if it changed meanwhile, place it."""
        if self.ctx.cfg["read"]["mark_read"] == "on_open" and not self.lazy:
            GLib.idle_add(lambda: self.mark_all_read() and False)
        if self.dirty:
            self.refresh()
        elif not self.positioned and not self._pending():
            GLib.idle_add(self._position, priority=GLib.PRIORITY_LOW)

    def hidden(self):
        """Another lane in front: "unread only" shows anew what's unread next time."""
        if self.lm.left():
            self.dirty = True
            for k in list(self.order):
                self._remove(k)
            self._queue = []
            self.keys, self.index = [], {}
            self.positioned = False

    def bring(self, key, then=None):
        """key's card on screen near the top — built around it if it wasn't (find,
        a link to a post far away); then(card) once it's there."""
        if key in self.rows:
            y = self._y(self.rows[key])
            if y is not None:
                self.adj.set_value(max(0, y - 40))
            if then is not None:
                then(self.rows[key])
            return
        if key not in self.index:
            return
        for k in list(self.order):
            self._remove(k)
        target = self.index[key]
        lo, hi = window_around(len(self.keys), target)
        self._queue = [("end", self.keys[target:hi]), ("start", self.keys[lo:target][::-1])]
        self.positioned = True  # placed here, not where reading starts
        self._wanted = (key, then)
        self._build_soon()

    def _bring_wanted(self):
        key, then = self._wanted
        self._wanted = None
        if key in self.rows:
            self.bring(key, then)
        return GLib.SOURCE_REMOVE

    def jump_first_unread(self):
        """↓ To new: the first unread at the top (built around it, if it wasn't), or —
        nothing new — the lane's newest end."""
        target = next((k for k in self.keys if k in self.unread), None)
        if target is not None and target in self.rows:
            y = self._y(self.rows[target])
            if y is not None:
                self.adj.set_value(max(0, y - 40))
                return
        if target is None and self.keys:
            end = self.keys[0] if self.newest_first else self.keys[-1]
            if end in self.rows:
                self.adj.set_value(0 if self.newest_first else
                                   self.adj.get_upper() - self.adj.get_page_size())
                return
        self._reset()  # not built: the lane anew, around where reading starts

    def _position(self):
        """Opened: where reading starts (common/lane.py start()) — the first unread at
        the top, or the newest end when all is read."""
        if self.positioned or self._pending() or self.get_root() is None:
            return GLib.SOURCE_REMOVE
        specs = [self.specs[k] for k in self.order]
        key, where = self.lm.start(specs)
        if key is None and self.unread:  # the divider's card is not built: the first unread
            key = next((k for k in self.order if k in self.unread), None)
            where = "bottom" if self.newest_first else "top"
        card = self.rows.get(key) if key is not None else None
        y = self._y(card) if card is not None else None
        if y is not None and where == "bottom":
            self.adj.set_value(max(0, y + card.get_height() - self.adj.get_page_size() + 40))
        elif y is not None:
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
        at_end = vtop >= self.adj.get_upper() - self.adj.get_page_size() - 1
        keys, unplaced, glimpsed = [], False, set()
        for k in self.order:
            card = self.rows[k]
            if not card.unread:
                continue
            y = self._y(card)
            if y is None or card.get_height() <= 0:
                unplaced = True  # not laid out yet: look again in a moment
                continue
            got = seen(y, y + card.get_height(), vtop, vbot, at_end, k in self._glimpsed)
            if got == "read":
                keys.append(k)
            elif got == "glimpsed":
                glimpsed.add(k)
        self._glimpsed = (self._glimpsed & self.unread) | glimpsed
        if unplaced:
            self._schedule_seen()
        ids = self.lm.read([self.rows[k].entry.id for k in keys])
        if ids:
            for k in keys:
                self.rows[k].set_unread(False)
            self.unread -= set(keys)
            self._glimpsed -= set(keys)
            self.ctx.view.mark_read(ids)
            self._pill(len(self.unread))
        return GLib.SOURCE_REMOVE

    def apply_width(self):
        """ui.max_width changed (↔): the column follows."""
        set_clamp(self.clamp, _width(self.ctx.cfg))

    def stop(self):
        """The window closes: whatever is queued is dropped (the core may close too)."""
        self.stopped = True
        self._queue = []
        for attr in ("_building", "_seen_timer", "_hold_timer"):
            src = getattr(self, attr, 0)
            if src:
                GLib.source_remove(src)
                setattr(self, attr, 0)
        if self._tick:
            self.remove_tick_callback(self._tick)
            self._tick = 0

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


FULL = 100_000  # "no limit" for the clamp


def _width(cfg):
    w = int(cfg["ui"].get("max_width") or 0)
    return min(w, 4000) if w else FULL


def y_in(widget, ancestor):
    """widget's top in ancestor's coordinates, or None (not laid out yet)."""
    if hasattr(widget, "compute_point"):  # GTK 4.12+
        from gi.repository import Graphene
        ok, pt = widget.compute_point(ancestor, Graphene.Point().init(0, 0))
        return pt.y if ok else None
    res = widget.translate_coordinates(ancestor, 0, 0)
    return res[1] if res else None
