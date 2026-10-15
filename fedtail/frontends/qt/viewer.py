"""Full-size image viewer.

Fits the window (never upscales). Double-click or Z: 100 % and back; in 100 %
drag to pan. ←/→/Space: flip. F: full screen. O: open in the browser.
Esc or a single click: close.
"""

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import QDialog, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ...i18n import _

FULL_SIDE = 8192


class Canvas(QWidget):
    """Draws the pixmap scaled to whatever size the window has right now.
    (A QLabel would instead grow the window to the size of the picture.)"""

    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.pm = None
        self.actual = False      # 100 % instead of fit
        self.offset = QPointF()  # pan in 100 % mode
        self._press = None
        self._moved = False
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMouseTracking(False)
        # a single click closes, but only if no double click follows
        self._click = QTimer(self, singleShot=True)
        self._click.timeout.connect(viewer.accept)

    def set_pixmap(self, pm):
        self.pm = pm
        self.actual = False
        self.offset = QPointF()
        self.update()

    def _target(self):
        w, h = self.width(), self.height()
        pw, ph = self.pm.width(), self.pm.height()
        if self.actual:
            scale = 1.0
        else:
            scale = min(1.0, w / pw, h / ph)
        tw, th = pw * scale, ph * scale
        x = (w - tw) / 2 + self.offset.x()
        y = (h - th) / 2 + self.offset.y()
        return QRectF(x, y, tw, th)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#000"))
        if self.pm is None:
            p.setPen(QColor("#888"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, _("loading"))
            return
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(self._target(), self.pm, QRectF(self.pm.rect()))

    def toggle_actual(self):
        if self.pm is not None:
            self.actual = not self.actual
            self.offset = QPointF()
            self.setCursor(Qt.CursorShape.OpenHandCursor if self.actual
                           else Qt.CursorShape.ArrowCursor)
            self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.position()
            self._moved = False

    def mouseMoveEvent(self, e):
        if self._press is None or not self.actual:
            return
        d = e.position() - self._press
        if abs(d.x()) + abs(d.y()) > 3:
            self._moved = True
        self.offset += d
        self._press = e.position()
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self._moved:
            self._click.start(250)
        self._press = None

    def mouseDoubleClickEvent(self, e):
        self._click.stop()
        self.toggle_actual()


class ImageViewer(QDialog):
    def __init__(self, parent, ctx, media, index=0):
        super().__init__(parent)
        self.ctx = ctx
        self.media = media
        self.i = index
        self.setWindowTitle(_("viewer_title"))
        self.setStyleSheet("QDialog { background: #000; } QLabel { color: #bbb; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 6)
        lay.setSpacing(4)
        self.canvas = Canvas(self)
        lay.addWidget(self.canvas, 1)
        self.caption = QLabel()
        self.caption.setWordWrap(True)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.caption)
        for key, fn in (("Left", lambda: self.go(-1)), ("Right", lambda: self.go(1)),
                        ("Space", lambda: self.go(1)), ("Backspace", lambda: self.go(-1)),
                        ("O", self.open_browser), ("F", self.toggle_full),
                        ("Z", self.canvas.toggle_actual)):
            QShortcut(QKeySequence(key), self).activated.connect(fn)
        screen = (parent.screen() if parent else self.screen()).availableGeometry()
        self.resize(int(screen.width() * 0.9), int(screen.height() * 0.9))
        self.move(screen.center() - QPoint(self.width() // 2, self.height() // 2))
        self.show_current()

    def url(self):
        m = self.media[self.i]
        return m.get("url") or m.get("remote_url") or m.get("preview_url") or ""

    def show_current(self):
        m = self.media[self.i]
        self.canvas.set_pixmap(None)
        n = f"{self.i + 1} / {len(self.media)}   " if len(self.media) > 1 else ""
        self.caption.setText(n + (m.get("description") or "") + "   " + _("viewer_keys"))
        want = self.i
        self.ctx.images.get(self.url(), lambda pm, w=want: self._loaded(w, pm), FULL_SIDE)

    def _loaded(self, index, pm):
        if index == self.i:
            self.canvas.set_pixmap(pm)

    def go(self, step):
        if len(self.media) > 1:
            self.i = (self.i + step) % len(self.media)
            self.show_current()

    def toggle_full(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def open_browser(self):
        self.ctx.open_url(self.url())
