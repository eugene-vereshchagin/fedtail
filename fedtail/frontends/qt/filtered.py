"""≡ → Filtered notifications (notify.filtered): who my server holds back and why.

Mastodon 4.3+ keeps mentions from strangers, brand-new accounts and the like aside
until let through. Here: the senders waiting (open the profile, Let through,
Dismiss) and the policy itself — for each kind of sender accept, filter or drop."""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from ...core.model import html_to_text
from ...i18n import _

log = logging.getLogger(__name__)

CHOICES = ("accept", "filter", "drop")


class FilteredDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.core = win.core
        self.setWindowTitle(_("filtered_title"))
        self.resize(560, 480)
        lay = QVBoxLayout(self)
        self.note = QLabel(_("filtered_loading"))
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._profile)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.accept_btn = QPushButton(_("filtered_accept"))
        self.dismiss_btn = QPushButton(_("filtered_dismiss"))
        self.profile_btn = QPushButton(_("filtered_profile"))
        for b, fn in ((self.accept_btn, lambda: self._answer(True)),
                      (self.dismiss_btn, lambda: self._answer(False)),
                      (self.profile_btn, lambda: self._profile(self.list.currentItem()))):
            b.setObjectName("tool")
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.policy_box = QGroupBox(_("filtered_policy"))
        form = QFormLayout(self.policy_box)
        self.combos = {}
        for key in self.core.FILTER_POLICY:
            box = QComboBox()
            for c in CHOICES:
                box.addItem(_("policy_" + c), c)
            box.currentIndexChanged.connect(lambda _i, k=key: self._set(k))
            self.combos[key] = box
            form.addRow(_("filtered_" + key), box)
        self.policy_box.hide()
        lay.addWidget(self.policy_box)
        self._filling = False
        self.load()

    def load(self):
        self.win.bridge.call(self.core.filtered(), ok=self.fill, fail=self.win.error)

    def fill(self, got):
        self.list.clear()
        if got is None:
            self.note.setText(_("filtered_unsupported"))
            for b in (self.accept_btn, self.dismiss_btn, self.profile_btn):
                b.setEnabled(False)
            return
        self.note.setText(_("filtered_note", n=len(got["requests"])))
        for r in got["requests"]:
            acc = r.get("account") or {}
            last = html_to_text((r.get("last_status") or {}).get("content", ""))
            text = f"@{acc.get('acct', '?')} — " + \
                _("filtered_count", n=int(r.get("notifications_count") or 0))
            if last:
                text += "\n" + last[:140]
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, r)
            self.list.addItem(it)
        self._filling = True
        try:
            for key, box in self.combos.items():
                if key in got["policy"]:
                    box.setCurrentIndex(CHOICES.index(got["policy"][key])
                                        if got["policy"][key] in CHOICES else 0)
                else:
                    box.setEnabled(False)
        finally:
            self._filling = False
        self.policy_box.setVisible(bool(got["policy"]))

    def _current(self, item=None):
        it = item or self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _answer(self, accept):
        r = self._current()
        if not r:
            return
        log.info("filtered: %s a sender", "accepted" if accept else "dismissed")
        self.win.bridge.call(self.core.answer_filtered(r["id"], accept),
                             ok=lambda _x: self.load(), fail=self.win.error)

    def _profile(self, item):
        r = self._current(item)
        if r and r.get("account"):
            self.win.open_account(r["account"]["id"])

    def _set(self, key):
        if self._filling:
            return
        value = self.combos[key].currentData()
        self.win.bridge.call(self.core.set_filter_policy(**{key: value}), fail=self.win.error)
