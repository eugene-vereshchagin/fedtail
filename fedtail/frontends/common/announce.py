"""The server's announcements without a toolkit: how my reaction counts before the
server answers."""

from __future__ import annotations

from dataclasses import replace

from ...model import Reaction


def react(reactions, name, on):
    """The reactions after mine on name went on or off (as the server will count it,
    shown before it answers); none left at zero."""
    rs, found = [], False
    for r in reactions:
        if r.name == name:
            found = True
            if r.me != on:
                r = replace(r, me=on, count=max(0, r.count + (1 if on else -1)))
        rs.append(r)
    if not found and on:
        rs.append(Reaction(name, 1, True))
    return tuple(r for r in rs if r.count)
