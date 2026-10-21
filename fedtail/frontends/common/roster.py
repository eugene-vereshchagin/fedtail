"""The roster (the lanes, followed threads and private talks as a messenger's contact
list, docs/LAYOUTS.md) without a toolkit: an item's key and what it opens, the lines
a row shows, what the search and "only new" leave, what "all read" marks, and how the
roster looks (kept in the profile's state)."""

from __future__ import annotations

from ...i18n import _
from ...model.text import snippet

# how the roster looks (its menu): the rows slim (compact: no status line, no face);
# the header, the search and the bottom row can go
LOOK = {"compact": False, "header": True, "search": True, "bottom": True,
        "only_new": False, "groups": True, "on_top": None}


def row_key(item):
    """A roster item's key among the rows: a lane by its name, a thread or talk by kind
    and id (one thread may be both followed and private)."""
    return item.key if item.kind == "lane" else f"{item.kind}/{item.key}"


def what(key):
    """(kind, id) a row's key opens: ("lane", name), ("person", …), ("thread", post id)."""
    if "/" not in key:
        return "lane", key
    kind, _sep, rest = key.partition("/")
    return kind, rest


def lines(item, faces):
    """What a row says under its title: (line, its tooltip, the status beside the face
    — "" without faces)."""
    last = item.last
    if last is None and item.who is not None:
        line, tip = "@" + item.who.handle, ""  # no talk yet: who it is
    elif last is not None:
        a = last.author
        line, tip = f"{a.name or a.username or a.handle}: {snippet(last, 80)}", \
            snippet(last, 300)
    else:
        line, tip = "", ""
    status = ""
    if faces:
        if item.who is not None:
            status = "@" + item.who.handle
            if last is not None:
                line = snippet(last, 80)
        elif item.unread:
            status = _("roster_unread", n=item.unread)
        elif item.total:
            status = _("roster_total", n=item.total)
    return line, tip, status


def face_url(item):
    """Whose face goes beside the row: the person's, else the newest post's author."""
    if item.who is not None:
        return item.who.avatar_static
    return item.last.author.avatar_static if item.last is not None else ""


def tip(item):
    """The row's tooltip ("" for a person: they have a card instead)."""
    if item.kind == "person":
        return ""
    return item.title + (f" — {_('roster_unread', n=item.unread)}" if item.unread else "")


def matches(item, line, text):
    t = text.casefold()
    return not t or t in item.title.casefold() or t in line.casefold()


def hidden(item, line, text, folded, look):
    """Is a row out of sight: searching, what doesn't match; else a folded group's, or
    a read one with "only new"."""
    if text:
        return item is not None and not matches(item, line, text)
    return folded or (look["only_new"] and item is not None and not item.unread)


def read_ids(view, key, item):
    """What "all read" on a row marks: a thread's or talk's posts, a lane's entries."""
    if item is not None and item.kind != "lane":
        return list(item.ids)
    return [e.id for _item, e in view.entries(key)]


def look(view):
    got = view.get_state("roster_look", {}) or {}
    return dict(LOOK, **{k: bool(v) for k, v in got.items() if k in LOOK})


def folded(view):
    return set(view.get_state("roster_folded", []) or [])


def group_counts(group):
    """A group's title and how many: (title, lanes with something new, lanes)."""
    title = _("lists_header") if group.name == "lists" else _("grp_" + group.name)
    return title, sum(1 for i in group.items if i.unread), len(group.items)


def group_word(words, lit):
    """The theme's words for a group's title line ({arrow} {title} ({lit}/{n}))."""
    key = "roster_group" if lit else "roster_group_quiet"
    return words.get(key, "{arrow} {title} ({lit}/{n})" if lit else "{arrow} {title} ({n})")
