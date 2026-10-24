"""The Silence dialog: word filters (the server's, so every client of yours obeys
them), muted and blocked people. Muting and blocking themselves live in a
post's ⋯ menu and on the profile; here you see the lists and undo."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
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
from ..common import timed

CONTEXTS = ["home", "notifications", "public", "thread", "account"]
KEEP = -1  # the term as it is (the edit window's first choice)


class FilterEditDialog(QDialog):
    """A filter of mine, changed: its title, words, fold or hide, where, how long."""

    def __init__(self, parent, f):
        super().__init__(parent)
        self.setWindowTitle(_("filter_edit_title", title=f.title or ", ".join(f.words)))
        form = QFormLayout(self)
        self.title = QLineEdit(f.title)
        form.addRow(_("filter_title_label"), self.title)
        self.words = QLineEdit(", ".join(f.words))
        self.words.setPlaceholderText(_("filter_words"))
        form.addRow(_("filter_new").rstrip(":"), self.words)
        self.action = QComboBox()
        self.action.addItem(_("filter_warn"), "warn")
        self.action.addItem(_("filter_hide"), "hide")
        self.action.setCurrentIndex(1 if f.action == "hide" else 0)
        form.addRow("", self.action)
        row = QHBoxLayout()
        self.ctx_boxes = {}
        for c in CONTEXTS:
            box = QCheckBox(_("filter_ctx_" + c))
            box.setChecked(c in f.contexts if f.contexts else c != "notifications")
            self.ctx_boxes[c] = box
            row.addWidget(box)
        form.addRow(_("filter_where"), row)
        self.span = QComboBox()
        self.span.setToolTip(_("filter_for_q"))
        self.span.addItem(timed.filter_extra(f).lstrip(" ·") or _("span_ever"), KEEP)
        for secs, label in timed.spans():
            self.span.addItem(label, secs)
        form.addRow(_("filter_for"), self.span)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def changes(self):
        """What view.edit_filter takes: title, words, action, contexts, expires_in."""
        return filter_changes(self.title.text(), self.words.text(), self.action.currentData(),
                              [c for c, b in self.ctx_boxes.items() if b.isChecked()],
                              self.span.currentData())


def filter_changes(title, words, action, contexts, span):
    """The edit window's answer as view.edit_filter's arguments (span KEEP: the term
    stays; 0: for good)."""
    return {"title": title.strip() or None,
            "words": [x.strip() for x in words.split(",") if x.strip()],
            "action": action, "contexts": list(contexts) or ["home"],
            "expires_in": None if span == KEEP else int(span or 0)}


class SilenceDialog(QDialog):
    TABS = ("filters", "muted", "blocked", "domains")  # in this order; tab= picks one

    def __init__(self, win, tab="filters"):
        super().__init__(win)
        self.win, self.core = win, win.ctx.view  # filters and people as fedtail.model
        self._filter_objs = {}  # id -> WordFilter, as last drawn
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
        tabs.setCurrentIndex(self.TABS.index(tab) if tab in self.TABS else 0)
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
        change = QPushButton(_("filter_edit"))
        change.setObjectName("tool")
        change.clicked.connect(lambda: self._edit_filter())
        self.filter_list.itemDoubleClicked.connect(lambda _it: self._edit_filter())
        btns = QHBoxLayout()
        btns.addWidget(change)
        btns.addWidget(rm)
        btns.addStretch(1)
        v.addLayout(btns)

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
        span_row = QHBoxLayout()
        span_row.addWidget(QLabel(_("filter_for")))
        self.span = QComboBox()  # how long: for good, an hour… (the server ends it)
        self.span.setToolTip(_("filter_for_q"))
        for secs, label in timed.spans():
            self.span.addItem(label, secs)
        span_row.addWidget(self.span)
        span_row.addStretch(1)
        v.addLayout(span_row)
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
                                                  self.action.currentData(), contexts,
                                                  expires_in=self.span.currentData() or None),
                             ok=lambda _f: (self.words.clear(), self.reload()),
                             fail=self.win.error)

    def _edit_filter(self, answer=None):
        """Edit… the chosen filter. answer: what the window would give (tests); None —
        the window asks."""
        it = self.filter_list.currentItem()
        f = self._filter_objs.get(it.data(Qt.ItemDataRole.UserRole)) if it else None
        if f is None:
            return
        if answer is None:
            dlg = FilterEditDialog(self, f)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            answer = dlg.changes()
        if not answer["words"] and not f.posts:
            return  # a word filter with no words left: "Delete" is for that
        if f.posts and not f.words:
            answer["words"] = None  # the hidden posts' filter: no words to set
        self.win.bridge.call(self.core.edit_filter(f.id, **answer),
                             ok=lambda _r: (self.win.statusBar().showMessage(
                                 _("filter_saved"), 6000), self.reload()),
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
        self._filter_objs = {f.id: f for f in filters}
        for f in filters:
            words = ", ".join(f.words)
            how = _("filter_hide") if f.action == "hide" else _("filter_warn")
            it = QListWidgetItem(f"{f.title or words} — {how}"
                                 + (f" ({words})" if words and words != f.title else "")
                                 + timed.filter_extra(f))
            it.setData(Qt.ItemDataRole.UserRole, f.id)
            self.filter_list.addItem(it)

    def _people(self, got):
        self.domain_list.clear()
        for d in got.domains:
            it = QListWidgetItem(d)
            it.setData(Qt.ItemDataRole.UserRole, d)
            self.domain_list.addItem(it)
        for lst, accounts in ((self.muted_list, got.muted), (self.blocked_list, got.blocked)):
            lst.clear()
            for a in accounts:
                it = QListWidgetItem(f"{a.name or a.username} @{a.handle or a.id}")
                it.setData(Qt.ItemDataRole.UserRole, a.id)
                lst.addItem(it)
