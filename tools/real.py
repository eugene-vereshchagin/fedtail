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


def wait_for_budget(profile="", need=150, longest=600, say=print):
    """Before a step on your account: the server's rate limit (GoToSocial: 300 requests
    in 5 minutes, per address — two computers behind one router share it) has room
    for the step, or the step waits for the window to begin anew. The night of 23.10
    the steps on the account came one after another and the later ones got only 429
    ("not connected in 60 s", a tour that waited for the server all along). One GET.
    Returns the seconds waited."""
    import time

    from fedtail.core import auth as authmod
    from fedtail.core import paths
    from fedtail.protocols.base import RateLimited
    p = paths.resolve(profile or None)
    data = authmod.load(p.auth_file)
    if not data:
        return 0
    api = read_only_client()(data["server"], data["token"])
    waited = 0.0
    for _ in range(3):
        try:
            api.verify_credentials()
        except RateLimited as e:
            pause = max(5.0, min(longest - waited, (e.until or time.time() + 60) - time.time()
                                 + 3))
        except Exception as e:  # noqa: BLE001 — the step itself will say what's wrong
            say(f"the server's limit: not known ({e})")
            return waited
        else:
            b = getattr(api, "budget", None)
            if b is None or not b.limit or b.remaining >= need:
                if b is not None and b.limit:
                    say(f"the server's limit: {b.remaining} of {b.limit} left")
                return waited
            pause = max(5.0, min(longest - waited, (b.reset or time.time() + 60)
                                 - time.time() + 3))
        if pause <= 0 or waited >= longest:
            break
        say(f"the server's limit is nearly spent: waiting {pause:.0f} s for a new window")
        time.sleep(pause)
        waited += pause
    return waited


if __name__ == "__main__":  # python3 tools/real.py --wait[=PROFILE]: the limit, then go
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    arg = next((a for a in sys.argv[1:] if a.startswith("--wait")), None)
    if arg is not None:
        wait_for_budget(arg.split("=", 1)[1] if "=" in arg else "")
