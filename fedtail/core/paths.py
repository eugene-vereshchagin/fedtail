"""Where a profile keeps its files."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

APP = "fedtail"
DEFAULT_PROFILE = "default"  # the first profile's folder name, and the main one until set
MAIN_FILE = "main-profile"  # in config_base(): the main profile's name (no --profile)
_PROFILE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


WINDOWS = os.name == "nt"


def _xdg(var, fallback):
    v = os.environ.get(var)
    return Path(v) if v else Path.home() / fallback


def config_base():
    """Where the profiles' config folders live: ~/.config/fedtail (XDG_CONFIG_HOME),
    on Windows %APPDATA%\\fedtail (it roams with the user)."""
    if WINDOWS and not os.environ.get("XDG_CONFIG_HOME"):
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming") / APP
    return _xdg("XDG_CONFIG_HOME", ".config") / APP


def data_base():
    """Where the profiles' data folders live: ~/.local/share/fedtail
    (XDG_DATA_HOME), on Windows %LOCALAPPDATA%\\fedtail (caches stay on this machine)."""
    if WINDOWS and not os.environ.get("XDG_DATA_HOME"):
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / APP
    return _xdg("XDG_DATA_HOME", ".local/share") / APP


@dataclass(frozen=True)
class Paths:
    profile: str
    config_file: Path
    data_dir: Path

    @property
    def auth_file(self):
        return self.data_dir / "auth.json"

    @property
    def db_file(self):
        return self.data_dir / "state.db"

    @property
    def cache_dir(self):
        return self.data_dir / "cache"

    @property
    def socket_file(self):
        return self.data_dir / "instance.sock"

    def ensure(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not WINDOWS:  # Windows keeps a user's AppData to that user anyway
            os.chmod(self.data_dir, 0o700)
        self.cache_dir.mkdir(exist_ok=True)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)


def main_profile():
    """The profile started without --profile: the one named in config_base()/main-profile,
    as long as its folders are there; else "default" (the first profile ever made)."""
    try:
        name = (config_base() / MAIN_FILE).read_text("utf-8").strip()
    except OSError:
        name = ""
    if name and name != MAIN_FILE and _PROFILE_RE.match(name) and \
            ((config_base() / name).is_dir() or (data_base() / name).is_dir()):
        return name
    return DEFAULT_PROFILE


def set_main(name):
    """Make this profile the one started without --profile."""
    if not _PROFILE_RE.match(name) or name == MAIN_FILE:
        raise ValueError(f"bad profile name {name!r}")
    config_base().mkdir(parents=True, exist_ok=True)
    (config_base() / MAIN_FILE).write_text(name + "\n", "utf-8")


def resolve(profile=None, config=None, data=None):
    """--profile NAME picks both dirs; --config / --data override each one; no name:
    the main profile."""
    profile = profile or main_profile()
    if profile == MAIN_FILE:
        raise ValueError(f"bad profile name {profile!r}: the name is taken by fedtail")
    if not _PROFILE_RE.match(profile):
        raise ValueError(f"bad profile name {profile!r}: use letters, digits, _ . -")
    cfg = Path(config).expanduser() if config else \
        config_base() / profile / "config.toml"
    dat = Path(data).expanduser() if data else \
        data_base() / profile
    return Paths(profile, cfg, dat)
