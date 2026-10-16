"""The version shown to people: `fedtail -V`, About, the sidebar, bug reports.

Releases are git tags `vX.Y.Z` (and `fedtail.__version__` says the same in the
tagged commit). Between releases `__version__` names the next one as
`X.Y.Z.dev0`, and a checkout shows how far it is past the last tag:

    0.2.0                      exactly the v0.2.0 commit
    0.3.0.dev7+gabc1234        7 commits after the last release tag
    0.3.0.dev7+gabc1234 (dirty)  …with uncommitted changes

A package can ship `_build.py` with BUILD, COMMIT, DATE instead (no git there).
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


def compose(base, since_tag, sha):
    """The displayed version from __version__, commits since the last release tag
    (None: no tag known) and the short commit."""
    release = base.split(".dev")[0]
    if ".dev" not in base:
        # a release; commits past its tag without a bump show as a local build of it
        return release if since_tag == 0 else f"{release}+{since_tag}.g{sha}"
    return f"{release}.dev{since_tag or 0}+g{sha}"


@functools.cache
def info():
    """{'version', 'commit', 'date'} — commit and date empty when unknown."""
    try:
        from ._build import BUILD, COMMIT, DATE  # written by packaging
        return {"version": BUILD, "commit": COMMIT, "date": DATE}
    except ImportError:
        pass
    if (ROOT / ".git").exists() and shutil.which("git"):
        try:
            sha = _git("rev-parse", "--short", "HEAD")
            date = _git("log", "-1", "--format=%cs")
            dirty = " (dirty)" if _git("status", "--porcelain", "--untracked-files=no") else ""
            described = _git("describe", "--tags", "--long", "--match", "v[0-9]*")
            if described:  # v0.2.0-7-gabc1234
                since = int(described.rsplit("-", 2)[1])
            else:  # no tags fetched (a shallow clone): count the whole history
                since = int(_git("rev-list", "--count", "HEAD") or 0)
            if sha:
                return {"version": compose(__version__, since, sha) + dirty,
                        "commit": sha, "date": date}
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return {"version": __version__, "commit": "", "date": ""}


def full():
    return info()["version"]
