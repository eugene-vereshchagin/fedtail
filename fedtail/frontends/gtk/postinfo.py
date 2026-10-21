"""What a post's ⋯ menu opens in the GTK window besides the editor, as the Qt window
has it: an edited post's versions, a complaint to the moderators, who liked or boosted
it (from my server, then from its own), the posts quoting a post of mine. What they say
and do is the core's (core.view) and common/'s; here only the windows."""

from __future__ import annotations

import logging

from ...i18n import _
from ...model.text import snippet
from ..richtext import history_html
from .dialogs import Page, _box, _buttons, _window
from .gi_setup import GLib, Gtk

log = logging.getLogger(__name__)


def show_history(win, st):
    """The versions of an edited post, oldest first, as the server keeps them."""
    page = Page(win, _("history_title"), "", on_link=win.on_link, width=560, height=480)
    page.set_markup(GLib.markup_escape_text(_("loading")))

    def got(versions):
        html = history_html(versions, win.theme.date, win.theme.c["link"].css())
        if html:
            page.set_html(html)
        else:
            page.set_markup(GLib.markup_escape_text(_("history_none")))
    win.call(win.view.history(st), got,
             lambda e: page.set_markup(GLib.markup_escape_text(_("load_failed", err=e))))
    page.present()
    return page


def report(win, st):
    """Complain about a post to my server's moderators: why, what kind, and whether
    the author's server hears too."""
    acc = st.author
    dlg = _window(win, _("report_title", acct=acc.handle), 480, 340)
    box = _box()
    quote = Gtk.Label(label=snippet(st, 200), xalign=0, wrap=True)
    quote.add_css_class("ft-muted")
    box.append(quote)
    kinds = ("spam", "legal", "violation", "other")
    kind = Gtk.DropDown.new_from_strings([_("report_" + k) for k in kinds])
    kind.set_selected(3)
    box.append(kind)
    why = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, vexpand=True)
    why.add_css_class("ft-compose-text")
    frame = Gtk.Frame(child=why)
    frame.add_css_class("ft-compose-frame")
    hint = Gtk.Label(label=_("report_why"), xalign=0)
    hint.add_css_class("ft-muted")
    box.append(hint)
    box.append(frame)
    remote = "@" in acc.handle
    fwd = Gtk.CheckButton(label=_("report_forward", host=acc.handle.split("@")[-1]))
    fwd.set_active(remote and win.cfg["post"].get("report_forward", True))
    fwd.set_visible(remote)
    box.append(fwd)
    cancel = Gtk.Button(label=_("cancel"))
    send = Gtk.Button(label=_("report_send"))
    send.add_css_class("suggested-action")
    cancel.connect("clicked", lambda _b: dlg.close())

    def go(_b):
        buf = why.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
        dlg.close()
        win.call(win.view.report(st, text, fwd.get_active(), kinds[kind.get_selected()]),
                 lambda _r: win.status(_("report_sent")))
    send.connect("clicked", go)
    box.append(_buttons(cancel, send))
    dlg.set_child(box)
    dlg.present()
    return dlg


def open_reactions(win, st, kind):
    """Who liked (kind="favourited_by") or boosted ("reblogged_by") a post, page by
    page, as my server knows them."""
    from .people import open_people
    return open_people(win, f"{kind}:{st.id}", _("who_" + kind, text=snippet(st, 30)),
                       lambda cur: win.view.who_reacted(st, kind, cur))


def open_quotes(win, post):
    """The posts quoting a post of mine, page by page; each card's ⋯ can take my post
    out of the quote."""
    from .card import Card
    key = f"quotes:{post.id}"
    page = win.extra_tabs.get(key)
    if page is not None:
        win.tabs.set_current_page(win.tabs.page_num(page))
        return page
    page, box, _title = win._new_tab(_("quotes_title", text=snippet(post, 40)),
                                     lambda: win.close_extra(key))
    win.extra_tabs[key] = page
    info = Gtk.Label(label=_("quotes_info"), xalign=0, wrap=True)
    info.add_css_class("ft-muted")
    box.append(info)
    more = Gtk.Button(label=_("older_down"))
    more.add_css_class("flat")
    cursor = [None]

    def got(r):
        posts, cursor[0] = r
        if more.get_parent() is not None:
            box.remove(more.get_parent())
        short = win.view.short_ids(posts)
        for p in posts:
            box.append(Card(win.ctx, p.id, p, short_id=short.get(p.id)))
        if not posts and cursor[0] is None and box.get_row_at_index(1) is None:
            box.append(Gtk.Label(label=_("search_none")))
        if cursor[0]:
            more.set_sensitive(True)
            box.append(more)

    def load(*_a):
        more.set_sensitive(False)
        win.call(win.view.quotes_of(post, cursor[0]), got)
    more.connect("clicked", load)
    load()
    return page


def read_up_to(win, sid):
    """This post and everything older in the lane it's in: read."""
    lv = win.lane_views.get(win._current_lane() or "")
    keys = list(getattr(lv, "keys", ()) or ())
    if lv is None or sid not in keys:
        win.view.mark_read([sid])
        return
    at = keys.index(sid)
    older = keys[at:] if lv.newest_first else keys[:at + 1]
    win.view.mark_read([k for k in older if k in lv.unread])
