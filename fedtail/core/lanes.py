"""Lanes: what the user sees on the left. A lane is a source plus a filter."""

from collections.abc import Callable
from dataclasses import dataclass

from . import langs, taggroups
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
    # a free lane (core/custom.py): the real sources its own stream is filled from
    feeds: tuple = ()


@dataclass
class LaneContext:
    me_id: str
    extra_bots: tuple
    mentions_all: bool = False
    subs_replies_to_me: bool = False
    hidden: frozenset = frozenset()  # authors put in lists: their list shows them…
    hide_in: frozenset = frozenset()  # …and these lanes don't (lists.hide_in)
    direct_apart: bool = False  # private messages only in "direct" (lanes.direct_apart)
    languages: frozenset = frozenset()  # lanes.languages: the ones I read (empty — all)
    languages_in: frozenset = frozenset()  # …in these lanes ("lists", "tags": all of them)
    detect: str = "untagged"  # lanes.detect_language
    min_words: int = 12  # lanes.detect_min_words
    bots_in_home: bool = False  # lanes.bots_in_home: Home keeps bots too


def _all(st, ctx):
    return True


def _people(st, ctx):
    return ctx.bots_in_home or not is_bot(st["account"], ctx.extra_bots)


def _bots(st, ctx):
    return is_bot(st["account"], ctx.extra_bots)


def keeps(lane, st, ctx):
    """Does this post belong in this lane? Someone you put in a list (and their
    boosts, and anybody's boost of their posts) leaves the lanes in lists.hide_in:
    the list is where they're read."""
    if lane.name in ctx.hide_in and (st["account"]["id"] in ctx.hidden
                                     or real(st)["account"]["id"] in ctx.hidden):
        return False
    if ctx.languages and in_scope(lane.name, ctx.languages_in) and \
            not langs.wanted(real(st), ctx.languages, ctx.detect, ctx.min_words):
        return False
    return lane.keep(st, ctx)


def in_scope(name, names):
    """Is a lane among `names`, where "lists" names every list and "tags" every tag lane?"""
    return name in names or "lists" in names and is_list(name) \
        or "tags" in names and taggroups.is_tags(name)


def _is_direct(st):
    return real(st).get("visibility") == "direct"


def _mine(st, ctx):
    return bool(ctx.me_id) and real(st)["account"]["id"] == ctx.me_id


def _comments(st, ctx):
    if ctx.direct_apart and _is_direct(st) or _mine(st, ctx):
        return False
    return is_comment_to_me(real(st), ctx.me_id)


def _other_mentions(st, ctx):
    # my own direct messages are in the mentions stream too (for "Direct", the whole
    # dialogue): never here
    if ctx.direct_apart and _is_direct(st) or _mine(st, ctx):
        return False
    return ctx.mentions_all or not is_comment_to_me(real(st), ctx.me_id)


def _direct(st, ctx):
    """Private messages: to me, and mine to others (app._carry_my_direct puts those in
    the mentions stream) — one dialogue, by the posts' own time."""
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
    # private messages to me and mine to others: the mentions stream (mine are added
    # to it by app._carry_my_direct), only what was sent to the named
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
    ("custom", []),  # free lanes (core/custom.py): the person's own, on top
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
        if group == "custom":
            got = [n for n in names if n.startswith("custom:")]
            if not got:
                continue
        elif group == "lists":
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
                        and not n.startswith("custom:")
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
    from . import custom  # it builds on lanes
    out += [c.lane() for c in custom.load(cfg)[0]]
    seen = set()
    for g in tag_groups:
        lane = tag_lane(g)
        if lane.name not in seen:
            seen.add(lane.name)
            out.append(lane)
    return out


# lanes.preset: sets of lanes "as in other clients" — what each sets in [lanes]. Built of
# today's lanes and switches; once free lanes come (docs/en/dev/feeds.md), a client's one
# "Notifications" becomes one lane with quick filters instead of Mentions + Activity.
_FEDTAIL = ["federated", "home", "local", "bots", "my_posts", "direct", "mentions", "replies",
            "subs", "bookmarks", "activity", "requests"]
PRESETS = {
    # fedtail's own: Point-style — replies and mentions apart, followed threads, bots apart
    "fedtail": {"enabled": _FEDTAIL, "posts_only": [], "mentions_all": False,
                "direct_apart": True, "bots_in_home": False},
    # Mastodon's web page: Home with everything, Notifications (mentions + the rest),
    # Private mentions apart, Live feeds, Bookmarks, Favourites, Follow requests
    "mastodon": {"enabled": ["home", "local", "federated", "mentions", "direct", "activity",
                             "requests", "bookmarks", "my_likes"],
                 "posts_only": [], "mentions_all": True, "direct_apart": True,
                 "bots_in_home": True},
    # Tusky's tabs: Home, Notifications (private ones among them), Local, Federated, Direct
    "tusky": {"enabled": ["home", "local", "federated", "mentions", "activity", "direct"],
              "posts_only": [], "mentions_all": True, "direct_apart": False,
              "bots_in_home": True},
    # Phanpy: Home, Mentions (private ones among them), Notifications with follow requests on
    # top, Bookmarks, Likes; Local as a shortcut
    "phanpy": {"enabled": ["home", "local", "mentions", "direct", "activity", "requests",
                           "bookmarks", "my_likes"],
               "posts_only": [], "mentions_all": True, "direct_apart": False,
               "bots_in_home": True},
}


def apply_preset(lanes_cfg):
    """[lanes] with its preset's values in place (lanes.preset = "own": as it is).
    Returns the keys the preset took over."""
    preset = PRESETS.get(lanes_cfg.get("preset"))
    if not preset:
        return []
    for key, value in preset.items():
        lanes_cfg[key] = list(value) if isinstance(value, list) else value
    return list(preset)


LOCAL_SOURCES = {"subs"}  # filled by the client itself, not a server stream


def sources_needed(lanes):
    """The server streams the lanes need: their own, and what free lanes are fed from."""
    need = {lane.source for lane in lanes if lane.source} | \
        {f for lane in lanes for f in lane.feeds}
    return sorted(s for s in need - LOCAL_SOURCES if not s.startswith("custom:"))
