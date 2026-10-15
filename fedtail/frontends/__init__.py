"""Frontend registry. A frontend is a module with run(core, instance, argv) -> int.

To add one: put it in fedtail/frontends/<name>/ and list it here.
"""

import importlib
import sys

FRONTENDS = {
    "qt": ("fedtail.frontends.qt",
           "Qt frontend needs PySide6.\n"
           "  Debian 13:  sudo apt install python3-pyside6.qtwidgets\n"
           "  elsewhere:  pip install 'PySide6-Essentials>=6.5'"),
}


def load(name):
    module, hint = FRONTENDS[name]
    try:
        return importlib.import_module(module)
    except ImportError as e:
        if "PySide6" in str(e) or "shiboken" in str(e):
            print(f"fedtail: {hint}", file=sys.stderr)
            sys.exit(3)
        raise
