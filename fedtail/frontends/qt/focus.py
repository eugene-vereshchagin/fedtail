"""A picture's description and focus point, before it is sent.

The focus point (Mastodon: x, y in -1…1, y up) tells every app that crops a
preview which part to keep. A click on the picture puts a cross there; "Centre"
takes it away (the default: the middle)."""

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ...i18n import _
from ..common.focus import from_focus, to_focus  # noqa: F401 — (used here, and by tests)

SIDE = 360


class _Picture(QLabel):
    clicked = Signal(float, float)

    def mousePressEvent(self, e):  # noqa: N802 — Qt's name
        p = e.position()
        self.clicked.emit(p.x(), p.y())


class FocusDialog(QDialog):
    def __init__(self, parent, path, description="", focus=None, with_focus=True):
        super().__init__(parent)
        self.setWindowTitle(_("alt_title"))
        self.focus = list(focus) if focus else None
        lay = QVBoxLayout(self)
        self.picture = None
        if with_focus:
            src = QPixmap(path)
            if not src.isNull():
                self.src = src.scaled(SIDE, SIDE, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
                self.picture = _Picture()
                self.picture.setFixedSize(self.src.size())
                self.picture.setCursor(Qt.CursorShape.CrossCursor)
                self.picture.setToolTip(_("focus_tip"))
                self.picture.clicked.connect(self._clicked)
                lay.addWidget(self.picture, 0, Qt.AlignmentFlag.AlignHCenter)
                row = QHBoxLayout()
                self.where = QLabel()
                self.where.setObjectName("muted")
                row.addWidget(self.where, 1)
                centre = QPushButton(_("focus_centre"))
                centre.setObjectName("tool")
                centre.clicked.connect(self._centre)
                row.addWidget(centre)
                lay.addLayout(row)
                self._draw()
        lay.addWidget(QLabel(_("alt_prompt")))
        self.text = QPlainTextEdit(description)
        self.text.setMinimumHeight(90)
        lay.addWidget(self.text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.text.setFocus()

    def description(self):
        return self.text.toPlainText().strip()

    def _clicked(self, x, y):
        self.focus = list(to_focus(x, y, self.src.width(), self.src.height()))
        self._draw()

    def _centre(self):
        self.focus = None
        self._draw()

    def _draw(self):
        pm = QPixmap(self.src)
        if self.focus:
            x, y = from_focus(self.focus, pm.width(), pm.height())
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            for color, width in ((QColor(0, 0, 0, 170), 4), (QColor("white"), 2)):
                p.setPen(QPen(color, width))
                p.drawEllipse(QPointF(x, y), 12, 12)
                p.drawLine(QPointF(x - 20, y), QPointF(x + 20, y))
                p.drawLine(QPointF(x, y - 20), QPointF(x, y + 20))
            p.end()
            self.where.setText(_("focus_at", x=f"{self.focus[0]:+.2f}", y=f"{self.focus[1]:+.2f}"))
        else:
            self.where.setText(_("focus_none"))
        self.picture.setPixmap(pm)
