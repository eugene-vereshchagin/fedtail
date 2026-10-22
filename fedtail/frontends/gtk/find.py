"""Ctrl+F in the GTK window, as in Qt: words to find in the lane in front — every post
of it, also those whose cards aren't built yet —, "3 of 7", ↑ ↓ (Enter, Shift+Enter)
round the end, Esc closes. "Deeper": everything stored for the lane (it is loaded down
to an older match); "In every lane": everything stored, lane by lane. What matches and
the words beside the box are common/find.py's; the lane brings a card on screen (LaneView.bring)."""

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
        self.deeper = Gtk.Button(label=_("find_deeper"))
        tip(self.deeper, _("find_deeper_tip"))
        self.deeper.connect("clicked", lambda _b: self.search_deeper())
        self.deeper.set_visible(False)
        self.append(self.deeper)
        self.everywhere = Gtk.CheckButton(label=_("find_everywhere"))
        tip(self.everywhere, _("find_everywhere_tip"))
        self.everywhere.set_active(bool(win.view.choice("find.everywhere", False)))
        self.everywhere.connect("toggled", lambda c: self._everywhere_toggled(c.get_active()))
        self.append(self.everywhere)
        for text, what, fn in (("↑", _("find_prev"), lambda: self.step(-1)),
                               ("↓", _("find_next"), lambda: self.step(1)),
                               ("✕", _("find_close"), self.close_bar)):
            b = Gtk.Button(label=text)
            b.add_css_class("flat")
            tip(b, what)
            b.connect("clicked", lambda _b, f=fn: f())
            self.append(b)
        self.view, self.hits, self.pos = None, [], -1
        # "in every lane": [{"lane", "item", "status_id", "index"}] from the core
        self.all_hits, self.all_pos, self._all_query, self._req = None, -1, None, 0
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
        if self.everywhere.get_active():
            if self.all_hits is None or self._all_query != self.entry.get_text():
                self._search_all(jump=True)
            elif self.all_hits:
                self.all_pos = rules.step(self.all_pos, len(self.all_hits), delta)
                self._go_all()
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
        if self.everywhere.get_active():
            self._search_all(jump)
            return
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
        query = self.entry.get_text()
        lane = self._lane()
        self.deeper.set_visible(bool(lane and query.strip())
                                and not self.everywhere.get_active())
        if self.everywhere.get_active():
            n = len(self.all_hits or ())
            text, over = rules.count_text(query, self.all_pos if self.all_hits else -1, n)
            self.count.set_text(text)
            (self.count.add_css_class if over else self.count.remove_css_class)("ft-over")
            return
        text, over = rules.count_text(query, self.pos, len(self.hits))
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

    # ---- deeper: everything stored for the lane ------------------------------------------
    def _lane(self):
        """The lane in front by name, if it is one (threads have no archive)."""
        view = self.win.current_lane_view()
        return getattr(view, "name", None) if hasattr(view, "load_older") else None

    def search_deeper(self):
        name, query = self._lane(), self.entry.get_text()
        if not name or not query.strip():
            return
        before = set(self.hits)
        self.deeper.set_sensitive(False)
        self.count.set_text(_("find_searching"))

        def done(res):
            self.deeper.set_sensitive(True)
            if not res["more"]:
                if not res["total"]:
                    self.count.set_text(_("find_archive_none"))
                else:
                    self._show_count()
                return
            # the lane grows when the core says so; then stand on the first new match
            GLib.timeout_add(400, lambda: (self._after_deeper(before), GLib.SOURCE_REMOVE)[1])
        self.win.call(self.win.view.deep_find(name, query), done,
                      lambda e: (self.deeper.set_sensitive(True), self.win.error(e)))

    def _after_deeper(self, before):
        view = self.win.current_lane_view()
        if view is not None and getattr(view, "dirty", False):
            view.refresh()
        self.search(jump=False)
        fresh = [i for i, k in enumerate(self.hits) if k not in before]
        if fresh:
            oldest_first = self.win.cfg["feed"]["order"] == "oldest_first"
            self.pos = fresh[-1] if oldest_first else fresh[0]
            self._go()

    # ---- in every lane ------------------------------------------------------------------
    def _everywhere_toggled(self, on):
        self.win.view.set_choice("find.everywhere", bool(on))
        self._mark(None)
        self.all_hits, self.all_pos, self._all_query = None, -1, None
        self.hits, self.pos = [], -1
        if self.get_visible():
            self.search(jump=True)

    def _search_all(self, jump):
        query = self.entry.get_text()
        self._req += 1
        req = self._req
        if not query.strip():
            self._mark(None)
            self.all_hits, self.all_pos, self._all_query = None, -1, None
            self._show_count()
            return
        if query == self._all_query and self.all_hits is not None:
            self._show_count()
            return
        self.count.set_text(_("find_searching"))

        def got(res, query=query):
            if req != self._req:  # typed on meanwhile
                return
            here = set(self.win.lane_rows)
            self.all_hits = [h for h in res or () if h["lane"] in here]
            self._all_query, self.all_pos = query, -1
            if not self.all_hits:
                self._mark(None)
                self._show_count()
                return
            # first the matches in the lane on screen
            lane = self._lane()
            mine = [i for i, h in enumerate(self.all_hits) if h["lane"] == lane]
            self.all_pos = mine[0] if mine else 0
            if jump:
                self._go_all()
            else:
                self._show_count()
        self.win.call(self.win.view.find_everywhere(query), got)

    def _go_all(self):
        if not self.all_hits or not 0 <= self.all_pos < len(self.all_hits):
            return
        hit = self.all_hits[self.all_pos]
        name = hit["lane"]
        self._mark(None)
        if name != self._lane():
            self.win.select_lane(name)
        view = self.win.lane_views.get(name)
        if view is None:
            return
        self.view = view
        if self.win.view.reveal_in_lane(name, hit["index"]) or view.dirty:
            view.refresh()  # loaded down to the match
        key = hit["item"] if hit["item"] in view.specs else next(
            (k for k, sp in view.specs.items() if sp.entry is not None and
             hit["status_id"] in (sp.entry.id, getattr(sp.post, "id", None))), None)
        if key is not None:
            view.bring(key, lambda card: self._mark(card))
        self._show_count()
