"""The one door the Kotlin side knocks on.

Kotlin calls module-level functions here through Chaquopy and gets JSON back (a str):
plain values cross the bridge both ways, nothing of Python's lives on in Kotlin. The
core itself is the repository's fedtail/ package, unchanged — this module only puts it
on its feet on a phone:

* start(files_dir, cache_dir) — where a profile's files go. fedtail's paths follow XDG,
  so the app's private folders become XDG_CONFIG_HOME / XDG_DATA_HOME / XDG_CACHE_HOME
  and the core needs no Android branch for that. Call once, before anything else.
* info() — what the core sees about itself: versions, TLS, the database, profiles.
  The first screen shows it; a bug report starts with it.

Later steps add the calls the screens need (log in, lanes, a lane's posts, mark read…),
each a function here over the same View the desktop's interfaces use.
"""

import json
import os
import platform
import time

_started = None


def start(files_dir, cache_dir):
    """Set the stage for the core; → info() as JSON."""
    global _started
    t = time.monotonic()
    os.environ["XDG_CONFIG_HOME"] = os.path.join(files_dir, "config")
    os.environ["XDG_DATA_HOME"] = os.path.join(files_dir, "data")
    os.environ["XDG_CACHE_HOME"] = cache_dir
    os.environ.setdefault("HOME", files_dir)
    for d in ("config", "data"):
        os.makedirs(os.path.join(files_dir, d), exist_ok=True)
    _started = t
    return info()


def info():
    """{'version', 'python', 'abi', 'ssl', 'store', 'profiles', 'sync', 'started_ms'}
    — or {'error': …} with what failed: the screen shows either."""
    out = {"python": platform.python_version(), "abi": platform.machine()}
    try:
        import ssl
        out["ssl"] = ssl.OPENSSL_VERSION
        from fedtail import version
        from fedtail.core import config, paths
        from fedtail.core.store import Store
        out["version"] = version.full()
        where = paths.resolve(None)
        where.ensure()
        cfg, _warnings = config.load(where.config_file)
        store = Store(where.db_file)
        try:
            out["store"] = store.diag_counts()
        finally:
            store.close()
        base = paths.data_base()
        out["profiles"] = sorted(p.name for p in base.iterdir() if p.is_dir()) \
            if base.is_dir() else []
        out["language"] = cfg["ui"]["language"]
        from fedtail.core.sync import crypto
        out["sync"] = crypto.available()
    except Exception as e:  # noqa: BLE001 — the screen says what broke, the app lives on
        import traceback
        out["error"] = f"{e.__class__.__name__}: {e}"
        out["trace"] = traceback.format_exc(limit=8)
    if _started is not None:
        out["started_ms"] = round((time.monotonic() - _started) * 1000)
    return json.dumps(out, ensure_ascii=False)
