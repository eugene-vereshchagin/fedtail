"""Ctrl+F in the GTK window, as in Qt: words to find in the lane in front — every post
of it, also those whose cards aren't built yet —, "3 of 7", ↑ ↓ (Enter, Shift+Enter)
round the end, Esc closes. What matches and the words beside the box are
common/find.py's; the lane brings a card on screen (LaneView.bring)."""

from __future__ import annotations

from ...i18n import _
from ..common import find as rules
from .gi_setup import Gdk, GLib, Gtk, tip


class FindBar(Gtk.Box):
    def __init__(self, win):
        super().__init__(spacing=6)
        self.win = win
        self.add_css_class("ft-findbar")
        for m in ("start", "end", "top", "bottom"):
            getattr(self, "set_margin_" + m)(4)
        self.entry = Gtk.SearchEntry(hexpand=True, placeholder_text=_("find_placeholder"))
        self.append(self.entry)
        self.count = Gtk.Label()
        self.count.add_css_class("ft-muted")
        self.append(self.count)
        for text, what, fn in (("↑", _("find_prev"), lambda: self.step(-1)),
                               ("↓", _("find_next"), lambda: self.step(1)),
                               ("✕", _("find_close"), self.close_bar)):
            b = Gtk.Button(label=text)
            b.add_css_class("flat")
            tip(b, what)
            b.connect("clicked", lambda _b, f=fn: f())
            self.append(b)
        self.view, self.hits, self.pos = None, [], -1
        self._marked = None
        self._timer = 0
        self.entry.connect("search-changed", lambda _e: self._soon())
        self.entry.connect("activate", lambda _e: self.step(1))
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key)
        self.entry.add_controller(keys)
        self.set_visible(False)

    # ---- public ---------------------------------------------------------------------
    def open(self):
        if self.get_visible() and self.entry.has_focus() and self.entry.get_text().strip():
            self.step(1)  # Ctrl+F once more: the next match
            return
        self.set_visible(True)
        self.entry.grab_focus()
        if self.entry.get_text():
            self.search(jump=True)

    def close_bar(self):
        self._mark(None)
        self.set_visible(False)

    def step(self, delta):
        if not self.get_visible():
            self.open()
            return
        self.search(jump=False)
        if not self.hits:
            return
        self.pos = rules.step(self.pos, len(self.hits), delta)
        self._go()

    # ---- searching -------------------------------------------------------------------
    def _soon(self):
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(200, self._fire)

    def _fire(self):
        self._timer = 0
        self.search(jump=True)
        return GLib.SOURCE_REMOVE

    def search(self, jump):
        view = self.win.current_lane_view()
        if view is not self.view:
            self._mark(None)
            self.view, self.pos = view, -1
        query = self.entry.get_text()
        old = self.hits[self.pos] if 0 <= self.pos < len(self.hits) else None
        self.hits = rules.hits([view.specs[k] for k in view.keys], query) \
            if view is not None else []
        if old in self.hits:
            self.pos = self.hits.index(old)
        elif jump and self.hits:
            self.pos = 0
            self._go()
            return
        else:
            self.pos = -1
            self._mark(None)
        self._show_count()

    def _go(self):
        key = self.hits[self.pos]
        self._mark(None)
        self.view.bring(key, lambda card: self._mark(card))
        self._show_count()

    def _mark(self, card):
        if self._marked is not None:
            self._marked.remove_css_class("ft-found")
        self._marked = card
        if card is not None:
            card.add_css_class("ft-found")

    def _show_count(self):
        text, over = rules.count_text(self.entry.get_text(), self.pos, len(self.hits))
        self.count.set_text(text)
        (self.count.add_css_class if over else self.count.remove_css_class)("ft-over")

    def _key(self, _ctl, keyval, _code, state):
        if keyval == Gdk.KEY_Escape:
            self.close_bar()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.step(-1 if state & Gdk.ModifierType.SHIFT_MASK else 1)
            return True
        return False
