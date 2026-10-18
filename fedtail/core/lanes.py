"""Lanes: what the user sees on the left. A lane is a source plus a filter."""

from collections.abc import Callable
from dataclasses import dataclass

from . import taggroups
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
    direct_apart: bool = False  # private messages only in "direct" (lanes.direct_apart)


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


def _is_direct(st):
    return real(st).get("visibility") == "direct"


def _comments(st, ctx):
    if ctx.direct_apart and _is_direct(st):
        return False
    return is_comment_to_me(real(st), ctx.me_id)


def _other_mentions(st, ctx):
    if ctx.direct_apart and _is_direct(st):
        return False
    return ctx.mentions_all or not is_comment_to_me(real(st), ctx.me_id)


def _direct(st, ctx):
    return _is_direct(st)


def _liked(st, ctx):
    return real(st).get("favourited", True)  # un-liked here or elsewhere: gone


def _bookmarked(st, ctx):
    return real(st).get("bookmarked", True)  # un-bookmarked here or elsewhere: gone


def _subs(st, ctx):
    # replies to me are already in "replies"; here goes the rest of the talk
    return ctx.subs_replies_to_me or not is_comment_to_me(real(st), ctx.me_id)


LANES = {
    "home": Lane("home", "home", _people),
    "replies": Lane("replies", "mentions", _comments, by_status_time=True),
    "mentions": Lane("mentions", "mentions", _other_mentions, by_status_time=True),
    "subs": Lane("subs", "subs", _subs, by_status_time=True),
    "bookmarks": Lane("bookmarks", "bookmarks", _bookmarked, lazy=True),
    "my_likes": Lane("my_likes", "favourites", _liked, lazy=True),
    "bots": Lane("bots", "home", _bots),
    "my_posts": Lane("my_posts", "mine", _all),
    # private messages to me: the mentions stream, only what was sent to the named
    "direct": Lane("direct", "mentions", _direct, by_status_time=True),
    "local": Lane("local", "local", _all, lazy=True),
    "federated": Lane("federated", "federated", _all, lazy=True),
    "requests": Lane("requests", None, _all),
    "activity": Lane("activity", None, _all),
}


# lanes once named otherwise (before 0.15): the old names still work wherever a lane is
# named — the config, the command line, what a window remembered
RENAMED = {"people": "home", "comments": "replies", "global": "federated",
           "favourites": "my_likes", "mine": "my_posts"}


def canonical(name):
    """A lane's name as it is now ("people" -> "home"); anything else as it was."""
    return RENAMED.get(name, name) if isinstance(name, str) else name


# the sidebar's sections, in order; a lane goes to the first section that names it,
# lists get their own section, anything else ends up in "more"
GROUPS = [
    ("standard", ["federated", "home", "local", "bots"]),        # from the widest down
    ("personal", ["my_posts", "direct", "mentions", "replies", "subs", "bookmarks", "my_likes",
                  "activity", "requests"]),
    ("lists", []),
    ("tags", []),  # lanes of several hashtags (core/taggroups.py)
]


def grouped(lanes):
    """[(group, [lane names])] for the sidebar, keeping the configured order inside."""
    names = [lane.name for lane in lanes]
    out = []
    placed = set()
    for group, members in GROUPS:
        if group == "lists":
            got = [n for n in names if is_list(n)]
        elif group == "tags":
            got = [n for n in names if taggroups.is_tags(n)]
            if not got:
                continue  # no tag lanes: no "Теги" heading either
        else:
            got = [n for n in names if n in members]
            if group == "standard":
                got += [n for n in names if n not in placed and n not in got
                        and not is_list(n) and not taggroups.is_tags(n)
                        and not any(n in m for _g, m in GROUPS)]
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


def chosen(name, wanted, never=(), title=None):
    """A lane picked by an option pair such as notify.lanes / notify.except or
    ui.icon_count / ui.icon_count_except: `wanted` names it ("all" names every lane)
    and `never` doesn't. Either may name all the lists at once — "lists" — or one by
    its title or id: "list:Друзья". title: this lane's title (a list's), if any."""
    def named(names, everything):
        if name in names or everything and "all" in names:
            return True
        if not is_list(name):
            return False
        picked = {x[len(LIST_PREFIX):].casefold() for x in names if is_list(x)}
        return "lists" in names or (title or "").casefold() in picked \
            or name[len(LIST_PREFIX):].casefold() in picked
    return named(wanted, True) and not named(never, False)


def tag_lane(spec):
    """Several hashtags as one lane: browsed while open, like Federated (no counts)."""
    name = taggroups.lane_name(spec)
    return Lane(name, name, _all, lazy=True)


def enabled(cfg, lists=(), tag_groups=()):
    out = [LANES[n] for n in cfg["lanes"]["enabled"]]
    if cfg["lists"]["enabled"]:
        out += [list_lane(x["id"]) for x in lists]
    seen = set()
    for g in tag_groups:
        lane = tag_lane(g)
        if lane.name not in seen:
            seen.add(lane.name)
            out.append(lane)
    return out


LOCAL_SOURCES = {"subs"}  # filled by the client itself, not a server stream


def sources_needed(lanes):
    return sorted({lane.source for lane in lanes if lane.source} - LOCAL_SOURCES)
