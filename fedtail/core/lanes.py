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


@dataclass
class LaneContext:
    me_id: str
    extra_bots: tuple
    mentions_all: bool = False
    subs_replies_to_me: bool = False


def _all(st, ctx):
    return True


def _people(st, ctx):
    return not is_bot(st["account"], ctx.extra_bots)


def _bots(st, ctx):
    return is_bot(st["account"], ctx.extra_bots)


def _comments(st, ctx):
    return is_comment_to_me(real(st), ctx.me_id)


def _other_mentions(st, ctx):
    return ctx.mentions_all or not is_comment_to_me(real(st), ctx.me_id)


def _subs(st, ctx):
    # replies to me are already in "comments"; here goes the rest of the talk
    return ctx.subs_replies_to_me or not is_comment_to_me(real(st), ctx.me_id)


LANES = {
    "people": Lane("people", "home", _people),
    "comments": Lane("comments", "mentions", _comments, by_status_time=True),
    "mentions": Lane("mentions", "mentions", _other_mentions, by_status_time=True),
    "subs": Lane("subs", "subs", _subs, by_status_time=True),
    "bots": Lane("bots", "home", _bots),
    "mine": Lane("mine", "mine", _all),
    "local": Lane("local", "local", _all),
    "requests": Lane("requests", None, _all),
}


def enabled(cfg):
    return [LANES[n] for n in cfg["lanes"]["enabled"]]


LOCAL_SOURCES = {"subs"}  # filled by the client itself, not a server stream


def sources_needed(lanes):
    return sorted({lane.source for lane in lanes if lane.source} - LOCAL_SOURCES)
