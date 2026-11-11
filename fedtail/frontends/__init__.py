"""Frontend registry. A frontend is a module with run(core, instance, argv) -> int.

To add one: put it in fedtail/frontends/<name>/ and list it here. (The terminal
commands — fedtail show, tail, post — are not a frontend: see cli.py.)
"""

import importlib
import sys

FRONTENDS = {
    "qt": ("fedtail.frontends.qt",
           "Qt frontend needs PySide6.\n"
           "  Debian 13:  sudo apt install python3-pyside6.qtwidgets\n"
           "  elsewhere:  pip install 'PySide6-Essentials>=6.5'"),
    "tui": ("fedtail.frontends.tui",
            "The terminal interface needs Textual.\n"
            "  Debian 13:  sudo apt install python3-textual\n"
            "  elsewhere:  pip install 'textual>=0.86'"),
    "web": ("fedtail.frontends.web", ""),
    "gtk": ("fedtail.frontends.gtk",
            "The GTK interface needs PyGObject and GTK 4.\n"
            "  Debian 13:  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1\n"
            "  elsewhere:  your distribution's PyGObject and GTK 4 packages"),
}


# the one-file build (PyInstaller) carries Qt, the terminal and the web page; GTK comes
# from the system, and a binary can't take it
FROZEN_HINT = ("The one-file build has the Qt window (--ui qt), the terminal (--ui tui) and\n"
               "  the web page (--ui web). The GTK window needs the system's GTK 4: install\n"
               "  the .deb package, or run fedtail from the source (python3 -m fedtail).")


def load(name):
    module, hint = FRONTENDS[name]
    try:
        return importlib.import_module(module)
    except ImportError as e:
        if getattr(sys, "frozen", False):  # nothing to install into a binary: what it has
            print(f"fedtail: {FROZEN_HINT}", file=sys.stderr)
            sys.exit(3)
        if any(x in str(e) for x in ("PySide6", "shiboken", "textual", "rich", "GTK 4")):
            print(f"fedtail: {hint}", file=sys.stderr)
            sys.exit(3)
        raise
