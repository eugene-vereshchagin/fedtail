"""Credentials live in a plain JSON file with 0600 permissions. No keyrings."""

import contextlib
import json
import os


def load(path):
    try:
        data = json.loads(path.read_text("utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("token"), str) or \
            not isinstance(data.get("server"), str) or not data["token"] or not data["server"]:
        return None  # a broken file: "log in", not a crash
    return data


def save(path, data):
    """A secret file (the token, the sync key, an invite, a password): the owner's only
    (0600, made so — never a file left over with its own mode), written whole or not at
    all, through a temporary file of its own (two writers at once can't remove each
    other's: the sync key's "sync.tmp" was shared, 29.10)."""
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        os.chmod(tmp, 0o600)  # mkstemp's own already; said for the platforms that differ
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _replace(tmp, path, tries=50):
    """os.replace, waited out on Windows: there a file being replaced by another writer
    that very moment can't be replaced ("Access is denied") — the next try a few ms later
    can; elsewhere it never fails so."""
    import time
    for i in range(tries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if os.name != "nt" or i == tries - 1:
                raise
            time.sleep(0.01 * (1 + i % 5))


def forget(path):
    try:
        path.unlink()
    except FileNotFoundError:
        pass
