"""A big thread in a GTK tab, built only near the screen — as a lane is, and as the Qt
window's thread of more than THREAD_WINDOWED posts (12.11: one of hundreds of posts with
pictures held them all, some 300 MB, while its tab was open).

Every post has a slot in the tab's list from the start, a guessed height tall; a slot
coming within a screen of the screen gets its card, one going three screens away gives
it back and keeps the card's height, so nothing below moves. A card built above the
screen is measured before it is shown (Gtk.Widget.measure) and the scroll moved by what
it changed, in the same frame: the posts on screen stay where they are."""

from __future__ import annotations

from .gi_setup import GLib, Gtk

THREAD_WINDOWED = 40  # a thread of more posts: windowed (as Qt's feed.THREAD_WINDOWED)


class Slot(Gtk.Box):
    """Where one post of the thread stands; its card inside it while built."""

    def __init__(self, index, height):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.index = index
        self.set_size_request(-1, height)

    @property
    def card(self):
        return self.get_first_child()


class ThreadWindow:
    AHEAD = 1.0   # cards exist this many screens above and below the screen…
    KEEP = 3.0    # …and are let go this far away
    GUESS = 320   # a slot's height before its card was ever built

    def __init__(self, page, box, items, make):
        """page: the tab's Gtk.ScrolledWindow; box: its list; items: the thread's
        ThreadItems in reading order; make(item) -> its Card."""
        self.page, self.box, self.items, self.make = page, box, list(items), make
        self.fresh = {}       # post id -> a newer Post than its item's (status_updated)
        self.cw_open = False  # the header's "open every warning", for cards built later
        self.slots = []
        for i, _it in enumerate(self.items):
            slot = Slot(i, self.GUESS)
            self.slots.append(slot)
            box.append(slot)
        self._idle = 0
        adj = page.get_vadjustment()
        adj.connect("value-changed", lambda *_a: self.soon())
        adj.connect("notify::page-size", lambda *_a: self.soon())
        self.soon()

    # ---- what the window and the header ask -----------------------------------------
    def cards(self):
        """The cards built now, top to bottom."""
        return [s.card for s in self.slots if s.card is not None]

    def update_post(self, post):
        """A post changed (edited, counted): its card if built; the one built later
        from it too."""
        self.fresh[post.id] = post
        for card in self.cards():
            if card.entry is not None and card.entry.id == post.id:
                card.update(post)

    def set_cw(self, on):
        self.cw_open = on
        for card in self.cards():
            card.set_cw(on)

    def slot_of(self, post_id):
        return next((s for s, it in zip(self.slots, self.items, strict=True)
                     if it.post.id == post_id), None)

    def bring(self, post_id):
        """The slot of post_id with its card built (the focus: where the tab opens)."""
        slot = self.slot_of(post_id)
        if slot is not None and slot.card is None:
            self._build(slot)
        return slot

    # ---- the window ---------------------------------------------------------------
    def soon(self):
        if not self._idle:
            self._idle = GLib.idle_add(self._update)

    def _y(self, slot):
        from .lane import y_in
        return y_in(slot, self.box)

    def _build(self, slot):
        """slot's card made and put in; → how much taller the slot is now."""
        it = self.items[slot.index]
        post = self.fresh.get(it.post.id)
        card = self.make(it if post is None else _with_post(it, post))
        if self.cw_open:
            card.set_cw(True)
        width = slot.get_width() or self.box.get_width()
        was = slot.get_height() or self.GUESS
        tall = card.measure(Gtk.Orientation.VERTICAL, width)[1] if width > 0 else was
        slot.set_size_request(-1, -1)
        slot.append(card)
        return tall - was

    def _let_go(self, slot):
        card = slot.card
        tall = slot.get_height()
        slot.remove(card)
        slot.set_size_request(-1, max(1, tall))  # its place kept: nothing below moves

    def _update(self):
        self._idle = 0
        if self.box.get_root() is None:  # the tab closed
            return GLib.SOURCE_REMOVE
        adj = self.page.get_vadjustment()
        top, vh = adj.get_value(), adj.get_page_size() or 600
        lo, hi = top - self.AHEAD * vh, top + vh + self.AHEAD * vh
        far_lo, far_hi = top - self.KEEP * vh, top + vh + self.KEEP * vh
        ys = [self._y(s) for s in self.slots]
        if any(y is None for y in ys) or not self.slots[-1].get_height() or \
                (len(ys) > 1 and ys[-1] <= ys[0]):  # not laid out yet: after the next frame
            GLib.timeout_add(50, lambda: (self.soon(), GLib.SOURCE_REMOVE)[1])
            return GLib.SOURCE_REMOVE
        # the reading place: the first slot beginning on the screen (common/strip)
        anchor = next((i for i, y in enumerate(ys) if y >= top), None)
        moved = 0
        for slot, y in zip(self.slots, ys, strict=True):
            h = slot.get_height()
            if slot.card is None and y < hi and y + h > lo:
                grew = self._build(slot)
                if anchor is not None and slot.index < anchor:
                    moved += grew  # above the place read: the screen goes with it
            elif slot.card is not None and (y + h < far_lo or y > far_hi):
                self._let_go(slot)
        if moved:
            adj.set_value(adj.get_value() + moved)
        return GLib.SOURCE_REMOVE


def _with_post(item, post):
    from dataclasses import replace
    try:
        return replace(item, post=post)
    except TypeError:
        return item
