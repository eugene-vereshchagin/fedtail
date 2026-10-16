"""Entry point of the one-file builds (PyInstaller), Linux and Windows."""

import os
import sys

# a windowed build has no console: print() and logging to the terminal go nowhere
for name in ("stdout", "stderr"):
    if getattr(sys, name) is None:
        setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115

from fedtail.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
