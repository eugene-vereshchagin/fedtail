"""A lane on screen: its header, the posts as cards, "Older".

A lane may hold thousands of posts; a GTK card costs milliseconds to build and lay out.
So, as in the Qt window (qt/feedview.py), every post has a place — a top and a height —
on one strip (common/strip.py, the same code for both toolkits), the body is as tall as
all of them, and only the cards within a screen above and below the screen exist,
placed by hand (Body). The ones on screen are built at once, the others a few at a time
between frames, nearest first; the ones gone far are let go. Before (a run of up to 120
rows in a ListBox, grown at its ends) GTK laid out every row at each scroll step and the
reader waited at the edge of what was built: 420 turns over 100 ms in the bench against
Qt's 4 (29.10).

Nothing jumps (docs/en/dev/design.md): when places above the screen change (a card built
and measured, posts come in), the card on top of the screen is held where it was. Posts
seen while the window is active are marked read.

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
from ..common.cardtext import thread_news_bit
from ..common.lane import MEDIA_KINDS, SEPARATOR, LaneModel, conversation_line, seen
from ..common.strip import Strip
from .card import Card, Separator, link_markup
from .gi_setup import GLib, Gtk, Pango, clamp, forget, set_clamp, side_by_side, tip, wrap_box

log = logging.getLogger(__name__)

SEEN_DELAY_MS = 400
AHEAD = 1.0         # cards exist this many screens above and below the screen
SLICE_MS = 12       # the cards beyond the screen are built this long at a time
GAP = 8             # between cards
FIRST_GUESS = 160   # a card's height before any was measured here
HOLD_S = 1.5        # the reading place held this long after the places last changed


class Body(Gtk.Widget):
    """The cards, each at its place on the strip: as tall as every place together, the
    cards that exist allocated where the strip says (their widths the body's). A card
    that wants another height (its pictures came, a warning opened) is measured again
    here, and the lane lays the places out anew."""

    def __init__(self, lane):
        super().__init__()
        self.lane = lane
        self.total = 0
        self.min_width = 0

    def do_measure(self, orientation, _for_size):
        if orientation == Gtk.Orientation.VERTICAL:
            return self.total, self.total, -1, -1
        return self.min_width, self.min_width, -1, -1

    def do_size_allocate(self, width, height, _baseline):
        from gi.repository import Graphene, Gsk
        lane = self.lane
        if width != lane.strip.width:
            GLib.idle_add(lane._width_changed, priority=GLib.PRIORITY_HIGH_IDLE)
        changed = False
        for key, box in lane.boxes.items():
            h = box.measure(Gtk.Orientation.VERTICAL, width)[1]
            if lane.strip.measured(key, width, h):
                changed = True
            y = lane.strip.ys.get(key, 0)
            box.allocate(width, h, -1, Gsk.Transform().translate(Graphene.Point().init(0, y)))
        if changed:  # the places below move: laid out anew, the reading place held
            GLib.idle_add(lane._relayout, priority=GLib.PRIORITY_HIGH_IDLE)


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
        self.rows = {}           # key -> Card that exists now
        self.boxes = {}          # key -> what stands at its place (the card, or the
                                 # "new below" line and the card)
        self.order = []          # keys of the cards that exist, top to bottom
        self.sep_above = None    # the key the "new below" line sits above
        self._glimpsed = set()   # unread cards seen in part (common/lane.py seen())
        self.positioned = False
        self.dirty = True        # the lane changed while not on screen
        self.stopped = False     # the window closed: no more work queued
        self.strip = Strip(GAP, 0, FIRST_GUESS)  # the places (common/strip.py)
        self._waiting = []       # keys near the screen not built yet, nearest first
        self._more = 0           # the idle source building them
        self._seen_timer = 0
        self._held = set()       # keys built wherever the screen is (gone to: bring)
        # where reading is held while the places settle: (key, its offset from the
        # screen's top, until when) — or ("end", newest_end, until)
        self._target = None

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
            group = None
            # Home's quick filters are many (tags, boosts, threads with news…): one row
            # of them wraps too, or a narrow window can't be narrower than they are
            seg = wrap_box(spacing=2, row_spacing=2) if len(self.lm.filters) > 3 \
                else Gtk.Box()
            seg.add_css_class("linked")
            now = self.lm.current_filter()
            for which in self.lm.filters:
                label, about = self.lm.filter_words(which)
                b = Gtk.ToggleButton(label=label)
                tip(b, about)
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
        read = Gtk.Button()
        self._dress(read, "mark_read", _("mark_all_read"), keep_words=True)
        read.connect("clicked", lambda _b: self.mark_all_read())
        if not self.lazy:
            tools.append(read)
        tools.append(self._media_button())
        # a lane of events only (Activity, Requests…): "Clear" — every notification, on
        # the server too (where the server can)
        self.clear_btn = None
        if self.lm.events_only():
            self.clear_btn = Gtk.Button(label=_("activity_clear"))
            tip(self.clear_btn, _("activity_clear_tip"))
            self.clear_btn.connect("clicked", lambda _b: self.clear())
            self.clear_btn.set_visible(ctx.supports("dismiss"))
            tools.append(self.clear_btn)
        refresh = Gtk.Button()  # as Qt's: the theme's picture alone, or the words
        self._dress(refresh, "refresh", _("refresh") + " (F5)")
        tip(refresh, _("refresh") + " (F5)")
        refresh.connect("clicked", lambda _b: ctx.view.refresh_by_hand())
        tools.append(refresh)
        self.append(header)

        self.older = Gtk.Button(label=_("older_down") if self.newest_first else _("older_up"))
        self.older.add_css_class("flat")
        self.older.connect("clicked", lambda _b: self.load_older())
        self.older.set_visible(False)  # only once the oldest stored post is on screen

        self.list = Body(self)  # the cards at their places (the strip's)
        self.list.add_css_class("ft-feed")
        self.list.set_overflow(Gtk.Overflow.HIDDEN)
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
        # reading.older_ahead: the "older" end in sight — the core fetches a page itself
        self.adj.connect("value-changed", lambda _a: self._older_in_sight())
        self.adj.connect("changed", lambda _a: self._apply_target())
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
        if self.clear_btn is not None:  # the server may have said it can't, meanwhile
            self.clear_btn.set_visible(self.ctx.supports("dismiss"))
        # a live lane the server gives empty (mastodon.social and the like keep them
        # for their own): said in the lane, big, as Qt does
        self.empty_note.set_visible(bool(getattr(built, "empty", False)))
        specs = built.specs
        old_sep = self.sep_above[0] if self.sep_above else None
        anchor = self._reading_anchor() if self.positioned and self.order else None
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
        del old_keys
        for k in [k for k in self.order if k not in index]:
            self._remove(k)
        new_sep = self.sep_above[0] if self.sep_above else None
        if new_sep != old_sep:  # the "new below" line moved: its cards made again
            for k in (old_sep, new_sep):
                if k in self.rows:
                    self._remove(k)
        self.strip.set_keys(keys)
        self._waiting = [k for k in self._waiting if k in index and k not in self.rows]
        for k in self.order:  # "you replied" under what's on screen: a reply just sent
            card = self.rows[k]
            if isinstance(card, EventRow) and card.ids != EventRow.ids_of(self.specs[k]):
                card.update_spec(self.specs[k])  # its events changed: one more like…
            card.set_unread(k in self.unread)
            self.rows[k].set_my_replies(self.specs[k].extra.get("my_replies", ()))
        self._pill(len(self.unread))
        self._lay_out()
        if not self.positioned:
            self._open(specs)
        elif anchor is not None:
            self._hold_at(anchor)
        self._realize()
        self._older_visible()

    def apply_read(self, ids):
        """Posts marked read (here as they were seen, or anywhere else): their marks
        go, nothing is rebuilt — a whole refresh for every few posts seen while
        scrolling was most of what a long lane cost (as Qt's apply_read)."""
        ids = set(ids)
        gone = [k for k in self.unread if self.specs.get(k) is not None
                and self.specs[k].entry is not None  # an event's row: seen, not read
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

    def apply_seen(self, mark):
        """Events seen up to `mark`: their rows lose the unread mark in place (as Qt's
        apply_seen) — a rebuild of every event lane at each mark froze the window."""
        gone = [k for k, sort in self.lm.event_sorts.items()
                if sort and sort <= mark and k in self.unread]
        for k in gone:
            self.unread.discard(k)
            if self.specs.get(k) is not None:
                self.specs[k] = replace(self.specs[k], unread=False)
            card = self.rows.get(k)
            if card is not None:
                card.set_unread(False)
        if gone:
            self._pill(len(self.unread))

    def _reset(self):
        """Another filter or view: the lane anew, placed anew."""
        for k in list(self.order):
            self._remove(k)
        self._waiting = []
        self.keys, self.index = [], {}
        self.strip.set_keys([])
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

    def _dress(self, button, picture, words, keep_words=False):
        """A header button as Qt's: the theme's picture (with the words beside it when
        keep_words), or the words alone when the theme has none."""
        from . import icons
        img = icons.image(picture, self.ctx.theme, 16)
        if img is None:
            button.set_label(words)
            return
        if keep_words:
            box = Gtk.Box(spacing=4)
            box.append(img)
            box.append(Gtk.Label(label=words))
            button.set_child(box)
        else:
            button.set_child(img)

    def _media_button(self):
        """The funnel: posts with pictures, gifs, video… only, boosts or not."""
        from . import icons
        funnel = icons.image("filter", self.ctx.theme, 16)
        button = Gtk.MenuButton(label="▾ " + _("media_filter")) if funnel is None \
            else Gtk.MenuButton(child=funnel)
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
        """Where reading starts (common/lane.py start()): the screen goes there — the
        first unread at the top (or its bottom, newest first), else the newest end."""
        self.positioned = True
        if not self.keys:
            return
        key, where = self.lm.start(specs)
        if key == SEPARATOR:
            key = self.sep_above[0] if self.sep_above else None
        if key is None and self.unread:  # the first unread
            key = next((k for k in self.keys if k in self.unread), None)
            where = "bottom" if self.newest_first else "top"
        if key in self.index:
            self._go(key, where)
        else:
            self._go_end(self.newest_first)
        self._schedule_seen()

    def _pending(self):
        """Cards near the screen still to be built."""
        return bool(self._waiting)

    # ---- the places --------------------------------------------------------------------
    def _width_now(self):
        w = self.list.get_width()
        if w <= 0:
            w = self.scroll.get_width() - 16
        return max(50, w)

    def _lay_out(self):
        """Every place again (common/strip.py), the body as tall as them all."""
        total = self.strip.lay_out(self._width_now())
        if total != self.list.total:
            self.list.total = total
            self.list.queue_resize()
        else:
            self.list.queue_allocate()

    def _relayout(self):
        """Cards measured another height than their places: the places anew, the
        reading place held."""
        if self.stopped:
            return GLib.SOURCE_REMOVE
        anchor = self._reading_anchor()
        self._lay_out()
        if anchor is not None:
            self._hold_at(anchor)
        self._realize()
        return GLib.SOURCE_REMOVE

    def _width_changed(self):
        """Another width (the window, ↔): the places for it, the reading place held."""
        if self.stopped or self.list.get_width() == self.strip.width:
            return GLib.SOURCE_REMOVE
        return self._relayout()

    def _offset(self):
        """The body's top in the scrolled column ("Older" or the empty note above it)."""
        y = y_in(self.list, self.clamp)  # (not the viewport: it moves with the scroll)
        return y or 0

    def _top(self):
        """The screen's top in the body's coordinates."""
        return self.adj.get_value() - self._offset()

    def _reading_anchor(self):
        t = self._target
        if t is not None and t[0] != "end" and time.monotonic() < t[2] and \
                t[0] in self.strip.ys:
            return t[0], t[1]
        return self.strip.anchor(max(0, self._top()))

    def _hold_at(self, anchor, seconds=HOLD_S):
        """The card of anchor (key, offset from the screen's top) kept there while the
        places settle — the upper bound changes after GTK allocates, so it is put back
        then too (_apply_target)."""
        self._target = (anchor[0], anchor[1], time.monotonic() + seconds)
        self._apply_target()

    def _go(self, key, where="top"):
        """The screen to key's place: its top a little below the screen's top, or
        (where="bottom") its bottom at the screen's bottom."""
        y = self.strip.ys.get(key)
        if y is None:
            return
        if where == "bottom":
            off = self.adj.get_page_size() - self.strip.height(key) - 40
        else:
            off = 40
        self._hold_at((key, off))

    def _go_end(self, newest_first):
        self._target = ("end", newest_first, time.monotonic() + HOLD_S)
        self._apply_target()

    def _apply_target(self):
        t = self._target
        if t is None:
            return
        if time.monotonic() > t[2]:
            self._target = None
            return
        page, upper = self.adj.get_page_size(), self.adj.get_upper()
        top = self._target_top()
        if top is None:
            self._target = None
            return
        value = max(0, min(top + self._offset(), upper - page))
        self._applied = upper
        if abs(self.adj.get_value() - value) > 0.5:
            self._setting = True
            try:
                self.adj.set_value(value)
            finally:
                self._setting = False

    def _target_top(self):
        """Where the screen's top is going, in the body (the target's), or None."""
        t = self._target
        if t is None:
            return None
        if t[0] == "end":
            return 0 if t[1] else max(0, self.strip.total - self.adj.get_page_size())
        return self.strip.top_for((t[0], t[1]))

    # ---- which cards exist -------------------------------------------------------------
    def _realize(self):
        """The cards near the screen built (those on it at once, the rest a few at a
        time), the ones gone far let go."""
        if self.stopped or not self.keys:
            return
        page = self.adj.get_page_size() or 600
        going = self._target_top() if self._target is not None and \
            time.monotonic() < self._target[2] else None
        # on its way somewhere (GTK places the screen after it allocates): the cards
        # there, not where the screen stands this moment
        top = max(0, going if going is not None else self._top())
        want = self.strip.wanted(top, page, AHEAD, self._held)
        wanted = set(want)
        gone = [k for k in self.order if k not in wanted]
        for k in gone:
            self._remove(k)
        if gone:  # their memory back to the system once the scrolling settles
            diag.trim_soon("cards scrolled past")
        now = self.strip.on_screen(want, top, page, self._held)
        made = [k for k in now if k not in self.rows]
        if made:
            with diag.busy(f"gtk lane {self.name}: build"):
                for k in made:
                    self._make(k)
        self._waiting = self.strip.by_nearness([k for k in want if k not in self.rows],
                                               top, page)
        if self._waiting and not self._more:
            self._more = GLib.idle_add(self._build_more, priority=GLib.PRIORITY_LOW)
        if made:
            self.list.queue_allocate()
        if not self._waiting:
            self._done_building()

    def _build_more(self):
        """A few of the cards beyond the screen, SLICE_MS at most, then a frame."""
        self._more = 0
        if self.stopped or self.get_root() is None:
            self._waiting = []
            return GLib.SOURCE_REMOVE
        until = time.monotonic() + SLICE_MS / 1000
        with diag.busy(f"gtk lane {self.name}: build"):
            while self._waiting and time.monotonic() < until:
                k = self._waiting.pop(0)
                if k in self.index and k not in self.rows:
                    self._make(k)
        self.list.queue_allocate()
        if self._waiting:
            self._more = GLib.idle_add(self._build_more, priority=GLib.PRIORITY_LOW)
        else:
            self._done_building()
        return GLib.SOURCE_REMOVE

    def _done_building(self):
        self._older_visible()
        self._schedule_seen()  # new cards may be on screen already

    def _make(self, k):
        sp = self.specs[k]
        if sp.extra.get("event"):  # a like, a follow, a request… in any lane
            card = EventRow(self.ctx, sp)
        else:
            card = Card(self.ctx, k, sp.entry, parent=sp.parent, unread=sp.unread,
                        short_id=sp.extra.get("short_id"),
                        my_replies=sp.extra.get("my_replies", ()),
                        via=sp.extra.get("via"), open_at=sp.open_at)
            line = conversation_line(sp)
            if line:
                card.add_conversation(*line)
            news = thread_news_bit(sp)
            if news is not None:
                card.add_thread_news(news)
            if sp.extra.get("deleted"):  # gone from its server, kept here
                from ..common.cardtext import Bit
                card.add_thread_news(Bit("🗑 " + _("deleted_mark"), "",
                                         _("deleted_mark_tip")))
        if self.sep_above and k == self.sep_above[0]:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            box.append(Separator(self.sep_above[1]))
            box.append(card)
        else:
            box = card
        box.set_parent(self.list)
        mw = box.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
        if mw > self.list.min_width:
            self.list.min_width = mw
            self.list.queue_resize()
        self.rows[k] = card
        self.boxes[k] = box
        i = self.index[k]
        lo, hi = 0, len(self.order)
        while lo < hi:  # the order of the lane: a bisection
            mid = (lo + hi) // 2
            if self.index.get(self.order[mid], -1) < i:
                lo = mid + 1
            else:
                hi = mid
        self.order.insert(lo, k)

    def _first_visible(self):
        """The first card reaching below the screen's top (by the places)."""
        a = self.strip.anchor(max(0, self._top()))
        return a[0] if a is not None and a[0] in self.rows else None

    def _remove(self, key):
        self.rows.pop(key, None)
        box = self.boxes.pop(key, None)
        if key in self.order:
            self.order.remove(key)
        if box is not None:
            box.unparent()
            forget(box)

    def _older_visible(self):
        """'Earlier' only when the oldest post stored is on screen (or nothing is)."""
        if self.lm.events_only():  # nothing older to fetch: events come with the poll
            self.older.set_visible(False)
            return
        if not self.keys:
            self.older.set_visible(not self.lazy)
            return
        oldest = self.keys[-1] if self.newest_first else self.keys[0]
        self.older.set_visible(oldest in self.rows and not self._pending())

    def _grow(self):
        """The cards near the screen now (scrolled): what was _grow in the run of rows."""
        self._realize()

    def _pill(self, n):
        self.pill.set_visible(n > 0)
        if n:
            self.pill.set_text(_("new_n", n=n))
        # nothing new: it still works — to the newest end of the lane (as Qt says)
        tip(self.to_new, _("to_new_tip") if n else _("to_end_tip"))

    def update_post(self, post):
        for card in self.rows.values():
            if card.entry is not None and real(card.entry).id == post.id:
                card.update(replace(card.entry, post=post) if isinstance(card.entry, Share)
                            else post)

    # ---- position and reading --------------------------------------------------------
    def shown(self):
        """The lane came on screen: catch up if it changed meanwhile, place it."""
        if self.lm.read_on_open():  # read.mark_read (common/lane.py decides)
            GLib.idle_add(lambda: self.mark_all_read() and False)
        if self.dirty:
            self.refresh()
        else:
            GLib.idle_add(self._relayout, priority=GLib.PRIORITY_LOW)  # its width now

    def hidden(self):
        """Another lane in front: "unread only" shows anew what's unread next time; out
        of sight for unload_hidden_minutes, its cards go (as Qt's)."""
        if self.lm.left():
            self.dirty = True
            self._drop_cards()
        minutes = self.ctx.cfg["ui"].get("unload_hidden_minutes", 0)
        if minutes:
            if getattr(self, "_unload_src", None):
                GLib.source_remove(self._unload_src)
            self._unload_src = GLib.timeout_add_seconds(
                int(minutes * 60), lambda: (setattr(self, "_unload_src", None),
                                            self.unload(), False)[-1])

    def _drop_cards(self):
        for k in list(self.order):
            self._remove(k)
        self._waiting = []
        self.keys, self.index = [], {}
        self.strip.set_keys([])
        self.positioned = False
        self._target = None

    def unload(self):
        """Its cards let go (ui.keep_hidden_lanes / unload_hidden_minutes,
        common/lanekeep.py); drawn anew when shown. → False: on screen, it stays."""
        if self.get_mapped():
            return False
        if self.order:
            log.info("lane %s unloaded: %d cards let go", self.name, len(self.order))
            self._drop_cards()
            self.dirty = True
            diag.trim_soon("a lane unloaded")
        return True

    def bring(self, key, then=None):
        """key's card on screen near the top — built there if it wasn't (find, a link
        to a post far away); then(card) once it's there."""
        if key not in self.index:
            return
        self._held = {key}
        self.positioned = True  # placed here, not where reading starts
        self._go(key)
        self._realize()
        if then is not None and key in self.rows:
            then(self.rows[key])

    def jump_first_unread(self):
        """↓ To new: the first unread at the top, or — nothing new — the lane's newest
        end."""
        self._held = set()
        target = next((k for k in self.keys if k in self.unread), None)
        if target is not None:
            self._go(target)
        elif self.keys:
            self._go_end(self.newest_first)
        self._realize()

    def _position(self):
        """Placed where reading starts (common/lane.py start()), once."""
        if not self.positioned and self.get_root() is not None:
            self._open([self.specs[k] for k in self.keys])
            self._realize()
        return GLib.SOURCE_REMOVE

    def _y(self, widget):
        """A card's top in the body (its place), or None."""
        key = getattr(widget, "key", None)
        if key is None:
            key = next((k for k, c in self.rows.items() if c is widget), None)
        return self.strip.ys.get(key) if key in self.rows else None

    def _scrolled(self):
        if self._target is not None and not getattr(self, "_setting", False):
            if self.adj.get_upper() != getattr(self, "_applied", None):
                self._apply_target()  # GTK clamped it to a new height: back on target
            else:  # moved by the reader: it goes where the reader goes
                self._target = None
                self._held = set()
        self._schedule_seen()
        self._realize()

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
        vtop = self._top()
        vbot = vtop + self.adj.get_page_size()
        at_end = self.adj.get_value() >= self.adj.get_upper() - self.adj.get_page_size() - 1
        keys, unplaced, glimpsed = [], False, set()
        for k in self.order:
            card = self.rows[k]
            if not card.unread:
                continue
            y, h = self.strip.ys.get(k), self.strip.h.get(k)
            if y is None or h is None:
                unplaced = True  # not measured yet: look again in a moment
                continue
            got = seen(y, y + h[1], vtop, vbot, at_end, k in self._glimpsed)
            if got == "read":
                keys.append(k)
            elif got == "glimpsed":
                glimpsed.add(k)
        self._glimpsed = (self._glimpsed & self.unread) | glimpsed
        if unplaced:
            self._schedule_seen()
        # an event's row goes by its key ("event:<id>"): LaneModel.read marks the events
        # seen (up to the newest of them) and gives back the posts to mark read
        events = [k for k in keys if self.rows[k].entry is None]
        posts = [k for k in keys if self.rows[k].entry is not None]
        ids = self.lm.read(events + [self.rows[k].entry.id for k in posts])
        done = events + (posts if ids else [])
        for k in done:
            self.rows[k].set_unread(False)
        self.unread -= set(done)
        self._glimpsed -= set(done)
        if ids:
            self.ctx.view.mark_read(ids)
        if done:
            self._pill(len(self.unread))
        return GLib.SOURCE_REMOVE

    def apply_width(self):
        """ui.max_width changed (↔): the column follows."""
        set_clamp(self.clamp, _width(self.ctx.cfg))

    def stop(self):
        """The window closes: whatever is queued is dropped (the core may close too)."""
        self.stopped = True
        self._waiting = []
        for attr in ("_more", "_seen_timer"):
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

    def clear(self):
        """Every notification gone, on the server too (a lane of events only): asked
        first."""
        view = self.ctx.view
        self.ctx.win.confirm(_("activity_clear"), _("activity_clear_q"),
                             lambda: self.ctx.win.call(view.clear_activity()))

    def load_older(self, fut=None):
        self.older.set_sensitive(False)

        def done(n):
            self.older.set_sensitive(True)
            self.older.set_label(_("no_older") if not n else
                                 _("older_down") if self.newest_first else _("older_up"))
        self.ctx.bridge.call(fut or self.ctx.view.load_older(self.name), done,
                             lambda err: (self.older.set_sensitive(True),
                                          self.ctx.status(_("error", err=err))))

    def _older_in_sight(self):
        """Within a screen of the "older" end: ask the core (core.older_ahead decides —
        the setting, one at a time, none after an empty page)."""
        if not self.older.get_visible() or not self.older.get_sensitive():
            return
        a = self.adj
        screen = a.get_page_size()
        near = a.get_value() >= a.get_upper() - 2 * screen if self.newest_first \
            else a.get_value() <= screen
        if near:
            fut = self.ctx.view.older_ahead(self.name)
            if fut is not None:
                self.older.set_label(_("loading"))
                self.load_older(fut)


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


class EventRow(Gtk.Box):
    """An event's row in any lane that takes events — Activity, Requests, a lane of
    one's own (common/activity.EventParts, the same parts every interface draws): who —
    what · when, the post it is about, × and a request's yes / no. Every button is a
    fedtail: link (common/links.py), handed to the window's link handler as a card's
    links are. Unread until seen on screen, as a post is; its key ("event:<id>") goes to
    LaneModel.read, so seen here is seen everywhere."""

    entry = None  # not a post: what looks for a card's post finds none here

    def __init__(self, ctx, spec):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.ctx, self.key = ctx, spec.key
        self.add_css_class("ft-card")
        self.unread = None
        self.update_spec(spec)

    @staticmethod
    def ids_of(spec):
        """The events in a spec's row: the same ones — the same row, nothing to redo."""
        return tuple(a.id for a in spec.extra.get("event") or ())

    def update_spec(self, spec):
        """The row drawn anew from its spec (its events changed: one more like…)."""
        from ..common.activity import ANSWER_WORDS, event_parts
        self.spec, self.ids = spec, self.ids_of(spec)
        while (child := self.get_first_child()) is not None:
            self.remove(child)
            forget(child)
        ctx = self.ctx
        parts = event_parts(spec.extra["row"], ctx.theme.date, ctx.supports("dismiss_one"))
        self.kind = parts.kind  # what it is about: tests, a stylesheet

        def follow(_label, uri):
            ctx.on_link(uri)
            return True
        esc = GLib.markup_escape_text
        if parts.notice:  # from the server itself: what happened, not who did it
            who = "<b>⚠ " + esc(parts.notice) + "</b>"
        else:
            who = ", ".join(link_markup(u, n) for n, u in parts.people)
            who += (" " + esc(parts.more)) if parts.more else ""
        line = Gtk.Label(xalign=0, wrap=True)
        line.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        line.set_markup(f"{who} <span alpha='70%'>— {esc(parts.what)}"
                        + (f" · {esc(parts.when)}" if parts.when else "") + "</span>")
        line.set_hexpand(True)
        if parts.tip:
            tip(line, parts.tip)
        line.connect("activate-link", follow)
        x = Gtk.Button(label="×", valign=Gtk.Align.START, halign=Gtk.Align.END)
        x.add_css_class("flat")
        tip(x, parts.hide_tip)
        x.connect("clicked", lambda _b, u=parts.hide: ctx.on_link(u))
        # the words and × beside them — not a horizontal box (the words wrap: GTK 4.18)
        self.append(side_by_side(line, x, 6))
        for yes, no in parts.answers:  # waiting for my yes: answered right here
            row = Gtk.Box(spacing=6)
            row.set_halign(Gtk.Align.END)
            for url, (words, about) in zip((yes, no), ANSWER_WORDS, strict=True):
                b = Gtk.Button(label=_(words))
                tip(b, _(about))
                if url == yes:
                    b.add_css_class("ft-primary")
                b.connect("clicked", lambda _b, u=url: ctx.on_link(u))
                row.append(b)
            self.append(row)
        if parts.post:
            post = Gtk.Label(xalign=0, wrap=True)
            post.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            post.set_markup(link_markup(parts.post_link, parts.post))
            post.add_css_class("ft-muted")
            post.connect("activate-link", follow)
            self.append(post)
        self.unread = None
        self.set_unread(spec.unread)

    def set_unread(self, on):
        on = bool(on)
        if on == self.unread:
            return
        self.unread = on
        (self.add_css_class if on else self.remove_css_class)("ft-unread")

    def set_my_replies(self, _replies):
        pass

    def update(self, _entry):
        pass
