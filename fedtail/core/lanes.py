"""Lanes: what the user sees on the left. A lane is a source plus a filter."""

from collections.abc import Callable
from dataclasses import dataclass

from . import langs, presets, taggroups
from .model import real


@dataclass
class Lane:
    name: str
    source: str | None  # None: no stream of posts (a lane of events only: Activity)
    keep: Callable  # keep(status, ctx) -> bool
    # order by the post's own time instead of when it reached us (notifications
    # can arrive late or out of order; the card shows the post's time)
    by_status_time: bool = False
    # a lane to browse, not to read through (local, federated): fetched only while
    # it's open, newest page first, no unread marks or badges
    lazy: bool = False
    # a free lane (core/custom.py): the real sources its own stream is filled from
    feeds: tuple = ()
    # …its quick filters: (key, words) — "main" (what isn't hidden), "chip:<n>" (one
    # condition's posts); none — the lane has no switches
    chips: tuple = ()
    # a lane of rules: its own switches ("posts_only", "unread_only") — only those; None —
    # a lane made of the server's (a list, a lane of tags): the usual ones
    switches: tuple | None = None
    # the sidebar's section it stands in (its rule's `group`: any word); "" — the sets'
    # own section (presets.toml [sections] own)
    group: str = ""
    # the set's lane to open first when ui.start_lane names none there (its rule's `start`)
    start: bool = False
    # shown only once something is in it (its rule's `hide_empty`; Unsorted always so)
    hide_empty: bool = False
    # the colour of its count in the sidebar (its rule's `badge`): "hot", "quiet", ""
    badge: str = ""
    # a lane of rules' way of reading (core/custom.py): the order — "arrival", "post_time",
    # or by "replies" / "likes" / "boosts" / "density" (the best where reading starts);
    # window — only posts of the last so many seconds (0: all; mode = "catch_up": 12 h);
    # filter_context — the server filters of this context hide / fold its posts
    sort: str = "arrival"
    window: float = 0.0
    filter_context: str = ""
    # per_author — at most so many posts of one author (the newest), 0: any;
    # bundle — "author": each author's posts together, the busiest author first
    per_author: int = 0
    bundle: str = ""
    # view — "threads": one card a thread (its post), the threads with new comments only
    # (common/lane.py); open_at — where a thread opened from a card opens ("post",
    # "first_unread"; "" — threads.open_at: core.open_at)
    view: str = ""
    threads_shown: str = ""  # "all": a threads view's every thread ("" / "new": with news)
    open_at: str = ""
    # the buttons under its posts, in order (its rule's `buttons`, atoms.CARD_BUTTONS);
    # None — not said: by what each post is (frontends/common/actions.buttons)
    buttons: tuple | None = None
    # what its rule marks it for (`marks`, atoms.MARKS): the options that pick lanes
    # take it by their word "marked" (MARKED)
    marks: frozenset = frozenset()
    # it takes events (likes, follows, follow requests… — a condition with `event`):
    # Core.lane_events gives them; with no source it takes nothing else (Activity)
    events: bool = False


@dataclass
class LaneContext:
    me_id: str
    extra_bots: tuple
    hidden: frozenset = frozenset()  # authors put in lists: their list shows them…
    hide_in: frozenset = frozenset()  # …and these lanes don't (lists.hide_in)
    languages: frozenset = frozenset()  # lanes.languages: the ones I read (empty — all)
    languages_in: frozenset = frozenset()  # …in these lanes ("lists", "tags": all of them)
    detect: str = "untagged"  # lanes.detect_language
    min_words: int = 12  # lanes.detect_min_words
    home_hidden_tags: frozenset = frozenset()  # tag lanes "not in Home": their tags leave it
    world: object = None  # core/atoms.World: what the lanes' rules know around a post
    # lists.hide_posts: what a list's timeline brought leaves the lanes in hide_in too
    # (an author who moved to another account, NOTES/17); `in` asks the store once
    listed: object = frozenset()


def _all(st, ctx):
    return True


def keeps(lane, st, ctx):
    """Does this post belong in this lane? Someone you put in a list (and their
    boosts, and anybody's boost of their posts) — and with lists.hide_posts whatever a
    list's timeline brought — leaves the lanes in lists.hide_in:
    the list is where they're read; a tag lane "not in Home" takes its tags out of Home;
    lanes.languages leaves what isn't read out of lanes.languages_in. Then the lane's rule."""
    if (lane.name in ctx.hide_in or MARKED in ctx.hide_in and "hide_listed" in lane.marks) \
            and (st["account"]["id"] in ctx.hidden
                                     or real(st)["account"]["id"] in ctx.hidden
                                     or st["id"] in ctx.listed or real(st)["id"] in ctx.listed):
        return False
    # "not in Home": out of every lane that reads the home timeline, whatever its name
    if ctx.home_hidden_tags and (lane.source == "home" or "home" in (lane.feeds or ())) and \
            {(x.get("name") or "").lower() for x in real(st).get("tags") or ()} & \
            ctx.home_hidden_tags:
        return False
    if ctx.languages and in_scope(lane.name, ctx.languages_in, "languages" in lane.marks) \
            and \
            not langs.wanted(real(st), ctx.languages, ctx.detect, ctx.min_words):
        return False
    return lane.keep(st, ctx)


# an option that picks lanes (notify.lanes, lists.hide_in…) says "marked": the lanes
# whose rules mark themselves for it (`marks`) — so no default names a lane
MARKED = "marked"


def in_scope(name, names, marked=False):
    """Is a lane among `names`, where "lists" names every list, "tags" every tag lane
    and "marked" the lanes whose rule marks them for this (marked: this one's does)?"""
    return name in names or marked and MARKED in names \
        or "lists" in names and is_list(name) \
        or "tags" in names and taggroups.is_tags(name)


# every name a set of lanes has (core/presets.py): the lanes "built in", that is written
# in fedtail/data/presets.toml — the config's word for each is its name
LANES = {n: None for n in presets.known_names()}


# lanes once named otherwise: the old names still work wherever a lane is named — the
# config, the command line, what a window remembered (presets.toml [renamed])
RENAMED = presets.renamed()


def canonical(name):
    """A lane's name as it is now ("people" -> "home", "custom:posts" -> "posts": every
    lane is one kind now); anything else as it was."""
    if isinstance(name, str) and name.startswith("custom:"):
        return name[len("custom:"):]
    return RENAMED.get(name, name) if isinstance(name, str) else name


# The sidebar's sections. A lane's section is its rule's `group` — any word, never its
# name: the sets' file has the usual ones, their order and what each is called
# (presets.toml [sections]); the server's lists and the lanes of tags have sections of
# their own.
LISTS, TAGS = "lists", "tags"


def grouped(lanes, order=()):
    """[(section, [lane names])] for the sidebar, the lanes in their order inside; each
    lane in one section: a list's, a tag lane's, else its rule's `group` (none — the
    file's own section). The sections: `order` first (lanes.sections), then the file's
    in its order, then any other by its first lane. Only those that hold a lane — and
    "lists" always (a list is made from its heading)."""
    out = {}
    for lane in lanes:
        if is_list(lane.name):
            group = LISTS
        elif taggroups.is_tags(lane.name):
            group = TAGS
        else:
            group = getattr(lane, "group", "") or presets.own_section()
        out.setdefault(group, []).append(lane.name)
    out.setdefault(LISTS, [])
    seq = dict.fromkeys([*(g for g in order if isinstance(g, str)), *presets.sections(), *out])
    return [(g, out[g]) for g in seq if g in out]


LIST_PREFIX = "list:"


def list_lane(list_id):
    """A server-side list (Mastodon/GoToSocial) shown as a lane of its own."""
    name = LIST_PREFIX + str(list_id)
    return Lane(name, name, _all)


def is_list(name):
    return name.startswith(LIST_PREFIX)


def chosen(name, wanted, never=(), title=None, marked=False):
    """A lane picked by an option pair such as notify.lanes / notify.except or
    ui.icon_count / ui.icon_count_except: `wanted` names it ("all" names every lane)
    and `never` doesn't. Either may name all the lists at once — "lists" — or one by
    its title or id: "list:Друзья" — and the lanes whose rules mark themselves for the
    option: "marked" (marked: this lane's does). title: this lane's title (a list's)."""
    def named(names, everything):
        if name in names or everything and "all" in names or marked and MARKED in names:
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
    """The lanes to show: the set's (lanes.preset) with config.toml's own over them, in
    lanes.enabled's order (core/custom.py, build)."""
    from . import custom  # it builds on lanes
    return custom.build(cfg, lists, tag_groups)


UNSORTED = "unsorted"  # what came and no lane took (only with free lanes; core/custom.py)
LOCAL_SOURCES = {"subs", UNSORTED}  # filled by the client itself, not a server stream


def sources_needed(lanes):
    """The server streams the lanes need: their own, and what free lanes are fed from."""
    need = {lane.source for lane in lanes if lane.source} | \
        {f for lane in lanes for f in lane.feeds}
    return sorted(s for s in need - LOCAL_SOURCES if not s.startswith("custom:"))
