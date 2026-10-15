"""Image viewer drawn over the main window (like Tuba), not as a separate window.

Fits the window; small pictures are enlarged up to ui.image_upscale times.
Double-click or Z: 100 % and back, drag to pan. ←/→/Space: flip.
O: open in the browser. Esc or a click on the dark backdrop: close.
"""

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget

from ...i18n import _

FULL_SIDE = 8192
MARGIN = 24
CAPTION_H = 44


class ImageOverlay(QWidget):
    def __init__(self, window, ctx, media, index=0):
        super().__init__(window)
        self.win = window
        self.ctx = ctx
        self.media = media
        self.i = index
        self.pm = None
        self.actual = False      # 100 % instead of fit
        self.offset = QPointF()  # pan in 100 % mode
        self._press = None
        self._moved = False
        self.upscale = float(ctx.cfg["ui"]["image_upscale"])
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        # a single click closes, unless it turns out to be a double click
        self._click = QTimer(self, singleShot=True)
        self._click.timeout.connect(self.close_viewer)
        window.installEventFilter(self)
        self.setGeometry(window.rect())
        self.show()
        self.raise_()
        self.setFocus()
        self.load()

    # ---- content ------------------------------------------------------------------
    def url(self):
        m = self.media[self.i]
        return m.get("url") or m.get("remote_url") or m.get("preview_url") or ""

    def load(self):
        self.pm = None
        self.actual = False
        self.offset = QPointF()
        want = self.i
        self.update()
        self.ctx.images.get(self.url(), lambda pm, w=want: self._loaded(w, pm), FULL_SIDE)

    def _loaded(self, index, pm):
        if index == self.i:
            self.pm = pm
            self.update()

    def go(self, step):
        if len(self.media) > 1:
            self.i = (self.i + step) % len(self.media)
            self.load()

    def close_viewer(self):
        self.win.removeEventFilter(self)
        self.hide()
        self.deleteLater()

    # ---- geometry -----------------------------------------------------------------
    def eventFilter(self, obj, e):
        if obj is self.win and e.type() == QEvent.Type.Resize:
            self.setGeometry(self.win.rect())
        return False

    def _area(self):
        return QRectF(MARGIN, MARGIN, self.width() - 2 * MARGIN,
                      self.height() - 2 * MARGIN - CAPTION_H)

    def image_rect(self):
        area = self._area()
        pw, ph = self.pm.width(), self.pm.height()
        if self.actual:
            scale = 1.0
        else:
            scale = min(area.width() / pw, area.height() / ph, self.upscale)
        tw, th = pw * scale, ph * scale
        x = area.x() + (area.width() - tw) / 2 + self.offset.x()
        y = area.y() + (area.height() - th) / 2 + self.offset.y()
        return QRectF(x, y, tw, th)

    # ---- painting -------------------------------------------------------------------
    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 215))
        p.setPen(QColor("#ddd"))
        if self.pm is None:
            p.drawText(self._area(), Qt.AlignmentFlag.AlignCenter, _("loading"))
        else:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawPixmap(self.image_rect(), self.pm, QRectF(self.pm.rect()))
        m = self.media[self.i]
        n = f"{self.i + 1} / {len(self.media)}    " if len(self.media) > 1 else ""
        desc = (m.get("description") or "").replace("\n", " ")
        cap = QRectF(MARGIN, self.height() - MARGIN - CAPTION_H, self.width() - 2 * MARGIN,
                     CAPTION_H)
        p.drawText(cap, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop |
                   Qt.TextFlag.TextWordWrap, n + desc)
        f = QFont(self.font())
        f.setPointSizeF(f.pointSizeF() * 0.85)
        p.setFont(f)
        p.setPen(QColor("#888"))
        p.drawText(cap, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                   _("viewer_keys"))

    # ---- input ------------------------------------------------------------------------
    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self.close_viewer()
        elif k in (Qt.Key.Key_Right, Qt.Key.Key_Space, Qt.Key.Key_PageDown):
            self.go(1)
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_Backspace, Qt.Key.Key_PageUp):
            self.go(-1)
        elif k == Qt.Key.Key_Z:
            self.toggle_actual()
        elif k == Qt.Key.Key_O:
            self.ctx.open_url(self.url())
        else:
            super().keyPressEvent(e)

    def toggle_actual(self):
        if self.pm is not None:
            self.actual = not self.actual
            self.offset = QPointF()
            self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.position()
            self._moved = False

    def mouseMoveEvent(self, e):
        if self._press is not None and self.actual:
            d = e.position() - self._press
            if abs(d.x()) + abs(d.y()) > 3:
                self._moved = True
            self.offset += d
            self._press = e.position()
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self._moved:
            on_image = self.pm is not None and self.image_rect().contains(e.position())
            if not on_image or not self.actual:
                self._click.start(250)
        self._press = None

    def mouseDoubleClickEvent(self, _e):
        self._click.stop()
        self.toggle_actual()

    def wheelEvent(self, e):
        self.go(-1 if e.angleDelta().y() > 0 else 1)
