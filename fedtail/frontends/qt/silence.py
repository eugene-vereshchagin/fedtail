"""The Silence dialog: word filters (the server's, so every client of yours obeys
them), muted and blocked people. Muting and blocking themselves live in a
post's ⋯ menu and on the profile; here you see the lists and undo."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...i18n import _

CONTEXTS = ["home", "notifications", "public", "thread", "account"]


class SilenceDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win, self.core = win, win.core
        self.setWindowTitle(_("silence_title"))
        self.setMinimumSize(560, 460)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)
        tabs.addTab(self._filters_tab(), _("silence_filters"))
        self.muted_list = QListWidget()
        tabs.addTab(self._people_tab(self.muted_list, "mute"), _("silence_muted"))
        self.blocked_list = QListWidget()
        tabs.addTab(self._people_tab(self.blocked_list, "block"), _("silence_blocked"))
        self.domain_list = QListWidget()
        tabs.addTab(self._people_tab(self.domain_list, "domain"), _("silence_domains"))
        close = QPushButton(_("close"))
        close.setObjectName("tool")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        self.reload()

    # ---- filters ------------------------------------------------------------------
    def _filters_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        hint = QLabel(_("filters_hint"))
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        v.addWidget(hint)
        self.filter_list = QListWidget()
        v.addWidget(self.filter_list, 1)
        rm = QPushButton(_("filter_delete"))
        rm.setObjectName("tool")
        rm.clicked.connect(self._delete_filter)
        v.addWidget(rm, 0, Qt.AlignmentFlag.AlignLeft)

        v.addWidget(QLabel(_("filter_new")))
        self.words = QLineEdit()
        self.words.setPlaceholderText(_("filter_words"))
        v.addWidget(self.words)
        row = QHBoxLayout()
        self.action = QComboBox()
        self.action.addItem(_("filter_warn"), "warn")
        self.action.addItem(_("filter_hide"), "hide")
        row.addWidget(self.action)
        self.ctx_boxes = {}
        for c in CONTEXTS:
            box = QCheckBox(_("filter_ctx_" + c))
            box.setChecked(c != "notifications")
            self.ctx_boxes[c] = box
            row.addWidget(box)
        row.addStretch(1)
        v.addLayout(row)
        add = QPushButton(_("filter_add"))
        add.setObjectName("primary")
        add.clicked.connect(self._add_filter)
        v.addWidget(add, 0, Qt.AlignmentFlag.AlignLeft)
        return w

    def _add_filter(self):
        words = [x.strip() for x in self.words.text().split(",") if x.strip()]
        if not words:
            return
        contexts = [c for c, b in self.ctx_boxes.items() if b.isChecked()] or ["home"]
        self.win.bridge.call(self.core.add_filter(", ".join(words), words,
                                                  self.action.currentData(), contexts),
                             ok=lambda _f: (self.words.clear(), self.reload()),
                             fail=self.win.error)

    def _delete_filter(self):
        it = self.filter_list.currentItem()
        if it:
            self.win.bridge.call(self.core.delete_filter(it.data(Qt.ItemDataRole.UserRole)),
                                 ok=lambda _r: self.reload(), fail=self.win.error)

    # ---- people -------------------------------------------------------------------
    def _people_tab(self, lst, kind):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(lst, 1)
        undo = QPushButton(_("unmute") if kind == "mute" else _("unblock"))
        if kind == "domain":
            hint = QLabel(_("silence_domains_hint"))
            hint.setObjectName("muted")
            hint.setWordWrap(True)
            v.insertWidget(0, hint)
        undo.setObjectName("tool")
        undo.clicked.connect(lambda: self._undo(lst, kind))
        v.addWidget(undo, 0, Qt.AlignmentFlag.AlignLeft)
        return w

    def _undo(self, lst, kind):
        it = lst.currentItem()
        if not it:
            return
        acc_id = it.data(Qt.ItemDataRole.UserRole)
        if kind == "domain":
            self.win.bridge.call(self.core.block_domain(acc_id, False),
                                 ok=lambda _r: self.reload(), fail=self.win.error)
            return
        call = self.core.mute if kind == "mute" else self.core.block
        self.win.bridge.call(call(acc_id, False), ok=lambda _r: self.reload(),
                             fail=self.win.error)

    # ---- loading --------------------------------------------------------------------
    def reload(self):
        # answers may come back out of order (the first load and the one after an
        # add run side by side): only the latest one is drawn
        self._gen = getattr(self, "_gen", 0) + 1
        gen = self._gen
        self.win.bridge.call(self.core.filters(),
                             ok=lambda f: gen == self._gen and self._filters(f),
                             fail=self.win.error)
        self.win.bridge.call(self.core.silenced_people(),
                             ok=lambda p: gen == self._gen and self._people(p),
                             fail=self.win.error)

    def _filters(self, filters):
        self.filter_list.clear()
        for f in filters:
            words = ", ".join(k.get("keyword", "") for k in f.get("keywords") or [])
            how = _("filter_hide") if f.get("filter_action") == "hide" else _("filter_warn")
            it = QListWidgetItem(f"{f.get('title') or words} — {how}"
                                 + (f" ({words})" if words and words != f.get("title") else ""))
            it.setData(Qt.ItemDataRole.UserRole, f["id"])
            self.filter_list.addItem(it)

    def _people(self, got):
        self.domain_list.clear()
        for d in got.get("domains") or []:
            it = QListWidgetItem(d)
            it.setData(Qt.ItemDataRole.UserRole, d)
            self.domain_list.addItem(it)
        for lst, accounts in ((self.muted_list, got["muted"]), (self.blocked_list, got["blocked"])):
            lst.clear()
            for a in accounts:
                it = QListWidgetItem(f"{a.get('display_name') or a.get('username', '')} "
                                     f"@{a.get('acct', a['id'])}")
                it.setData(Qt.ItemDataRole.UserRole, a["id"])
                lst.addItem(it)
