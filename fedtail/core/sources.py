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


def _notification_entry(n):
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
        "home": Source("home", api.home, _status_entry),
        "mentions": Source("mentions", api.mentions, _notification_entry),
        "mine": Source("mine", lambda **kw: api.account_statuses(me_id, **kw), _status_entry),
        "local": Source("local", api.local, _status_entry),
        "federated": Source("federated", api.federated, _status_entry),
    }


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


def refresh_top(store, source, page_size):
    """For lanes you browse rather than read through (local, federated): just the
    newest page. A hole between it and what we had is fine there."""
    return store.put_items(source.name, _entries(source, source.fetch(limit=page_size)))


def fetch_older(store, source, page_size):
    """One page older than the oldest item we have. Returns the new statuses."""
    oldest = store.oldest_item(source.name)
    page = source.fetch(limit=page_size, max_id=oldest) if oldest else \
        source.fetch(limit=page_size)
    entries = _entries(source, page)
    new = set(store.put_items(source.name, entries))
    return [st for item_id, st, _ in entries if item_id in new]
