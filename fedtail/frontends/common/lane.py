"""What a lane shows, without a toolkit: the cards (CardSpec) built from the View's
entries — with what each answers, my replies, the short #ids — the "new below" divider
fixed where reading stood, the filters (everything / posts only / what was unread),
conversations instead of the feed, the media funnel, where reading starts, and the rule
for "seen on screen = read". qt/feed.py LaneWidget and gtk/lane.py LaneView draw this.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ...i18n import _
from ...model import Share, real
from ...model.text import snippet

POSTS_ONLY_LANES = ("home", "bots", "my_posts", "local")  # "posts only" makes sense here
CONVERSATION_LANES = ("replies", "mentions", "subs")       # …and "as conversations" here
MEDIA_KINDS = ("text", "image", "gifv", "video", "audio")
VIDEO_EXT = (".mp4", ".webm", ".mov", ".m4v", ".mkv", ".ogv")
SEPARATOR = "__sep__"


@dataclass
class CardSpec:
    """What one card shows: a post of fedtail.model (a Post, or a Share around one),
    and where and how. Cards read nothing else of the server (docs/PROTOCOLS.md)."""
    key: str                   # unique within a view (item id or status id)
    entry: object = None       # Post | Share; None for the "new below" divider
    depth: int = 0
    number: int | None = None  # /N inside a thread
    parent: object = None      # the Post it answers, "missing", or None (unknown / no reply)
    unread: bool = False
    focus: bool = False
    in_thread: bool = False
    extra: dict = field(default_factory=dict)  # my_replies, short_id, separator, via…

    @property
    def post(self):
        """The post itself (the one inside a Share), or None."""
        return real(self.entry) if self.entry is not None else None


def make_spec(view, key, entry, extra=None, **kw):
    """A CardSpec for a lane entry (Post | Share) of the View: with which account of
    mine got it, when the window shows several."""
    extra = dict(extra or {})
    via = view.via(entry)
    if via:
        extra["via"] = via
    return CardSpec(key=key, entry=entry, extra=extra, **kw)


def account_color(name):
    """A colour of its own for each account of mine, from its name: steady, readable
    under white letters (Qt's QColor.fromHsl(h, 150, 105)), "#rrggbb"."""
    import colorsys
    import hashlib
    h = int(hashlib.sha1(name.lower().encode()).hexdigest()[:4], 16) % 360
    r, g, b = colorsys.hls_to_rgb(h / 360, 105 / 255, 150 / 255)
    return "#" + "".join(f"{round(x * 255):02x}" for x in (r, g, b))


def true_kind(m):
    """Servers sometimes call a video an "image" (a remote one they couldn't sort);
    the file's name knows better. A copy with the right kind."""
    url = (m.url or m.remote_url).lower().split("?")[0]
    if m.kind in ("image", "unknown") and url.endswith(VIDEO_EXT):
        return replace(m, kind="video")
    return m


def thumb_box(w, h, height, max_w):
    """The box a picture of w×h gets in a card: `height` tall and as wide as its shape
    says, but no wider than max_w (then less tall); unknown size: a square."""
    if not (w and h):
        return height, height
    tw = int(height * w / h)
    if tw <= max_w:
        return max(tw, 24), height
    return max_w, max(24, int(max_w * h / w))


def card_boxes(media, cfg, small=(150, 230)):
    """(height, max width) of the pictures of a post: one alone — ui.image_height tall,
    across the lane's width; several — a smaller tile each."""
    visual = [m for m in media if m.kind in ("image", "gifv", "video") and (m.preview or m.url)]
    if len(visual) == 1:
        return cfg["ui"]["image_height"], max(200, (cfg["ui"]["max_width"] or 900) - 60)
    return small


def decode_side(tw, th, w, h, cfg, dpr=1.0, most=1200):
    """How big a feed picture has to be decoded for its box (filled, on this screen's
    pixel density), in steps of 100 — not the 1200 px of before: a picture kept in memory
    four times the pixels it is shown at was most of the memory a lane held
    (ui.image_decode = "box"). None: as before."""
    if cfg["ui"].get("image_decode", "box") != "box":
        return None
    if w and h:  # filling the box: the short side reaches it, the long one goes past
        scale = max(tw / w, th / h)
        need = max(w, h) * scale
    else:
        need = max(tw, th) * 2
    need = int(-(-need * max(1.0, dpr) // 100) * 100)
    return max(100, min(most, need))


def media_kinds(entry):
    """What a post (Post | Share) shows: {"image", "gifv", "video", "audio"} from its
    attachments (a video a server called a picture counts as a video), or {"text"}."""
    kinds = {true_kind(m).kind for m in real(entry).media}
    kinds &= set(MEDIA_KINDS)
    return kinds or {"text"}


class MediaFilter:
    """The funnel: only posts with pictures, gifs, video… and boosts or not — for this
    run only (never saved: posts that vanish after a restart drive one mad)."""

    def __init__(self):
        self.wanted = set(MEDIA_KINDS)
        self.boosts = True

    def active(self):
        return self.wanted != set(MEDIA_KINDS) or not self.boosts

    def keeps(self, entry):
        if not self.boosts and isinstance(entry, Share):
            return False
        return self.wanted == set(MEDIA_KINDS) or bool(media_kinds(entry) & self.wanted)

    def toggle(self, kind, on):
        (self.wanted.add if on else self.wanted.discard)(kind)

    def reset(self):
        self.wanted = set(MEDIA_KINDS)
        self.boosts = True


@dataclass
class Built:
    """A lane drawn: the cards top to bottom (the divider among them, a CardSpec with
    key SEPARATOR), the line for the header (unread-only / media funnel), how many are
    unread, and whether a browse lane came back empty from the server."""
    specs: list
    info: str = ""
    unread: int = 0
    empty: bool = False


class LaneModel:
    """The state of a lane's choices and how its cards are made. separator_text(n)
    is the theme's words for the divider."""

    def __init__(self, view, name, separator_text=None):
        self.view, self.name = view, name
        self.cfg = view.cfg
        self.newest_first = self.cfg["feed"]["order"] == "newest_first"
        lane = view.lane_by_name.get(name)
        self.lazy = bool(getattr(lane, "lazy", False))
        self.has_posts_only = name in POSTS_ONLY_LANES or name.startswith("list:")
        self.separator_text = separator_text or (lambda n: _("new_below"))
        self.separator = None    # (key of the first unread when the lane opened, count)
        self.kept = None         # "unread only": the item keys shown while it's open
        self.conv_members = {}   # conversation top id -> member ids
        self.media = MediaFilter()
        opts = ["all"]
        if self.has_posts_only:
            opts.append("posts")
        if not self.lazy:
            opts.append("unread")
        self.filters = opts      # what the filter control offers ("all" alone: none)

    # ---- the choices -------------------------------------------------------------------
    def current_filter(self):
        if self.has_posts_only and self.view.posts_only(self.name):
            return "posts"
        if "unread" in self.filters and self.view.choice(f"unread_only.{self.name}"):
            return "unread"
        return "all"

    def unread_only(self):
        return len(self.filters) > 1 and self.current_filter() == "unread"

    def set_filter(self, which):
        """"all", "posts" (no replies) or "unread"; the caller places the lane anew."""
        if self.has_posts_only and self.view.posts_only(self.name) != (which == "posts"):
            self.view.set_posts_only(self.name, which == "posts")
        self.view.set_choice(f"unread_only.{self.name}", which == "unread")
        self.kept = None
        self.separator = None

    def conversations_offered(self):
        return self.name in CONVERSATION_LANES

    def conversations(self):
        return self.conversations_offered() and \
            bool(self.view.choice(f"conversations.{self.name}"))

    def set_conversations(self, on):
        self.view.set_choice(f"conversations.{self.name}", bool(on))
        self.separator = None

    def left(self):
        """The lane went out of sight: "unread only" shows anew what's unread next time."""
        if self.unread_only():
            self.kept = None
            return True
        return False

    # ---- the cards ----------------------------------------------------------------------
    def build(self, positioned):
        """The cards as they are now. positioned: the reader has been placed in the lane
        already (the divider stays where it was then)."""
        view = self.view
        entries = view.entries(self.name)  # [(item id, Post | Share)], oldest first
        unread = set() if self.lazy else view.unread(entries)
        info = ""
        if self.unread_only():
            fresh = {item for item, e in entries if e.id in unread}
            self.kept = fresh if self.kept is None else self.kept | fresh
            entries = [e for e in entries if e[0] in self.kept]
            info = _("unread_only_info", n=len(fresh)) if self.kept else _("unread_only_none")
        if self.media.active():
            entries = [x for x in entries if self.media.keeps(x[1])]
            info = _("media_filter_info", n=len(entries))
        posts = [e for _, e in entries]
        parents = view.parents(posts)
        answers = view.my_replies(posts)  # {post id: [my replies to it]}
        short = view.short_ids(posts)
        specs, unknown = [], []
        for item_id, e in entries:
            parent = parents.get(e.id)
            if parent is None and real(e).reply_to:
                unknown.append(e)
            pid = real(e).id
            specs.append(make_spec(view, item_id, e, parent=parent, unread=e.id in unread,
                                   extra={"my_replies": answers.get(pid, []),
                                          "short_id": short.get(pid)}))
        if self.conversations():
            specs = self._conversation_specs(entries, unread, parents, answers, short)
        if self.name in ("replies", "mentions"):
            view.check_my_replies(posts)
        if unknown:
            view.ensure_parents(unknown)
        # "new below": fixed where the reader stood when the lane opened
        if self.separator is None and not positioned and not self.unread_only():
            first = next((s for s in specs if s.unread), None)
            if first is not None and any(not s.unread for s in specs):
                self.separator = (first.key, sum(1 for s in specs if s.unread))
        if self.separator and any(s.key == self.separator[0] for s in specs):
            i = next(i for i, s in enumerate(specs) if s.key == self.separator[0])
            specs.insert(i, CardSpec(key=SEPARATOR, extra={
                "separator": self.separator_text(self.separator[1])}))
        if self.newest_first:
            specs.reverse()
        lane = view.lane_by_name.get(self.name)
        empty = self.lazy and not specs and lane is not None and \
            lane.source in getattr(view, "browse_empty", ())
        return Built(specs, info, sum(1 for s in specs if s.unread), empty)

    def _conversation_specs(self, entries, unread, parents, answers, short):
        """One card per conversation: its top post, with a line about the rest."""
        view = self.view
        groups = view.conversations(entries, unread)
        tops = [g["top"] for g in groups]
        more_short = view.short_ids(tops)
        self.conv_members = {g["top"].id: g["members"] for g in groups}
        specs = []
        for g in groups:
            top = g["top"]
            pid = real(top).id
            specs.append(make_spec(
                view, "conv:" + g["key"], top,
                parent=parents.get(top.id) or view.parent(top),
                unread=g["unread"] > 0,
                extra={"my_replies": answers.get(pid, []),
                       "short_id": more_short.get(pid) or short.get(pid),
                       "conversation": {"members": g["members"], "unread": g["unread"],
                                        "last": g["last"]}}))
        return specs

    # ---- where reading starts, what was read -------------------------------------------
    def start(self, specs):
        """Where reading starts: (key, "top" | "bottom"), or (None, "end") for the
        lane's newest end (feed.start_at)."""
        unread = [s.key for s in specs if s.unread]
        if self.cfg["feed"]["start_at"] == "first_unread" and unread:
            if self.newest_first:
                return unread[-1], "bottom"
            if any(s.key == SEPARATOR for s in specs):
                return SEPARATOR, "top"
            return unread[0], "top"
        return None, "end"

    def start_key(self, specs):
        """The card reading starts at (the ones around it are built first)."""
        if not specs:
            return None
        key, _where = self.start(specs)
        if key is not None:
            return key
        return specs[0].key if self.newest_first else specs[-1].key

    def read(self, ids):
        """Ids seen on screen → the post ids to mark read (read.mark_read = "on_scroll";
        a conversation card seen = its members seen). [] when reading is by hand."""
        if self.cfg["read"]["mark_read"] != "on_scroll":
            return []
        return [m for i in ids for m in self.conv_members.get(i, [i])]


def read_up_to(entries, sid):
    """⋯ → "Read up to here": the ids of this post and of every one older than it among
    entries (a lane, a thread, a profile — whichever way round it is shown), by their
    time, not by where they stand: Qt went by feed.order, wrong in a profile shown newest
    first, and kept only those its view marked unread (none in a profile) — the
    behaviour check of 23.10 found it marking nothing. [sid] when sid isn't among them."""
    entries = [e for e in entries if e is not None]
    target = next((e for e in entries if e.id == sid or real(e).id == sid), None)
    if target is None:
        return [sid]
    def time(e):  # a boost stands where it was boosted
        return getattr(e, "created", None) or real(e).created
    when = time(target)
    if when is None:  # no times: by place, as shown
        at = entries.index(target)
        return [e.id for e in entries[:at + 1]]
    out = []
    for e in entries:
        t = time(e)
        if e is target or (t is not None and t <= when):
            out.append(e.id)
            if real(e).id != e.id:
                out.append(real(e).id)
    return list(dict.fromkeys(out))


def age_days(p, cfg):
    """How many days old a post is, when that's more than feed.old_days; else 0 — an
    old post pulled from someone's outbox is marked "old", not read as news."""
    limit = int(cfg["feed"].get("old_days", 30) or 0)
    if not limit or p.created is None:
        return 0
    from datetime import UTC, datetime
    days = (datetime.now(UTC) - p.created).days
    return days if days > limit else 0


def seen(top, bottom, vtop, vbottom, at_end=False, glimpsed=False, slack=2):
    """Is a card read now? Its top and bottom and the viewport's, in one coordinate;
    at_end: the view stands at the lane's end; glimpsed: the card was on screen before.
    "read" — it is on screen whole, or (taller than the screen) its end has come into
    view, or the lane's end is on screen with it, or the reader went on past it after
    seeing it; "glimpsed" — on screen, not all of it yet; None — not seen."""
    vh = vbottom - vtop
    on_screen = top < vbottom and bottom > vtop
    fully = top >= vtop - slack and bottom <= vbottom + slack
    tall_and_done = bottom - top > vh and vtop < bottom <= vbottom + slack
    tail = at_end and on_screen
    passed = glimpsed and bottom <= vtop + slack
    if fully or tall_and_done or tail or passed:
        return "read"
    return "glimpsed" if on_screen else None


def conversation_line(spec):
    """The line under a conversation card: ("N in the conversation, new: M · the last —
    who: «…»", id of the last post) — or None (a conversation of the one post)."""
    conv = spec.extra.get("conversation")
    p = spec.post
    if not conv or p is None or (len(conv["members"]) <= 1 and conv["last"].id == p.id):
        return None
    last = conv["last"]
    who = last.author.name or last.author.username
    return (_("conv_line", n=len(conv["members"]), new=conv["unread"]) + " · " +
            _("conv_last", who=who, text=snippet(last, 90)), last.id)
