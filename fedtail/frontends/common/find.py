"""Ctrl+F without a toolkit: which cards match, the next match round the end, and the
words beside the box ("3 of 7", "nothing here", "2 of 5 · in Replies")."""

from __future__ import annotations

from ...i18n import _
from ...model.text import haystack, matches


def hits(specs, query):
    """Keys of the cards (CardSpec, top to bottom; also those not built yet) whose post
    has the words; the divider never."""
    if not query.strip():
        return []
    return [s.key for s in specs if s.entry is not None and not s.extra.get("separator")
            and matches(query, haystack(s.entry, s.extra.get("short_id")))]


def step(pos, n, delta):
    """The match after (delta 1) or before (-1) pos among n, round the end; from none
    (pos -1) the first or the last."""
    if not n:
        return -1
    if pos < 0:
        return 0 if delta > 0 else n - 1
    return (pos + delta) % n


def count_text(query, pos, n, lane_title=None, everywhere=False, searched=True):
    """(the words beside the box, whether it found nothing). Everywhere: lane_title of
    the lane the current match is in; searched=False — not asked yet."""
    if not query.strip() or (everywhere and not searched):
        return "", False
    if not n:
        return _("find_none_anywhere") if everywhere else _("find_none"), True
    if everywhere:
        return _("find_count_lane", i=pos + 1, n=n, lane=lane_title or ""), False
    return _("find_count", i=pos + 1 if pos >= 0 else 0, n=n), False
