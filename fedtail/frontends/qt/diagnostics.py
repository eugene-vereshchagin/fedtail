"""The Qt side of diagnostics (see fedtail/diag.py): Qt's own messages go into
the log instead of the terminal, a watchdog notices a frozen window, and the
stats line gets widget and image-cache counts — the usual places where a
long-running Qt program leaks."""

import logging

from PySide6.QtCore import QTimer, QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

from ... import diag

qtlog = logging.getLogger("fedtail.qt")
_LEVEL = {QtMsgType.QtDebugMsg: logging.DEBUG, QtMsgType.QtInfoMsg: logging.DEBUG,
          QtMsgType.QtWarningMsg: logging.WARNING, QtMsgType.QtCriticalMsg: logging.ERROR,
          QtMsgType.QtFatalMsg: logging.CRITICAL}
# known harmless chatter: into the log at debug level, never to the terminal
_QUIET = ("libpng warning", "propagateSizeHints", "QFont::setPointSizeF")


def _qt_message(kind, context, message):
    level = _LEVEL.get(kind, logging.WARNING)
    if any(q in message for q in _QUIET):
        level = logging.DEBUG
    cat = getattr(context, "category", "") or "qt"
    qtlog.log(level, "[%s] %s", cat, message)


def install(app, win, cfg):
    qInstallMessageHandler(_qt_message)

    seconds = float(cfg["debug"]["watchdog_seconds"])
    dog = diag.Watchdog(seconds)
    beat = QTimer(app)
    beat.setInterval(1000)
    beat.timeout.connect(dog.beat)
    beat.start()
    dog.start()
    app.aboutToQuit.connect(dog.stop)

    def counts():
        views = [w.view for w in list(win.lane_widgets.values()) + win.extra_tabs()
                 if getattr(w, "view", None) is not None]
        return {"widgets": len(QApplication.allWidgets()),
                "rows": sum(len(v.rows) for v in views),
                "tabs": win.tabs.count(),
                "images_mem": len(win.images.mem),
                "images_mb": round(win.images.mem_bytes / 1024 / 1024, 1),
                "images_waiting": len(win.images.waiting)}
    diag.add_stats("qt", counts)
    return dog, beat
