"""Ctrl+F: find in the lane, thread or profile that is open, like in a browser."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from ...i18n import _
from ..findtext import haystack, matches


class FindBar(QWidget):
    closed = Signal()

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("findBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(_("find_placeholder"))
        self.edit.setClearButtonEnabled(True)
        self.edit.installEventFilter(self)
        lay.addWidget(self.edit, 1)
        self.count = QLabel()
        self.count.setObjectName("counter")
        lay.addWidget(self.count)
        for text, tip, slot in (("↑", _("find_prev"), lambda: self.step(-1)),
                                ("↓", _("find_next"), lambda: self.step(1)),
                                ("✕", _("find_close"), self.close_bar)):
            b = QPushButton(text)
            b.setObjectName("tool")
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            lay.addWidget(b)
        self.view = None
        self.hits = []
        self.pos = -1
        self._timer = QTimer(self, singleShot=True, interval=200)
        self._timer.timeout.connect(lambda: self.search(jump=True))
        self.edit.textChanged.connect(lambda _t: self._timer.start())
        self.hide()

    # ---- public ---------------------------------------------------------------------
    def open(self):
        self.show()
        self.edit.setFocus()
        self.edit.selectAll()
        if self.edit.text():
            self.search(jump=True)

    def close_bar(self):
        self._mark(None)
        self.hide()
        self.closed.emit()

    def view_changed(self):
        """Another lane or tab came up: look there."""
        if self.isVisible():
            self._mark(None)
            self.search(jump=True)

    def step(self, delta):
        if not self.isVisible():
            self.open()
            return
        self.search(jump=False)  # the view may have changed since
        if not self.hits:
            return
        self.pos = (self.pos + delta) % len(self.hits) if self.pos >= 0 else \
            (0 if delta > 0 else len(self.hits) - 1)
        self._go()

    # ---- searching -------------------------------------------------------------------
    def search(self, jump):
        view = self.win.current_view()
        if view is not self.view:
            self._mark(None)
            self.view, self.pos = view, -1
        query = self.edit.text()
        old = self.hits[self.pos] if 0 <= self.pos < len(self.hits) else None
        self.hits = []
        if view is not None and query.strip():
            for key in view.order:
                row = view.rows[key]
                if row.status_id is None:
                    continue
                spec = row.spec
                if matches(query, haystack(spec.status, spec.extra.get("short_id"))):
                    self.hits.append(key)
        if old in self.hits:
            self.pos = self.hits.index(old)
        elif jump and self.hits:
            self.pos = self._nearest(view)
            self._go()
            return
        else:
            self.pos = -1
            self._mark(None)
        self._show_count()

    def _nearest(self, view):
        """The first hit from where the reader is now, not from the very top."""
        top = view.verticalScrollBar().value()
        for i, key in enumerate(self.hits):
            row = view.rows[key]
            if view._top(row) + row.height() > top:
                return i
        return 0

    def _go(self):
        key = self.hits[self.pos]
        self._mark(key)
        self.view.scroll_to(key, "top")
        self._show_count()

    def _mark(self, key):
        if self.view is None:
            return
        for k, row in self.view.rows.items():
            card = getattr(row, "card", None)
            if card is None:
                continue
            want = "true" if k == key else "false"
            if card.property("found") != want:
                card.setProperty("found", want)
                card.style().unpolish(card)
                card.style().polish(card)

    def _show_count(self):
        if not self.edit.text().strip():
            self.count.setText("")
        elif not self.hits:
            self.count.setText(_("find_none"))
        else:
            self.count.setText(_("find_count", i=self.pos + 1 if self.pos >= 0 else 0,
                                 n=len(self.hits)))
        self.count.setProperty("over", "true" if self.edit.text().strip() and not self.hits
                               else "false")
        self.count.style().unpolish(self.count)
        self.count.style().polish(self.count)

    # ---- keys ----------------------------------------------------------------------
    def eventFilter(self, obj, e):
        if e.type() == e.Type.KeyPress:
            if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.step(-1 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1)
                return True
            if e.key() == Qt.Key.Key_Escape:
                self.close_bar()
                return True
            if e.matches(QKeySequence.StandardKey.FindNext):
                self.step(1)
                return True
            if e.matches(QKeySequence.StandardKey.FindPrevious):
                self.step(-1)
                return True
        return super().eventFilter(obj, e)
