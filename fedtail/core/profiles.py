"""Profiles: one account each, each with its own config, theme, data and window.

The window's account switcher and `--profiles` list them from the data folders;
each profile keeps a small profile.json there (who it is and on which server —
never the token) so the list can say "@me@server" without logging in.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)

CARD = "profile.json"
NOT_PROFILES = {"themes"}  # ~/.config/fedtail/themes: shared by all profiles


def data_root():
    return paths.data_base()


def config_root():
    return paths.config_base()


def remember(where, me, server):
    """Write who this profile is (on connect)."""
    card = {"acct": me.get("acct", ""), "display_name": me.get("display_name", ""),
            "server": server}
    try:
        f = where.data_dir / CARD
        if not f.exists() or json.loads(f.read_text("utf-8")) != card:
            f.write_text(json.dumps(card, ensure_ascii=False), "utf-8")
    except (OSError, ValueError) as e:
        log.warning("profile card: %s", e)


def listing():
    """[{"name", "acct", "server", "display_name", "logged_in"}] for every profile
    found in the data and config folders, the default first, then by name."""
    # a profile is a config folder with config.toml or a data folder with a login or a
    # database in it — not just any folder there (themes/ lives next to the profiles)
    marks = {config_root(): ("config.toml",), data_root(): ("auth.json", "state.db")}
    names = set()
    for root, files in marks.items():
        if root.is_dir():
            names |= {p.name for p in root.iterdir() if p.is_dir()
                      and p.name not in NOT_PROFILES and paths._PROFILE_RE.match(p.name)
                      and any((p / f).exists() for f in files)}
    out = []
    for name in names:
        d = data_root() / name
        card = {}
        try:
            card = json.loads((d / CARD).read_text("utf-8"))
        except (OSError, ValueError):
            pass
        out.append({"name": name, "acct": card.get("acct", ""),
                    "display_name": card.get("display_name", ""),
                    "server": card.get("server", ""),
                    "logged_in": (d / "auth.json").exists()})
    out.sort(key=lambda p: (p["name"] != paths.DEFAULT_PROFILE, p["name"].lower()))
    return out


def label(p):
    """"@me@server (work)" — how a profile is named in menus and lists."""
    host = p["server"].split("://")[-1].rstrip("/") if p["server"] else ""
    who = f"@{p['acct']}" + (f"@{host}" if host and "@" not in p["acct"] else "") \
        if p["acct"] else ""
    if who:
        return who if p["name"] == paths.DEFAULT_PROFILE else f"{who} ({p['name']})"
    return p["name"]


def command(profile):
    """(argv, cwd) that starts fedtail with this profile — from the same checkout
    or installation this one runs from."""
    if getattr(sys, "frozen", False):  # the one-file build
        return [sys.executable, "--profile", profile], None
    root = Path(__file__).resolve().parent.parent.parent
    if (root / "pyproject.toml").exists():
        return [sys.executable, "-m", "fedtail", "--profile", profile], str(root)
    return [sys.executable, "-m", "fedtail", "--profile", profile], None


def launch(profile, after=0.0):
    """Start fedtail with that profile, detached. If it is already running, the new
    process asks it to show itself and leaves (SingleInstance). after: seconds to
    wait first (a restart of this very profile: let this window close)."""
    argv, cwd = command(profile)
    log.info("starting profile %s%s", profile, f" in {after} s" if after else "")
    env = dict(os.environ)
    if after:  # a small Python waits, then starts it: works the same on every system
        argv = [sys.executable, "-c",
                f"import subprocess, time; time.sleep({float(after)}); "
                f"subprocess.Popen({argv!r}, cwd={cwd!r})"]
    detached = {"creationflags": 0x00000008 | 0x00000200} if paths.WINDOWS else \
        {"start_new_session": True}  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **detached)
