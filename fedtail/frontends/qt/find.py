"""Ctrl+F: find in the lane, thread or profile that is open, like in a browser — or,
with "in every lane" ticked, in everything stored for every lane: ↓ / Enter / Ctrl+F
again goes to the next match, into another lane when that's where it is."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from ...i18n import _
from ..common import find as rules


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
        self.everywhere = QCheckBox(_("find_everywhere"))
        self.everywhere.setObjectName("check")
        self.everywhere.setToolTip(_("find_everywhere_tip"))
        self.everywhere.setChecked(bool(win.core.choice("find.everywhere", False)))
        self.everywhere.toggled.connect(self._everywhere_toggled)
        lay.addWidget(self.everywhere)
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
        # "in every lane": [{"lane", "item", "status_id", "index"}] from the core
        self.all_hits, self.all_pos, self._all_query, self._req = None, -1, None, 0
        self._moving = False  # switching lanes ourselves: not "the reader went elsewhere"
        self._timer = QTimer(self, singleShot=True, interval=200)
        self._timer.timeout.connect(lambda: self.search(jump=True))
        self.edit.textChanged.connect(lambda _t: self._timer.start())
        self.hide()

    # ---- public ---------------------------------------------------------------------
    def open(self):
        if self.isVisible() and self.edit.hasFocus() and self.edit.text().strip():
            self.step(1)  # Ctrl+F once more, as in a browser's bar: the next match
            return
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
        if self._moving:
            return
        if self.isVisible() and self.everywhere.isChecked():
            self._mark(None)  # the matches stay; the current one is marked if it's here
            self.view = self.win.current_view()
            hit = self._all_hit()
            if hit and hit["lane"] == self._lane_name():
                self._mark(self._key_in_view(hit))
            return
        if self.isVisible():
            self._mark(None)
            self.search(jump=True)

    def step(self, delta):
        if not self.isVisible():
            self.open()
            return
        if self.everywhere.isChecked():
            if self.all_hits is None or self._all_query != self.edit.text():
                self._search_all(jump=True)
            elif self.all_hits:
                self.all_pos = rules.step(self.all_pos, len(self.all_hits), delta)
                self._go_all()
            return
        self.search(jump=False)  # the view may have changed since
        if not self.hits:
            return
        self.pos = rules.step(self.pos, len(self.hits), delta)
        self._go()

    # ---- searching -------------------------------------------------------------------
    def search(self, jump):
        if self.everywhere.isChecked():
            self._search_all(jump)
            return
        view = self.win.current_view()
        if view is not self.view:
            self._mark(None)
            self.view, self.pos = view, -1
        query = self.edit.text()
        old = self.hits[self.pos] if 0 <= self.pos < len(self.hits) else None
        self.hits = []
        if view is not None:
            # every post of the lane, also those whose cards aren't built yet
            self.hits = rules.hits(view.model or [view.rows[k].spec for k in view.order],
                                   query)
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

    # ---- in every lane ----------------------------------------------------------------
    def _everywhere_toggled(self, on):
        self.win.core.set_choice("find.everywhere", bool(on))
        self._mark(None)
        self.all_hits, self.all_pos, self._all_query = None, -1, None
        self.hits, self.pos = [], -1
        if self.isVisible():
            self.search(jump=True)

    def _all_hit(self):
        if self.all_hits and 0 <= self.all_pos < len(self.all_hits):
            return self.all_hits[self.all_pos]
        return None

    def _search_all(self, jump):
        query = self.edit.text()
        self._req += 1
        req = self._req
        if not query.strip():
            self._mark(None)
            self.all_hits, self.all_pos, self._all_query = None, -1, None
            self._show_count()
            return
        if query == self._all_query and self.all_hits is not None:
            self._show_count()  # the same words: the matches found stay
            return
        self.count.setText(_("find_searching"))

        def got(res, query=query):
            if req != self._req:  # typed on meanwhile
                return
            here = set(getattr(self.win, "lane_items", {}))
            self.all_hits = [h for h in res if h["lane"] in here]
            self._all_query, self.all_pos = query, -1
            if not self.all_hits:
                self._mark(None)
                self._show_count()
                return
            # first the matches in the lane on screen, from where the reader is
            lane = self._lane_name()
            mine = [i for i, h in enumerate(self.all_hits) if h["lane"] == lane]
            self.all_pos = mine[0] if mine else 0
            if jump:
                self._go_all()
            else:
                self._show_count()
        self.win.bridge.call(self.win.core.find_everywhere(query), ok=got,
                             fail=self.win.error)

    def _key_in_view(self, hit):
        """The card key of a match in the view on screen: the item itself, or (posts
        gathered into conversations) whatever card shows that post."""
        view = self.view
        if view is None:
            return None
        if view.has(hit["item"]):
            return hit["item"]
        want = {hit["status_id"]}
        for spec in view.model or [view.rows[k].spec for k in view.order]:
            if spec.entry is not None and (spec.entry.id in want or spec.post.id in want):
                return spec.key
        return None

    def _go_all(self):
        hit = self._all_hit()
        if hit is None:
            return
        name = hit["lane"]
        self._mark(None)
        if name != self._lane_name():
            self._moving = True
            try:
                self.win.select_lane(name)
            finally:
                self._moving = False
        w = self.win.lane_widgets.get(name)
        if w is None:
            return
        self.view = w.view
        if self.win.core.reveal_in_lane(name, hit["index"]) or \
                self._key_in_view(hit) is None:
            w.refresh(force=True)  # loaded down to the match, or drawn at all
            self.view = w.view
        key = self._key_in_view(hit)
        if key is not None:
            self.view.scroll_to(key, "top")
            self._mark(key)
            # a lane just opened may still settle on its own reading place: be firm
            QTimer.singleShot(150, self, lambda h=hit, k=key: self._settle(h, k))
        self._show_count()

    def _settle(self, hit, key):
        if self._all_hit() is hit and self.view is not None and self.view.has(key):
            self.view.scroll_to(key, "top")
            self._mark(key)

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
            QTimer.singleShot(400, self, lambda: self._after_deeper(before))
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
        """The match's card marked "found": the view keeps the mark (and the card built)
        while it is the one shown, whatever the scrolling builds and lets go."""
        if self.view is None:
            return
        mark = getattr(self.view, "mark_found", None)
        if mark is not None:
            mark(key)
            return
        for k, row in self.view.rows.items():  # a list that isn't a FeedView
            card = getattr(row, "card", None)
            if card is None:
                continue
            want = "true" if k == key else "false"
            if card.property("found") != want:
                card.setProperty("found", want)
                card.style().unpolish(card)
                card.style().polish(card)

    def _show_count(self):
        everywhere = self.everywhere.isChecked()
        self.deeper.setVisible(not everywhere and bool(self._lane_name()) and
                               bool(self.edit.text().strip()))
        if everywhere:
            hit = self._all_hit()
            text, over = rules.count_text(
                self.edit.text(), self.all_pos, len(self.all_hits or []),
                self.win.lane_title(hit["lane"]) if hit else "", everywhere=True,
                searched=self.all_hits is not None)
        else:
            text, over = rules.count_text(self.edit.text(), self.pos, len(self.hits))
        self.count.setText(text)
        self.count.setProperty("over", "true" if over else "false")
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
