"""The keys of a lane's posts (ui.post_keys, help/keys.md "A lane and a thread"): j / k
walk the posts, r f b m o and Enter act on the one under the cursor, as a fedtail: link
of its card would. One table for every window: GTK had none of them (21.11)."""

from ...core import keys

# what an action of the config's [keys] (core/keys.py POSTS) means among posts: walk the
# cursor, go between a thread's top comments, fold a branch, or do what a card's link does
MEANING = {"next_post": ("walk", 1), "previous_post": ("walk", -1),
           "next_comment": ("top", 1), "previous_comment": ("top", -1),
           "fold_branch": ("fold", None),
           "reply": ("act", "reply"), "like": ("act", "fav"), "boost": ("act", "boost"),
           "bookmark": ("act", "bookmark"), "open_thread": ("act", "thread")}


def meaning(cfg, key):
    """What a key pressed among posts means — (kind, value) of MEANING — or None: not
    the posts' key, or window.post_keys is off. key: core.keys.Key (keys.from_qt,
    keys.from_gdk, or parsed from a terminal's or the page's own words). The one table of
    every interface, the keys the config's ([keys]) — they were letters written into
    each window (23.11)."""
    if not ((cfg or {}).get("ui") or {}).get("post_keys", True):
        return None
    action = keys.table(cfg, keys.POSTS).get(key)
    return MEANING.get(action) if action else None


def step(posts, at, delta, first_on_screen=None):
    """The post the cursor goes to: from `at` by delta (stopping at either end), or —
    no cursor among the posts yet — the first one on screen."""
    if not posts:
        return None
    if at not in posts:
        return first_on_screen if first_on_screen in posts else posts[0]
    return posts[max(0, min(len(posts) - 1, posts.index(at) + delta))]


def link(action, post_id):
    """What the card's own link for it says: fedtail:<action>/<id> (common/links.py)."""
    return f"fedtail:{action}/{post_id}"


# a thread's own keys (help/keys.md): ] / [ the next / previous top comment, - its branch
THREAD_KEYS = {"bracketright": 1, "bracketleft": -1}
FOLD = "minus"


def top_comment(posts, at, delta, depth_of):
    """] / [ in a thread: the next (delta > 0) or previous comment at the top of the tree
    (depth 1, the post itself 0) from `at`; None when there is no other. One rule for
    Qt, GTK, the terminal and the page (the terminal skipped the post itself)."""
    tops = [k for k in posts if depth_of(k) <= 1]
    if len(tops) < 2:
        return None
    i = posts.index(at) if at in posts else -1
    if delta > 0:
        return next((k for k in tops if posts.index(k) > i), tops[-1])
    return next((k for k in reversed(tops) if posts.index(k) < i), tops[0])


def branch(every, at, depth_of):
    """- in a thread: (head, below) — the branch the key folds: from however deep a reply
    it is pressed, its top comment's; below: the keys under the head, deeper than it.
    every: all the thread's keys in order (folded ones too)."""
    i = every.index(at)
    depth = depth_of(at)
    if depth > 1:
        i = next((j for j in range(i, -1, -1) if depth_of(every[j]) <= 1), i)
        depth = depth_of(every[i])
    below = []
    for k in every[i + 1:]:
        if depth_of(k) <= depth:
            break
        below.append(k)
    return every[i], below


def fold(folded, hidden, head, below):
    """The branch under head folded away, or shown again: folded (heads) and hidden (the
    keys not drawn) changed in place. → whether anything changed."""
    if not below:
        return False
    if head in folded:
        folded.discard(head)
        hidden.difference_update(below)
    else:
        folded.add(head)
        hidden.update(below)
    return True


def hidden_under(folded, every, depth_of):
    """A thread drawn anew (it grew, it was refreshed): the branches folded stay folded.
    folded loses the heads that are gone (in place); → the keys not to draw — everything
    under the heads left, the replies that came meanwhile too. The interfaces kept the
    keys hidden before, so a new reply stood alone under a folded head (Qt), or unfolded
    everything (the terminal)."""
    folded.intersection_update(every)
    hidden = set()
    for head in folded:
        hidden.update(branch(every, head, depth_of)[1])
    return hidden


def unfold_for(folded, hidden, every, key, depth_of):
    """The post to go to (the next new one, the one asked for) lies in a folded branch:
    the branch is shown again. → its head, or None when key was in sight already."""
    if key not in hidden or key not in every:
        return None
    for head in [h for h in every if h in folded]:
        below = branch(every, head, depth_of)[1]
        if key in below:
            fold(folded, hidden, head, below)
            return head
    return None


# threads.remember_folded: which branches of which thread are folded, in the profile's
# state — the same in every interface, through a restart. Off: nothing read or written.
REMEMBERED = 300  # threads; the oldest go


def remembers(cfg):
    return bool(((cfg or {}).get("feed") or {}).get("remember_folded"))


def remembered(view, root):
    """The heads folded in the thread of `root` the last time (a set; empty when off)."""
    if not root or not remembers(view.cfg):
        return set()
    return set((view.get_state("thread_folded") or {}).get(str(root)) or ())


def remember(view, root, folded):
    """The thread's folded heads kept (none folded: the thread forgotten)."""
    if not root or not remembers(view.cfg):
        return
    every = dict(view.get_state("thread_folded") or {})
    before = every.pop(str(root), None)
    if folded:
        every[str(root)] = sorted(str(k) for k in folded)  # (last touched: last to go)
    elif before is None:
        return
    for old in list(every)[:max(0, len(every) - REMEMBERED)]:
        del every[old]
    view.set_state("thread_folded", every)
