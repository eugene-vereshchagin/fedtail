"""The unread count on the icon: drawn into the tray icon, and sent to the task bar
the way KDE Plasma (and Unity, Dash to Dock…) listen for it — the
com.canonical.Unity.LauncherEntry D-Bus signal, keyed by the .desktop file."""

import logging

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

log = logging.getLogger(__name__)

SIZE = 64  # the tray scales it down; drawn big, it stays sharp


def text(n):
    return "" if n <= 0 else ("99+" if n > 99 else str(n))


def icon_with_count(base, n, bg="#d0402b", fg="#ffffff"):
    """base QIcon with a round badge holding n in the lower right corner; n <= 0 → base."""
    label = text(n)
    if not label:
        return base
    pix = base.pixmap(SIZE, SIZE)
    if pix.isNull():
        pix = QPixmap(SIZE, SIZE)
        pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    h = SIZE * 0.56
    w = max(h, h * (0.42 + 0.3 * len(label)))
    r = QRectF(SIZE - w, SIZE - h, w, h)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(bg))
    p.drawRoundedRect(r, h / 2, h / 2)
    f = QFont()
    f.setBold(True)
    f.setPixelSize(int(h * (0.72 if len(label) == 1 else 0.6)))
    p.setFont(f)
    p.setPen(QColor(fg))
    p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)
    p.end()
    return QIcon(pix)


class Launcher:
    """The count on the task bar button. Needs QtDBus (Debian:
    python3-pyside6.qtdbus) and the menu entry from --install-desktop; without
    either it quietly does nothing (and says once in the log why)."""

    def __init__(self, desktop_id):
        self.uri = f"application://{desktop_id}.desktop"
        self.last = None
        self.bus = None
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusMessage
        except ImportError:
            log.info("no QtDBus: the task bar shows no count (python3-pyside6.qtdbus)")
            return
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            log.info("no D-Bus session: the task bar shows no count")
            return
        self.bus, self._msg = bus, QDBusMessage

    def set(self, n):
        if self.bus is None or n == self.last:
            return
        self.last = n
        msg = self._msg.createSignal("/fedtail", "com.canonical.Unity.LauncherEntry",
                                     "Update")
        msg.setArguments([self.uri, {"count": max(n, 0), "count-visible": n > 0}])
        if not self.bus.send(msg):
            log.warning("task bar count not sent: %s", self.bus.lastError().message())
        else:
            log.debug("task bar count %d", n)
