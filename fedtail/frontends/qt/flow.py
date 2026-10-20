"""A layout that lays its widgets in a row and wraps to the next line when the row
is full — buttons keep their natural width instead of being squeezed and cut."""

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout


class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing=6, justify=False):
        super().__init__(parent)
        self._items = []
        self._gap = spacing
        # justify: once they take more than a row, every full row is stretched to the
        # edge (the Mail.ru Agent's tabs); the last one keeps its natural widths
        self._justify = justify
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):  # noqa: N802 — Qt's name
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):  # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, width):  # noqa: N802
        return self._lay_out(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._lay_out(rect, apply=True)

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
        # the widest item, not all of them side by side: more items wrap, the window
        # around never has to grow for them
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _lay_out(self, rect, apply):
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        rows, row, x = [], [], r.x()
        for item in self._items:
            if item.widget() is not None and item.widget().isHidden():
                continue
            hint = item.sizeHint()
            if row and x + hint.width() > r.right() + 1:
                rows.append(row)
                row, x = [], r.x()
            row.append((item, hint))
            x += hint.width() + self._gap
        if row:
            rows.append(row)
        y = r.y()
        for n, row in enumerate(rows):
            extra = 0
            if self._justify and len(rows) > 1 and n < len(rows) - 1:
                used = sum(h.width() for _i, h in row) + self._gap * (len(row) - 1)
                extra = max(0, r.width() - used) / len(row)
            x, line = float(r.x()), 0
            for item, hint in row:
                w = hint.width() + extra
                if apply:
                    item.setGeometry(QRect(QPoint(round(x), y), QSize(round(w), hint.height())))
                x += w + self._gap
                line = max(line, hint.height())
            y += line + self._gap
        return (y - self._gap if rows else y) - rect.y() + m.bottom()
