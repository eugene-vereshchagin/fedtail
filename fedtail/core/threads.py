"""Conversation tree from the server's context of a post (ancestors, descendants)."""

from dataclasses import dataclass

from .proto import raw


@dataclass
class Node:
    status: dict
    depth: int
    number: int  # 0 for the root, then /1 /2 … in reading order, like Point


def build(focus, context, flat=False):
    """Flatten a thread into tree order.

    Children are sorted by time. Replies whose parent we can't see (deleted,
    private, blocked) are hung under the root so nothing silently disappears.
    flat (feed.thread_layout = "flat"): every reply right under the root, all by time —
    the newest at the bottom, no branches (NOTES/21: a late answer to an early comment
    stood above the comments written before it).
    """
    ancestors = (context or {}).get("ancestors", [])
    descendants = (context or {}).get("descendants", [])
    every = ancestors + [focus] + descendants
    by_id = {s["id"]: s for s in every}

    root = ancestors[0] if ancestors else focus
    while raw.reply_to(root) in by_id:
        root = by_id[raw.reply_to(root)]

    children = {}
    orphans = []
    for s in every:
        if s["id"] == root["id"]:
            continue
        parent = raw.reply_to(s)
        if parent in by_id:
            children.setdefault(parent, []).append(s)
        else:
            orphans.append(s)
    children.setdefault(root["id"], []).extend(orphans)
    if flat:
        children = {root["id"]: [s for lst in children.values() for s in lst]}
    for lst in children.values():
        lst.sort(key=lambda s: s.get("created_at", ""))

    out, seen = [], set()
    stack = [(root, 0)]
    while stack:  # iterative DFS: deep flame wars must not hit the recursion limit
        s, depth = stack.pop()
        if s["id"] in seen:
            continue
        seen.add(s["id"])
        out.append(Node(s, depth, len(out)))
        for child in reversed(children.get(s["id"], [])):
            stack.append((child, depth + 1))
    return out


def conversations(entries, get_status, unread):
    """Lane entries gathered by conversation, for the "conversations" view.

    entries: [(item_id, status)] oldest → newest; get_status(id) looks a parent
    up in the store; unread: set of status ids. Each conversation is keyed by
    the highest post we know of its thread (the root, when we have it) and comes
    out once, at the place of its newest entry:

        [{"key", "top": status, "members": [status…], "unread": n, "last": status}]
    """
    groups, order = {}, []
    for _item, st in entries:
        s = raw.real(st)
        top, seen = s, set()
        while raw.reply_to(top) and top["id"] not in seen:
            seen.add(top["id"])
            parent = get_status(raw.reply_to(top))
            if not parent:
                break
            top = parent
        key = top["id"]
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"key": key, "top": top, "members": [], "unread": 0}
        g["members"].append(st)
        g["unread"] += st["id"] in unread
        g["last"] = st
        if key in order:
            order.remove(key)
        order.append(key)  # where its newest entry is
    return [groups[k] for k in order]
