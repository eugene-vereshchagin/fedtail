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

_translators = []


def translate_qt(app):
    """Qt's own words in the interface's language: the standard buttons (Close,
    Cancel, OK), the context menus of text fields — English in a Russian window
    before. From Qt's translations (the wheel brings them; Debian:
    qt6-translations-l10n); none there — English, as before."""
    from PySide6.QtCore import QLibraryInfo, QTranslator

    from ... import i18n
    lang = i18n.current_language()
    if lang == "en" or _translators:
        return
    where = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for name in ("qtbase", "qt"):
        t = QTranslator(app)
        if t.load(f"{name}_{lang}", where):
            app.installTranslator(t)
            _translators.append(t)
            return
    logging.getLogger("fedtail").info("no Qt translations for %s in %s", lang, where)


def run(core, instance, argv):
    import os
    if QApplication.instance() is None and \
            os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
        # left over from running the tests in the same terminal (they set it): the window
        # would be drawn nowhere — fedtail "started" and nothing showed (Windows, 22.10)
        del os.environ["QT_QPA_PLATFORM"]
        print("fedtail: QT_QPA_PLATFORM=offscreen in this terminal (from the tests?) — "
              "ignored, or the window would be invisible", file=sys.stderr)
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("fedtail")
    translate_qt(app)
    from ...desktop import desktop_id
    app.setDesktopFileName(desktop_id(core.paths.profile))
    app.setQuitOnLastWindowClosed(False)
    theme = themes.apply(app, core.cfg)
    notify.set_style(core.cfg["ui"].get("app_icon", "possum"))
    if core.cfg["ui"]["themed_icon"] and core.cfg["ui"].get("app_icon") == "bubble":
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
    def message(msg):
        if msg.startswith("open "):
            bridge.open_requested.emit(msg[5:].strip())
        else:
            bridge.raise_requested.emit()
    instance.listen(message)
    url = getattr(core, "open_at_start", None)
    if url:
        win.open_when_ready(url)

    # Ctrl+C in the terminal, and the session ending (SIGTERM at logout or shutdown):
    # quit as from the menu — the window's place, the read marks, the drafts kept
    signal.signal(signal.SIGINT, lambda *_: win.quit())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: win.quit())
    tick = QTimer()  # Python's signal handlers run only when Python does: once a second
    tick.start(1000)
    tick.timeout.connect(lambda: None)

    if win.roster is not None:
        # the split layout starts with the roster only: the messages window comes
        # when something in it is opened
        win.roster.show()
        win.roster.refresh_soon()
    else:
        win.show()
    QTimer.singleShot(1500, win, lambda: _log_size(win))
    QTimer.singleShot(0, win.start)
    try:
        return app.exec()
    finally:
        win.drop_tray()  # however the loop ended: no icon left behind on Windows
        app.processEvents()
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
