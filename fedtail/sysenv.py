"""Starting other programs from the one-file build without handing them our insides.

The one-file build unpacks Python and Qt into a temporary folder and points
LD_LIBRARY_PATH (and a few Qt variables) at it. A program started from there —
the browser, the text editor for the config, notify-send, KDE's own "open with" —
would load our Qt instead of the system's and fail or ask what to open the file
with. So everything we start gets the environment as it was before we were
unpacked. From the source, nothing changes.
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
