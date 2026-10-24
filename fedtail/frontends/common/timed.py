"""Choices that have a time or a kind to them, the same in every interface: how long a
mute or a filter lasts, which of someone's posts a profile shows, whose replies a list
shows. And muting with those choices asked through the host.

The host asks with ``choose(title, text, options, done, check=None)``: options are
(key, label) pairs, check an optional tick-box label; done(key, ticked) is called with
what was picked (never, when the question is closed). A host without ``choose``
mutes for good at once, as before."""

import time

from ...i18n import _
from ...model import Share, real

# (seconds, i18n key); 0 — for good
SPANS = ((0, "span_ever"), (3600, "span_hour"), (86400, "span_day"),
         (7 * 86400, "span_week"), (30 * 86400, "span_month"))

# what a profile shows under its header: the key the View's account_posts(show=) takes
PROFILE_SHOWS = (("posts", "profile_show_posts"), ("all", "profile_show_all"),
                 ("media", "profile_show_media"))

# whose replies a list's lane shows (the server's replies_policy)
REPLIES_POLICIES = (("list", "replies_policy_list"), ("followed", "replies_policy_followed"),
                    ("none", "replies_policy_none"))


def spans():
    """[(seconds, label)] for a "how long" question."""
    return [(secs, _(key)) for secs, key in SPANS]


def profile_shows():
    return [(key, _(label)) for key, label in PROFILE_SHOWS]


def replies_policies():
    return [(key, _(label)) for key, label in REPLIES_POLICIES]


def profile_show(cfg):
    """What a profile shows first, from feed.profile_show."""
    got = (cfg or {}).get("feed", {}).get("profile_show", "posts")
    return got if got in dict(PROFILE_SHOWS) else "posts"


def until(secs, now=None):
    """When something that lasts secs from now ends, as people read it ("" — never)."""
    if not secs:
        return ""
    return time.strftime("%d.%m %H:%M", time.localtime((now or time.time()) + secs))


def filter_bits(f):
    """What else a filter says, as words: how many single posts it hides, when it ends."""
    out = []
    if f.posts:
        out.append(_("posts_n", n=f.posts))
    if f.expires is not None:
        out.append(_("filter_until", until=f.expires.astimezone().strftime("%d.%m.%Y %H:%M")))
    return out


def filter_extra(f):
    """filter_bits as a tail for a line ("" or " · …")."""
    return "".join(" · " + b for b in filter_bits(f))


def keeps(entry, show, acc_id):
    """Is this post of acc_id's one the profile shows with show? Posts from their own
    server come unfiltered: the same rule as the server's (replies only to themselves
    in "posts"; own posts with pictures in "media")."""
    if show == "all":
        return True
    p = real(entry)
    if show == "media":
        return not isinstance(entry, Share) and bool(p.media)
    return not p.reply_to or p.reply_to_author == acc_id


KEEP = -1  # the term as it is (a filter edit's first choice)


def filter_changes(title, words, action, contexts, span):
    """The edit window's answer as view.edit_filter's arguments (span KEEP: the term
    stays; 0: for good)."""
    return {"title": title.strip() or None,
            "words": [x.strip() for x in words.split(",") if x.strip()],
            "action": action, "contexts": list(contexts) or ["home"],
            "expires_in": None if span == KEEP else int(span or 0)}


def mute(view, host, acc, done=None):
    """Mute acc, asking how long and whether their notifications still come. done(r)
    when the server said yes (r: what view.mute gave)."""
    def go(secs, posts_only=False):
        def ok(r):
            if secs:
                host.status(_("muted_for_msg", acct=acc.handle, until=until(secs)))
            else:
                host.status(_("muted_msg", acct=acc.handle))
            if done:
                done(r)
        host.call(view.mute(acc.id, True, duration=secs, notifications=not posts_only), ok)
    choose = getattr(host, "choose", None)
    if choose is None:
        go(0)
        return
    choose(_("mute_acct", acct=acc.handle), _("mute_for_q", acct=acc.handle), spans(),
           lambda secs, ticked: go(int(secs or 0), bool(ticked)), check=_("mute_posts_only"))


__all__ = ["KEEP", "PROFILE_SHOWS", "REPLIES_POLICIES", "SPANS", "filter_bits",
           "filter_changes", "filter_extra",
           "keeps", "mute", "profile_show",
           "profile_shows", "replies_policies", "spans", "until"]
