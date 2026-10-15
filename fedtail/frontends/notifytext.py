"""What a desktop notification says, for each privacy level. No Qt: testable.

privacy:
  full   — who and what ("Comment from Kot: take the power supply…")
  sender — who, never what ("Comment from Kot")
  count  — only how many ("2 new comments"), no names at all
"""

from dataclasses import dataclass

from ..core.model import real, snippet
from ..i18n import _

ORDER = ["comments", "mentions", "requests"]  # the rest come after, by name
ACTIVITY_ORDER = ["follow", "favourite", "reblog"]
MAX_LINES = 3


@dataclass
class Note:
    title: str
    body: str
    lane: str            # open this lane on click…
    thread: str = ""     # …or this thread, when there is just one post


def _account(obj):
    """A status's author, or the account itself (follow requests)."""
    return real(obj)["account"] if "account" in obj else obj


def _who(obj):
    acc = _account(obj)
    return acc.get("display_name") or acc.get("username") or acc.get("acct", "?")


_titles = None


def _lane_title(lane):
    return (_titles and _titles(lane)) or _("lane_" + lane)


def build(items, privacy="full", titles=None):
    """items: [(lane, status or account)] → one Note per lane.
    titles(lane) names lanes that aren't built in (lists)."""
    global _titles
    _titles = titles
    groups, acts = {}, {}
    for lane, obj in items:
        if lane == "activity":
            acts.setdefault(obj["type"], []).append(obj)
        else:
            groups.setdefault(lane, []).append(obj)
    lanes = [x for x in ORDER if x in groups] + sorted(x for x in groups if x not in ORDER)
    notes = [_note(lane, groups[lane], privacy) for lane in lanes]
    kinds = [k for k in ACTIVITY_ORDER if k in acts] + sorted(k for k in acts
                                                              if k not in ACTIVITY_ORDER)
    return notes + [_activity_note(k, acts[k], privacy) for k in kinds]


def _activity_note(kind, notifs, privacy):
    """"★ 3 in favourites" — from whom, and (full) on which post."""
    n = len(notifs)
    key = kind if kind in ("favourite", "reblog", "follow") else "other"
    title = _(f"notify_act_{key}_n", n=n)
    if privacy == "count":
        return Note("fedtail", title, "activity")
    names = list(dict.fromkeys(_who(x["account"]) for x in notifs))
    shown = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
    body = _("notify_from", names=shown)
    posts = list(dict.fromkeys(snippet(x["status"], 80) for x in notifs if x.get("status")))
    if privacy == "full" and posts:
        body += "\n" + "\n".join(f"«{p}»" for p in posts[:2])
    sids = {real(x["status"])["id"] for x in notifs if x.get("status")}
    return Note(title, body, "activity", sids.pop() if len(sids) == 1 else "")


def _note(lane, objs, privacy):
    n = len(objs)
    kind = lane if lane in ("comments", "mentions", "requests") else "lane"
    count_title = _(f"notify_{kind}_n", n=n, lane=_lane_title(lane))
    if privacy == "count":
        return Note("fedtail", count_title, lane)

    names = list(dict.fromkeys(_who(o) for o in objs))
    if n == 1:
        obj = objs[0]
        title = _(f"notify_{kind}_one", name=names[0], lane=_lane_title(lane))
        thread = real(obj)["id"] if lane != "requests" else ""
        if privacy == "sender" or lane == "requests":
            body = "@" + _account(obj).get("acct", "")
        else:
            body = snippet(obj, 200)
        return Note(title, body, lane, thread)

    if privacy == "sender" or lane == "requests":
        shown = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
        return Note(count_title, _("notify_from", names=shown), lane)
    lines = [f"{_who(o)}: {snippet(o, 90)}" for o in objs[:MAX_LINES]]
    if n > MAX_LINES:
        lines.append(_("notify_more", n=n - MAX_LINES).strip())
    return Note(count_title, "\n".join(lines), lane)
