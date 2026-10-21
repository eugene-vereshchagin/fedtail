""""Add to list" in the GTK window, as Qt's submenu: every list of mine, ticked where
the person is; a server takes only people I follow into lists, so for someone else the
ticks are dead under "follow first", with Follow right there — and until the server
says which it is, dead too. A new list made with them in it."""

from __future__ import annotations

from ...i18n import _
from ...model import Relationship
from .gi_setup import Gtk


def list_open(rel, inside):
    """May the ticks be used: someone I follow (or asked to), or already in a list
    (taking out is always fine). Not known yet (None): no."""
    if inside:
        return True
    return rel is not None and bool(rel.following or rel.requested)


def popover(win, account, anchor):
    """The lists for account, in a popover at anchor (a button)."""
    view = win.view
    pop = Gtk.Popover()
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    for m in ("start", "end", "top", "bottom"):
        getattr(box, "set_margin_" + m)(6)
    inside = set(view.lists_of(account.id) or ())
    note = Gtk.Label(label=_("list_checking"), xalign=0, wrap=True)
    note.add_css_class("ft-muted")
    box.append(note)
    follow = Gtk.Button(label=_("follow"))
    follow.set_visible(False)

    def do_follow(_b):
        pop.popdown()
        win.call(view.follow(account.id),
                 lambda rel: win.status(_("followed_now", acct="@" + account.handle)
                                        if rel.following else _("follow_asked_list")))
    follow.connect("clicked", do_follow)
    box.append(follow)
    ticks = []
    for x in view.lists:
        c = Gtk.CheckButton(label=x.title)
        c.set_active(x.id in inside)
        c.list_id = x.id
        ticks.append(c)
        box.append(c)

    def toggled(c):
        if not c.get_sensitive():
            return
        on = c.get_active()
        win.call(view.set_in_list(c.list_id, account.id, on),
                 lambda r: win.status(_("list_pending") if r == "pending" else
                                      _("list_added" if on else "list_removed")))
    for c in ticks:
        c.connect("toggled", toggled)
    new = Gtk.Button(label=_("list_new"))
    new.add_css_class("flat")
    new.connect("clicked", lambda _b: (pop.popdown(), win.new_list(add=account.id)))
    box.append(new)

    def apply(rel):
        ok = list_open(rel, inside)
        for c in ticks:
            c.set_sensitive(ok)
        new.set_sensitive(ok)
        note.set_text(_("list_follow_first") if rel is not None else _("list_checking"))
        note.set_visible(not ok)
        follow.set_visible(not ok and rel is not None)
    rel = view.relation_known(account.id)
    apply(rel)
    if rel is None:
        win.call(view.relationship(account.id), apply, lambda _e: apply(Relationship()))
    pop.set_child(box)
    pop.set_parent(anchor)
    pop.connect("closed", lambda p: p.unparent())
    pop.popup()
    return pop
