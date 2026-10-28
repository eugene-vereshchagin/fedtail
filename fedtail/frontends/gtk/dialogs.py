"""Small windows of the GTK frontend: a question with a line to type in, a page of
text (the server, the federation status, help), the Silence window (word filters,
mutes, blocks, blocked servers), scheduled posts, filtered notifications. What they
say and do is the core's and common/'s, as in the Qt window."""

from __future__ import annotations

import logging

from ...i18n import _
from .. import pango
from ..common import timed
from .gi_setup import GLib, Gtk, Pango, tip, vscroll

log = logging.getLogger(__name__)


def _window(parent, title, width=560, height=440):
    win = Gtk.Window(title=title, transient_for=parent, modal=False)
    win.set_default_size(width, height)
    win.add_css_class("fedtail")
    return win


def _buttons(*buttons):
    row = Gtk.Box(spacing=6, halign=Gtk.Align.END)
    row.set_margin_top(6)
    for b in buttons:
        row.append(b)
    return row


def _box(margin=12, spacing=8):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
    for side in ("top", "bottom", "start", "end"):
        getattr(box, "set_margin_" + side)(margin)
    return box


def info(parent, title, text):
    """A window of text to read and close (Qt's QMessageBox.information)."""
    win = _window(parent, title, 560, 420)
    box = _box()
    lab = Gtk.Label(label=text, xalign=0, yalign=0, wrap=True, selectable=True)
    scroll = Gtk.ScrolledWindow(vexpand=True)
    scroll.set_child(lab)
    box.append(scroll)
    ok = Gtk.Button(label=_("close"))
    ok.connect("clicked", lambda _b: win.close())
    box.append(_buttons(ok))
    win.set_child(box)
    win.present()
    return win


def ask_text(parent, title, question, then, text="", ok_label=None, allow_empty=False):
    """A line to type in; then(text) on OK (stripped; never empty unless allow_empty —
    an empty note, "all languages")."""
    win = _window(parent, title, 420, -1)
    win.set_modal(True)
    box = _box()
    box.append(Gtk.Label(label=question, xalign=0, wrap=True))
    entry = Gtk.Entry(text=text)
    entry.set_activates_default(True)
    box.append(entry)
    cancel = Gtk.Button(label=_("cancel"))
    ok = Gtk.Button(label=ok_label or "OK")
    ok.add_css_class("suggested-action")

    def done(*_a):
        got = entry.get_text().strip()
        if got or allow_empty:
            win.close()
            then(got)
    ok.connect("clicked", done)
    entry.connect("activate", done)
    cancel.connect("clicked", lambda _b: win.close())
    box.append(_buttons(cancel, ok))
    win.set_child(box)
    win.set_default_widget(ok)
    win.present()
    return win


def choose(parent, title, text, options, then, check=None):
    """One of options ([(key, label)]) by radio buttons, and a tick box when check (its
    label) is given; then(key, ticked) on OK — never on Cancel or close."""
    win = _window(parent, title, 420, -1)
    win.set_modal(True)
    box = _box()
    box.append(Gtk.Label(label=text, xalign=0, wrap=True))
    radios, first = [], None
    for key, label in options:
        r = Gtk.CheckButton(label=label)
        if first is None:
            first = r
            r.set_active(True)
        else:
            r.set_group(first)
        radios.append((key, r))
        box.append(r)
    tick = None
    if check:
        tick = Gtk.CheckButton(label=check)
        tick.set_margin_top(6)
        box.append(tick)
    cancel = Gtk.Button(label=_("cancel"))
    ok = Gtk.Button(label="OK")
    ok.add_css_class("suggested-action")

    def done(*_a):
        key = next((k for k, r in radios if r.get_active()), options[0][0])
        ticked = bool(tick and tick.get_active())
        win.close()
        then(key, ticked)
    ok.connect("clicked", done)
    cancel.connect("clicked", lambda _b: win.close())
    box.append(_buttons(cancel, ok))
    win.set_child(box)
    win.set_default_widget(ok)
    win.radios, win.tick, win.ok = radios, tick, ok  # (tests answer it)
    win.present()
    return win


class Page(Gtk.Window):
    """A page of text made from HTML (pango.py): the server about itself, the
    federation status, a help page. Links go to on_link."""

    def __init__(self, parent, title, html="", on_link=None, width=720, height=600,
                 extra=None):
        super().__init__(title=title, transient_for=parent)
        self.set_default_size(width, height)
        self.add_css_class("fedtail")
        self.on_link = on_link
        box = _box(0, 0)
        self.label = Gtk.Label(xalign=0, yalign=0, wrap=True)
        self.label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        for side in ("top", "bottom", "start", "end"):
            getattr(self.label, "set_margin_" + side)(14)
        self.label.connect("activate-link", self._link)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self.label)
        self.scroll = scroll
        if extra is not None:
            tabs = Gtk.Notebook()
            tabs.append_page(scroll, Gtk.Label(label=extra[0]))
            tabs.append_page(extra[2], Gtk.Label(label=extra[1]))
            tabs.set_vexpand(True)
            box.append(tabs)
        else:
            box.append(scroll)
        close = Gtk.Button(label=_("close"))
        close.connect("clicked", lambda _b: self.close())
        row = _buttons(close)
        for side in ("bottom", "end"):
            getattr(row, "set_margin_" + side)(8)
        box.append(row)
        self.button_row = row
        self.set_child(box)
        self.set_html(html)

    def extra_button(self, button):
        """One more button beside Close (Open in browser…)."""
        self.button_row.prepend(button)

    def set_html(self, html):
        self.label.set_markup(pango.markup(html or ""))

    def set_markup(self, markup):
        self.label.set_markup(markup)

    def _link(self, _label, uri):
        if self.on_link is not None:
            self.on_link(uri)
            return True
        return False


FILTER_CONTEXTS = ("home", "notifications", "public", "thread", "account")
def edit_filter(parent, f, then):
    """A filter of mine, changed: title, words, fold or hide, where, how long;
    then(changes) on OK (timed.filter_changes)."""
    w = _window(parent, _("filter_edit_title", title=f.title or ", ".join(f.words)), 520, -1)
    w.set_modal(True)
    box = _box()
    box.append(Gtk.Label(label=_("filter_title_label"), xalign=0))
    title = Gtk.Entry(text=f.title)
    box.append(title)
    box.append(Gtk.Label(label=_("filter_new").rstrip(":"), xalign=0))
    words = Gtk.Entry(text=", ".join(f.words), placeholder_text=_("filter_words"))
    box.append(words)
    action = Gtk.DropDown.new_from_strings([_("filter_warn"), _("filter_hide")])
    action.set_selected(1 if f.action == "hide" else 0)
    box.append(action)
    box.append(Gtk.Label(label=_("filter_where"), xalign=0))
    row = Gtk.Box(spacing=8)
    ctx = {}
    for c in FILTER_CONTEXTS:
        b = Gtk.CheckButton(label=_("filter_ctx_" + c),
                            active=c in f.contexts if f.contexts else c != "notifications")
        ctx[c] = b
        row.append(b)
    box.append(row)
    span_row = Gtk.Box(spacing=8)
    span_row.append(Gtk.Label(label=_("filter_for")))
    spans = [(timed.KEEP, timed.filter_extra(f).lstrip(" ·") or _("span_ever"))] + timed.spans()
    span = Gtk.DropDown.new_from_strings([label for _s, label in spans])
    tip(span, _("filter_for_q"))
    span_row.append(span)
    box.append(span_row)
    cancel = Gtk.Button(label=_("cancel"))
    ok = Gtk.Button(label="OK")
    ok.add_css_class("suggested-action")

    def done(*_a):
        w.close()
        then(timed.filter_changes(title.get_text(), words.get_text(),
                            "hide" if action.get_selected() == 1 else "warn",
                            [c for c, b in ctx.items() if b.get_active()],
                            spans[span.get_selected()][0]))
    ok.connect("clicked", done)
    cancel.connect("clicked", lambda _b: w.close())
    box.append(_buttons(cancel, ok))
    w.set_child(box)
    w.title_entry, w.words, w.action, w.ctx, w.span, w.ok = title, words, action, ctx, span, ok
    w.present()
    return w


def silence(win, tab="filters"):
    """≡ → For the tender and sensitive: word filters, muted, blocked, blocked servers —
    the lists as the server has them (fedtail.model: WordFilter, Silenced), undone
    from here; a filter added from here."""
    view = win.view
    dlg = _window(win, _("silence_title"), 600, 480)
    tabs = Gtk.Notebook()
    tabs.set_vexpand(True)
    pages = {}

    def listbox():
        lb = Gtk.ListBox()
        lb.set_selection_mode(Gtk.SelectionMode.SINGLE)
        sc = vscroll(vexpand=True)
        sc.set_child(lb)
        return lb, sc

    # word filters
    fbox = _box(8, 6)
    hint = Gtk.Label(label=_("filters_hint"), xalign=0, wrap=True)
    hint.add_css_class("ft-muted")
    fbox.append(hint)
    filters, sc = listbox()
    fbox.append(sc)
    rm = Gtk.Button(label=_("filter_delete"))
    change = Gtk.Button(label=_("filter_edit"))
    rm_row = Gtk.Box(spacing=6)
    rm_row.append(change)
    rm_row.append(rm)
    fbox.append(rm_row)
    fbox.append(Gtk.Label(label=_("filter_new"), xalign=0))
    words = Gtk.Entry(placeholder_text=_("filter_words"))
    fbox.append(words)
    row = Gtk.Box(spacing=8)
    action = Gtk.DropDown.new_from_strings([_("filter_warn"), _("filter_hide")])
    row.append(action)
    contexts = {}
    for c in ("home", "notifications", "public", "thread", "account"):
        b = Gtk.CheckButton(label=_("filter_ctx_" + c), active=c != "notifications")
        contexts[c] = b
        row.append(b)
    fbox.append(row)
    span_row = Gtk.Box(spacing=8)
    span_row.append(Gtk.Label(label=_("filter_for")))
    spans = timed.spans()  # how long: for good, an hour… (the server ends it)
    span = Gtk.DropDown.new_from_strings([label for _s, label in spans])
    tip(span, _("filter_for_q"))
    span_row.append(span)
    fbox.append(span_row)
    add = Gtk.Button(label=_("filter_add"), halign=Gtk.Align.START)
    add.add_css_class("suggested-action")
    fbox.append(add)
    tabs.append_page(fbox, Gtk.Label(label=_("silence_filters")))
    pages["filters"] = 0

    people = {}
    for i, (key, label) in enumerate((("muted", "silence_muted"), ("blocked", "silence_blocked"),
                                      ("domains", "tender_domains")), start=1):
        box = _box(8, 6)
        if key == "domains":
            h = Gtk.Label(label=_("silence_domains_hint"), xalign=0, wrap=True)
            h.add_css_class("ft-muted")
            box.append(h)
        lb, sc = listbox()
        box.append(sc)
        undo = Gtk.Button(label=_("unmute") if key == "muted" else _("unblock"),
                          halign=Gtk.Align.START)
        box.append(undo)
        people[key] = (lb, undo)
        tabs.append_page(box, Gtk.Label(label=_(label)))
        pages[key] = i

    def row_of(text, data):
        r = Gtk.ListBoxRow()
        r.data = data
        lab = Gtk.Label(label=text, xalign=0)
        lab.set_ellipsize(Pango.EllipsizeMode.END)
        for side in ("top", "bottom", "start", "end"):
            getattr(lab, "set_margin_" + side)(4)
        r.set_child(lab)
        return r

    def clear(lb):
        while (c := lb.get_first_child()) is not None:
            lb.remove(c)

    gen = [0]
    objs = {}  # id -> WordFilter, as last drawn

    def reload():
        gen[0] += 1
        n = gen[0]

        def got_filters(fs):
            if n != gen[0]:
                return
            clear(filters)
            objs.clear()
            objs.update({f.id: f for f in fs})
            for f in fs:
                w = ", ".join(f.words)
                how = _("filter_hide") if f.action == "hide" else _("filter_warn")
                filters.append(row_of(f"{f.title or w} — {how}"
                                      + (f" ({w})" if w and w != f.title else "")
                                      + timed.filter_extra(f), f.id))

        def got_people(s):
            if n != gen[0]:
                return
            for key, items in (("muted", s.muted), ("blocked", s.blocked)):
                lb = people[key][0]
                clear(lb)
                for a in items:
                    lb.append(row_of(f"{a.name or a.username} @{a.handle or a.id}", a.id))
            lb = people["domains"][0]
            clear(lb)
            for d in s.domains:
                lb.append(row_of(d, d))
        win.call(view.filters(), got_filters)
        win.call(view.silenced_people(), got_people)

    def add_filter(_b):
        ws = [x.strip() for x in words.get_text().split(",") if x.strip()]
        if not ws:
            return
        ctx = [c for c, b in contexts.items() if b.get_active()] or ["home"]
        how = "hide" if action.get_selected() == 1 else "warn"
        secs = spans[span.get_selected()][0] if span.get_selected() < len(spans) else 0
        win.call(view.add_filter(", ".join(ws), ws, how, ctx, expires_in=secs or None),
                 lambda _f: (words.set_text(""), reload()))

    def change_filter(_b=None, answer=None):
        """Edit… the chosen filter; answer: what the window gives (tests: at once)."""
        r = filters.get_selected_row()
        f = objs.get(r.data) if r is not None else None
        if f is None:
            return

        def save(ch):
            if not ch["words"] and not f.posts:
                return  # a word filter with no words left: "Delete" is for that
            if f.posts and not f.words:
                ch["words"] = None  # the hidden posts' filter: no words to set
            win.call(view.edit_filter(f.id, **ch),
                     lambda _r: (win.status(_("filter_saved")), reload()))
        if answer is not None:
            save(answer)
        else:
            dlg.editing = edit_filter(dlg, f, save)

    def delete_filter(_b):
        r = filters.get_selected_row()
        if r is not None:
            win.call(view.delete_filter(r.data), lambda _r: reload())

    def undo(key):
        r = people[key][0].get_selected_row()
        if r is None:
            return
        if key == "domains":
            call = view.block_domain(r.data, False)
        elif key == "muted":
            call = view.mute(r.data, False)
        else:
            call = view.block(r.data, False)
        win.call(call, lambda _r: reload())

    add.connect("clicked", add_filter)
    words.connect("activate", add_filter)
    rm.connect("clicked", delete_filter)
    change.connect("clicked", change_filter)
    filters.connect("row-activated", lambda _lb, _r: change_filter())
    for key, (_lb, b) in people.items():
        b.connect("clicked", lambda _b, k=key: undo(k))
    box = _box(8, 6)
    box.append(tabs)
    close = Gtk.Button(label=_("close"))
    close.connect("clicked", lambda _b: dlg.close())
    box.append(_buttons(close))
    dlg.set_child(box)
    tabs.set_current_page(pages.get(tab, 0))
    reload()
    dlg.reload = reload
    dlg.words, dlg.span, dlg.add, dlg.filters = words, span, add, filters  # (tests)
    dlg.change_filter, dlg.editing = change_filter, None
    dlg.present()
    return dlg


def scheduled(win):
    """Posts waiting on the server to go out at their time; any can be cancelled."""
    view = win.view
    dlg = _window(win, _("scheduled_title"), 560, 380)
    box = _box()
    lb = Gtk.ListBox()
    sc = vscroll(vexpand=True)
    sc.set_child(lb)
    box.append(sc)
    cancel = Gtk.Button(label=_("scheduled_cancel"), halign=Gtk.Align.START)
    box.append(cancel)

    def fill(items):
        while (c := lb.get_first_child()) is not None:
            lb.remove(c)
        for s in items:
            r = Gtk.ListBoxRow()
            r.sid = s.id
            lab = Gtk.Label(xalign=0, label=f"{win.theme.date(s.at) if s.at else ''} — "
                                            f"{s.text[:120]}")
            lab.set_ellipsize(Pango.EllipsizeMode.END)
            r.set_child(lab)
            lb.append(r)
        if not items:
            lb.append(Gtk.Label(label=_("scheduled_none")))

    def drop(_b):
        r = lb.get_selected_row()
        if r is not None and hasattr(r, "sid"):
            win.call(view.cancel_scheduled(r.sid), lambda _r: win.call(view.scheduled(), fill))
    cancel.connect("clicked", drop)
    close = Gtk.Button(label=_("close"))
    close.connect("clicked", lambda _b: dlg.close())
    box.append(_buttons(close))
    dlg.set_child(box)
    win.call(view.scheduled(), fill)
    dlg.present()
    return dlg


def server_info(win):
    """My server about itself (common/server.py makes the page), and what it can do —
    the probe as a table, asked by a button, copied as Markdown."""
    from ..common import server
    view = win.view
    probe = _box(8, 6)
    note = Gtk.Label(xalign=0, wrap=True)
    note.add_css_class("ft-muted")
    probe.append(note)
    grid = Gtk.Label(xalign=0, yalign=0, selectable=True, wrap=True)
    sc = Gtk.ScrolledWindow(vexpand=True)
    sc.set_child(grid)
    probe.append(sc)
    run = Gtk.Button(label=_("probe_run"))
    tip(run, _("probe_tip"))
    copy = Gtk.Button(label=_("probe_copy"))
    probe.append(_buttons(copy, run))
    rows = []

    def show(got):
        text, got_rows = server.probe_rows(got, win.theme.date)
        note.set_text(text)
        rows[:] = [(what, answer) for what, answer, _known in got_rows]
        grid.set_markup("\n".join(f"<b>{GLib.markup_escape_text(what)}</b>  "
                                   f"{GLib.markup_escape_text(answer)}"
                                   for what, answer in rows))

    def ask(_b):
        run.set_sensitive(False)
        note.set_text(_("probe_running"))
        win.call(view.probe_server(), lambda got: (run.set_sensitive(True), show(got)),
                 lambda e: (run.set_sensitive(True), note.set_text(_("probe_failed", err=e))))

    def copy_md(_b):
        if rows:
            win.get_clipboard().set(server.probe_markdown(domain[0], note.get_text(), rows))
            win.status(_("probe_copied"))
    run.connect("clicked", ask)
    copy.connect("clicked", copy_md)
    domain = [""]
    page = Page(win, _("server_info"), "", win.on_link,
                extra=(_("server_about_tab"), _("probe_tab"), probe))

    def got_info(info):
        domain[0] = info.domain or info.title
        page.set_title(_("server_info") + " — " + (info.title or info.domain))
        page.set_html(server.server_html(info, lambda h: h)
                      + server.server_more_html(info, lambda h: h))
    win.call(view.server_info(), got_info)
    try:
        show(view.last_probe())
    except Exception:  # noqa: BLE001 — nothing asked yet
        show(None)
    page.present()
    return page


def federation(win):
    """Debug → Federation status: what this run saw of my server and the others
    (fedstatus.py makes the page, as for Qt)."""
    from .. import fedstatus
    page = Page(win, _("fed_title"), _("loading"), win.on_link, 900, 700)
    got = [None]

    def show(data):
        got[0] = data
        page.set_html(fedstatus.html(data))

    def load(*_a):
        win.call(win.view.federation_status(), show)

    def copy(*_a):  # for an issue, as Qt's
        if got[0] is not None:
            page.get_clipboard().set(fedstatus.text(got[0]))
            win.status(_("fed_copied"), seconds=5)

    def count_anew(*_a):
        from ...core import health
        health.REC.clear()
        log.info("federation status: counting anew")
        load()
    bar = page.get_child().get_last_child()
    for word, fn in reversed((("fed_refresh", load), ("fed_copy", copy),
                              ("fed_reset", count_anew))):
        b = Gtk.Button(label=_(word))
        b.connect("clicked", fn)
        bar.prepend(b)
    load()
    # live while open: the numbers move as polls come (as Qt's, every 15 s)
    GLib.timeout_add_seconds(15, lambda: (load(), True)[1] if page.get_visible()
                             else GLib.SOURCE_REMOVE)
    page.present()
    return page


CHOICES = ("accept", "filter", "drop")


def filtered(win):
    """≡ → Filtered notifications (notify.filtered): who my server holds back — open
    the profile, let through, dismiss — and the policy, for each kind of sender."""
    from ...model.text import snippet
    view = win.view
    dlg = _window(win, _("filtered_title"), 580, 500)
    box = _box()
    note = Gtk.Label(label=_("filtered_loading"), xalign=0, wrap=True)
    box.append(note)
    lb = Gtk.ListBox()
    sc = vscroll(vexpand=True)
    sc.set_child(lb)
    box.append(sc)
    accept = Gtk.Button(label=_("filtered_accept"))
    dismiss = Gtk.Button(label=_("filtered_dismiss"))
    profile = Gtk.Button(label=_("filtered_profile"))
    row = Gtk.Box(spacing=6)
    for b in (accept, dismiss, profile):
        row.append(b)
    box.append(row)
    policy = Gtk.Grid(column_spacing=8, row_spacing=4)
    policy.set_visible(False)
    box.append(policy)
    combos = {}
    filling = [False]
    for i, key in enumerate(getattr(view, "FILTER_POLICY", ()) or ()):
        policy.attach(Gtk.Label(label=_("filtered_" + key), xalign=0), 0, i, 1, 1)
        dd = Gtk.DropDown.new_from_strings([_("policy_" + c) for c in CHOICES])
        dd.connect("notify::selected", lambda d, _p, k=key: set_policy(k, d))
        policy.attach(dd, 1, i, 1, 1)
        combos[key] = dd

    def set_policy(key, dd):
        if not filling[0]:
            win.call(view.set_filter_policy(**{key: CHOICES[dd.get_selected()]}))

    def fill(got):
        while (c := lb.get_first_child()) is not None:
            lb.remove(c)
        if got is None:
            note.set_text(_("filtered_unsupported"))
            for b in (accept, dismiss, profile):
                b.set_sensitive(False)
            return
        note.set_text(_("filtered_note", n=len(got["requests"])))
        for r in got["requests"]:  # HeldBack
            text = f"@{r.who.handle if r.who else '?'} — " + _("filtered_count", n=r.count)
            if r.last:
                text += "\n" + snippet(r.last, 140)
            item = Gtk.ListBoxRow()
            item.held = r
            lab = Gtk.Label(label=text, xalign=0, wrap=True)
            item.set_child(lab)
            lb.append(item)
        filling[0] = True
        try:
            for key, dd in combos.items():
                if key in got["policy"]:
                    val = got["policy"][key]
                    dd.set_selected(CHOICES.index(val) if val in CHOICES else 0)
                else:
                    dd.set_sensitive(False)
        finally:
            filling[0] = False
        policy.set_visible(bool(got["policy"]))

    def current():
        r = lb.get_selected_row()
        return getattr(r, "held", None)

    def answer(ok):
        r = current()
        if r is not None:
            win.call(view.answer_filtered(r.id, ok), lambda _x: load())

    def open_profile(*_a):
        r = current()
        if r is not None and r.who is not None:
            win.open_account(r.who.id)

    def load():
        win.call(view.filtered(), fill)
    accept.connect("clicked", lambda _b: answer(True))
    dismiss.connect("clicked", lambda _b: answer(False))
    profile.connect("clicked", open_profile)
    lb.connect("row-activated", open_profile)
    close = Gtk.Button(label=_("close"))
    close.connect("clicked", lambda _b: dlg.close())
    box.append(_buttons(close))
    dlg.set_child(box)
    load()
    dlg.present()
    return dlg
