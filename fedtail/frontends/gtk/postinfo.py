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
from .gi_setup import GLib, Gtk, tip

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
    # "Breaks the server's rules": which ones (the server's list, ticked)
    rules_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    rules_box.append(Gtk.Label(label=_("report_rules"), xalign=0))
    rules_box.set_visible(False)
    box.append(rules_box)
    rule_ticks = []  # (rule id, Gtk.CheckButton)
    asked = [False]

    def got_rules(info):
        for rid, (text, hint) in zip(info.rule_ids, info.rules, strict=False):
            b = Gtk.CheckButton(label=text)
            tip(b, hint or text)
            rule_ticks.append((rid, b))
            rules_box.append(b)

    def kind_changed(*_a):
        on = kinds[kind.get_selected()] == "violation"
        rules_box.set_visible(on)
        if on and not rule_ticks and not asked[0]:
            asked[0] = True
            win.call(win.view.server_info(), got_rules)
    kind.connect("notify::selected", kind_changed)
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
        what = kinds[kind.get_selected()]
        ids = [rid for rid, b in rule_ticks if b.get_active()]
        if what == "violation" and not ids:
            win.status(_("report_rules_need"))
            return
        dlg.close()
        win.call(win.view.report(st, text, fwd.get_active(), what,
                                 **({"rule_ids": ids} if ids else {})),
                 lambda _r: win.status(_("report_sent")))
    send.connect("clicked", go)
    dlg.kind, dlg.rule_ticks, dlg.send = kind, rule_ticks, go  # (tests)
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


def open_link_posts(win, url):
    """Who else shared this link (Mastodon 4.3: the server keeps trending links only):
    their posts, page by page, as the Qt window's tab."""
    from urllib.parse import urlsplit

    from .card import Card
    key = f"link:{url}"
    page = win.extra_tabs.get(key)
    if page is not None:
        win.tabs.set_current_page(win.tabs.page_num(page))
        return page
    page, box, _title = win._new_tab(_("link_posts_title",
                                       host=urlsplit(url).hostname or url),
                                     lambda: win.close_extra(key))
    win.extra_tabs[key] = page
    info = Gtk.Label(label=url, xalign=0, wrap=True)
    info.add_css_class("ft-muted")
    box.append(info)
    more = Gtk.Button(label=_("older_down"))
    more.add_css_class("flat")
    last = [None]  # the oldest post shown: the next page is older than it
    shown = [0]

    def got(posts):
        if more.get_parent() is not None:
            box.remove(more.get_parent())
        short = win.view.short_ids(posts)
        for p in posts:
            box.append(Card(win.ctx, p.id, p, short_id=short.get(p.id)))
        shown[0] += len(posts)
        if not shown[0]:
            info.set_text(_("link_posts_none"))
        if posts:
            last[0] = posts[-1].id
            more.set_sensitive(True)
            box.append(more)

    def load(*_a):
        more.set_sensitive(False)
        win.call(win.view.link_timeline(url, max_id=last[0]), got)
    more.connect("clicked", load)
    load()
    page.link_info, page.link_more = info, more  # (tests)
    return page


def remote_page(view, host, cursor):
    """core.remote_public, its two failures made answers: a future of (posts, cursor) or
    ("closed", None) / ("bad", None) — the bridge hands a fail only the words."""
    from concurrent.futures import Future
    out = Future()

    def done(f):
        exc = f.exception()
        if isinstance(exc, LookupError):
            out.set_result(("closed", None))
        elif isinstance(exc, ValueError):
            out.set_result(("bad", None))
        elif exc is not None:
            out.set_exception(exc)
        else:
            out.set_result(f.result())
    view.remote_public(host, cursor).add_done_callback(done)
    return out


def open_remote_lane(win, host):
    """Another server's public lane (core.remote_public): read without an account, its
    posts fetched into mine page by page — as the Qt window's tab; one tab a server."""
    from .card import Card
    key = f"remote:{host}"
    page = win.extra_tabs.get(key)
    if page is not None:
        win.tabs.set_current_page(win.tabs.page_num(page))
        return page
    page, box, _title = win._new_tab(_("remote_public_title", host=host),
                                     lambda: win.close_extra(key))
    win.extra_tabs[key] = page
    info = Gtk.Label(label=_("remote_public_tip"), xalign=0, wrap=True)
    info.add_css_class("ft-muted")
    box.append(info)
    more = Gtk.Button(label=_("older_down"))
    more.add_css_class("flat")
    cursor = [None]  # the server's own: its ids, not mine
    shown = [0]

    def got(res):
        posts, nxt = res
        if more.get_parent() is not None:
            box.remove(more.get_parent())
        if posts in ("closed", "bad"):
            info.set_text(_("remote_public_closed", host=host) if posts == "closed"
                          else _("remote_public_bad", text=host))
            return
        short = win.view.short_ids(posts)
        for p in posts:
            box.append(Card(win.ctx, p.id, p, short_id=short.get(p.id)))
        shown[0] += len(posts)
        if not shown[0]:
            info.set_text(_("remote_public_closed", host=host))
        cursor[0] = nxt
        if nxt:
            more.set_sensitive(True)
            box.append(more)

    def load(*_a):
        more.set_sensitive(False)
        win.call(remote_page(win.view, host, cursor[0]), got)
    more.connect("clicked", load)
    load()
    page.remote_info, page.remote_more = info, more  # (tests)
    return page


def read_up_to(win, sid):
    """This post and everything older in the lane it's in: read."""
    from ..common.lane import read_up_to as up_to
    lv = win.lane_views.get(win._current_lane() or "")
    specs = getattr(lv, "specs", None) or {}
    entries = [specs[k].entry for k in getattr(lv, "keys", ()) or () if k in specs]
    win.view.mark_read(up_to(entries, sid))


def read_whole(win, st):
    """📄 The whole text from the author's server: an article my server cut to a title
    and a link, an event with its time and place — in a page of its own, as in Qt."""
    from ..richtext import esc, sanitize
    win.status(_("long_form_wait"))

    def when(iso):
        from datetime import datetime
        try:
            t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return (t.astimezone() if t.tzinfo else t).strftime("%d.%m.%Y %H:%M")
        except ValueError:
            return esc(iso)

    def got(d):
        if not d:
            win.error(_("long_form_none"))
            return
        parts = []
        if d["name"]:
            parts.append(f"<h2>{esc(d['name'])}</h2>")
        event = [x for x in (
            "🗓 " + " — ".join(when(t) for t in (d["start"], d["end"]) if t)
            if d["start"] else "", "📍 " + esc(d["location"]) if d["location"] else "") if x]
        if event:
            parts.append("<p><b>" + "<br>".join(event) + "</b></p>")
        if d["summary"]:
            parts.append(f"<p><i>{sanitize(d['summary'])}</i></p>")
        parts.append(sanitize(d["content"]) or esc(snippet(st, 2000)))
        page = Page(win, d["name"] or _("long_form_title"), "".join(parts),
                    on_link=win.on_link, width=820, height=760)
        if d["url"]:
            b = Gtk.Button(label=_("open_browser"))
            b.connect("clicked", lambda _b: win.open_url(d["url"]))
            page.extra_button(b)
        page.present()
    win.call(win.view.long_form(st), got)
