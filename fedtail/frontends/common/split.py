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


# ---- the line's "more": everything the full editor has, reachable from the line -----------

@dataclass(frozen=True)
class More:
    """An item of the input line's ⋯ menu. kind: "here" — done in the line itself (the
    emoji picker); "check" — a switch (on); "choice" — one of several (choices: [(key,
    label)], on: the key chosen); "editor" — done in the full editor, opened with what
    the line holds (its text, warning, visibility, language, files) and that tool."""
    key: str
    label: str
    kind: str = "editor"
    on: object = None
    choices: tuple = ()


def line_more(view, cfg, reply_to=None, media=0, sensitive=False, account=None):
    """The input line's ⋯ menu: what the full editor offers and the line has no room for
    — one list for the Qt and the GTK line (each had what its author thought of: no
    emoji, no poll, no "From", no way to the editor at all, 24.11). media: how many
    files are attached; account: the "From" chosen (None — the one it starts with)."""
    post = cfg.get("post") or {}
    out = [More("emoji", _("emoji_pick"), "here")]
    try:
        accounts, first = view.post_accounts(reply_to)
    except AttributeError:
        accounts, first = [], ""
    if accounts:  # all accounts in one window: which one it goes from
        out.append(More("from", _("dock_from"), "choice",
                        account if account is not None else first,
                        tuple((key, _("post_from", acct=handle)) for key, handle in accounts)))
    if media:
        out.append(More("sensitive", _("sensitive_mark"), "check", bool(sensitive)))
        out.append(More("alt", _("dock_describe")))  # …their focus point, a cover
    else:
        out.append(More("poll", _("poll_add")))      # a poll or pictures, as the server takes
    if post.get("schedule", True):
        out.append(More("schedule", _("schedule")))
    if post.get("drafts_place", True):
        out.append(More("drafts", _("drafts_title")))
    if post.get("preview", True):
        out.append(More("preview", _("preview")))
    out.append(More("editor", _("dock_editor")))
    return out


def line_before_send(cfg, text, media, language):
    """What stands between the input line and Send — the editor's own questions, which
    the line has no room to ask: "alt" — a file goes without its words and
    post.alt_reminder asks about that; "lang" — the text reads as another language than
    the post is marked with (post.lang_check). Either hands the post to the full editor
    (to_editor), which asks. "" — nothing: send."""
    from .compose import lang_mismatch
    post = cfg.get("post") or {}
    if post.get("alt_reminder", True) and any(not (m[1] if len(m) > 1 else "") for m in media):
        return "alt"
    if lang_mismatch(cfg, text, language):
        return "lang"
    return ""


def line_warning_shown(cfg):
    """post.cw_field: the warning's field shown from the start, as in the editor."""
    return bool((cfg.get("post") or {}).get("cw_field", False))


# ---- the line's words kept (post.drafts_autosave) -------------------------------------------

LINE = "line"  # a draft's mark: the input line wrote it, not the full editor


def line_draft(view, target):
    """The draft the line itself left for this post (target: the Post answered, None —
    a new one), or None: with post.drafts_autosave off, with no draft, or with one the
    full editor wrote — that one is the editor's (it may hold a poll, files with their
    words…), the line neither shows it nor writes over it."""
    if not (view.cfg.get("post") or {}).get("drafts_autosave", True):
        return None
    from .compose import draft_key
    d = view.get_draft(draft_key(view, target))
    return d if isinstance(d, dict) and d.get(LINE) else None


def line_keep(view, target, typed, text="", cw="", visibility="", language=None):
    """What the line holds, kept as the draft the full editor would open for the same
    post — words typed survive a crash, as the editor's do (the line kept nothing,
    24.11). typed: are there words of the reader's (not only the mentions put in)?
    Nothing typed — the line's own draft goes. A draft the editor wrote is left alone.
    → the draft's key when the line's draft stands (sent with the post, the core drops
    it then), else None."""
    if not (view.cfg.get("post") or {}).get("drafts_autosave", True):
        return None
    from .compose import draft_key, snapshot
    key = draft_key(view, target)
    had = view.get_draft(key)
    if had and not (isinstance(had, dict) and had.get(LINE)):
        return None  # the editor's own
    if not typed:
        if had:
            view.delete_draft(key)
        return None
    view.save_draft(key, dict(snapshot(text, cw, visibility, [], language, False, None),
                              **{LINE: True}))
    return key
