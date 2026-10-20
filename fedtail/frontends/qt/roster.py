"""The roster window of ``ui.layout = "qip"`` (docs/LAYOUTS.md): a narrow window of its
own, as in QIP, Psi+ or the Mail.ru Agent — who I am on top, a search line, then the
lanes in groups, each with its unread count, a line of its newest post and the face of
its author. A click opens the lane in the main window, which in this layout is the
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
from ...model.text import snippet
from .text import display_name, esc

log = logging.getLogger(__name__)

AVATAR = 40      # mine, in the header
FACE = 28        # the newest post's author, beside an item
REFRESH_MS = 300  # coalesce bursts of events into one rebuild


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
        from .window import LANE_ICON
        if win.theme.shape["lane_icons"]:
            kind = {"thread": "subs", "talk": "direct"}.get(item.kind,
                                                             item.key.split(":")[0])
            ic = QIcon.fromTheme(LANE_ICON.get(kind, ""))
            if not ic.isNull():
                icon.setPixmap(ic.pixmap(18, 18))
        h.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(0)
        top = QHBoxLayout()
        top.setSpacing(6)
        self.name = QLabel()
        self.name.setObjectName("rosterName")
        top.addWidget(self.name, 1)
        self.badge = QLabel()
        self.badge.setObjectName("badge")
        self.badge.setProperty("kind", "normal")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setMinimumWidth(22)
        top.addWidget(self.badge)
        col.addLayout(top)
        self.line = QLabel()
        self.line.setObjectName("rosterLine")
        self.line.setTextFormat(Qt.TextFormat.PlainText)
        col.addWidget(self.line)
        h.addLayout(col, 1)
        self.face = QLabel()
        self.face.setFixedSize(FACE, FACE)
        h.addWidget(self.face, 0, Qt.AlignmentFlag.AlignTop)
        self._face_url = None
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
        last = item.last
        if last is not None:
            a = last.author
            # a status line: who wrote last and how it begins, plain text
            self.line.setText(f"{a.name or a.username or a.handle}: {snippet(last, 80)}")
            self.line.setToolTip(snippet(last, 300))
        else:
            self.line.setText("")
        self.line.setVisible(bool(self.line.text()))
        url = last.author.avatar_static if last is not None else ""
        if url != self._face_url:
            self._face_url = url
            self.face.clear()
            if url:
                from .card import _round
                self.roster.win.images.get(
                    url, lambda pm, w=self.face: _alive(w) and w.setPixmap(_round(pm, FACE)))
        tip = item.title + (f" — {_('roster_unread', n=item.unread)}" if new else "")
        self.setToolTip(tip)

    def matches(self, text):
        t = text.casefold()
        return not t or t in self.item.title.casefold() or t in self.line.text().casefold()


def row_key(item):
    """A roster item's key among the rows: a lane by its name, a thread or talk by kind
    and id (one thread may be both followed and private)."""
    return item.key if item.kind == "lane" else f"{item.kind}/{item.key}"


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
        lit = sum(1 for i in group.items if i.unread)
        title = _("lists_header") if group.name == "lists" else _("grp_" + group.name)
        self.label.setText(f"{'▸' if folded else '▾'} <b>{esc(title)}</b> "
                           f"({lit}/{len(group.items)})")

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
        self.setWindowTitle(_("roster_title"))
        self.setWindowIcon(win.windowIcon())
        if win.cfg["ui"].get("roster_on_top", False):
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(280, 640)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)
        # who I am: face, name, @address, and what is new in Activity
        head = QHBoxLayout()
        self.avatar = QLabel()
        self.avatar.setFixedSize(AVATAR, AVATAR)
        head.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignTop)
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
        head.addLayout(who, 1)
        v.addLayout(head)
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
        self.list.itemActivated.connect(self._activated)
        self.list.itemClicked.connect(self._activated)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        v.addWidget(self.list, 1)
        # at the bottom, as in every messenger: the menu, and what I do — write
        bottom = QHBoxLayout()
        self.menu_btn = QPushButton(_("menu"))
        self.menu_btn.setObjectName("tool")
        self.menu_btn.clicked.connect(lambda: self.win._pop_app_menu(self.menu_btn))
        bottom.addWidget(self.menu_btn)
        self.write_btn = QPushButton(win.theme.word("compose", _("write")))
        self.write_btn.setObjectName("compose")
        self.write_btn.setToolTip(_("write") + " (Ctrl+N)")
        self.write_btn.clicked.connect(lambda: self.win.compose())
        bottom.addWidget(self.write_btn, 1)
        v.addLayout(bottom)
        self.rows, self.heads = {}, {}
        self.folded = set(win.core.get_state("roster_folded", []) or [])
        self._shape = None
        self._timer = QTimer(self, singleShot=True, interval=REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self._restore_place()

    # ---- contents ------------------------------------------------------------------
    def refresh_soon(self):
        self._timer.start()

    def refresh(self):
        view = self.win.ctx.view
        me = view.me if self.win.core.me else None
        self._show_me(me)
        groups = view.roster() if me is not None else []
        shape = [(g.name, tuple(row_key(i) for i in g.items)) for g in groups]
        if shape != self._shape:  # lanes came or went: build anew
            self._build(groups)
            self._shape = shape
        for g in groups:
            if g.name in self.heads:
                self.heads[g.name].show_counts(g, g.name in self.folded)
            for item in g.items:
                self.rows[row_key(item)].update_item(item)
        self._filter(self.search.text())

    def _build(self, groups):
        self.list.clear()
        self.rows, self.heads = {}, {}
        for g in groups:
            if not g.items:
                continue
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, None)
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            head = RosterHeader(self, g.name)
            it.setSizeHint(QSize(0, head.sizeHint().height()))
            self.list.addItem(it)
            self.list.setItemWidget(it, head)
            self.heads[g.name] = head
            for item in g.items:
                row_it = QListWidgetItem()
                row = RosterRow(self, item)
                row_it.setData(Qt.ItemDataRole.UserRole, row.key)
                row_it.setData(Qt.ItemDataRole.UserRole + 1, g.name)
                row_it.setSizeHint(QSize(0, max(row.sizeHint().height(), FACE + 8)))
                self.list.addItem(row_it)
                self.list.setItemWidget(row_it, row)
                self.rows[row.key] = row

    def _show_me(self, me):
        if me is None:
            self.me_name.setText(_("roster_offline"))
            self.me_handle.setText("")
            self.news.setText("")
            return
        self.me_name.setText(f"<b>{display_name(me)}</b>")
        self.me_handle.setText("@" + me.handle)
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
                it.setHidden(False)
                continue
            group = it.data(Qt.ItemDataRole.UserRole + 1)
            row = self.rows.get(key)
            hide = (group in self.folded and not text) or (row is not None and
                                                           not row.matches(text))
            it.setHidden(hide)

    def toggle(self, group):
        self.folded ^= {group}
        self.win.core.set_state("roster_folded", sorted(self.folded))
        self.refresh()

    # ---- acting ----------------------------------------------------------------------
    def open(self, key):
        """An item chosen (a row's key): its lane, or its thread, in front in the
        messages window."""
        kind, _sep, post_id = key.partition("/") if "/" in key else ("lane", "", key)
        if kind == "lane":
            self.win.select_lane(key)
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
        if not key:
            return
        m = QMenu(self)
        m.addAction(_("roster_open"), lambda: self.open(key))
        row = self.rows.get(key)
        if row is not None and row.item.unread:
            m.addAction(_("mark_all_read"), lambda: self._read_all(key))
        m.exec(self.list.mapToGlobal(pos))

    def _read_all(self, key):
        """Everything in it read (marking the read ones again changes nothing)."""
        view = self.win.ctx.view
        row = self.rows.get(key)
        if row is not None and row.item.kind != "lane":
            ids = list(row.item.ids)
        else:
            ids = [e.id for _item, e in view.entries(key)]
        if ids:
            view.mark_read(ids)

    # ---- the window ------------------------------------------------------------------
    def _restore_place(self):
        got = self.win.core.get_state("roster_geometry")
        if isinstance(got, str):
            from PySide6.QtCore import QByteArray
            try:
                self.restoreGeometry(QByteArray(bytes.fromhex(got)))
            except ValueError:
                pass
        else:  # the first time: on the left of the main window
            g = self.win.geometry()
            self.move(QPoint(max(0, g.left() - self.width() - 12), g.top()))

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
