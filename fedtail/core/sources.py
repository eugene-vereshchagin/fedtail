"""Server-side streams we keep a local copy of.

Each source is caught up *forward* from the newest known item with min_id,
page by page, so the local copy never has holes and reading can stay
chronological. Older history is pulled on request with max_id.
"""

from collections.abc import Callable
from dataclasses import dataclass

from .store import now_iso, sort_key


@dataclass
class Source:
    name: str
    fetch: Callable  # fetch(limit=, max_id=, min_id=) -> list of raw objects
    entry: Callable  # raw -> (item_id, status, created_at) or None


def _status_entry(st):
    return st["id"], st, st.get("created_at", "")


def notification_entry(n):
    st = n.get("status")
    if not st:
        return None
    return n["id"], st, n.get("created_at", "")


class _Cursor:
    """A stream that pages by the Link header: "older" continues from where the
    previous page ended, whatever the oldest stored item is."""

    def __init__(self, fetch, attr):
        self.fetch_page, self.attr, self.next = fetch, attr, None

    def __call__(self, limit=40, max_id=None, min_id=None):
        page = self.fetch_page(limit=limit, max_id=self.next if max_id else None)
        self.next = getattr(self.fetch_page.__self__, self.attr, None)
        return page


def make_sources(api, me_id):
    return {
        "bookmarks": Source("bookmarks", _Cursor(api.bookmarks, "bookmarks_next"),
                            _status_entry),
        "favourites": Source("favourites", _Cursor(api.favourites, "favourites_next"),
                             _status_entry),
        "home": Source("home", api.home, _status_entry),
        "mentions": Source("mentions", api.mentions, notification_entry),
        # posts of the people with the bell on: the server tells them as notifications
        "watched": Source("watched", lambda **kw: api.notifications(["status"], **kw),
                          notification_entry),
        "mine": Source("mine", lambda **kw: api.account_statuses(me_id, **kw), _status_entry),
        "local": Source("local", api.local, _status_entry),
        "federated": Source("federated", api.federated, _status_entry),
    }


def conversation_entry(c):
    """A private conversation's newest post (conversations): the post, as a timeline's."""
    st = c.get("last_status") if isinstance(c, dict) else None
    return (st["id"], st, st.get("created_at", "")) if st else None


def _first_page(fetch):
    """A stream with no paging of its own (trends, conversations): its page once, no
    "older"; a min_id is no cursor there — the page again, the store drops repeats."""
    def page(limit=40, max_id=None, min_id=None):
        return [] if max_id else (fetch(limit) or [])
    return page


def wider_sources(api, bubble=()):
    """Streams for lanes of rules beyond the built-in ones (feeds.md §2.1): my server's
    trending posts, private conversations, and the "bubble" — Federated, only the
    servers chosen (lanes.bubble)."""
    hosts = {h.lower().lstrip("@") for h in bubble or ()}

    def in_bubble(st):
        acct = ((st or {}).get("account") or {}).get("acct") or ""
        return _status_entry(st) if "@" in acct and acct.split("@", 1)[1].lower() in hosts \
            else None
    return {
        "trends": Source("trends", _first_page(lambda n: api.trends("statuses", limit=min(n, 40))),
                         _status_entry),
        "direct": Source("direct", _first_page(lambda n: api.conversations(limit=min(n, 40))),
                         conversation_entry),
        "bubble": Source("bubble", api.federated, in_bubble),
    }


ACCOUNT_FLAGS = ("posts", "media", "noboosts", "pinned")  # account:<id>/<flag>…


def account_parts(arg):
    """account:<id>/posts/media/tag:linux → ("<id>", {"posts", "media"}, "linux"); a
    word it doesn't know → ValueError (the rule says so)."""
    acc, *rest = arg.split("/")
    flags, tag = set(), None
    for part in rest:
        if part.startswith("tag:") and part[4:]:
            tag = part[4:].lstrip("#")
        elif part in ACCOUNT_FLAGS:
            flags.add(part)
        else:
            raise ValueError(f"account:…/{part} — one of {', '.join(ACCOUNT_FLAGS)}, tag:<tag>")
    if not acc:
        raise ValueError("account: — an account's id")
    return acc, flags, tag


def prefixed_source(api, name, remote=None, rss=None):
    """A stream named with its parameter: account:<id> (someone's posts; /posts — no
    replies, /media — with pictures, /noboosts, /pinned, /tag:<tag> — the server
    filters), link:<url> (posts sharing a link), quotes:<id> (quotes of a post),
    search:<words> (posts found), rss:<address> (a feed's items: rss(url) gives them),
    remote:<host> (another server's public lane, fetched into mine: remote(host) gives
    its new posts)."""
    kind, _sep, arg = name.partition(":")
    if kind == "account":
        try:
            acc, flags, tag = account_parts(arg)
        except ValueError:
            return None
        if "pinned" in flags:
            return Source(name, _first_page(lambda _n: api.pinned(acc)), _status_entry)
        opts = {"exclude_replies": "posts" in flags, "only_media": "media" in flags,
                "exclude_reblogs": "noboosts" in flags, "tagged": tag}
        return Source(name, lambda **kw: api.account_statuses(acc, **kw, **opts),
                      _status_entry)
    if kind == "search" and arg.strip():
        return Source(name, lambda **kw: api.search_statuses(arg, **kw), _status_entry)
    if kind == "rss" and rss is not None and arg.strip():
        return Source(name, _first_page(lambda _n: rss(arg)), _status_entry)
    if kind == "link":
        return Source(name, lambda **kw: api.link_timeline(arg, **kw), _status_entry)
    if kind == "quotes":
        return Source(name, lambda limit=40, max_id=None, min_id=None:
                      api.quotes(arg, max_id)[0] or [], _status_entry)
    if kind == "remote" and remote is not None:
        return Source(name, _first_page(lambda _n: remote(arg)), _status_entry)
    return None


def tag_group_source(api, spec, one_request=False):
    """A lane of tags. one_request (lanes.tags_one_request, where the server takes
    any[]/all[]/none[] — Mastodon): the whole group asked at once, not a tag at a time."""
    from . import taggroups
    if one_request:
        return Source(taggroups.lane_name(spec),
                      lambda **kw: taggroups.fetch_once(api.tag_timeline, spec, **kw),
                      _status_entry)
    return Source(taggroups.lane_name(spec),
                  lambda **kw: taggroups.fetch(api.tag_timeline, spec, **kw), _status_entry)


def list_source(api, list_id):
    name = f"list:{list_id}"
    return Source(name, lambda **kw: api.list_timeline(list_id, **kw), _status_entry)


def _entries(source, page):
    return [e for e in (source.entry(raw) for raw in page) if e]


def _newest_raw_id(source, page):
    best = None
    for raw in page:
        e = source.entry(raw)
        item_id, created = (e[0], e[2]) if e else (raw["id"], raw.get("created_at", ""))
        key = sort_key(created, item_id)
        if best is None or key > best[0]:
            best = (key, item_id)
    return best[1] if best else None


def catch_up(store, source, page_size, limit):
    """Fetch everything newer than what we have (up to `limit`). Returns new item ids."""
    newest = store.newest_item(source.name)
    if newest is None:
        return _fill_empty(store, source, page_size, limit)

    new, cursor = [], newest
    while True:
        page = source.fetch(limit=page_size, min_id=cursor)
        if not page:
            break
        new += store.put_items(source.name, _entries(source, page))
        nxt = _newest_raw_id(source, page)
        if nxt is None or nxt == cursor or len(page) < page_size or len(new) >= limit:
            break
        cursor = nxt
    return new


def _fill_empty(store, source, page_size, limit):
    """No cursor yet. The very first time take one page; if the source was
    already watched (it was just empty), walk back to the moment we started
    watching so nothing that arrived in between is skipped."""
    key = f"source_since:{source.name}"
    since = store.kv_get(key)
    store.kv_set(key, since or now_iso())
    page = source.fetch(limit=page_size)
    entries = _entries(source, page)
    new = store.put_items(source.name, entries)
    while since and entries and len(page) == page_size and len(new) < limit:
        oldest = min(entries, key=lambda e: sort_key(e[2], e[0]))
        if (oldest[2] or "") <= since:
            break
        page = source.fetch(limit=page_size, max_id=oldest[0])
        entries = _entries(source, page)
        new += store.put_items(source.name, [e for e in entries if (e[2] or "") > since])
    return new


def refresh_top(store, source, page_size, keep=None):
    """For lanes you browse rather than read through (local, federated): the newest page,
    and pages back from it till one meets what is stored or `keep` posts came — the newest
    `keep` of the stream however fast it flows (lanes.browse_keep). A hole between them and
    what we had is fine there. Returns the new item ids."""
    page = source.fetch(limit=page_size)
    source.last_count = len(page or [])  # 0: the server gave nothing (its live feeds off)
    entries = _entries(source, page)
    new = store.put_items(source.name, entries)
    seen = len(page or [])
    while keep and entries and len(page) == page_size and len(new) == seen and seen < keep:
        oldest = min(entries, key=lambda e: sort_key(e[2], e[0]))
        page = source.fetch(limit=min(page_size, keep - seen), max_id=oldest[0])
        entries = _entries(source, page)
        got = store.put_items(source.name, entries)
        new += got
        seen += len(page or [])
        if len(got) < len(entries):  # met what was stored: the rest is there already
            break
    return new


def fetch_older(store, source, page_size):
    """One page older than the oldest item we have. Returns the new statuses."""
    oldest = store.oldest_item(source.name)
    page = source.fetch(limit=page_size, max_id=oldest) if oldest else \
        source.fetch(limit=page_size)
    entries = _entries(source, page)
    new = set(store.put_items(source.name, entries))
    return [st for item_id, st, _ in entries if item_id in new]
