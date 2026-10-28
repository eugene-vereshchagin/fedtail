"""One post on screen, and the "new below" divider."""

import re
from dataclasses import replace
from urllib.parse import quote, unquote

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...core import config
from ...i18n import _
from ...model import Share
from ...model.text import (
    collapse_tag_stuffing,
    html_to_text,
    is_bot,
    snippet,
    without_quote_fallback,
)
from ..common import actions
from ..common.cardtext import newcomer_bit, thread_news_bit
from ..common.lane import (  # noqa: F401  (Qt's names)
    VIDEO_EXT,
    CardSpec,
    conversation_line,
    decode_side,
    make_spec,
    thumb_box,
)
from ..common.lane import true_kind as _true_kind
from ..richtext import plain_tip
from .text import clean, display_name, emojify, esc, link, strip_emoji

RAIL_W = 20
MAX_DEPTH_INDENT = 8
THUMB_H = 170
THUMB_MAX_W = 380
# fedtail's own pictures for a post's buttons (frontends/qt/icons.py)
VIS_WORD = {"public": "pub", "unlisted": "unl", "followers": "priv", "direct": "dm"}
VIS_KEY = {"followers": "private"}  # the words for it in i18n: vis_private
QUOTE_SHOWN = {"accepted"}


class ClickLabel(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class ClickFrame(QFrame):
    clicked = Signal()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)


def _host(url):
    from urllib.parse import urlsplit
    host = urlsplit(url).hostname or ""
    return host[4:] if host.startswith("www.") else host


def _fill_html(fmt, **parts):
    """A theme's words with HTML put in: the words' own letters escaped ("<{name}>" in
    the psi theme stays angle brackets), the parts as they are."""
    from string import Formatter
    out = []
    for literal, key, _spec, _conv in Formatter().parse(fmt):
        out.append(esc(literal))
        if key is not None:
            out.append(parts.get(key, ""))
    return "".join(out)


def emoji_reactions(post):
    """[(name, count)] — emoji reactions where the server passes them on (Akkoma,
    Pleroma, Fedibird, Iceshrimp and kin), the most given first."""
    return sorted(((r.name, r.count) for r in post.reactions if r.count > 0),
                  key=lambda r: -r[1])


def _set_prop(w, name, value):
    if w.property(name) != value:
        w.setProperty(name, value)
        w.style().unpolish(w)
        w.style().polish(w)


class WrapLabel(QLabel):
    """A word-wrapped label that always takes the height its text needs at the
    width it actually got. Plain QLabel, deep in nested layouts, sometimes gets
    a height computed for another width, and the last lines get cut off."""

    _fit_for = None  # (width, text) the minimum height was last worked out for

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not self.wordWrap():
            return
        # laying out rich text is the costly part, and a resize that only changes the
        # height (the one setMinimumHeight itself causes) can't change the answer
        key = (self.width(), self.text())
        if key == self._fit_for:
            return
        self._fit_for = key
        h = self.heightForWidth(self.width())
        if h > 0 and h != self.minimumHeight():
            self.setMinimumHeight(h)


class SeparatorRow(QWidget):
    """'new below · 12' between what was read and what wasn't."""

    def __init__(self, spec, ctx):
        super().__init__()
        self.spec = spec
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 6, 0, 6)
        h.setSpacing(12)
        lines = ctx.theme.shape["card_style"] == "card"
        if lines:
            left = QFrame()
            left.setObjectName("sepLine")
            h.addWidget(left, 1)
        self.label = QLabel(spec.extra["separator"])
        self.label.setObjectName("sepText")
        h.addWidget(self.label, 0 if lines else 1)
        if lines:
            right = QFrame()
            right.setObjectName("sepLine")
            h.addWidget(right, 1)

    status_id = None
    real_id = None

    def update_spec(self, spec):
        self.spec = spec
        self.label.setText(spec.extra["separator"])

    def set_unread(self, _unread):
        pass


class EventRow(QWidget):
    """An event's row in any lane that takes events — Activity, Requests, a lane of
    one's own (common/activity.EventParts, the same parts every interface draws): who —
    what · when, the post it is about, × and a request's yes / no. Every button is a
    fedtail: link (common/links.py). Unread until seen on screen, as a post is; seen
    here is seen everywhere (its key goes to LaneModel.read)."""

    real_id = None

    def __init__(self, spec, ctx):
        super().__init__()
        self.ctx = ctx
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 2, 0, 2)
        self.card = None
        self.update_spec(spec)

    @property
    def status_id(self):
        return self.spec.key  # "event:<id>": what LaneModel.read marks seen

    def update_spec(self, spec):
        from ..common.activity import ANSWER_WORDS, event_parts
        self.spec = spec
        if self.card is not None:
            self.lay.removeWidget(self.card)
            self.card.deleteLater()
        theme, link = self.ctx.theme, self.ctx.on_link
        dismiss_one = bool(self.ctx.supports("dismiss_one")) if self.ctx.supports else True
        parts = event_parts(spec.extra["row"], theme.date, dismiss_one)
        card = self.card = QFrame()
        card.setObjectName("card")
        card.setProperty("kind", parts.kind)  # what it is about: tests, stylesheets
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 10, 16, 10)
        v.setSpacing(4)
        text, muted = theme.c["text"].name(), theme.c["muted"].name()
        if parts.notice:  # from the server itself: what happened, not who did it
            who = f"<b>⚠ {esc(parts.notice)}</b>"
        else:
            who = ", ".join(f'<a href="{esc(u)}" style="text-decoration:none;color:{text};">'
                            f"<b>{esc(n)}</b></a>" for n, u in parts.people)
            who += (" " + esc(parts.more)) if parts.more else ""
        top = WrapLabel(f'{who} <span style="color:{muted};">— {esc(parts.what)}'
                     + (f" · {esc(parts.when)}" if parts.when else "") + "</span>")
        top.setTextFormat(Qt.TextFormat.RichText)
        top.setWordWrap(True)
        top.setToolTip(parts.tip)
        top.linkActivated.connect(link)
        line = QHBoxLayout()
        line.addWidget(top, 1)
        x = QPushButton("×")
        x.setObjectName("tool")  # as wide as the theme's padding needs (a fixed 28 px cut the
        # cross down to a dot in a roomy theme)
        x.setToolTip(parts.hide_tip)
        x.clicked.connect(lambda _c=False, u=parts.hide: link(u))
        line.addWidget(x, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(line)
        for yes, no in parts.answers:  # waiting for my yes: answered right here
            row = QHBoxLayout()
            row.addStretch(1)
            for url, (words, tip) in zip((yes, no), ANSWER_WORDS, strict=True):
                b = QPushButton(_(words))
                b.setObjectName("primary" if url == yes else "tool")
                b.setToolTip(_(tip))
                b.clicked.connect(lambda _c=False, u=url: link(u))
                row.addWidget(b)
            v.addLayout(row)
        if parts.post:
            post = WrapLabel(f'<a href="{esc(parts.post_link)}" style="text-decoration:none;'
                          f'color:{muted};">{esc(parts.post)}</a>')
            post.setTextFormat(Qt.TextFormat.RichText)
            post.setWordWrap(True)
            post.setCursor(Qt.CursorShape.PointingHandCursor)
            post.linkActivated.connect(link)
            v.addWidget(post)
        self.lay.addWidget(card)
        self.set_unread(spec.unread)

    def set_unread(self, unread):
        self.spec.unread = unread
        _set_prop(self.card, "unread", "true" if unread else "false")


def row_class(spec):
    """The row a spec makes in a FeedView: the divider, an event, or a post."""
    if spec.extra.get("separator"):
        return SeparatorRow
    return EventRow if spec.extra.get("event") else PostRow


class PostRow(QWidget):
    """Thread rails + the card itself."""

    def __init__(self, spec, ctx):
        super().__init__()
        self.ctx = ctx
        self.spec = spec
        self.theme = ctx.theme
        self.cw_open = config.expand_cw(ctx.cfg)
        self.translation = None
        self.show_translation = False
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        for _i in range(min(spec.depth, MAX_DEPTH_INDENT)):
            rail_box = QWidget()
            rail_box.setFixedWidth(RAIL_W)
            rb = QHBoxLayout(rail_box)
            rb.setContentsMargins(0, 0, 0, 0)
            rail = QFrame()
            rail.setObjectName("rail")
            rail.setFixedWidth(2)
            rb.addWidget(rail, 0, Qt.AlignmentFlag.AlignHCenter)
            row.addWidget(rail_box)
        if spec.depth:
            row.addSpacing(6)
        self.card = QFrame()
        self.card.setObjectName("card")
        self.card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        # a right click anywhere on the card opens the post's ⋯ menu; connected once,
        # the menu itself is rebuilt with the card
        self._menu = None
        self._has_menu = False  # a ⋯ button was made (_more_button)
        self.card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.card.customContextMenuRequested.connect(self._card_menu)
        row.addWidget(self.card)
        self.lay = QVBoxLayout(self.card)
        if self.theme.shape["card_style"] == "rule":
            self.lay.setContentsMargins(6, 10, 6, 14)
        else:
            self.lay.setContentsMargins(18, 14, 18, 12)
        self.lay.setSpacing(0)
        self.body = None
        self.mark = None
        self._build()
        self._flags()

    def _edited_mark(self, p):
        """"· edited", a link to the versions."""
        mark = link("history", p.id, _("edited_mark"), self.theme.css("muted"))
        lab = self._label("· " + mark, "meta", wrap=False)
        lab.setToolTip(_("edited_tip", when=self.theme.date(p.edited)))
        return lab

    def _card_menu(self, pos):
        menu = self._menu_now()
        if menu is not None:
            menu.exec(self.card.mapToGlobal(pos))

    def _text_menu(self, lab, pos):
        """A right click on the post's text: the post's menu too (a long post is all
        text, and its own menu used to stand in the way), with Copy on top when
        something is selected."""
        if self.ensure_menu() is None:
            return
        menu = QMenu(lab)
        if lab.hasSelectedText():
            sel = lab.selectedText()
            if self._can_quote():
                menu.addAction(_("quote_in_reply"), lambda: self._quote_reply(sel))
            menu.addAction(_("copy"), lambda: QGuiApplication.clipboard().setText(sel))
            menu.addSeparator()
        menu.addActions(self._menu.actions())
        menu.exec(lab.mapToGlobal(pos))

    def _can_quote(self):
        return self.ctx.quote_reply is not None and \
            bool(self.ctx.cfg["post"].get("quote_prefix", "> "))

    def _selected_text(self):
        """What is selected in the post's text, if anything."""
        if self.body is None:
            return ""
        for lab in self.body.findChildren(QLabel):
            if lab.hasSelectedText():
                return lab.selectedText()
        return ""

    def _quote_reply(self, text=None):
        """↩ with a quote: the text given, what is selected in the post, or all of it."""
        p = self.spec.post
        whole = text is None and not self._selected_text()
        text = text or self._selected_text() or html_to_text(without_quote_fallback(p.text))
        self.ctx.quote_reply(self.spec.entry, text, whole)

    def _route_text_menus(self):
        for lab in self.body.findChildren(QLabel):
            if lab.contextMenuPolicy() == Qt.ContextMenuPolicy.DefaultContextMenu:
                lab.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                lab.customContextMenuRequested.connect(
                    lambda pos, w=lab: self._text_menu(w, pos))

    # ---- public -----------------------------------------------------------------
    @property
    def status_id(self):
        return self.spec.entry.id

    @property
    def real_id(self):
        return self.spec.post.id

    def update_spec(self, spec):
        old = self.spec
        self.spec = spec
        if (old.entry is not spec.entry and old.entry != spec.entry) \
                or _parent_key(old.parent) != _parent_key(spec.parent) \
                or old.number != spec.number or old.focus != spec.focus \
                or old.extra.get("short_id") != spec.extra.get("short_id") \
                or _ids(old.extra.get("my_replies")) != _ids(spec.extra.get("my_replies")) \
                or _conv_key(old) != _conv_key(spec) \
                or old.extra.get("thread_news") != spec.extra.get("thread_news") \
                or old.extra.get("deleted") != spec.extra.get("deleted"):
            self._build()
        self._flags()

    def set_unread(self, unread):
        self.spec.unread = unread
        self._flags()

    # ---- building ---------------------------------------------------------------
    def _flags(self):
        _set_prop(self.card, "unread", "true" if self.spec.unread else "false")
        _set_prop(self.card, "focus", "true" if self.spec.focus else "false")
        if self.mark is not None:
            self.mark.setVisible(self.spec.unread)

    def _label(self, html="", name=None, selectable=False, wrap=True):
        lab = WrapLabel(html)
        lab.setTextFormat(Qt.TextFormat.RichText)
        lab.setWordWrap(wrap)
        lab.setOpenExternalLinks(False)
        flags = Qt.TextInteractionFlag.LinksAccessibleByMouse
        if selectable:
            flags |= Qt.TextInteractionFlag.TextSelectableByMouse
        lab.setTextInteractionFlags(flags)
        lab.linkActivated.connect(self.ctx.on_link)
        # shortened links show the whole address on hover
        lab.linkHovered.connect(lambda url: lab.setToolTip(plain_tip(_hover_text(url))))
        if name:
            lab.setObjectName(name)
        return lab

    def _emoji_label(self, html, emojis, name=None, selectable=False, wrap=True,
                     fallback=None):
        """A label whose :shortcodes: become the server's emoji pictures; the ones not
        downloaded yet are fetched and put in when they come (feed.custom_emoji).
        feed.emoji = false: no emoji at all, neither pictures nor Unicode ones; a name
        that was nothing but emoji falls back to the html given as fallback."""
        if not self.ctx.cfg["feed"].get("emoji", True):
            out = strip_emoji(html, emojis)
            if fallback is not None and not re.sub(r"<[^>]*>|\s|&nbsp;", "", out):
                out = fallback
            return self._label(out, name, selectable, wrap)
        lab = self._label(html, name, selectable, wrap)
        if not emojis or not self.ctx.cfg["feed"].get("custom_emoji", True):
            return lab
        lab.ensurePolished()
        px = max(14, lab.fontMetrics().height())

        def render():
            out, missing = emojify(html, emojis, px, self.ctx.images.local)
            try:
                lab.setText(out)
            except RuntimeError:  # the card was rebuilt meanwhile
                return []
            return missing
        for url in set(render()):
            self.ctx.images.get(url, lambda _pm: render(), 128, owner=lab)
        return lab

    def _build(self):
        self._build_body()
        self._route_text_menus()  # every time: a rebuilt card has new labels

    def _build_body(self):
        if self.body is not None:
            self.lay.removeWidget(self.body)
            self.body.deleteLater()
        self.body = QWidget()
        v = QVBoxLayout(self.body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(9)
        self.lay.addWidget(self.body)

        spec = self.spec
        entry = spec.entry
        p = spec.post

        if isinstance(entry, Share):
            # the booster's name opens their profile (a relay bot: who is behind it)
            booster = entry.by
            name = (f'<a href="fedtail:account/{esc(booster.id)}" style="color:inherit;'
                    f'text-decoration:none;">{display_name(booster)}</a>')
            line = self._emoji_label(
                _("boosted_by", name=name) + " · " +
                _("boost_time", when=self.theme.date(entry.created)),
                booster.emojis, "boost")
            # right click: the booster's profile, or into a list (a relay bot into
            # "Morning", say)
            line.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            line.customContextMenuRequested.connect(
                lambda pos, w=line, a=booster: self._booster_menu(w, a, pos))
            v.addWidget(line)

        if self.theme.shape["card_header"] == "compact":
            v.addLayout(self._header_compact(p))
        elif self.theme.shape["card_header"] == "chat":
            v.addLayout(self._header_chat(p))
        else:
            v.addLayout(self._header_rich(p))

        if not spec.in_thread and p.reply_to and self.ctx.cfg["feed"]["show_reply_context"]:
            v.addWidget(self._label(self._context_html(p), "ctx"))
        if spec.extra.get("deleted"):  # gone from its server, kept here
            gone = self._label("🗑 " + esc(_("deleted_mark")), "newcomer")
            gone.setToolTip(_("deleted_mark_tip"))
            v.addWidget(gone)
        new = newcomer_bit(p, spec.parent)  # someone new in a private talk
        if new is not None:
            lab = self._label(esc(new.text), "newcomer")
            lab.setToolTip(new.tip)
            v.addWidget(lab)

        # with its parent from the start: a widget without one becomes a window of its own
        # when shown — the CW switch below shows or hides it before it goes into the
        # layout, and every card under a CW made (and threw away) a native window: tens
        # of milliseconds each, 16 s for a lane of 300 such posts
        content = QWidget(self.body)
        cv = QVBoxLayout(content)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(8)
        quote_mode = self.ctx.cfg["feed"].get("quotes", "card")
        quote = p.quote if quote_mode != "off" else None
        tr = getattr(self, "translation", None)
        if tr and self.show_translation:
            row = QHBoxLayout()
            row.addWidget(self._label(esc(_("translated_from", lang=tr.get("lang") or "?",
                                               provider=tr.get("provider") or "")),
                                      "quoteNote"), 1)
            back = QPushButton(_("show_original"))
            back.setObjectName("tool")
            back.clicked.connect(self._translate)
            row.addWidget(back)
            cv.addLayout(row)
        if p.text:
            html = p.text
            if tr and self.show_translation and tr.get("html"):
                html = tr["html"]
            if quote:
                html = without_quote_fallback(html)
            if self.ctx.cfg["feed"].get("collapse_tags", True):
                html = collapse_tag_stuffing(html, full=bool(self.spec.in_thread))
            if self.ctx.cfg["ui"]["links_in_app"]:
                # @mentions, #tags, fediverse links stay inside
                html = self.ctx.view.in_app(replace(p, text=html))
            mk = self.ctx.cfg["feed"].get("text_markup", True)
            text = self._emoji_label(clean(html, self.theme.css("link"), mk), p.emojis,
                                     "postText", selectable=True)
            cv.addWidget(text)
        media = self._media(p)
        if media:
            cv.addWidget(media)
        if quote:
            cv.addWidget(self._quote(quote, quote_mode))
        elif not media:
            card = self._link_card(p)
            if card:
                cv.addWidget(card)
        if p.poll:
            cv.addWidget(self._poll(p))
        reacted = emoji_reactions(p) if self.ctx.cfg["feed"].get("emoji", True) else []
        if reacted:
            line = self._label(" ".join(
                (esc(name) if len(name) <= 4 else ":" + esc(name.strip(":")) + ":")
                + f" {count}" for name, count in reacted[:12]), "reactions")
            line.setToolTip(_("reactions_tip"))
            cv.addWidget(line)

        # a server filter that says "warn": folded like a content warning, closed
        warned = list(p.filtered) if not self.ctx.cfg["ui"]["arts_mode"] else []
        if warned:
            self.cw_open = False
        if p.warning or warned:
            cw_row = QHBoxLayout()
            label = " · ".join(([_("filtered_by", title=", ".join(warned))] if warned else []) +
                               (["⚠ " + p.warning] if p.warning else []))
            cw_row.addWidget(self._emoji_label(esc(label), p.emojis, "cw"), 1)
            btn = QPushButton()
            btn.setObjectName("tool")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cw_row.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)
            v.addLayout(cw_row)

            def sync():
                content.setVisible(self.cw_open)
                btn.setText(_("cw_hide") if self.cw_open else _("cw_show"))

            def toggle():
                self.cw_open = not self.cw_open
                sync()
            btn.clicked.connect(toggle)
            sync()

            def set_cw(on):  # a thread's "open every CW"
                self.cw_open = bool(on)
                sync()
            self.set_cw = set_cw
        v.addWidget(content)
        v.addWidget(self._actions(p))
        answers = spec.extra.get("my_replies") or []
        if answers:
            last = answers[-1]
            more = f" (+{len(answers) - 1})" if len(answers) > 1 else ""
            v.addWidget(self._label(link("thread", last.id, "↳ " + _(
                "you_replied", when=self.theme.date(last.created),
                text=esc(snippet(last, 120))) + more, self.theme.css("on_myreply")),
                "myreply"))
        line = conversation_line(spec)
        if line:
            text, last_id = line
            v.addWidget(self._label(link("thread", last_id, "💬 " + esc(text),
                                         self.theme.css("link")), "ctx"))
        news = thread_news_bit(spec)  # a followed thread with new replies
        if news is not None:
            lab = self._label(link("thread", p.id, esc(news.text), self.theme.css("accent"),
                                   bold=True), "threadNews")
            lab.setToolTip(news.tip)
            v.addWidget(lab)

    # ---- header -------------------------------------------------------------------
    def _short_id(self, h, replies=None, where="header"):
        """#a3f: in the header (where="header") or under the post with the number of
        replies (shape.short_id = "footer", point.im). Called from both places: each
        puts it only where the theme wants it."""
        place = where
        if (self.theme.shape.get("short_id") or "header") != place:
            return
        sid = self.spec.extra.get("short_id")
        if sid:
            text = link("alias", sid, "#" + sid, self.theme.css("muted"))
            if place == "footer" and replies:
                text += f' <span style="color:{self.theme.css("muted")};">| {int(replies)}</span>'
            lab = QLabel(text)
            lab.setObjectName("shortId")
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
            lab.setCursor(Qt.CursorShape.PointingHandCursor)
            lab.setToolTip(_("short_id_tip"))
            lab.linkActivated.connect(self.ctx.on_link)
            h.addWidget(lab, 0, Qt.AlignmentFlag.AlignTop if place == "header"
                        else Qt.AlignmentFlag.AlignVCenter)

    def _unread_mark(self):
        if self.theme.shape["unread_mark"] == "star":
            m = QLabel("*")
            m.setObjectName("star")
        else:
            m = QLabel()
            m.setObjectName("dot")
            m.setFixedSize(8, 8)
        m.setToolTip(_("unread_tip"))
        self.mark = m
        return m

    def _header_rich(self, p):
        acc = p.author
        h = QHBoxLayout()
        h.setSpacing(12)
        size = int(self.theme.shape["avatar"])
        if self.theme.shape["card_avatars"] and size:
            avatar = ClickLabel()
            avatar.setFixedSize(QSize(size, size))
            avatar.setCursor(Qt.CursorShape.PointingHandCursor)
            avatar.setToolTip("@" + acc.handle)
            avatar.setAccessibleName(_("a11y_avatar", acct=acc.handle))
            avatar.clicked.connect(lambda a=acc.id: self.ctx.on_link(f"fedtail:account/{a}"))
            h.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
            self.ctx.images.face(acc.avatar_static, size,
                                 lambda pm, w=avatar, s=size: w.setPixmap(_round(pm, s)),
                                 owner=avatar)
        line = QHBoxLayout()
        line.setSpacing(6)
        # "stacked" (point.im): the name alone on top, @address · time · … under it
        stacked = self.theme.shape["card_header"] == "stacked"
        top = line
        if stacked:
            top = QHBoxLayout()
            top.setSpacing(6)
        if self.spec.number:
            num = QLabel(f"/{self.spec.number}")
            num.setObjectName("num")
            top.addWidget(num)
        named = acc.color or self.theme.css("name")  # people.nick_colors: mine for them
        top.addWidget(self._emoji_label(link("account", acc.id, display_name(acc),
                                             named, bold=True),
                                        acc.emojis, "name", wrap=False,
                                        fallback=link("account", acc.id,
                                                      esc(acc.username or acc.handle),
                                                      named, bold=True)))
        bot = f" [{_('bot')}]" if is_bot(acc, self.ctx.cfg["lanes"]["extra_bots"]) else ""
        line.addWidget(self._label(
            f'@{esc(acc.handle)}{esc(bot)} · '
            + link("thread", p.id, self.theme.date(p.created), self.theme.css("muted")),
            "meta", wrap=False))
        vis = p.visibility
        from . import icons as pictures
        icon = pictures.icon(actions.vis_picture(vis), self.theme)
        vis_label = QLabel()
        vis_label.setToolTip(_("vis_" + VIS_KEY.get(vis, vis)))
        if icon.isNull():
            vis_label.setText("· " + VIS_WORD.get(vis, vis))
            vis_label.setObjectName("meta")
        else:
            vis_label.setPixmap(icon.pixmap(14, 14))
        line.addWidget(vis_label)
        if p.edited:
            line.addWidget(self._edited_mark(p))
        old = self._old_mark(p)
        if old:
            line.addWidget(old)
        self._via_mark(line)
        top.addWidget(self._unread_mark(), 0, Qt.AlignmentFlag.AlignVCenter)
        self._pinned_mark(top)
        top.addStretch(1)
        if self.spec.focus and self.spec.in_thread:
            came = QLabel(_("came_from"))
            came.setObjectName("cameFrom")
            top.addWidget(came)
        if stacked:
            line.addStretch(1)
            col = QVBoxLayout()
            col.setSpacing(1)
            col.addLayout(top)
            col.addLayout(line)
            h.addLayout(col, 1)
        else:
            h.addLayout(line, 1)
        self._short_id(h)
        return h

    def _old_mark(self, p):
        """An old post (feed.old_days): pulled from someone's outbox, or a thread from
        long ago — "old" in the header, so it isn't read as news."""
        days = _age_days(p, self.ctx.cfg)
        if not days:
            return None
        lab = QLabel(_("old_post", n=days))
        lab.setObjectName("meta")
        lab.setToolTip(_("old_post_tip"))
        return lab

    def _header_chat(self, p):
        """As in ICQ clients: "Name (15:25:43 23/06/2007)" bold, mine in one colour,
        the others' in another; a click on the name — the profile, on the time — the
        thread."""
        acc = p.author
        h = QHBoxLayout()
        h.setSpacing(6)
        h.addWidget(self._unread_mark())
        if self.spec.number:
            num = QLabel(f"/{self.spec.number}")
            num.setObjectName("num")
            h.addWidget(num)
        mine = acc.id == self.ctx.me_id
        color = self.theme.css("chat_me" if mine else "chat_them")
        when = self.theme.date(p.created, self.theme.words.get("chat_date")) \
            if p.created else ""
        name = link("account", acc.id, display_name(acc), acc.color or color, bold=True)
        stamp = link("thread", p.id, esc(when), color, bold=True)
        line = _fill_html(self.theme.words.get("chat", "{name} ({when})"),
                          name=name, when=stamp)
        # one line, as in the originals: a narrow window cuts the name, never wraps it
        head = self._emoji_label(line, acc.emojis, "chatName", wrap=False)
        head.setMinimumWidth(60)  # below its width: cut at the edge
        h.addWidget(head, 0)
        if p.edited:
            h.addWidget(self._edited_mark(p))
        self._via_mark(h)
        self._pinned_mark(h)
        h.addStretch(1)
        if self.spec.focus and self.spec.in_thread:
            came = QLabel(_("came_from"))
            came.setObjectName("cameFrom")
            h.addWidget(came)
        self._short_id(h)
        return h

    def _header_compact(self, p):
        acc = p.author
        h = QHBoxLayout()
        h.setSpacing(8)
        h.addWidget(self._unread_mark())
        if self.spec.number:
            num = QLabel(f"/{self.spec.number}")
            num.setObjectName("num")
            h.addWidget(num)
        size = min(int(self.theme.shape["avatar"]), 28)  # one line: a small face
        if self.theme.shape["card_avatars"] and size:
            avatar = ClickLabel()
            avatar.setFixedSize(QSize(size, size))
            avatar.setCursor(Qt.CursorShape.PointingHandCursor)
            avatar.setToolTip("@" + acc.handle)
            avatar.clicked.connect(lambda a=acc.id: self.ctx.on_link(f"fedtail:account/{a}"))
            h.addWidget(avatar)
            self.ctx.images.face(acc.avatar_static, size,
                                 lambda pm, w=avatar, s=size: w.setPixmap(_round(pm, s)),
                                 owner=avatar)
        user, _sep, host = acc.handle.partition("@")
        h.addWidget(self._label(link("account", acc.id, "@" + esc(user),
                                     acc.color or self.theme.css("text"), bold=True),
                                "name", wrap=False))
        vis = p.visibility
        bot = f" [{_('bot')}]" if is_bot(acc, self.ctx.cfg["lanes"]["extra_bots"]) else ""
        days = _age_days(p, self.ctx.cfg)
        meta = " · ".join(x for x in (esc(host) + esc(bot),
                                      link("thread", p.id, self.theme.date(p.created),
                                           self.theme.css("muted")),
                                      VIS_WORD.get(vis, vis),
                                      _("old_post", n=days) if days else "") if x)
        h.addWidget(self._label(meta, "meta", wrap=False))
        if p.edited:
            h.addWidget(self._edited_mark(p))
        self._via_mark(h)
        self._pinned_mark(h)
        h.addStretch(1)
        if self.spec.focus and self.spec.in_thread:
            came = QLabel(_("came_from"))
            came.setObjectName("cameFrom")
            h.addWidget(came)
        self._short_id(h)
        return h

    def _pinned_mark(self, row):
        if self.spec.extra.get("pinned"):
            pin = QLabel("📌 " + _("pinned"))
            pin.setObjectName("cameFrom")
            row.addWidget(pin)

    def _via_mark(self, row):
        """All accounts in one window: which of mine got this post (and acts on it)."""
        via = self.spec.extra.get("via")
        if via:
            lab = QLabel("→ " + via)
            lab.setObjectName("via")
            lab.setToolTip(_("via_tip", acct=via))
            if self.ctx.cfg["ui"].get("account_colors", True):
                # one colour per account of mine, the same every time: whose it is at a
                # glance, without reading "→ @nick"
                color = account_color(via)
                lab.setStyleSheet(f"QLabel {{ color: white; background: {color}; "
                                  "border-radius: 6px; padding: 0 6px; }")
            row.addWidget(lab)

    def _context_html(self, p):
        parent = self.spec.parent
        if parent is None:
            body = _("ctx_loading")
        elif parent == "missing":
            body = _("ctx_missing")
        else:
            body = _("ctx_reply", name="<b>" + display_name(parent.author) + "</b>",
                     text=esc(snippet(parent, 140)))
        return link("thread", p.id, f"↑ {body}", self.theme.css("muted"))

    # ---- actions ------------------------------------------------------------------
    def _actions(self, p):
        """Flat buttons under a post: icon, text or both (ui.actions)."""
        style = self.ctx.cfg["ui"]["actions"]
        box = _ActionsBox()
        box.setObjectName("actions")
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(2)
        if self.theme.shape.get("short_id") == "footer":  # point.im: #a3f | 4, left
            self._short_id(h, replies=p.counts.replies, where="footer")
        if self.theme.shape.get("actions_align") == "right":
            h.addStretch(1)
        buttons = actions.buttons(self.spec.entry, self._actions_ctx(),
                                  unread=self.spec.unread, open_at=self.spec.open_at)
        from . import icons as pictures
        own = pictures.wanted(self.theme)  # the messengers' look (split, "additional")
        if own and style == "text":
            style = "both"  # the split layout has pictures by the words, as messengers did
        for bt in buttons:
            action, glyph, label, count, active = (bt.action, bt.glyph, bt.label, bt.count,
                                                   bt.active)
            b = QToolButton()
            b.setAutoRaise(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(label)
            b.setAccessibleName(label + count)
            ic = pictures.icon(actions.action_picture(action, active) or action, self.theme)
            # the short form, for when the row doesn't fit: the icon (or the glyph) and
            # the count — never a label cut in half ("В избран…")
            short = count.replace(" · ", "")
            box.short.append((b, (glyph + (" " + short if short else "")) if ic.isNull()
                              else short, ic))
            if style == "text" or ic.isNull():
                b.setText((glyph if style == "icons" else label) + count)
                b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            else:
                b.setIcon(ic)
                if style == "icons":
                    b.setText(count.replace(" · ", ""))
                    b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon
                                         if count else Qt.ToolButtonStyle.ToolButtonIconOnly)
                else:
                    b.setText(label + count)
                    b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            if active:
                b.setProperty("active", "true")
            b.clicked.connect(lambda _c=False, u=bt.url: self.ctx.on_link(u))
            # a right click on the like or the boost: who did it
            if bt.who:
                b.setToolTip(label + "\n" + _("who_right_click"))
                b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                b.customContextMenuRequested.connect(
                    lambda _p, u=bt.who: self.ctx.on_link(u))
            h.addWidget(b)
        if self.theme.shape.get("actions_align") != "right":
            h.addStretch(1)
        h.addWidget(self._more_button())
        return box

    def _booster_menu(self, lab, acc, pos):
        menu = QMenu(lab)
        menu.addAction(_("open_profile"),
                       lambda a=acc.id: self.ctx.on_link(f"fedtail:account/{a}"))
        link = "fedtail:copyhandle/" + quote(acc.handle, safe="")
        menu.addAction(_("copy_handle"), lambda u=link: self.ctx.on_link(u))
        if self.ctx.fill_list_menu is not None and acc.id != self.ctx.me_id:
            lists = menu.addMenu(_("add_to_list"))
            lists.aboutToShow.connect(lambda m=lists, a=acc: self.ctx.fill_list_menu(m, a))
        menu.exec(lab.mapToGlobal(pos))

    def _more_button(self):
        b = QToolButton()
        b.setAutoRaise(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip(_("more"))
        b.setAccessibleName(_("more"))
        from . import icons as pictures
        ic = pictures.icon("more", self.theme)
        if ic.isNull():
            b.setText("⋯")
        else:
            b.setIcon(ic)
        # the menu is made and filled when it opens, not with every card: two dozen
        # actions and submenus per card were most of the widgets a lane held, and even an
        # empty QMenu per card (a window of its own) added up when a lane opened; what it
        # reads then — unread, subscribed, pinned — is how things are now
        self._has_menu = True  # also shown on a right click on the card (see __init__)
        if self._menu is not None:
            self._menu.clear()  # the card was rebuilt: what was in it may be stale
        b.clicked.connect(lambda _c=False, w=b: self._pop_more(w))
        return b

    def _menu_now(self):
        """The post's ⋯ menu, made the first time it's needed (filled as it shows)."""
        if self._menu is None and self._has_menu:
            menu = QMenu(self.card)
            menu.aboutToShow.connect(lambda m=menu: self._fill_more(m, self.spec.entry))
            self._menu = menu
        return self._menu

    def _pop_more(self, b):
        menu = self._menu_now()
        if menu is not None:
            menu.exec(b.mapToGlobal(QPoint(0, b.height())))

    def ensure_menu(self):
        """The post's menu with its actions in it (a right click on the text copies
        them before the menu has ever opened)."""
        menu = self._menu_now()
        if menu is not None and not menu.actions():
            self._fill_more(menu, self.spec.entry)
        return menu

    def _actions_ctx(self):
        """What common/actions.py needs to know about this window."""
        c = self.ctx
        return actions.Ctx(
            cfg=c.cfg, me_id=c.me_id, supports=c.supports, subscribed=c.subscribed,
            thread_quiet=c.thread_quiet, lists=c.fill_list_menu is not None,
            act_as=c.act_as, long_form=bool(c.long_form), translate=bool(c.translate),
            translates=getattr(getattr(c, "view", None), "translation_languages", None),
            quote_reply=self._can_quote(), in_thread=self.spec.in_thread)

    def _fill_more(self, menu, entry):
        """The post's ⋯ menu: what's in it comes from common/actions.py."""
        menu.clear()
        from .opener import open_link
        for it in actions.menu(entry, self._actions_ctx(),
                               short_id=self.spec.extra.get("short_id"),
                               unread=self.spec.unread):
            if it.kind == "separator":
                menu.addSeparator()
            elif it.kind == "link":
                menu.addAction(it.label, lambda u=it.url: self.ctx.on_link(u))
            elif it.kind == "open":
                menu.addAction(it.label, lambda u=it.url: open_link(u))
            elif it.kind == "copy":
                menu.addAction(it.label,
                               lambda t=it.text: QGuiApplication.clipboard().setText(t))
            elif it.kind == "lists":
                lists = menu.addMenu(it.label)
                lists.aboutToShow.connect(lambda m=lists, a=it.data:
                                          self.ctx.fill_list_menu(m, a))
            elif it.kind == "act_as":
                sub = menu.addMenu(it.label)
                for label, e, tag, action in it.data:
                    sub.addAction(label, lambda e=e, t=tag, a=action:
                                  self.ctx.do_act_as(e, t, a))
            elif it.kind == "long_form":
                menu.addAction(it.label, lambda e=it.data: self.ctx.long_form(e))
            elif it.kind == "translate":
                menu.addAction(it.label, self._translate)
            elif it.kind == "quote_reply":
                menu.addAction(it.label, lambda: self._quote_reply())

    # ---- media --------------------------------------------------------------------
    # ---- polls --------------------------------------------------------------------
    def _poll(self, p):
        """Options to pick and a Vote button; or the results — after voting, when
        it's over, on my own post, or when asked."""
        poll = p.poll
        box = QFrame()
        box.setObjectName("poll")
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 2, 0, 2)
        v.setSpacing(6)
        mine = p.author.id == self.ctx.me_id
        results = poll.voted or poll.expired or mine or \
            getattr(self, "poll_results", False) or self.ctx.vote is None
        options = poll.options
        if results:
            total = poll.total
            own = set(poll.my_votes)
            top = max((o.votes or 0 for o in options), default=0)
            for i, o in enumerate(options):
                n = o.votes
                pct = round(100 * (n or 0) / total) if total and n is not None else 0
                row = QHBoxLayout()
                title = esc(o.title)
                if i in own:
                    title = "✓ " + title
                if n is not None and n == top and top > 0:
                    title = f"<b>{title}</b>"
                row.addWidget(self._label(title, "pollOption"), 1)
                row.addWidget(self._label(f"{pct}%" if n is not None else "?", "meta"))
                v.addLayout(row)
                bar = QProgressBar()
                bar.setObjectName("pollBar")
                bar.setRange(0, 100)
                bar.setValue(pct)
                bar.setTextVisible(False)
                bar.setProperty("mine", "true" if i in own else "false")
                v.addWidget(bar)
        else:
            group = QButtonGroup(box)
            group.setExclusive(not poll.multiple)
            for i, o in enumerate(options):
                b = (QCheckBox if poll.multiple else QRadioButton)(o.title)
                b.setObjectName("pollChoice")
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                group.addButton(b, i)
                v.addWidget(b)
            row = QHBoxLayout()
            vote = QPushButton(_("poll_vote"))
            vote.setObjectName("tool")
            vote.setEnabled(False)
            vote.setCursor(Qt.CursorShape.PointingHandCursor)

            def picked():
                return [group.id(b) for b in group.buttons() if b.isChecked()]
            group.buttonToggled.connect(lambda *_a: vote.setEnabled(bool(picked())))

            def send():
                vote.setEnabled(False)
                vote.setText(_("poll_sending"))
                self.ctx.vote(p, picked())
            vote.clicked.connect(send)
            row.addWidget(vote)
            peek = QPushButton(_("poll_results"))
            peek.setObjectName("tool")
            peek.setCursor(Qt.CursorShape.PointingHandCursor)

            def show_results():
                self.poll_results = True
                self._build()
            peek.clicked.connect(show_results)
            row.addWidget(peek)
            row.addStretch(1)
            v.addLayout(row)
        v.addWidget(self._label(self._poll_footer(p), "meta"))
        return box

    def _poll_footer(self, p):
        poll = p.poll
        voters = poll.people
        n = voters if voters is not None else poll.votes
        parts = [_("poll_people" if voters is not None else "poll_votes", n=n)]
        if poll.expired:
            parts.append(_("poll_closed"))
        elif poll.expires:
            parts.append(_("poll_until", when=self.theme.date(poll.expires)))
        if poll.multiple:
            parts.append(_("poll_multiple"))
        if self.ctx.refresh_poll is not None and not poll.expired:
            parts.append(link("poll", p.id, _("poll_refresh")))
        return " · ".join(parts)

    def _media(self, p):
        atts = [_true_kind(m) for m in p.media]
        if not atts:
            return None
        box = QWidget()
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        visual = [m for m in atts if m.kind in ("image", "gifv", "video")
                  and (m.preview or m.url)]
        images = [x for x in visual if x.kind == "image"]
        moving = [x for x in visual if x.kind in ("gifv", "video")]
        single = len(visual) == 1
        big_h = self.ctx.cfg["ui"]["image_height"]
        big_w = max(200, (self.ctx.cfg["ui"]["max_width"] or 900) - 60)
        pos = 0
        # marked sensitive by the author, with no warning text to hide behind: covered
        # until clicked (feed.sensitive_media); under a CW the whole post is folded anyway
        covered = p.sensitive and not p.warning and \
            not getattr(self, "media_revealed", False) and \
            config.sensitive_media(self.ctx.cfg) == "hide"
        for m in atts:
            full = m.url or m.remote_url
            if m in visual and covered:
                lab = ClickLabel("⚠ " + _("sensitive_media") + "\n" + _("sensitive_click"))
                lab.setObjectName("media")
                lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lab.setWordWrap(True)
                lab.setCursor(Qt.CursorShape.PointingHandCursor)
                w, h = _dims(m)
                lab.setFixedSize(*_thumb_box(w, h, *((big_h, big_w) if single else (150, 230))))
                lab.setToolTip(plain_tip(m.alt))
                lab.clicked.connect(self._reveal_media)
                grid.addWidget(lab, pos // 3, pos % 3)
                pos += 1
                continue
            if m in visual:
                cell = (pos // 3, pos % 3)
                pos += 1
                lab = ClickLabel(_("image_loading"))
                lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lab.setToolTip(plain_tip(m.alt))
                lab.setAccessibleName(_("media_" + m.kind))
                lab.setAccessibleDescription(m.alt or _("a11y_no_alt"))
                lab.setCursor(Qt.CursorShape.PointingHandCursor)
                lab.setObjectName("media")
                # reserve the final size now, so loading never shifts the text below
                w, h = _dims(m)
                tw, th = _thumb_box(w, h, *((big_h, big_w) if single else (150, 230)))
                focus = None
                if not single and self.ctx.cfg["ui"].get("media_grid") == "square":
                    tw = th = 150
                    focus = _focus(m)
                lab.setFixedSize(tw, th)
                radius = min(10, int(self.theme.shape["radius"]))
                # right click: save it, open it
                lab.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                lab.customContextMenuRequested.connect(
                    lambda pos, w=lab, mm=m: self._media_menu(w, mm, pos))
                if m.kind == "image":
                    idx = images.index(m)
                    lab.clicked.connect(lambda i=idx: self.ctx.show_images(images, i))
                    # the preview first, at once; a single big picture then gets the full
                    # file, which may take a while (a big photo, a slow server)
                    src = m.preview or full
                    upgrade = full if single and full and full != src else None
                else:  # gifv / video: a still frame here, played over the window on a click
                    upgrade = None
                    lab.setToolTip(plain_tip(_("media_" + m.kind) + " ▶ " + m.alt))
                    lab.clicked.connect(lambda mm=m: self.ctx.play_video(mm, moving))
                    src = m.preview
                    if m.kind == "gifv" and self.ctx.loop_gifv is not None:
                        self.ctx.loop_gifv(lab, m, lambda pm, a=tw, b=th, r=radius, f=focus:
                                           _fit(pm, a, b, r, f))
                if src:
                    self._load_media(lab, src, full if src != full else None, tw, th, radius,
                                     kind=m.kind, upgrade=upgrade, focus=focus,
                                     side=_decode_side(lab, tw, th, w, h, self.ctx.cfg))
                elif m.kind != "image":  # a video without a still frame: say what it is
                    lab.setText("▶ " + _("media_" + m.kind) + "\n" + _("media_click"))
                grid.addWidget(lab, *cell)
            elif m.kind == "audio" and self.ctx.audio_bar is not None and \
                    (bar := self.ctx.audio_bar(m)) is not None:
                row = -(-pos // 3)  # a row of its own, under the pictures
                grid.addWidget(bar, row, 0, 1, 3)
                pos = (row + 1) * 3
            else:
                kind = _("media_" + (m.kind or "unknown"))
                grid.addWidget(self._label(f'<a href="{esc(full)}">[{kind}]</a>'),
                               pos // 3, pos % 3)
                pos += 1
        if self.ctx.cfg["ui"].get("alt_text") == "caption" and not covered:
            row = (pos + 2) // 3
            for i, m in enumerate(visual):
                desc = m.alt.strip()
                if desc:
                    num = f"{i + 1}. " if len(visual) > 1 else ""
                    cap = self._label(esc(num + desc[:400]), "altCaption")
                    grid.addWidget(cap, row, 0, 1, 4)
                    row += 1
        grid.setColumnStretch(3, 1)
        return box

    def _quote(self, quote, mode):
        """The quoted post, framed inside this one (feed.quotes = "card"), or a line
        with a link to it ("link"); a quote that can't be shown says why."""
        state, q, qid = quote.state, quote.post, quote.id
        if state not in QUOTE_SHOWN or (q is None and not qid):
            why = _("quote_" + state) if _("quote_" + state) != "quote_" + state \
                else _("quote_unavailable")
            line = "❝ " + why
            if qid and state in ("blocked_account", "blocked_domain", "muted_account"):
                line += " · " + link("thread", qid, _("quote_show_anyway"),
                                     self.theme.css("link"))
            return self._label(line, "quoteNote")
        if q is None or mode == "link":
            who = ""
            if q is not None:
                who = " " + _("quote_by", name=display_name(q.author)) + ": " + \
                    esc(snippet(q, 90))
            return self._label(link("thread", qid, "❝" + who if who else "❝ " +
                                    _("quote_open"), self.theme.css("link")), "quoteNote")
        box = ClickFrame()
        box.setObjectName("quoteBox")
        box.setCursor(Qt.CursorShape.PointingHandCursor)
        box.clicked.connect(lambda: self.ctx.on_link(f"fedtail:thread/{qid}"))
        v = QVBoxLayout(box)
        v.setContentsMargins(12, 8, 12, 10)
        v.setSpacing(4)
        acc = q.author
        v.addWidget(self._emoji_label(
            f"<b>{display_name(acc)}</b> @{esc(acc.handle)} · " + esc(self.theme.date(q.created)),
            acc.emojis, "quoteHead", wrap=False))
        if q.warning:
            v.addWidget(self._emoji_label("⚠ " + esc(q.warning), q.emojis, "cw"))
        else:
            html = self.ctx.view.in_app(q) if self.ctx.cfg["ui"]["links_in_app"] else q.text
            mk = self.ctx.cfg["feed"].get("text_markup", True)
            v.addWidget(self._emoji_label(clean(html, self.theme.css("link"), mk),
                                          q.emojis, "quoteText", selectable=True))
            if q.media:
                v.addWidget(self._label("🖼 " + _("quote_media", n=len(q.media)), "quoteHead"))
        return box

    def _link_card(self, p):
        """The page a post links to, as the server saw it: title, a line or two of
        description, the site, a picture (feed.link_cards)."""
        mode = self.ctx.cfg["feed"].get("link_cards", "full")
        c = p.card
        if mode == "off" or c is None or not c.url or not (c.title or c.image):
            return None
        url = c.url
        box = ClickFrame()
        box.setObjectName("linkCard")
        box.setCursor(Qt.CursorShape.PointingHandCursor)
        box.setToolTip(plain_tip(_hover_text(url)))
        box.clicked.connect(lambda: self.ctx.on_link(url))
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 10, 0)
        h.setSpacing(12)
        side = 96
        if mode == "full" and c.image:
            pic = QLabel()
            pic.setObjectName("linkCardImage")
            pic.setFixedSize(side, side)
            pic.setToolTip(plain_tip(c.image_alt))

            def got(pm, lab=pic):
                _set(lab, _fit(pm, side, side, 0))
            self.ctx.images.get(c.image, got, owner=pic)
            h.addWidget(pic, 0, Qt.AlignmentFlag.AlignTop)
        else:
            h.setContentsMargins(10, 0, 10, 0)
        col = QVBoxLayout()
        col.setContentsMargins(0, 8, 0, 8)
        col.setSpacing(2)
        site = c.provider or _host(url)
        col.addWidget(self._label(esc(site), "linkCardSite", wrap=False))
        if c.title:
            col.addWidget(self._label("<b>" + esc(c.title[:200]) + "</b>", "linkCardTitle"))
        desc = c.description.strip()
        if desc and mode == "full":
            col.addWidget(self._label(esc(desc[:220] + ("…" if len(desc) > 220 else "")),
                                      "linkCardText"))
        col.addStretch(1)
        h.addLayout(col, 1)
        return box

    def _translate(self):
        p = self.spec.post

        def done(result):
            self.translation = result or {}
            self.show_translation = True
            try:
                self._build()
            except RuntimeError:
                pass
        if getattr(self, "translation", None):
            self.show_translation = not self.show_translation
            self._build()
        elif self.ctx.translate:
            self.ctx.translate(p, done)

    def _reveal_media(self):
        self.media_revealed = True
        self._build()

    def _media_menu(self, lab, m, pos):
        menu = QMenu(lab)
        url = m.url or m.remote_url
        if self.ctx.save_image:
            menu.addAction(_("save_image") if m.kind == "image" else _("save_media"),
                           lambda: self.ctx.save_image(m))
        menu.addAction(_("open_browser"), lambda: self.ctx.open_url(url))
        menu.addAction(_("copy_link"), lambda: QGuiApplication.clipboard().setText(url))
        menu.exec(lab.mapToGlobal(pos))

    def _load_media(self, lab, src, fallback, tw, th, radius, kind="image", upgrade=None,
                    focus=None, big=False, side=None):
        """The picture into its box; if it won't come, the fallback; if nothing comes,
        say so (a click still opens it). upgrade: a sharper file to put in once this
        one is shown — if it fails, the one shown stays. A video's still frame gets a
        ▶ on it; a video without one says it's a video, not a broken picture."""
        def show(pm):
            pm = _fit(pm, tw, th, radius, focus)
            if kind != "image":
                pm = _play_mark(pm)
            try:
                lab.setPixmap(pm)
            except RuntimeError:  # the card was rebuilt meanwhile
                return
            if upgrade:
                self.ctx.images.get(upgrade, lambda big: _set(lab, _fit(big, tw, th, radius)),
                                    big=True, owner=lab,
                                    **({"max_side": side} if side else {}))

        def failed():
            if fallback and fallback != src:
                self._load_media(lab, fallback, None, tw, th, radius, kind, focus=focus,
                                 big=True, side=side)
            else:
                lab.setText(_("image_failed") if kind == "image" else
                            "▶ " + _("media_" + kind) + "\n" + _("media_click"))
                lab.setWordWrap(True)
        # the original named: once it comes (opened in the viewer), a preview that gave up
        # is asked again instead of staying broken
        self.ctx.images.get(src, show, failed=failed, original=fallback or upgrade, big=big,
                            owner=lab, **({"max_side": side} if side else {}))


def _set(lab, pm):
    try:
        lab.setPixmap(pm)
    except RuntimeError:  # gone meanwhile
        pass


def _play_mark(pm):
    """A round ▶ in the middle of a still frame."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QPolygonF
    out = QPixmap(pm)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    side = max(28, min(out.width(), out.height()) // 4)
    dpr = out.devicePixelRatio() or 1
    cx, cy = out.width() / dpr / 2, out.height() / dpr / 2
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 140))
    p.drawEllipse(QPointF(cx, cy), side / 2, side / 2)
    p.setBrush(QColor(255, 255, 255, 230))
    r = side / 4
    p.drawPolygon(QPolygonF([QPointF(cx - r * 0.7, cy - r), QPointF(cx - r * 0.7, cy + r),
                             QPointF(cx + r, cy)]))
    p.end()
    return out


def _conv_key(spec):
    c = spec.extra.get("conversation")
    return (len(c["members"]), c["unread"], c["last"].id) if c else None


def _hover_text(url):
    """What a link's tooltip says: the web address, also for in-app links that
    were made from one (fedtail:resolve/…)."""
    if url.startswith("http"):
        return url
    if url.startswith("fedtail:resolve/"):
        return unquote(url[len("fedtail:resolve/"):])
    if url.startswith("fedtail:tag/"):
        return "#" + unquote(url[len("fedtail:tag/"):])
    return ""


def _decode_side(lab, tw, th, w, h, cfg):
    """common/lane.py decode_side, on this label's screen."""
    from .images import FEED_SIDE
    try:
        dpr = max(1.0, float(lab.devicePixelRatioF()))
    except (AttributeError, RuntimeError):
        dpr = 1.0
    return decode_side(tw, th, w, h, cfg, dpr, FEED_SIDE)



_HINTS = {}  # (words, style, has a picture, font, stylesheet's id) → width


def _hint_width(b):
    """A button's width as Qt would ask it — once for each kind of button: every card
    has the same few ("Reply", "Like · 3"…), and asking each of them its size hint
    styled them all one by one (0.4 s when a lane opened, 23.10)."""
    key = (b.text(), int(b.toolButtonStyle().value) if hasattr(b, "toolButtonStyle")
           else 0, not b.icon().isNull(), b.font().key(), b.objectName(),
           id(b.style()))
    w = _HINTS.get(key)
    if w is None:
        if len(_HINTS) > 2000:
            _HINTS.clear()
        w = _HINTS[key] = b.sizeHint().width()
    return w


class _ActionsBox(QWidget):
    """The row of buttons under a post. Too narrow for the labels (a narrow window, a
    long word in a translation): the buttons go short — icon or glyph and the count —
    instead of Qt cutting the words; wide again, the labels come back."""

    def __init__(self):
        super().__init__()
        self.short = []   # (button, short text, icon)
        self.full = None  # (text, style) of each button as built
        self.is_short = False

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.full is None:
            # measured once: asking every button its size on every resize of every card
            # froze the window for a second when a lane opened
            self.full = [(b.text(), b.toolButtonStyle()) for b, _t, _i in self.short]
            lay = self.layout()
            self._full_width = sum(_hint_width(b) for b, _t, _i in self.short) + \
                lay.spacing() * (lay.count() + 1) + 40  # the ⋯ button and some air
        go_short = self._full_width > self.width()
        if go_short == self.is_short:
            return
        for (b, text, ic), (full_text, full_style) in zip(self.short, self.full,
                                                          strict=False):
            if go_short:
                b.setText(text)
                b.setToolButtonStyle(
                    Qt.ToolButtonStyle.ToolButtonTextOnly if ic.isNull() else
                    (Qt.ToolButtonStyle.ToolButtonTextBesideIcon if text
                     else Qt.ToolButtonStyle.ToolButtonIconOnly))
                if not ic.isNull():
                    b.setIcon(ic)
            else:
                b.setText(full_text)
                b.setToolButtonStyle(full_style)
        self.is_short = go_short




def account_color(name):
    """A colour of its own for each account, from its name (common/lane.py's)."""
    from ..common.lane import account_color as color
    return color(name)


def _age_days(p, cfg):
    """How many days old a post is, when that's more than feed.old_days; else 0."""
    limit = int(cfg["feed"].get("old_days", 30) or 0)
    if not limit or p.created is None:
        return 0
    from datetime import UTC, datetime
    days = (datetime.now(UTC) - p.created).days
    return days if days > limit else 0

def _dims(m):
    return (m.width, m.height) if m.width and m.height else (None, None)


def _thumb_box(w, h, height=THUMB_H, max_w=THUMB_MAX_W):
    return thumb_box(w, h, height, max_w)


def _focus(m):
    """The author's focus point (x, y in -1…1, y up), (0, 0) if none."""
    if not m.focus:
        return 0.0, 0.0
    x, y = m.focus
    return max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y))


def _crop_rect(sw, sh, w, h, focus):
    """Where a w×h window over a picture scaled to sw×sh goes, centred on the focus."""
    fx, fy = focus
    cx, cy = (fx + 1) / 2 * sw, (1 - fy) / 2 * sh
    x = int(min(max(cx - w / 2, 0), max(sw - w, 0)))
    y = int(min(max(cy - h / 2, 0), max(sh - h, 0)))
    return x, y


def _fit(pm: QPixmap, w, h, radius=0, focus=None):
    """Into w×h: whole (focus None), or filling it, cut around the focus point."""
    if focus is None:
        scaled = pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    else:
        big = pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation)
        x, y = _crop_rect(big.width(), big.height(), w, h, focus)
        scaled = big.copy(x, y, min(w, big.width()), min(h, big.height()))
    if not radius:
        return scaled
    out = QPixmap(scaled.size())
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(out.rect()), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, scaled)
    p.end()
    return out


AVATAR_RADIUS = -1  # shape.avatar_radius of the theme in use (set by the window)


def _round(pm: QPixmap, size, radius=None):
    """An avatar cut to the theme's shape: a circle (-1), a square (0), rounded corners."""
    radius = AVATAR_RADIUS if radius is None else radius
    scaled = pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                       Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    if radius is None or radius < 0:
        path.addEllipse(QRectF(0, 0, size, size))
    else:
        path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    p.setClipPath(path)
    p.drawPixmap((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    p.end()
    return out


def _ids(posts):
    return [p.id for p in posts or ()]


def _parent_key(p):
    if p is None or p == "missing":
        return p
    return (p.id, p.text)
