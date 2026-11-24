"""What a desktop notification says, for each privacy level. No Qt: testable.

privacy:
  full   — who and what ("Comment from Kot: take the power supply…")
  sender — who, never what ("Comment from Kot")
  count  — only how many ("2 new comments"), no names at all
"""

import html
import logging
from dataclasses import dataclass

from ..i18n import _
from ..model import Account, Activity, real
from ..model.text import snippet

WORDS = {1: "replies", 2: "mentions"}  # Core.lane_rank → the note's words (notify_<…>_n)
ACTIVITY_ORDER = ["follow", "like", "share"]
# the words for a kind of activity: notify_act_<…>_n
ACT_WORDS = {"follow": "notify_act_follow_n", "like": "notify_act_favourite_n",
             "share": "notify_act_reblog_n"}
MAX_LINES = 3  # notify.max_lines' default
log = logging.getLogger(__name__)


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


def _is_request(obj):
    """A follow request: an account waiting (as the core said them before 0.22), or the
    event of one, as any lane of events takes it now."""
    return isinstance(obj, Account) or (isinstance(obj, Activity) and obj.kind == "request"
                                        and obj.asks == "follow")


def _who(obj):
    acc = _account(obj)
    return (acc.name or acc.username or acc.handle or "?") if acc else "?"


_titles = None
_lines = MAX_LINES  # build()'s, for the note it makes
_rank = None


def _ranked(lane):
    try:
        return int(_rank(lane)) if _rank else 4
    except Exception:  # noqa: BLE001 — a lane gone meanwhile: the plain words
        return 4


def desktop_argv(base, note, seconds=0):
    """notify-send's arguments for a note. Its body is markup to the desktop (links,
    bold, on some desktops pictures), and a post's text may say "<a href=…>" in plain
    letters: escaped, so it shows as written. "--" first: a name that begins with "--"
    is a name, not an option."""
    # notify.seconds: how long it stays (0 — as the desktop keeps it)
    timeout = [f"--expire-time={int(seconds * 1000)}"] if seconds else []
    return base + timeout + ["--", note.title, html.escape(note.body, quote=False)]


def _lane_title(lane):
    from ..core import presets  # no core's word: the set's for the name, else the name
    return (_titles and _titles(lane)) or presets.title(lane)


def build(items, privacy="full", titles=None, lines=MAX_LINES, rank=None):
    """items: [(lane, Post, Share, Account or Activity)] → one Note per lane.
    titles(lane) names lanes that aren't built in (lists); lines — the posts a note
    lists at most (notify.max_lines); rank(lane) — how personal the lane's rule is
    (Core.lane_rank: 1 replies to me, 2 mentions): the notes' words and order come from
    it, never from a lane's name — a lane of one's own with the replies' rule says
    "a reply", a lane merely called "replies" doesn't."""
    global _titles, _lines, _rank
    _titles, _lines, _rank = titles, lines, rank
    groups, acts = {}, {}
    for lane, obj in items:
        if isinstance(obj, Activity) and not _is_request(obj):  # a like, a follow…
            acts.setdefault(obj.kind, []).append((lane, obj))
        else:
            groups.setdefault(lane, []).append(obj)
    # the most personal first, follow requests before the rest, then by name
    lanes = sorted(groups, key=lambda x: (_ranked(x),
                                          not all(_is_request(o) for o in groups[x]), x))
    notes = [_note(lane, groups[lane], privacy) for lane in lanes]
    kinds = [k for k in ACTIVITY_ORDER if k in acts] + sorted(k for k in acts
                                                              if k not in ACTIVITY_ORDER)
    return notes + [_activity_note(k, [o for _l, o in acts[k]], privacy, acts[k][0][0])
                    for k in kinds]


def quiet(cfg, on_screen):
    """The one rule of every interface: a note about the lane the reader is looking at
    (the window active, that lane open) is not shown, unless notify.when_focused. The
    notes about other lanes come all the same — the page kept quiet about every lane
    while its tab was in front, the phone while the app was (21.11)."""
    return bool(on_screen) and not cfg.get("when_focused", False)


def due(view, items, cfg, on_screen, titles=None):
    """The notes to show now for what the core says came (items: [(lane, a post,
    account or notification)]): none when notify.enabled is off; without the ones about
    a lane the reader is looking at (on_screen(lane)), unless notify.when_focused."""
    if not items:
        return []
    if not cfg["enabled"]:
        log.debug("notify: %d new, notifications are off", len(items))
        return []
    notes = []
    for note in build(view.model_of(list(items)), cfg["privacy"], titles,
                      cfg.get("max_lines", MAX_LINES), getattr(view, "lane_rank", None)):
        if quiet(cfg, on_screen(note.lane)):
            log.info("notify: %s skipped, that lane is on screen (notify.when_focused)",
                     note.lane)
            continue
        notes.append(note)
    return notes


def _activity_note(kind, notifs, privacy, lane):
    """"★ 3 in favourites" — from whom, and (full) on which post."""
    n = len(notifs)
    title = _(ACT_WORDS.get(kind, "notify_act_other_n"), n=n)
    if privacy == "count":
        return Note("fedtail", title, lane)
    names = list(dict.fromkeys(_who(x) for x in notifs))
    shown = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
    body = _("notify_from", names=shown)
    posts = list(dict.fromkeys(snippet(x.post, 80) for x in notifs if x.post))
    if privacy == "full" and posts:
        body += "\n" + "\n".join(f"«{p}»" for p in posts[:2])
    sids = {x.post.id for x in notifs if x.post}
    return Note(title, body, lane, sids.pop() if len(sids) == 1 else "")


def _note(lane, objs, privacy):
    n = len(objs)
    requests = all(_is_request(o) for o in objs)  # in "requests" or any lane of events
    kind = "requests" if requests else WORDS.get(_ranked(lane), "lane")
    count_title = _(f"notify_{kind}_n", n=n, lane=_lane_title(lane))
    if privacy == "count":
        return Note("fedtail", count_title, lane)

    names = list(dict.fromkeys(_who(o) for o in objs))
    if n == 1:
        obj = objs[0]
        title = _(f"notify_{kind}_one", name=names[0], lane=_lane_title(lane))
        thread = real(obj).id if not requests else ""
        if privacy == "sender" or requests:
            body = "@" + (_account(obj).handle if _account(obj) else "")
        else:
            body = snippet(real(obj), 200)
        return Note(title, body, lane, thread)

    if privacy == "sender" or requests:
        shown = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
        return Note(count_title, _("notify_from", names=shown), lane)
    most = max(1, int(_lines))
    shown = [f"{_who(o)}: {snippet(real(o), 90)}" for o in objs[:most]]
    if n > most:
        shown.append(_("notify_more", n=n - most).strip())
    return Note(count_title, "\n".join(shown), lane)
