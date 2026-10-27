"""The Activity lane, without a toolkit: which notifications become one row (one kind,
one post, side by side), what a row says (who — the first few names and "and N more" —
what, when, about which post), and the server's own notices in words. qt/feed.py
ActivityWidget and the GTK window draw these rows."""

from __future__ import annotations

from dataclasses import dataclass

from ...core.view import ACTIVITY_FILTERS as FILTERS  # the quick filters over Activity
from ...core.view import ACTIVITY_STATE as STATE
from ...core.view import activity_keeps as keeps  # noqa: F401 — for the interfaces
from ...i18n import _

MAX_NAMES = 3

# the i18n words a row of activity can say (act_<key>); a row's "kind" is the key
ACT_KINDS = tuple(k[4:] for k in (
    "act_favourite", "act_reblog", "act_follow", "act_poll", "act_update", "act_status",
    "act_pending.reply", "act_pending.favourite", "act_pending.reblog",
    "act_severed_relationships", "act_moderation_warning", "act_follow_request",
    "act_my_follow", "act_unfollow", "act_gone", "act_lost"))

# fedtail.model's kinds → the words for them in i18n (act_<key>)
_ACT_KEY = {"like": ACT_KINDS[0], "share": ACT_KINDS[1], "follow": ACT_KINDS[2],
            "poll": ACT_KINDS[3], "update": ACT_KINDS[4], "post": ACT_KINDS[5],
            "my_follow": ACT_KINDS[12], "unfollow": ACT_KINDS[13], "gone": ACT_KINDS[14],
            "lost": ACT_KINDS[15]}
_ASKS_KEY = {"reply": ACT_KINDS[6], "like": ACT_KINDS[7], "share": ACT_KINDS[8],
             "follow": ACT_KINDS[11]}
_NOTICE_KEY = {"severed": ACT_KINDS[9], "warning": ACT_KINDS[10]}


def act_key(a):
    """An Activity's key among ACT_KINDS (or its model kind, for the others)."""
    if a.kind == "request":
        return _ASKS_KEY.get(a.asks, "request")
    if a.kind == "notice":
        return _NOTICE_KEY.get(a.details.kind if a.details else "", "notice")
    return _ACT_KEY.get(a.kind, a.kind)


def notice_text(n):
    """What the server's own notice (a Notice) says: follows cut by a block, a
    moderators' warning."""
    if n.kind == "severed":
        return _("act_severed", target=n.target or "?", n=n.lost,
                 why=_("severed_" + (n.reason or "domain_block")))
    if n.kind == "warning":
        return _("act_warning", action=_("warn_" + (n.action or "none")), text=n.text[:300])
    return ""


def filter_words(which):
    """(words, tip) of a quick filter."""
    return _("actf_" + which), _("actf_" + which + "_tip")


def chosen(view):
    got = view.get_state(STATE) if hasattr(view, "get_state") else None
    return got if got in FILTERS else "all"


def groups(entries):
    """Neighbouring Activity of one kind about one post become one row."""
    out = []
    for a in entries:
        key = (act_key(a), a.post.id if a.post else None)
        if out and out[-1]["key"] == key:
            out[-1]["entries"].append(a)
        else:
            out.append({"key": key, "entries": [a]})
    return out


def who_of(entries):
    """([Account] each once, newest first; how many in all) of a row's entries: each
    entry's person and the people a server's group names — and a server's group counts
    those it doesn't name too (300 likes, 8 people given)."""
    people = list({p.id: p for a in entries
                   for p in ((a.who,) if a.who is not None else ()) + tuple(a.people)
                   }.values())
    in_groups = {p.id for a in entries if a.people for p in a.people}
    total = max(len(people), sum(a.count for a in entries if a.people) +
                sum(1 for p in people if p.id not in in_groups))
    return people, total


@dataclass
class Row:
    kind: str          # act_key of its first entry
    what: str          # the words for the kind
    people: list       # [Account] who did it, each once, in order
    more: int          # how many beyond MAX_NAMES
    when: str          # the newest time, and since when when they came over a while
    notice: str        # the server's own notice in words, or ""
    post: object       # the Post it's about, or None
    entries: list      # the Activity in it
    newest_sort: str   # for what's seen (mark_activity_seen)
    unread: bool
    request: bool      # waiting for my yes (an interaction to approve)


def event_bit(entries, date):
    """An event (or several of one kind about one post) as one line in a lane of posts
    (a lane of rules with `event`, feeds.md §2.3): who — what · when: about which post.
    A Bit of common/cardtext: the line, where a click goes, a tip."""
    from ...model.text import snippet
    from .cardtext import Bit, name_of
    first = entries[0]
    kind = act_key(first)
    people, total = who_of(entries)
    more = total - min(len(people), MAX_NAMES)
    who = ", ".join(name_of(p) for p in people[:MAX_NAMES]) + \
        (" " + _("act_more", n=more) if more > 0 else "")
    if first.kind == "notice" and first.details is not None:
        who = "⚠ " + notice_text(first.details)
    what = _("act_" + kind) if kind in ACT_KINDS else kind
    times = sorted(a.created for a in entries if a.created)
    text = f"{who} — {what}" + (f" · {date(times[-1])}" if times else "")
    if first.post is not None:
        text += " · «" + snippet(first.post, 80) + "»"
        link = f"fedtail:thread/{first.post.id}"
    else:
        link = f"fedtail:account/{people[0].id}" if people else ""
    tip = "\n".join(f"{date(a.created) if a.created else ''}  "
                     f"{'@' + a.who.handle if a.who else ''}" for a in entries[:30])
    return Bit(text, link, tip, kind="event:" + kind)


def rows(entries, seen, date, oldest_first=True):
    """The lane's rows: entries newest first (as View.activity gives them), seen — the
    mark up to which they're seen, date(datetime) — the theme's way of writing a time."""
    out = []
    for g in groups(entries):
        es = g["entries"]
        first = es[0]
        kind = act_key(first)
        people, total = who_of(es)
        times = sorted((a.created for a in es if a.created), reverse=True)
        when = date(times[0]) if times else ""
        if len(times) > 1 and date(times[-1]) != when:
            when = f"{date(times[-1])} … {when}"
        notice = notice_text(first.details) if first.kind == "notice" and \
            first.details is not None else ""
        out.append(Row(kind, _("act_" + kind) if kind in ACT_KINDS else kind,
                       people[:MAX_NAMES], max(0, total - min(len(people), MAX_NAMES)), when,
                       notice,
                       first.post, es, max(a.sort for a in es),
                       any(a.sort > seen for a in es), first.kind == "request"))
    if oldest_first:
        out.reverse()
    return out
