"""Ctrl+F: find in the lane, thread or profile that is open, like in a browser."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from ...core.search import haystack, matches
from ...i18n import _


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
        self.deeper = QPushButton(_("find_deeper"))
        self.deeper.setObjectName("tool")
        self.deeper.setToolTip(_("find_deeper_tip"))
        self.deeper.clicked.connect(self.search_deeper)
        self.deeper.hide()
        lay.addWidget(self.deeper)
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
            # every post of the lane, also those whose cards aren't built yet
            for spec in view.model or [view.rows[k].spec for k in view.order]:
                if not spec.status or spec.extra.get("separator"):
                    continue
                if matches(query, haystack(spec.status, spec.extra.get("short_id"))):
                    self.hits.append(spec.key)
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

    def _lane_name(self):
        """The lane on screen, if the view is a lane (threads have no archive)."""
        w = self.win.tabs.currentWidget()
        if w is self.win.stack:
            w = self.win.stack.currentWidget()
        return getattr(w, "name", None) if hasattr(w, "load_older") else None

    def search_deeper(self):
        name = self._lane_name()
        query = self.edit.text()
        if not name or not query.strip():
            return
        before = set(self.hits)
        self.deeper.setEnabled(False)
        self.count.setText(_("find_searching"))

        def done(res):
            self.deeper.setEnabled(True)
            if not res["more"]:
                self.count.setText(_("find_archive_none") if not res["total"]
                                   else _("find_count", i=self.pos + 1, n=len(self.hits)))
                return
            # the lane grows when the core says so; then stand on the first new match
            QTimer.singleShot(400, lambda: self._after_deeper(before))
        self.win.bridge.call(self.win.core.deep_find(name, query), ok=done,
                             fail=lambda e: (self.deeper.setEnabled(True), self.win.error(e)))

    def _after_deeper(self, before):
        self.search(jump=False)
        fresh = [i for i, k in enumerate(self.hits) if k not in before]
        if fresh:
            # the new match closest to what was loaded before: with oldest first, older
            # posts came in above, so that's the last of them; newest first — the first
            oldest_first = self.win.cfg["feed"]["order"] == "oldest_first"
            self.pos = fresh[-1] if oldest_first else fresh[0]
            self._go()

    def _nearest(self, view):
        """The first hit from where the reader is now, not from the very top."""
        top = view.verticalScrollBar().value()
        keys = view.keys() if view.model else list(view.order)
        place = {k: i for i, k in enumerate(keys)}
        # the first built card still on screen, and its place among all of them
        here = next((place[k] for k in view.order if k in place and
                     view._top(view.rows[k]) + view.rows[k].height() > top), 0)
        for i, key in enumerate(self.hits):
            if place.get(key, -1) >= here:
                return i
        return 0

    def _go(self):
        key = self.hits[self.pos]
        self.view.scroll_to(key, "top")  # builds its card if it wasn't built yet
        self._mark(key)
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
        self.deeper.setVisible(bool(self._lane_name()) and bool(self.edit.text().strip()))
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
