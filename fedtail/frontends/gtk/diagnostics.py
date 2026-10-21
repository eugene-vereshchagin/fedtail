"""The GTK side of diag.py: the freeze watchdog and the stall meter ticking from the
GLib main loop (what qt/diagnostics.py does with QTimers), and GTK's own warnings into
the log."""

import logging

from ... import diag
from .gi_setup import GLib

log = logging.getLogger("fedtail.gtk")


def install(cfg):
    """Start the watchdog (stacks of all threads into the log when the main loop stops
    answering for debug.watchdog_seconds) and the stall meter (debug.stall_ms). What
    install() returns must be kept; stop() on quit."""
    seconds = float(cfg["debug"]["watchdog_seconds"]) if diag.is_on() else 0
    dog = diag.Watchdog(seconds)
    GLib.timeout_add(1000, lambda: (dog.beat(), GLib.SOURCE_CONTINUE)[1])
    dog.start()
    stall_ms = int(cfg["debug"].get("stall_ms", 0)) if diag.is_on() else 0
    meter = diag.StallMeter(stall_ms)
    if stall_ms:
        GLib.timeout_add(int(meter.interval * 1000),
                         lambda: (meter.tick(), GLib.SOURCE_CONTINUE)[1])
        meter.start()
        diag.add_stats("freezes", meter.counts)
    _gtk_messages()

    def stop():
        dog.stop()
        meter.stop()
    return stop


def _gtk_messages():
    """GLib's and GTK's warnings ("Gtk-WARNING …") into fedtail's log as well."""
    def handler(domain, level, message, _data=None):
        lvl = logging.WARNING if level & (GLib.LogLevelFlags.LEVEL_WARNING |
                                          GLib.LogLevelFlags.LEVEL_CRITICAL) else logging.DEBUG
        log.log(lvl, "[%s] %s", domain or "glib", message)
    for domain in ("Gtk", "Gdk", "GLib", "GLib-GObject", "Gsk", "Pango", "Adwaita"):
        try:
            GLib.log_set_handler(domain, GLib.LogLevelFlags.LEVEL_MASK, handler, None)
        except Exception:  # noqa: BLE001 — older PyGObject: the terminal keeps them
            return
