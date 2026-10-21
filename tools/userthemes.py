"""Your own themes (the ones in ~/.config/fedtail/themes that fedtail didn't bring — a
theme of your making, a set you got elsewhere) for the dev tools: each tool runs in a
temporary config folder, and without this it would see the built-in themes only.

    OWN = userthemes.bring(TMP / "config")   # before XDG_CONFIG_HOME points at TMP/config

The copies go into the temporary folder; yours are only read. The gallery
(tools/gallery.py) never takes them: they are tested, not published."""

from __future__ import annotations

import shutil
from pathlib import Path


def own_themes():
    """{name: its .toml} — the themes in your themes folder that aren't built in."""
    from fedtail.frontends import themefile
    src = themefile.user_dir()
    builtin = {p.stem for p in themefile.BUILTIN_DIR.glob("*.toml")}
    if not src.is_dir():
        return {}
    return {p.stem: p for p in sorted(src.glob("*.toml")) if p.stem not in builtin}


def bring(config_home):
    """Copy your own themes (and their folders: pictures, fonts) under config_home's
    fedtail/themes. Returns their names."""
    found = own_themes()
    if not found:
        return []
    dst = Path(config_home) / "fedtail" / "themes"
    dst.mkdir(parents=True, exist_ok=True)
    for name, toml in found.items():
        shutil.copy2(toml, dst / toml.name)
        folder = toml.with_suffix("")
        if folder.is_dir():
            shutil.copytree(folder, dst / name, dirs_exist_ok=True)
    print("your own themes: " + ", ".join(found), flush=True)
    return list(found)
