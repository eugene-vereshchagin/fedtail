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
    """Shows notes from the core's "notify" event. Backends: "desktop" (notify-send,
    the freedesktop way: KDE shows them as its own, with an Open button) and
    "tray" (the tray icon's balloon). Every decision is logged, so "I got no
    notification" can be answered from the log."""

    clicked = Signal(object)  # the Note whose "Open" was pressed
    failed = Signal(str)      # notify-send didn't work: tell the user once

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.cfg = win.cfg["notify"]
        self.notify_send = shutil.which("notify-send")
        wanted = self.cfg["backend"]
        if wanted == "auto":
            self.backend = "desktop" if self.notify_send else "tray"
        else:
            self.backend = wanted
        self.problem = ""
        if self.backend == "desktop" and not self.notify_send:
            self.problem = _("notify_no_send")
            self.backend = "tray"
        elif wanted == "auto" and not self.notify_send:
            self.problem = _("notify_no_send")
        if self.backend == "tray" and not win.tray:
            self.problem = _("notify_nothing")
        log.info("notifications: %s (notify-send: %s, tray: %s)%s", self.backend,
                 self.notify_send or "not found", "yes" if win.tray else "no",
                 f" — {self.problem}" if self.problem else "")
        self._tray_note = None
        self._warned = False
        if win.tray:
            win.tray.messageClicked.connect(
                lambda: self._tray_note and self.clicked.emit(self._tray_note))

    def on_screen(self, lane):
        """Is this lane what the reader is looking at right now?"""
        return self.win.isActiveWindow() and self.win.isVisible() and \
            self.win.current_lane() == lane

    def notify(self, items):
        """items: [(lane, status or account or notification)] from the core."""
        if not items:
            return
        if not self.cfg["enabled"]:
            log.debug("notify: %d new, notifications are off", len(items))
            return
        notes = notifytext.build(items, self.cfg["privacy"], self.win.lane_title)
        for note in notes:
            if not self.cfg["when_focused"] and self.on_screen(note.lane):
                log.debug("notify: %s skipped, that lane is on screen", note.lane)
                continue
            self._show(note)

    def test(self):
        """Debug menu: show a sample right now, whatever has focus."""
        note = notifytext.Note("fedtail", _("notify_test_body"), "people")
        self._show(note)
        return self.backend

    def _show(self, note):
        log.info("notify: %s via %s (%d chars)", note.lane, self.backend,
                 len(note.title) + len(note.body))
        if self.backend == "desktop" and self.notify_send:
            threading.Thread(target=self._desktop, args=(note,), name="fedtail-notify",
                             daemon=True).start()
        elif self.win.tray:
            self._tray_note = note
            self.win.tray.showMessage(note.title, note.body, self.win.windowIcon(), 8000)
        else:
            log.warning("notify: nowhere to show it (no notify-send, no tray)")

    def _desktop(self, note):
        base = [self.notify_send, "--app-name=fedtail", f"--icon={icon_path()}",
                "--hint=string:desktop-entry:fedtail", "--category=im.received"]
        try:
            # with --wait, notify-send prints the chosen action when "Open" is pressed
            r = subprocess.run(base + [f"--action=open={_('open_action')}", "--wait",
                                       note.title, note.body],
                               capture_output=True, text=True, timeout=600)
            log.debug("notify-send exit %s, out %r, err %r", r.returncode,
                      r.stdout.strip()[:80], r.stderr.strip()[:200])
            if r.returncode != 0:
                # an old notify-send without --action/--wait: show it plainly
                r2 = subprocess.run(base + [note.title, note.body], capture_output=True,
                                    text=True, timeout=30)
                if r2.returncode != 0:
                    log.warning("notify-send failed (%s): %s", r2.returncode,
                                r2.stderr.strip()[:300])
                    self._fail(r2.stderr.strip() or f"exit {r2.returncode}")
                return
            if r.stdout.strip() == "open":
                self.clicked.emit(note)
        except subprocess.TimeoutExpired:
            pass  # nobody pressed anything for ten minutes: fine
        except (OSError, subprocess.SubprocessError) as e:
            log.warning("notify-send failed: %s", e)
            self._fail(str(e))

    def _fail(self, why):
        if not self._warned:
            self._warned = True
            self.failed.emit(why)
