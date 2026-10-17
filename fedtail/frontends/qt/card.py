"""One post on screen, and the "new below" divider."""

from dataclasses import dataclass, field
from urllib.parse import unquote

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPainterPath, QPixmap
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

from ...core import config, links
from ...core.model import QUOTE_SHOWN, is_bot, quoted, real, snippet, without_quote_fallback
from ...i18n import _, current_language
from .text import clean, display_name, emojify, esc, link

RAIL_W = 20
MAX_DEPTH_INDENT = 8
THUMB_H = 170
THUMB_MAX_W = 380
VIS_ICONS = {
    "public": ("globe", "applications-internet"),
    "unlisted": ("object-unlocked", "unlock"),
    "private": ("object-locked", "lock"),
    "direct": ("mail-message", "mail-unread"),
}
VIS_WORD = {"public": "pub", "unlisted": "unl", "private": "priv", "direct": "dm"}


@dataclass
class CardSpec:
    key: str                 # unique within a view (item id or status id)
    status: dict
    depth: int = 0
    number: int | None = None  # /N inside a thread
    parent: object = None      # parent status, "missing", or None (unknown / not a reply)
    unread: bool = False
    focus: bool = False
    in_thread: bool = False
    extra: dict = field(default_factory=dict)  # my_replies, short_id, separator


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


def _set_prop(w, name, value):
    if w.property(name) != value:
        w.setProperty(name, value)
        w.style().unpolish(w)
        w.style().polish(w)


def _theme_icon(names):
    for n in names:
        ic = QIcon.fromTheme(n)
        if not ic.isNull():
            return ic
    return QIcon()


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

    def _edited_mark(self, st):
        """"· edited", a link to the versions."""
        mark = link("history", st["id"], _("edited_mark"), self.theme.css("muted"))
        lab = self._label("· " + mark, "meta", wrap=False)
        lab.setToolTip(_("edited_tip", when=self.theme.date(st["edited_at"])))
        return lab

    def _card_menu(self, pos):
        if self._menu is not None:
            self._menu.exec(self.card.mapToGlobal(pos))

    # ---- public -----------------------------------------------------------------
    @property
    def status_id(self):
        return self.spec.status["id"]

    @property
    def real_id(self):
        return real(self.spec.status)["id"]

    def update_spec(self, spec):
        old = self.spec
        self.spec = spec
        if (old.status is not spec.status and old.status != spec.status) \
                or _parent_key(old.parent) != _parent_key(spec.parent) \
                or old.number != spec.number or old.focus != spec.focus \
                or old.extra.get("short_id") != spec.extra.get("short_id") \
                or _ids(old.extra.get("my_replies")) != _ids(spec.extra.get("my_replies")) \
                or _conv_key(old) != _conv_key(spec):
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
        lab.linkHovered.connect(lambda url: lab.setToolTip(_hover_text(url)))
        if name:
            lab.setObjectName(name)
        return lab

    def _emoji_label(self, html, emojis, name=None, selectable=False, wrap=True):
        """A label whose :shortcodes: become the server's emoji pictures; the ones not
        downloaded yet are fetched and put in when they come (feed.custom_emoji)."""
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
            self.ctx.images.get(url, lambda _pm: render(), 128)
        return lab

    def _build(self):
        if self.body is not None:
            self.lay.removeWidget(self.body)
            self.body.deleteLater()
        self.body = QWidget()
        v = QVBoxLayout(self.body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(9)
        self.lay.addWidget(self.body)

        spec = self.spec
        wrapper = spec.status
        st = real(wrapper)

        if wrapper.get("reblog"):
            v.addWidget(self._emoji_label(
                _("boosted_by", name=display_name(wrapper["account"])) + " · " +
                _("boost_time", when=self.theme.date(wrapper.get("created_at", ""))),
                wrapper["account"].get("emojis"), "boost"))

        if self.theme.shape["card_header"] == "compact":
            v.addLayout(self._header_compact(st))
        else:
            v.addLayout(self._header_rich(st))

        if not spec.in_thread and st.get("in_reply_to_id") and \
                self.ctx.cfg["feed"]["show_reply_context"]:
            v.addWidget(self._label(self._context_html(st), "ctx"))

        # with its parent from the start: a widget without one becomes a window of its own
        # when shown — the CW switch below shows or hides it before it goes into the
        # layout, and every card under a CW made (and threw away) a native window: tens
        # of milliseconds each, 16 s for a lane of 300 such posts
        content = QWidget(self.body)
        cv = QVBoxLayout(content)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(8)
        quote_mode = self.ctx.cfg["feed"].get("quotes", "card")
        quote = quoted(st) if quote_mode != "off" else None
        tr = getattr(self, "translation", None)
        if tr and self.show_translation:
            src = tr.get("detected_source_language") or "?"
            row = QHBoxLayout()
            row.addWidget(self._label(esc(_("translated_from", lang=src,
                                               provider=tr.get("provider") or "")),
                                      "quoteNote"), 1)
            back = QPushButton(_("show_original"))
            back.setObjectName("tool")
            back.clicked.connect(self._translate)
            row.addWidget(back)
            cv.addLayout(row)
        if st.get("content"):
            html = st["content"]
            if tr and self.show_translation and tr.get("content"):
                html = tr["content"]
            if quote:
                html = without_quote_fallback(html)
            if self.ctx.cfg["ui"]["links_in_app"]:
                html = links.in_app(html, st)  # @mentions, #tags, fediverse links stay inside
            text = self._emoji_label(clean(html, self.theme.css("link")), st.get("emojis"),
                                     "postText", selectable=True)
            cv.addWidget(text)
        media = self._media(st)
        if media:
            cv.addWidget(media)
        if quote:
            cv.addWidget(self._quote(quote, quote_mode))
        elif not media:
            card = self._link_card(st)
            if card:
                cv.addWidget(card)
        if st.get("poll"):
            cv.addWidget(self._poll(st))

        # a server filter that says "warn": folded like a content warning, closed
        warned = [(f.get("filter") or {}).get("title") or "?" for f in st.get("filtered") or []
                  if (f.get("filter") or {}).get("filter_action", "warn") == "warn"
                  and not self.ctx.cfg["ui"]["arts_mode"]]
        if warned:
            self.cw_open = False
        if st.get("spoiler_text") or warned:
            cw_row = QHBoxLayout()
            label = " · ".join(([_("filtered_by", title=", ".join(warned))] if warned else []) +
                               (["⚠ " + st["spoiler_text"]] if st.get("spoiler_text") else []))
            cw_row.addWidget(self._emoji_label(esc(label), st.get("emojis"), "cw"), 1)
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
        v.addWidget(content)
        v.addWidget(self._actions(st))
        answers = spec.extra.get("my_replies") or []
        if answers:
            last = answers[-1]
            more = f" (+{len(answers) - 1})" if len(answers) > 1 else ""
            v.addWidget(self._label(link("thread", last["id"], "↳ " + _(
                "you_replied", when=self.theme.date(last.get("created_at", "")),
                text=esc(snippet(last, 120))) + more, self.theme.css("on_myreply")),
                "myreply"))
        conv = spec.extra.get("conversation")
        if conv and len(conv["members"]) > 1 or conv and conv["last"]["id"] != st["id"]:
            last = conv["last"]
            who = (real(last)["account"].get("display_name") or
                   real(last)["account"].get("username", ""))
            text = _("conv_line", n=len(conv["members"]), new=conv["unread"]) + " · " + \
                _("conv_last", who=esc(who), text=esc(snippet(last, 90)))
            v.addWidget(self._label(link("thread", real(last)["id"], "💬 " + text,
                                         self.theme.css("link")), "ctx"))

    # ---- header -------------------------------------------------------------------
    def _short_id(self, h):
        sid = self.spec.extra.get("short_id")
        if sid:
            lab = QLabel(link("alias", sid, "#" + sid, self.theme.css("muted")))
            lab.setObjectName("shortId")
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
            lab.setCursor(Qt.CursorShape.PointingHandCursor)
            lab.setToolTip(_("short_id_tip"))
            lab.linkActivated.connect(self.ctx.on_link)
            h.addWidget(lab, 0, Qt.AlignmentFlag.AlignTop)

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

    def _header_rich(self, st):
        acc = st["account"]
        h = QHBoxLayout()
        h.setSpacing(12)
        size = int(self.theme.shape["avatar"])
        if self.theme.shape["card_avatars"] and size:
            avatar = ClickLabel()
            avatar.setFixedSize(QSize(size, size))
            avatar.setCursor(Qt.CursorShape.PointingHandCursor)
            avatar.setToolTip("@" + acc["acct"])
            avatar.setAccessibleName(_("a11y_avatar", acct=acc["acct"]))
            avatar.clicked.connect(lambda a=acc["id"]: self.ctx.on_link(f"fedtail:account/{a}"))
            h.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
            self.ctx.images.get(acc.get("avatar_static") or acc.get("avatar"),
                                lambda pm, w=avatar, s=size: w.setPixmap(_round(pm, s)))
        line = QHBoxLayout()
        line.setSpacing(6)
        if self.spec.number:
            num = QLabel(f"/{self.spec.number}")
            num.setObjectName("num")
            line.addWidget(num)
        line.addWidget(self._emoji_label(link("account", acc["id"], display_name(acc),
                                              self.theme.css("text"), bold=True),
                                         acc.get("emojis"), "name", wrap=False))
        bot = f" [{_('bot')}]" if is_bot(acc, self.ctx.cfg["lanes"]["extra_bots"]) else ""
        line.addWidget(self._label(
            f'@{esc(acc["acct"])}{esc(bot)} · '
            + link("thread", st["id"], self.theme.date(st.get("created_at", "")),
                   self.theme.css("muted")),
            "meta", wrap=False))
        vis = st.get("visibility", "public")
        icon = _theme_icon(VIS_ICONS.get(vis, ())) if self.theme.shape["icons"] else QIcon()
        vis_label = QLabel()
        vis_label.setToolTip(_("vis_" + vis))
        if icon.isNull():
            vis_label.setText("· " + VIS_WORD.get(vis, vis))
            vis_label.setObjectName("meta")
        else:
            vis_label.setPixmap(icon.pixmap(14, 14))
        line.addWidget(vis_label)
        if st.get("edited_at"):
            line.addWidget(self._edited_mark(st))
        self._via_mark(line)
        line.addWidget(self._unread_mark(), 0, Qt.AlignmentFlag.AlignVCenter)
        self._pinned_mark(line)
        line.addStretch(1)
        if self.spec.focus and self.spec.in_thread:
            came = QLabel(_("came_from"))
            came.setObjectName("cameFrom")
            line.addWidget(came)
        h.addLayout(line, 1)
        self._short_id(h)
        return h

    def _header_compact(self, st):
        acc = st["account"]
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
            avatar.setToolTip("@" + acc["acct"])
            avatar.clicked.connect(lambda a=acc["id"]: self.ctx.on_link(f"fedtail:account/{a}"))
            h.addWidget(avatar)
            self.ctx.images.get(acc.get("avatar_static") or acc.get("avatar"),
                                lambda pm, w=avatar, s=size: w.setPixmap(_round(pm, s)))
        user, _sep, host = acc["acct"].partition("@")
        h.addWidget(self._label(link("account", acc["id"], "@" + esc(user), self.theme.css("text"),
                                     bold=True), "name", wrap=False))
        vis = st.get("visibility", "public")
        bot = f" [{_('bot')}]" if is_bot(acc, self.ctx.cfg["lanes"]["extra_bots"]) else ""
        meta = " · ".join(x for x in (esc(host) + esc(bot),
                                      link("thread", st["id"],
                                           self.theme.date(st.get("created_at", "")),
                                           self.theme.css("muted")),
                                      VIS_WORD.get(vis, vis)) if x)
        h.addWidget(self._label(meta, "meta", wrap=False))
        if st.get("edited_at"):
            h.addWidget(self._edited_mark(st))
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
        via = self.spec.status.get("_via") if self.spec.status else None
        if via:
            lab = QLabel("→ " + via)
            lab.setObjectName("via")
            lab.setToolTip(_("via_tip", acct=via))
            row.addWidget(lab)

    def _context_html(self, st):
        p = self.spec.parent
        if p is None:
            body = _("ctx_loading")
        elif p == "missing":
            body = _("ctx_missing")
        else:
            body = _("ctx_reply", name="<b>" + display_name(real(p)["account"]) + "</b>",
                     text=esc(snippet(p, 140)))
        return link("thread", st["id"], f"↑ {body}", self.theme.css("muted"))

    # ---- actions ------------------------------------------------------------------
    def _actions(self, st):
        """Flat buttons under a post: icon, text or both (ui.actions)."""
        style = self.ctx.cfg["ui"]["actions"]
        box = QWidget()
        box.setObjectName("actions")
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(2)
        n = lambda x: f" · {x}" if x else ""
        fav = bool(st.get("favourited"))
        boosted = bool(st.get("reblogged"))
        buttons = [("reply", ("mail-reply-sender",), "↩", _("reply"), "", False)]
        buttons.append(("fav", ("rating", "starred-symbolic") if fav else
                        ("rating-unrated", "non-starred-symbolic"), "★" if fav else "☆",
                        _("faved") if fav else _("fav"), n(st.get("favourites_count")), fav))
        if st.get("visibility") in ("public", "unlisted"):
            buttons.append(("boost", ("media-playlist-repeat", "retweet"), "♻",
                            _("boosted") if boosted else _("boost"),
                            n(st.get("reblogs_count")), boosted))
        if not self.spec.in_thread:
            buttons.append(("thread", ("view-list-tree", "format-indent-more"), "⤷",
                            _("thread"), n(st.get("replies_count")), False))
        if self.ctx.cfg["ui"].get("bookmark_button", True):
            marked = bool(st.get("bookmarked"))
            buttons.append(("bookmark", ("bookmark-new", "bookmarks"), "🔖",
                            _("unbookmark") if marked else _("bookmark"), "", marked))
        if self.spec.unread and self.ctx.cfg["read"].get("read_button", False):
            buttons.append(("readone", ("mail-mark-read", "object-select-symbolic"), "✓",
                            _("mark_one_read"), "", False))
        for action, icons, glyph, label, count, active in buttons:
            b = QToolButton()
            b.setAutoRaise(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(label)
            b.setAccessibleName(label + count)
            ic = _theme_icon(icons) if self.theme.shape["icons"] else QIcon()
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
            b.clicked.connect(lambda _c=False, a=action, i=st["id"]:
                              self.ctx.on_link(f"fedtail:{a}/{i}"))
            # a right click on the like or the boost: who did it
            who = {"fav": ("favourited_by", "favourites_count"),
                   "boost": ("reblogged_by", "reblogs_count")}.get(action)
            if who and st.get(who[1]) and self.ctx.supports(who[0]):
                b.setToolTip(label + "\n" + _("who_right_click"))
                b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                b.customContextMenuRequested.connect(
                    lambda _p, k=who[0], i=st["id"]: self.ctx.on_link(f"fedtail:{k}/{i}"))
            h.addWidget(b)
        h.addStretch(1)
        h.addWidget(self._more_button(st))
        return box

    def _more_button(self, st):
        b = QToolButton()
        b.setAutoRaise(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip(_("more"))
        b.setAccessibleName(_("more"))
        ic = _theme_icon(("overflow-menu", "application-menu", "view-more-symbolic")) \
            if self.theme.shape["icons"] else QIcon()
        if ic.isNull():
            b.setText("⋯")
        else:
            b.setIcon(ic)
        menu = QMenu(b)
        url = st.get("url") or st.get("uri") or ""
        from .opener import open_link
        menu.addAction(_("open_browser"), lambda u=url: open_link(u))
        menu.addAction(_("copy_link"), lambda u=url: QGuiApplication.clipboard().setText(u))
        sid = self.spec.extra.get("short_id")
        if sid:
            menu.addAction(_("copy_id", id="#" + sid),
                           lambda s=sid: QGuiApplication.clipboard().setText("#" + s))
        author = real(st)["account"]
        if self.ctx.fill_list_menu is not None and author["id"] != self.ctx.me_id:
            lists = menu.addMenu(_("add_to_list"))
            lists.aboutToShow.connect(lambda m=lists, a=author: self.ctx.fill_list_menu(m, a))
        approval = (real(st).get("quote_approval") or {}).get("current_user")
        if self.ctx.cfg["post"].get("quote_action", True) and approval in ("automatic", "manual"):
            quote_url = f"fedtail:quote/{real(st)['id']}"
            menu.addAction(_("quote") if approval == "automatic" else _("quote_ask"),
                           lambda u=quote_url: self.ctx.on_link(u))
        lang = (real(st).get("language") or "").split("-")[0]
        if self.ctx.translate and lang and lang != current_language() and real(st).get("content"):
            menu.addAction(_("translate"), self._translate)
        menu.addAction(_("unbookmark") if real(st).get("bookmarked") else _("bookmark"),
                       lambda i=st["id"]: self.ctx.on_link(f"fedtail:bookmark/{i}"))
        if self.spec.unread:  # by hand, whatever read.mark_read says
            menu.addAction(_("mark_one_read"),
                           lambda i=st["id"]: self.ctx.on_link(f"fedtail:readone/{i}"))
            menu.addAction(_("mark_read_upto"),
                           lambda i=st["id"]: self.ctx.on_link(f"fedtail:readupto/{i}"))
        # who liked, who boosted; quotes of my post; my post out of someone's quote
        s = real(st)
        sup = self.ctx.supports
        for kind, count in (("favourited_by", "favourites_count"),
                            ("reblogged_by", "reblogs_count")):
            if sup(kind) and s.get(count):
                menu.addAction(_("who_" + kind + "_n", n=s[count]),
                               lambda i=st["id"], k=kind: self.ctx.on_link(f"fedtail:{k}/{i}"))
        if s["account"]["id"] == self.ctx.me_id and sup("quotes") and \
                s.get("visibility") in ("public", "unlisted"):
            menu.addAction(_("quotes_of"), lambda i=st["id"]:
                           self.ctx.on_link(f"fedtail:quotes/{i}"))
        quoted = (s.get("quote") or {}).get("quoted_status") or {}
        if (quoted.get("account") or {}).get("id") == self.ctx.me_id and sup("quotes") and \
                s["account"]["id"] != self.ctx.me_id:
            menu.addAction(_("revoke_quote"), lambda i=st["id"]:
                           self.ctx.on_link(f"fedtail:revokequote/{i}"))
        if sup("mute_thread") and s.get("muted") is not None:  # threads I'm in
            muted = bool(s.get("muted"))
            menu.addAction(_("unmute_thread" if muted else "mute_thread"),
                           lambda i=st["id"], m=muted:
                           self.ctx.on_link(f"fedtail:{'unmute' if m else 'mute'}thread/{i}"))
        if self.ctx.subscribed is not None:
            menu.addSeparator()
            on = self.ctx.subscribed(st)
            menu.addAction(_("unsub_thread" if on else "sub_thread"),
                           lambda i=st["id"], on=on:
                           self.ctx.on_link(f"fedtail:{'unsub' if on else 'sub'}/{i}"))
        if author["id"] != self.ctx.me_id:
            menu.addSeparator()
            menu.addAction(_("mute_acct", acct=author["acct"]),
                           lambda i=st["id"]: self.ctx.on_link(f"fedtail:mute/{i}"))
            menu.addAction(_("block_acct", acct=author["acct"]),
                           lambda i=st["id"]: self.ctx.on_link(f"fedtail:block/{i}"))
            domain = author["acct"].partition("@")[2]
            if domain:
                menu.addAction(_("block_domain", domain=domain),
                               lambda i=st["id"]: self.ctx.on_link(f"fedtail:blockdomain/{i}"))
            if not self.ctx.cfg["ui"]["arts_mode"]:
                menu.addAction(_("report"),
                               lambda i=st["id"]: self.ctx.on_link(f"fedtail:report/{i}"))
        if st["account"]["id"] == self.ctx.me_id:
            menu.addSeparator()
            menu.addAction(_("edit"), lambda i=st["id"]: self.ctx.on_link(f"fedtail:edit/{i}"))
            if real(st).get("visibility") in ("public", "unlisted"):
                pinned = bool(real(st).get("pinned"))
                pin_url = f"fedtail:{'unpin' if pinned else 'pin'}/{real(st)['id']}"
                menu.addAction(_("unpin") if pinned else _("pin"),
                               lambda u=pin_url: self.ctx.on_link(u))
            menu.addAction(_("delete"), lambda i=st["id"]: self.ctx.on_link(f"fedtail:delete/{i}"))
        b.setMenu(menu)
        self._menu = menu  # also shown on a right click on the card (see __init__)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        return b

    # ---- media --------------------------------------------------------------------
    # ---- polls --------------------------------------------------------------------
    def _poll(self, st):
        """Options to pick and a Vote button; or the results — after voting, when
        it's over, on my own post, or when asked."""
        poll = st["poll"]
        box = QFrame()
        box.setObjectName("poll")
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 2, 0, 2)
        v.setSpacing(6)
        mine = st["account"]["id"] == self.ctx.me_id
        results = poll.get("voted") or poll.get("expired") or mine or \
            getattr(self, "poll_results", False) or self.ctx.vote is None
        options = poll.get("options") or []
        if results:
            total = (poll.get("voters_count") if poll.get("multiple") else None) or \
                poll.get("votes_count") or 0
            own = set(poll.get("own_votes") or [])
            top = max((o.get("votes_count") or 0 for o in options), default=0)
            for i, o in enumerate(options):
                n = o.get("votes_count")
                pct = round(100 * (n or 0) / total) if total and n is not None else 0
                row = QHBoxLayout()
                title = esc(o.get("title", ""))
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
            group.setExclusive(not poll.get("multiple"))
            for i, o in enumerate(options):
                b = (QCheckBox if poll.get("multiple") else QRadioButton)(o.get("title", ""))
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
                self.ctx.vote(st, picked())
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
        v.addWidget(self._label(self._poll_footer(st), "meta"))
        return box

    def _poll_footer(self, st):
        poll = st["poll"]
        voters = poll.get("voters_count")
        n = voters if voters is not None else poll.get("votes_count") or 0
        parts = [_("poll_people" if voters is not None else "poll_votes", n=n)]
        if poll.get("expired"):
            parts.append(_("poll_closed"))
        elif poll.get("expires_at"):
            parts.append(_("poll_until", when=self.theme.date(poll["expires_at"])))
        if poll.get("multiple"):
            parts.append(_("poll_multiple"))
        if self.ctx.refresh_poll is not None and not poll.get("expired"):
            parts.append(link("poll", st["id"], _("poll_refresh")))
        return " · ".join(parts)

    def _media(self, st):
        atts = [_true_kind(m) for m in st.get("media_attachments") or []]
        if not atts:
            return None
        box = QWidget()
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        visual = [m for m in atts if m.get("type") in ("image", "gifv", "video")
                  and (m.get("preview_url") or m.get("url"))]
        images = [x for x in visual if x.get("type") == "image"]
        single = len(visual) == 1
        big_h = self.ctx.cfg["ui"]["image_height"]
        big_w = max(200, (self.ctx.cfg["ui"]["max_width"] or 900) - 60)
        pos = 0
        # marked sensitive by the author, with no warning text to hide behind: covered
        # until clicked (feed.sensitive_media); under a CW the whole post is folded anyway
        covered = bool(st.get("sensitive")) and not st.get("spoiler_text") and \
            not getattr(self, "media_revealed", False) and \
            config.sensitive_media(self.ctx.cfg) == "hide"
        for m in atts:
            full = m.get("url") or m.get("remote_url") or ""
            if m in visual and covered:
                lab = ClickLabel("⚠ " + _("sensitive_media") + "\n" + _("sensitive_click"))
                lab.setObjectName("media")
                lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lab.setWordWrap(True)
                lab.setCursor(Qt.CursorShape.PointingHandCursor)
                w, h = _dims(m)
                lab.setFixedSize(*_thumb_box(w, h, *((big_h, big_w) if single else (150, 230))))
                lab.setToolTip(m.get("description") or "")
                lab.clicked.connect(self._reveal_media)
                grid.addWidget(lab, pos // 3, pos % 3)
                pos += 1
                continue
            if m in visual:
                cell = (pos // 3, pos % 3)
                pos += 1
                lab = ClickLabel(_("image_loading"))
                lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lab.setToolTip(m.get("description") or "")
                lab.setAccessibleName(_("media_" + m["type"]))
                lab.setAccessibleDescription(m.get("description") or _("a11y_no_alt"))
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
                if m.get("type") == "image":
                    idx = images.index(m)
                    lab.clicked.connect(lambda i=idx: self.ctx.show_images(images, i))
                    # the preview first, at once; a single big picture then gets the full
                    # file, which may take a while (a big photo, a slow server)
                    src = m.get("preview_url") or full
                    upgrade = full if single and full and full != src else None
                else:  # gifv / video: still frame here, playback in the browser
                    upgrade = None
                    lab.setToolTip(_("media_" + m["type"]) + " ▶ " + (m.get("description") or ""))
                    lab.clicked.connect(lambda u=full: self.ctx.open_url(u))
                    src = m.get("preview_url")
                if src:
                    self._load_media(lab, src, full if src != full else None, tw, th, radius,
                                     kind=m["type"], upgrade=upgrade, focus=focus)
                elif m["type"] != "image":  # a video without a still frame: say what it is
                    lab.setText("▶ " + _("media_" + m["type"]) + "\n" + _("media_click"))
                grid.addWidget(lab, *cell)
            else:
                kind = _("media_" + (m.get("type") or "unknown"))
                grid.addWidget(self._label(f'<a href="{esc(full)}">[{kind}]</a>'),
                               pos // 3, pos % 3)
                pos += 1
        if self.ctx.cfg["ui"].get("alt_text") == "caption" and not covered:
            row = (pos + 2) // 3
            for i, m in enumerate(visual):
                desc = (m.get("description") or "").strip()
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
        state, q, qid = quote
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
                who = " " + _("quote_by", name=display_name(q["account"])) + ": " + \
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
        acc = q["account"]
        v.addWidget(self._emoji_label(
            f"<b>{display_name(acc)}</b> @{esc(acc.get('acct', ''))} · "
            + esc(self.theme.date(q.get("created_at", ""))), acc.get("emojis"), "quoteHead",
            wrap=False))
        if q.get("spoiler_text"):
            v.addWidget(self._label("⚠ " + esc(q["spoiler_text"]), "cw"))
        else:
            html = q.get("content") or ""
            if self.ctx.cfg["ui"]["links_in_app"]:
                html = links.in_app(html, q)
            v.addWidget(self._emoji_label(clean(html, self.theme.css("link")),
                                          q.get("emojis"), "quoteText", selectable=True))
            n = len(q.get("media_attachments") or [])
            if n:
                v.addWidget(self._label("🖼 " + _("quote_media", n=n), "quoteHead"))
        return box

    def _link_card(self, st):
        """The page a post links to, as the server saw it: title, a line or two of
        description, the site, a picture (feed.link_cards)."""
        mode = self.ctx.cfg["feed"].get("link_cards", "full")
        c = st.get("card") or {}
        url = c.get("url") or ""
        if mode == "off" or not url or not (c.get("title") or c.get("image")):
            return None
        box = ClickFrame()
        box.setObjectName("linkCard")
        box.setCursor(Qt.CursorShape.PointingHandCursor)
        box.setToolTip(_hover_text(url))
        box.clicked.connect(lambda: self.ctx.on_link(url))
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 10, 0)
        h.setSpacing(12)
        side = 96
        if mode == "full" and c.get("image"):
            pic = QLabel()
            pic.setObjectName("linkCardImage")
            pic.setFixedSize(side, side)
            pic.setToolTip(c.get("image_description") or "")

            def got(pm, lab=pic):
                _set(lab, _fit(pm, side, side, 0))
            self.ctx.images.get(c["image"], got)
            h.addWidget(pic, 0, Qt.AlignmentFlag.AlignTop)
        else:
            h.setContentsMargins(10, 0, 10, 0)
        col = QVBoxLayout()
        col.setContentsMargins(0, 8, 0, 8)
        col.setSpacing(2)
        site = c.get("provider_name") or _host(url)
        col.addWidget(self._label(esc(site), "linkCardSite", wrap=False))
        if c.get("title"):
            col.addWidget(self._label("<b>" + esc(c["title"][:200]) + "</b>", "linkCardTitle"))
        desc = (c.get("description") or "").strip()
        if desc and mode == "full":
            col.addWidget(self._label(esc(desc[:220] + ("…" if len(desc) > 220 else "")),
                                      "linkCardText"))
        col.addStretch(1)
        h.addLayout(col, 1)
        return box

    def _translate(self):
        st = real(self.spec.status)

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
            self.ctx.translate(st, done)

    def _reveal_media(self):
        self.media_revealed = True
        self._build()

    def _media_menu(self, lab, m, pos):
        menu = QMenu(lab)
        url = m.get("url") or m.get("remote_url") or ""
        if self.ctx.save_image:
            menu.addAction(_("save_image"), lambda: self.ctx.save_image(m))
        menu.addAction(_("open_browser"), lambda: self.ctx.open_url(url))
        menu.addAction(_("copy_link"), lambda: QGuiApplication.clipboard().setText(url))
        menu.exec(lab.mapToGlobal(pos))

    def _load_media(self, lab, src, fallback, tw, th, radius, kind="image", upgrade=None,
                    focus=None, big=False):
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
                                    big=True)

        def failed():
            if fallback and fallback != src:
                self._load_media(lab, fallback, None, tw, th, radius, kind, focus=focus,
                                 big=True)
            else:
                lab.setText(_("image_failed") if kind == "image" else
                            "▶ " + _("media_" + kind) + "\n" + _("media_click"))
                lab.setWordWrap(True)
        # the original named: once it comes (opened in the viewer), a preview that gave up
        # is asked again instead of staying broken
        self.ctx.images.get(src, show, failed=failed, original=fallback or upgrade, big=big)


def _set(lab, pm):
    try:
        lab.setPixmap(pm)
    except RuntimeError:  # gone meanwhile
        pass


VIDEO_EXT = (".mp4", ".webm", ".mov", ".m4v", ".mkv", ".ogv")


def _true_kind(m):
    """Servers sometimes call a video an "image" (a remote one they couldn't sort);
    the file's name knows better. A copy with the right "type"."""
    url = (m.get("url") or m.get("remote_url") or "").lower().split("?")[0]
    if m.get("type") in ("image", "unknown", None) and url.endswith(VIDEO_EXT):
        return dict(m, type="video")
    return m


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
    return (len(c["members"]), c["unread"], c["last"]["id"]) if c else None


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


def _dims(m):
    meta = m.get("meta") or {}
    for k in ("original", "small"):
        d = meta.get(k) or {}
        if d.get("width") and d.get("height"):
            return d["width"], d["height"]
    return None, None


def _thumb_box(w, h, height=THUMB_H, max_w=THUMB_MAX_W):
    if not (w and h):
        return height, height
    tw = int(height * w / h)
    if tw <= max_w:
        return max(tw, 24), height
    return max_w, max(24, int(max_w * h / w))


def _focus(m):
    """The author's focus point (Mastodon: x, y in -1…1, y up), (0, 0) if none."""
    f = (m.get("meta") or {}).get("focus") or {}
    try:
        x, y = float(f.get("x", 0)), float(f.get("y", 0))
    except (TypeError, ValueError):
        return 0.0, 0.0
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


def _round(pm: QPixmap, size):
    """Avatar cut to a circle."""
    scaled = pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                       Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addEllipse(QRectF(0, 0, size, size))
    p.setClipPath(path)
    p.drawPixmap((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    p.end()
    return out


def _ids(statuses):
    return [s["id"] for s in statuses or ()]


def _parent_key(p):
    if p is None or p == "missing":
        return p
    return (p.get("id"), p.get("content"))
