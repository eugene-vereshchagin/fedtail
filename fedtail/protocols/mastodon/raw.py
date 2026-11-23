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


def says_warning(obj):
    """Does the object say anything of a warning at all (even "none")? A post's source
    from a server that gives no warning with it doesn't."""
    return "spoiler_text" in (obj or {})


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

# a status's fields that hold another object's id, besides its own, its account's and
# its mentions' (the window of several accounts marks every id with whose it is)
ID_FIELDS = ("in_reply_to_id", "in_reply_to_account_id")


def light(st):
    """As little of a status as tells which post it is and which it boosts."""
    inner = st.get("reblog")
    return {"id": st["id"], "reblog": {"id": inner["id"]}} if inner else {"id": st["id"]}


def is_account(obj):
    """Is this object an account (not a status, not a relationship)?"""
    return isinstance(obj, dict) and "acct" in obj and "id" in obj


# the same things as SQLite's JSON paths, for the store's own questions
SQL_BOOSTED_ID = "$.reblog.id"
SQL_REPLY_TO = "$.in_reply_to_id"
SQL_AUTHOR_ID = "$.account.id"
SQL_HANDLE = "$.account.acct"
SQL_NAME = "$.account.display_name"
# the posts a post leads to besides its parent: the one it boosts, the one it quotes
SQL_LEADS = ("$.reblog.id", "$.quote.quoted_status_id", "$.quote.quoted_status.id",
             "$.quote_id")
# a link card's address and title: the boosted post's first, else its own
SQL_CARD_URL = ("$.reblog.card.url", "$.card.url")
SQL_CARD_TITLE = ("$.reblog.card.title", "$.card.title")

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

# an account as "who went" keeps it between two looks at my followers
FOLLOWER_KEPT = ("id", "acct", "username", "display_name", "url", "avatar",
                 "avatar_static", "bot")


def account(aid, handle="", username="", name="", **more):
    """An account made here, in the server's shape — the one behind a row fedtail tells
    itself (a new release, a device that joined, a server that went) or an RSS feed."""
    return {"id": aid, "acct": handle, "username": username, "display_name": name, **more}


def post(sid, author, content, created_at, url="", uri="", **more):
    """A post made here (an RSS item), in the server's shape: public, nobody's reply, no
    warning, no attachments, every count at nought, nothing of mine on it."""
    return {"id": sid, "account": author, "in_reply_to_id": None,
            "in_reply_to_account_id": None, "created_at": created_at,
            "visibility": "public", "content": content, "spoiler_text": "",
            "sensitive": False, "mentions": [], "tags": [], "media_attachments": [],
            "replies_count": 0, "favourites_count": 0, "reblogs_count": 0,
            "favourited": False, "reblogged": False, "url": url, "uri": uri, **more}


def source(text, warning=""):
    """What I typed for a post, in the shape the server gives its source in."""
    return {"text": text, "spoiler_text": warning}


# ---- a translation (what the server's translator answers, and ours in its shape) --------

def translation(content, warning="", **more):
    """A post's translation: its text and its warning's words, with what else is known
    (the language found, who translated)."""
    return {"content": content, "spoiler_text": warning, **more}


def translated_warning(done):
    """The warning's words in a translation ("" — none, or not translated)."""
    return (done or {}).get("spoiler_text") or ""


def with_translation(st, done):
    """The post with its text (and its warning, when translated) from a translation."""
    out = dict(st, content=done.get("content") or st.get("content") or "")
    if translated_warning(done):
        out["spoiler_text"] = translated_warning(done)
    return out


# ---- a push subscription -----------------------------------------------------------------

# what a push subscription is told about: everything the activity shows
PUSH_ALERTS = {"mention": True, "status": True, "reblog": True, "follow": True,
               "follow_request": True, "favourite": True, "poll": True, "update": True}


# ---- what the rules ask (core/atoms.py) --------------------------------------------------

# the server's notification type (and the types fedtail tells itself) → the rules' event
EVENT_OF = {"favourite": "favourite", "reblog": "reblog", "follow": "follow",
            "follow_request": "follow_request", "poll": "poll", "update": "update",
            "status": "status", "quote": "quote", "quoted_update": "quoted_update",
            "pending.reply": "pending", "pending.favourite": "pending",
            "pending.reblog": "pending", "admin.sign_up": "admin", "admin.report": "admin",
            "severed_relationships": "severed", "moderation_warning": "warning",
            "annual_report": "annual_report", "fedtail.followed": "i_followed",
            "fedtail.unfollow": "unfollow", "fedtail.gone": "gone", "fedtail.lost_domain": "lost",
            "fedtail.moved": "moved", "fedtail.unliked": "unliked",
            "fedtail.device": "device", "fedtail.release": "release"}

# my marks on a post, the rules' word → the server's field: set — the mark is there; said
# and false — it was taken back
MY_MARKS = {"bookmarked": "bookmarked", "liked": "favourited", "boosted": "reblogged"}
