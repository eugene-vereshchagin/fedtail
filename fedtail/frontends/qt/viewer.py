"""Image viewer drawn over the main window (like Tuba), not as a separate window.

Fits the window; small pictures are enlarged up to ui.image_upscale times.
Double-click or Z: 100 % and back, drag to pan. ←/→/Space: flip.
O: open in the browser. S: save to the downloads folder (ui.save_dir) — or the
half-transparent buttons in the top right corner. Esc or a click on the dark
backdrop: close. The feed's small copy shows at once while the original loads; an
original that won't show says why (format, network), R asks again.
"""

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget

from ...i18n import _

FULL_SIDE = 8192
MARGIN = 24
CAPTION_H = 44
BUTTONS_CSS = """
QToolButton { background: rgba(0, 0, 0, 120); color: rgba(255, 255, 255, 210);
    border: 1px solid rgba(255, 255, 255, 60); border-radius: 8px; padding: 7px 14px; }
QToolButton:hover { background: rgba(255, 255, 255, 45); color: white;
    border-color: rgba(255, 255, 255, 140); }
"""


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
        self.buttons = QWidget(self)
        self.buttons.setStyleSheet(BUTTONS_CSS)
        row = QHBoxLayout(self.buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.btn_save = None
        if ctx.save_image:
            self.btn_save = self._button("⤓  " + _("viewer_save"), _("viewer_save_tip"),
                                         lambda: ctx.save_image(self.media[self.i]))
            row.addWidget(self.btn_save)
        row.addWidget(self._button("↗", _("open_browser") + " (O)",
                                   lambda: ctx.open_url(self.url())))
        row.addWidget(self._button("✕", _("close") + " (Esc)", self.close_viewer))
        self.setGeometry(window.rect())
        self.show()
        self.raise_()
        self.setFocus()
        self.load()

    def _button(self, text, tip, fn):
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # the keys stay with the viewer
        b.clicked.connect(fn)
        return b

    def resizeEvent(self, e):
        self.buttons.adjustSize()
        self.buttons.move(self.width() - self.buttons.width() - MARGIN, MARGIN)
        self.buttons.raise_()
        super().resizeEvent(e)

    # ---- content ------------------------------------------------------------------
    def url(self):
        m = self.media[self.i]
        return m.url or m.remote_url or m.preview

    def load(self, retry=False):
        self.pm = None
        self.preview = False   # what's shown is the small picture, the original is coming
        self.problem = ""      # why the original won't show, if it won't
        self.actual = False
        self.offset = QPointF()
        want = self.i
        self.update()
        m = self.media[self.i]
        if m.preview and m.preview != self.url():
            # the feed's small picture first (usually cached already), the original after
            self.ctx.images.get(m.preview, lambda pm, w=want: self._small(w, pm))
        self.ctx.images.get(self.url(), lambda pm, w=want: self._loaded(w, pm), FULL_SIDE,
                            failed=lambda w=want: self._failed(w), retry=retry)

    def _small(self, index, pm):
        if index == self.i and self.pm is None:
            self.pm, self.preview = pm, True
            self.update()

    def _loaded(self, index, pm):
        if index == self.i:
            self.pm, self.preview, self.problem = pm, False, ""
            self.update()

    def _failed(self, index):
        if index != self.i:
            return
        kind, detail = self.ctx.images.why.get(self.url(), ("network", ""))
        self.problem = _("viewer_format", kind=detail) if kind == "format" else \
            _("viewer_unreachable", err=detail or "?")
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
            p.drawText(self._area(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                       self.problem or _("loading"))
        else:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawPixmap(self.image_rect(), self.pm, QRectF(self.pm.rect()))
        m = self.media[self.i]
        n = f"{self.i + 1} / {len(self.media)}    " if len(self.media) > 1 else ""
        if self.pm is not None and (self.preview or self.problem):
            n += (self.problem or _("viewer_original_coming")) + "    "
        desc = m.alt.replace("\n", " ")
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
        elif k == Qt.Key.Key_R:  # the original again, now
            self.load(retry=True)
        elif k == Qt.Key.Key_O:
            self.ctx.open_url(self.url())
        elif k == Qt.Key.Key_S and self.ctx.save_image:
            self.ctx.save_image(self.media[self.i])
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
