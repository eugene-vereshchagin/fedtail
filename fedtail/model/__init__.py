"""fedtail's own data model: what the core hands the frontends, whatever the protocol.

Every protocol (``fedtail/protocols/<name>/``) turns its server's objects into these;
nothing outside ``fedtail/protocols/`` reads a server's JSON (docs/PROTOCOLS.md). The
vocabulary is ActivityPub's — a post is a Note, a boost an Announce ("share"), a poll a
Question — not the shape of one server's API.

All types are frozen dataclasses with slots: cheap to keep thousands of, safe to hand
between threads. A change (a new like count, a vote) is a new object made with
``dataclasses.replace``. Times are aware ``datetime`` in UTC; ids are opaque strings,
never compared as numbers — order comes from ``Post.sort``.

Text is a sanitised subset of HTML (``<p> <br> <a> <span> <b> <i> <em> <strong> <code>
<pre> <blockquote> <ul> <ol> <li>`` and the like), the one format every frontend parses:
ActivityPub carries HTML already, other markups are turned into it by their protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# who may see a post, from the widest to the narrowest
VISIBILITIES = ("public", "unlisted", "followers", "direct")

# what a media attachment is
MEDIA_KINDS = ("image", "gifv", "video", "audio", "unknown")

# what happened, in an Activity
ACTIVITY_KINDS = (
    "mention",         # a post mentioning me (a reply too)
    "like",            # somebody liked my post
    "share",           # somebody boosted my post
    "quote",           # somebody quoted my post
    "follow",          # somebody follows me now
    "follow_request",  # somebody asks to follow me
    "poll",            # a poll I voted in or made has ended
    "update",          # a post I boosted or quoted was edited
    "post",            # somebody I "ring the bell" for posted
    "reaction",        # an emoji reaction to my post (Akkoma, Misskey)
    "notice",          # the server tells me something (moderation, severed follows…)
    "other",
)


@dataclass(frozen=True, slots=True)
class Ref:
    """Where an object comes from: which protocol, which profile (account) of this
    fedtail, and its id there. Objects of different accounts never mix up in one
    window (ui.merge), even when two servers hand out the same id."""
    proto: str
    profile: str
    id: str

    def __str__(self):
        return f"{self.proto}:{self.profile}:{self.id}"


@dataclass(frozen=True, slots=True)
class Emoji:
    """A custom emoji: :shortcode: in a text becomes this picture."""
    shortcode: str
    url: str
    static_url: str = ""


@dataclass(frozen=True, slots=True)
class Field:
    """A line of a profile's table: name, value (HTML), and when the server checked
    that the link in it points back (None: not checked)."""
    name: str
    value: str
    verified: datetime | None = None


@dataclass(frozen=True, slots=True)
class Account:
    """A person, a bot, a group (a Person, a Service, a Group in ActivityPub)."""
    ref: Ref
    handle: str                    # user@server; a bare "user" for my own server's people
    username: str
    name: str = ""                 # display name, may hold :emoji:
    url: str = ""                  # the profile page
    uri: str = ""                  # the ActivityPub id
    avatar: str = ""
    avatar_static: str = ""
    header: str = ""
    header_static: str = ""
    note: str = ""                 # the bio, HTML
    fields: tuple[Field, ...] = ()
    emojis: tuple[Emoji, ...] = ()
    bot: bool = False
    group: bool = False
    locked: bool = False           # follow requests are approved by hand
    discoverable: bool | None = None
    created: datetime | None = None
    last_post: datetime | None = None
    posts: int = 0
    followers: int = 0
    following: int = 0
    moved: Account | None = None   # the account moved there

    @property
    def id(self):
        return self.ref.id


@dataclass(frozen=True, slots=True)
class Mention:
    ref: Ref
    handle: str
    username: str = ""
    url: str = ""
    uri: str = ""

    @property
    def id(self):
        return self.ref.id


@dataclass(frozen=True, slots=True)
class Media:
    ref: Ref
    kind: str = "unknown"          # one of MEDIA_KINDS
    url: str = ""                  # on my server (or the original)
    preview: str = ""
    remote_url: str = ""           # on the author's server
    alt: str = ""
    width: int = 0
    height: int = 0
    duration: float = 0.0          # seconds, for video and audio
    focus: tuple[float, float] | None = None  # -1…1, where to crop around
    blurhash: str = ""


@dataclass(frozen=True, slots=True)
class PollOption:
    title: str
    votes: int | None = None       # None: the server hides counts until it ends
    emojis: tuple[Emoji, ...] = ()


@dataclass(frozen=True, slots=True)
class Poll:
    ref: Ref
    options: tuple[PollOption, ...]
    multiple: bool = False
    expires: datetime | None = None
    expired: bool = False
    votes: int = 0
    voters: int | None = None
    voted: bool = False
    my_votes: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class Card:
    """A link preview under a post."""
    url: str
    title: str = ""
    description: str = ""
    image: str = ""
    image_alt: str = ""
    provider: str = ""
    kind: str = "link"             # link, photo, video, rich
    author: str = ""
    width: int = 0
    height: int = 0


@dataclass(frozen=True, slots=True)
class Quote:
    """The post this one quotes. post is None when only its id is known (fetch it) or
    when it can't be shown (state says why: pending, rejected, revoked, deleted…)."""
    state: str = "accepted"
    post: Post | None = None
    id: str | None = None


@dataclass(frozen=True, slots=True)
class Reaction:
    """An emoji reaction (Akkoma, Misskey): the emoji, how many, did I."""
    name: str
    count: int = 0
    me: bool = False
    url: str = ""


@dataclass(frozen=True, slots=True)
class Counts:
    replies: int = 0
    shares: int = 0
    likes: int = 0
    quotes: int = 0


@dataclass(frozen=True, slots=True)
class Mine:
    """What I did to a post."""
    liked: bool = False
    shared: bool = False
    bookmarked: bool = False
    muted: bool | None = None      # the thread is muted; None: the server didn't say
                                   #   (it says so only for threads I'm in)
    pinned: bool = False


@dataclass(frozen=True, slots=True)
class Policy:
    """Who may do what to a post (GoToSocial interaction policies, Mastodon's quote
    approval): for each action the audiences that may at once and with approval —
    "public", "followers", "following", "mentioned", "author", or a handle."""
    reply: tuple[str, ...] = ()
    reply_approval: tuple[str, ...] = ()
    share: tuple[str, ...] = ()
    share_approval: tuple[str, ...] = ()
    like: tuple[str, ...] = ()
    like_approval: tuple[str, ...] = ()
    quote: tuple[str, ...] = ()
    quote_approval: tuple[str, ...] = ()
    can_quote: str = ""            # what my server says I may do: automatic, manual, denied


@dataclass(frozen=True, slots=True)
class Post:
    """A post: a Note (or an Article, a Page, a Question) in ActivityPub."""
    ref: Ref
    author: Account
    created: datetime | None
    sort: str                      # orders posts of one profile as text, oldest first
    text: str = ""                 # HTML
    source: str = ""               # what the author typed (Markdown, plain), when given:
    source_type: str = ""          #   GoToSocial sends it with my own posts; a MIME type
    warning: str = ""              # the content warning (spoiler); "" — none
    sensitive: bool = False        # media hidden until clicked
    visibility: str = "public"     # one of VISIBILITIES
    local_only: bool = False       # stays on its server (no federation)
    lang: str = ""
    url: str = ""                  # the page to open in a browser
    uri: str = ""                  # the ActivityPub id
    kind: str = "Note"             # the ActivityPub type, when the server says
    title: str = ""                # an Article's or a Page's name
    reply_to: str | None = None    # id of the parent
    reply_to_author: str | None = None
    edited: datetime | None = None
    media: tuple[Media, ...] = ()
    poll: Poll | None = None
    card: Card | None = None
    quote: Quote | None = None
    mentions: tuple[Mention, ...] = ()
    tags: tuple[str, ...] = ()     # hashtags, without #
    emojis: tuple[Emoji, ...] = ()
    reactions: tuple[Reaction, ...] = ()
    counts: Counts = field(default_factory=Counts)
    mine: Mine = field(default_factory=Mine)
    policy: Policy | None = None
    app: str = ""                  # the client it was posted from, when shown
    filtered: tuple[str, ...] = ()  # titles of my filters it matched ("warn" ones)
    hidden: bool = False           # a "hide" filter matched

    @property
    def id(self):
        return self.ref.id


@dataclass(frozen=True, slots=True)
class Share:
    """A boost: somebody passing a post on (an Announce). It has its own id and time,
    and that's what a lane holds; the post is inside."""
    ref: Ref
    by: Account
    post: Post
    created: datetime | None
    sort: str
    visibility: str = "public"

    @property
    def id(self):
        return self.ref.id


@dataclass(frozen=True, slots=True)
class Activity:
    """Something that happened to me: a like, a follow, a mention… (a notification)."""
    ref: Ref
    kind: str                      # one of ACTIVITY_KINDS
    who: Account | None
    created: datetime | None
    sort: str
    post: Post | None = None
    emoji: str = ""                # for a reaction
    notice: str = ""               # for a notice: what the server says, as text
    group_key: str = ""            # the server's grouping key, when it groups them

    @property
    def id(self):
        return self.ref.id


@dataclass(frozen=True, slots=True)
class ServerInfo:
    """My server about itself."""
    title: str = ""
    domain: str = ""
    description: str = ""          # HTML, or plain text (some servers)
    contact: Account | None = None
    email: str = ""
    rules: tuple[tuple[str, str], ...] = ()  # (rule, hint)
    about: str = ""                # HTML: the long description
    privacy: str = ""              # HTML: the privacy policy


@dataclass(frozen=True, slots=True)
class Tag:
    """A hashtag: its name (without #), whether I follow it, how much it's used."""
    name: str
    url: str = ""
    following: bool | None = None  # None: the server didn't say
    posts: int = 0                 # on someone's profile: how many of their posts carry it
    uses: int = 0                  # these days, in all (the server's history)
    people: int = 0                # these days, how many people used it
    last_post: datetime | None = None


@dataclass(frozen=True, slots=True)
class Relationship:
    """Between me and an account."""
    following: bool = False
    followed_by: bool = False
    requested: bool = False        # I asked to follow, not answered yet
    requested_by: bool = False     # they asked to follow me
    muting: bool = False
    blocking: bool = False
    blocked_by: bool = False
    notifying: bool = False        # the bell: their new posts come as notifications
    showing_shares: bool = True    # their boosts come into Home
    endorsed: bool = False         # shown on my profile
    note: str = ""                 # my private note on them
    languages: tuple[str, ...] | None = None  # only these of theirs come to Home (None: all)


@dataclass(frozen=True, slots=True)
class ThreadItem:
    """A post in a thread, in reading order: how deep it hangs and its number there
    (0 for the root, then /1 /2 … like on Point)."""
    post: Post
    depth: int
    number: int


def real(entry):
    """The post a lane entry is about: the boosted one for a Share, else the post."""
    return entry.post if isinstance(entry, Share) else entry
