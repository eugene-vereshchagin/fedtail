"""Full-size image viewer: ←/→ to flip, Esc or click to close, O for browser."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

from ...i18n import _

FULL_SIDE = 4096


class ImageViewer(QDialog):
    def __init__(self, parent, ctx, media, index=0):
        super().__init__(parent)
        self.ctx = ctx
        self.media = media
        self.i = index
        self.pm = None
        self.setWindowTitle(_("viewer_title"))
        self.setStyleSheet("QDialog { background: #000; } QLabel { color: #ccc; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        self.pic = QLabel(_("loading"))
        self.pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pic.setMinimumSize(1, 1)
        lay.addWidget(self.pic, 1)
        self.caption = QLabel()
        self.caption.setWordWrap(True)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.caption)
        for key, fn in (("Left", lambda: self.go(-1)), ("Right", lambda: self.go(1)),
                        ("Space", lambda: self.go(1)), ("Backspace", lambda: self.go(-1)),
                        ("O", self.open_browser)):
            QShortcut(QKeySequence(key), self).activated.connect(fn)
        screen = (parent.screen() if parent else self.screen()).availableGeometry()
        self.resize(int(screen.width() * 0.9), int(screen.height() * 0.9))
        self.show_current()

    def url(self):
        m = self.media[self.i]
        return m.get("url") or m.get("remote_url") or m.get("preview_url") or ""

    def show_current(self):
        m = self.media[self.i]
        self.pm = None
        self.pic.setText(_("loading"))
        n = f"{self.i + 1} / {len(self.media)}   " if len(self.media) > 1 else ""
        desc = m.get("description") or ""
        self.caption.setText(n + desc + "   " + _("viewer_keys"))
        want = self.i
        self.ctx.images.get(self.url(), lambda pm, w=want: self._loaded(w, pm), FULL_SIDE)

    def _loaded(self, index, pm):
        if index != self.i:
            return
        self.pm = pm
        self._fit()

    def _fit(self):
        if self.pm is None:
            return
        size = self.pic.size()
        if self.pm.width() <= size.width() and self.pm.height() <= size.height():
            self.pic.setPixmap(self.pm)  # never upscale
        else:
            self.pic.setPixmap(self.pm.scaled(size, Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def go(self, step):
        if len(self.media) > 1:
            self.i = (self.i + step) % len(self.media)
            self.show_current()

    def open_browser(self):
        self.ctx.open_url(self.url())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.accept()
        super().mouseReleaseEvent(e)
