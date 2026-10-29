"""A place of common/places.py in a window of its own — GTK's twin of qt/place.py: any
place drawn as the web page, the terminal and the phone draw it (the hint, the tabs, the
rows with their buttons, the form, "more"); what a button answers is done the window's
way. Collections (Mastodon 4.6) live here, and any place without a widget of its own."""

from __future__ import annotations

from html import escape

from ...i18n import _
from ...model import real
from ..common.places import PLACES, Places
from .dialogs import _box, _window
from .gi_setup import Gtk, tip, vscroll


def _plain(text):
    import re
    from html import unescape
    return unescape(re.sub(r"<br\s*/?>", "\n", re.sub(r"<(?!br)[^>]+>", "", str(text or ""))))


class PlaceWindow:
    """One place; a button that opens another of it goes on in the same window."""

    def __init__(self, win, name, arg="", tab=""):
        self.win = win
        self.view = win.view
        self.places = Places(self.view)
        self.name, self.arg, self.tab, self.cursor = name, arg, tab, ""
        self.fields = {}
        self.page = None  # the page drawn last (as Qt's PlaceDialog keeps it)
        self.window = _window(win, _(PLACES.get(name, name)), 640, 640)
        outer = _box()
        self.hint = Gtk.Label(wrap=True, xalign=0)
        self.hint.add_css_class("dim-label")
        outer.append(self.hint)
        self.tabs = Gtk.Box(spacing=6)
        outer.append(self.tabs)
        scroll = vscroll(vexpand=True)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scroll.set_child(self.rows)
        outer.append(scroll)
        self.form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.append(self.form)
        # what a button answered — in this window, not the main one's status line behind it
        self.said = Gtk.Label(wrap=True, xalign=0)
        self.said.set_visible(False)
        outer.append(self.said)
        self.window.set_child(outer)
        self.window.present()
        self.load()

    def load(self):
        name, arg, tab, cursor = self.name, self.arg, self.tab, self.cursor
        self.win.call(self.view.bg.submit(lambda: self.places.page(name, arg, tab, cursor)),
                      self.draw)

    @staticmethod
    def _empty(box):
        while (c := box.get_first_child()) is not None:
            box.remove(c)

    def _button(self, b):
        w = Gtk.Button(label=b.label)
        if b.primary:
            w.add_css_class("ft-primary")
        if b.tip:
            tip(w, b.tip)
        w.connect("clicked", lambda _w, btn=b: self.press(btn))
        return w

    def draw(self, page):
        self.page = page
        self.window.set_title(page.title)
        self.hint.set_text(page.hint)
        self.hint.set_visible(bool(page.hint))
        self._empty(self.tabs)
        for key, words in page.tabs:
            b = Gtk.ToggleButton(label=words, active=key == page.tab)
            b.connect("clicked", lambda _b, k=key: self.go(self.name, self.arg, k))
            self.tabs.append(b)
        if not self.cursor:
            self._empty(self.rows)
        for r in page.rows:
            self.rows.append(self.row(r))
        if not page.rows and not self.cursor:
            empty = Gtk.Label(label=page.empty or "—")
            empty.add_css_class("dim-label")
            self.rows.append(empty)
        self._empty(self.form)
        self.fields = {}
        for f in page.form:
            self.field(f)
        buttons = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        for b in (page.more, page.submit):
            if b is not None:
                buttons.append(self._button(b))
        self.form.append(buttons)

    def row(self, r):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.add_css_class("card")
        box.set_margin_start(2)
        box.set_margin_end(2)
        label = Gtk.Label(wrap=True, xalign=0)
        if r.kind == "html":
            _markup(label, _pango(r.title), _plain(r.title))
            label.connect("activate-link", lambda _l, uri: (self.win.on_link(uri), True)[1])
        elif r.kind == "post" and r.data is not None:
            from ...model.text import snippet
            p = real(r.data)
            label.set_markup(f"<b>{escape(p.author.name or p.author.handle)}</b> "
                             f"@{escape(p.author.handle)}\n{escape(snippet(p, 400))}")
        elif r.kind == "qr":
            box.append(_qr_picture(r.data or ()))
            label.set_text(r.line)
        elif r.kind == "heading":
            label.set_markup(f"<b>{escape(r.title)}</b>")
        else:
            words = f"<b>{escape(r.title)}</b>" if r.title else ""
            if r.line:
                words += ("\n" if words else "") + escape(r.line)
            label.set_markup(words)
        box.append(label)
        btns = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        if r.kind == "post" and r.data is not None:
            sid = real(r.data).id
            b = Gtk.Button(label=_("thread"))
            b.connect("clicked", lambda _b: self.win.open_thread(sid))
            btns.append(b)
        for b in r.buttons:
            btns.append(self._button(b))
        if btns.get_first_child() is not None:
            box.append(btns)
        return box

    def field(self, f):
        if f.kind == "check":
            w = Gtk.CheckButton(label=f.label, active=bool(f.value))
            self.form.append(w)
            self.fields[f.name] = ("check", w)
        elif f.kind == "choice":
            if f.label:
                self.form.append(Gtk.Label(label=f.label, xalign=0))
            values = [v for v, _w in f.choices]
            w = Gtk.DropDown.new_from_strings([words for _v, words in f.choices])
            if f.value in values:
                w.set_selected(values.index(f.value))
            elif str(f.value) in values:
                w.set_selected(values.index(str(f.value)))
            self.form.append(w)
            self.fields[f.name] = ("choice", (w, values))
        elif f.kind == "checks":
            if f.label:
                self.form.append(Gtk.Label(label=f.label, xalign=0))
            row = Gtk.Box(spacing=6)
            boxes = []
            for value, words in f.choices:
                c = Gtk.CheckButton(label=words, active=value in (f.value or ()))
                row.append(c)
                boxes.append((value, c))
            self.form.append(row)
            self.fields[f.name] = ("checks", boxes)
        elif f.kind == "file":
            picked = {"path": ""}
            w = Gtk.Button(label=f.label)

            def choose(_b, w=w, picked=picked):
                dlg = Gtk.FileDialog()

                def done(d, res):
                    try:
                        gfile = d.open_finish(res)
                    except Exception:  # noqa: BLE001 — dismissed
                        return
                    if gfile is not None and gfile.get_path():
                        picked["path"] = gfile.get_path()
                        w.set_label(f.label + " ✓")
                dlg.open(self.window, None, done)
            w.connect("clicked", choose)
            self.form.append(w)
            self.fields[f.name] = ("file", picked)
        elif f.kind == "text":
            if f.label:
                self.form.append(Gtk.Label(label=f.label, xalign=0))
            w = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
            w.get_buffer().set_text(str(f.value or ""))
            w.set_size_request(-1, 90)
            self.form.append(w)
            self.fields[f.name] = ("text", w)
        else:
            w = Gtk.Entry(text=str(f.value or ""), placeholder_text=f.label)
            if f.kind == "secret":  # a password: dots, as everywhere
                w.set_visibility(False)
                w.set_input_purpose(Gtk.InputPurpose.PASSWORD)
            self.form.append(w)
            self.fields[f.name] = ("line", w)
        if f.tip:
            hint = Gtk.Label(label=f.tip, wrap=True, xalign=0)
            hint.add_css_class("dim-label")
            self.form.append(hint)

    def values(self):
        out = {}
        for name, (kind, w) in self.fields.items():
            if kind == "check":
                out[name] = w.get_active()
            elif kind == "choice":
                drop, values = w
                i = drop.get_selected()
                out[name] = values[i] if 0 <= i < len(values) else None
            elif kind == "checks":
                out[name] = [value for value, c in w if c.get_active()]
            elif kind == "file":
                if w["path"]:
                    out[name] = w["path"]
            elif kind == "text":
                buf = w.get_buffer()
                out[name] = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            else:
                out[name] = w.get_text()
        return out

    def press(self, btn, confirmed=False, answer=None):
        values = self.values()
        self.win.call(self.view.bg.submit(lambda: self.places.act(
            *btn.act, values=values, confirmed=confirmed, answer=answer)),
            lambda out: self.answered(btn, out, answer))

    def say(self, text, error=False):
        self.said.set_text(("⚠ " if error else "✓ ") + _plain(text))
        for c in ("ft-over", "ft-dot"):
            self.said.remove_css_class(c)
        self.said.add_css_class("ft-over" if error else "ft-dot")
        self.said.set_visible(True)

    def answered(self, btn, out, answer):
        if out.error:
            self.say(out.error, error=True)
            return
        if out.confirm:
            self.win.confirm(self.window.get_title() or "", _plain(out.confirm),
                             lambda: self.press(btn, True, answer))
            return
        if out.ask:
            title, question, text = out.ask
            self.win.ask_text(title, question, lambda got: self.press(btn, False, got), text)
            return
        if out.copy:
            self.win.get_clipboard().set(out.copy)
        if out.message:
            self.say(out.message)
            self.win.status(_plain(out.message))
        if out.compose:
            self.win.compose(text=str(out.compose.get("text") or ""))
        o = out.open or {}
        if o.get("thread"):
            self.win.open_thread(o["thread"])
        elif o.get("account"):
            self.win.open_account(o["account"])
        elif o.get("url"):
            self.win.open_url(o["url"])
        elif o.get("back"):
            self.window.close()
            return
        elif o.get("page") == "settings" and hasattr(self.win, "open_settings"):
            self.win.open_settings(o.get("arg", ""), o.get("tab", ""))  # the real window
            return
        elif o.get("page"):
            page = o["page"]
            if isinstance(page, (tuple, list)):
                self.go(page[0], page[1] if len(page) > 1 else "")
            else:
                self.go(page, o.get("arg", ""), o.get("tab", ""), o.get("cursor", ""))
            return
        if out.refresh:
            self.cursor = ""
            self.load()

    def go(self, name, arg="", tab="", cursor=""):
        same = (name, arg) == (self.name, self.arg)
        self.name, self.arg, self.tab = name, arg, tab
        self.cursor = cursor if same else ""
        self.load()


def _markup(label, markup, plain):
    """Markup when Pango can read it, else the plain words (never an empty label)."""
    from .gi_setup import Pango
    try:
        Pango.parse_markup(markup, -1, "\0")
    except Exception:  # noqa: BLE001 — not Pango's: the words alone
        label.set_text(plain)
        return
    label.set_markup(markup)


def _pango(html):
    """The place's safe HTML as Pango markup: what Pango doesn't know, as plain text."""
    import re
    text = re.sub(r"<br\s*/?>", "\n", str(html or ""))
    text = re.sub(r"</p>\s*<p>", "\n\n", text)
    text = re.sub(r'<a [^>]*href="([^"]*)"[^>]*>', r'<a href="\1">', text)
    text = re.sub(r"<(?!/?(?:a|b|i|u|tt|big|small|sub|sup)\b)[^>]+>", "", text)
    return text


__all__ = ["PlaceWindow"]


def _qr_picture(rows, module=6):
    """A QR code (common/qr.rows) as a picture: dark on white whatever the theme."""
    from gi.repository import Gdk, GLib
    n = len(rows) * module
    data = bytearray()
    for row in rows:
        line = b"".join((b"\x00\x00\x00" if c == "1" else b"\xff\xff\xff") * module
                        for c in row)
        data += line * module
    tex = Gdk.MemoryTexture.new(n, n, Gdk.MemoryFormat.R8G8B8, GLib.Bytes.new(bytes(data)),
                                n * 3)
    pic = Gtk.Picture.new_for_paintable(tex)
    pic.set_can_shrink(False)
    pic.set_halign(Gtk.Align.CENTER)
    return pic
