"""One post as a GTK widget, built from the model only (Post / Share): the face, who and
when, what it answers, the text (Pango markup), pictures, a poll, a quoted post, a
link's card, "you replied", and the buttons and ⋯ menu of common/actions.py — the
same choices the Qt card makes (qt/card.py), drawn with GTK.
"""

from __future__ import annotations

from ...core import config
from ...i18n import _
from ...model import Post, Share, real
from ...model.text import snippet
from .. import pango, richtext
from ..common import actions
from ..common.cardtext import newcomer_bit
from ..common.links import thread_url
from .gi_setup import Gdk, GLib, Gtk, Pango, fit_box, forget, tip

VIS_WORD = {"public": "pub", "unlisted": "unl", "followers": "priv", "direct": "dm"}

WRAP_MIN_CHARS = 20  # the narrowest a wrapped text asks to be
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
        # a width to start from: without one GTK lays the text out a character a line
        # to find how narrow it could go — a third of what a card cost to lay out
        lab.set_width_chars(WRAP_MIN_CHARS)
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
            ctx.images.get(url, self.set_from_paintable, max_side=max(64, size * 2),
                           owner=self)


class Card(Gtk.Box):
    """A post card. key: the lane item id (a boost and its post differ); entry: the
    Post or Share; parent: the Post it answers, "missing" or None."""

    def __init__(self, ctx, key, entry, parent=None, unread=False, short_id=None,
                 depth=0, number=None, my_replies=(), via=None, open_at=None):
        # vertical, the face laid over the column's left margin: GTK 4.18 takes a
        # horizontal box's least height as its children's at their least width — the
        # text wrapped word by word — above the natural one at the width it has, and
        # warned of every card ("reported min height 225 and natural height 199")
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.ctx, self.key = ctx, key
        self.entry = entry
        # where its thread opens (CardSpec.open_at; none given — threads.open_at)
        view = getattr(ctx, "view", None)
        self.open_at = open_at or (view.open_at() if hasattr(view, "open_at") else "post")
        self.short_id = short_id
        self.via = via  # all accounts in one window: which of mine got it
        self.add_css_class("ft-card")
        self.unread = None
        self.depth = depth
        if depth:
            self.set_margin_start(min(depth, 8) * 18)
        shape = ctx.theme.shape
        self.column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.column.set_hexpand(True)
        body = Gtk.Overlay()
        body.set_child(self.column)
        if shape.get("card_avatars", True) and ctx.images is not None:
            size = int(shape.get("avatar", 40))
            face = Avatar(ctx, self.post.author, size)
            face.set_halign(Gtk.Align.START)
            face.set_valign(Gtk.Align.START)
            # as Qt's: a click on the face opens the profile; a screen reader says so
            acc_id = self.post.author.id
            press = Gtk.GestureClick()
            press.connect("released", lambda *_a: ctx.on_link(f"fedtail:account/{acc_id}"))
            face.add_controller(press)
            face.set_cursor_from_name("pointer")
            try:  # set once, before it's shown: no round trip to the accessibility bus
                face.update_property([Gtk.AccessibleProperty.LABEL],
                                     [_("a11y_avatar", acct=self.post.author.handle)])
            except (AttributeError, TypeError):  # an older PyGObject
                pass
            body.add_overlay(face)
            self.column.set_margin_start(size + 10)
            self.column.set_size_request(-1, size)  # a short post: the face still fits
        self.append(body)
        self._build(parent, number, my_replies)
        self.set_unread(unread)
        click = Gtk.GestureClick(button=3)  # a right click: the post's menu
        click.connect("pressed", lambda _g, _n, x, y: self._menu_at(x, y))
        self.add_controller(click)

    def _booster_menu(self, anchor, acc):
        """Their profile, their @address, a list of mine — for whoever boosted."""
        from urllib.parse import quote
        pop = Gtk.Popover()
        pop.set_has_arrow(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        items = [(_("open_profile"), lambda: self.ctx.on_link(f"fedtail:account/{acc.id}")),
                 (_("copy_handle"), lambda: self.ctx.on_link(
                     "fedtail:copyhandle/" + quote(acc.handle, safe="")))]
        if acc.id != self.ctx.me_id and self.ctx.win.cfg["lists"]["enabled"]:
            items.append((_("add_to_list") + " ▾",
                          lambda: self.ctx.win.lists_popover(acc, anchor)))
        for label, fn in items:
            b = Gtk.Button(label=label)
            b.add_css_class("flat")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, f=fn: (pop.popdown(), f()))
            box.append(b)
        pop.set_child(box)
        pop.set_parent(anchor)
        pop.connect("closed", lambda p: p.unparent())
        pop.popup()
        self.booster_pop = pop
        return pop

    def set_cw(self, open_):
        """Open or close what's behind the content warning (a thread's "show all")."""
        if getattr(self, "cw_inner", None) is None:
            return
        self.cw_open = bool(open_)
        self.cw_inner.set_visible(self.cw_open)
        self.cw_btn.set_label(_("cw_hide") if self.cw_open else _("cw_show"))

    def mark(self, words, css="ft-muted"):
        """A word at the end of the card's top line: "you came from here" in a thread,
        "📌 pinned" on a profile (as Qt's)."""
        lab = _label(words, (css,))
        lab.set_hexpand(True)
        lab.set_xalign(1)
        self.head.append(lab)
        return lab

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
        box = getattr(self, "poll_box", None)
        post = self.post
        if box is not None and post.poll is not None and post.poll != getattr(
                self, "poll_shown", None):  # fresh counts (refresh, a vote elsewhere)
            self._fill_poll(box, post, getattr(self, "poll_peek", False))

    # ---- building ----------------------------------------------------------------
    def _chat_head(self, head, p):
        """As in ICQ clients and as Qt's (shape.card_header = "chat"): "Name (15:25:43
        23/06/2007)" bold in one line, mine in one colour, the others' in another; the
        name leads to the profile, the time to the thread."""
        ctx = self.ctx
        mine = p.author.id == ctx.me_id
        color = ctx.theme.c["chat_me" if mine else "chat_them"].name()
        when = ctx.theme.date(p.created, ctx.theme.words.get("chat_date")) \
            if p.created else ""

        def part(url, text):
            return (f'<a href="{GLib.markup_escape_text(url)}"><span foreground="{color}" '
                    f'weight="bold">{GLib.markup_escape_text(text)}</span></a>')
        line = GLib.markup_escape_text(ctx.theme.words.get("chat", "{name} ({when})"))
        name = part(f"fedtail:account/{p.author.id}", name_of(p.author))
        if p.author.color:  # people.nick_colors
            name = name.replace(f'foreground="{color}"', f'foreground="{p.author.color}"', 1)
        line = line.replace("{name}", name)
        line = line.replace("{when}", part(thread_url(p.id, self.open_at), when))
        lab = _label(line, ("ft-chat-name",), markup=True)
        lab.set_ellipsize(Pango.EllipsizeMode.END)  # one line: cut, never wrapped
        lab.connect("activate-link", self._link)
        tip(lab, "@" + p.author.handle + " · " + actions.vis_word(p.visibility))
        head.append(lab)
        if p.edited:
            ed = _label(link_markup(f"fedtail:history/{p.id}", _("edited_mark")),
                        ("ft-muted",), markup=True)
            ed.connect("activate-link", self._link)
            head.append(ed)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        head.append(spacer)
        if self.short_id:
            sid = _label(link_markup(f"fedtail:alias/{self.short_id}", "#" + self.short_id),
                         ("ft-mono",), markup=True)
            sid.connect("activate-link", self._link)
            tip(sid, _("short_id_tip"))
            head.append(sid)

    def _build(self, parent, number, my_replies):
        p, ctx, col = self.post, self.ctx, self.column
        if isinstance(self.entry, Share):  # who boosted it (their profile), and when
            by = self.entry.by
            text = _("boosted_by", name=GLib.markup_escape_text(name_of(by)))
            text = text.replace(GLib.markup_escape_text(name_of(by)),
                                link_markup(f"fedtail:account/{by.id}", name_of(by)), 1)
            if self.entry.created:
                text += " · " + GLib.markup_escape_text(
                    _("boost_time", when=ctx.theme.date(self.entry.created)))
            boost = _label("♻ " + text, ("ft-muted",), markup=True)
            boost.connect("activate-link", self._link)
            right = Gtk.GestureClick(button=3)  # who boosted: their own menu, as Qt's
            right.connect("pressed", lambda g, *_a, who=by, lab=boost: (
                g.set_state(Gtk.EventSequenceState.CLAIMED), self._booster_menu(lab, who)))
            boost.add_controller(right)
            col.append(boost)
        head = Gtk.Box(spacing=6)
        mark = "*" if ctx.theme.shape.get("unread_mark") == "star" else "●"
        self.dot = _label(mark, ("ft-dot",))
        tip(self.dot, _("unread_tip"))
        head.append(self.dot)
        self.head = head
        if ctx.theme.shape.get("card_header") == "chat":
            self._chat_head(head, p)
        else:
            if p.author.color:  # people.nick_colors: their name in my colour
                name = _label(f'<span foreground="{p.author.color}">'
                              f'{GLib.markup_escape_text(name_of(p.author))}</span>',
                              ("ft-name",), markup=True)
            else:
                name = _label(name_of(p.author), ("ft-name",))
            name.set_ellipsize(Pango.EllipsizeMode.END)
            head.append(name)
            handle = _label(link_markup(f"fedtail:account/{p.author.id}", "@" + p.author.handle),
                            ("ft-muted",), markup=True)
            handle.connect("activate-link", self._link)
            handle.set_ellipsize(Pango.EllipsizeMode.END)
            handle.set_hexpand(True)
            head.append(handle)
            if self.via:  # → @account, in a colour of its own (ui.account_colors), as Qt's
                from ..common.lane import account_color
                text = GLib.markup_escape_text("→ " + self.via)
                if ctx.cfg["ui"].get("account_colors", True):
                    text = (f'<span background="{account_color(self.via)}" foreground="white">'
                            f" {text} </span>")
                via_lab = _label(text, ("ft-via",), markup=True)
                tip(via_lab, _("via_tip", acct=self.via))
                head.append(via_lab)
            if number:
                head.append(_label(f"/{number}", ("ft-mono",)))
            if self.short_id:
                sid = _label(link_markup(f"fedtail:alias/{self.short_id}", "#" + self.short_id),
                             ("ft-mono",), markup=True)
                sid.connect("activate-link", self._link)
                tip(sid, _("short_id_tip"))
                head.append(sid)
            # the time (the thread), who sees it, "edited" — as Qt's header has them
            meta = []
            if p.created:
                meta.append(link_markup(thread_url(p.id, self.open_at),
                                        ctx.theme.date(p.created)))
            from . import icons
            vis_pic = icons.image(actions.vis_picture(p.visibility), ctx.theme, 14)
            if vis_pic is None:  # the theme's picture of who sees it, or the word
                meta.append(GLib.markup_escape_text(VIS_WORD.get(p.visibility, p.visibility)))
            if p.edited:
                meta.append(link_markup(f"fedtail:history/{p.id}", _("edited_mark")))
            from ..common.lane import age_days
            days = age_days(p, ctx.cfg)
            if days:
                meta.append(GLib.markup_escape_text(_("old_post", n=days)))
            info = _label(" · ".join(meta), ("ft-muted",), markup=True)
            tips = [actions.vis_word(p.visibility)]
            if p.edited:
                tips.append(_("edited_tip", when=ctx.theme.date(p.edited)))
            if days:
                tips.append(_("old_post_tip"))
            tip(info, "\n".join(tips))
            info.connect("activate-link", self._link)
            head.append(info)
            if vis_pic is not None:
                tip(vis_pic, actions.vis_word(p.visibility))
                head.append(vis_pic)
        col.append(head)

        if parent == "missing":
            col.append(_label(_("ctx_missing"), ("ft-ctx",), wrap=True))
        elif parent is None and p.reply_to and not ctx.in_thread and \
                ctx.cfg["feed"].get("show_reply_context", True):
            col.append(_label(_("ctx_loading"), ("ft-ctx",), wrap=True))  # (as Qt)
        elif isinstance(parent, Post) and not ctx.in_thread:
            text = _("ctx_reply", name=name_of(parent.author), text=snippet(parent, 160))
            ctx_lab = _label(link_markup(f"fedtail:thread/{p.id}", "↑ " + text), ("ft-ctx",),
                             markup=True, wrap=True)
            ctx_lab.connect("activate-link", self._link)
            col.append(ctx_lab)
        new = newcomer_bit(p, parent)  # someone new in a private talk
        if new is not None:
            new_lab = _label(new.text, ("ft-newcomer",), wrap=True)
            tip(new_lab, new.tip)
            col.append(new_lab)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        # the text in a box of its own: a translation takes its place and gives it back
        self.text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.text_box.append(self._body(p))
        inner.append(self.text_box)
        if p.media:
            inner.append(self._media(p))
        if p.poll is not None:
            inner.append(self._poll(p))
        quote_mode = ctx.cfg["feed"].get("quotes", "card")
        if p.quote is not None and quote_mode != "off":
            inner.append(self._quote_of(p.quote, quote_mode))
        cards = ctx.cfg["feed"].get("link_cards", "full")
        if p.card is not None and not p.media and cards != "off":
            inner.append(self._link_card(p.card))
        reacted = sorted(((r.name, r.count) for r in p.reactions if r.count > 0),
                         key=lambda x: -x[1]) if ctx.cfg["feed"].get("emoji", True) else []
        if reacted:  # emoji reactions where the server passes them on (Akkoma & kin)
            line = _label(" ".join((name if len(name) <= 4 else ":" + name.strip(":") + ":")
                                   + f" {count}" for name, count in reacted[:12]),
                          ("ft-muted",), wrap=True)
            tip(line, _("reactions_tip"))
            inner.append(line)
        # a server filter that says "warn": folded as a content warning, and closed;
        # a warning of the author's open or not as ui.expand_cw / ui.arts_mode say
        warned = list(p.filtered) if not ctx.cfg["ui"].get("arts_mode") else []
        if p.warning or warned:
            label = " · ".join(([_("filtered_by", title=", ".join(warned))] if warned else [])
                               + (["⚠ " + p.warning] if p.warning else []))
            # the warning and "show" / "hide" by it, as Qt's (an expander's arrow said
            # nothing to someone who never met one)
            self.cw_open = not warned and config.expand_cw(ctx.cfg)
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            cw = _label(label, ("ft-cw",), wrap=True)
            row.append(cw)
            self.cw_btn = Gtk.Button(halign=Gtk.Align.START)
            self.cw_btn.add_css_class("flat")
            self.cw_btn.connect("clicked", lambda _b: self.set_cw(not self.cw_open))
            row.append(self.cw_btn)
            col.append(row)
            self.cw_inner = inner
            col.append(inner)
            self.set_cw(self.cw_open)
        else:
            col.append(inner)

        self.mine_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        col.append(self.mine_box)
        self.mine_ids = None
        self.set_my_replies(my_replies)

        bar = Gtk.Box(spacing=4)
        # never wider than the lane: in a narrow window (or with big fonts) the words on
        # the buttons end in "…", the pictures stay (a wrapping row of them cost the
        # scrolling a quarter more: Python laying out every card)
        self.actions = Gtk.Box(spacing=4)
        self.actions.set_hexpand(True)
        bar.append(self.actions)
        self.more = Gtk.MenuButton()
        from . import icons
        # (a child of its own, a picture or a label: no ▾ beside it)
        self.more.set_child(icons.image("more", ctx.theme) or Gtk.Label(label="⋯"))
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

    def add_thread_news(self, bit):
        """A followed thread with new replies (common/cardtext.py thread_news_bit)."""
        lab = _label(link_markup(bit.link, bit.text), ("ft-newcomer",), markup=True, wrap=True)
        tip(lab, bit.tip)
        lab.connect("activate-link", self._link)
        self.column.insert_child_after(lab, self.mine_box)

    def add_conversation(self, text, last_id):
        """A conversation card (common/lane.py conversation_line): the rest of it."""
        lab = _label(link_markup(thread_url(last_id, self.open_at), "💬 " + text), ("ft-ctx",),
                     markup=True, wrap=True)
        lab.connect("activate-link", self._link)
        self.column.insert_child_after(lab, self.mine_box)

    def _body(self, p):
        cfg = self.ctx.cfg
        html = self.ctx.view.in_app(p) if cfg["ui"]["links_in_app"] else p.text
        html = richtext.clean(html, markup=cfg["feed"]["text_markup"])
        if not cfg["feed"]["emoji"]:
            html = richtext.strip_emoji(html, p.emojis)
        # one Pango layout, not a wrapping label: a quarter of the cost (textblock.py)
        from .textblock import TextBlock
        self.body_block = TextBlock(pango.markup(html, sanitized=True),
                                    self.ctx.theme.c["link"].name(),
                                    lambda uri: self._link(None, uri), css=("ft-body",),
                                    on_select=self._selection_menu)
        return self.body_block

    def _selection_menu(self, text, _x, _y):
        """A right click on selected text: quote it in a reply, copy it (as Qt's)."""
        pop = Gtk.Popover()
        pop.set_has_arrow(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        items = []
        if self._can_quote():
            items.append((_("quote_in_reply"), lambda: self.ctx.win.quote_reply(
                self.entry, text)))
        items.append((_("copy"), lambda: (self.get_clipboard().set(text),
                                         self.ctx.status(text[:120]))))
        for label, fn in items:
            b = Gtk.Button(label=label)
            b.add_css_class("flat")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, f=fn: (pop.popdown(), f()))
            box.append(b)
        pop.set_child(box)
        pop.set_parent(self.body_block)
        pop.connect("closed", lambda p: p.unparent())
        pop.popup()
        self.selection_pop = pop
        return pop

    def _can_quote(self):
        return self.ctx.me_id is not None and \
            bool(self.ctx.cfg["post"].get("quote_prefix", "> "))

    def _media(self, p):
        """Pictures as the Qt card has them: one alone — ui.image_height tall, as wide
        as its shape says (up to the lane's width), never cut; several — tiles of their
        own shape, three in a row. A click: the viewer over the window (ui.image_viewer),
        a video or a gif — outside for now; marked sensitive — covered until clicked."""
        from ..common.lane import card_boxes, decode_side, thumb_box, true_kind
        atts = [true_kind(m) for m in p.media]
        grid = Gtk.Grid(column_spacing=6, row_spacing=6, halign=Gtk.Align.START)
        visual = [m for m in atts if m.kind in ("image", "gifv", "video")
                  and (m.preview or m.url) and self.ctx.images is not None]
        images = [m for m in visual if m.kind == "image"]
        height, max_w = card_boxes(visual, self.ctx.cfg)
        covered = p.sensitive and not p.warning and not getattr(self, "media_revealed", False) \
            and config.sensitive_media(self.ctx.cfg) == "hide"
        pos = 0
        for m in atts:
            full = m.url or m.remote_url
            if m in visual:
                tw, th = thumb_box(m.width, m.height, height, max_w)
                if covered:
                    cell = Gtk.Button(label="⚠ " + _("sensitive_media") + "\n" +
                                      _("sensitive_click"))
                    cell.add_css_class("ft-thumb")
                    cell.connect("clicked", lambda _b: self._reveal_media())
                else:
                    cell = self._picture(m, tw, th, decode_side(
                        tw, th, m.width, m.height, self.ctx.cfg,
                        self.get_scale_factor() or 1.0) or 1200, images, full)
                cell = fit_box(cell, tw, th)  # narrows with the window, its shape kept
                if m.alt:
                    tip(cell, m.alt)
                grid.attach(cell, pos % 3, pos // 3, 1, 1)
                pos += 1
            else:
                word = _("media_" + m.kind) if m.kind in ("image", "video", "audio", "gifv") \
                    else _("media_unknown")
                lab = _label(link_markup(full, ("▶ " if m.kind == "audio" else "📎 ") + word),
                             ("ft-muted",), markup=True)
                if m.kind == "audio":  # played here, as Qt's (the player, sound only)
                    moving = [x for x in p.media if x.kind in ("video", "gifv", "audio")]
                    lab.connect("activate-link", lambda _l, _u, a=m, mv=moving: (
                        self.ctx.win.play_media(mv, mv.index(a) if a in mv else 0), True)[1])
                else:
                    lab.connect("activate-link",
                                lambda _l, u: (self.ctx.open_url(u), True)[1])
                row = -(-pos // 3)
                grid.attach(lab, 0, row, 3, 1)
                pos = (row + 1) * 3
        if self.ctx.cfg["ui"].get("alt_text") == "caption" and not covered:
            row = -(-pos // 3)
            for i, m in enumerate(visual):
                if m.alt.strip():
                    num = f"{i + 1}. " if len(visual) > 1 else ""
                    grid.attach(_label(num + m.alt.strip()[:400], ("ft-muted",), wrap=True),
                                0, row, 3, 1)
                    row += 1
        self.media_box = grid
        return grid

    def _picture(self, m, tw, th, side, images, full):
        """One picture in its box (cut to it only by a hair: the box has its shape); a
        video or a gif: its still frame with ▶ over it."""
        pic = Gtk.Picture()
        pic.set_can_shrink(True)
        # the box has the picture's shape when the server said its size: filled; a size
        # not said (a square box) — the whole picture in it, not cut to a square
        pic.set_content_fit(Gtk.ContentFit.COVER if m.width and m.height
                            else Gtk.ContentFit.CONTAIN)
        pic.add_css_class("ft-thumb")
        pic.set_overflow(Gtk.Overflow.HIDDEN)
        pic.set_alternative_text(m.alt or _("a11y_no_alt"))
        # a video's still frame only — never the video itself fetched as a picture (as Qt)
        src = (m.preview or full) if m.kind == "image" else m.preview
        over = Gtk.Overlay()
        over.set_child(pic)
        over.set_overflow(Gtk.Overflow.HIDDEN)
        # "loading…" over the box until it comes; if it never does, said (a click still
        # opens it) — as Qt's
        state = _label(_("image_loading"), ("ft-muted",), wrap=True)
        state.set_halign(Gtk.Align.CENTER)
        state.set_valign(Gtk.Align.CENTER)
        state.set_justify(Gtk.Justification.CENTER)
        over.add_overlay(state)

        def came(paintable):
            pic.set_paintable(paintable)
            state.set_visible(False)

        def failed():
            state.set_text(_("image_failed") if m.kind == "image" else
                           "▶ " + _("media_" + m.kind) + "\n" + _("media_click"))
        if src:
            self.ctx.images.get(src, came, max_side=side, failed=failed, original=full,
                                owner=pic)
        else:
            failed()
        if m.kind != "image":
            play = Gtk.Label(label="▶")
            play.add_css_class("ft-play")
            play.set_halign(Gtk.Align.CENTER)
            play.set_valign(Gtk.Align.CENTER)
            over.add_overlay(play)
        click = Gtk.GestureClick()
        if m.kind == "image" and m in images:
            idx = images.index(m)
            click.connect("released", lambda *_a: self.ctx.show_images(images, idx))
        elif m.kind in ("video", "gifv"):  # the player over the window, as Qt's
            moving = [x for x in self.post.media if x.kind in ("video", "gifv", "audio")]
            idx = moving.index(m) if m in moving else 0
            click.connect("released", lambda *_a: self.ctx.win.play_media(moving, idx))
        else:
            click.connect("released", lambda *_a: self.ctx.open_url(full))
        over.add_controller(click)
        right = Gtk.GestureClick(button=3)  # its own menu, not the post's
        right.connect("pressed", lambda g, *_a: (
            g.set_state(Gtk.EventSequenceState.CLAIMED), self._media_menu(over, m)))
        over.add_controller(right)
        over.set_cursor(Gdk.Cursor.new_from_name("pointer", None))
        return over

    def _media_menu(self, anchor, m):
        """Save it, open it in the browser, copy its link — as Qt's."""
        url = m.url or m.remote_url or m.preview
        pop = Gtk.Popover()
        pop.set_has_arrow(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        items = [(_("save_image") if m.kind == "image" else _("save_media"),
                  lambda: self.ctx.save_media(m)),
                 (_("open_browser"), lambda: self.ctx.open_url(url)),
                 (_("copy_link"), lambda: (self.get_clipboard().set(url),
                                           self.ctx.status(url)))]
        for label, fn in items:
            b = Gtk.Button(label=label)
            b.add_css_class("flat")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, f=fn: (pop.popdown(), f()))
            box.append(b)
        pop.set_child(box)
        pop.set_parent(anchor)
        pop.connect("closed", lambda p: p.unparent())
        pop.popup()
        self.media_pop = pop
        return pop

    def _reveal_media(self):
        self.media_revealed = True
        old = getattr(self, "media_box", None)
        if old is None or old.get_parent() is None:
            return
        parent = old.get_parent()
        new = self._media(self.post)
        parent.insert_child_after(new, old)
        parent.remove(old)
        forget(old)

    def _poll(self, p):
        """Options to pick and Vote (or a peek at the results), as in Qt; the results
        as lines with a bar each — after voting, when it's over, on my own post."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.poll_box = box
        self._fill_poll(box, p, False)
        return box

    def _fill_poll(self, box, p, peek):
        while (c := box.get_first_child()) is not None:
            box.remove(c)
            forget(c)
        poll = p.poll
        self.poll_shown, self.poll_peek = poll, peek
        mine = p.author.id == self.ctx.me_id
        if poll.voted or poll.expired or mine or peek:
            total = max(1, poll.total)
            for i, opt in enumerate(poll.options):
                row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                pct = (opt.votes or 0) * 100 // total if opt.votes is not None else None
                text = ("✓ " if i in poll.my_votes else "") + opt.title + \
                    (f" — {pct}%" if pct is not None else "")
                row.append(_label(text, wrap=True))
                if pct is not None:
                    bar = Gtk.LevelBar()
                    bar.set_min_value(0)
                    bar.set_max_value(100)
                    bar.set_value(pct)
                    row.append(bar)
                box.append(row)
        else:
            picks, first = [], None
            for opt in poll.options:
                b = Gtk.CheckButton(label=opt.title)
                if not poll.multiple:  # one of them: radio buttons
                    if first is None:
                        first = b
                    else:
                        b.set_group(first)
                picks.append(b)
                box.append(b)
            row = Gtk.Box(spacing=6)
            vote = Gtk.Button(label=_("poll_vote"))
            vote.set_sensitive(False)
            peek_b = Gtk.Button(label=_("poll_results"))
            peek_b.add_css_class("flat")
            for b in picks:
                b.connect("toggled", lambda *_a: vote.set_sensitive(
                    any(x.get_active() for x in picks)))

            def send(_b):
                vote.set_sensitive(False)
                vote.set_label(_("poll_sending"))
                chosen = [i for i, x in enumerate(picks) if x.get_active()]

                def done(post):
                    self.ctx.win.status(_("poll_voted"))
                    if post is not None and getattr(post, "poll", None) is not None:
                        self._fill_poll(box, post, False)
                self.ctx.win.call(self.ctx.view.vote(p, chosen), done,
                                  lambda e: (vote.set_label(_("poll_vote")),
                                             vote.set_sensitive(True),
                                             self.ctx.win.error(e)))
            vote.connect("clicked", send)
            peek_b.connect("clicked", lambda _b: self._fill_poll(box, p, True))
            row.append(vote)
            row.append(peek_b)
            box.append(row)
        n = poll.people if poll.people is not None else poll.votes
        parts = [_("poll_people" if poll.people is not None else "poll_votes", n=n)]
        if poll.expired:
            parts.append(_("poll_closed"))
        elif poll.expires:
            parts.append(_("poll_until", when=self.ctx.theme.date(poll.expires)))
        if poll.multiple:
            parts.append(_("poll_multiple"))
        foot = GLib.markup_escape_text(" · ".join(parts))
        if not poll.expired:  # fresh counts from the server, as Qt's "refresh"
            foot += " · " + link_markup("fedtail:poll-refresh", _("poll_refresh"))
        lab = _label(foot, ("ft-muted",), markup=True)
        lab.connect("activate-link", lambda _l, _u: (self.refresh_poll(box, p, peek), True)[1])
        box.append(lab)

    def refresh_poll(self, box, p, peek):
        def done(post):
            post = real(post) if post is not None and hasattr(post, "id") else \
                self.ctx.view.by_id(p.id)
            if post is not None and getattr(post, "poll", None) is not None:
                self._fill_poll(box, real(post), peek)
        self.ctx.win.call(self.ctx.view.refresh_poll(p), done, self.ctx.win.error)

    def _quote_of(self, quote, mode):
        """The quoted post framed in this one (feed.quotes = "card") or a line with a
        link to it ("link"); a quote that can't be shown says why — as in Qt."""
        state, q, qid = quote.state, quote.post, quote.id
        if state != "accepted" or (q is None and not qid):
            key = "quote_" + state
            why = _(key) if _(key) != key else _("quote_unavailable")
            text = GLib.markup_escape_text("❝ " + why)
            if qid and state in ("blocked_account", "blocked_domain", "muted_account"):
                text += " · " + link_markup(f"fedtail:thread/{qid}", _("quote_show_anyway"))
            lab = _label(text, ("ft-muted",), markup=True, wrap=True)
            lab.connect("activate-link", self._link)
            return lab
        if q is None or mode == "link":
            words = "❝ " + (_("quote_by", name=name_of(q.author)) + ": " + snippet(q, 90)
                            if q is not None else _("quote_open"))
            lab = _label(link_markup(f"fedtail:thread/{qid}", words), markup=True, wrap=True)
            lab.connect("activate-link", self._link)
            return lab
        return self._quote(q)

    def _quote(self, q):
        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        frame.add_css_class("ft-ctx")
        head = _label(link_markup(f"fedtail:thread/{q.id}", name_of(q.author) + " @" +
                                  q.author.handle), markup=True)
        head.connect("activate-link", self._link)
        frame.append(head)
        if q.warning:  # a warning stays a warning inside a quote too
            frame.append(_label("⚠ " + q.warning, ("ft-muted",), wrap=True))
        else:
            frame.append(self._body(q))
            if q.media:
                frame.append(_label("🖼 " + _("quote_media", n=len(q.media)), ("ft-muted",)))
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
                           in_thread=c.in_thread,
                           long_form=bool(c.cfg["feed"].get("long_form", True)),
                           lists=True,
                           translate=bool(getattr(c.view.caps, "translation", False)),
                           translates=getattr(c.view, "translation_languages", None),
                           quote_reply=self._can_quote())

    def _fill_actions(self):
        if not hasattr(self, "actions"):
            return
        while (child := self.actions.get_first_child()) is not None:
            self.actions.remove(child)
        from . import icons
        style = self.ctx.cfg["ui"]["actions"]
        own = icons.wanted(self.ctx.theme)  # the messengers' look (split, "additional")
        if own and style == "text":
            style = "both"  # the split layout has pictures by the words, as messengers did
        for bt in actions.buttons(self.entry, self._actx(), unread=bool(self.unread),
                                  open_at=self.open_at):
            short = bt.count.replace(" · ", "")
            pic = actions.action_picture(bt.action, bt.active) or bt.action
            img = icons.image(pic, self.ctx.theme)
            if style == "icons":
                text = (bt.glyph + " " if img is None else "") + short
            elif style == "text":
                text = bt.label + bt.count
            else:
                text = ("" if img is not None else bt.glyph + " ") + bt.label + bt.count
            b = Gtk.Button()
            words = Gtk.Label(label=text.strip()) if text.strip() else None
            if words is not None:
                words.set_ellipsize(Pango.EllipsizeMode.END)
                words.set_width_chars(min(3, len(text.strip())))
            if img is not None:
                inner = Gtk.Box(spacing=4)
                inner.append(img)
                if words is not None:
                    inner.append(words)
                b.set_child(inner)
            else:
                b.set_child(words or Gtk.Label())
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
            if it.kind not in ("link", "open", "copy", "long_form", "translate", "lists",
                               "quote_reply"):
                continue  # as another account: not in GTK yet
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
        if it.kind == "lists":
            self.ctx.win.lists_popover(it.data, self.more)
        elif it.kind == "translate":
            self.translate()
        elif it.kind == "quote_reply":  # ↩ quoting what's selected, or all of it
            from ...model.text import html_to_text, without_quote_fallback
            block = getattr(self, "body_block", None)
            sel = block.selected() if block is not None else ""
            self.ctx.win.quote_reply(self.entry, sel or html_to_text(
                without_quote_fallback(self.post.text)), whole=not sel)
        elif it.kind == "long_form":
            self.ctx.win.read_whole(it.data)
        elif it.kind == "link":
            self.ctx.on_link(it.url)
        elif it.kind == "open":
            self.ctx.open_url(it.url)
        elif it.kind == "copy":
            self.get_clipboard().set(it.text)
            self.ctx.status(it.text)

    def _link(self, _label, uri):
        self.ctx.on_link(uri)
        return True  # handled: GTK must not open it itself

    # ---- translation (as Qt's: the server translates; the original a click away) -----
    def translate(self):
        tr = getattr(self, "translation", None)
        if tr is not None:
            self._show_text(not self.showing_translation)
            return
        caps = getattr(self.ctx.view, "caps", None)  # as Qt: the server says it can't
        if caps is not None and not getattr(caps, "translation", True):
            self.ctx.win.error(_("translate_none"))
            return

        def got(t):
            self.translation = t
            self._show_text(True)
        self.ctx.win.call(self.ctx.view.translate(self.post), got)

    def _show_text(self, translated):
        self.showing_translation = translated
        box = self.text_box
        while (c := box.get_first_child()) is not None:
            box.remove(c)
            forget(c)
        p = self.post
        if translated:
            from dataclasses import replace as _replace
            tr = self.translation
            row = Gtk.Box(spacing=8)
            row.append(_label(_("translated_from", lang=tr.lang or "?",
                                provider=tr.provider or ""), ("ft-muted",), wrap=True))
            back = Gtk.Button(label=_("show_original"))
            back.add_css_class("flat")
            back.connect("clicked", lambda _b: self._show_text(False))
            row.append(back)
            box.append(row)
            box.append(self._body(_replace(p, text=tr.html or p.text)))
        else:
            box.append(self._body(p))


class Separator(Gtk.Box):
    """The "new below" line."""

    def __init__(self, text):
        super().__init__()
        self.key = "__sep__"
        lab = _label(text, ("ft-separator",), xalign=0.5)
        lab.set_hexpand(True)
        self.append(lab)
