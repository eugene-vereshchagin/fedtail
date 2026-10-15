"""The version shown to people: `fedtail -V`, About, bug reports.

`fedtail.__version__` is the release this code is heading to. Run from a git
checkout, the build is told apart by the commits on top of it:
0.2.0.dev143+g87f64ef (143 commits in history, commit 87f64ef). A package
can drop a `_build.py` with BUILD = "…" next to this file instead.
"""

import functools
import shutil
import subprocess
from pathlib import Path

from . import __version__

ROOT = Path(__file__).resolve().parent.parent


def _git(*args):
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                       timeout=5)
    return r.stdout.strip() if r.returncode == 0 else ""


@functools.cache
def info():
    """{'version', 'commit', 'date'} — commit and date empty when unknown."""
    try:
        from ._build import BUILD, COMMIT, DATE  # written by packaging
        return {"version": BUILD, "commit": COMMIT, "date": DATE}
    except ImportError:
        pass
    base = __version__.split(".dev")[0]
    if (ROOT / ".git").exists() and shutil.which("git"):
        try:
            count, sha = _git("rev-list", "--count", "HEAD"), _git("rev-parse", "--short", "HEAD")
            date = _git("log", "-1", "--format=%cs")
            dirty = "-dirty" if _git("status", "--porcelain", "--untracked-files=no") else ""
            if count and sha:
                return {"version": f"{base}.dev{count}+g{sha}", "commit": sha + dirty,
                        "date": date}
        except (OSError, subprocess.SubprocessError):
            pass
    return {"version": __version__, "commit": "", "date": ""}


def full():
    return info()["version"]
