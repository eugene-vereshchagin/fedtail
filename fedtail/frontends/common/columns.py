"""Lanes side by side (ui.layout = "columns", or ❯ in the sidebar) without a toolkit:
which lanes are the columns at start."""

from __future__ import annotations

MOST = 4  # columns the default has at most


def default_names(view, known):
    """The columns with nothing said: by the lanes' rules, not their names — the lane
    opened first, then the lanes of replies and mentions (Core.lane_rank 1–2), then a
    lane of events (Activity), at most MOST."""
    from . import sidebar
    known = list(known)
    out = []
    first = sidebar.start_lane(view, known, closable=False)
    if first:
        out.append(first)
    rank = getattr(view, "lane_rank", None)
    if rank is not None:
        out += [n for n in known if rank(n) in (1, 2)]
    by_name = getattr(view, "lane_by_name", {}) or {}
    out += [n for n in known if getattr(by_name.get(n), "events", False)
            and not getattr(by_name.get(n), "source", None)][:1]
    return list(dict.fromkeys(out))[:MOST]


def start_names(cfg, remembered, known, list_titles=None, view=None):
    """The columns at start: as left last time, else the config's, else the default
    (default_names, with the view) — only lanes there are (a list gone, a lane switched
    off). list_titles: {title: lane} so the config may say "list:Друзья"."""
    known = list(known)
    titles = list_titles or {}
    fallback = default_names(view, known) if view is not None else []
    for names in (remembered, cfg["ui"].get("columns") or [], fallback):
        got = []
        for n in names or []:
            if n not in known and n.startswith("list:"):
                n = titles.get(n[len("list:"):], n)
            if n in known and n not in got:
                got.append(n)
        if got:
            return got
    return known[:1]
