"""Lanes: what the user sees on the left. A lane is a source plus a filter."""

from collections.abc import Callable
from dataclasses import dataclass

from .model import is_bot, is_comment_to_me, real


@dataclass
class Lane:
    name: str
    source: str | None  # None: not a status stream (follow requests)
    keep: Callable  # keep(status, ctx) -> bool
    # order by the post's own time instead of when it reached us (notifications
    # can arrive late or out of order; the card shows the post's time)
    by_status_time: bool = False
    # a lane to browse, not to read through (local, federated): fetched only while
    # it's open, newest page first, no unread marks or badges
    lazy: bool = False


@dataclass
class LaneContext:
    me_id: str
    extra_bots: tuple
    mentions_all: bool = False
    subs_replies_to_me: bool = False
    hidden: frozenset = frozenset()  # authors put in lists: their list shows them…
    hide_in: frozenset = frozenset()  # …and these lanes don't (lists.hide_in)


def _all(st, ctx):
    return True


def _people(st, ctx):
    return not is_bot(st["account"], ctx.extra_bots)


def _bots(st, ctx):
    return is_bot(st["account"], ctx.extra_bots)


def keeps(lane, st, ctx):
    """Does this post belong in this lane? Someone you put in a list (and their
    boosts, and anybody's boost of their posts) leaves the lanes in lists.hide_in:
    the list is where they're read."""
    if lane.name in ctx.hide_in and (st["account"]["id"] in ctx.hidden
                                     or real(st)["account"]["id"] in ctx.hidden):
        return False
    return lane.keep(st, ctx)


def _comments(st, ctx):
    return is_comment_to_me(real(st), ctx.me_id)


def _other_mentions(st, ctx):
    return ctx.mentions_all or not is_comment_to_me(real(st), ctx.me_id)


def _bookmarked(st, ctx):
    return real(st).get("bookmarked", True)  # un-bookmarked here or elsewhere: gone


def _subs(st, ctx):
    # replies to me are already in "comments"; here goes the rest of the talk
    return ctx.subs_replies_to_me or not is_comment_to_me(real(st), ctx.me_id)


LANES = {
    "people": Lane("people", "home", _people),
    "comments": Lane("comments", "mentions", _comments, by_status_time=True),
    "mentions": Lane("mentions", "mentions", _other_mentions, by_status_time=True),
    "subs": Lane("subs", "subs", _subs, by_status_time=True),
    "bookmarks": Lane("bookmarks", "bookmarks", _bookmarked, lazy=True),
    "bots": Lane("bots", "home", _bots),
    "mine": Lane("mine", "mine", _all),
    "local": Lane("local", "local", _all, lazy=True),
    "global": Lane("global", "federated", _all, lazy=True),
    "requests": Lane("requests", None, _all),
    "activity": Lane("activity", None, _all),
}


# the sidebar's sections, in order; a lane goes to the first section that names it,
# lists get their own section, anything else ends up in "more"
GROUPS = [
    ("standard", ["global", "people", "local", "bots"]),        # from the widest down
    ("personal", ["mine", "mentions", "comments", "subs", "bookmarks", "activity",
                  "requests"]),
    ("lists", []),
]


def grouped(lanes):
    """[(group, [lane names])] for the sidebar, keeping the configured order inside."""
    names = [lane.name for lane in lanes]
    out = []
    placed = set()
    for group, members in GROUPS:
        if group == "lists":
            got = [n for n in names if is_list(n)]
        else:
            got = [n for n in names if n in members]
            if group == "standard":
                got += [n for n in names if n not in placed and n not in got
                        and not is_list(n) and not any(n in m for _g, m in GROUPS)]
        placed.update(got)
        out.append((group, got))
    return out


LIST_PREFIX = "list:"


def list_lane(list_id):
    """A server-side list (Mastodon/GoToSocial) shown as a lane of its own."""
    name = LIST_PREFIX + str(list_id)
    return Lane(name, name, _all)


def is_list(name):
    return name.startswith(LIST_PREFIX)


def enabled(cfg, lists=()):
    out = [LANES[n] for n in cfg["lanes"]["enabled"]]
    if cfg["lists"]["enabled"]:
        out += [list_lane(x["id"]) for x in lists]
    return out


LOCAL_SOURCES = {"subs"}  # filled by the client itself, not a server stream


def sources_needed(lanes):
    return sorted({lane.source for lane in lanes if lane.source} - LOCAL_SOURCES)
