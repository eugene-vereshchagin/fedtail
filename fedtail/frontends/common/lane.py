"""What a lane shows, without a toolkit: the cards (CardSpec) built from the View's
entries — with what each answers, my replies, the short #ids — the "new below" divider
fixed where reading stood, the filters (everything / posts only / what was unread),
conversations instead of the feed, the media funnel, where reading starts, and the rule
for "seen on screen = read". qt/feed.py LaneWidget and gtk/lane.py LaneView draw this.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ...core.atoms import MEDIA_KINDS, VIDEO_EXT  # one list for the core and the cards
from ...i18n import _
from ...model import Share, real
from ...model.text import snippet

SEPARATOR = "__sep__"


@dataclass
class CardSpec:
    """What one card shows: a post of fedtail.model (a Post, or a Share around one),
    and where and how. Cards read nothing else of the server (docs/en/dev/protocols.md)."""
    key: str                   # unique within a view (item id or status id)
    entry: object = None       # Post | Share; None for the "new below" divider
    depth: int = 0
    number: int | None = None  # /N inside a thread
    parent: object = None      # the Post it answers, "missing", or None (unknown / no reply)
    unread: bool = False
    focus: bool = False
    in_thread: bool = False
    extra: dict = field(default_factory=dict)  # my_replies, short_id, separator, via…
    # where its thread opens: "post" / "first_unread" (core.open_at: the lane's own, else
    # threads.open_at) — the card's links say it (common/links.thread_url)
    open_at: str = "post"

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
    if "open_at" not in kw and hasattr(view, "open_at"):
        kw["open_at"] = view.open_at()  # threads.open_at; a lane puts its own (build)
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
    run, like every quick filter; kept between runs only with feed.remember_choices
    (LaneModel keeps it then)."""

    def __init__(self, changed=None):
        self.changed = changed  # called on each change: the core filters by it (a choice)
        self._wanted = set(MEDIA_KINDS)
        self._boosts = True

    # the windows change these in place; each change goes to the core at once — it counts
    # the lane's window by the funnel (Core._funnel), and finding in the lane asks it
    @property
    def wanted(self):
        return _Kinds(self._wanted, self._said)

    @wanted.setter
    def wanted(self, kinds):
        self._wanted = set(kinds)
        self._said()

    @property
    def boosts(self):
        return self._boosts

    @boosts.setter
    def boosts(self, on):
        self._boosts = bool(on)
        self._said()

    def _said(self):
        if self.changed is not None:
            self.changed()

    def active(self):
        return self.wanted != set(MEDIA_KINDS) or not self.boosts

    def keeps(self, entry):
        if not self.boosts and isinstance(entry, Share):
            return False
        return self.wanted == set(MEDIA_KINDS) or bool(media_kinds(entry) & self.wanted)

    def toggle(self, kind, on):
        (self.wanted.add if on else self.wanted.discard)(kind)

    def reset(self):
        self._wanted, self._boosts = set(MEDIA_KINDS), True
        self._said()


class _Kinds(set):
    """MediaFilter.wanted as a set, its add / discard told to the filter."""

    def __init__(self, kinds, said):
        super().__init__(kinds)
        self._target, self._said = kinds, said

    def add(self, kind):
        super().add(kind)
        self._target.add(kind)
        self._said()

    def discard(self, kind):
        super().discard(kind)
        self._target.discard(kind)
        self._said()


@dataclass
class Built:
    """A lane drawn: the cards top to bottom (the divider among them, a CardSpec with
    key SEPARATOR), the line for the header (unread-only / media funnel), how many are
    unread, and whether a browse lane came back empty from the server."""
    specs: list
    info: str = ""
    unread: int = 0
    empty: bool = False
    held: int = 0  # feed.on_new = "hold": new posts kept out until Refresh


class LaneModel:
    """The state of a lane's choices and how its cards are made. separator_text(n)
    is the theme's words for the divider."""

    def __init__(self, view, name, separator_text=None):
        self.view, self.name = view, name
        self.cfg = view.cfg
        self.newest_first = self.cfg["feed"]["order"] == "newest_first"
        lane = view.lane_by_name.get(name)
        self.lazy = bool(getattr(lane, "lazy", False))
        # what the lane's rule makes of it (Core.lane_rank: 0 private, 1 replies, 2
        # mentions, 3 followed threads, 4 the rest) — never its name: a lane of one's
        # own is offered the same as the set's
        rank = view.lane_rank(name) if hasattr(view, "lane_rank") else 4
        self.rank = rank
        self.sources = {getattr(lane, "source", None), *(getattr(lane, "feeds", ()) or ())}
        # "posts only" (the comments hidden): a lane of posts that isn't personal
        self.has_posts_only = rank == 4 and bool(getattr(lane, "source", None)) and \
            not getattr(lane, "events", False)
        self.chips = tuple(getattr(lane, "chips", ()) or ())  # a free lane's quick filters
        self.separator_text = separator_text or (lambda n: _("new_below"))
        self.separator = None    # (key of the first unread when the lane opened, count)
        self.kept = None         # "unread only": the item keys shown while it's open
        self.shown = None        # on_new = "hold": the item keys let in so far
        self.refreshes = getattr(view, "hand_refreshes", 0)
        self.conv_members = {}   # conversation top id -> member ids
        self.event_sorts = {}    # an event row's key -> its newest sort (what's seen)
        # view = "threads" (a lane of rules): one card a thread, as on Point — the threads
        # with new comments; one read while the lane is open stays till it is left
        self.threads_view = getattr(lane, "view", "") == "threads"
        self.threads_kept = set()
        self.media = MediaFilter()
        kept = view.choice(f"media.{name}") if hasattr(view, "choice") else None
        if isinstance(kept, dict):  # feed.remember_choices: as it was left
            self.media.wanted = {k for k in kept.get("wanted") or () if k in MEDIA_KINDS} \
                or set(MEDIA_KINDS)
            self.media.boosts = bool(kept.get("boosts", True))
        self._media_kept = self._media_state()
        self.media.changed = self._keep_media
        opts = ["all"]
        if self.chips:  # "main" (what isn't hidden) before "all"
            opts = [k for k, _w in self.chips if k == "main"] + ["all"]
        if self.has_posts_only:
            opts.append("posts")
        opts += [k for k, _w in self.chips if k != "main"]  # then each switch
        if not self.lazy:
            opts.append("unread")
        self.filters = opts      # what the filter control offers ("all" alone: none)

    # ---- the choices -------------------------------------------------------------------
    def filter_words(self, which):
        """(words, tip) for a filter: the built-in ones from i18n, a free lane's switch as
        its rule names it."""
        builtin = {"all": ("show_all", "show_all_tip"), "posts": ("posts_only", "posts_only_tip"),
                   "unread": ("unread_only", "unread_only_tip"),
                   "main": ("chips_main", "chips_main_tip")}
        if which in builtin:
            return _(builtin[which][0]), _(builtin[which][1])
        words = dict(self.chips).get(which) or which
        if words.startswith("@"):  # a built-in lane's: an i18n key
            return _(words[1:]), _(words[1:] + "_tip")
        return words, _("chip_tip", words=words)

    def current_filter(self):
        if self.chips:
            which = self.view.lane_filter(self.name)
            if which != "all":  # a chip, or "main"
                return which
        if self.has_posts_only and self.view.posts_only(self.name):
            return "posts"
        if "unread" in self.filters and self.view.choice(f"unread_only.{self.name}"):
            return "unread"
        return "all"

    def unread_only(self):
        return len(self.filters) > 1 and self.current_filter() == "unread"

    def set_filter(self, which):
        """"all", "posts" (no replies) or "unread"; a free lane's "main" or "chip:<n>" too;
        the caller places the lane anew."""
        if self.chips:  # a chip or "main"; anything else is no chip
            self.view.set_lane_filter(self.name, which if which == "main"
                                      or which.startswith("chip:") else "all")
        if self.has_posts_only and self.view.posts_only(self.name) != (which == "posts"):
            self.view.set_posts_only(self.name, which == "posts")
        self.view.set_choice(f"unread_only.{self.name}", which == "unread")
        self.kept = None
        self.separator = None

    def read_on_open(self):
        """read.mark_read = "on_open": the lane read whole the moment it comes on screen —
        not a browsed one (nothing is unread there)."""
        return self.cfg["read"]["mark_read"] == "on_open" and not self.lazy

    def conversations_offered(self):
        return self.rank in (1, 2, 3) and not self.threads_view  # replies, mentions, threads

    def conversations(self):
        return self.threads_view or self.conversations_offered() and \
            bool(self.view.choice(f"conversations.{self.name}"))

    def set_conversations(self, on):
        self.view.set_choice(f"conversations.{self.name}", bool(on))
        self.separator = None

    def left(self):
        """The lane went out of sight: "unread only" shows anew what's unread next time
        (and a threads lane, the threads with new comments only)."""
        self.threads_kept = set()
        if self.unread_only():
            self.kept = None
            return True
        return False

    # ---- the cards ----------------------------------------------------------------------
    def _media_state(self):
        return {"wanted": sorted(self.media.wanted), "boosts": self.media.boosts}

    def _keep_media(self):
        """The funnel changed (any window changes it in place): kept as a choice."""
        now = self._media_state()
        if now != self._media_kept and hasattr(self.view, "set_choice"):
            self.view.set_choice(f"media.{self.name}", now)
            self._media_kept = now

    def _hold(self, entries, positioned):
        """feed.on_new = "hold" (Elk's way): what came after the lane was drawn waits
        out of it — the header says "N new" — till Refresh lets it in. Older posts
        (paging down, a thread's parents) come in at once. → (entries, how many wait)."""
        if self.cfg["feed"].get("on_new") != "hold":
            self.shown = None
            return entries, 0
        hand = getattr(self.view, "hand_refreshes", 0)
        keys = [k for k, _e in entries]
        if not positioned or self.shown is None or hand != self.refreshes:
            self.refreshes = hand
            self.shown = set(keys)
            return entries, 0
        last = max((i for i, k in enumerate(keys) if k in self.shown), default=-1)
        self.shown.update(keys[:last + 1])  # older ones: in
        held = [k for k in keys[last + 1:] if k not in self.shown]
        if not held:
            return entries, 0
        wait = set(held)
        return [x for x in entries if x[0] not in wait], len(held)

    def build(self, positioned):
        """The cards as they are now. positioned: the reader has been placed in the lane
        already (the divider stays where it was then)."""
        view = self.view
        self._keep_media()
        entries = view.entries(self.name)  # [(item id, Post | Share)], oldest first
        unread = set() if self.lazy else view.unread(entries)
        info = ""
        if self.unread_only():
            fresh = {item for item, e in entries if e.id in unread}
            self.kept = fresh if self.kept is None else self.kept | fresh
            entries = [e for e in entries if e[0] in self.kept]
            info = _("unread_only_info", n=len(fresh)) if self.kept else _("unread_only_none")
        entries, held = self._hold(entries, positioned)
        if self.media.active():
            entries = [x for x in entries if self.media.keeps(x[1])]
            info = _("media_filter_info", n=len(entries))
        if held:
            info = _("held_info", n=held) + (" · " + info if info else "")
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
        gone = getattr(view, "deleted_ids", None)
        gone = gone() if callable(gone) else set()
        if gone:  # its server no longer has it: kept, marked (feeds.md §2.4)
            for s in specs:
                if s.entry is not None and (s.entry.id in gone or real(s.entry).id in gone):
                    s.extra["deleted"] = True
        news = getattr(view, "thread_news", None)
        news = news() if news else {}
        if news:  # a followed thread with new replies: said under its post
            for s in specs:
                n = news.get(real(s.entry).id) if s.entry is not None else None
                if n:
                    s.extra["thread_news"] = n
        tagged = getattr(view, "came_by_tag", None)
        if tagged is not None and view.cfg["feed"].get("why_home") and \
                "home" in self.sources:  # "via #tag": why a stranger's post came by Home
            for s in specs:
                if s.entry is not None and not isinstance(s.entry, Share):
                    tag = tagged(s.entry)
                    if tag:
                        s.extra["via_tag"] = tag
        specs = self._with_events(specs)
        at = view.open_at(self.name) if hasattr(view, "open_at") else "post"
        for s in specs:
            s.open_at = at
        if self.rank in (1, 2):  # replies and mentions: did I answer them elsewhere?
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
        return Built(specs, info, sum(1 for s in specs if s.unread), empty, held)

    def events_only(self):
        """A lane of events only (Activity, Requests — any lane whose rule takes
        nothing but events): its rows are events, no posts."""
        lane = self.view.lane_by_name.get(self.name)
        return bool(getattr(lane, "events", False) and not getattr(lane, "source", None))

    def _with_events(self, specs):
        """A lane of rules that takes events (likes, follows, follow requests… — feeds.md
        §2.3): their rows among the posts, by time — each run of one kind about one post
        as one row (CardSpec "event:<id>", extra["event"]: [Activity], extra["row"]: the
        row's words, common/activity.Row). Unread: newer than what's seen (one mark for
        every lane: Core.mark_activity_seen). Not while a kind of media is shown (an
        event is none); with "unread only" — the unseen ones. Among posts, none come
        before the oldest post shown (the lane's window); a lane of events only shows
        them all; those without a time (a follow request waiting) stand as the newest."""
        if self.media.active():
            return specs
        events = getattr(self.view, "lane_events", None)
        events = events(self.name) if events else []
        if not events:
            return specs
        from .activity import rows as act_rows
        seen_at = getattr(self.view, "activity_seen", None)
        seen_at = seen_at() if seen_at else ""
        rows = act_rows(events, seen_at, lambda _d: "", oldest_first=False)  # when: drawn
        only = self.events_only()

        def when_post(s):
            e = s.entry
            return (e.created if isinstance(e, Share) and e.created else real(e).created) \
                if e is not None else None
        made = []
        for r in rows:
            times = [a.created for a in r.entries if a.created]
            key = "event:" + r.entries[0].id
            self.event_sorts[key] = r.newest_sort
            made.append((max(times) if times else None,
                         CardSpec(key=key, unread=r.unread,
                                  extra={"event": r.entries, "row": r})))
        if self.unread_only():
            made = [m for m in made if m[1].unread or m[1].key in (self.kept or ())]
            self.kept = (self.kept or set()) | {m[1].key for m in made}
        # oldest first; without a time (a follow request waiting) — now: the newest
        undated = [spec for when, spec in made if when is None]
        made = sorted(((w, sp) for w, sp in made if w is not None), key=lambda r: r[0])
        timed = [when_post(s) for s in specs]
        oldest = min((t for t in timed if t is not None), default=None)
        out, i = [], 0
        for when, spec in made:
            if not only and oldest is not None and when < oldest:
                continue
            while i < len(specs) and timed[i] is not None and timed[i] <= when:
                out.append(specs[i])
                i += 1
            out.append(spec)
        return out + specs[i:] + undated

    def _conversation_specs(self, entries, unread, parents, answers, short):
        """One card per conversation: its top post, with a line about the rest."""
        view = self.view
        groups = view.conversations(entries, unread)
        if self.threads_view:  # the threads with new comments (and those read just now)
            groups = [g for g in groups if g["unread"] or g["key"] in self.threads_kept]
            self.threads_kept |= {g["key"] for g in groups}
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
        a conversation card seen = its members seen). [] when reading is by hand. An
        event row seen ("event:<id>") marks the events seen up to it, here and now."""
        newest = max((self.event_sorts.get(i, "") for i in ids if str(i).startswith(
            "event:")), default="")
        if newest:
            seen = getattr(self.view, "mark_activity_seen", None)
            if seen is not None:
                seen(newest)
        ids = [i for i in ids if not str(i).startswith("event:")]
        if self.cfg["read"]["mark_read"] != "on_scroll":
            return []
        return [m for i in ids for m in self.conv_members.get(i, [i])]


def marks_seen(cfg):
    """read.mark_read: are posts seen on screen marked read (all but "manual")?"""
    return cfg["read"]["mark_read"] != "manual"


def seen_read(cfg, ids):
    """The ids seen on screen to mark read: all of them, or none when reading is by
    hand (read.mark_read = "manual") — every interface decides it here."""
    return list(ids) if marks_seen(cfg) else []


def thread_read_on_open(cfg, unread):
    """A thread opened: its unread posts read at once, unless reading is by hand."""
    return sorted(unread) if marks_seen(cfg) else []


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
