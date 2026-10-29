"""Small windows of the GTK frontend: a question with a line to type in, a page of
text (the server, the federation status, help), the Silence window (word filters,
mutes, blocks, blocked servers), scheduled posts, filtered notifications. What they
say and do is the core's and common/'s, as in the Qt window."""

from __future__ import annotations

import logging

from ...i18n import _
from .. import pango
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


