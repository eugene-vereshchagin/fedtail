"""Entry point of the one-file builds (PyInstaller), Linux and Windows."""

import os
import sys

# a windowed build has no console: print() and logging to the terminal go nowhere
for name in ("stdout", "stderr"):
    if getattr(sys, name) is None:
        setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115

# the restart's helper (core/profiles.launch): this file has no `python -c`, so the
# helper comes in the environment — run it, and nothing else
from fedtail.core.profiles import relaunch_from_env  # noqa: E402

if __name__ == "__main__" and relaunch_from_env():
    sys.exit(0)

from fedtail.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
