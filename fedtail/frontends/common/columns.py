"""Lanes side by side (ui.layout = "columns", or ❯ in the sidebar) without a toolkit:
which lanes are the columns at start."""

from __future__ import annotations

DEFAULT = ["home", "replies", "activity"]


def start_names(cfg, remembered, known, list_titles=None):
    """The columns at start: as left last time, else the config's, else the default —
    only lanes there are (a list gone, a lane switched off). list_titles: {title: lane}
    so the config may say "list:Друзья"."""
    known = list(known)
    titles = list_titles or {}
    for names in (remembered, cfg["ui"].get("columns") or [], DEFAULT):
        got = []
        for n in names or []:
            if n not in known and n.startswith("list:"):
                n = titles.get(n[len("list:"):], n)
            if n in known and n not in got:
                got.append(n)
        if got:
            return got
    return known[:1]
