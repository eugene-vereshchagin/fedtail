"""The roster window of ``ui.layout = "split"`` (docs/LAYOUTS.md): a narrow window of its
own, as in QIP, Psi+ or the Mail.ru Agent — who I am on top, a search line, then the
lanes in groups, each with its unread count, a line of its newest post and the face of
its author. A double click (or Enter) opens the lane in the main window, which in this layout is the
messages window: no sidebar, the lanes and threads as its tabs.

It reads View.roster() only (the model), and refreshes a moment after anything new or
read — the same events that update the sidebar's badges."""

import logging

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...i18n import _
from ..common import roster as rules
from ..common.roster import LOOK, row_key  # noqa: F401  (Qt's names)
from .text import display_name, esc

log = logging.getLogger(__name__)

AVATAR = 40      # mine, in the header
FACE = 28        # the newest post's author, beside an item
REFRESH_MS = 300  # coalesce bursts of events into one rebuild
# how the roster looks (the ⚙ menu, kept in state): a compact one is a line an item —
# no status line, no face; the header, the search and the bottom row can go
class RosterRow(QWidget):
    """One item: icon, the lane's name (bold when there is something new), the count,
    and under it the newest post as a status line; its author's face on the right."""

    def __init__(self, roster, item):
        super().__init__()
        self.roster, self.key = roster, row_key(item)
        win = roster.win
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(8)
        icon = QLabel()
        icon.setFixedWidth(18)
        from .. import iconpack
        from . import icons as pictures
        own = {"person": "status", "talk": "talk", "thread": "thread"}.get(item.kind)
        ic = pictures.icon(own, win.theme) if own else QIcon()  # a flower for a person
        if ic.isNull():  # else the lane's picture
            kind = {"thread": "subs", "talk": "direct", "person": "direct"}.get(item.kind,
                                                             item.key.split(":")[0])
            ic = pictures.icon(iconpack.lane_picture(kind), win.theme, 18)
        if not ic.isNull():
            icon.setPixmap(ic.pixmap(16 if own else 18, 16 if own else 18))
        h.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        self.icon, self.icon_pm = icon, icon.pixmap() if not icon.pixmap().isNull() else None
        col = QVBoxLayout()
        col.setSpacing(0)
        top = QHBoxLayout()
        top.setSpacing(6)
        self.name = QLabel()
        self.name.setObjectName("rosterName")
        # always rich text: an escaped title without tags ("&quot;") was taken for plain
        self.name.setTextFormat(Qt.TextFormat.RichText)
        top.addWidget(self.name, 1)
        self.badge = QLabel()
        self.badge.setObjectName("badge")
        self.badge.setProperty("kind", "normal")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setMinimumWidth(22)
        top.addWidget(self.badge)
        col.addLayout(top)
        # shape.roster_rows = "faces" (the Agent, Psi): a status under the name — who it
        # is, or how much is new — then the line; the face big, on the left
        self.status = QLabel()
        self.status.setObjectName("rosterStatus")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.hide()
        col.addWidget(self.status)
        self.line = QLabel()
        self.line.setObjectName("rosterLine")
        self.line.setTextFormat(Qt.TextFormat.PlainText)
        col.addWidget(self.line)
        h.addLayout(col, 1)
        self.face = QLabel()
        self.face.setFixedSize(FACE, FACE)
        h.addWidget(self.face, 0, Qt.AlignmentFlag.AlignTop)
        self._face_url = None
        from .dock import HoverCard  # a person: their card on hover, as QIP had it
        HoverCard(win, self, lambda: self.item.who)
        self.compact = roster.look["compact"]
        self.faces = win.theme.shape.get("roster_rows") == "faces" and not self.compact
        if self.faces:
            size = int(win.theme.shape.get("roster_face", 40))
            h.removeWidget(self.face)
            self.face.setFixedSize(size, size)
            self.face.setObjectName("faceFrame")
            h.insertWidget(0, self.face, 0, Qt.AlignmentFlag.AlignTop)
            h.setContentsMargins(4, 3, 8, 3)
            self.icon.hide()  # its picture is in the face's frame when nobody's face is
        if self.compact:
            h.setContentsMargins(6, 1, 6, 1)
            self.face.hide()
        self.update_item(item)

    def update_item(self, item):
        self.item = item
        new = item.unread > 0
        self.name.setText(f"<b>{esc(item.title)}</b>" if new else esc(item.title))
        self.name.setProperty("unread", "true" if new else "false")
        self.name.style().unpolish(self.name)
        self.name.style().polish(self.name)
        self.badge.setText(str(item.unread) if item.unread < 1000 else "999+")
        self.badge.setVisible(new)
        line, tip, status = rules.lines(item, self.faces)
        self.line.setText(line)
        self.line.setToolTip(tip)
        self.line.setVisible(bool(line) and not self.compact)
        if self.faces:
            self.status.setText(status)
            self.status.setVisible(bool(status))
        url = rules.face_url(item)
        if self.faces and not url:  # a big frame with nobody in it: the lane's own picture
            self.face.setVisible(not self.compact and self.icon_pm is not None)
            if self.icon_pm is not None and self._face_url != "":
                self._face_url = ""
                self.face.setPixmap(self.icon_pm.scaled(
                    self.face.width() // 2, self.face.height() // 2,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
                self.face.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return self._tip(item, new)
        if self.faces:
            self.face.setVisible(not self.compact)
        if url != self._face_url and not self.compact:
            self._face_url = url
            self.face.clear()
            if url:
                from .card import _round
                self.roster.win.images.get(
                    url, lambda pm, w=self.face: _alive(w) and w.setPixmap(
                        _round(pm, w.width())))
        self._tip(item, new)

    def _tip(self, item, _new=None):
        self.setToolTip(rules.tip(item))  # a person has the card instead of a tooltip

    def matches(self, text):
        return rules.matches(self.item, self.line.text(), text)


def pop_menu(menu, btn, above=True):
    from .window import pop_menu as pop  # the window's (it pops its own menus too)
    pop(menu, btn, above)


def _alive(w):
    try:
        w.objectName()
        return True
    except RuntimeError:  # gone with a rebuild
        return False


class RosterHeader(QWidget):
    """A group's title: "▾ Ленты (2/5)" — lanes with something new / lanes; a click
    folds it."""

    def __init__(self, roster, name):
        super().__init__()
        self.roster, self.group = roster, name
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(_("group_fold_tip"))
        h = QHBoxLayout(self)
        h.setContentsMargins(6, 6, 6, 2)
        self.label = QLabel()
        self.label.setObjectName("rosterGroup")
        h.addWidget(self.label, 1)

    def show_counts(self, group, folded):
        """The title with how many: "(15)" — nothing new; "(2/15)" — something new in 2,
        the 2 in the theme's colour of the new."""
        lit = sum(1 for i in group.items if i.unread)
        title = _("lists_header") if group.name == "lists" else _("grp_" + group.name)
        from .card import _fill_html
        theme = self.roster.win.theme
        key = "roster_group" if lit else "roster_group_quiet"
        word = theme.words.get(key, "{arrow} {title} ({lit}/{n})" if lit
                               else "{arrow} {title} ({n})")
        lit_html = f'<span style="color:{theme.css("dot")}">{lit}</span>'
        self.label.setText(_fill_html(word, arrow="▸" if folded else "▾", title=esc(title),
                                      lit=lit_html, n=str(len(group.items))))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.roster.toggle(self.group)
            e.accept()


class RosterWindow(QWidget):
    """The roster: a window of its own beside the messages window."""

    def __init__(self, win):
        super().__init__(None, Qt.WindowType.Window)
        self.win = win
        self.setObjectName("roster")
        # a QWidget of our own: without this its stylesheet background (the theme's
        # gradient) is never painted
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle(_("roster_title"))
        self.setWindowIcon(win.windowIcon())
        self.resize(280, 640)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)
        # who I am: face, name, @address, and what is new in Activity
        head = QWidget()
        head_row = QHBoxLayout(head)
        head_row.setContentsMargins(0, 0, 0, 0)
        self.avatar = QLabel()
        self.avatar.setFixedSize(AVATAR, AVATAR)
        head_row.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignTop)
        who = QVBoxLayout()
        who.setSpacing(0)
        self.me_name = QLabel()
        self.me_name.setObjectName("rosterMe")
        who.addWidget(self.me_name)
        self.me_handle = QLabel()
        self.me_handle.setObjectName("muted")
        who.addWidget(self.me_handle)
        self.news = QLabel()
        self.news.setObjectName("rosterNews")
        self.news.linkActivated.connect(lambda _u: self.open("activity"))
        who.addWidget(self.news)
        head_row.addLayout(who, 1)
        v.addWidget(head)
        self.search = QLineEdit()
        self.search.setPlaceholderText(_("roster_search"))
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip(_("roster_search_tip"))
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._search_enter)
        v.addWidget(self.search)
        self.list = QListWidget()
        self.list.setObjectName("rosterList")
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # a double click opens, as in every messenger (Enter too); one click selects
        self.list.itemDoubleClicked.connect(self._activated)
        self.list.installEventFilter(self)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        v.addWidget(self.list, 1)
        # at the bottom, as in every messenger: the menu, who I am (the accounts), and
        # how the roster looks
        self.bottom = QWidget()
        bottom = QHBoxLayout(self.bottom)
        bottom.setContentsMargins(0, 0, 0, 0)
        self.menu_btn = QPushButton(_("menu"))
        self.menu_btn.setObjectName("tool")
        self.menu_btn.clicked.connect(lambda: self.win._pop_app_menu(self.menu_btn, True))
        bottom.addWidget(self.menu_btn)
        self.account_btn = QPushButton()
        self.account_btn.setObjectName("tool")
        self.account_btn.setToolTip(_("accounts"))
        self.account_btn.clicked.connect(self._pop_accounts)
        bottom.addWidget(self.account_btn, 1)
        self.look_btn = QPushButton("⚙")
        self.look_btn.setObjectName("tool")
        self.look_btn.setToolTip(_("roster_look"))
        self.look_btn.clicked.connect(lambda: pop_menu(self._look_menu(), self.look_btn, True))
        bottom.addWidget(self.look_btn)
        v.addWidget(self.bottom)
        self.head_box = head
        self.rows, self.heads = {}, {}
        self._queue, self._tall = [], {}
        self.folded = rules.folded(win.ctx.view)
        self.look = rules.look(win.ctx.view)
        self._shape = None
        self._mutuals_asked = False
        self._timer = QTimer(self, singleShot=True, interval=REFRESH_MS)
        self._timer.timeout.connect(self.refresh_in_background)
        self._computing = self._again = False
        self._restore_place()
        self._apply_look()
        self.dress()

    # ---- contents ------------------------------------------------------------------
    def refresh_soon(self):
        self._timer.start()

    def refresh_in_background(self):
        """The roster worked out in the core's threads (it reads every lane: a third of
        a second on a big store), put on screen when done; one at a time."""
        view = self.win.ctx.view
        if not self.win.core.me:
            return self.refresh()
        if self._computing:
            self._again = True
            return
        self._computing = True

        def done(groups):
            self._computing = False
            self._show(groups)
            if self._again:
                self._again = False
                self.refresh_soon()

        def failed(e):
            self._computing = False
            log.info("roster: %s", e)
        self.win.bridge.call(self.win.core.submit(view.roster), ok=done, fail=failed)

    def refresh(self):
        """At once, in this thread (a click, a fold, the tests)."""
        view = self.win.ctx.view
        me = view.me if self.win.core.me else None
        self._show(view.roster() if me is not None else [])

    def _show(self, groups):
        view = self.win.ctx.view
        me = view.me if self.win.core.me else None
        self._show_me(me)
        if me is not None and not self._mutuals_asked:
            self._mutuals_asked = True  # whom to write to: asked once a day
            self.win.bridge.call(view.refresh_mutuals(), ok=lambda _n: self.refresh_soon(),
                                 fail=lambda e: log.info("mutuals: %s", e))
        shape = [(g.name, tuple(row_key(i) for i in g.items)) for g in groups]
        old = self._shape or []
        if shape != old:
            if old and shape[:len(old)] == old:  # groups added at the end (People came)
                self._build(groups[len(old):], append=True)
            else:  # lanes came or went: build anew
                self._build(groups)
            self._shape = shape
        for g in groups:
            if g.name in self.heads:
                self.heads[g.name].show_counts(g, g.name in self.folded)
            for item in g.items:
                row = self.rows.get(row_key(item))
                if row is not None:  # not built yet: it comes with this very item
                    row.update_item(item)
        self._filter(self.search.text())

    def _build(self, groups, append=False):
        self.list.setUpdatesEnabled(False)
        try:
            self._build_rows(groups, append)
        finally:
            self.list.setUpdatesEnabled(True)

    BATCH = 16  # rows built at a time: a full roster at once froze the window ~350 ms

    def _build_rows(self, groups, append=False):
        """The rows, a batch now and the rest a batch a tick after (each RosterRow is a
        handful of widgets): the roster shows at once and fills in as it goes."""
        if not append:
            self.list.clear()
            self.rows, self.heads = {}, {}
            self._queue = []
            self._tall = {}  # a row's height, measured once a shape (asking each is slow)
        for g in groups:
            if g.items:
                self._queue.append(("head", g, None))
                self._queue += [("row", g, item) for item in g.items]
        self._build_some()

    def _build_some(self):
        n = 0
        self.list.setUpdatesEnabled(False)
        try:
            while self._queue and n < self.BATCH:
                kind, g, item = self._queue.pop(0)
                if kind == "head":
                    it = QListWidgetItem()
                    it.setData(Qt.ItemDataRole.UserRole, None)
                    it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    head = RosterHeader(self, g.name)
                    head.show_counts(g, g.name in self.folded)
                    it.setSizeHint(QSize(0, head.sizeHint().height()))
                    self.list.addItem(it)
                    self.list.setItemWidget(it, head)
                    self.heads[g.name] = head
                    continue
                row_it = QListWidgetItem()
                row = RosterRow(self, item)
                row_it.setData(Qt.ItemDataRole.UserRole, row.key)
                row_it.setData(Qt.ItemDataRole.UserRole + 1, g.name)
                shape = (row.compact, row.faces, bool(row.line.text()),
                         row.status.isVisibleTo(row))
                if shape not in self._tall:
                    h = row.sizeHint().height()
                    self._tall[shape] = h if row.compact else max(h, row.face.height() + 8)
                row_it.setSizeHint(QSize(0, self._tall[shape]))
                self.list.addItem(row_it)
                self.list.setItemWidget(row_it, row)
                self.rows[row.key] = row
                n += 1
        finally:
            self.list.setUpdatesEnabled(True)
        self._filter(self.search.text())
        if self._queue:
            QTimer.singleShot(0, self._build_some)

    def _show_me(self, me):
        if me is None:
            self.account_btn.setText(_("accounts") + " ▾")
            self.me_name.setText(_("roster_offline"))
            self.me_handle.setText("")
            self.news.setText("")
            return
        self.me_name.setText(f"<b>{display_name(me)}</b>")
        self.me_handle.setText("@" + me.handle)
        self.account_btn.setText("@" + me.handle.partition("@")[0] + " ▾")
        self.account_btn.setToolTip(f"{_('accounts')}: @{me.handle}")
        n = self.win.core.activity_unread()
        link = self.win.theme.c["link"].name()
        self.news.setText(f'<a href="fedtail:activity" style="color:{link};">'
                          f'{esc(_("roster_news", n=n) if n else _("roster_no_news"))}</a>')
        if me.avatar_static and getattr(self, "_my_face", None) != me.avatar_static:
            self._my_face = me.avatar_static
            from .card import _round
            self.win.images.get(me.avatar_static,
                                lambda pm: self.avatar.setPixmap(_round(pm, AVATAR)))

    def _filter(self, text):
        for i in range(self.list.count()):
            it = self.list.item(i)
            key = it.data(Qt.ItemDataRole.UserRole)
            if key is None:  # a group's title: there while searching, else always
                it.setHidden(not self.look["groups"])
                continue
            group = it.data(Qt.ItemDataRole.UserRole + 1)
            row = self.rows.get(key)
            folded = group in self.folded and self.look["groups"]
            it.setHidden(rules.hidden(row.item if row is not None else None,
                                      row.line.text() if row is not None else "", text,
                                      folded, self.look))

    def toggle(self, group):
        self.folded ^= {group}
        self.win.core.set_state("roster_folded", sorted(self.folded))
        self.refresh()

    # ---- acting ----------------------------------------------------------------------
    def open(self, key):
        """An item chosen (a row's key): its lane, or its thread, in front in the
        messages window."""
        kind, post_id = rules.what(key)
        self.win.show_raise()  # first: what opens in a shown window gets a tab
        if kind == "lane":
            self.win.select_lane(key)
        elif kind == "person":
            row = self.rows.get(key)
            item = row.item if row is not None else None
            if item is not None and item.who is not None:
                self.win.write_to(item.who)  # our talk, a tab of its own, written to
        else:
            self.win.open_thread(post_id)
        self.win.show_raise()

    def _activated(self, it):
        key = it.data(Qt.ItemDataRole.UserRole) if it else None
        if key:
            self.open(key)

    def _search_enter(self):
        """Enter: the only lane found opens; otherwise the words go to Search."""
        shown = [k for k, r in self.rows.items() if r.matches(self.search.text())]
        if len(shown) == 1:
            self.open(shown[0])
        elif self.search.text().strip():
            self.win.open_search(self.search.text().strip())
            self.win.show_raise()
        self.search.clear()

    def _menu(self, pos):
        from PySide6.QtWidgets import QMenu
        it = self.list.itemAt(pos)
        key = it.data(Qt.ItemDataRole.UserRole) if it else None
        if not key:  # empty space or a group's title: how the roster looks
            self._look_menu().exec(self.list.mapToGlobal(pos))
            return
        m = QMenu(self)
        m.addAction(_("roster_open"), lambda: self.open(key))
        row = self.rows.get(key)
        if row is not None and row.item.unread:
            m.addAction(_("mark_all_read"), lambda: self._read_all(key))
        m.addSeparator()
        m.addMenu(self._look_menu()).setText(_("roster_look"))
        m.exec(self.list.mapToGlobal(pos))

    def _read_all(self, key):
        """Everything in it read (marking the read ones again changes nothing)."""
        view = self.win.ctx.view
        row = self.rows.get(key)
        ids = rules.read_ids(view, key, row.item if row is not None else None)
        if ids:
            view.mark_read(ids)

    def dress(self):
        """Pictures on the bottom buttons (ui.additional_icons); again after a theme."""
        from . import icons
        t = self.win.theme
        icons.dress(self.menu_btn, "menu", t, words=_("menu"))
        icons.dress(self.look_btn, "settings", t, glyph="⚙")
        self.account_btn.setIcon(icons.icon("accounts", t) if icons.wanted(t)
                                 else QIcon())

    def _pop_accounts(self):
        pop_menu(self.win.accounts_menu(self), self.account_btn, True)

    def eventFilter(self, obj, e):
        from PySide6.QtCore import QEvent
        if obj is self.list and e.type() == QEvent.Type.KeyPress and \
                e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._activated(self.list.currentItem())
            return True
        return super().eventFilter(obj, e)

    # ---- how it looks ------------------------------------------------------------
    def _look_menu(self):
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        for key in ("compact", "header", "search", "bottom", "only_new", "groups",
                    "on_top"):
            a = m.addAction(_("roster_look_" + key))
            a.setCheckable(True)
            a.setChecked(bool(self._on_top() if key == "on_top" else self.look[key]))
            a.toggled.connect(lambda on, k=key: self.set_look(k, on))
        return m

    def _on_top(self):
        on = self.look["on_top"]
        return self.win.cfg["ui"].get("roster_on_top", False) if on is None else on

    def set_look(self, key, on):
        self.look[key] = bool(on)
        self.win.core.set_state("roster_look", self.look)
        if key == "compact":
            self._shape = None  # the rows are built anew
        self._apply_look()
        self.refresh()

    def _apply_look(self):
        self.head_box.setVisible(self.look["header"])
        self.search.setVisible(self.look["search"])
        self.bottom.setVisible(self.look["bottom"])
        top = bool(self._on_top())
        if bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) != top:
            shown = self.isVisible()
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, top)
            if shown:
                self.show()

    # ---- the window ------------------------------------------------------------------
    def _restore_place(self):
        got = self.win.core.get_state("roster_geometry")
        if isinstance(got, str):
            from PySide6.QtCore import QByteArray
            try:
                self.restoreGeometry(QByteArray(bytes.fromhex(got)))
            except ValueError:
                pass
        # the first time — or a place saved over the messages' window (the old default
        # put it there when the window stood at the screen's left edge): placed beside
        # it once both are on the screen (showEvent)

    def showEvent(self, e):  # noqa: N802 — Qt's name
        super().showEvent(e)
        QTimer.singleShot(0, self.step_aside)

    def step_aside(self, force=False):
        """The roster beside the messages' window, never over it: on its left if the
        screen has room there, else on its right; with no room either side, at the
        screen's right edge and the messages' window narrowed to its left (as a
        messenger stands). A place of the user's own that covers little of the window
        is left as it is."""
        win = self.win
        if not win.isVisible() or win.isFullScreen():
            return
        me, them = self.frameGeometry(), win.frameGeometry()
        over = me.intersected(them)
        if not force and over.width() * over.height() < me.width() * me.height() // 3:
            return
        screen = (win.screen() or self.screen()).availableGeometry()
        gap = 8
        top = max(screen.top(), min(them.top(), screen.bottom() - me.height()))
        if them.left() - screen.left() >= me.width() + gap:
            self.move(QPoint(them.left() - me.width() - gap, top))
        elif screen.right() - them.right() >= me.width() + gap:
            self.move(QPoint(them.right() + gap + 1, top))
        else:
            x = screen.right() - me.width() + 1
            room = x - gap - screen.left()
            if win.isMaximized():
                win.showNormal()
            if room >= max(win.minimumWidth(), 480):
                # the frame's edges: what the window manager adds around the contents
                fw = them.width() - win.width()
                fh = them.height() - win.height()
                win.setGeometry(screen.left() + fw // 2, screen.top() + fh - fw // 2,
                                room - fw, min(win.height(), screen.height() - fh))
            self.move(QPoint(x, screen.top()))
        log.info("roster placed beside the window (it stood over it)")

    def save_place(self):
        try:
            self.win.core.set_state("roster_geometry", bytes(self.saveGeometry()).hex())
        except Exception as e:  # noqa: BLE001 — closing after the core: nothing to keep in
            log.debug("roster place: %s", e)

    def closeEvent(self, e):
        """Closing the roster is closing fedtail, as in a messenger: to the tray with
        ui.close_to_tray (both windows go, the tray brings both back), else for good."""
        self.save_place()
        win = self.win
        if win.quitting:
            e.accept()
            return
        if win.tray and win.cfg["ui"]["close_to_tray"]:
            e.ignore()
            self.hide()
            win.hide()
            return
        e.accept()
        win.quit()
