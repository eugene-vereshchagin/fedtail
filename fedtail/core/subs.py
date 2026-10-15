"""Thread subscriptions, the way Point.im had them.

Mastodon has no such thing: a server tells you only about replies that
mention you. So the client follows threads itself: it remembers which posts
of a thread it has already seen and, every few minutes, asks the server for
the thread again. Anything new — two people answering each other under your
post, say — lands in the "Subscriptions" lane.

You are subscribed automatically to your own posts and to threads you
comment in (flags), and by hand from a post's menu or the thread header.
Leaving a thread is remembered, so automatic subscription won't drag you back.
"""

import logging
from datetime import UTC, datetime, timedelta

from .api import ApiError
from .model import real
from .store import now_iso

log = logging.getLogger(__name__)
SOURCE = "subs"


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def subscribe(store, api, status, auto=False):
    """Follow the thread `status` is in. Returns the thread's root id, or None
    when an automatic subscription hits a thread the user left."""
    st = real(status)
    ctx = api.context(st["id"])
    anc, desc = ctx.get("ancestors", []), ctx.get("descendants", [])
    root = anc[0]["id"] if anc else st["id"]
    if auto and store.sub_left(root):
        return None
    everything = anc + [st] + desc
    store.put_statuses(everything)
    if auto:
        # from my post on: what others wrote after it (and we haven't shown) is news
        since = st.get("created_at") or now_iso()
        known = [s["id"] for s in everything if (s.get("created_at") or "") <= since]
    else:
        # by hand: everything there now is seen; whatever appears later is news
        since = ""
        known = [s["id"] for s in everything]
    latest = max([s.get("created_at") or "" for s in everything] + [now_iso()])
    store.sub_add(root, since, latest, auto, known)
    return root


def unsubscribe(store, status_or_root):
    root = store.sub_root_of(status_or_root) or status_or_root
    store.sub_remove(root)
    return root


def check(store, api, me_id, interval_minutes, active_days, max_threads):
    """Ask the server about followed threads that are due. Returns new item ids."""
    now = datetime.now(UTC)
    due = store.subs_due(_iso(now - timedelta(days=active_days)),
                         _iso(now - timedelta(minutes=interval_minutes)), max_threads)
    new = []
    for root, since, _last in due:
        try:
            ctx = api.context(root)
        except ApiError as e:
            if e.status == 404:  # the thread is gone
                store.sub_remove(root, remember=False)
                continue
            raise
        desc = ctx.get("descendants", [])
        known = store.sub_members(root)
        fresh = [s for s in desc if s["id"] not in known
                 and (s.get("created_at") or "") > since and s["account"]["id"] != me_id]
        if desc:
            store.put_statuses(desc)
        new += store.put_items(SOURCE, [(s["id"], s, s.get("created_at", "")) for s in fresh])
        latest = max([s.get("created_at") or "" for s in desc] + [since])
        store.sub_checked(root, now_iso(), latest, [s["id"] for s in desc])
    return new
