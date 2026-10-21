"""The two lanes that aren't streams of posts, in GTK: Activity — who liked, boosted,
followed, a row per kind and post (common/activity.py makes the rows, as for Qt) — and
follow requests to let in or turn away."""

from __future__ import annotations

from ...i18n import _
from ...model.text import snippet, snippet_html
from ..common import activity
from .card import link_markup, name_of
from .gi_setup import GLib, Gtk, Pango
from .lane import seen, y_in

SEEN_DELAY_MS = 700


def _label(markup="", css=(), wrap=True):
    lab = Gtk.Label(xalign=0)
    lab.set_markup(markup)
    if wrap:
        lab.set_wrap(True)
        lab.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    for c in css:
        lab.add_css_class(c)
    return lab


class _Lane(Gtk.Box):
    """A header and a scrolled column of rows, rebuilt whole (these lanes are short)."""

    def __init__(self, win, title):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win, self.view = win, win.view
        self.dirty = True
        self.header = Gtk.Box(spacing=8)
        self.header.add_css_class("ft-lane-header")
        t = Gtk.Label(label=win.theme.word("lane_title", title), xalign=0)
        t.add_css_class("ft-lane-title")
        t.set_hexpand(True)
        self.header.append(t)
        self.append(self.header)
        self.list = Gtk.ListBox()
        self.list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list.add_css_class("ft-feed")
        self.list.set_margin_start(8)
        self.list.set_margin_end(8)
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.add_css_class("ft-view")
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_vexpand(True)
        self.scroll.set_child(self.list)
        self.append(self.scroll)
        self.adj = self.scroll.get_vadjustment()

    def _clear(self):
        while (row := self.list.get_first_child()) is not None:
            self.list.remove(row)

    def shown(self):
        if self.dirty:
            self.refresh()

    def stop(self):
        pass

    def window_activated(self):
        pass

    def update_post(self, _post):
        pass


class ActivityLane(_Lane):
    def __init__(self, win):
        super().__init__(win, _("lane_activity"))
        read = Gtk.Button(label=_("mark_all_read"))
        read.add_css_class("flat")
        read.connect("clicked", lambda _b: self.view.mark_activity_seen())
        self.header.append(read)
        self._seen_timer = 0
        self.positioned = False
        self.adj.connect("value-changed", lambda _a: self._schedule_seen())

    def refresh(self):
        self.dirty = False
        kept = self.adj.get_value() if self.positioned else None
        self._clear()
        oldest_first = self.win.cfg["feed"]["order"] == "oldest_first"
        rows = activity.rows(self.view.activity(), self.view.activity_seen(),
                             self.win.theme.date, oldest_first)
        if not rows:
            self.list.append(_label(_("activity_none"), ("ft-muted",)))
        first_new = None
        for r in rows:
            w = self._row(r)
            self.list.append(w)
            if r.unread and first_new is None:
                first_new = w
        GLib.idle_add(self._place, first_new, kept, oldest_first, priority=GLib.PRIORITY_LOW)

    def _place(self, first_new, kept, oldest_first):
        if kept is not None:
            self.adj.set_value(kept)
        elif first_new is not None and oldest_first:
            y = y_in(first_new, self.list)
            self.adj.set_value(max(0, (y or 0) - 14))
        elif oldest_first:
            self.adj.set_value(self.adj.get_upper())
        self.positioned = True
        self._schedule_seen()
        return GLib.SOURCE_REMOVE

    def _row(self, r):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.add_css_class("ft-card")
        if r.unread:
            box.add_css_class("ft-unread")
        box.newest_sort = r.newest_sort
        if r.notice:
            who = "<b>⚠ " + GLib.markup_escape_text(r.notice) + "</b>"
        else:
            who = ", ".join(link_markup(f"fedtail:account/{a.id}", name_of(a))
                            for a in r.people)
            if r.more:
                who += " " + GLib.markup_escape_text(_("act_more", n=r.more))
        top = Gtk.Box(spacing=6)
        line = _label(f"{who} <span alpha='70%'>— {GLib.markup_escape_text(r.what)}"
                      + (f" · {GLib.markup_escape_text(r.when)}" if r.when else "") + "</span>")
        line.set_hexpand(True)
        line.connect("activate-link", lambda _l, u: (self.win.on_link(u), True)[1])
        top.append(line)
        x = Gtk.Button(label="×")
        x.add_css_class("flat")
        x.set_tooltip_text(_("activity_dismiss_tip" if self.view.can_dismiss_one()
                             else "activity_hide_tip"))
        x.connect("clicked", lambda _b, ids=[a.id for a in r.entries]: self._dismiss(ids))
        top.append(x)
        box.append(top)
        if r.request:  # waiting for my yes (GoToSocial): answer right here, one by one
            for a in r.entries:
                row = Gtk.Box(spacing=6)
                row.set_halign(Gtk.Align.END)
                for ok in (True, False):
                    b = Gtk.Button(label=_("ok_interaction") if ok else _("no_interaction"))
                    if ok:
                        b.add_css_class("ft-primary")
                    b.connect("clicked", lambda _b, en=a, ok=ok: self._answer(en, ok))
                    row.append(b)
                box.append(row)
        if r.post is not None:
            post = _label(link_markup(f"fedtail:thread/{r.post.id}",
                                      "«" + snippet(r.post, 160) + "»"), ("ft-muted",))
            post.connect("activate-link", lambda _l, u: (self.win.on_link(u), True)[1])
            box.append(post)
        return box

    def _answer(self, entry, ok):
        self.win.call(self.view.answer_interaction(entry, ok),
                      lambda found: self.win.status(_(("approved" if ok else "rejected")
                                                      if found else "approval_gone")))

    def _dismiss(self, ids):
        for nid in ids:
            self.win.call(self.view.dismiss_activity(nid))

    def _schedule_seen(self):
        if not self._seen_timer:
            self._seen_timer = GLib.timeout_add(SEEN_DELAY_MS, self._mark_seen)

    def window_activated(self):
        self._schedule_seen()

    def stop(self):
        if self._seen_timer:
            GLib.source_remove(self._seen_timer)
            self._seen_timer = 0

    def _mark_seen(self):
        """Up to the newest row on screen: the mark is one point in time."""
        self._seen_timer = 0
        root = self.get_root()
        if root is None or not root.is_active() or not self.get_mapped():
            return GLib.SOURCE_REMOVE
        vtop = self.adj.get_value()
        vbot = vtop + self.adj.get_page_size()
        at_end = vtop + self.adj.get_page_size() >= self.adj.get_upper() - 2
        best = ""
        child = self.list.get_first_child()
        while child is not None:
            w = child.get_child() if isinstance(child, Gtk.ListBoxRow) else child
            sort = getattr(w, "newest_sort", "")
            y = y_in(w, self.list) if sort else None
            if y is not None:
                h = w.get_height()
                if seen(y, y + h, vtop, vbot) or (at_end and y < vbot and y + h > vtop):
                    best = max(best, sort)
            child = child.get_next_sibling()
        if best and best > (self.view.activity_seen() or ""):
            self.view.mark_activity_seen(best)
        return GLib.SOURCE_REMOVE


class RequestsLane(_Lane):
    """People asking to follow me (a locked account): let in or turn away."""

    def __init__(self, win):
        super().__init__(win, _("lane_requests"))

    def refresh(self):
        self.dirty = False
        self._clear()
        reqs = self.view.follow_requests()
        if not reqs:
            self.list.append(_label(_("no_requests"), ("ft-muted",)))
        for acc in reqs:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            box.add_css_class("ft-card")
            name = _label(f"<b>{GLib.markup_escape_text(name_of(acc))}</b> " +
                          link_markup(f"fedtail:account/{acc.id}", "@" + acc.handle))
            name.connect("activate-link", lambda _l, u: (self.win.on_link(u), True)[1])
            box.append(name)
            if acc.note:
                box.append(_label(GLib.markup_escape_text(snippet_html(acc.note, 300)),
                                  ("ft-muted",)))
            row = Gtk.Box(spacing=6)
            for ok in (True, False):
                b = Gtk.Button(label=_("approve") if ok else _("reject"))
                if ok:
                    b.add_css_class("ft-primary")
                b.connect("clicked", lambda _b, a=acc.id, ok=ok: self._answer(a, ok))
                row.append(b)
            box.append(row)
            self.list.append(box)

    def _answer(self, acc_id, ok):
        self.win.call(self.view.answer_follow(acc_id, ok), lambda _r: self.refresh())
