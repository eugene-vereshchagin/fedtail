"""Where a profile keeps its files."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

APP = "fedtail"
DEFAULT_PROFILE = "default"
_PROFILE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _xdg(var, fallback):
    v = os.environ.get(var)
    return Path(v) if v else Path.home() / fallback


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
        os.chmod(self.data_dir, 0o700)
        self.cache_dir.mkdir(exist_ok=True)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)


def resolve(profile=None, config=None, data=None):
    """--profile NAME picks both dirs; --config / --data override each one."""
    profile = profile or DEFAULT_PROFILE
    if not _PROFILE_RE.match(profile):
        raise ValueError(f"bad profile name {profile!r}: use letters, digits, _ . -")
    cfg = Path(config).expanduser() if config else \
        _xdg("XDG_CONFIG_HOME", ".config") / APP / profile / "config.toml"
    dat = Path(data).expanduser() if data else \
        _xdg("XDG_DATA_HOME", ".local/share") / APP / profile
    return Paths(profile, cfg, dat)
