"""Starting other programs from the one-file build without handing them our insides.

The one-file build unpacks Python and Qt into a temporary folder and points
LD_LIBRARY_PATH (and a few Qt variables) at it. A program started from there —
the browser, the text editor for the config, notify-send, KDE's own "open with" —
would load our Qt instead of the system's and fail or ask what to open the file
with. So everything we start gets the environment as it was before we were
unpacked. From the source, nothing changes.

Also the desktop's font where Qt can't ask for it (desktop_font): a GTK desktop's
settings, read with the desktop's own gsettings.
"""

import os
import shutil
import subprocess
import sys

FROZEN = bool(getattr(sys, "frozen", False))
# set by the one-file loader or for Qt inside it; meaningless (or harmful) outside
OURS = ("QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QTWEBENGINEPROCESS_PATH", "PYTHONHOME", "PYTHONPATH", "_MEIPASS2",
        "_PYI_APPLICATION_HOME_DIR", "_PYI_ARCHIVE_FILE", "_PYI_PARENT_PROCESS_LEVEL")


def own_binary():
    """The file that starts this build again: the .AppImage itself (its runtime says
    where, APPIMAGE) — not the program inside it, whose folder is unmounted once we
    exit; else the one-file build's own file (sys.executable)."""
    image = os.environ.get("APPIMAGE", "")
    if FROZEN and image and os.path.isfile(image):
        return image
    return sys.executable


def child_env():
    """The environment for a program we start (None: just inherit ours)."""
    if not FROZEN:
        return None
    env = dict(os.environ)
    for var in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        orig = env.pop(var + "_ORIG", None)
        if orig is not None:
            env[var] = orig
        else:
            env.pop(var, None)
    for var in OURS:
        env.pop(var, None)
    return env


def open_external(url, always=False):
    """Open a link or a file with the desktop's choice. True if handed over; False
    means: let Qt try (from the source, or when there's no opener). always: from the
    source too (Qt has tried and failed)."""
    if not (FROZEN or always) or not sys.platform.startswith("linux"):
        return False
    for opener in ("xdg-open", "kde-open", "gio"):
        exe = shutil.which(opener)
        if exe:
            argv = [exe, "open", url] if opener == "gio" else [exe, url]
            subprocess.Popen(argv, env=child_env(), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            return True
    return False


# the GTK desktops' interface settings, by XDG_CURRENT_DESKTOP; GNOME's for the rest
FONT_SCHEMAS = (("CINNAMON", "org.cinnamon.desktop.interface"),
                ("MATE", "org.mate.interface"),
                ("", "org.gnome.desktop.interface"))


def parse_font_name(raw):
    """GTK's font name ("'Ubuntu Bold 11'", as gsettings prints it) → (family, size
    in points) — the style words after the family are dropped; None for nonsense."""
    words = raw.strip().strip("'\"").split()
    if len(words) < 2:
        return None
    try:
        size = float(words[-1])
    except ValueError:
        return None
    styles = {"bold", "italic", "oblique", "light", "medium", "regular", "semi-bold",
              "semibold", "thin", "heavy", "black", "condensed", "book", "ultra-light",
              "extra-light", "semi-light", "ultra-bold", "extra-bold", "demi-bold"}
    family = words[:-1]
    while len(family) > 1 and family[-1].lower() in styles:
        family.pop()
    if size <= 0 or not family:
        return None
    return " ".join(family), size


def desktop_font(run=subprocess.run):
    """The interface font a GTK desktop (Cinnamon, MATE, GNOME, Xfce with GNOME's
    schemas) is set to, as (family, points); None when it can't be told. For Qt
    without the desktop's integration (the one-file build, the AppImage): it gets a
    bare "Sans" otherwise."""
    if not sys.platform.startswith("linux"):
        return None
    exe = shutil.which("gsettings")
    if not exe:
        return None
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    schema = next(s for key, s in FONT_SCHEMAS if key in desktop)
    try:
        out = run([exe, "get", schema, "font-name"], capture_output=True, text=True,
                  timeout=5, env=child_env(), stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return parse_font_name(out.stdout)
