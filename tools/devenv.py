"""What the dev tools need that the system's Python doesn't have (Playwright and its
Chromium, for the web walk and the gallery), in a virtual environment of their own —
the system's Python stays as Debian keeps it (PEP 668: no pip there).

    python3 tools/devenv.py          # once; again to update

The environment sees the system's packages too (PySide6, GTK, Textual from apt), so
nothing is installed twice. tools/selfcheck.py finds it by itself. Where: the cache
folder (~/.cache/fedtail/devenv; Windows: %LOCALAPPDATA%\\fedtail\\devenv) — delete it
and nothing else is touched."""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

PACKAGES = ["playwright"]


def where():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "fedtail" / "devenv"


def python():
    """The environment's Python, or None if it isn't made yet."""
    d = where()
    p = d / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return p if p.exists() else None


def main():
    d = where()
    if python() is None:
        print(f"making {d} (with the system's packages visible)…", flush=True)
        venv.EnvBuilder(system_site_packages=True, with_pip=True).create(d)
    py = str(python())
    subprocess.check_call([py, "-m", "pip", "install", "--upgrade", *PACKAGES])
    subprocess.check_call([py, "-m", "playwright", "install", "chromium"])
    print(f"\nready: {py}\ntools/selfcheck.py uses it for the web walk and the gallery.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
