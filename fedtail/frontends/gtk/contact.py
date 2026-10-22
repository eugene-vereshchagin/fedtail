"""Who this is, as QIP showed a contact on hover (and Qt's split layout does): a card
beside the pointer a moment after it stays on a face — the name, the @address, how we
stand, the bio's first lines, how much they post and since when; it goes when the
pointer leaves or clicks. hover(win, widget, who) puts it on a widget."""

from __future__ import annotations

from ...i18n import _
from ...model.text import html_to_text
from .gi_setup import GLib, Gtk, Pango

DELAY_MS = 600
BIO_CHARS = 220


def lines(view, who, date):
    """[(text, css)] for the card: what Qt's ContactCard says, in its order."""
    out = [("@" + who.handle, "ft-muted")]
    rel = view.relation_known(who.id)
    if rel is not None:
        stand = _("faces_mutual") if rel.following and rel.followed_by else \
            _("faces_follows_me") if rel.followed_by else \
            _("following_them") if rel.following else ""
        if stand:
            out.append((stand, "ft-name"))
    bio = html_to_text(who.note or "").strip()
    if bio:
        out.append((bio[:BIO_CHARS] + ("…" if len(bio) > BIO_CHARS else ""), ""))
    if who.posts or who.followers:
        out.append((_("card_counts", posts=who.posts, followers=who.followers,
                       following=who.following), "ft-muted"))
    if who.created:
        out.append((_("card_since", when=date(who.created.isoformat())), "ft-muted"))
    if who.bot:
        out.append((_("bot"), "ft-muted"))
    return out


def card(win, who):
    """The card's content: the lines at the left, the face at the right."""
    from .card import Avatar
    box = Gtk.Box(spacing=10)
    for m in ("start", "end", "top", "bottom"):
        getattr(box, "set_margin_" + m)(6)
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    col.set_size_request(260, -1)
    name = Gtk.Label(label=who.name or who.username, xalign=0)
    name.add_css_class("ft-name")
    name.set_ellipsize(Pango.EllipsizeMode.END)
    col.append(name)
    for text, css in lines(win.view, who, win.theme.date):
        lab = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=40)
        lab.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        if css:
            lab.add_css_class(css)
        col.append(lab)
    # (a box of fixed parts, never a wrapping row: GTK 4.18's least height, measure.py)
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    row = Gtk.Overlay()
    col.set_margin_end(72)
    row.set_child(col)
    if win.ctx.images is not None:
        face = Avatar(win.ctx, who, 64)
        face.set_halign(Gtk.Align.END)
        face.set_valign(Gtk.Align.START)
        row.add_overlay(face)
    outer.append(row)
    box.append(outer)
    return box


def hover(win, widget, who):
    """The card of who() a moment after the pointer stays on widget."""
    state = {"timer": 0, "pop": None}

    def away(*_a):
        if state["timer"]:
            GLib.source_remove(state["timer"])
            state["timer"] = 0
        pop = state["pop"]
        if pop is not None:
            state["pop"] = None
            pop.popdown()

    def show():
        state["timer"] = 0
        acc = who()
        if acc is None or widget.get_root() is None:
            return GLib.SOURCE_REMOVE
        pop = Gtk.Popover(autohide=False, has_arrow=False)
        pop.add_css_class("ft-contact-card")
        pop.set_child(card(win, acc))
        pop.set_parent(widget)
        pop.connect("closed", lambda p: p.unparent())
        state["pop"] = pop
        pop.popup()
        rel = win.view.relation_known(acc.id)
        if rel is None:  # how we stand isn't known yet: asked, the card says it then
            win.call(win.view.relationship(acc.id),
                     lambda _r: state["pop"] is pop and pop.set_child(card(win, acc)),
                     lambda _e: None)
        return GLib.SOURCE_REMOVE

    def enter(*_a):
        away()
        state["timer"] = GLib.timeout_add(DELAY_MS, show)

    motion = Gtk.EventControllerMotion()
    motion.connect("enter", enter)
    motion.connect("leave", away)
    widget.add_controller(motion)
    click = Gtk.GestureClick(button=0)
    click.connect("pressed", away)
    widget.add_controller(click)
    widget.connect("unmap", away)
    return state
