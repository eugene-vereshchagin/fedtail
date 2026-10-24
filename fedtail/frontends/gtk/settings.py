"""The settings window drawn by GTK — Qt's (qt/settings.py): the chapters on the left,
one chapter's options as cards on the right, a search over all of them. What it shows
and what saving does is common/settings.py's: a change goes into config.toml at once
(that line only), and the window offers to restart."""

from __future__ import annotations

import logging

from ...i18n import _
from ..common import settings as model_of
from .gi_setup import GLib, Gtk

log = logging.getLogger(__name__)

CSS = """
.ft-set-card { border-radius: 8px; padding: 8px 12px; }
.ft-set-changed { border-left: 3px solid @accent_color; }
.ft-set-title { font-weight: 600; }
.ft-set-about { opacity: 0.75; }
.ft-set-name { font-family: monospace; font-size: smaller; opacity: 0.6; }
.ft-set-group { font-size: larger; margin-top: 6px; }
"""

_provider = None


def _short(words, n=70):
    return words if len(words) <= n else words[:n - 3].rsplit(" ", 1)[0] + "…"


def _label(text, *classes, wrap=False, select=False):
    lab = Gtk.Label(label=text, xalign=0, wrap=wrap, selectable=select)
    if wrap:
        lab.set_wrap_mode(2)  # Pango.WrapMode.WORD_CHAR
    for c in classes:
        lab.add_css_class(c)
    return lab


class SettingsWindow(Gtk.Window):
    def __init__(self, win):
        super().__init__(transient_for=win, title=_("settings_title"))
        self.win = win
        self.view = win.view
        self.path = model_of.config_file(self.view)
        self.stamp = self._stamp()
        self.chapters = model_of.model(self.view)
        self.current = self.chapters[0].key if self.chapters else ""
        self.set_default_size(900, 680)
        global _provider
        if _provider is None:
            _provider = Gtk.CssProvider()
            if hasattr(_provider, "load_from_string"):
                _provider.load_from_string(CSS)
            else:
                _provider.load_from_data(CSS, -1)
            Gtk.StyleContext.add_provider_for_display(
                self.get_display(), _provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in ("top", "bottom", "start", "end"):
            getattr(outer, f"set_margin_{m}")(12)
        self.search = Gtk.SearchEntry(placeholder_text=_("settings_search"))
        self.search.connect("search-changed", lambda _e: self._redraw())
        outer.append(self.search)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
        self.list = Gtk.ListBox()
        self.list.add_css_class("navigation-sidebar")
        for ch in self.chapters:
            row = Gtk.ListBoxRow()
            row.set_child(_label(f"{ch.number}. {ch.title}"))
            row.key = ch.key
            self.list.append(row)
        self.list.connect("row-selected", self._chosen)
        side = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        side.set_child(self.list)
        side.set_size_request(200, -1)
        paned.set_start_child(side)
        paned.set_resize_start_child(False)
        self.scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, hexpand=True)
        paned.set_end_child(self.scroll)
        paned.set_position(210)
        outer.append(paned)

        outer.append(_label(_("settings_hint", file=str(self.path)), "ft-muted", wrap=True))
        bottom = Gtk.Box(spacing=8)
        self.status = _label("", wrap=True)
        self.status.set_hexpand(True)
        bottom.append(self.status)
        b = Gtk.Button(label=_("settings_open_file"))
        b.connect("clicked", lambda _b: self.win.open_path(self.path))
        bottom.append(b)
        self.restart = Gtk.Button(label=_("settings_restart"),
                                  tooltip_text=_("settings_restart_tip"))
        self.restart.add_css_class("suggested-action")
        self.restart.set_visible(False)
        self.restart.connect("clicked", lambda _b: (self.close(), self.win.restart()))
        bottom.append(self.restart)
        b = Gtk.Button(label=_("close"))
        b.connect("clicked", lambda _b: self.close())
        bottom.append(b)
        outer.append(bottom)
        self.set_child(outer)
        self.connect("notify::is-active", self._activated)
        first = self.list.get_row_at_index(0)
        if first is not None:
            self.list.select_row(first)
        else:
            self._redraw()

    # ---- the file ----------------------------------------------------------------------
    def _stamp(self):
        try:
            st = self.path.stat()
            return st.st_mtime_ns, st.st_size
        except OSError:
            return None

    def _fresh(self):
        if self._stamp() == self.stamp:
            return False
        self.stamp = self._stamp()
        self.chapters = model_of.model(self.view)
        self.status.set_text(_("settings_changed_outside"))
        return True

    def _activated(self, *_a):
        if self.is_active() and self._fresh():
            self._redraw()

    def save(self, option, value):
        self._fresh()
        now = model_of.option(self.chapters, option.name)
        if now is None or (value is not model_of.UNSET and value == now.value
                           and now.in_file):
            return  # a control drawn before the last save, saying it again
        try:
            words = model_of.save(self.view, {(option.section, option.key): value})
        except model_of.SaveError as e:
            self.status.set_text("⚠ " + str(e))
            GLib.idle_add(lambda: (self._redraw(), False)[1])
            return
        log.info("settings: %s changed", option.name)
        self.stamp = self._stamp()
        self.chapters = model_of.model(self.view)
        self.status.set_text(words)
        self.restart.set_visible(True)
        GLib.idle_add(lambda: (self._redraw(), False)[1])  # once the control's signal is done

    # ---- drawing -----------------------------------------------------------------------
    def _chosen(self, _lb, row):
        if row is not None:
            self.current = row.key
            self._redraw()

    def _redraw(self):
        self.controls = {}  # option's name → its control, as drawn now
        adj = self.scroll.get_vadjustment()
        what = self.search.get_text().strip() or self.current
        keep = adj.get_value() if getattr(self, "_drawn", None) == what else 0
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in ("bottom", "start", "end"):
            getattr(page, f"set_margin_{m}")(8)
        q = self.search.get_text().strip()
        self.list.set_sensitive(not q)
        if q:
            found = model_of.find(self.chapters, q)
            if not found:
                page.append(_label(_("settings_none"), "ft-muted"))
            for ch, hits in found:
                page.append(_label(f"{ch.number}. {ch.title}", "ft-set-group", "ft-active"))
                for o in hits:
                    page.append(self._card(o))
        else:
            ch = next((c for c in self.chapters if c.key == self.current), None)
            group = None
            for o in ch.options if ch else ():
                if o.group and o.group != group:
                    group = o.group
                    page.append(_label(group, "ft-set-group", "ft-active"))
                page.append(self._card(o))
        self.scroll.set_child(page)
        self._drawn = what
        GLib.idle_add(lambda: (adj.set_value(keep), False)[1])

    def _card(self, o):
        card = Gtk.Grid(column_spacing=12, row_spacing=4)
        card.add_css_class("ft-card")
        card.add_css_class("ft-set-card")
        if o.changed:
            card.add_css_class("ft-set-changed")
        title = _label(o.title, "ft-set-title", wrap=True)
        title.set_hexpand(True)
        card.attach(title, 0, 0, 1, 1)
        control = self.controls[o.name] = self._control(o)
        row = 1
        if o.kind == "checks":
            card.attach(control, 0, row, 2, 1)
            row += 1
        else:
            control.set_halign(Gtk.Align.END)
            control.set_valign(Gtk.Align.START)
            card.attach(control, 1, 0, 1, 1)
        about = o.about
        if about and about.split("\n", 1)[0].rstrip(".:") == o.title.rstrip("."):
            about = about.split("\n", 1)[1] if "\n" in about else ""
        if about:
            card.attach(_label(about, "ft-set-about", wrap=True, select=True), 0, row, 2, 1)
            row += 1
        foot = Gtk.Box(spacing=8)
        name = _label(o.name + ("" if o.changed else "  ·  " + _(
            "settings_default", value=o.default_shown())), "ft-set-name")
        name.set_hexpand(True)
        foot.append(name)
        if o.changed:
            reset = Gtk.Button(label=_("settings_reset"),
                               tooltip_text=_("settings_reset_tip", value=o.default_shown()))
            reset.connect("clicked", lambda _b, o=o: self.save(o, model_of.UNSET))
            foot.append(reset)
        card.attach(foot, 0, row, 2, 1)
        return card

    def _control(self, o):
        if o.kind == "bool":
            w = Gtk.Switch(active=bool(o.value))
            w.connect("notify::active", lambda s, _p, o=o: self.save(o, bool(s.get_active())))
            return w
        if o.kind == "int":
            low = o.minimum if o.minimum is not None else (0 if o.default >= 0 else -10**6)
            w = Gtk.SpinButton.new_with_range(low, 10**9, 1)
            w.set_value(int(o.value))
            w.set_width_chars(8)
            w.set_update_policy(Gtk.SpinButtonUpdatePolicy.IF_VALID)

            def done(s, o=o):
                n = int(s.get_value())
                if n != o.value:
                    self.save(o, n)
            w.connect("value-changed", done)
            return w
        if o.kind == "choice":
            words = [str(v) if t == str(v) else f"{v} — {_short(t, 48)}" for v, t in o.choices]
            w = Gtk.DropDown.new_from_strings(words)
            values = [v for v, _t in o.choices]
            if o.value in values:
                w.set_selected(values.index(o.value))
            w.set_size_request(240, -1)

            def picked(d, _p, o=o, values=values):
                i = d.get_selected()
                if 0 <= i < len(values) and values[i] != o.value:
                    self.save(o, values[i])
            w.connect("notify::selected", picked)
            return w
        if o.kind == "checks":
            box = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4,
                              column_spacing=14, homogeneous=True)
            ticks = []
            for v, words in o.choices:
                c = Gtk.CheckButton(label=_short(words, 32), active=v in (o.value or ()),
                                    tooltip_text=f"{v}: {words}" if words != v else v)
                ticks.append((v, c))
                box.append(c)

            def ticked(_c, o=o, ticks=ticks):
                now = [v for v, c in ticks if c.get_active()]
                self.save(o, [v for v in o.value if v in now] +
                          [v for v in now if v not in o.value])
            for _v, c in ticks:
                c.connect("toggled", ticked)
            return box
        w = Gtk.Entry(text=o.line(), width_chars=28)
        if o.kind == "list":
            w.set_placeholder_text("a, b, c")

        def typed(*_a, w=w, o=o):
            try:
                value = o.parse(w.get_text())
            except ValueError as e:
                self.status.set_text(f"⚠ {o.title}: {e}")
                return
            if value != o.value:
                self.save(o, value)
        w.connect("activate", typed)
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", typed)
        w.add_controller(focus)
        return w


__all__ = ["SettingsWindow"]
