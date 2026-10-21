"""One post as a GTK widget, built from the model only (Post / Share): the face, who and
when, what it answers, the text (Pango markup), pictures, a poll, a quoted post, a
link's card, "you replied", and the buttons and ⋯ menu of common/actions.py — the
same choices the Qt card makes (qt/card.py), drawn with GTK.
"""

from __future__ import annotations

from ...i18n import _
from ...model import Post, Share, real
from ...model.text import snippet
from .. import pango, richtext
from ..common import actions
from .gi_setup import Gdk, GLib, Gtk, Pango, tip

THUMB_H = 180       # px: a picture's height in a card
QUOTE_DEPTH = 1     # a quoted post shows its own quote no deeper than this


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


def link_markup(url, text):
    return f'<a href="{GLib.markup_escape_text(url)}">{GLib.markup_escape_text(text)}</a>'


class Avatar(Gtk.Image):
    """A face of a fixed size, rounded as the theme says (shape.avatar_shape)."""

    def __init__(self, ctx, account, size):
        super().__init__()
        self.set_pixel_size(size)
        self.set_size_request(size, size)
        self.set_halign(Gtk.Align.START)
        self.set_valign(Gtk.Align.START)
        self.add_css_class("ft-avatar")
        self.add_css_class("ft-avatar-" + ctx.theme.shape.get("avatar_shape", "circle"))
        self.set_overflow(Gtk.Overflow.HIDDEN)  # the rounding cuts the picture
        if ctx.images is not None:
            url = account.avatar_static or account.avatar
            # read small: a face twice its size at most (sharp on a HiDPI screen)
            ctx.images.get(url, self.set_from_paintable, max_side=max(64, size * 2))


class Card(Gtk.Box):
    """A post card. key: the lane item id (a boost and its post differ); entry: the
    Post or Share; parent: the Post it answers, "missing" or None."""

    def __init__(self, ctx, key, entry, parent=None, unread=False, short_id=None,
                 depth=0, number=None, my_replies=()):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.ctx, self.key = ctx, key
        self.entry = entry
        self.short_id = short_id
        self.add_css_class("ft-card")
        self.unread = None
        self.depth = depth
        if depth:
            self.set_margin_start(min(depth, 8) * 18)
        shape = ctx.theme.shape
        if shape.get("card_avatars", True) and ctx.images is not None:
            self.append(Avatar(ctx, self.post.author, int(shape.get("avatar", 40))))
        self.column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.column.set_hexpand(True)
        self.append(self.column)
        self._build(parent, number, my_replies)
        self.set_unread(unread)
        click = Gtk.GestureClick(button=3)  # a right click: the post's menu
        click.connect("pressed", lambda _g, _n, x, y: self._menu_at(x, y))
        self.add_controller(click)

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
        self._fill_actions()

    def update(self, entry):
        """Counters and my marks changed (status_updated): only the buttons move."""
        self.entry = entry
        self._fill_actions()

    # ---- building ----------------------------------------------------------------
    def _build(self, parent, number, my_replies):
        p, ctx, col = self.post, self.ctx, self.column
        if isinstance(self.entry, Share):
            col.append(_label(_("boosted_by", name=name_of(self.entry.by)), ("ft-muted",)))
        head = Gtk.Box(spacing=6)
        mark = "*" if ctx.theme.shape.get("unread_mark") == "star" else "●"
        self.dot = _label(mark, ("ft-dot",))
        head.append(self.dot)
        name = _label(name_of(p.author), ("ft-name",))
        name.set_ellipsize(Pango.EllipsizeMode.END)
        head.append(name)
        handle = _label(link_markup(f"fedtail:account/{p.author.id}", "@" + p.author.handle),
                        ("ft-muted",), markup=True)
        handle.connect("activate-link", self._link)
        handle.set_ellipsize(Pango.EllipsizeMode.END)
        handle.set_hexpand(True)
        head.append(handle)
        if number:
            head.append(_label(f"/{number}", ("ft-mono",)))
        if self.short_id:
            sid = _label(link_markup(f"fedtail:alias/{self.short_id}", "#" + self.short_id),
                         ("ft-mono",), markup=True)
            sid.connect("activate-link", self._link)
            head.append(sid)
        when = ctx.theme.date(p.created) if p.created else ""
        head.append(_label(when + (" ✎" if p.edited else ""), ("ft-muted",)))
        col.append(head)

        if parent == "missing":
            col.append(_label(_("ctx_missing"), ("ft-ctx",), wrap=True))
        elif isinstance(parent, Post) and not ctx.in_thread:
            text = _("ctx_reply", name=name_of(parent.author), text=snippet(parent, 160))
            ctx_lab = _label(link_markup(f"fedtail:thread/{p.id}", "↑ " + text), ("ft-ctx",),
                             markup=True, wrap=True)
            ctx_lab.connect("activate-link", self._link)
            col.append(ctx_lab)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        inner.append(self._body(p))
        if p.media:
            inner.append(self._media(p))
        if p.poll is not None:
            inner.append(self._poll(p))
        if p.quote is not None and p.quote.post is not None and \
                ctx.cfg["feed"].get("quotes", "card") == "card":
            inner.append(self._quote(p.quote.post))
        cards = ctx.cfg["feed"].get("link_cards", "full")
        if p.card is not None and not p.media and cards != "off":
            inner.append(self._link_card(p.card))
        if p.warning:
            exp = Gtk.Expander(label="⚠ " + p.warning)
            exp.set_child(inner)
            col.append(exp)
        else:
            col.append(inner)

        self.mine_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        col.append(self.mine_box)
        self.mine_ids = None
        self.set_my_replies(my_replies)

        bar = Gtk.Box(spacing=4)
        self.actions = Gtk.Box(spacing=4)
        self.actions.set_hexpand(True)
        bar.append(self.actions)
        self.more = Gtk.MenuButton()
        self.more.set_child(Gtk.Label(label="⋯"))  # (a label of its own: no ▾ beside it)
        self.more.add_css_class("flat")
        self.more.add_css_class("ft-action")
        tip(self.more, _("more"))
        self.more.set_create_popup_func(self._fill_menu)
        bar.append(self.more)
        col.append(bar)

    def set_my_replies(self, replies):
        """ "you replied" under the post (as Qt shows it), the newest few; rebuilt only
        when they changed — a reply just sent shows at once (the "parents" event)."""
        replies = list(replies or ())
        ids = tuple(r.id for r in replies)
        if ids == self.mine_ids:
            return
        self.mine_ids = ids
        while (child := self.mine_box.get_first_child()) is not None:
            self.mine_box.remove(child)
        for mine in replies[:3]:
            when = self.ctx.theme.date(mine.created) if mine.created else ""
            lab = _label(link_markup(f"fedtail:thread/{mine.id}",
                                     "↳ " + _("you_replied", when=when,
                                              text=snippet(mine, 80))),
                         ("ft-myreply",), markup=True, wrap=True)
            lab.connect("activate-link", self._link)
            self.mine_box.append(lab)
        self.mine_box.set_visible(bool(replies))

    def add_conversation(self, text, last_id):
        """A conversation card (common/lane.py conversation_line): the rest of it."""
        lab = _label(link_markup(f"fedtail:thread/{last_id}", "💬 " + text), ("ft-ctx",),
                     markup=True, wrap=True)
        lab.connect("activate-link", self._link)
        self.column.insert_child_after(lab, self.mine_box)

    def _body(self, p):
        cfg = self.ctx.cfg
        html = self.ctx.view.in_app(p) if cfg["ui"]["links_in_app"] else p.text
        html = richtext.clean(html, markup=cfg["feed"]["text_markup"])
        if not cfg["feed"]["emoji"]:
            html = richtext.strip_emoji(html, p.emojis)
        lab = _label(pango.markup(html, sanitized=True), ("ft-body",), markup=True, wrap=True)
        lab.connect("activate-link", self._link)
        return lab

    def _media(self, p):
        """Pictures in a row, cut to the card (their focus point is not used yet); a
        video or a sound is a line to open; a click opens the original outside."""
        box = Gtk.Box(spacing=4)
        from ...core import config
        sensitive = p.sensitive and config.sensitive_media(self.ctx.cfg) == "hide"
        for m in p.media[:4]:
            if m.kind in ("image", "gifv", "video") and (m.preview or m.url) and \
                    self.ctx.images is not None and not sensitive:
                pic = Gtk.Picture()
                pic.set_can_shrink(True)
                pic.set_content_fit(Gtk.ContentFit.COVER)
                pic.set_size_request(-1, THUMB_H)
                pic.set_hexpand(True)
                pic.add_css_class("ft-thumb")
                pic.set_overflow(Gtk.Overflow.HIDDEN)
                pic.set_alternative_text(m.alt or None)
                if m.alt:
                    tip(pic, m.alt)
                self.ctx.images.get(m.preview or m.url, pic.set_paintable)
                click = Gtk.GestureClick()
                click.connect("released", lambda *_a, u=m.url or m.remote_url:
                              self.ctx.open_url(u))
                pic.add_controller(click)
                pic.set_cursor(Gdk.Cursor.new_from_name("pointer", None))
                box.append(pic)
            else:
                word = _("media_" + m.kind) if m.kind in ("image", "video", "audio", "gifv") \
                    else _("media_unknown")
                if sensitive:
                    word = "⚠ " + _("sensitive_media") + " · " + word
                lab = _label(link_markup(m.url or m.remote_url, "📎 " + word), ("ft-muted",),
                             markup=True)
                lab.connect("activate-link", lambda _l, u: (self.ctx.open_url(u), True)[1])
                box.append(lab)
        return box

    def _poll(self, p):
        """The results as lines with a bar each (voting comes with the editor)."""
        poll = p.poll
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        total = max(1, poll.voters or poll.votes or 0)
        for i, opt in enumerate(poll.options):
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            mine = i in poll.my_votes
            pct = (opt.votes or 0) * 100 // total if opt.votes is not None else None
            text = ("✓ " if mine else "") + opt.title + (f" — {pct}%" if pct is not None else "")
            row.append(_label(text, wrap=True))
            if pct is not None:
                bar = Gtk.LevelBar()
                bar.set_min_value(0)
                bar.set_max_value(100)
                bar.set_value(pct)
                row.append(bar)
            box.append(row)
        state = _("poll_closed") if poll.expired else (
            _("poll_until", when=self.ctx.theme.date(poll.expires)) if poll.expires else "")
        box.append(_label(f"{poll.votes} · {state}".strip(" ·"), ("ft-muted",)))
        return box

    def _quote(self, q):
        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        frame.add_css_class("ft-ctx")
        head = _label(link_markup(f"fedtail:thread/{q.id}", name_of(q.author) + " @" +
                                  q.author.handle), markup=True)
        head.connect("activate-link", self._link)
        frame.append(head)
        frame.append(self._body(q))
        return frame

    def _link_card(self, card):
        title = card.title or card.url
        text = link_markup(card.url, title)
        if card.description:
            text += "\n" + GLib.markup_escape_text(card.description[:200])
        lab = _label(text, ("ft-ctx",), markup=True, wrap=True)
        lab.connect("activate-link", self._link)
        return lab

    # ---- buttons and the menu ------------------------------------------------------
    def _actx(self):
        c = self.ctx
        return actions.Ctx(cfg=c.cfg, me_id=c.me_id, supports=c.supports,
                           subscribed=c.subscribed, thread_quiet=c.thread_quiet,
                           in_thread=c.in_thread)

    def _fill_actions(self):
        if not hasattr(self, "actions"):
            return
        while (child := self.actions.get_first_child()) is not None:
            self.actions.remove(child)
        style = self.ctx.cfg["ui"]["actions"]
        for bt in actions.buttons(self.entry, self._actx(), unread=bool(self.unread)):
            short = bt.count.replace(" · ", "")
            if style == "icons":
                text = bt.glyph + (" " + short if short else "")
            elif style == "text":
                text = bt.label + bt.count
            else:
                text = f"{bt.glyph} {bt.label}" + bt.count
            b = Gtk.Button(label=text)
            b.add_css_class("ft-action")
            b.add_css_class("flat")
            if bt.active:
                b.add_css_class("ft-active")
            tip(b, bt.label + ("\n" + _("who_right_click") if bt.who else ""))
            b.connect("clicked", lambda _b, u=bt.url: self.ctx.on_link(u))
            if bt.who:
                right = Gtk.GestureClick(button=3)
                right.connect("pressed", lambda *_a, u=bt.who: self.ctx.on_link(u))
                b.add_controller(right)
            self.actions.append(b)

    def _fill_menu(self, button):
        """The ⋯ menu, made when it opens: what's in it is common/actions.py's."""
        pop = Gtk.Popover()
        pop.set_has_arrow(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for it in actions.menu(self.entry, self._actx(), short_id=self.short_id,
                               unread=bool(self.unread)):
            if it.kind == "separator":
                box.append(Gtk.Separator())
                continue
            if it.kind not in ("link", "open", "copy"):
                continue  # lists, other accounts, translation…: not in GTK yet
            b = Gtk.Button(label=it.label)
            b.add_css_class("flat")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, it=it, pop=pop: (pop.popdown(), self._do(it)))
            box.append(b)
        pop.set_child(box)
        button.set_popover(pop)

    def _menu_at(self, x, y):
        self._fill_menu(self.more)
        pop = self.more.get_popover()
        if pop is not None:
            self.more.popup()

    def _do(self, it):
        if it.kind == "link":
            self.ctx.on_link(it.url)
        elif it.kind == "open":
            self.ctx.open_url(it.url)
        elif it.kind == "copy":
            self.get_clipboard().set(it.text)
            self.ctx.status(it.text)

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
