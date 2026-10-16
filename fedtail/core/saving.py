"""Saving pictures to disk: where (the desktop's Downloads folder unless the
config says otherwise) and under which name (the file's own, never overwriting)."""

import os
import re
import shlex
from pathlib import Path
from urllib.parse import unquote, urlparse

_EXT_BY_TYPE = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                "image/webp": ".webp", "image/avif": ".avif", "video/mp4": ".mp4"}


def downloads_dir():
    """XDG_DOWNLOAD_DIR from ~/.config/user-dirs.dirs (on a Russian desktop that is
    ~/Загрузки), else ~/Downloads."""
    home = Path.home()
    conf = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "user-dirs.dirs"
    try:
        for line in conf.read_text("utf-8").splitlines():
            if line.startswith("XDG_DOWNLOAD_DIR="):
                value = shlex.split(line.split("=", 1)[1])[0]
                return Path(value.replace("$HOME", str(home)))
    except (OSError, ValueError, IndexError):
        pass
    return home / "Downloads"


def save_dir(cfg):
    configured = cfg["ui"]["save_dir"]
    return Path(os.path.expanduser(configured)) if configured else downloads_dir()


def file_name(url, content_type=""):
    """The file's own name from the URL, made safe; an extension if it lacks one."""
    name = unquote(Path(urlparse(url).path).name) or "picture"
    name = re.sub(r"[^\w.\-]+", "_", name).strip("._") or "picture"
    if not Path(name).suffix:
        name += _EXT_BY_TYPE.get(content_type.split(";")[0].strip(), ".jpg")
    return name


def free_path(folder, name):
    """folder/name, or name-1, name-2 … if taken: nothing is ever overwritten."""
    p = Path(folder) / name
    stem, suffix, n = p.stem, p.suffix, 1
    while p.exists():
        p = p.with_name(f"{stem}-{n}{suffix}")
        n += 1
    return p
