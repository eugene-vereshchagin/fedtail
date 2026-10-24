"""Thread subscriptions, the way Point.im had them.

Mastodon has no such thing: a server tells you only about replies that
mention you. So the client follows threads itself: it remembers which posts
of a thread it has already seen and, every few minutes, asks the server for
the thread again. Anything new — two people answering each other under your
post, say — lands in the "Subscriptions" lane.

You are subscribed automatically to your own posts and to threads you
comment in (flags), and by hand from a post's menu or the thread header.
Leaving a thread is remembered, so automatic subscription won't drag you back.

A server only stops mentions from a thread if it can mute the thread (GoToSocial
can't), and replies in a thread tag everyone in it by themselves. So a thread can be
muted here too (`quiet`), and a left one may count as muted (flag subs.leave_mutes):
its mentions are dropped as they come, told by their parent post — the posts of such a
thread are kept in `left_members`, and every dropped mention joins them.
"""

import logging
from datetime import UTC, datetime, timedelta

from ..protocols.mastodon.api import ApiError
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


def leave(store, api, status, quiet=False):
    """Leave the thread `status` is in: unsubscribe and remember all its posts as
    the left thread's; `quiet` also mutes it here. Asks the server for the thread
    (the real root and every post in it); without an answer goes by what it knows.
    Returns the root id."""
    st = real(status)
    root = store.sub_root_of(st["id"]) or \
        (st.get("in_reply_to_id") and store.sub_root_of(st["in_reply_to_id"])) or None
    members = [st["id"]]
    try:
        ctx = api.context(st["id"])
        anc, desc = ctx.get("ancestors", []), ctx.get("descendants", [])
        root = root or (anc[0]["id"] if anc else st["id"])
        members += [s["id"] for s in anc + desc]
    except (ApiError, OSError) as e:  # offline: the post itself is the best guess
        log.info("leave thread %s: no context (%s)", st["id"], e)
        root = root or store.left_root_of([st["id"], st.get("in_reply_to_id")]) or st["id"]
    store.sub_remove(root, members=members)
    if quiet:
        store.quiet_set(root)
        store.drop_items_of_thread("mentions", root)
    return root


def unquiet(store, status):
    """Let a thread muted here speak again (it stays unsubscribed)."""
    root = quiet_root(store, status)
    if root:
        store.quiet_set(root, False)
    return root


def quiet_root(store, status, left_too=False):
    """The muted (or, left_too, left) thread this post is known to be in, or None."""
    st = real(status)
    root = store.left_root_of([st["id"], st.get("in_reply_to_id")])
    return root if root and root in store.quiet_roots(left_too) else None


MAX_HOPS = 50


def silenced(store, api, status, left_too):
    """Is this post (a mention that came) from a muted thread — or a left one, when
    left_too? Climbs its parents through the store; where the chain breaks, asks the
    server for the thread once. A post found to be in one joins it, so the next
    reply under it is told at once. Returns the thread's root or None."""
    roots = store.quiet_roots(left_too)
    if not roots:
        return None
    st = real(status)
    seen, cur = [st["id"]], st
    root = None
    for _ in range(MAX_HOPS):
        hit = store.left_root_of([cur["id"]])
        if hit or cur["id"] in roots:
            root = hit or cur["id"]
            break
        pid = cur.get("in_reply_to_id")
        if not pid:
            break
        nxt = store.get_status(pid)
        if nxt is None:
            seen.append(pid)
            hit = store.left_root_of([pid])
            if hit or pid in roots:
                root = hit or pid
                break
            try:  # the chain breaks here: the server knows the rest
                anc = api.context(st["id"]).get("ancestors", [])
            except (ApiError, OSError) as e:
                log.debug("silenced? %s: %s", st["id"], e)
                break
            ids = [a["id"] for a in anc]
            root = store.left_root_of(ids) or (ids[0] if ids and ids[0] in roots else None)
            seen += ids
            break
        seen.append(nxt["id"])
        cur = nxt
    if root not in roots:
        return None
    store.left_add(root, seen)
    return root


# a thread quiet for a while is asked about less often: (quiet for at least, hours) →
# times subs.interval_minutes. A thread alive now: every interval; quiet a day: every
# hour (at 5 minutes); quiet three days: every three. The night of 22.10: 97 threads,
# each asked every 5 minutes — 56% of all requests, the server's limit spent, 1.7 h of
# 10 waiting for it.
QUIET = ((72, 36), (24, 12), (1, 3))
SHARE = 4  # of what the server still allows this window, at most a quarter for threads


def every(last_activity, now, interval_minutes):
    """How often a thread is asked about, from when it was last alive."""
    try:
        last = datetime.fromisoformat((last_activity or "").replace("Z", "+00:00"))
    except ValueError:
        return timedelta(minutes=interval_minutes)
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    quiet_h = (now - last).total_seconds() / 3600
    times = next((t for hours, t in QUIET if quiet_h >= hours), 1)
    return timedelta(minutes=interval_minutes * times)


def budget_share(api, max_threads, now=None):
    """How many threads this round may ask about: max_threads, or a quarter of what the
    server still allows this window when it says (so the lanes keep theirs)."""
    b = getattr(api, "budget", None)
    if b is None or not b.limit:
        return max_threads
    if b.reset and b.reset < (now if now is not None else datetime.now(UTC).timestamp()):
        return max_threads  # the window is over: it starts anew
    return max(0, min(max_threads, b.remaining // SHARE))


def slow(store, root, since, err):
    """A thread the server didn't give (a big thread on a slow server timing out): marked
    checked, so it waits its turn instead of being asked again at once every poll and
    holding up the others — and not the reader's error, only the log's."""
    log.warning("subs: thread %s not loaded (%s); next time", root, err)
    store.sub_checked(root, now_iso(), since, [])


def check(store, api, me_id, interval_minutes, active_days, max_threads):
    """Ask the server about followed threads that are due. Returns new item ids."""
    now = datetime.now(UTC)
    limit = budget_share(api, max_threads)
    if limit <= 0:
        log.info("subs: the server's limit is nearly spent — threads wait")
        return []
    candidates = store.subs_due(_iso(now - timedelta(days=active_days)),
                                _iso(now - timedelta(minutes=interval_minutes)),
                                max_threads * 10)
    due = [r for r in candidates
           if (r[3] or "") < _iso(now - every(r[2], now, interval_minutes))][:limit]
    new = []
    for root, since, _last, _checked in due:
        try:
            ctx = api.context(root)
        except ApiError as e:
            if e.status == 404:  # the thread is gone
                store.sub_remove(root, remember=False)
                continue
            if e.status in (401, 403, 429):  # the token, the limit: the round stops
                raise
            slow(store, root, since, e)
            continue
        except Exception as e:  # noqa: BLE001 — a timeout, the network: this one waits
            slow(store, root, since, e)
            continue
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
