"""The desktop's fractional scale (125 %, 150 %) for GTK 4 on X11.

GTK 4 on X11 scales only by whole numbers (GDK_SCALE); a desktop at 125 % is told to it
as a text DPI (Xft/DPI, 120 = 125 %) over XSETTINGS — which KDE gives GTK apps only
through its GTK settings daemon (kde-gtk-config). Without it GTK sat at 100 % beside a
Qt window at 125 %. So, when GTK has no DPI of its own, the desktop's is taken from
where X keeps it (xrdb's Xft.dpi, which Plasma sets) or from Plasma's own setting
(kdeglobals, [KScreen] ScaleFactor). The text grows; GTK's pictures and gaps keep their
pixels, as with every GTK app on X11. Wayland scales GTK itself: left alone."""

from __future__ import annotations

import configparser
import logging
import os
import subprocess
from pathlib import Path

from .gi_setup import Gdk, Gtk

log = logging.getLogger(__name__)

BASE = 96.0


def _xrdb_dpi():
    try:
        out = subprocess.run(["xrdb", "-query"], capture_output=True, text=True,
                             timeout=1.5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        key, _sep, value = line.partition(":")
        if key.strip() == "Xft.dpi":
            try:
                return float(value.strip())
            except ValueError:
                return None
    return None


def _kde_dpi():
    path = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "kdeglobals"
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        cp.read(path, encoding="utf-8")
        factor = float(cp.get("KScreen", "ScaleFactor", fallback="0") or 0)
    except (configparser.Error, ValueError, OSError):
        return None
    return BASE * factor if factor > 0 else None


def desktop_dpi():
    """The desktop's text DPI where it says one (120 for 125 %), or None."""
    return _xrdb_dpi() or _kde_dpi()


def gtk_dpi(settings=None):
    """GTK's own text DPI now (-1/0: not set — 96)."""
    settings = settings or Gtk.Settings.get_default()
    raw = settings.get_property("gtk-xft-dpi") if settings else -1
    return raw / 1024.0 if raw and raw > 0 else BASE


def apply():
    """Take the desktop's DPI when GTK has none of its own (X11 only). Returns the
    effective text scale (1.25 for 125 %)."""
    settings = Gtk.Settings.get_default()
    display = Gdk.Display.get_default()
    if settings is None or display is None:
        return 1.0
    kind = type(display).__name__
    have = settings.get_property("gtk-xft-dpi")
    if "X11" in kind and not os.environ.get("GDK_DPI_SCALE") and \
            (not have or have <= 0 or have == int(BASE * 1024)):
        want = desktop_dpi()
        if want and abs(want - BASE) >= 1:
            settings.set_property("gtk-xft-dpi", int(want * 1024))
            log.info("GTK text scale %.0f%% from the desktop (%.0f dpi)", want / BASE * 100,
                     want)
    return gtk_dpi(settings) / BASE
