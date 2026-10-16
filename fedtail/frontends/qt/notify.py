"""Desktop notifications.

KDE (and any freedesktop desktop) shows them through notify-send, with an
"Open" button that brings fedtail up on the right lane or thread. Without
notify-send the tray balloon is used.
"""

import logging
import shutil
import subprocess
import threading
from importlib import resources

from PySide6.QtCore import QObject, Signal

from ...i18n import _
from .. import notifytext

log = logging.getLogger(__name__)


_themed = None  # the icon drawn in the current theme's colours, set at start-up


def icon_path():
    """The icon for the window, tray and notifications: the theme's own, or the
    standard one."""
    return _themed or str(resources.files("fedtail").joinpath("data/icons/fedtail.svg"))


def use_theme_icon(theme, folder):
    """Draw the icon in the theme's colours into folder/icon-<theme>.svg."""
    global _themed
    from .. import iconart
    c = iconart.colors(theme.icon, theme.c["accent"].name(), theme.c["hot"].name())
    path = folder / f"icon-{theme.id}.svg"
    text = iconart.svg(c)
    try:
        if not path.exists() or path.read_text("utf-8") != text:
            path.write_text(text, "utf-8")
        _themed = str(path)
    except OSError as e:
        log.warning("themed icon: %s", e)
    return icon_path()


class Notifier(QObject):
    clicked = Signal(object)  # the Note whose "Open" was pressed

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.cfg = win.cfg["notify"]
        backend = self.cfg["backend"]
        self.notify_send = shutil.which("notify-send")
        if backend == "auto":
            backend = "desktop" if self.notify_send else "tray"
        self.backend = backend
        self._tray_note = None
        if win.tray:
            win.tray.messageClicked.connect(
                lambda: self._tray_note and self.clicked.emit(self._tray_note))

    def notify(self, items):
        """items: [(lane, status or account)] from the core."""
        if not self.cfg["enabled"] or not items:
            return
        if self.win.isActiveWindow() and not self.cfg["when_focused"]:
            return
        for note in notifytext.build(items, self.cfg["privacy"], self.win.lane_title):
            self._show(note)

    def _show(self, note):
        if self.backend == "desktop" and self.notify_send:
            threading.Thread(target=self._desktop, args=(note,), daemon=True).start()
        elif self.win.tray:
            self._tray_note = note
            self.win.tray.showMessage(note.title, note.body, self.win.windowIcon(), 8000)

    def _desktop(self, note):
        base = [self.notify_send, "--app-name=fedtail", f"--icon={icon_path()}",
                "--hint=string:desktop-entry:fedtail", "--category=im.received"]
        try:
            # with --wait, notify-send prints the chosen action when "Open" is pressed
            r = subprocess.run(base + [f"--action=open={_('open_action')}", "--wait",
                                       note.title, note.body],
                               capture_output=True, text=True, timeout=600)
            if r.returncode != 0 and "action" in (r.stderr or ""):
                # an old notify-send without actions: show it plainly
                subprocess.run(base + [note.title, note.body], timeout=30)
                return
            if r.stdout.strip() == "open":
                self.clicked.emit(note)
        except (OSError, subprocess.SubprocessError) as e:
            log.warning("notify-send failed: %s", e)
