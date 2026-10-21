"""The Point-style command line (core/commands.py has the grammar), carried out on the
core, and what it says while you type — for every interface: the terminal, the web
page, the Qt and the GTK windows."""

from ...core.commands import parse
from ...i18n import _
from ...model.text import reply_mentions, snippet
from .actions import vis_word


class Failed(str):
    """A result that says it didn't work: the line stays for mending."""


def preview(core, text):
    """What Enter will do with text, in words ("" for an empty line): which post a reply
    goes to, who will see a new post — so nothing is sent by surprise."""
    if not text.strip():
        return ""
    c = parse(text)
    if c.kind in ("open", "reply", "sub", "unsub", "boost", "bookmark", "delete"):
        st = core.by_alias(c.alias)
        if st is None:
            return _("cmd_no_post", alias=c.alias) + (
                " " + _("cmd_as_post") if c.kind == "reply" and
                core.cfg["post"]["plain_posts"] else "")
        where = f"#{c.alias}" + (f"/{c.number}" if c.number else "")
        return _("cmd_do_" + c.kind, where=where, who=st.author.handle,
                 text=snippet(st, 50), vis=vis_word(core.reply_visibility(st)))
    if c.kind in ("follow", "unfollow", "profile", "direct"):
        return _("cmd_do_" + c.kind, who=c.user)
    if c.kind == "post":
        return _("cmd_do_post", vis=vis_word(core.default_visibility())) \
            if core.cfg["post"]["plain_posts"] else _("cmd_unknown")
    if c.kind == "help":
        return _("cmd_do_help")
    return _("cmd_unknown")


class History:
    """↑ and ↓ through the lines run before."""

    def __init__(self):
        self.lines, self.pos = [], 0

    def add(self, line):
        if line.strip() and (not self.lines or self.lines[-1] != line):
            self.lines.append(line)
        self.pos = len(self.lines)

    def up(self):
        if not self.lines:
            return None
        self.pos = max(0, self.pos - 1)
        return self.lines[self.pos]

    def down(self):
        if not self.lines:
            return None
        self.pos = min(len(self.lines), self.pos + 1)
        return self.lines[self.pos] if self.pos < len(self.lines) else ""


class Commands:
    """The command line (core/commands.py), carried out on the core (a core.view.View).
    Each method returns a future; done(message) is how the interface hears back.
    Results: a message, ("thread", post id), ("profile", Account), ("delete", Post),
    or the Post made."""

    def __init__(self, core):
        self.core = core

    def run(self, line, reply_to=None, unknown_as_post=False):
        """(future or None, message or None). reply_to: the post the line answers
        when the interface put "#alias " in front itself (the r key). unknown_as_post:
        "#abc text" with no such post goes out as a post (post.plain_posts) — the
        window's command line does that; a terminal says there's no such post."""
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
            if unknown_as_post and c.kind == "reply" and core.cfg["post"]["plain_posts"]:
                return core.post(line.strip(), core.default_visibility()), _("sent")
            return None, _("cmd_no_post", alias=c.alias)
        return self._post(c), None

    def _user(self, c):
        core = self.core

        def job():
            acc = core.find_user(c.user).result()
            if acc is None:
                return Failed(_("cmd_no_user", who=c.user))
            if c.kind == "direct":
                core.post(c.text, "direct").result()
                return _("sent")
            if c.kind == "profile":
                return ("profile", acc)
            on = c.kind == "follow"
            core.follow(acc.id, on).result()
            return _("cmd_followed" if on else "cmd_unfollowed", who=acc.handle)
        return core.bg.submit(job)

    def _post(self, c):
        core = self.core

        def job():
            p = core.target(c.alias, c.number).result()
            if p is None:
                return Failed(_("cmd_no_comment", where=f"#{c.alias}/{c.number}"))
            if c.kind == "open":
                return ("thread", p.id)
            if c.kind == "reply":
                me = core.me
                text = reply_mentions(p, me.handle if me else "") + c.text
                core.post(text, core.reply_visibility(p), p).result()
                return _("sent")
            if c.kind in ("sub", "unsub"):
                (core.subscribe if c.kind == "sub" else core.unsubscribe)(p).result()
                return _("subbed" if c.kind == "sub" else "unsubbed")
            if c.kind == "boost":
                core.share(p).result()
                return _("cmd_boosted")
            if c.kind == "bookmark":
                on = not p.mine.bookmarked
                core.bookmark(p, on).result()
                return _("bookmarked" if on else "unbookmarked")
            if c.kind == "delete":
                return ("delete", p)
            return None
        return core.bg.submit(job)
