"""Desktop notifications from the GTK window. What a notification says (and how much,
notify.privacy) is notifytext.py's, shared with Qt; when one is shown is the same rule
as Qt's (notify.enabled, notify.when_focused). The GTK way of showing it: a
Gio.Notification through the application — GNOME's own, the portal or the
freedesktop daemon elsewhere — whose click brings the window to the thread or the lane;
notify-send when the application has no session bus."""

import logging
import shutil
import subprocess
import threading

from ...i18n import _
from .. import notifytext
from .gi_setup import Gio, GLib

log = logging.getLogger(__name__)

ACTION = "open-note"   # app.open-note("thread:<id>" | "lane:<name>")


class Notifier:
    def __init__(self, win, app):
        self.win, self.app = win, app
        self.cfg = win.cfg["notify"]
        bus = app.get_dbus_connection() if app is not None else None
        self.backend = "gio" if bus is not None else (
            "notify-send" if shutil.which("notify-send") else "none")
        log.info("notifications: %s", self.backend)
        if app is not None and app.lookup_action(ACTION) is None:
            act = Gio.SimpleAction.new(ACTION, GLib.VariantType.new("s"))
            act.connect("activate", lambda _a, v: self.opened(v.get_string()))
            app.add_action(act)

    def notify(self, items):
        """items: [(lane, a post, account or notification)] from the core."""
        for note in notifytext.due(self.win.view, items, self.cfg, self.on_screen,
                                   self.win.lane_title):
            self.show(note)

    def test(self):
        """Debug menu: a sample right now, whatever has focus; says how it went out."""
        self.show(notifytext.Note("fedtail", _("notify_test_body"), "home"))
        return self.backend

    def on_screen(self, lane):
        return self.win.is_active() and self.win.lane_on_screen(lane)

    def show(self, note):
        log.info("notify: %s via %s", note.lane, self.backend)
        target = f"thread:{note.thread}" if note.thread else f"lane:{note.lane}"
        if self.backend == "gio":
            n = Gio.Notification.new(note.title)
            n.set_body(note.body)
            n.set_default_action_and_target_value(f"app.{ACTION}", GLib.Variant("s", target))
            n.add_button_with_target_value(_("open_action"), f"app.{ACTION}",
                                           GLib.Variant("s", target))
            self.app.send_notification(None, n)
        elif self.backend == "notify-send":
            argv = notifytext.desktop_argv([shutil.which("notify-send"), "--app-name=fedtail"],
                                           note)
            threading.Thread(target=subprocess.run, args=(argv,),
                             kwargs={"capture_output": True, "timeout": 30},
                             daemon=True).start()

    def opened(self, target):
        """A notification was clicked: the window, at what it was about."""
        self.win.present()
        kind, _sep, what = target.partition(":")
        if kind == "thread" and what:
            self.win.open_thread(what)
        elif kind == "lane" and what in self.win.lane_rows:
            self.win.sidebar.select_row(self.win.lane_rows[what])
