"""The Qt side of diagnostics (see fedtail/diag.py): Qt's own messages go into
the log instead of the terminal, a watchdog notices a frozen window, and the
stats line gets widget and image-cache counts — the usual places where a
long-running Qt program leaks."""

import logging
from collections import Counter

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

    seconds = float(cfg["debug"]["watchdog_seconds"]) if diag.is_on() else 0
    dog = diag.Watchdog(seconds)
    beat = QTimer(app)
    beat.setInterval(1000)
    beat.timeout.connect(dog.beat)
    beat.start()
    dog.start()
    app.aboutToQuit.connect(dog.stop)

    # freezes too short for the watchdog: how long, and what the GUI thread was doing
    stall_ms = int(cfg["debug"].get("stall_ms", 0)) if diag.is_on() else 0
    meter = diag.StallMeter(stall_ms)
    if stall_ms:
        tick = QTimer(app)
        tick.setInterval(int(meter.interval * 1000))
        tick.timeout.connect(meter.tick)
        tick.start()
        meter.start()
        app.aboutToQuit.connect(meter.stop)
        diag.add_stats("freezes", meter.counts)

    # Qt's widgets may only be looked at from the GUI thread: it counts them on a timer
    # and the stats thread reads the last count (walking them from there could crash)
    seen = {}

    def count():
        with diag.busy("diag: count widgets"):
            views = [w.view for w in list(win.lane_widgets.values()) + win.extra_tabs()
                     if getattr(w, "view", None) is not None]
            widgets = QApplication.allWidgets()
            seen.update({"widgets": len(widgets),
                         "rows": sum(len(v.rows) for v in views),
                         "model": sum(len(v.model) for v in views),
                         "tabs": win.tabs.count(),
                         "images_mem": len(win.images.mem),
                         "images_mb": round(win.images.mem_bytes / 1024 / 1024, 1),
                         "images_waiting": len(win.images.waiting)})
            return widgets

    def census():
        widgets = count()
        if diag._state.get("census_on"):
            diag.census("qt_widgets", Counter(type(w).__name__ for w in widgets))

    count()
    every = QTimer(win)  # dies with the window it counts
    every.setInterval(30_000)
    every.timeout.connect(count)
    every.start()
    minutes = float(cfg["debug"].get("stats_minutes", 5))
    if minutes > 0 and diag.is_on():
        census_timer = QTimer(win)
        census_timer.setInterval(int(minutes * 60_000))
        census_timer.timeout.connect(census)
        census_timer.start()
        QTimer.singleShot(60_000, win, census)  # the baseline, once the window has settled
    win.widget_census = census  # the Debug menu: now
    diag.add_stats("qt", lambda: dict(seen))
    diag.add_stats("img", win.images.counts)
    return dog, beat
