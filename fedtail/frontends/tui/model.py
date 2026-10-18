"""What the terminal interface shows and does, without Textual: posts turned into
lines, the Point-style command line carried out. Tested on its own."""

import textwrap
from dataclasses import dataclass, field
from datetime import datetime

from ...core import config
from ...core.commands import parse
from ...core.model import html_to_text, real, reply_mentions, snippet
from ...i18n import _


@dataclass
class Shown:
    """One post as lines: head (who, when, #alias), context (what it answers),
    body (the text, wrapped), foot (media, counters). kind: for colouring."""
    head: list = field(default_factory=list)   # [(kind, text)]
    context: str = ""
    body: list = field(default_factory=list)   # [str]
    cw: str = ""
    foot: str = ""


def when(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    except (ValueError, AttributeError):
        return ""
    today = datetime.now().astimezone().date()
    return dt.strftime("%H:%M") if dt.date() == today else dt.strftime("%d.%m %H:%M")


def show_post(core, wrapper, alias=None, unread=False, number=None, width=80, parent=None):
    """parent: the status this one answers (for the context line), "missing", or None."""
    st = real(wrapper)
    acc = st.get("account") or {}
    tcfg = core.cfg.get("tui", {})
    out = Shown()
    if number is not None:
        out.head.append(("num", f"/{number}" if number else "#"))
    if alias:
        out.head.append(("alias", f"#{alias}"))
    out.head.append(("who", "@" + acc.get("acct", "?")))
    name = (acc.get("display_name") or "").strip()
    if name and name != acc.get("username"):
        out.head.append(("name", name))
    out.head.append(("time", when(st.get("created_at", ""))))
    if wrapper.get("reblog"):
        out.head.append(("boost", "♻ @" + (wrapper.get("account") or {}).get("acct", "?")))
    if st.get("visibility") == "direct":
        out.head.append(("direct", "✉"))
    elif st.get("visibility") == "private":
        out.head.append(("muted", "🔒"))
    if unread:
        out.head.append(("unread", "●"))
    if st.get("in_reply_to_id") and tcfg.get("show_context", True) and number is None:
        if isinstance(parent, dict):
            p = real(parent)
            out.context = "↳ @" + (p.get("account") or {}).get("acct", "?") + ": " + \
                snippet(p, max(20, width - 20))
        elif parent == "missing":
            out.context = "↳ " + _("tui_parent_gone")
        else:
            out.context = "↳ …"
    expand = config.expand_cw(core.cfg)
    if st.get("spoiler_text"):
        out.cw = "⚠ " + st["spoiler_text"]
    if not st.get("spoiler_text") or expand:
        text = html_to_text(st.get("content", ""))
        for para in text.split("\n"):
            out.body += textwrap.wrap(para, max(20, width)) or [""]
        while out.body and not out.body[-1]:
            out.body.pop()
    foot = []
    media = st.get("media_attachments") or []
    if media:
        foot.append(_("cli_media", n=len(media)))
    if st.get("poll"):
        foot.append("📊 " + _("tui_poll"))
    for key, mark in (("replies_count", "↩"), ("reblogs_count", "♻"),
                      ("favourites_count", "★" if st.get("favourited") else "☆")):
        if st.get(key):
            foot.append(f"{mark} {st[key]}")
    if st.get("bookmarked"):
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


class Commands:
    """The command line (core/commands.py), carried out on the core. Each method
    returns a future; done(message) is how the interface hears back."""

    def __init__(self, core):
        self.core = core

    def run(self, line, reply_to=None):
        """(future or None, message or None). reply_to: the post the line answers
        when the interface put "#alias " in front itself (the r key)."""
        core = self.core
        c = parse(line)
        if c.kind == "error":
            return None, _("cmd_unknown")
        if c.kind == "help":
            return None, _("cmd_help")
        if c.kind == "post":
            if not core.cfg["post"]["plain_posts"]:
                return None, _("cmd_unknown")
            return core.post(c.text, core.default_visibility()), _("sent")
        if c.kind in ("follow", "unfollow", "direct", "profile"):
            return self._user(c), None
        if core.by_alias(c.alias) is None:
            return None, _("cmd_no_post", alias=c.alias)
        return self._post(c), None

    def _user(self, c):
        core = self.core

        def job():
            acc = core.find_user(c.user).result()
            if acc is None:
                return _("cmd_no_user", who=c.user)
            if c.kind == "direct":
                core.post(c.text, "direct").result()
                return _("sent")
            if c.kind == "profile":
                return ("profile", acc)
            on = c.kind == "follow"
            core.follow(acc["id"], on).result()
            return _("cmd_followed" if on else "cmd_unfollowed", who=acc["acct"])
        return core.bg.submit(job)

    def _post(self, c):
        core = self.core

        def job():
            st = core.target(c.alias, c.number).result()
            if st is None:
                return _("cmd_no_comment", where=f"#{c.alias}/{c.number}")
            s = real(st)
            if c.kind == "open":
                return ("thread", s["id"])
            if c.kind == "reply":
                text = reply_mentions(s, core.me["acct"]) + c.text
                core.post(text, core.reply_visibility(s), s["id"]).result()
                return _("sent")
            if c.kind in ("sub", "unsub"):
                (core.subscribe if c.kind == "sub" else core.unsubscribe)(s).result()
                return _("subbed" if c.kind == "sub" else "unsubbed")
            if c.kind == "boost":
                core.boost(s).result()
                return _("cmd_boosted")
            if c.kind == "bookmark":
                on = not s.get("bookmarked")
                core.bookmark(s, on).result()
                return _("bookmarked" if on else "unbookmarked")
            if c.kind == "delete":
                return ("delete", s)
            return None
        return core.bg.submit(job)


def lane_label(core, name, width=22):
    title = core.lane_title(name) or _("lane_" + name)
    lane = core.lane_by_name.get(name)
    n = 0 if lane is None or lane.lazy or lane.source is None else core.unread_count(name)
    count = f" {n}" if n else ""
    room = max(4, width - len(count))
    if len(title) > room:
        title = title[:room - 1] + "…"
    return title, n


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
