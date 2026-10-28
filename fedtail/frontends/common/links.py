"""In-app links, `fedtail:<action>/<arg>`, and what each one does.

Cards, profiles and menus speak in these links (richtext.link, the post menu in
common/actions.py); a window hands every link it gets to `Links.open()`. Opening a
place (a thread, a profile, a tag) and anything that needs a dialog stays the window's
job — it is asked through the `host` it passes in; what happens on the core, and in
which order, is decided here, once for every toolkit.

The host is the window. It must have:
  call(future, ok=None, fail=None)   run ok/fail in the GUI thread (the bridge)
  status(text)                       a passing message (the status line)
  error(text)                        a failure to show
  confirm(title, text, then)         ask; then() only on yes (may answer later: GTK)
  open_url(url) open_thread(id, at) open_account(id) open_tag(tag) resolve_link(url)
  copy_handle(handle) put_alias(alias)
  compose(reply_to=None, invite=False, edit=None, quote=None)
  show_history(post) report(post) open_reactions(post, kind) open_quotes(post)
  read_up_to(id) redrafted(redraft)
A host without one of the optional ones (report, open_quotes…) gets a "not here yet"
status instead — the GTK window grows into it stage by stage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import unquote

from ...i18n import _
from ...model.text import snippet
from . import timed

log = logging.getLogger(__name__)

PREFIX = "fedtail:"
# actions whose argument is not a post id
NOT_A_POST = ("account", "tag", "resolve", "alias", "copyhandle", "eventyes", "eventno",
              "eventhide")


@dataclass(frozen=True)
class Link:
    action: str
    arg: str


def parse(url):
    """A fedtail: link as (action, argument), or None for a link to the outside."""
    if not url or not url.startswith(PREFIX):
        return None
    action, _sep, arg = url[len(PREFIX):].partition("/")
    return Link(action, arg)


def make(action, arg):
    return f"{PREFIX}{action}/{arg}"


# where a thread opens (threads.open_at, a lane's open_at): the link says it —
# fedtail:thread/<id> at that post, fedtail:threadnew/<id> at its first unread comment
THREAD_AT = {"post": "thread", "first_unread": "threadnew"}


def thread_url(pid, at="post"):
    """The link opening the thread of post `pid`, standing where `at` says."""
    return make(THREAD_AT.get(at, "thread"), pid)


class Links:
    def __init__(self, view, host):
        self.view, self.host = view, host

    def open(self, url):
        link = parse(url)
        if link is None:
            log.info("link: browser")
            self.host.open_url(url)
            return
        action, arg = link.action, link.arg
        log.info("action %s %s", action, arg if action not in ("tag", "resolve") else "…")
        h = self.host
        if action == "copyhandle":  # someone's @user@server, to call them anywhere
            self._ask(h, "copy_handle", unquote(arg))
        elif action == "alias":  # a post's #abc: into the command line
            self._ask(h, "put_alias", arg)
        elif action == "tag":
            self._ask(h, "open_tag", unquote(arg))
        elif action in ("mutetag", "unmutetag"):  # a hashtag, in one click (Fedilab's way)
            tag, on = unquote(arg).lstrip("#"), action == "mutetag"
            h.call(self.view.mute_tag(tag, on), fail=h.error,
                   ok=lambda _r: h.status(_("tag_muted_msg" if on else "tag_unmuted_msg",
                                            tag=tag)))
        elif action == "resolve":
            self._ask(h, "resolve_link", unquote(arg))
        elif action in ("thread", "threadnew"):
            h.open_thread(arg, "first_unread" if action == "threadnew" else "post")
        elif action == "account":
            self._ask(h, "open_account", arg)
        elif action in ("eventyes", "eventno"):  # a follow request, an approval: answered
            ok = action == "eventyes"
            h.call(self.view.answer_event(unquote(arg), ok),
                   ok=lambda found: h.status(_(("approved" if ok else "rejected") if found
                                               else "approval_gone")),
                   fail=h.error)
        elif action == "eventhide":  # × on an event's row: its events, gone
            h.call(self.view.dismiss_events([unquote(i) for i in arg.split(",") if i]),
                   fail=h.error)
        else:
            post = self.view.by_id(arg)
            if post is None:
                h.error(_("not_in_cache"))
            else:
                self.post_action(action, arg, post)

    @staticmethod
    def _ask(host, name, *args):
        fn = getattr(host, name, None)
        if fn is None:
            host.status(_("gtk_not_yet"))
            return None
        return fn(*args)

    def post_action(self, action, arg, st):
        """The actions on a post (st: the Post)."""
        v, h = self.view, self.host
        if action == "poll":
            h.call(v.refresh_poll(st), fail=h.error)
        elif action == "reply":
            h.compose(reply_to=st)
        elif action == "invite":  # call someone into this thread: a reply naming them
            if v.me:
                h.compose(reply_to=st, invite=True)
        elif action == "edit":
            h.compose(edit=st)
        elif action == "history":
            self._ask(h, "show_history", st)
        elif action == "mute":  # how long, and their notifications too or not
            timed.mute(v, h, st.author)
        elif action == "block":
            acc = st.author
            h.confirm(_("block"), _("block_q", acct=acc.handle),
                      lambda: h.call(v.block(acc.id, True),
                                     ok=lambda _r: h.status(_("blocked_msg",
                                                              acct=acc.handle))))
        elif action == "hidepost":  # this one post, through a filter of the server's
            h.confirm(_("hide_post"), _("hide_post_tip"),
                      lambda: h.call(v.hide_post(st), ok=lambda _r: h.status(_("post_hidden")),
                                     fail=h.error))
        elif action == "bookmark":
            on = not st.mine.bookmarked
            h.call(v.bookmark(st, on),
                   ok=lambda _s: h.status(_("bookmarked" if on else "unbookmarked")))
        elif action == "fav":
            h.call(v.like(st))
        elif action == "boost":
            h.call(v.share(st))
        elif action == "open":
            h.open_url(st.url or st.uri)
        elif action in ("sub", "unsub"):
            sub = action == "sub"
            h.call((v.subscribe if sub else v.unsubscribe)(st),
                   ok=lambda _r: h.status(_("subbed" if sub else "unsubbed")))
        elif action == "report":
            self._ask(h, "report", st)
        elif action == "blockdomain":
            domain = st.author.handle.partition("@")[2]
            if domain:
                h.confirm(_("block_domain", domain=domain), _("block_domain_q", domain=domain),
                          lambda: h.call(v.block_domain(domain, True),
                                         ok=lambda _d: h.status(_("domain_blocked",
                                                                  domain=domain)),
                                         fail=h.error))
        elif action == "quote":
            h.compose(quote=st)
        elif action == "readone":
            v.mark_read([arg])
        elif action == "readupto":
            self._ask(h, "read_up_to", arg)
        elif action in ("favourited_by", "reblogged_by"):
            self._ask(h, "open_reactions", st, action)
        elif action in ("mutethread", "unmutethread"):
            on = action == "mutethread"
            h.call(v.mute_thread(st, on),
                   ok=lambda _s: h.status(_("thread_muted" if on else "thread_unmuted")),
                   fail=h.error)
        elif action == "quotes":
            self._ask(h, "open_quotes", st)
        elif action == "react":  # an emoji of mine on it: the place of reactions
            self._ask(h, "_place", "react", st.id)
        elif action == "why":  # which lanes take it, by which condition (feeds.md §8)
            self._ask(h, "_place", "why", arg or st.id)
        elif action == "raw":  # the post's JSON as the server gave it (debug.raw_json)
            self._ask(h, "_place", "raw", st.id)
        elif action == "around":  # what came just before and after it (feed.around_post)
            self._ask(h, "_place", "around", st.id)
        elif action == "linkposts":  # who else shared the post's link (Mastodon 4.3)
            if st.card and st.card.url:
                self._ask(h, "open_link_posts", st.card.url)
        elif action == "revokequote":
            mine = st.quote.post if st.quote else None
            if mine:
                h.confirm(_("revoke_quote"), _("revoke_quote_q", acct=st.author.handle),
                          lambda: h.call(v.revoke_quote(mine, st),
                                         ok=lambda _s: h.status(_("quote_taken_back")),
                                         fail=h.error))
        elif action in ("pin", "unpin"):
            on = action == "pin"
            h.call(v.pin(st, on), ok=lambda _s: h.status(_("pinned_msg" if on
                                                           else "unpinned_msg")),
                   fail=h.error)
        elif action == "delete":
            h.confirm(_("delete_q_title"), _("delete_q", text=snippet(st, 200)),
                      lambda: h.call(v.delete(st)))
        elif action == "redraft":
            n = len(st.media)
            q = _("redraft_q", text=snippet(st, 200)) + (
                "\n\n" + _("redraft_media", n=n) if n else "")
            h.confirm(_("redraft"), q,
                      lambda: h.call(v.redraft(st), ok=h.redrafted, fail=h.error))
        else:
            log.warning("unknown action %s", action)
