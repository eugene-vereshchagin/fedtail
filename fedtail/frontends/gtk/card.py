"""One post as a GTK widget: who and when, what it answers, the text (as Pango markup),
attachments as a line, and the buttons. Built from the model only (Post / Share).

Stage 1 of docs/GTK.md: no pictures in the card yet, no post menu — those come with
the shared actions module (stage 2). What the card shows mirrors qt/card.py.
"""

from __future__ import annotations

from ...i18n import _
from ...model import Post, Share, real
from ...model.text import snippet
from .. import pango, richtext
from .gi_setup import GLib, Gtk, Pango


def _label(text="", css=(), markup=False, wrap=False, xalign=0.0, selectable=False):
    lab = Gtk.Label(xalign=xalign)
    if markup:
        lab.set_markup(text)
    else:
        lab.set_text(text)
    if wrap:
        lab.set_wrap(True)
        lab.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    lab.set_selectable(selectable)
    for c in css:
        lab.add_css_class(c)
    return lab


def name_of(account):
    """The name to show, as plain text (labels here are not markup)."""
    return account.name or account.username or account.handle


class Card(Gtk.Box):
    """A post card. key: the lane item id (a boost and its post differ); entry: the
    Post or Share; parent: the Post it answers, "missing" or None."""

    def __init__(self, ctx, key, entry, parent=None, unread=False, short_id=None,
                 depth=0, number=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.ctx, self.key = ctx, key
        self.entry = entry
        self.add_css_class("ft-card")
        self.unread = None
        self.depth = depth
        if depth:
            self.set_margin_start(min(depth, 8) * 18)
        self._build(parent, short_id, number)
        self.set_unread(unread)

    # ---- state -------------------------------------------------------------------
    @property
    def post(self) -> Post:
        return real(self.entry)

    def set_unread(self, on):
        on = bool(on)
        if on == self.unread:
            return
        self.unread = on
        (self.add_css_class if on else self.remove_css_class)("ft-unread")
        self.dot.set_visible(on)

    def update(self, entry):
        """Counters and my marks changed (status_updated): only the buttons move."""
        self.entry = entry
        self._fill_actions()

    # ---- building ----------------------------------------------------------------
    def _build(self, parent, short_id, number):
        p, ctx = self.post, self.ctx
        if isinstance(self.entry, Share):
            self.append(_label(_("boosted_by", name=name_of(self.entry.by)), ("ft-muted",)))
        head = Gtk.Box(spacing=6)
        self.dot = _label("●", ("ft-dot",))
        head.append(self.dot)
        name = _label(name_of(p.author), ("ft-name",))
        name.set_ellipsize(Pango.EllipsizeMode.END)
        head.append(name)
        handle = _label("@" + p.author.handle, ("ft-muted",))
        handle.set_ellipsize(Pango.EllipsizeMode.END)
        handle.set_hexpand(True)
        head.append(handle)
        if number:
            head.append(_label(f"/{number}", ("ft-mono",)))
        if short_id:
            head.append(_label(short_id, ("ft-mono",)))
        when = ctx.theme.date(p.created) if p.created else ""
        head.append(_label(when, ("ft-muted",)))
        self.append(head)

        if parent == "missing":
            self.append(_label(_("ctx_missing"), ("ft-ctx",), wrap=True))
        elif isinstance(parent, Post) and not ctx.in_thread:
            text = snippet(parent, 160)
            ctx_lab = _label(_("ctx_reply", name=name_of(parent.author),
                               text=text), ("ft-ctx",), wrap=True)
            self.append(ctx_lab)

        body = self._body()
        if p.warning:
            exp = Gtk.Expander(label="⚠ " + p.warning)
            exp.set_child(body)
            self.append(exp)
        else:
            self.append(body)

        if p.media:
            kinds = ", ".join(_("media_" + m.kind) if m.kind in
                              ("image", "video", "audio", "gifv") else _("media_unknown")
                              for m in p.media)
            links = " ".join(f'<a href="{GLib.markup_escape_text(m.url)}">[{i}]</a>'
                             for i, m in enumerate(p.media, 1) if m.url)
            lab = _label(f"📎 {GLib.markup_escape_text(kinds)} {links}", ("ft-muted",),
                         markup=True, wrap=True)
            lab.connect("activate-link", self._link)
            self.append(lab)

        self.actions = Gtk.Box(spacing=6)
        self.append(self.actions)
        self._fill_actions()

    def _body(self):
        p, cfg = self.post, self.ctx.cfg
        html = self.ctx.view.in_app(p) if cfg["ui"]["links_in_app"] else p.text
        html = richtext.clean(html, markup=cfg["feed"]["text_markup"])
        if not cfg["feed"]["emoji"]:
            html = richtext.strip_emoji(html, p.emojis)
        lab = _label(pango.markup(html, sanitized=True), ("ft-body",), markup=True, wrap=True)
        lab.connect("activate-link", self._link)
        return lab

    def _fill_actions(self):
        while (child := self.actions.get_first_child()) is not None:
            self.actions.remove(child)
        p = self.post
        n = p.counts

        def button(text, tip, fn, active=False):
            b = Gtk.Button(label=text)
            b.add_css_class("ft-action")
            b.add_css_class("flat")
            if active:
                b.add_css_class("ft-active")
            b.set_tooltip_text(tip)
            b.connect("clicked", lambda _b: fn())
            self.actions.append(b)
            return b

        button(f"💬 {n.replies}" if n.replies else "💬", _("thread"),
               lambda: self.ctx.open_thread(p))
        button(f"★ {n.likes}" if n.likes else "★", _("unfav") if p.mine.liked else _("fav"),
               lambda: self.ctx.act("like", p), p.mine.liked)
        if p.visibility in ("public", "unlisted"):
            button(f"♻ {n.shares}" if n.shares else "♻",
                   _("unboost") if p.mine.shared else _("boost"),
                   lambda: self.ctx.act("share", p), p.mine.shared)
        if p.url:
            button("↗", _("open_browser"), lambda: self.ctx.open_url(p.url))

    def _link(self, _label, uri):
        self.ctx.on_link(uri)
        return True  # handled: GTK must not open it itself


class Separator(Gtk.Box):
    """The "new below" line."""

    def __init__(self, text):
        super().__init__()
        self.key = "__sep__"
        lab = _label(text, ("ft-separator",), xalign=0.5)
        lab.set_hexpand(True)
        self.append(lab)
