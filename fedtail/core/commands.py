"""Point-style commands, typed into one line. No Qt: parsed and tested here, run
by the frontend.

    #a3f              open the post (its thread)
    #a3f text         reply to it
    #a3f/2 text       reply to comment /2 of that thread
    #a3f/2            open the thread at comment /2
    S #a3f   U #a3f   subscribe to / unsubscribe from the thread
    S @user  U @user  follow / unfollow
    ! #a3f            boost ("recommend" on Point)
    ~ #a3f            bookmark (again: remove)
    D #a3f            delete my post (asks first)
    @user             open the profile
    @user text        a post to them only (direct)
    ?                 the list of commands
    anything else     a new post (if cmdline.plain_posts)

Short ids are the `#a3f` aliases shown on every card; `@user` is a handle,
`user@server` or a local name.
"""

import re
from dataclasses import dataclass

_POST = r"#([a-z][0-9a-z]{2,})(?:/(\d+))?"
_USER = r"@([\w.\-]+(?:@[\w.\-]+)?)"


@dataclass
class Command:
    kind: str           # open, reply, sub, unsub, follow, unfollow, boost, bookmark,
    #                    delete, profile, direct, post, help, error
    alias: str = ""     # the post's short id (without '#')
    number: int = 0     # /N inside the thread, 0 = the post itself
    user: str = ""      # handle without the leading '@'
    text: str = ""      # what to send


_LETTERS = {"S": ("sub", "follow"), "U": ("unsub", "unfollow")}


def parse(line):
    """One line → a Command. Never raises: a typo becomes kind="error"."""
    s = (line or "").strip()
    if not s:
        return Command("error")
    if s in ("?", "help", "HELP", "справка"):
        return Command("help")

    m = re.fullmatch(r"([SU])\s+(.+)", s)
    if m:
        letter, rest = m.groups()
        post = re.fullmatch(_POST, rest.strip())
        user = re.fullmatch(_USER, rest.strip())
        if post:
            return Command(_LETTERS[letter][0], post.group(1), int(post.group(2) or 0))
        if user:
            return Command(_LETTERS[letter][1], user=user.group(1))
        return Command("error", text=s)

    m = re.fullmatch(r"([!~D])\s*" + _POST, s)
    if m:
        kind = {"!": "boost", "~": "bookmark", "D": "delete"}[m.group(1)]
        return Command(kind, m.group(2), int(m.group(3) or 0))

    m = re.match(_POST + r"(?:\s+(.*))?$", s, re.S)
    if m:
        alias, num, text = m.group(1), int(m.group(2) or 0), (m.group(3) or "").strip()
        return Command("reply" if text else "open", alias, num, text=text)

    m = re.match(_USER + r"(?:\s+(.*))?$", s, re.S)
    if m and not m.group(2):
        return Command("profile", user=m.group(1))
    if m:
        return Command("direct", user=m.group(1), text=s)

    return Command("post", text=s)
