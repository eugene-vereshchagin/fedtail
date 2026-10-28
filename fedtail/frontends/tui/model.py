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
    above: list = field(default_factory=list)  # [(kind, text)] over the head: boosted
    colors: dict = field(default_factory=dict)  # {kind: "#rrggbb"}: my colour for a name
    below: list = field(default_factory=list)  # [(kind, text)] under the text: a quote,
    #                                            reactions, "you replied", a conversation


def when(t):
    if t is None:
        return ""
    dt = t.astimezone()
    today = datetime.now().astimezone().date()
    return dt.strftime("%H:%M") if dt.date() == today else dt.strftime("%d.%m %H:%M")


def poll_line(poll, date=None):
    """A poll in words, as the windows' card says it: how many (people or votes), closed
    or until when, several may be picked."""
    date = date or when
    people = getattr(poll, "people", poll.voters)
    n = people if people is not None else poll.votes
    parts = [_("poll_people" if people is not None else "poll_votes", n=n)]
    if poll.expired:
        parts.append(_("poll_closed"))
    elif poll.expires is not None:
        parts.append(_("poll_until", when=date(poll.expires)))
    if poll.multiple and not poll.expired:
        parts.append(_("poll_multiple"))
    return " · ".join(parts)


def show_post(core, entry, alias=None, unread=False, number=None, width=80, parent=None,
              spec=None, open_cw=False):
    """entry: a Post or a Share (core.view). parent: the Post this one answers (for the
    context line), "missing", or None. spec: its CardSpec (common/lane.py) — the card's
    words then are the windows' (common/cardtext.py): who boosted it and when, edited,
    old, the warning a filter folds, the quote, reactions, "you replied", the
    conversation. open_cw: the text under a warning shown too (a thread's "open every
    CW")."""
    p = real(entry)
    acc = p.author
    tcfg = core.cfg.get("tui", {})
    out = Shown()
    words = None
    if spec is not None:
        from ..common.cardtext import card_words
        words = card_words(spec, core.cfg, when, in_thread=number is not None)
    if number is not None:
        out.head.append(("num", f"/{number}" if number else "#"))
    if alias:
        out.head.append(("alias", f"#{alias}"))
    out.head.append(("who", "@" + (acc.handle or "?")))
    name = acc.name.strip()
    if name and name != acc.username:
        out.head.append(("name", name))
    if acc.color:  # people.nick_colors: who in my colour for them
        out.colors["who"] = out.colors["name"] = acc.color
    out.head.append(("time", when(p.created)))
    if words is not None:
        if words.boosted is not None:
            out.above.append(("boost", words.boosted.text))
        if words.newcomer is not None:  # someone new in a private talk
            out.above.append(("newcomer", words.newcomer.text))
        for b in words.meta:
            if b.kind in ("edited", "old", "deleted"):
                out.head.append(("muted", b.text))
    elif isinstance(entry, Share):
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
    if words is not None and words.warning:
        out.cw = words.warning
    elif p.warning:
        out.cw = "⚠ " + p.warning
    folded = words is not None and words.folded
    if (not p.warning and not folded) or ((config.expand_cw(core.cfg) or open_cw)
                                          and not folded):
        for para in html_to_text(p.text).split("\n"):
            out.body += textwrap.wrap(para, max(20, width)) or [""]
        while out.body and not out.body[-1]:
            out.body.pop()
    foot = []
    if p.media:
        foot.append(_("cli_media", n=len(p.media)))
    if p.poll:
        foot.append("📊 " + _("tui_poll") + ": " + poll_line(p.poll))
    for n, mark in ((p.counts.replies, "↩"), (p.counts.shares, "♻"),
                    (p.counts.likes, "★" if p.mine.liked else "☆")):
        if n:
            foot.append(f"{mark} {n}")
    if p.mine.bookmarked:
        foot.append("🔖")
    via = _via(core, entry)
    if via:  # every account in one window: the one that got it (and acts on it)
        foot.append("⇄ " + via)
    out.foot = "  ".join(foot)
    if words is not None:
        if words.quote is not None:
            out.below.append(("quote", words.quote.text))
        if words.reactions:
            out.below.append(("muted", words.reactions))
        for b in words.my_replies:
            out.below.append(("myreply", b.text))
        if words.conversation is not None:
            out.below.append(("conv", words.conversation.text))
        if words.thread_news is not None:
            out.below.append(("newcomer", words.thread_news.text))
    return out


def _via(core, entry):
    try:
        return core.via(entry) or ""
    except (AttributeError, TypeError):  # a core without accounts merged (a fake)
        return ""


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
    """(title, number) of a lane's row on the left. The number is the core's for every
    lane alike (common/sidebar.count): unread posts, events not seen in a lane that
    takes them; nothing for a browse lane."""
    from ..common import sidebar
    title = core.lane_title(name) or _("lane_" + name)
    n = sidebar.count(core, name)
    count = f" {n}" if n else ""
    room = max(4, width - len(count))
    if len(title) > room:
        title = title[:room - 1] + "…"
    return title, n


def event_lines(parts):
    """An event's row (common/activity.EventParts) as lines of (kind, text, link):
    who (each name opens the person) — what · when, × (hides the row), a request's
    yes / no, the post it is about (opens its thread). Every link is a fedtail: one
    (common/links.py); link None — just words. The same parts the windows draw."""
    from ..common.activity import ANSWER_WORDS
    top = []
    if parts.notice:  # from the server itself: what happened, not who did it
        top.append(("notice", "⚠ " + parts.notice, None))
    else:
        for i, (who, link) in enumerate(parts.people):
            if i:
                top.append(("muted", ", ", None))
            top.append(("who", who, link))
        if parts.more:
            top.append(("name", " " + parts.more, None))
    top.append(("muted", " — " + parts.what + (f" · {parts.when}" if parts.when else ""),
                None))
    if parts.unread:
        top.append(("unread", " ●", None))
    top.append(("hide", "  [×]", parts.hide))
    lines = [top]
    for yes, no in parts.answers:  # waiting for my yes: answered right here
        line = []
        for url, (words, _tip) in zip((yes, no), ANSWER_WORDS, strict=True):
            if line:
                line.append(("muted", " ", None))
            line.append(("yes" if url == yes else "no", f"[{_(words)}]", url))
        lines.append(line)
    if parts.post:
        lines.append([("event_post", parts.post, parts.post_link)])
    if parts.answers:
        lines.append([("muted", _("tui_request_keys"), None)])
    return lines


def ordered_lanes(core):
    """[(group title or None, [lane names])] in the window's sidebar order
    (ui.sidebar_groups: with section titles, or without)."""
    return [(title, names) for _key, title, names in lane_groups(core)]


def lane_groups(core):
    """[(group key or None, its title or None, [lane names])]: the sections of the
    windows' sidebar (common/sidebar.py folds them by key)."""
    from ...core import lanes as lanes_module
    groups = lanes_module.grouped(core.lanes)
    if not core.cfg["ui"]["sidebar_groups"]:
        return [(None, None, [n for _g, names in groups for n in names])]
    out = []
    for group, names in groups:
        if names:
            out.append((group, _("lists_header") if group == "lists" else
                        _("grp_" + group), names))
    return out


def start_lane(core, names):
    """The lane to open first: the one of last time, else Home, else the first."""
    want = core.get_state("lane")
    if want in names:
        return want
    return "home" if "home" in names else (names[0] if names else None)
