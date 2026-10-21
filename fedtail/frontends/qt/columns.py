"""Lanes side by side, in columns (ui.layout = "columns", or ❯ next to the menu).

The lane widgets are the same ones the single view shows: switching moves them here and
back, with their cards, scroll positions and filters as they were."""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...i18n import _
from ..common.columns import DEFAULT, start_names  # noqa: F401  (Qt's names)

log = logging.getLogger("fedtail.qt")

class ColumnsArea(QScrollArea):
    """A row of columns; scrolls sideways when they don't fit. `name` and `view` are
    the column in focus, so the rest of the window treats it as the lane on screen."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("columns")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("columnsInner")
        self.row = QHBoxLayout(inner)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(1)
        self.setWidget(inner)
        self.frames = {}   # lane name -> its column frame
        self.order = []
        self.focused = None
        QApplication.instance().focusChanged.connect(self._focus_moved)

    # ---- what the window asks ---------------------------------------------------------
    @property
    def name(self):
        return self.focused

    @property
    def view(self):
        w = self.win.lane_widgets.get(self.focused)
        return getattr(w, "view", None)

    def names(self):
        return list(self.order)

    # ---- columns ------------------------------------------------------------------------
    def add(self, name, widget, at=None):
        if name in self.frames:
            return
        frame = QFrame()
        frame.setObjectName("column")
        frame.setMinimumWidth(self.win.cfg["ui"].get("column_width", 460))
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(6, 2, 6, 0)
        bar.setSpacing(2)
        for text, tip, fn in (("‹", _("column_left"), lambda n=name: self.move(n, -1)),
                              ("›", _("column_right"), lambda n=name: self.move(n, 1))):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addStretch(1)
        close = QToolButton()
        close.setText("✕")
        close.setToolTip(_("column_close"))
        close.setAutoRaise(True)
        close.clicked.connect(lambda _c=False, n=name: self.win.close_column(n))
        bar.addWidget(close)
        v.addLayout(bar)
        self._take(widget)
        v.addWidget(widget, 1)
        widget.show()
        self.frames[name] = frame
        at = len(self.order) if at is None else max(0, min(at, len(self.order)))
        self.order.insert(at, name)
        self.row.insertWidget(at, frame, 1)
        if self.focused is None:
            self.focused = name

    def _take(self, widget):
        """Out of the single view's stack, if it is there."""
        stack = self.win.stack
        if stack.indexOf(widget) >= 0:
            stack.removeWidget(widget)

    def drop(self, name):
        """The column goes; its lane widget is handed back (still alive)."""
        frame = self.frames.pop(name, None)
        if frame is None:
            return None
        self.order.remove(name)
        widget = self.win.lane_widgets.get(name)
        if widget is not None and widget.parent() is frame:
            widget.setParent(None)
        self.row.removeWidget(frame)
        frame.deleteLater()
        if self.focused == name:
            self.focused = self.order[0] if self.order else None
        return widget

    def move(self, name, step):
        if name not in self.order:
            return
        i = self.order.index(name)
        j = max(0, min(len(self.order) - 1, i + step))
        if i == j:
            return
        self.order.insert(j, self.order.pop(i))
        frame = self.frames[name]
        self.row.removeWidget(frame)
        self.row.insertWidget(j, frame, 1)
        self.win.columns_changed()

    def release(self):
        """All columns go; the lane widgets come back to the caller, alive."""
        try:
            QApplication.instance().focusChanged.disconnect(self._focus_moved)
        except (RuntimeError, TypeError):
            pass
        out = []
        for name in list(self.order):
            w = self.drop(name)
            if w is not None:
                out.append((name, w))
        return out

    def focus(self, name, keys=False):
        if name not in self.frames:
            return
        self.focused = name
        self.ensureWidgetVisible(self.frames[name], 0, 0)
        w = self.win.lane_widgets.get(name)
        if keys and getattr(w, "view", None) is not None:
            w.view.setFocus()  # j / k right away

    def _focus_moved(self, _old, new):
        """A click or Tab into a column makes it the one in focus (the sidebar follows)."""
        if new is None or not self.isVisible():
            return
        for name, frame in self.frames.items():
            if frame.isAncestorOf(new) and name != self.focused:
                self.focused = name
                self.win.column_focused(name)
                break
