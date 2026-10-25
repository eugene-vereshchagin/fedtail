"""A profile's posts in the GTK window, as Qt's: what they pinned first (📌), then page
after page from my server ("▼ older"); someone from another server mine knows little
about — their newest read from their own server at once; and once my server has nothing
older, "▼ older — from their server", a few posts at a time as mine fetches them."""

from __future__ import annotations

from ...i18n import _
from ...model import real
from ..common import timed
from .card import Card
from .gi_setup import Gtk, forget, tip

BATCH = 4  # posts my server fetches by address per call (seconds each)


class ProfilePosts:
    def __init__(self, win, box, acc):
        self.win, self.view, self.box, self.acc = win, win.view, box, acc
        self.items = []        # posts and boosts, newest first
        self.pinned = []
        self.cards = []        # the cards shown, in order
        self.first_page = None
        self.origin_asked = False
        self.older_origin = False
        self.origin_next = None
        self.host = ""
        self.show = timed.profile_show(win.cfg)  # posts / all / media (the switch)
        handle = acc.handle or ""
        if "@" in handle and win.cfg["feed"].get("remote_profiles", True):
            self.host = handle.split("@", 1)[1]
        self.switch = self._switch()
        box.append(self.switch)
        self.more_btn = Gtk.Button(label=_("older_down"))
        self.more_btn.add_css_class("flat")
        self.more_btn.connect("clicked", lambda _b: self.more())
        self.more_btn.set_visible(False)
        box.append(self.more_btn)
        if win.cfg["feed"].get("profile_pinned", True):
            win.call(self.view.pinned(acc.id), self._pinned, lambda _e: None)
        self.more()

    # ---- posts / posts and replies / media ------------------------------------------
    def _switch(self):
        """Three linked buttons, as other clients have: which of their posts to show."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        row.add_css_class("linked")
        row.set_halign(Gtk.Align.START)
        for side in ("top", "bottom", "start"):
            getattr(row, "set_margin_" + side)(4)
        self.show_buttons, first = {}, None
        for key, label in timed.profile_shows():
            b = Gtk.ToggleButton(label=label)
            tip(b, _("profile_show_tip"))
            if first is None:
                first = b
            else:
                b.set_group(first)
            b.set_active(key == self.show)
            b.connect("toggled", lambda b, k=key: b.get_active() and self.set_show(k))
            self.show_buttons[key] = b
            row.append(b)
        return row

    def set_show(self, show):
        """Another kind of posts: everything read again from the top."""
        if show == self.show:
            return
        self.show = show
        if not self.show_buttons[show].get_active():
            self.show_buttons[show].set_active(True)
        self.items, self.first_page = [], None
        self.origin_asked = self.older_origin = False
        self.origin_next = None
        self.more_btn.set_label(_("older_down"))
        tip(self.more_btn, "")
        self.render()
        self.more()

    def _keeps(self, e):
        return timed.keeps(e, self.show, self.acc.id)

    # ---- showing ----------------------------------------------------------------------
    def render(self):
        """Pinned first (marked), then the rest by time — the cards made anew (a
        profile's few dozen)."""
        for c in self.cards:
            gone = c.get_parent() or c
            self.box.remove(gone)
            forget(gone)
        self.cards = []
        top = {real(e).id for e in self.pinned}
        everything = self.pinned + [e for e in self.items if real(e).id not in top]
        short = self.view.short_ids(everything)
        at = self._first_index()
        for i, e in enumerate(everything):
            pin = i < len(self.pinned)
            card = Card(self.win.ctx, ("pin:" if pin else "") + e.id, e,
                        short_id=short.get(real(e).id))
            if pin:
                card.mark("📌 " + _("pinned"))
            self.box.insert(card, at + i)
            self.cards.append(card)

    def _first_index(self):
        """Where the posts start in the tab's list: after the head and "Posts"."""
        i, row = 0, self.box.get_row_at_index(0)
        while row is not None:
            child = row.get_child()
            if child is self.more_btn or isinstance(child, Card):
                return i
            i += 1
            row = self.box.get_row_at_index(i)
        return i

    def _merge(self, entries):
        known = {e.id for e in self.items}
        new = [e for e in entries or () if e.id not in known and self._keeps(e)]
        if new:
            self.items = sorted(self.items + new, key=lambda e: e.sort, reverse=True)
            self.view.ensure_parents(new)
            self.render()
        return new

    def _pinned(self, posts):
        self.pinned = list(posts or ())
        if self.pinned:
            self.render()

    # ---- my server's pages, then theirs -----------------------------------------------
    def more(self):
        if self.older_origin:
            return self._more_from_origin()
        self.more_btn.set_sensitive(False)
        last = self.items[-1].id if self.items else None
        want = self.show  # a page for a kind switched away from meanwhile: dropped
        self.win.call(self.view.account_posts(self.acc.id, last, show=want),
                      lambda page: want == self.show and self._page(page),
                      lambda e: (self.more_btn.set_sensitive(True), self.win.error(e)))

    def _page(self, page):
        page = list(page or ())
        if self.first_page is None:
            self.first_page = page
        self._merge(page)
        self.more_btn.set_visible(True)
        self.more_btn.set_sensitive(True)
        self._from_origin()
        if not page:
            self._offer_origin()

    def _offer_origin(self):
        """My server has nothing older: the button now reads further back from theirs."""
        if not self.host or self.older_origin:
            self.more_btn.set_label(_("no_older"))
            self.more_btn.set_sensitive(False)
            return
        self.older_origin = True
        self.more_btn.set_label(_("older_from_origin", host=self.host))
        tip(self.more_btn, _("older_from_origin_tip", host=self.host))
        self.more_btn.set_sensitive(True)

    def _more_from_origin(self):
        host, btn = self.host, self.more_btn
        btn.set_sensitive(False)
        btn.set_label(_("origin_asking", host=host))
        have = [real(e).uri for e in self.items if real(e).uri]
        shown = [0]

        def listed(r):
            # the addresses come fast; my server fetching each post is the slow part,
            # so they come in a few at a time and show as they come
            uris, self.origin_next = r
            if not uris:
                return done()
            btn.set_label(_("origin_fetching", n=0, total=len(uris), host=host))
            step(list(uris), len(uris))

        def step(left, total):
            batch, rest = left[:BATCH], left[BATCH:]

            def got(entries):
                shown[0] += len(self._merge(entries))
                if rest:
                    btn.set_label(_("origin_fetching", n=total - len(rest), total=total,
                                    host=host))
                    step(rest, total)
                else:
                    done()
            self.win.call(self.view.resolve_statuses(batch), got, failed)

        def done():
            if self.origin_next:
                btn.set_label(_("older_from_origin", host=host))
                btn.set_sensitive(True)
            else:
                btn.set_label(_("no_older"))
            self.win.status(_("origin_got", n=shown[0], host=host) + " · " +
                            _("older_from_origin_note"), seconds=8)

        def failed(e):
            btn.set_label(_("older_from_origin", host=host))
            btn.set_sensitive(True)
            self.win.error(e)
        self.win.call(self.view.older_from_origin(self.acc, self.origin_next, have,
                                                  resolve=False), listed, failed)

    def _from_origin(self):
        """Someone mine knows little about (fewer posts here than their profile counts):
        their newest read from their own server."""
        acc, page = self.acc, self.first_page
        if self.origin_asked or page is None or not self.host:
            return
        if len(page) >= min(acc.posts, self.win.cfg["feed"]["page_size"]):
            return  # my server has them
        self.origin_asked = True
        self.win.status(_("origin_asking", host=self.host), seconds=0)
        have = [real(e).uri for e in self.items]

        def got(entries):
            new = self._merge(entries)
            self.win.status(_("origin_got", n=len(new), host=self.host) if new else "",
                            seconds=6)
        self.win.call(self.view.posts_from_origin(acc, have), got,
                      lambda _e: self.win.status(""))
