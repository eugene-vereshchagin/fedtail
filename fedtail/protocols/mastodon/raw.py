"""A Mastodon server's status and account objects, read by what a thing is rather than
by Mastodon's name for it: the core keeps what the server gave (the store's raw JSON) and
asks it through these — ``raw.reply_to(st)``, not ``st["in_reply_to_id"]`` — so that its
own logic names no field of this protocol (docs/en/dev/protocols.md, stage 7). Another
protocol brings a module of the same functions over its own objects.

Only what Mastodon calls differently from everyone is here; what every protocol has under
one name — an id, the account, the text, who sees it, when — the core reads as it is.
No I/O, no state."""

# ---- a status ------------------------------------------------------------------------

def boosted(st):
    """The post this one boosts (the whole object), or None — it is a post itself."""
    return st.get("reblog")


def real(st):
    """The post itself: the boosted one for a boost."""
    return st.get("reblog") or st


def with_boosted(st, inner):
    """The same boost around another copy of its post."""
    return dict(st, reblog=inner)


def reply_to(st):
    """The id of the post this one answers, or None."""
    return st.get("in_reply_to_id")


def reply_to_author(st):
    """The id of the account this one answers, or None."""
    return st.get("in_reply_to_account_id")


def warning(st):
    """The content warning's words ("" — none)."""
    return st.get("spoiler_text") or ""


def media(st):
    """The attachments, as the server gave them ([] — none)."""
    return st.get("media_attachments") or []


def media_preview(m):
    """An attachment's small picture."""
    return m.get("preview_url")


def media_remote(m):
    """An attachment's address on its author's server."""
    return m.get("remote_url")


def liked(st):
    """Did I like it?"""
    return bool(st.get("favourited"))


def shared(st):
    """Did I boost it?"""
    return bool(st.get("reblogged"))


def marked(st, liked=None, shared=None):
    """The same status with my like / boost set (None — as it is)."""
    out = dict(st)
    if liked is not None:
        out["favourited"] = bool(liked)
    if shared is not None:
        out["reblogged"] = bool(shared)
    return out


def replies(st):
    """How many direct replies the server counts (None — it doesn't say)."""
    return st.get("replies_count")


def shares(st):
    """How many boosts the server counts."""
    return st.get("reblogs_count")


def likes(st):
    """How many likes the server counts."""
    return st.get("favourites_count")


def with_counts(st, replies=None, shares=None, likes=None):
    """The same status with these counts set (None — as it is)."""
    out = dict(st)
    for key, value in (("replies_count", replies), ("reblogs_count", shares),
                       ("favourites_count", likes)):
        if value is not None:
            out[key] = value
    return out


# what of a status changes while it stands in a lane: its numbers and my marks on it
COUNTED = ("replies_count", "reblogs_count", "favourites_count", "quotes_count",
           "favourited", "reblogged", "bookmarked", "muted", "pinned")
# …and the two of them another server's own copy says better
SHARED_AND_LIKED = ("favourites_count", "reblogs_count")

# the same things as SQLite's JSON paths, for the store's own questions
SQL_BOOSTED_ID = "$.reblog.id"
SQL_REPLY_TO = "$.in_reply_to_id"

# ---- an account ----------------------------------------------------------------------


def handle(acc):
    """user, or user@host for someone of another server ("" — unknown)."""
    return (acc or {}).get("acct") or ""


def name(acc):
    """The name they show ("" — none set)."""
    return (acc or {}).get("display_name") or ""


def posts_count(acc):
    return (acc or {}).get("statuses_count")


def followers_count(acc):
    return (acc or {}).get("followers_count")


def following_count(acc):
    return (acc or {}).get("following_count")


# an account as a roster keeps it: who they are, their face, how busy
ROSTER_KEPT = ("id", "username", "acct", "display_name", "avatar", "avatar_static",
               "url", "uri", "emojis", "bot", "note", "locked", "created_at",
               "last_status_at", "statuses_count", "followers_count", "following_count")
