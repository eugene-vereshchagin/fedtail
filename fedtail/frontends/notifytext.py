"""What a desktop notification says, for each privacy level. No Qt: testable.

privacy:
  full   — who and what ("Comment from Kot: take the power supply…")
  sender — who, never what ("Comment from Kot")
  count  — only how many ("2 new comments"), no names at all
"""

import html
from dataclasses import dataclass

from ..i18n import _
from ..model import Account, Activity, real
from ..model.text import snippet

ORDER = ["replies", "mentions", "requests"]  # the rest come after, by name
ACTIVITY_ORDER = ["follow", "like", "share"]
# the words for a kind of activity: notify_act_<…>_n
ACT_WORDS = {"follow": "notify_act_follow_n", "like": "notify_act_favourite_n",
             "share": "notify_act_reblog_n"}
MAX_LINES = 3


@dataclass
class Note:
    title: str
    body: str
    lane: str            # open this lane on click…
    thread: str = ""     # …or this thread, when there is just one post


def _account(obj):
    """A post's author, an activity's someone, or the account itself (follow requests)."""
    if isinstance(obj, Account) or obj is None:
        return obj
    if isinstance(obj, Activity):
        return obj.who
    return real(obj).author


def _who(obj):
    acc = _account(obj)
    return (acc.name or acc.username or acc.handle or "?") if acc else "?"


_titles = None


def desktop_argv(base, note):
    """notify-send's arguments for a note. Its body is markup to the desktop (links,
    bold, on some desktops pictures), and a post's text may say "<a href=…>" in plain
    letters: escaped, so it shows as written. "--" first: a name that begins with "--"
    is a name, not an option."""
    return base + ["--", note.title, html.escape(note.body, quote=False)]


def _lane_title(lane):
    return (_titles and _titles(lane)) or _("lane_" + lane)


def build(items, privacy="full", titles=None):
    """items: [(lane, Post, Share, Account or Activity)] → one Note per lane.
    titles(lane) names lanes that aren't built in (lists)."""
    global _titles
    _titles = titles
    groups, acts = {}, {}
    for lane, obj in items:
        if lane == "activity":
            acts.setdefault(obj.kind, []).append(obj)
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
    title = _(ACT_WORDS.get(kind, "notify_act_other_n"), n=n)
    if privacy == "count":
        return Note("fedtail", title, "activity")
    names = list(dict.fromkeys(_who(x) for x in notifs))
    shown = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
    body = _("notify_from", names=shown)
    posts = list(dict.fromkeys(snippet(x.post, 80) for x in notifs if x.post))
    if privacy == "full" and posts:
        body += "\n" + "\n".join(f"«{p}»" for p in posts[:2])
    sids = {x.post.id for x in notifs if x.post}
    return Note(title, body, "activity", sids.pop() if len(sids) == 1 else "")


def _note(lane, objs, privacy):
    n = len(objs)
    kind = lane if lane in ("replies", "mentions", "requests") else "lane"
    count_title = _(f"notify_{kind}_n", n=n, lane=_lane_title(lane))
    if privacy == "count":
        return Note("fedtail", count_title, lane)

    names = list(dict.fromkeys(_who(o) for o in objs))
    if n == 1:
        obj = objs[0]
        title = _(f"notify_{kind}_one", name=names[0], lane=_lane_title(lane))
        thread = real(obj).id if lane != "requests" else ""
        if privacy == "sender" or lane == "requests":
            body = "@" + (_account(obj).handle if _account(obj) else "")
        else:
            body = snippet(real(obj), 200)
        return Note(title, body, lane, thread)

    if privacy == "sender" or lane == "requests":
        shown = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
        return Note(count_title, _("notify_from", names=shown), lane)
    lines = [f"{_who(o)}: {snippet(real(o), 90)}" for o in objs[:MAX_LINES]]
    if n > MAX_LINES:
        lines.append(_("notify_more", n=n - MAX_LINES).strip())
    return Note(count_title, "\n".join(lines), lane)
