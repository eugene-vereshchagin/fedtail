"""Qt Widgets frontend (PySide6)."""

import logging
import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import notify
from . import theme as themes
from .bridge import Bridge
from .window import MainWindow


def run(core, instance, argv):
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("fedtail")
    from ...desktop import desktop_id
    app.setDesktopFileName(desktop_id(core.paths.profile))
    app.setQuitOnLastWindowClosed(False)
    theme = themes.apply(app, core.cfg)
    if core.cfg["ui"]["themed_icon"]:
        notify.use_theme_icon(theme, core.paths.cache_dir)
    app.setWindowIcon(QIcon(notify.icon_path()))

    bridge = Bridge(core)
    win = MainWindow(core, bridge, theme)
    # Qt messages into the log, a watchdog for a frozen window, widget counts
    from . import diagnostics
    keep = diagnostics.install(app, win, core.cfg)  # noqa: F841 — the timer must live
    from PySide6 import __version__ as pyside
    from PySide6.QtCore import qVersion
    screen = app.primaryScreen()
    logging.getLogger("fedtail").info(
        "Qt %s, PySide6 %s, platform %s, style %s, theme %s, font %s %gpt, screen %s "
        "dpr %g dpi %.0f, %s", qVersion(), pyside, app.platformName(),
        app.style().metaObject().className(), core.cfg["ui"]["theme"], app.font().family(),
        app.font().pointSizeF(), screen.name() if screen else "-",
        screen.devicePixelRatio() if screen else 0, screen.logicalDotsPerInch() if screen else 0,
        "one-file build" if getattr(sys, "frozen", False) else "from source")
    instance.listen(lambda _msg: bridge.raise_requested.emit())

    # Ctrl+C in the terminal should quit, not be swallowed by the Qt loop
    signal.signal(signal.SIGINT, lambda *_: win.quit())
    tick = QTimer()
    tick.start(500)
    tick.timeout.connect(lambda: None)

    win.show()
    QTimer.singleShot(1500, lambda: _log_size(win))
    QTimer.singleShot(0, win.start)
    try:
        return app.exec()
    finally:
        win.images.shutdown()
        core.shutdown()


def _log_size(win):
    """What the window ended up as, and what keeps it from being narrower: a window
    that "always opens too wide" has some widget asking for that width."""
    from PySide6.QtWidgets import QWidget
    try:
        hint = win.minimumSizeHint()
        wide = sorted(((w.minimumSizeHint().width(), w.metaObject().className(),
                        w.objectName()) for w in win.findChildren(QWidget)
                       if w.isVisible()), reverse=True)[:5]
        logging.getLogger("fedtail").info(
            "window %dx%d, needs at least %dx%d; widest: %s", win.width(), win.height(),
            hint.width(), hint.height(),
            ", ".join(f"{cls}#{name or '-'} {w}px" for w, cls, name in wide))
    except RuntimeError:
        pass


if __name__ == "__main__":
    sys.exit("run fedtail with:  python3 -m fedtail")
