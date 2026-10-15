"""One post on screen."""

from dataclasses import dataclass, field

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.model import is_bot, real, snippet
from ...i18n import _, months
from .text import clean, display_name, esc, link, when

VIS_ICON = {"public": "🌐", "unlisted": "🔓", "private": "🔒", "direct": "✉"}
INDENT = 18
MAX_DEPTH_INDENT = 10
THUMB_H = 170
THUMB_MAX_W = 380


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
    extra: dict = field(default_factory=dict)


class ClickLabel(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)


def _set_prop(w, name, value):
    if w.property(name) != value:
        w.setProperty(name, value)
        w.style().unpolish(w)
        w.style().polish(w)


class PostRow(QWidget):
    """Indentation + rail + the card itself."""

    def __init__(self, spec, ctx):
        super().__init__()
        self.ctx = ctx
        self.spec = spec
        self.cw_open = ctx.cfg["ui"]["expand_cw"]
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        depth = min(spec.depth, MAX_DEPTH_INDENT)
        if depth:
            row.addSpacing(INDENT * depth)
            rail = QFrame()
            rail.setObjectName("rail")
            rail.setFixedWidth(2)
            row.addWidget(rail)
            row.addSpacing(6)
        self.card = QFrame()
        self.card.setObjectName("card")
        self.card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addWidget(self.card)
        self.lay = QVBoxLayout(self.card)
        self.lay.setContentsMargins(10, 8, 10, 8)
        self.lay.setSpacing(4)
        self.body = None
        self._build()
        self._flags()

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
                or old.number != spec.number:
            self._build()
        self._flags()

    def set_unread(self, unread):
        self.spec.unread = unread
        self._flags()

    # ---- building ---------------------------------------------------------------
    def _flags(self):
        _set_prop(self.card, "unread", "true" if self.spec.unread else "false")
        _set_prop(self.card, "focus", "true" if self.spec.focus else "false")

    def _label(self, html="", name=None, selectable=False):
        lab = QLabel(html)
        lab.setTextFormat(Qt.TextFormat.RichText)
        lab.setWordWrap(True)
        lab.setOpenExternalLinks(False)
        flags = Qt.TextInteractionFlag.LinksAccessibleByMouse
        if selectable:
            flags |= Qt.TextInteractionFlag.TextSelectableByMouse
        lab.setTextInteractionFlags(flags)
        lab.linkActivated.connect(self.ctx.on_link)
        if name:
            lab.setObjectName(name)
        return lab

    def _build(self):
        if self.body is not None:
            self.lay.removeWidget(self.body)
            self.body.deleteLater()
        self.body = QWidget()
        v = QVBoxLayout(self.body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        self.lay.addWidget(self.body)

        spec, ctx = self.spec, self.ctx
        wrapper = spec.status
        st = real(wrapper)
        acc = st["account"]

        if wrapper.get("reblog"):
            boosted = when(wrapper.get("created_at", ""), months())
            v.addWidget(self._label(_("boosted_by", name=display_name(wrapper["account"])) +
                                    " · " + _("boost_time", when=boosted), "boost"))

        head = QHBoxLayout()
        head.setSpacing(8)
        avatar = ClickLabel()
        avatar.setFixedSize(QSize(32, 32))
        avatar.setCursor(Qt.CursorShape.PointingHandCursor)
        avatar.clicked.connect(lambda a=acc["id"]: ctx.on_link(f"fedtail:account/{a}"))
        head.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
        ctx.images.get(acc.get("avatar_static") or acc.get("avatar"),
                       lambda pm, w=avatar: w.setPixmap(_fit(pm, 32, 32)))
        bot = f' <span style="color:{ctx.theme.muted}">[{_("bot")}]</span>' \
            if is_bot(acc, ctx.cfg["lanes"]["extra_bots"]) else ""
        vis = st.get("visibility", "public")
        num = f' <b>/{spec.number}</b>' if spec.number else ""
        title = (f'{link("account", acc["id"], "<b>" + display_name(acc) + "</b>")}'
                 f' <span style="color:{ctx.theme.muted}">@{esc(acc["acct"])}</span>{bot}'
                 f'<br><span style="color:{ctx.theme.muted}">'
                 f'{link("thread", st["id"], when(st.get("created_at", ""), months()))}'
                 f' · <span title="{esc(_("vis_" + vis))}">{VIS_ICON.get(vis, "?")}</span>'
                 f'{num}</span>')
        head.addWidget(self._label(title), 1)
        v.addLayout(head)

        if not spec.in_thread and st.get("in_reply_to_id") and \
                ctx.cfg["feed"]["show_reply_context"]:
            v.addWidget(self._label(self._context_html(st), "ctx"))

        content = QWidget()
        cv = QVBoxLayout(content)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(6)
        if st.get("content"):
            cv.addWidget(self._label(clean(st["content"]), selectable=True))
        media = self._media(st)
        if media:
            cv.addWidget(media)

        if st.get("spoiler_text"):
            cw_row = QHBoxLayout()
            cw_row.addWidget(self._label("⚠ " + esc(st["spoiler_text"]), "cw"), 1)
            btn = QPushButton()
            btn.setFlat(True)
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
        v.addWidget(self._label(self._actions_html(st), "actions"))

    def _context_html(self, st):
        p = self.spec.parent
        if p is None:
            body = _("ctx_loading")
        elif p == "missing":
            body = _("ctx_missing")
        else:
            body = _("ctx_reply", name="<b>" + display_name(real(p)["account"]) + "</b>",
                     text=esc(snippet(p, 140)))
        return link("thread", st["id"], f"↪ {body}")

    def _actions_html(self, st):
        n = lambda x: f" {x}" if x else ""
        acts = [link("reply", st["id"], _("reply"))]
        acts.append(link("fav", st["id"],
                         ("★" if st.get("favourited") else "☆") + n(st.get("favourites_count"))))
        if st.get("visibility") in ("public", "unlisted"):
            acts.append(link("boost", st["id"],
                             ("♻✓" if st.get("reblogged") else "♻") +
                             n(st.get("reblogs_count"))))
        if not self.spec.in_thread:
            acts.append(link("thread", st["id"], _("thread") + n(st.get("replies_count"))))
        acts.append(link("open", st["id"], "↗"))
        if st["account"]["id"] == self.ctx.me_id:
            acts.append(link("delete", st["id"], _("delete")))
        return " &nbsp;·&nbsp; ".join(acts)

    def _media(self, st):
        atts = st.get("media_attachments") or []
        if not atts:
            return None
        box = QWidget()
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        single = len(atts) == 1
        for i, m in enumerate(atts):
            cell = (i // 3, i % 3)
            full = m.get("url") or m.get("remote_url") or ""
            if m.get("type") in ("image", "gifv") and m.get("preview_url"):
                lab = ClickLabel("🖼")
                lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lab.setToolTip(m.get("description") or "")
                lab.setCursor(Qt.CursorShape.PointingHandCursor)
                # reserve the final size now, so loading never shifts the text below
                small = (m.get("meta") or {}).get("small") or {}
                tw, th = _thumb_box(small.get("width"), small.get("height"),
                                    *((THUMB_H, THUMB_MAX_W) if single else (140, 210)))
                lab.setFixedSize(tw, th)
                lab.clicked.connect(lambda u=full: self.ctx.open_url(u))
                self.ctx.images.get(m["preview_url"],
                                    lambda pm, w=lab, tw=tw, th=th: w.setPixmap(_fit(pm, tw, th)))
                grid.addWidget(lab, *cell)
            else:
                kind = _("media_" + (m.get("type") or "unknown"))
                grid.addWidget(self._label(f'<a href="{esc(full)}">[{kind}]</a>'), *cell)
        grid.setColumnStretch(3, 1)
        return box


def _thumb_box(w, h, height=THUMB_H, max_w=THUMB_MAX_W):
    if not (w and h):
        return height, height
    tw = int(height * w / h)
    if tw <= max_w:
        return max(tw, 24), height
    return max_w, max(24, int(max_w * h / w))


def _fit(pm: QPixmap, w, h):
    return pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)


def _parent_key(p):
    if p is None or p == "missing":
        return p
    return (p.get("id"), p.get("content"))
