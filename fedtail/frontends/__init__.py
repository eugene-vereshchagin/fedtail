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
}


def load(name):
    module, hint = FRONTENDS[name]
    try:
        return importlib.import_module(module)
    except ImportError as e:
        if any(x in str(e) for x in ("PySide6", "shiboken", "textual", "rich")):
            print(f"fedtail: {hint}", file=sys.stderr)
            sys.exit(3)
        raise
