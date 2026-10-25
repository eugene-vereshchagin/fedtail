"""The sidebar without a toolkit: its sections (grouped or plain), the count on every
lane, the number on the tray/launcher icon, and which sections are folded (kept in
the profile's state, so both windows fold the same)."""

from __future__ import annotations

from ...core import lanes as lanes_mod


def groups(view, cfg):
    """[(group | None, [lane names])], top to bottom: ui.sidebar_groups' sections, or
    the lanes and then the lists. "lists" is left out when lists are off."""
    if cfg["ui"]["sidebar_groups"]:
        out = lanes_mod.grouped(view.lanes)
    else:
        out = [(None, [x.name for x in view.lanes if not lanes_mod.is_list(x.name)]),
               ("lists", [x.name for x in view.lanes if lanes_mod.is_list(x.name)])]
    return [(g, names) for g, names in out if g != "lists" or cfg["lists"]["enabled"]]


def count(view, name):
    """The number on a lane's row: unread posts; activity not seen; follow requests;
    nothing for browse lanes (no "unread" there) or before login."""
    try:
        if not view.me:
            return 0
        if name == "requests":
            return len(view.follow_requests() or ())
        if name == "activity":
            return int(view.activity_unread() or 0)
        if getattr(view.lane_by_name.get(name), "lazy", False):
            return 0
        return int(view.unread_count(name) or 0)
    except Exception:  # noqa: BLE001 — a lane the core doesn't count
        return 0


def fresh(view, name):
    """"Of them new": how many of the lane's unread came with the last update that
    brought anything (core.fresh_count); 0 when it can't tell."""
    try:
        if not view.me or getattr(view.lane_by_name.get(name), "lazy", False):
            return 0
        return int(view.fresh_count(name) or 0)
    except Exception:  # noqa: BLE001 — a lane the core doesn't count
        return 0


def fresh_words(n):
    """The words under (or after) a count: "of them new 56" — "" for none."""
    from ...i18n import _
    return _("fresh_of_them", n=n) if n else ""


def slow_words(view):
    """Slow mode on: "slow · next at 14:30" for a status line; "" when off (or unknown)."""
    import time
    try:
        nxt = view.next_round() if view.slow_minutes() else None
    except Exception:  # noqa: BLE001 — a core without slow mode (an old fake)
        return ""
    if not nxt:
        return ""
    from ...i18n import _
    return _("slow_on_short", time=time.strftime("%H:%M", time.localtime(nxt)))


def counts(view, names):
    return {name: count(view, name) for name in names}


def icon_total(view, cfg, numbers):
    """What the tray / launcher icon says: the lanes ui.icon_count chose."""
    return sum(n for name, n in numbers.items()
               if view.lane_chosen(name, cfg["ui"]["icon_count"],
                                   cfg["ui"].get("icon_count_except", [])))


def badge_text(n):
    return str(n) if n < 1000 else "999+"


def folded(view):
    """The sections folded away."""
    return set(view.get_state("folded_groups") or [])


def fold(view, group, on=None):
    """Fold a section (on=None: the other way round); returns whether it is folded."""
    now = folded(view)
    on = (group not in now) if on is None else bool(on)
    (now.add if on else now.discard)(group)
    view.set_state("folded_groups", sorted(now))
    return on
