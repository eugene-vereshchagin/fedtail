"""The sidebar without a toolkit: its sections (grouped or plain), the count on every
lane, the number on the tray/launcher icon, and which sections are folded (kept in
the profile's state, so both windows fold the same)."""

from __future__ import annotations

from ...core import lanes as lanes_mod
from ...i18n import _


def groups(view, cfg):
    """[(group | None, [lane names])], top to bottom: ui.sidebar_groups' sections, or
    the lanes and then the lists. "lists" is left out when lists are off."""
    if cfg["ui"]["sidebar_groups"]:
        out = lanes_mod.grouped(view.lanes)
    else:
        out = [(None, [x.name for x in view.lanes if not lanes_mod.is_list(x.name)]),
               ("lists", [x.name for x in view.lanes if lanes_mod.is_list(x.name)])]
    return [(g, names) for g, names in out if g != "lists" or cfg["lists"]["enabled"]]


def hub_kind(view, name):
    """The section of the phone's overview a lane stands in, by what its rule takes —
    never its name: "you" (addressed to me: private, replies, mentions — Core.lane_rank —
    and a lane of events only), "browse" (browsed, or one's own posts: nothing to catch up
    on), "lists", else "reading"."""
    lane = view.lane_by_name.get(name)
    if lane is None:
        return "browse"
    if getattr(lane, "events", False) and not lane.source:
        return "you"
    sources = {lane.source, *(getattr(lane, "feeds", ()) or ())} - {None}
    if lane.lazy or not lane.source or sources == {"mine"}:
        return "browse"
    if lanes_mod.is_list(name):
        return "lists"
    rank = view.lane_rank(name) if hasattr(view, "lane_rank") else 4
    return "you" if rank in (0, 1, 2) else "reading"


def peek(view, name, n=90):
    """"Who: the first words" of a lane's first unread post (oldest first), "" — none."""
    from ...model import real
    from ...model.text import snippet
    try:
        entries = view.entries(name)
        unread = view.unread(entries)
    except Exception:  # noqa: BLE001 — a lane not made yet: no peek, the count still shows
        return ""
    for _item, e in entries:
        if e.id not in unread:
            continue
        p = real(e)
        who = p.author.name or p.author.username or ""
        words = snippet(p, n)
        return f"{who}: {words}" if who else words
    return ""


def group_title(group):
    """A section's heading, None for the plain list's lanes."""
    if not group:
        return None
    return _("lists_header") if group == "lists" else _("grp_" + group)


def start_lane(view, names, closable=True):
    """The lane every interface opens first (ui.start_lane), or None: "none" — every lane
    closed behind the curtain, nothing read by just starting (every interface draws it,
    curtain(); closable=False — Enter on the curtain, the phone, the columns — takes the
    lane of last time); "last" — the lane of last time; or a lane by
    name. A lane not there (the first start, a lane off) gives the set's own (its rule's
    `start = true`, presets.toml), else the sidebar's first — no lane's name assumed.
    names: the lanes the sidebar has."""
    want = view.cfg["ui"].get("start_lane") or "none"
    if want == "none" and closable:
        return None
    name = want if want not in ("none", "last") else view.get_state("lane")
    if name in names:
        return name
    return next((x.name for x in view.lanes if getattr(x, "start", False) and x.name in names),
                names[0] if names else None)


def curtain(view, names):
    """The words of the curtain — every lane closed (ui.start_lane = "none", or Esc):
    (title, what piles up behind it, how to open). Every interface draws these: the
    terminal and the web page opened the lane of last time instead (29.10)."""
    waiting = [(view.lane_title(n) or _("lane_" + n), count(view, n)) for n in names]
    waiting = [(t, c) for t, c in waiting if c]
    info = _("curtain_waiting", items=", ".join(f"{t} — {c}" for t, c in waiting)) \
        if waiting else _("curtain_empty")
    return _("curtain_title"), info, _("curtain_hint")


def lane_label(view, name, width=22):
    """(title, number) of a lane's row, cut to width: the terminal's and the web page's
    sidebar. The number is the core's for every lane alike (count)."""
    title = view.lane_title(name) or _("lane_" + name)
    n = count(view, name)
    number = f" {n}" if n else ""
    room = max(4, width - len(number))
    if len(title) > room:
        title = title[:room - 1] + "…"
    return title, n


def count(view, name):
    """The number on a lane's row: unread posts — events not seen, in a lane of events
    (the core counts both); nothing for browse lanes (no "unread" there) or before
    login."""
    try:
        if not view.me:
            return 0
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


def poll_words(view, now=None):
    """How fresh the lanes are, for a status line: "⟳ updating the lanes…" while a
    round goes on, "⚠ no answer from the server since 14:20" when rounds fail,
    "updated 14:32" otherwise; "" before the first round or without a core that says."""
    import time
    try:
        st = view.poll_state() or {}
    except Exception:  # noqa: BLE001 — a core without it (an old fake)
        return ""
    if not isinstance(st, dict):
        return ""
    from ...i18n import _
    ok = st.get("ok_at")
    if not isinstance(ok, (int, float)):
        ok = None
    at = time.strftime("%H:%M", time.localtime(ok)) if ok else ""
    if st.get("failing"):
        return _("poll_failing", time=at) if ok else _("poll_failing_never")
    if st.get("busy"):
        return _("poll_busy")
    return _("poll_ok", time=at) if ok else ""


def polling(view):
    """A poll round on right now (the curtain's opossum swings)."""
    try:
        st = view.poll_state() or {}
    except Exception:  # noqa: BLE001 — a core that doesn't say
        return False
    return bool(isinstance(st, dict) and st.get("busy"))


def status_words(view):
    """The status line's freshness and slow mode together: "updated 14:32 · slow ·
    next at 14:45"."""
    return " · ".join(x for x in (poll_words(view), slow_words(view)) if x)


def counts(view, names):
    return {name: count(view, name) for name in names}


def icon_total(view, cfg, numbers):
    """What the tray / launcher icon says: the lanes ui.icon_count chose."""
    return sum(n for name, n in numbers.items()
               if view.lane_chosen(name, cfg["ui"]["icon_count"],
                                   cfg["ui"].get("icon_count_except", [])))


def badge_kind(view, name):
    """The colour of a lane's count, by its rule (`badge`): "hot" — to answer (replies
    to me), "quiet" — no hurry (bots, activity), "normal". Every interface's sidebar:
    the windows kept it by the lanes' names, twice, and the web page had none (29.10)."""
    lane = view.lane_by_name.get(name)
    return getattr(lane, "badge", "") or "normal"


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
