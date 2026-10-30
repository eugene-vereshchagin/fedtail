"""Desktop notifications.

KDE (and any freedesktop desktop) shows them through notify-send, with an
"Open" button that brings fedtail up on the right lane or thread. Without
notify-send the tray balloon is used.
"""

import logging
import os
import shutil
import subprocess
import threading
from importlib import resources

from PySide6.QtCore import QObject, Signal

from ... import sysenv
from ...desktop import desktop_id
from ...i18n import _
from .. import notifytext

log = logging.getLogger(__name__)


_themed = None  # the icon drawn in the current theme's colours, set at start-up
_style = "possum"  # ui.app_icon


def mascot_path():
    """The opossum holding its own tail: fedtail's picture (About, the menu entry)."""
    return str(resources.files("fedtail").joinpath("data/icons/fedtail.png"))


def swing_path():
    """The opossum swinging (a Telegram sticker, as the icon): the curtain while the
    lanes are being updated."""
    return str(resources.files("fedtail").joinpath("data/icons/fedtail-swing.gif"))


def possum_style():
    """ui.app_icon = "possum": the picture is the opossum (not the drawn bubble)."""
    return _style != "bubble"


def set_style(style):
    """ui.app_icon: "possum" (the picture) or "bubble" (drawn; in the theme's colours
    with ui.themed_icon)."""
    global _style, _themed
    _style, _themed = style, None


def icon_path():
    """The icon for the window, tray and notifications: the opossum; or the bubble,
    the theme's own or the standard one."""
    if _style != "bubble":
        return mascot_path()
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
        elif wanted == "auto" and not self.notify_send and os.name != "nt":
            # (on Windows the tray's own notifications are the native ones: no problem)
            self.problem = _("notify_no_send")
        if self.backend == "tray" and not win.tray:
            self.problem = _("notify_nothing")
        log.info("notifications: %s (notify-send: %s, tray: %s)%s", self.backend,
                 self.notify_send or "not found", "yes" if win.tray else "no",
                 f" — {self.problem}" if self.problem else "")
        self._tray_note = None
        self._warned = False
        self._nowhere_said = False
        if win.tray:
            win.tray.messageClicked.connect(
                lambda: self._tray_note and self.clicked.emit(self._tray_note))

    def on_screen(self, lane):
        """Is this lane what the reader is looking at right now?"""
        return self.win.isActiveWindow() and self.win.isVisible() and \
            self.win.lane_on_screen(lane)

    def notify(self, items):
        """items: [(lane, status or account or notification)] from the core."""
        for note in notifytext.due(self.win.ctx.view, items, self.cfg, self.on_screen,
                                   self.win.lane_title):
            self._show(note)

    def test(self):
        """Debug menu: show a sample right now, whatever has focus."""
        note = notifytext.Note("fedtail", _("notify_test_body"), "home")
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
            # notify.seconds: how long the balloon stays (0 — Qt's usual 8 s)
            ms = int(float(self.cfg.get("seconds", 0) or 8) * 1000)
            self.win.tray.showMessage(note.title, note.body, self.win.windowIcon(), ms)
        else:
            # once: the settings already say it (self.problem); each further one — info
            # the settings and the status bar say it already (self.problem): info then
            (log.info if self._nowhere_said or self.problem else log.warning)(
                "notify: nowhere to show it (no notify-send, no tray)")
            self._nowhere_said = True

    def _desktop(self, note):
        # the desktop entry's own name (desktop_id: the app id, a profile's own for another
        # profile) — "fedtail" named no entry, so the desktop knew neither its icon nor
        # its group in the notification settings
        entry = desktop_id(getattr(getattr(self.win.core, "paths", None), "profile", None))
        base = [self.notify_send, "--app-name=FedTail", f"--icon={icon_path()}",
                f"--hint=string:desktop-entry:{entry}", "--category=im.received"]
        try:
            # with --wait, notify-send prints the chosen action when "Open" is pressed
            wait = base + [f"--action=open={_('open_action')}", "--wait"]
            seconds = float(self.cfg.get("seconds", 0) or 0)
            r = subprocess.run(notifytext.desktop_argv(wait, note, seconds),
                               capture_output=True, text=True, timeout=600,
                               env=sysenv.child_env())
            log.debug("notify-send exit %s, out %r, err %r", r.returncode,
                      r.stdout.strip()[:80], r.stderr.strip()[:200])
            if r.returncode != 0:
                # an old notify-send without --action/--wait: show it plainly
                r2 = subprocess.run(notifytext.desktop_argv(base, note, seconds),
                                    capture_output=True,
                                    text=True, timeout=30, env=sysenv.child_env())
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
