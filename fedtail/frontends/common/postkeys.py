"""The keys of a lane's posts (ui.post_keys, help/keys.md "A lane and a thread"): j / k
walk the posts, r f b m o and Enter act on the one under the cursor, as a fedtail: link
of its card would. One table for every window: GTK had none of them (21.11)."""

# a key's name (lower case; Enter by its name) -> the card's link action
ACTIONS = {"r": "reply", "f": "fav", "b": "boost", "m": "bookmark", "o": "thread",
           "enter": "thread", "return": "thread", "kp_enter": "thread"}
WALK = {"j": 1, "k": -1}


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
