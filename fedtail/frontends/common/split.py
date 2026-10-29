"""The split layout (a messenger's look: lanes in one window, the messages and an
input line in another, docs/en/dev/layouts.md) without a toolkit: what the input line starts
with and says about itself, when what's typed there is a command, whose face goes
beside it, and a private talk with one person."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ...i18n import _
from ...model import real
from ...model.text import norm_handle, reply_mentions
from .actions import VIS_KEY

# a Point-style command in the input line: "#a3f", "#a3f text", "! #a3f", "S #a3f", "?"
COMMAND = re.compile(r"^(#[a-z][0-9a-z]{2,}|[!~?]|[SUD]\s+[#@])")


@dataclass
class Start:
    """What the input line holds when it starts on something: the text put in for the
    reader (mentions), the visibility (None: keep it), the words about where it goes,
    and whom it goes to (for the face)."""
    prefill: str
    visibility: str | None
    about: str
    whom: object = None


def reply_start(view, post):
    """Answering post (None: a new post of my own)."""
    me = view.me
    if post is None:
        return Start("", view.reply_visibility(None), _("dock_new"))
    return Start(reply_mentions(post, me.handle if me else ""), view.reply_visibility(post),
                 _("dock_reply", name=post.author.username), post.author)


def private_start(account):
    """A private message to someone: "@them ", direct."""
    return Start("@" + account.handle + " ", "direct",
                 _("dock_private", name=account.username or account.handle), account)


def about_line(about, visibility):
    """Above the line, in words: where this goes and who will see it — "in the thread:
    a reply to andy · seen by: followers"."""
    vis = _("vis_short_" + VIS_KEY.get(visibility, visibility))
    return f"{about} · {_('dock_seen_by', who=vis)}"


def command(text, prefill, cfg):
    """The text, when it is a command for the command line (ui.dock_commands) — one
    line, not just what was put in; "@user …" stays a post (a reply begins with it)."""
    text = text.strip()
    if not cfg["ui"].get("dock_commands", True) or "\n" in text or text == prefill.strip():
        return None
    return text if COMMAND.match(text) else None


def faces_mode(cfg, shape):
    """How faces are shown: the theme's shape.faces ("qip", "agent", "none"); "none"
    with ui.faces = false."""
    if not cfg["ui"].get("faces", True):
        return "none"
    return shape.get("faces", "qip")


def face(mode, account, me):
    """Whose face goes beside the line: whom it goes to (nobody for my own post), or,
    as the Agent had it ("agent"), mine whoever it goes to."""
    if mode == "agent":
        return me
    if mode == "none":
        return None
    if account is not None and me is not None and account.id == me.id:
        return None
    return account


def other_side(post, me, target=None):
    """The account on the other side of what's being read: the author of post — and
    when that's mine (or nothing is), whom I answer (target, the post I reply to)."""
    if (post is None or (me and post.author.id == me.id)) and target is not None:
        post = target
    if post is None or (me and post.author.id == me.id):
        return None
    return post.author


def talk_with(view, entries, handle):
    """The entries of a private lane that are between me and this one person only:
    written by them to me alone, or by me to them alone."""
    me = norm_handle(view.me.handle) if view.me else ""
    them = norm_handle(handle)
    out = []
    for item, e in entries:
        p = real(e)
        people = {norm_handle(p.author.handle)} | {norm_handle(m.handle) for m in p.mentions}
        people.discard(me)
        if people == {them}:
            out.append((item, e))
    return out


def talk(view, handle, sent=()):
    """A private talk with one person, as the chat window shows it: [(item, post)] by
    the posts' own time — what the lanes of private messages hold between us (the core's
    private_lanes: by their rules, whatever their names), and my messages just sent
    (`sent`, posts) that no lane has yet — and which of them are unread. ([], set())
    when no lane takes private messages."""
    lanes = view.private_lanes() if hasattr(view, "private_lanes") else []
    mine, have = [], set()
    for lane in lanes:
        for item, e in talk_with(view, view.entries(lane), handle):
            if e.id not in have:
                have.add(e.id)
                mine.append((item, e))
    if not lanes:
        return [], set()
    mine += [(None, p) for p in sent if p.id not in have]
    mine.sort(key=lambda x: (x[1].created is not None, x[1].created or 0))
    return mine, view.unread([e for _i, e in mine])

