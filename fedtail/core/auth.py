"""Credentials live in a plain JSON file with 0600 permissions. No keyrings."""

import json
import os


def load(path):
    try:
        data = json.loads(path.read_text("utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return None
    if not data.get("token") or not data.get("server"):
        return None
    return data


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def forget(path):
    try:
        path.unlink()
    except FileNotFoundError:
        pass
