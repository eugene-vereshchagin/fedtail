""""Loading…" with the swinging opossum beside it (ui.app_icon = "possum"; the bubble
style — the words alone): over a lane being drawn, in a thread waiting for its replies.
The sticker swings while the plate is shown and stops when it hides."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

SIDE = 36  # the sticker's size on the plate, px


class LoadingPlate(QFrame):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setObjectName("loadingPlate")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 6, 18, 6)
        lay.setSpacing(10)
        self.movie = None
        self.pic = QLabel()
        self.pic.setFixedSize(QSize(SIDE, SIDE))
        from . import notify as notify_module
        if notify_module.possum_style():
            from PySide6.QtGui import QMovie
            self.movie = QMovie(notify_module.swing_path(), parent=self)
            self.movie.setScaledSize(QSize(SIDE, SIDE))
            self.movie.setCacheMode(QMovie.CacheMode.CacheAll)
            self.pic.setMovie(self.movie)
            lay.addWidget(self.pic, 0, Qt.AlignmentFlag.AlignVCenter)
        self.words = QLabel(text)
        self.words.setObjectName("loadingWords")
        lay.addWidget(self.words, 0, Qt.AlignmentFlag.AlignVCenter)

    def setText(self, text):  # noqa: N802 — the QLabel it stands in for had it
        self.words.setText(text)
        self.adjustSize()

    def text(self):
        return self.words.text()

    def showEvent(self, e):  # noqa: N802
        if self.movie is not None:
            self.movie.start()
        super().showEvent(e)

    def hideEvent(self, e):  # noqa: N802
        if self.movie is not None:
            self.movie.stop()
        super().hideEvent(e)
