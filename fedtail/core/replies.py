"""Replies your server never got.

A server knows the replies that reached it: from people someone there follows,
or sent to someone there. The rest of a conversation lives on other servers. Every
post's own server publishes who answered it (ActivityPub: the post's "replies"
collection), so fedtail can read that list and ask *your* server to fetch the
missing ones by their address — after which they are ordinary posts there, in
the thread, answerable and likeable.

Reading the collection is a request to the post's server and the repliers'
servers — without your token (only your IP address shows), like honest counters;
`feed.complete_threads` turns it off.
"""

import logging
from urllib.parse import urlparse

log = logging.getLogger(__name__)

AP_ACCEPT = ('application/activity+json, application/ld+json; '
             'profile="https://www.w3.org/ns/activitystreams"')


def _id(x):
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return x.get("id")
    return None


def collection_items(get_json, coll, pages=3):
    """Item ids of an ActivityPub collection (embedded or by address), first pages only."""
    out = []
    if isinstance(coll, str):
        coll = get_json(coll)
    seen_pages = 0
    page = coll.get("first") if isinstance(coll, dict) else None
    if isinstance(coll, dict):
        out += [_id(i) for i in coll.get("items") or coll.get("orderedItems") or []]
    while page is not None and seen_pages < pages:
        if isinstance(page, str):
            page = get_json(page)
        if not isinstance(page, dict):
            break
        seen_pages += 1
        out += [_id(i) for i in page.get("items") or page.get("orderedItems") or []]
        page = page.get("next")
    return [i for i in out if i and urlparse(i).scheme in ("https", "http")]


def reply_uris(get_json, root_uri, limit=40, depth=3):
    """Addresses of replies in the conversation under root_uri, walking the replies
    of replies a few levels down; at most `limit` of them."""
    found, queue, done = [], [(root_uri, 0)], set()
    while queue and len(found) < limit:
        uri, level = queue.pop(0)
        if uri in done:
            continue
        done.add(uri)
        try:
            obj = get_json(uri)
        except Exception as e:  # someone else's server: anything may happen
            log.debug("replies of %s: %s", uri, e)
            continue
        if not isinstance(obj, dict) or not obj.get("replies"):
            continue
        try:
            items = collection_items(get_json, obj["replies"])
        except Exception as e:
            log.debug("replies collection of %s: %s", uri, e)
            continue
        for item in items:
            if item not in found and item != root_uri:
                found.append(item)
                if level + 1 < depth:
                    queue.append((item, level + 1))
            if len(found) >= limit:
                break
    return found


PUBLIC = {"https://www.w3.org/ns/activitystreams#Public", "as:Public", "Public"}


def _audience(x):
    v = x.get("to") or []
    v = [v] if isinstance(v, str) else list(v)
    c = x.get("cc") or []
    return set(v + ([c] if isinstance(c, str) else list(c)))


def outbox_post_uris(get_json, outbox, limit=20, pages=3):
    """Addresses of the newest public posts in an actor's outbox — the posts they
    wrote themselves (Create), not their boosts; at most `limit`."""
    found = []
    col = get_json(outbox) if isinstance(outbox, str) else outbox
    if not isinstance(col, dict):
        return found
    page = col.get("first")
    items = list(col.get("orderedItems") or col.get("items") or [])
    seen = 0
    while len(found) < limit:
        for it in items:
            if not isinstance(it, dict) or it.get("type") != "Create":
                continue
            obj = it.get("object")
            target = obj if isinstance(obj, dict) else it
            if not (_audience(target) | _audience(it)) & PUBLIC:
                continue
            uri = _id(obj)
            if uri and urlparse(uri).scheme in ("https", "http") and uri not in found:
                found.append(uri)
            if len(found) >= limit:
                break
        if page is None or seen >= pages or len(found) >= limit:
            break
        page = get_json(page) if isinstance(page, str) else page
        if not isinstance(page, dict):
            break
        seen += 1
        items = list(page.get("orderedItems") or page.get("items") or [])
        page = page.get("next")
    return found
