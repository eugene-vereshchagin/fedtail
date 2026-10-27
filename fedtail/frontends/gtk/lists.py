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


def lane_menu(win, row):
    """A right click on a list in the sidebar, as in Qt: who's in it, up / down, rename,
    exclusive (its people's posts out of Home), delete; on another lane — a new list."""
    view, core = win.view, win.core
    name = row.name
    pop = Gtk.Popover()
    pop.set_has_arrow(False)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    def item(label, fn, sensitive=True):
        b = Gtk.Button(label=label)
        b.add_css_class("flat")
        b.get_child().set_xalign(0)
        b.set_sensitive(sensitive)
        b.connect("clicked", lambda _b: (pop.popdown(), fn()))
        box.append(b)
        return b
    if name.startswith("list:"):
        lid = name[len("list:"):]
        lists = list(view.lists)
        x = next((y for y in lists if y.id == lid), None)
        if x is None:
            return None
        ids = [y.id for y in lists]
        item(_("list_people"), lambda: open_list_people(win, x))
        item(_("list_up"), lambda: win.call(core.submit(core.move_list, x.id, -1)),
             ids.index(x.id) > 0)
        item(_("list_down"), lambda: win.call(core.submit(core.move_list, x.id, 1)),
             ids.index(x.id) < len(ids) - 1)
        box.append(Gtk.Separator())
        item(_("list_rename"), lambda: _rename(win, x))
        ex = Gtk.CheckButton(label=_("list_exclusive"))
        ex.set_active(x.exclusive)
        from .gi_setup import tip
        tip(ex, _("list_exclusive_tip"))
        ex.connect("toggled", lambda c: win.call(core.update_list(x.id, x.title,
                                                                   c.get_active())))
        box.append(ex)
        _replies_choice(box, win, core, x)
        box.append(Gtk.Separator())
        item(_("list_delete"), lambda: win.confirm(
            _("list_delete"), _("list_delete_q", title=x.title),
            lambda: win.call(core.delete_list(x.id))))
    elif name.startswith("tags:"):  # a group of tags: out of the sidebar, as Qt's
        from ...core import taggroups
        g = next((g for g in view.tag_groups
                  if f"tags:{taggroups.key(g)}" == name), None)
        drop = item(_("tags_drop"), lambda: win.call(core.drop_tag_group(name)))
        from .gi_setup import tip
        if g is not None and not g.get("saved"):
            drop.set_sensitive(False)  # from the config: taken out there
            tip(drop, _("tags_in_config"))
        elif g is not None:  # its posts in Home too, or only here (as Qt's menu)
            home = Gtk.CheckButton(label=_("tags_in_home"))
            home.set_active(not g.get("not_in_home"))
            tip(home, _("tags_in_home_tip"))
            home.connect("toggled", lambda c: win.call(
                core.set_tag_group_in_home(name, c.get_active())))
            box.append(home)
    elif win.cfg["lists"]["enabled"]:
        item(_("list_new"), win.new_list)
    if not name.startswith(("list:", "tags:")) and name in view.lane_by_name and \
            name not in ("activity", "requests"):
        item(_("le_edit_lane"), lambda: win.open_place("lane", name))
    item(_("le_title") + "…", lambda: win.open_place("lanes"))
    pop.set_child(box)
    pop.set_parent(row)
    pop.connect("closed", lambda p: p.unparent())
    pop.popup()
    return pop


def _replies_choice(box, win, core, x):
    """Whose replies the list's lane shows (the server's replies_policy): three radio
    buttons, the list's own picked."""
    from ..common import timed
    from .gi_setup import tip
    head = Gtk.Label(label=_("replies_policy"), xalign=0)
    head.add_css_class("ft-muted")
    tip(head, _("replies_policy_tip"))
    box.append(head)
    now = x.replies or "list"  # the server's default when it doesn't say
    first, radios = None, {}
    for key, label in timed.replies_policies():
        r = Gtk.CheckButton(label=label)
        if first is None:
            first = r
        else:
            r.set_group(first)
        r.set_active(key == now)
        tip(r, _("replies_policy_tip"))
        r.connect("toggled", lambda c, k=key: c.get_active() and k != now and win.call(
            core.update_list(x.id, x.title, x.exclusive, replies_policy=k)))
        radios[key] = r
        box.append(r)
    return radios


def _rename(win, x):
    from .dialogs import ask_text

    def done(title):
        if title != x.title:
            win.call(win.core.update_list(x.id, title, x.exclusive))
    ask_text(win, _("list_rename"), _("list_name_q"), done, x.title)


def open_list_people(win, x):
    """Who is in a list: a tab of people, each taken out right there (×)."""
    from .people import open_people
    return open_people(win, f"list-people:{x.id}", _("list_people_title", title=x.title),
                       lambda _cursor: win.view.list_people(x.id),
                       dismiss=lambda acc_id: win.core.set_in_list(x.id, acc_id, False),
                       dismiss_label=_("list_take_out"))
