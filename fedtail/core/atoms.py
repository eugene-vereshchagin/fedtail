"""Atoms: everything fedtail can tell apart about a post or an event, and the rules of free
lanes made of them (docs/en/dev/feeds.md §2, §4).

A post's atoms are computed once, from the stored status and what the core knows around it
(`World`: whom I follow, who follows me, followed tags, read marks, threads…) into `Facts`.
A rule (`Rule.parse` of a `[[lanes.custom]]` table) is conditions over those facts: inside a
condition every key must match (AND), a list of values means any of them, `any` — any of the
conditions, `none` — none of them. Unknown keys and values are warnings, never errors: the
condition that has one never matches, so a typo shows as a marked lane, not a crash.

Nothing here does I/O or knows a toolkit; the lanes don't use it yet (feeds.md §9, step 1).
"""

import re
from collections.abc import Container, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from . import langs
from .model import html_to_text, is_bot, norm_acct, real

NEW_ACCOUNT_DAYS = 30   # Mastodon's notification policy: "new accounts"
NEW_FOLLOWER_DAYS = 3   # …and "followed you lately"

# ---- the words ---------------------------------------------------------------------------

SOURCES = {"home", "local", "federated", "mentions", "watched", "direct", "bookmarks",
           "favourites", "mine", "subs", "context", "trends", "bubble"}
# sources with a parameter: list:<id>, tags:<spec>, account:<id>, remote:<host>[/local|
# /federated|/trends], link:<url>, quotes:<id>
SOURCE_PREFIXES = ("list:", "tags:", "account:", "remote:", "link:", "quotes:", "search:",
                   "rss:")

AUTHOR = {"me", "followed", "follower", "mutual", "stranger", "bot", "local", "remote",
          "new", "not_follower", "new_follower", "limited", "bell", "boosts_off", "in_list",
          # taken out of Home by hand ("Not in Home" on a profile), still followed
          "hidden_home"}
VISIBILITY = {"public", "unlisted", "followers", "direct", "mutuals", "local_only"}
KIND = {"post", "reply", "self_reply", "boost", "self_boost", "quote", "poll", "edited"}
ME = {"reply", "reply_to_post", "reply_to_comment", "mention", "direct", "in_my_thread",
      "boost_of_mine", "quote_of_mine", "my_boost"}
PARENT = {"mine", "followed", "stranger", "unknown"}
# what a post shows, for a lane's funnel ("only video…"): the windows' words for it
MEDIA_KINDS = ("text", "image", "gifv", "video", "audio")
VIDEO_EXT = (".mp4", ".webm", ".mov", ".m4v", ".mkv", ".ogv")


def media_kinds(st):
    """{"image", "gifv", "video", "audio"} of a status's attachments (a boost: its post's;
    a video a server called a picture — by its file's name — counts as a video), or
    {"text"}."""
    st = st.get("reblog") or st
    kinds = set()
    for m in st.get("media_attachments") or ():
        kind = m.get("type")
        url = str(m.get("url") or m.get("remote_url") or "").lower().split("?")[0]
        if kind in ("image", "unknown") and url.endswith(VIDEO_EXT):
            kind = "video"
        if kind in MEDIA_KINDS:
            kinds.add(kind)
    return kinds or {"text"}


HAS = {"media", "image", "video", "audio", "cw", "sensitive", "link", "poll", "alt_missing",
       "followed_tag"}
HAS_PREFIXES = ("tag:", "link:", "word:")
STATE = {"unread", "read", "subscribed", "bookmarked", "liked", "boosted", "replied",
         "in_list", "muted_thread", "filtered_warn", "new_replies",
         # taken back — the server says so (a missing flag is no answer)
         "unbookmarked", "unliked",
         # gone from its server (404/410 when fetched again): kept here, marked
         "deleted"}
VIA = {"followed", "tag", "boost", "mine", "list"}
# what a boost (or a like, a boost, a quote event) is about: my post or comment, someone
# else's post or comment, and whether its original was already known / read before
TARGET = {"my_post", "my_comment", "post", "comment", "seen", "read"}
EVENTS = {"favourite", "reblog", "follow", "follow_request", "poll", "update", "status",
          "quote", "quoted_update", "pending", "admin", "severed", "warning",
          "annual_report", "i_followed",
          # derived by fedtail itself, comparing snapshots (feeds.md §2.4)
          "unfollow", "removed_follower", "moved", "gone", "unfollowed_back", "unliked",
          "deleted", "lost"}
TEXT_IN = {"text", "cw", "alt", "poll", "name"}  # name: the author's name and @nick

# the server's notification type → our event word
EVENT_OF = {"favourite": "favourite", "reblog": "reblog", "follow": "follow",
            "follow_request": "follow_request", "poll": "poll", "update": "update",
            "status": "status", "quote": "quote", "quoted_update": "quoted_update",
            "pending.reply": "pending", "pending.favourite": "pending",
            "pending.reblog": "pending", "admin.sign_up": "admin", "admin.report": "admin",
            "severed_relationships": "severed", "moderation_warning": "warning",
            "annual_report": "annual_report", "fedtail.followed": "i_followed",
            "fedtail.unfollow": "unfollow", "fedtail.gone": "gone", "fedtail.lost_domain": "lost",
            "fedtail.moved": "moved", "fedtail.unliked": "unliked"}

# the server's visibility → ours (Mastodon "private" is followers-only; GoToSocial's
# "mutuals_only"; Akkoma's "local" is public that stays home)
_VISIBILITY_OF = {"public": "public", "unlisted": "unlisted", "private": "followers",
                  "limited": "followers", "direct": "direct", "mutuals_only": "mutuals",
                  "local": "local_only"}

_SET_KEYS = {"source": SOURCES, "author": AUTHOR, "visibility": VISIBILITY, "kind": KIND,
             "me": ME, "parent": PARENT, "has": HAS, "lang": None, "state": STATE,
             "via": VIA, "target": TARGET, "event": EVENTS, "id": None}
_COUNT_KEYS = ("likes", "boosts", "replies")
# keys of a condition that only say how the lane shows it (feeds.md §4: switches)
_SHOW_KEYS = {"switch", "shown", "priority"}
# a condition of `none` that counts only while that lane is shown: "apart = "direct"" — the
# private ones are read in Direct, when it's on; without it they stay here
_LANE_KEYS = {"apart"}
_GROUP_KEYS = {"any"}  # an inner OR: one of these tables too (an AND of ORs)
_TEXT_KEYS = {"text", "text_in", "text_case", "text_regex"}
_AGE_KEYS = {"age", "age_of"}
_TIME_KEYS = {"until"}  # the condition holds till then (a mute for a week, a lane for a trip)
CONDITION_KEYS = set(_SET_KEYS) | set(_COUNT_KEYS) | _SHOW_KEYS | _TEXT_KEYS | _AGE_KEYS | \
    _LANE_KEYS | _GROUP_KEYS | _TIME_KEYS

_ANCHOR_RE = re.compile(r'<a\b[^>]*\bhref="([^"]+)"[^>]*>')
_AGE_RE = re.compile(r"^\s*([<>]=?)\s*(\d+(?:\.\d+)?)\s*([mhdw])\s*$")
_COUNT_RE = re.compile(r"^\s*(<=|>=|<|>|=)?\s*(\d+)\s*$")
_UNIT = {"m": timedelta(minutes=1), "h": timedelta(hours=1), "d": timedelta(days=1),
         "w": timedelta(weeks=1)}


# ---- what the core knows around a post ---------------------------------------------------

@dataclass
class World:
    """What the atoms need besides the post. The core fills it; every field may stay
    empty — an atom that needs it then is simply not there (and `Facts.unsure` says so)."""
    me_id: str = ""
    my_host: str = ""                    # my server's domain ("social.example")
    following: Container = frozenset()   # account ids I follow
    followers: Container = frozenset()   # account ids that follow me
    new_followers: Container = frozenset()  # …of them, followed me lately (< 3 days)
    bell: Container = frozenset()        # accounts I rang the bell on (relationship.notifying)
    boosts_off: Container = frozenset()  # accounts whose boosts I hid (showing_reblogs false)
    hidden_home: Container = frozenset()  # accounts taken out of Home by hand, still followed
    in_lists: Container = frozenset()    # accounts in any of my lists
    followed_tags: Container = frozenset()  # lower-case names
    extra_bots: tuple = ()
    read: Container = frozenset()        # status ids marked read
    replied: Container = frozenset()     # status ids I replied to (from any client)
    subscribed: Container = frozenset()  # status ids of followed threads' posts
    my_threads: Container = frozenset()  # status ids of posts in threads where I wrote
    muted_threads: Container = frozenset()
    filtered_warn: Container = frozenset()  # status ids a server "warn" filter matched
    seen_before: Container = frozenset()  # originals stored before this boost reached us
    new_replies: Container = frozenset()  # posts whose followed thread has unread replies
    deleted: Container = frozenset()     # posts their server no longer has (404/410)
    parents: Mapping = field(default_factory=dict)  # status id → its parent or "missing"
    now: datetime | None = None          # None: now
    detect: str = "off"                   # lanes.detect_language (core/langs.py)
    min_words: int = 12                  # lanes.detect_min_words


@dataclass
class Facts:
    """A post's atoms (or an event's). Sets of words per axis, plus what is matched by
    value (time, counts, text). `unsure` — axes not known yet (the parent isn't fetched):
    a lane may wait for them (feeds.md §8, "atoms known late")."""
    source: set = field(default_factory=set)
    author: set = field(default_factory=set)
    visibility: set = field(default_factory=set)
    kind: set = field(default_factory=set)
    me: set = field(default_factory=set)
    parent: set = field(default_factory=set)
    has: set = field(default_factory=set)
    lang: set = field(default_factory=set)
    state: set = field(default_factory=set)
    via: set = field(default_factory=set)
    target: set = field(default_factory=set)
    event: set = field(default_factory=set)
    id: set = field(default_factory=set)
    created: datetime | None = None       # the post's (or the boost's) own time
    original_created: datetime | None = None  # a boost: the original's time
    counts: dict = field(default_factory=dict)  # likes / boosts / replies, as last fetched
    texts: dict = field(default_factory=dict)   # text / cw / alt / poll → plain text
    unsure: set = field(default_factory=set)


def _when(s):
    if not s:
        return None
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def _host(url):
    try:
        h = urlsplit(url or "").hostname or ""
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def handle(account, my_host=""):
    """'nick@host' in lower case, my server's people included."""
    acct = norm_acct(account.get("acct"))
    if acct and "@" not in acct:
        host = my_host or _host(account.get("url"))
        acct = f"{acct}@{host}" if host else acct
    return acct


def _author_atoms(acc, world, now):
    out = set()
    aid = acc.get("id")
    acct = handle(acc, world.my_host)
    if aid and aid == world.me_id:
        out.add("me")
    else:
        followed, follower = aid in world.following, aid in world.followers
        out |= {"followed"} if followed else set()
        out |= {"follower"} if follower else {"not_follower"}
        out |= {"mutual"} if followed and follower else set()
        out |= set() if followed else {"stranger"}
        out |= {"new_follower"} if aid in world.new_followers else set()
    if is_bot(acc, world.extra_bots):
        out.add("bot")
    local = "@" not in norm_acct(acc.get("acct")) or \
        bool(world.my_host) and acct.endswith("@" + world.my_host.lower())
    out.add("local" if local else "remote")
    created = _when(acc.get("created_at"))
    if created and now - created < timedelta(days=NEW_ACCOUNT_DAYS):
        out.add("new")
    if acc.get("limited"):
        out.add("limited")
    for flag, ids in (("bell", world.bell), ("boosts_off", world.boosts_off),
                      ("in_list", world.in_lists), ("hidden_home", world.hidden_home)):
        if aid in ids:
            out.add(flag)
    if acct:
        out.add("@" + acct)
        if "@" in acct:
            out.add("domain:" + acct.rsplit("@", 1)[1])
    return out


def _until(value):
    """A condition's end: a date ("2026-11-01" — its midnight, UTC) or a moment; a TOML
    date or datetime as is. None — not one."""
    from datetime import date
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if not isinstance(value, str):
        return None
    try:
        d = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _texts(st):
    out = {"text": html_to_text(st.get("content") or ""), "cw": st.get("spoiler_text") or ""}
    out["alt"] = "\n".join(m.get("description") or "" for m in st.get("media_attachments")
                           or [])
    poll = st.get("poll") or {}
    out["poll"] = "\n".join(o.get("title") or "" for o in poll.get("options") or [])
    acc = st.get("account") or {}
    out["name"] = f"{acc.get('display_name') or ''}\n@{acc.get('acct') or ''}"
    return out


def _target(st, world):
    """What an action is about: whose, a post or a comment, known or read already."""
    mine = bool(world.me_id) and (st.get("account") or {}).get("id") == world.me_id
    comment = bool(st.get("in_reply_to_id"))
    out = {("my_" if mine else "") + ("comment" if comment else "post")}
    if st.get("id") in world.seen_before:
        out.add("seen")
    if st.get("id") in world.read:
        out.add("read")
    return out


def post_facts(status, world=None, source=None, needs=None):
    """The atoms of a stored status (a boost: of the boost and of what it boosts).
    source: the stream it came from ("home", "list:7"…), or several of them. needs: the axes
    a rule asks about (Rule.needs) — the dear ones (a parent looked up, read marks, links,
    the language, the text) only then; None — all of them."""
    def want(axis):
        return needs is None or axis in needs

    world = world or World()
    now = world.now or datetime.now(UTC)
    f = Facts()
    if source:
        f.source = {source} if isinstance(source, str) else set(source)
    st, wrapper = real(status), status
    boost = st is not wrapper
    me = world.me_id
    f.id = {st.get("id", "")} | ({wrapper.get("id", "")} if boost else set())
    f.author = _author_atoms(st.get("account") or {}, world, now)
    f.visibility = {_VISIBILITY_OF.get(st.get("visibility") or "public", "public")}
    if st.get("local_only"):
        f.visibility.add("local_only")

    # kind
    reply_to = st.get("in_reply_to_id")
    author_id = (st.get("account") or {}).get("id")
    if boost:
        f.kind.add("boost")
        if (wrapper.get("account") or {}).get("id") == author_id:
            f.kind.add("self_boost")
        if (wrapper.get("account") or {}).get("id") == me and me:
            f.me.add("my_boost")
        if author_id == me and me:
            f.me.add("boost_of_mine")
    if reply_to:
        f.kind.add("reply")
        if st.get("in_reply_to_account_id") == author_id:
            f.kind.add("self_reply")
    elif not boost:
        f.kind.add("post")
    quoted = st.get("quote")
    if isinstance(quoted, dict):  # Mastodon 4.5: {"state", "quoted_status"}; others: the post
        quoted = quoted.get("quoted_status", quoted)
    if quoted:
        f.kind.add("quote")
        if me and (quoted.get("account") or {}).get("id") == me:
            f.me.add("quote_of_mine")
    if st.get("poll"):
        f.kind.add("poll")
    if st.get("edited_at"):
        f.kind.add("edited")

    # me
    mine = bool(me) and author_id == me
    if not want("me"):
        pass
    elif me and not mine:
        if reply_to and st.get("in_reply_to_account_id") == me:
            f.me.add("reply")
            parent = world.parents.get(reply_to)
            if isinstance(parent, dict):
                f.me.add("reply_to_comment" if parent.get("in_reply_to_id")
                         else "reply_to_post")
            else:
                f.unsure.add("me")
        elif any(m.get("id") == me for m in st.get("mentions") or []):
            f.me.add("mention")
        if st.get("visibility") == "direct" and \
                any(m.get("id") == me for m in st.get("mentions") or []):
            f.me.add("direct")
    elif mine and st.get("visibility") == "direct":
        f.me.add("direct")  # my own private messages: the dialogue is whole
    if want("me") and st.get("id") in world.my_threads and not mine:
        f.me.add("in_my_thread")

    # parent
    if reply_to and want("parent"):
        parent = world.parents.get(reply_to)
        pid = st.get("in_reply_to_account_id")
        if me and pid == me:
            f.parent.add("mine")
        elif pid and pid in world.following:
            f.parent.add("followed")
        elif isinstance(parent, dict) or pid:
            f.parent.add("stranger")
        else:
            f.parent.add("unknown")

    # has
    if want("has") or want("via"):
        _has_atoms(f, st, world)

    if want("lang"):
        f.lang = {langs.post_language(st, world.detect, world.min_words) or "unknown"}

    # state
    if want("state"):
        _state_atoms(f, st, wrapper, world, author_id)

    if boost and want("target"):
        f.target = _target(st, world)

    # via: why it is in my home
    if not want("via"):
        pass
    elif mine:
        f.via.add("mine")
    elif boost and (wrapper.get("account") or {}).get("id") in world.following:
        f.via.add("boost")
    elif author_id in world.following:
        f.via.add("followed")
    elif "followed_tag" in f.has:
        f.via.add("tag")
    if want("via") and author_id in world.in_lists:
        f.via.add("list")

    f.created = _when(wrapper.get("created_at"))
    f.original_created = _when(st.get("created_at"))
    f.counts = {"likes": st.get("favourites_count") or 0,
                "boosts": st.get("reblogs_count") or 0,
                "replies": st.get("replies_count") or 0}
    if want("text"):
        f.texts = _texts(st)
    return f


def _has_atoms(f, st, world):
    media = st.get("media_attachments") or []
    if media:
        f.has.add("media")
        for m in media:
            kind = {"gifv": "video"}.get(m.get("type"), m.get("type"))
            if kind in ("image", "video", "audio"):
                f.has.add(kind)
            if not (m.get("description") or "").strip():
                f.has.add("alt_missing")
    if st.get("spoiler_text"):
        f.has.add("cw")
    if st.get("sensitive"):
        f.has.add("sensitive")
    if st.get("poll"):
        f.has.add("poll")
    tags = {(t.get("name") or "").lower() for t in st.get("tags") or [] if t.get("name")}
    f.has |= {"tag:" + t for t in tags}
    if any(t in world.followed_tags for t in tags):
        f.has.add("followed_tag")
    links = {_host((st.get("card") or {}).get("url"))}
    for a in _ANCHOR_RE.finditer(st.get("content") or ""):
        if not re.search(r'class="[^"]*\b(mention|hashtag)\b', a.group(0)):
            links.add(_host(a.group(1)))
    links.discard("")
    if links:
        f.has.add("link")
        f.has |= {"link:" + h for h in links}


def _state_atoms(f, st, wrapper, world, author_id):
    sid = st.get("id")
    f.state.add("read" if sid in world.read else "unread")
    for flag, key in (("bookmarked", "bookmarked"), ("liked", "favourited"),
                      ("boosted", "reblogged")):
        if st.get(key):
            f.state.add(flag)
    for flag, key in (("unbookmarked", "bookmarked"), ("unliked", "favourited")):
        if key in st and not st[key]:
            f.state.add(flag)
    if sid in world.replied:
        f.state.add("replied")
    if sid in world.subscribed:
        f.state.add("subscribed")
    if author_id in world.in_lists:
        f.state.add("in_list")
    if st.get("muted") or sid in world.muted_threads:
        f.state.add("muted_thread")
    if sid in world.filtered_warn or wrapper.get("id") in world.filtered_warn:
        f.state.add("filtered_warn")
    if sid in world.new_replies:
        f.state.add("new_replies")
    if sid in world.deleted:
        f.state.add("deleted")

def event_facts(notification, world=None):
    """The atoms of an event (a notification, or one fedtail derived: {"type": "unfollow",
    "account": …}): the event's word, who did it, and the post it is about, if any."""
    world = world or World()
    now = world.now or datetime.now(UTC)
    st = notification.get("status")
    f = post_facts(st, world) if st else Facts()
    f.kind = set()  # the event isn't a post: its post's kind stays in target
    if st:
        f.target = _target(real(st), world)
    typ = notification.get("type") or ""
    f.event = {EVENT_OF.get(typ, typ)} if typ != "mention" else set()
    if typ == "fedtail.unfollow" and (notification.get("account") or {}).get("_back"):
        f.event.add("unfollowed_back")  # one I follow too
    f.author = _author_atoms(notification.get("account") or {}, world, now)
    f.id |= {notification.get("id", "")}
    f.created = _when(notification.get("created_at")) or f.created
    return f


# ---- conditions and rules ----------------------------------------------------------------

def _check_value(key, v, warn):
    if not isinstance(v, str) or not v:
        warn(f"{key}: {v!r} is not a word")
        return False
    known = _SET_KEYS[key]
    if key == "source" and v.startswith(SOURCE_PREFIXES) and v.split(":", 1)[1]:
        return True
    if key == "author" and (re.fullmatch(r"@?[^@\s]+@[^@\s]+", v)
                            or re.fullmatch(r"domain:(\{[^{}]+\}|[^{}\s]+)", v)):
        return True
    if key == "has" and v.startswith(HAS_PREFIXES) and v.split(":", 1)[1]:
        return True
    if key in ("lang", "id"):
        return True
    if known is not None and v in known:
        return True
    warn(f"{key}: unknown value {v!r}")
    return False


def _norm(key, v):
    if key == "author" and "@" in v and not v.startswith("domain:"):
        return "@" + norm_acct(v)
    if key in ("lang", "has") or key == "author" and v.startswith("domain:"):
        return v.lower()
    return v


def _words(v):
    return [v] if isinstance(v, str) else list(v) if isinstance(v, (list, tuple)) else [v]


def _cmp(op, a, b):
    return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b, "=": a == b}[op]


@dataclass
class Condition:
    """One table of `any` / `none`: every key must match."""
    sets: dict = field(default_factory=dict)    # key → set of words (any of them)
    counts: dict = field(default_factory=dict)  # likes / boosts / replies → (op, n)
    age: tuple | None = None                    # (op, timedelta)
    age_of: str = "post"                        # post | original
    text: list = field(default_factory=list)    # OR of AND groups
    text_in: tuple = ("text", "cw")
    text_case: bool = False
    text_regex: bool = False
    switch: str = ""                            # a chip over the lane (feeds.md §4)
    shown: bool = True
    priority: int = 0
    apart: str = ""                             # counts only while this lane is shown
    until: datetime | None = None               # holds till then, never after
    inner: list = field(default_factory=list)   # `any` inside: one of these too
    broken: bool = False                        # had an unknown key or value: never matches
    raw: dict = field(default_factory=dict)

    @classmethod
    def parse(cls, table, warnings=None):
        warnings = [] if warnings is None else warnings
        c = cls(raw=dict(table) if isinstance(table, dict) else {})

        def warn(msg):
            warnings.append(msg)
            c.broken = True

        if not isinstance(table, dict):
            warn(f"a condition is a table, not {table!r}")
            return c
        for key, value in table.items():
            if key not in CONDITION_KEYS:
                warn(f"unknown key {key!r}")
            elif key in _SET_KEYS:
                words = _words(value)
                good = {_norm(key, w) for w in words if _check_value(key, w, warn)}
                if key == "has":  # "word:x" is text matching
                    for w in [w for w in good if w.startswith("word:")]:
                        good.discard(w)
                        c.text.append([w[5:]])
                if good:
                    c.sets[key] = good
            elif key in _COUNT_KEYS:
                m = _COUNT_RE.match(str(value))
                if m:
                    c.counts[key] = (m.group(1) or ">=", int(m.group(2)))
                else:
                    warn(f"{key}: {value!r} — a number with <, >, <=, >= or =")
            elif key == "age":
                m = _AGE_RE.match(str(value))
                if m:
                    c.age = (m.group(1), float(m.group(2)) * _UNIT[m.group(3)])
                else:
                    warn(f"age: {value!r} — like \"<1d\", \">2h\" (m, h, d, w)")
            elif key == "age_of":
                if value in ("post", "original"):
                    c.age_of = value
                else:
                    warn(f"age_of: {value!r} — post or original")
            elif key == "text":
                groups = [[value]] if isinstance(value, str) else \
                    [_words(g) for g in value] if isinstance(value, (list, tuple)) else None
                if not groups or any(not all(isinstance(w, str) and w for w in g)
                                     for g in groups):
                    warn(f"text: {value!r} — a list of groups of words")
                else:
                    c.text += [g for g in groups if g]
            elif key == "text_in":
                where = _words(value)
                bad = [w for w in where if w not in TEXT_IN]
                if bad or not where:
                    warn(f"text_in: {bad or value!r} — of {sorted(TEXT_IN)}")
                else:
                    c.text_in = tuple(where)
            elif key in ("text_case", "text_regex", "shown"):
                if isinstance(value, bool):
                    setattr(c, key, value)
                else:
                    warn(f"{key}: true or false, not {value!r}")
            elif key == "switch":
                if isinstance(value, str) and value:
                    c.switch = value
                else:
                    warn(f"switch: a word for the chip, not {value!r}")
            elif key == "apart":
                if isinstance(value, str) and value:
                    c.apart = value
                else:
                    warn(f"apart: a lane's name, not {value!r}")
            elif key == "priority":
                if isinstance(value, int) and not isinstance(value, bool):
                    c.priority = value
                else:
                    warn(f"priority: a number, not {value!r}")
            elif key == "until":
                when = _until(value)
                if when is None:
                    warn(f"until: {value!r} — a date, like \"2026-11-01\" or "
                         f"\"2026-11-01T18:00\"")
                else:
                    c.until = when
            elif key == "any":
                if not isinstance(value, (list, tuple)) or not value:
                    warn(f"any: a list of tables (one of them), not {value!r}")
                else:
                    inner = [cls.parse(t, warnings) for t in value]
                    if any(i.broken for i in inner):
                        c.broken = True
                    c.inner = inner
        if c.text_regex and not c.broken:
            flags = 0 if c.text_case else re.I
            try:
                c.text = [[re.compile(w, flags) for w in g] for g in c.text]
            except re.error as e:
                warn(f"text: not a regular expression ({e})")
        return c

    @property
    def needs(self):
        """The axes this condition asks about (post_facts computes only these)."""
        out = set(self.sets)
        if self.text:
            out.add("text")
        for i in self.inner:
            out |= i.needs
        return out

    def _text_ok(self, facts):
        hay = "\n".join(facts.texts.get(k, "") for k in self.text_in)
        if not self.text_case and not self.text_regex:
            hay = hay.casefold()
        for group in self.text:
            if all((w.search(hay) if self.text_regex else
                    (w if self.text_case else w.casefold()) in hay) for w in group):
                return True
        return False

    def matches(self, facts, now=None):
        if self.broken:
            return False
        if self.until is not None and (now or datetime.now(UTC)) >= self.until:
            return False  # its time is over: as if it weren't there
        for key, words in self.sets.items():
            if key == "author":
                if not any(_author_word(w, facts.author) for w in words):
                    return False
            elif not getattr(facts, key) & words:
                return False
        for key, (op, n) in self.counts.items():
            if not _cmp(op, facts.counts.get(key, 0), n):
                return False
        if self.age:
            when = facts.original_created if self.age_of == "original" else facts.created
            if when is None:
                return False
            now = now or datetime.now(UTC)
            if not _cmp(self.age[0], now - when, self.age[1]):
                return False
        if self.text and not self._text_ok(facts):
            return False
        if self.inner and not any(i.matches(facts, now) for i in self.inner):
            return False
        return True

    def why_not(self, facts, now=None):
        """The first key that kept this post out ("" — it matched), for "Why is it here?"
        and --explain-lane."""
        if self.broken:
            return "the condition has an error"
        for key in self.sets:
            if not Condition(sets={key: self.sets[key]}).matches(facts, now):
                return key
        for key in self.counts:
            if not Condition(counts={key: self.counts[key]}).matches(facts, now):
                return key
        if self.age and not Condition(age=self.age, age_of=self.age_of).matches(facts, now):
            return "age"
        if self.text and not self._text_ok(facts):
            return "text"
        if self.inner and not any(i.matches(facts, now) for i in self.inner):
            return "any"
        return ""


def _author_word(word, have):
    if word.startswith("domain:{") and word.endswith("}"):
        return any(f"domain:{d.strip().lower()}" in have for d in word[8:-1].split(","))
    return word in have


# what a free lane's table may hold besides its conditions (feeds.md §4)
RULE_KEYS = {"name", "title", "any", "none", "source", "sort", "read", "group", "mode",
             "window", "filter_context", "icon", "per_author", "bundle", "view", "open_at",
             "start", "hide_empty"}
# the pictures a lane may wear (`icon`): the built-in lanes' own, by the word the
# frontends' icon set has for each (frontends/iconpack.py LANE)
LANE_ICONS = ("home", "local", "federated", "bots", "my_posts", "direct", "replies",
              "mentions", "subs", "bookmarks", "my_likes", "activity", "requests", "list",
              "tags", "star_full")
# the library of pictures for one's own lanes (data/icons/lanes, tools/lane_pictures.py)
LANE_LIBRARY = ("bolt", "book", "bulb", "calendar", "camera", "car", "chart", "clock",
                "cloud", "code", "commented", "cup", "film", "fire", "fish", "flag",
                "flask", "food",
                "game", "globe", "heart", "image", "important", "inbox", "leaf", "link",
                "megaphone", "moon", "mountain", "music", "news", "palette", "paw",
                "people", "person", "pin", "plane", "quote", "rss", "search", "shield",
                "sparkle", "sun", "wrench")
LANE_ICONS = tuple(dict.fromkeys(LANE_ICONS + LANE_LIBRARY))
_RULE_WORDS = {"sort": {"arrival", "post_time", "replies", "likes", "boosts", "density"},
               "read": {"through", "browse"}, "mode": {"lane", "catch_up"},
               "filter_context": {"home", "public", "notifications", "thread", "account"},
               # catch-up: each author's posts together, the busiest author first
               "bundle": {"", "author"},
               # "threads": one card a thread — its post, with how many new comments
               # (as on Point); a click opens it at the first of them
               "view": {"", "threads"},
               # where a thread opened from its card opens; "" — threads.open_at
               "open_at": {"", "post", "first_unread"}}


@dataclass
class Rule:
    """A free lane's rule: a post goes in if it matches any of `any` and none of `none`;
    `source`, when given, narrows every condition to those sources."""
    name: str
    title: str = ""
    any: list = field(default_factory=list)
    none: list = field(default_factory=list)
    source: set = field(default_factory=set)
    sort: str = "arrival"
    read: str = "through"
    group: str = ""
    mode: str = "lane"
    window: timedelta | None = None
    filter_context: str = ""
    icon: str = ""                 # one of LANE_ICONS; "" — the lane's own, or a list's
    per_author: int = 0            # at most so many posts of one author (the newest); 0 — any
    bundle: str = ""               # "author": each author's posts together
    view: str = ""                 # "threads": one card a thread, the new comments counted
    open_at: str = ""              # a thread from its card: "post" / "first_unread"; ""
                                   # — as threads.open_at says
    hide_empty: bool = False       # shown only once something is in it ("Important people")
    start: bool = False            # the set's lane to open first, when ui.start_lane names
                                   # none there (common/sidebar.start_lane)
    warnings: list = field(default_factory=list)

    @classmethod
    def parse(cls, table):
        warnings = []
        if not isinstance(table, dict):
            return cls(name="", warnings=[f"a lane is a table, not {table!r}"])
        name = table.get("name")
        rule = cls(name=name if isinstance(name, str) else "", warnings=warnings)
        if not rule.name:
            warnings.append("a lane needs a name")
        title = table.get("title") or rule.name
        if isinstance(title, dict):  # one per language: { ru = "Посты", en = "Posts" }
            title = {str(k): str(v) for k, v in title.items() if v} or rule.name
        rule.title = title if isinstance(title, dict) else str(title)
        for key in table:
            if key not in RULE_KEYS:
                warnings.append(f"unknown key {key!r}")
        for key in ("any", "none"):
            value = table.get(key, [])
            if isinstance(value, dict):
                value = [value]
            if not isinstance(value, list):
                warnings.append(f"{key}: a list of conditions")
                continue
            setattr(rule, key, [Condition.parse(t, warnings) for t in value])
        if "source" in table:
            for s in _words(table["source"]):
                if _check_value("source", s, warnings.append):
                    rule.source.add(s)
        for key, words in _RULE_WORDS.items():
            if key in table:
                if table[key] in words:
                    setattr(rule, key, table[key])
                else:
                    warnings.append(f"{key}: {table[key]!r} — one of {sorted(words)}")
        if "group" in table:
            rule.group = str(table["group"])
        for flag in ("start", "hide_empty"):
            if flag in table:
                if isinstance(table[flag], bool):
                    setattr(rule, flag, table[flag])
                else:
                    warnings.append(f"{flag}: {table[flag]!r} — true or false")
        if "icon" in table:
            if table["icon"] in LANE_ICONS:
                rule.icon = table["icon"]
            else:
                warnings.append(f"icon: {table['icon']!r} — one of "
                                f"{', '.join(sorted(LANE_ICONS))}")
        if "per_author" in table:
            v = table["per_author"]
            if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
                rule.per_author = v
            else:
                warnings.append(f"per_author: {v!r} — a number of posts, 0 — any")
        if "window" in table:
            m = _AGE_RE.match("<" + str(table["window"]).lstrip("<>="))
            if m:
                rule.window = float(m.group(2)) * _UNIT[m.group(3)]
            else:
                warnings.append(f"window: {table['window']!r} — like \"12h\", \"2d\"")
        if rule.mode == "catch_up" and rule.window is None:
            rule.window = timedelta(hours=12)
        if not rule.any:
            warnings.append("the lane takes nothing: `any` is empty")
        for c in rule.any:
            reason = never(c)
            if reason:
                warnings.append(f"never filled: {reason}")
        return rule

    @property
    def needs(self):
        return set().union(*(c.needs for c in self.any + self.none)) if self.any or self.none \
            else set()

    def _narrowed(self, facts):
        return not self.source or bool(facts.source & self.source)

    def taken_by(self, facts, now=None):
        """The condition that takes this post (the first of `any`, by priority), or None."""
        if not self._narrowed(facts) or any(c.matches(facts, now) for c in self.none):
            return None
        for c in sorted(self.any, key=lambda c: -c.priority):
            if c.matches(facts, now):
                return c
        return None

    def takes(self, facts, now=None):
        return self.taken_by(facts, now) is not None

    def explain(self, facts, now=None):
        """[(where, condition index, "" or what kept it out)] — every condition's verdict."""
        out = []
        if not self._narrowed(facts):
            out.append(("source", -1, "source"))
        out += [("none", i, c.why_not(facts, now)) for i, c in enumerate(self.none)]
        out += [("any", i, c.why_not(facts, now)) for i, c in enumerate(self.any)]
        return out


# combinations no server ever gives a client (feeds.md §3)
def never(cond):
    """Why a condition can't be filled by any source, or ""."""
    s = cond.sets
    who = s.get("author", set())
    if s.get("visibility") == {"followers"} and who and who <= {"stranger", "not_follower"}:
        return "followers-only posts of people I don't follow never reach me"
    if s.get("source") == {"home"} and s.get("kind") == {"reply"} and \
            s.get("parent") == {"stranger"} and who and who <= {"followed"}:
        return "Mastodon's home drops replies of the followed to people I don't follow"
    if s.get("source") and s["source"] <= {"local", "federated", "trends"} and \
            s.get("visibility") and s["visibility"] <= {"unlisted", "followers", "direct"}:
        return "public lanes hold public posts only"
    if cond.inner and all(never(i) for i in cond.inner):
        return never(cond.inner[0])
    return ""
