"""--real for the dev tools: your own account instead of the fake server — the real
server, the network as it is, your lanes, your database's thousands of posts.

    python3 tools/qt_tour.py out/ --real            # the main profile
    python3 tools/qt_bench.py --real=work           # the profile "work"

What is used is a copy: the profile's config.toml, auth.json and state.db (copied by
SQLite's backup, safe while fedtail runs) go into the tool's temporary folder; your own
files are only read. And the server is only asked, never told: every request but GET
is stopped before it goes out (no post, like, follow, mark read, upload — the tool's
clicks on them end in "read-only"). The token stays on this machine; the screenshots
and logs show your real feed, so look at them before sending them anywhere."""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tomllib
from pathlib import Path

READ_ONLY = "selfcheck: read-only, not sent"


def wanted(argv=None):
    """The profile --real asks for: "" for the main one, None without --real."""
    for a in (sys.argv if argv is None else argv)[1:]:
        if a == "--real":
            return ""
        if a.startswith("--real="):
            return a.split("=", 1)[1]
    return None


def snapshot(tmp, argv=None):
    """Copy the profile into tmp/real. Call it before the tool points XDG_* at its
    temporary folder (where the real profile is found is read from them)."""
    name = wanted(argv)
    if name is None:
        return None
    from fedtail.core import paths
    src = paths.resolve(name or None)
    if not src.auth_file.exists():
        raise SystemExit(f"--real: no login in {src.data_dir} (profile {src.profile})")
    dst = Path(tmp) / "real"
    (dst / "data").mkdir(parents=True, exist_ok=True)
    if src.config_file.exists():
        shutil.copy2(src.config_file, dst / "config.toml")
    shutil.copy2(src.auth_file, dst / "data" / "auth.json")
    if src.db_file.exists():
        with sqlite3.connect(f"file:{src.db_file}?mode=ro", uri=True) as a, \
                sqlite3.connect(dst / "data" / src.db_file.name) as b:
            a.backup(b)
    print(f"--real: profile {src.profile}, a copy in {dst}; the server: read-only",
          flush=True)
    return {"profile": src.profile, "dir": dst}


def config(snap, ui=None, feed=None):
    """The profile's own settings, with the tool's ui (theme, layout…) over them."""
    from fedtail.core import config as cfgmod
    user = {}
    f = snap["dir"] / "config.toml"
    if f.exists():
        with open(f, "rb") as fh:
            user = tomllib.load(fh)
    user.setdefault("ui", {}).update(ui or {})
    user.setdefault("feed", {}).update(feed or {})
    cfg, _ = cfgmod.validate(user)
    return cfg


def read_only_client():
    from fedtail import protocols
    proto = protocols.get()
    base = proto.client

    class ReadOnly(base):
        def _req(self, method, path, **kw):
            if method.upper() not in ("GET", "HEAD"):
                raise proto.error(403, READ_ONLY)
            return super()._req(method, path, **kw)
    return ReadOnly


def core(snap, cfg):
    from fedtail.core.app import Core
    from fedtail.core.paths import Paths
    p = Paths(snap["profile"], snap["dir"] / "config.toml", snap["dir"] / "data")
    return Core(cfg, p, api_class=read_only_client())
