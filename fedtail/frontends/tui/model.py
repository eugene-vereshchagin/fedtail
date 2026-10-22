"""What the terminal interface shows and does, without Textual: posts turned into
lines, the Point-style command line carried out. Tested on its own."""

import textwrap
from dataclasses import dataclass, field
from datetime import datetime

from ...core import config
from ...i18n import _
from ...model import Share, real
from ...model.text import html_to_text, snippet
from ..common.commands import Commands  # noqa: F401 — the TUI's, now shared


@dataclass
class Shown:
    """One post as lines: head (who, when, #alias), context (what it answers),
    body (the text, wrapped), foot (media, counters). kind: for colouring."""
    head: list = field(default_factory=list)   # [(kind, text)]
    context: str = ""
    body: list = field(default_factory=list)   # [str]
    cw: str = ""
    foot: str = ""


def when(t):
    if t is None:
        return ""
    dt = t.astimezone()
    today = datetime.now().astimezone().date()
    return dt.strftime("%H:%M") if dt.date() == today else dt.strftime("%d.%m %H:%M")


def show_post(core, entry, alias=None, unread=False, number=None, width=80, parent=None):
    """entry: a Post or a Share (core.view). parent: the Post this one answers (for the
    context line), "missing", or None."""
    p = real(entry)
    acc = p.author
    tcfg = core.cfg.get("tui", {})
    out = Shown()
    if number is not None:
        out.head.append(("num", f"/{number}" if number else "#"))
    if alias:
        out.head.append(("alias", f"#{alias}"))
    out.head.append(("who", "@" + (acc.handle or "?")))
    name = acc.name.strip()
    if name and name != acc.username:
        out.head.append(("name", name))
    out.head.append(("time", when(p.created)))
    if isinstance(entry, Share):
        out.head.append(("boost", "♻ @" + (entry.by.handle or "?")))
    if p.visibility == "direct":
        out.head.append(("direct", "✉"))
    elif p.visibility == "followers":
        out.head.append(("muted", "🔒"))
    if unread:
        out.head.append(("unread", "●"))
    if p.reply_to and tcfg.get("show_context", True) and number is None:
        if parent == "missing":
            out.context = "↳ " + _("tui_parent_gone")
        elif parent is not None:
            out.context = "↳ @" + (parent.author.handle or "?") + ": " + \
                snippet(parent, max(20, width - 20))
        else:
            out.context = "↳ …"
    if p.warning:
        out.cw = "⚠ " + p.warning
    if not p.warning or config.expand_cw(core.cfg):
        for para in html_to_text(p.text).split("\n"):
            out.body += textwrap.wrap(para, max(20, width)) or [""]
        while out.body and not out.body[-1]:
            out.body.pop()
    foot = []
    if p.media:
        foot.append(_("cli_media", n=len(p.media)))
    if p.poll:
        foot.append("📊 " + _("tui_poll"))
    for n, mark in ((p.counts.replies, "↩"), (p.counts.shares, "♻"),
                    (p.counts.likes, "★" if p.mine.liked else "☆")):
        if n:
            foot.append(f"{mark} {n}")
    if p.mine.bookmarked:
        foot.append("🔖")
    out.foot = "  ".join(foot)
    return out


class DeleteGuard:
    """D #id deletes when it is said twice in a row about the same post, within a
    little while: the first time only asks (Enter again — gone)."""
    WINDOW = 30  # s

    def __init__(self, clock=None):
        import time
        self.clock = clock or time.monotonic
        self.asked = None  # (status id, when)

    def confirmed(self, sid):
        now = self.clock()
        if self.asked and self.asked[0] == sid and now - self.asked[1] <= self.WINDOW:
            self.asked = None
            return True
        self.asked = (sid, now)
        return False


def lane_label(core, name, width=22):
    title = core.lane_title(name) or _("lane_" + name)
    lane = core.lane_by_name.get(name)
    if name == "activity":  # not posts: its own "seen" mark
        n = _safe(lambda: core.activity_unread())
    elif name == "requests":
        n = _safe(lambda: len(core.follow_requests()))
    else:
        n = 0 if lane is None or lane.lazy or lane.source is None else core.unread_count(name)
    count = f" {n}" if n else ""
    room = max(4, width - len(count))
    if len(title) > room:
        title = title[:room - 1] + "…"
    return title, n


def _safe(fn):
    try:
        return int(fn() or 0)
    except (AttributeError, TypeError, ValueError):  # a core without it (an old fake)
        return 0


# Activity.kind → what the line says (the Qt window's words where it has them)
ACTIVITY_WORD = {"like": "act_favourite", "share": "act_reblog", "follow": "act_follow",
                 "poll": "act_poll", "update": "act_update", "post": "act_status",
                 "mention": "act_mention", "quote": "act_quote", "reaction": "act_reaction",
                 "follow_request": "act_follow_request"}


def show_activity(a, width=80, unread=False):
    """One activity row (an Activity of core.view) as Shown: who, what, when; the post
    it is about below, in a line."""
    out = Shown()
    if a.who is not None:
        out.head.append(("who", "@" + (a.who.handle or "?")))
        name = (a.who.name or "").strip()
        if name and name != a.who.username:
            out.head.append(("name", name))
    word = ACTIVITY_WORD.get(a.kind)
    if a.kind == "reaction" and a.emoji:
        what = f"{a.emoji} " + _("act_reaction")
    elif a.kind == "notice":
        what = a.notice or _("act_other")
    else:
        what = _(word) if word else _("act_other")
    out.head.append(("boost", what))
    if a.count > 1:  # a server's group: the rest of them
        out.head.append(("time", _("act_more", n=a.count - 1)))
    out.head.append(("time", when(a.created)))
    if unread:
        out.head.append(("unread", "●"))
    if a.post is not None:
        out.body = [snippet(a.post, max(20, width))]
    return out


def show_request(acc, width=80):
    """A follow request as Shown: who asks; a / d — accept / reject."""
    out = Shown()
    out.head.append(("who", "@" + (acc.handle or "?")))
    name = (acc.name or "").strip()
    if name and name != acc.username:
        out.head.append(("name", name))
    note = html_to_text(acc.note or "").strip()
    if note:
        out.body = textwrap.wrap(note, max(20, width))[:3]
    out.foot = _("tui_request_keys")
    return out


def ordered_lanes(core):
    """[(group title or None, [lane names])] in the window's sidebar order
    (ui.sidebar_groups: with section titles, or without)."""
    from ...core import lanes as lanes_module
    groups = lanes_module.grouped(core.lanes)
    if not core.cfg["ui"]["sidebar_groups"]:
        return [(None, [n for _g, names in groups for n in names])]
    out = []
    for group, names in groups:
        if names:
            out.append((_("lists_header") if group == "lists" else _("grp_" + group), names))
    return out


def start_lane(core, names):
    """The lane to open first: the one of last time, else Home, else the first."""
    want = core.get_state("lane")
    if want in names:
        return want
    return "home" if "home" in names else (names[0] if names else None)
