"""A scrollable list of cards that builds only the ones on screen (docs/en/dev/memory.md,
step 5): lanes, threads, profiles.

The one rule: nothing moves under the reader. Every update keeps the first visible card
at the same place on screen, and pictures reserve their space before they load.

How: every spec of the list has a place — a top and a height (measured once its card was
built at this width, else the mean of those measured); the body is as tall as all of
them; only the cards within AHEAD screens of the screen exist as widgets, placed by hand.
Scrolling builds the ones coming near and lets go of the ones gone far, keeping what the
reader did to them (an opened warning, a translation shown). A card whose height changes
(its text laid out at last, a warning opened) moves the ones below it, and the reading
place is held by the card on top of the screen. A lane of a thousand posts is some 25
cards at a time — before, a window of 40 to 120 cards was built and kept, about a megabyte
each with its pictures (some 18 MB a lane), and a lane took 0.6 s to open.

The cards themselves are card.py's: the same widgets, the same look, links, selection,
menus and accessibility; only how many of them exist changed. `windowed = False` (a
thread, a profile: short, and read whole) builds them all.
"""

import logging
import time
from dataclasses import replace

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from ... import diag
from ...i18n import _
from ...model import Share
from ...model import real as real_entry
from ..common.lane import seen
from ..common.strip import Strip
from .card import _set_prop as _mark
from .card import row_class

log = logging.getLogger(__name__)

READING_S = 5  # s after a scroll by hand that a window without focus still counts as read


class _Watch(QObject):
    """Tells the view when a card (or the header, the footer) wants another height."""

    def __init__(self, view):
        super().__init__(view)
        self.view = view

    def eventFilter(self, obj, e):  # noqa: N802 — Qt's name
        if e.type() == QEvent.Type.LayoutRequest:
            self.view._remeasure(obj)
        return False


class FeedView(QScrollArea):
    seen = Signal(list)  # status ids the reader has actually seen
    stood = Signal(str)  # the card on top of the screen, read there (the scroll standing)

    MARGIN = 10   # around the column
    GAP = 8       # between cards
    AHEAD = 1.0   # cards exist this many screens above and below the screen
    KEPT = ("cw_open", "translation", "show_translation")  # what a card let go remembers
    FIRST_GUESS = 160  # a card's height before any was measured here

    # the places (common/strip.py, shared with GTK's lane): these names are the strip's
    _ys = property(lambda self: self.strip.ys,
                   lambda self, v: setattr(self.strip, "ys", v))
    _h = property(lambda self: self.strip.h, lambda self, v: setattr(self.strip, "h", v))
    _hidden = property(lambda self: self.strip.hidden,
                       lambda self, v: setattr(self.strip, "hidden", v))
    _width = property(lambda self: self.strip.width,
                      lambda self, v: setattr(self.strip, "width", v))

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.strip = Strip(self.GAP, self.MARGIN, self.FIRST_GUESS)
        self.setObjectName("feed")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # j / k and friends
        self.cursor_key = None
        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.body = QWidget()
        self.body.setObjectName("feedBody")
        self.setWidget(self.body)
        self._watch = _Watch(self)
        # the header and the footer: what the lane puts above and below the cards
        self._head = QWidget(self.body)
        self.header = QVBoxLayout(self._head)
        self._foot = QWidget(self.body)
        self.footer = QVBoxLayout(self._foot)
        for box, lay in ((self._head, self.header), (self._foot, self.footer)):
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(self.GAP)
            box.installEventFilter(self._watch)
        self.model = []      # every spec, top to bottom
        self._index = {}     # key -> its place in model
        self.rows = {}       # key -> card, for the cards that exist now
        self.order = []      # their keys, top to bottom
        self._ys = {}        # key -> the top of its place in the body
        self._h = {}         # key -> (width, height) measured
        self._kept = {}      # key -> what its card held when let go (KEPT)
        self._hidden = set()  # keys folded away ("-" in a thread)
        # cards that exist wherever the screen is: the one gone to (a link, find, j / k)
        # until the reader scrolls by hand — it is being looked at, marked, waited for
        self._held = set()
        self.found_key = None  # the match find shows (its card marked "found")
        self._width = 0      # the cards' width the heights were measured at
        self._total = 0
        self.windowed = False  # lanes: only the cards near the screen; else all
        self._relayout = QTimer(self, singleShot=True, interval=0)
        self._relayout.timeout.connect(self._settle_heights)
        self._dirty = set()  # cards that asked for another height
        self._pending = []   # keys near the screen not built yet (_build_more)
        self._more = QTimer(self, singleShot=True, interval=0)
        self._more.timeout.connect(self._build_more)
        self._seen_timer = QTimer(self, singleShot=True, interval=350)
        self._seen_timer.timeout.connect(self._emit_seen)
        # while the feed keeps moving the quiet moment never comes: look every so often
        # anyway, so posts that went by under the reader's eyes count too
        self._seen_tick = QTimer(self, singleShot=True, interval=300)
        self._seen_tick.timeout.connect(self._emit_seen)
        self._glimpsed = set()  # unread rows that have been on screen at some point
        self._swept = set()  # unread rows the screen went over whole while scrolling
        self._touched_at = 0.0  # when the reader last scrolled by hand (monotonic)
        sb = self.verticalScrollBar()
        sb.valueChanged.connect(self._scrolled)
        # a card's real height comes only when it is laid out, sometimes passes later:
        # "where to stand" is kept as a target and applied again while things settle,
        # until the reader touches the scroll or it has been quiet for a while
        self._target = None
        self._target_timer = QTimer(self, singleShot=True, interval=1500)
        self._target_timer.timeout.connect(self._drop_target)
        sb.rangeChanged.connect(lambda *_: self._apply_target())
        sb.actionTriggered.connect(lambda _a: self._touched())

    # ---- geometry ---------------------------------------------------------------
    def _column(self):
        """(x, width) of the cards: ui.max_width wide at most, or the whole width (0, or
        "full width" ticked in the ≡ menu), in the middle."""
        vw = self.viewport().width()
        maxw = self.ctx.cfg["ui"]["max_width"]
        cw = min(vw, maxw) if maxw else vw
        return (vw - cw) // 2 + self.MARGIN, max(50, cw - 2 * self.MARGIN)

    def apply_width(self):
        """Laid out anew for the window's width (or ui.max_width changed)."""
        self._lay_out()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._lay_out()
        self._seen_timer.start()

    def _guess(self):
        return self.strip.guess()

    def _height(self, key, guess):
        return self.strip.height(key, guess)

    def _measure(self, row, width):
        row.ensurePolished()  # the theme's fonts and margins first: they are the height
        lay = row.layout()
        if lay is not None:
            lay.activate()
        h = row.heightForWidth(width) if row.hasHeightForWidth() else -1
        if h <= 0:
            h = row.sizeHint().height()
        return max(1, h)

    def _lay_out(self, anchor=None, depth=0):
        """Every place again — the tops from the heights — and the cards where they go;
        the reading place held: `anchor` (key, offset from the screen's top), else the
        card on top of the screen now."""
        x, w = self._column()
        if anchor is None and (self._target is None or self._target[0] == "anchor"):
            anchor = self._reading_anchor()
        if w != self._width:
            self._width = w
            for key, row in self.rows.items():  # the ones there: measured at once
                self._h[key] = (w, self._measure(row, w))
        hh = self._head.sizeHint().height() if self.header.count() else 0
        fh = self._foot.sizeHint().height() if self.footer.count() else 0
        self._total = self.strip.lay_out(w, hh, fh)
        ys = self._ys
        if hh:
            self._head.setGeometry(x, self.strip.head[0], w, hh)
            self._head.show()
        else:
            self._head.hide()
        if fh:
            self._foot.setGeometry(x, self.strip.foot_top, w, fh)
            self._foot.show()
        else:
            self._foot.hide()
        guess = self._guess()
        self.body.setFixedSize(self.viewport().width(), self._total)
        for key, row in self.rows.items():
            row.setGeometry(x, ys[key], w, self._height(key, guess))
        if anchor is not None and anchor[0] in ys:
            self.verticalScrollBar().setValue(max(0, ys[anchor[0]] - anchor[1]))
        self._chrome = (self._head.sizeHint().height() if self.header.count() else 0,
                        self._foot.sizeHint().height() if self.footer.count() else 0)
        self._apply_target()
        self._realize(depth)

    _chrome = (0, 0)  # the header's and the footer's heights as laid out

    def _remeasure(self, obj):
        if obj in (self._head, self._foot):
            self._relayout.start()
            return
        key = getattr(getattr(obj, "spec", None), "key", None)
        if key is not None and self.rows.get(key) is obj:
            self._dirty.add(key)
            self._relayout.start()

    def _settle_heights(self):
        """Cards that asked for another height (laid out at last, a warning opened):
        measured, and if any changed — every place again, the reading place held."""
        changed = False
        for key in self._dirty:
            row = self.rows.get(key)
            if row is None:
                continue
            h = self._measure(row, self._width)
            if self._h.get(key) != (self._width, h):
                self._h[key] = (self._width, h)
                changed = True
        self._dirty = set()
        chrome = (self._head.sizeHint().height() if self.header.count() else 0,
                  self._foot.sizeHint().height() if self.footer.count() else 0)
        if changed or chrome != self._chrome:
            self._lay_out()

    # ---- which cards exist --------------------------------------------------------
    def _wanted(self):
        """The keys whose places are near the screen (all of them, not windowed)."""
        if not self.windowed:
            return [s.key for s in self.model if s.key not in self._hidden]
        sb = self.verticalScrollBar()
        return self.strip.wanted(sb.value(), self.viewport().height(), self.AHEAD,
                                 self._held | {self.cursor_key, self.found_key})

    def _first_place(self, y, guess):
        """The index in the model of the first place whose bottom is below y."""
        return self.strip.first_place(y, guess)

    _paused = False  # the cards let go for a restyle: none built till they're brought back

    SLICE_MS = 8  # the cards beyond the screen are built this long at a time

    def _realize(self, depth=0):
        """The cards near the screen built, the others let go. The ones on screen (and
        held) at once; the ones a screen above and below a few at a time, between the
        window's other work — built all at once they froze it for 300–430 ms when a
        lane opened or a jump went far (the logs of 29.10: card.__init__, _measure)."""
        if self._paused:
            return
        want = self._wanted()
        wanted = set(want)
        gone = [k for k in self.rows if k not in wanted]
        for key in gone:
            self._let_go(key)
        if gone:  # their memory back to the system once the scrolling settles
            diag.trim_soon("cards scrolled past")
        now = self._on_screen(want) if self.windowed else want
        x, w = self._column()
        guess = self._guess()
        new = False
        for key in now:
            if key not in self.rows:
                new = self._build(key, x, w, guess) or new
        self._pending = self._by_nearness([k for k in want if k not in self.rows])
        self.order = [k for k in want if k in self.rows]
        if new and depth < 4:
            # heights not as guessed: the places anew (and the cards near the screen again)
            self._lay_out(depth=depth + 1)
            return
        if new:
            # still not as guessed after four rounds (tall pictures, a lane opened far
            # from where the heights were known): the places anew at the next turn, not
            # at the lane's next refresh — till then the cards stood at the old places,
            # a gap above the last post for 15–30 s (29.10)
            QTimer.singleShot(0, self, self._lay_out)
        if self._pending:
            self._more.start()
        self._seen_timer.start()

    def _on_screen(self, want):
        """Of the keys wanted, those whose places the screen shows now, and the held."""
        sb = self.verticalScrollBar()
        return self.strip.on_screen(want, sb.value(), self.viewport().height(),
                                    self._held | {self.cursor_key, self.found_key})

    def _by_nearness(self, keys):
        """Nearest the screen first — below it first at the same distance (reading on)."""
        sb = self.verticalScrollBar()
        return self.strip.by_nearness(keys, sb.value(), self.viewport().height())

    def _build_more(self):
        """A few of the cards beyond the screen, SLICE_MS at most, then the window's
        turn again; on until they are all there."""
        if self._paused or not self._pending:
            return
        x, w = self._column()
        guess = self._guess()
        until = time.monotonic() + self.SLICE_MS / 1000
        new = False
        while self._pending and time.monotonic() < until:
            key = self._pending.pop(0)
            if key in self.rows or key not in self._index or key in self._hidden:
                continue
            new = self._build(key, x, w, guess) or new
        self.order = [s.key for s in self.model if s.key in self.rows]
        if new:
            self._lay_out()  # places anew, the reading place held; what's left requeued
            return
        if self._pending:
            self._more.start()
        else:
            self._seen_timer.start()

    def _build(self, key, x, w, guess):
        """One card made and put in its place. → whether its height is not as guessed."""
        spec = self.model[self._index[key]]
        try:
            row = row_class(spec)(spec, self.ctx)
        except Exception as e:  # noqa: BLE001 — one card broken: said in its place, the
            # rest built as ever (it stopped the loop: the cards after it on screen never
            # came — holes in the lane)
            row = self._broken(key, spec, e)
        kept = self._kept.pop(key, None)
        if kept:
            changed = False
            for a, v in kept.items():
                if getattr(row, a, None) != v:
                    setattr(row, a, v)
                    changed = True
            if changed and hasattr(row, "_build"):
                row._build()
        row.setParent(self.body)
        h = self._measure(row, w)
        new = self.strip.measured(key, w, h, guess)
        row.setGeometry(x, self._ys.get(key, 0), w, h)
        row.show()
        # the layout Qt asks of a card just shown, done now — before the watcher is on:
        # through it each card was measured twice more for nothing (9185 measures for
        # 2962 cards, 3 ms each); the height is cached then, the second look costs little
        QCoreApplication.sendPostedEvents(row, QEvent.Type.LayoutRequest)
        h2 = self._measure(row, w)
        if h2 != h:
            new = self.strip.measured(key, w, h2, guess) or new
            row.setGeometry(x, self._ys.get(key, 0), w, h2)
        row.installEventFilter(self._watch)
        self.rows[key] = row
        if hasattr(row, "card"):
            if key == self.cursor_key:
                _mark(row.card, "keyed", True)
            if key == self.found_key:
                _mark(row.card, "found", "true")
        return new

    _logged = set()  # keys whose broken card is in the log already (once each)

    def _broken(self, key, spec, err):
        """A card that couldn't be built: one line in its place saying so; its story in
        the log, once."""
        from PySide6.QtWidgets import QLabel
        if key not in FeedView._logged:
            FeedView._logged.add(key)
            log.exception("card %s couldn't be built", key)
        row = QLabel(_("card_broken", err=type(err).__name__))
        row.setObjectName("muted")
        row.setWordWrap(True)
        row.spec, row.status_id = spec, None
        row.update_spec = lambda s, row=row: setattr(row, "spec", s)
        row.set_unread = lambda _on: None
        return row

    def _let_go(self, key):
        row = self.rows.pop(key)
        if key in self.order:
            self.order.remove(key)
        kept = {a: getattr(row, a) for a in self.KEPT if hasattr(row, a)}
        if kept:
            self._kept[key] = kept
        row.removeEventFilter(self._watch)
        row.hide()
        row.deleteLater()

    # ---- the reading place ----------------------------------------------------------
    def _top(self, row):
        return self._ys.get(getattr(getattr(row, "spec", None), "key", None), 0)

    def _anchor(self):
        """(key, its top less the screen's top) of the card on top of the screen — by the
        places, built or not: the one there now is what the reader sees."""
        if not self.model:
            return None
        return self.strip.anchor(self.verticalScrollBar().value())

    def _reading_anchor(self):
        """The card that holds the reading place: the anchor being held, while one is,
        else the card on top of the screen."""
        t = self._target
        if t is not None and t[0] == "anchor" and t[1] in self._ys:
            return t[1], t[2]
        return self._anchor()

    def _set_target(self, target):
        self._target = target
        self._apply_target()
        QTimer.singleShot(0, self._apply_target)
        self._target_timer.start()

    def _drop_target(self):
        if self._target is not None:
            self._target = None
            self._seen_timer.start()

    def _apply_target(self):
        t = self._target
        if t is None:
            return
        sb = self.verticalScrollBar()
        if t[0] == "end":
            value = sb.maximum() if t[1] else 0
        else:
            if t[1] not in self._ys:
                self._target = None
                return
            top = self._ys[t[1]]
            if t[0] == "anchor":
                value = top - t[2]
            elif t[2] == "bottom":
                value = top + self._height(t[1], self._guess()) - self.viewport().height() + 10
            else:
                value = top - 6
        if sb.value() != max(0, value):
            sb.setValue(max(0, value))
        self._target_timer.start()  # still settling: keep the target a bit longer

    def wheelEvent(self, e):
        self._touched()
        super().wheelEvent(e)

    def _touched(self):
        """The reader moved the feed (wheel, keys, scroll bar): what comes on screen now
        is being read, even in a window without focus (KDE scrolls those too)."""
        self._touched_at = time.monotonic()
        self._held = set()  # the card gone to may go now, as any other
        self._drop_target()

    def mark_found(self, key):
        """The match find shows: its card marked (and kept built while it is)."""
        old, self.found_key = self.found_key, key
        for k in (old, key):
            row = self.rows.get(k)
            if row is not None and hasattr(row, "card"):
                _mark(row.card, "found", "true" if k == key else "false")
        if key is not None:
            self._bring(key)

    def _window_active(self):
        # any window of fedtail in front counts: in the split layout the roster is the
        # active one right after a lane is opened from it (and the desktop may refuse
        # to hand the focus over), while the posts are plainly being read
        if self.window().isActiveWindow():
            return True
        from PySide6.QtWidgets import QApplication
        front = QApplication.activeWindow()
        return front is not None and getattr(self.window(), "roster", None) is front

    def _scrolled(self, value):
        self._realize()
        # what the screen went over on its way here: a card the window passed whole is
        # read, though no tick caught it standing (a scroll by the wheel moves less than
        # a screen at a time; a jump — the scroll bar dragged, End — counts nothing)
        old = getattr(self, "_last_value", value)
        self._last_value = value
        vh = self.viewport().height()
        if old != value and abs(value - old) <= vh and \
                time.monotonic() - self._touched_at < 1.0:
            lo, hi = min(old, value), max(old, value) + vh
            for key in self.order[self._first_below(lo):]:
                row = self.rows.get(key)
                if row is None:
                    continue
                top = self._top(row)
                if top > hi:
                    break
                if row.spec.unread and top >= lo - 2 and top + row.height() <= hi + 2:
                    self._swept.add(key)
        self._seen_timer.start()
        if not self._seen_tick.isActive():
            self._seen_tick.start()

    def _first_below(self, y):
        """The index in self.order of the first card whose bottom is below y (binary
        search: the cards stand in order down the feed)."""
        lo, hi = 0, len(self.order)
        while lo < hi:
            mid = (lo + hi) // 2
            row = self.rows[self.order[mid]]
            if self._top(row) + row.height() <= y:
                lo = mid + 1
            else:
                hi = mid
        return lo

    # ---- keys -------------------------------------------------------------------------
    # j / k between posts; r f b m o act on the one under the cursor (ui.post_keys)
    POST_KEYS = {Qt.Key.Key_R: "reply", Qt.Key.Key_F: "fav", Qt.Key.Key_B: "boost",
                 Qt.Key.Key_M: "bookmark", Qt.Key.Key_O: "thread",
                 Qt.Key.Key_Return: "thread", Qt.Key.Key_Enter: "thread"}

    def keyPressEvent(self, e):
        from PySide6.QtWidgets import QApplication, QLineEdit, QTextEdit
        if isinstance(QApplication.focusWidget(), (QLineEdit, QTextEdit)):
            # a field in the header (Search): its Enter is its own, not "open the post"
            e.accept()
            return
        plain = e.modifiers() in (Qt.KeyboardModifier.NoModifier,
                                  Qt.KeyboardModifier.KeypadModifier)
        if plain and self.ctx.cfg["ui"].get("post_keys", True) and self._post_key(e.key()):
            e.accept()
            return
        self._touched()
        super().keyPressEvent(e)

    def _spec(self, key):
        i = self._index.get(key)
        return self.model[i] if i is not None else None

    def _posts(self):
        """The keys of posts (not dividers, not events), top to bottom, built or not."""
        return [s.key for s in self.model if s.entry is not None and
                s.key not in self._hidden and not s.extra.get("event")]

    def _post_key(self, key):
        posts = self._posts()
        if not posts:
            return False
        if key in (Qt.Key.Key_J, Qt.Key.Key_K):
            if self.cursor_key not in posts:
                # start from the post at the top of the screen
                top = self.verticalScrollBar().value()
                guess = self._guess()
                nxt = next((k for k in posts if self._ys.get(k, 0) + self._height(k, guess)
                            > top + 4), posts[0])
            else:
                i = posts.index(self.cursor_key) + (1 if key == Qt.Key.Key_J else -1)
                nxt = posts[max(0, min(len(posts) - 1, i))]
            self.put_cursor(nxt)
            return True
        if key in (Qt.Key.Key_BracketRight, Qt.Key.Key_BracketLeft):
            # a thread: the next / previous comment at the top of the tree (depth 1)
            tops = [k for k in posts if getattr(self._spec(k), "depth", 0) <= 1]
            if len(tops) < 2:
                return False
            at = posts.index(self.cursor_key) if self.cursor_key in posts else -1
            if key == Qt.Key.Key_BracketRight:
                nxt = next((k for k in tops if posts.index(k) > at), tops[-1])
            else:
                nxt = next((k for k in reversed(tops) if posts.index(k) < at), tops[0])
            self.put_cursor(nxt)
            return True
        if key == Qt.Key.Key_Minus and self.cursor_key in posts:
            return self._fold_branch(posts)
        action = self.POST_KEYS.get(key)
        if action is None or self.cursor_key not in posts:
            return False
        p = self._spec(self.cursor_key).post
        self.ctx.on_link(f"fedtail:{action}/{p.id}")
        return True

    def _fold_branch(self, posts):
        """"-" in a thread: the branch under the post at the cursor folded away, or shown
        again — from however deep a reply it is pressed, its whole top comment's branch."""
        def depth_of(k):
            return getattr(self._spec(k), "depth", 0)
        at = posts.index(self.cursor_key)
        depth = depth_of(self.cursor_key)
        if depth > 1:  # from a deep reply: its top comment's branch
            at = next((i for i in range(at, -1, -1) if depth_of(posts[i]) <= 1), at)
            depth = depth_of(posts[at])
            self.put_cursor(posts[at])
        below = []
        every = [s.key for s in self.model if s.entry is not None]
        for k in every[every.index(posts[at]) + 1:]:
            if depth_of(k) <= depth:
                break
            below.append(k)
        if not below:
            return False
        folded = getattr(self, "_folded", set())
        hide = posts[at] not in folded
        (folded.add if hide else folded.discard)(posts[at])
        self._folded = folded
        (self._hidden.update if hide else self._hidden.difference_update)(below)
        self._lay_out()
        return True

    def put_cursor(self, key):
        old = self.rows.get(self.cursor_key)
        if old is not None and hasattr(old, "card"):
            _mark(old.card, "keyed", False)
        self.cursor_key = key
        self.scroll_to(key, "top")
        row = self.rows.get(key)
        if row is not None and hasattr(row, "card"):
            _mark(row.card, "keyed", True)

    # ---- content ------------------------------------------------------------------
    def set_specs(self, specs, keep_position=True, around=None):
        """Show these specs. keep_position: the card on top of the screen stays where it
        is; around (a key): when it starts over, the screen goes near it (the caller
        places it exactly)."""
        anchor = self._reading_anchor() if keep_position else None
        self.model = list(specs)
        self._index = {s.key: i for i, s in enumerate(self.model)}
        self.strip.set_keys(s.key for s in self.model)
        for key in [k for k in self.rows if k not in self._index]:
            self._let_go(key)
        for key in [k for k in self._kept if k not in self._index]:
            del self._kept[key]
        for key, row in self.rows.items():
            spec = self.model[self._index[key]]
            if row.spec is not spec:
                row.update_spec(spec)
                self._dirty.add(key)
        if self._dirty:
            for key in list(self._dirty):  # their new heights, before the places
                row = self.rows.get(key)
                if row is not None:
                    self._h[key] = (self._width, self._measure(row, self._width))
            self._dirty = set()
        if not keep_position and around in self._index:
            self._lay_out(anchor=(around, 6))
        else:
            self._lay_out(anchor=anchor)
        if anchor and anchor[0] in self._ys and \
                (self._target is None or self._target[0] == "anchor"):
            self._set_target(("anchor", anchor[0], anchor[1]))
        self._seen_timer.start()

    def keys(self):
        """Every key shown or to be shown (built or not)."""
        return [s.key for s in self.model]

    def has(self, key):
        return key in self._index

    def _bring(self, key):
        """The card of key built: the screen goes to it. True if it is there now."""
        if key in self.rows:
            return True
        if key not in self._index:
            return False
        if key in self._hidden:
            return False
        self._held.add(key)
        self.verticalScrollBar().setValue(max(0, self._ys.get(key, 0) - 6))
        self._realize()
        return key in self.rows

    def clear(self):
        self.set_specs([], keep_position=False)

    def rebuild_rows(self):
        """Every card built again from what it holds, in its place, the reading place
        kept (another theme tried from the menu: new colours, shapes and words)."""
        anchor = self._reading_anchor()
        for key in list(self.rows):
            self._let_go(key)
        self._h = {}
        self._width = 0  # measured anew in the new look
        self._lay_out(anchor=anchor)
        if anchor and anchor[0] in self._ys:
            self._set_target(("anchor", anchor[0], anchor[1]))

    def let_go_rows(self):
        """Before the whole application is restyled (a theme tried): the cards go now,
        not after — Qt restyles every widget alive, and restyling them only to build them
        again in the new theme was most of the seconds a theme took. bring_back_rows()
        builds them again, the reading place kept. The caller flushes the deletions
        (sendPostedEvents DeferredDelete) before restyling."""
        if not self.rows:
            return None
        anchor = self._reading_anchor()
        for key in list(self.rows):
            self._let_go(key)
        self.order = []
        self._pending = []
        # the restyle resizes and re-lays out everything: no card is built meanwhile —
        # it would be built in the old theme, and kept
        self._paused = True
        return anchor

    def bring_back_rows(self, state):
        self._paused = False
        if state is None:
            self._lay_out()
            return
        self._h = {}
        self._width = 0
        self._lay_out(anchor=state)
        if state[0] in self._ys:
            self._set_target(("anchor", state[0], state[1]))

    def scroll_to(self, key, where="top"):
        if self._bring(key):
            self._set_target(("row", key, where))

    def scroll_to_end(self, end=True):
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum() if end else 0)
        self._realize()
        self._set_target(("end", end))

    def set_unread(self, status_ids, unread=False):
        ids = set(status_ids)
        for spec in self.model:  # cards not built too: they're built as they are now
            if spec.entry is not None and spec.entry.id in ids or spec.key in ids:
                spec.unread = unread  # (an event's row by its key, "event:<id>")
        for row in self.rows.values():
            if row.status_id in ids:
                row.set_unread(unread)

    def refresh_status(self, changed):
        """One post changed (a like, a boost, an edit): only its cards are redone.
        changed: the Post as it is now (None: look at every card)."""
        if changed is None:
            self.refresh_from_store()
            return
        changed = real_entry(changed)
        for i, spec in enumerate(self.model):
            if spec.entry is None or spec.post.id != changed.id:
                continue
            # the post itself changed: on its own card, and inside every boost of it
            # (a boost's stored copy still holds the post as it was)
            fresh = replace(spec.entry, post=changed) if isinstance(spec.entry, Share) \
                else changed
            if fresh == spec.entry:
                continue
            new = replace(spec, entry=fresh)
            self.model[i] = new
            row = self.rows.get(spec.key)
            if row is not None:
                row.update_spec(new)

    def refresh_from_store(self):
        for key, row in self.rows.items():
            if row.status_id is None:
                continue
            fresh = self.ctx.view.stored(row.status_id)
            if fresh is not None and fresh != row.spec.entry:
                new = replace(row.spec, entry=fresh)
                self.model[self._index[key]] = new
                row.update_spec(new)

    def remove_status(self, sid):
        keep = [s for s in self.model if s.entry is None or
                (s.entry.id != sid and s.post.id != sid)]
        if len(keep) != len(self.model):
            self.set_specs(keep)

    def unread_keys(self):
        """Unread, built or not, top to bottom."""
        return [s.key for s in self.model if s.unread]

    def unread_status_ids(self):
        return [s.entry.id for s in self.model if s.unread and s.entry is not None]

    # ---- what the reader saw --------------------------------------------------------
    def _check_holes(self):
        """The screen mostly empty with nothing waiting to be built: a hole in the
        lane (29.10, not seen in the bench) — said in the log with what stands where,
        once a minute at most, so a report shows it."""
        if not self.windowed or self._pending or not self.model or self._paused:
            return
        sb = self.verticalScrollBar()
        top, vh = sb.value(), self.viewport().height()
        if vh < 100 or self._total <= vh:
            return
        shown = 0
        for k in self.order:
            r = self.rows[k]
            y = self._ys.get(k, 0)
            shown += max(0, min(top + vh, y + r.height()) - max(top, y))
        if shown >= vh * 0.5:
            return
        now = time.monotonic()
        if now - getattr(self, "_hole_said", 0) >= 60:
            self._hole_said = now
            want = self._wanted()
            log.warning("hole in a lane: %d of %d px on screen covered at %d (max %d, "
                        "total %d, width %d, hidden %d, target %s); wanted %s; built %s; "
                        "places %s", shown, vh, top, sb.maximum(), self._total,
                        self._width, len(self._hidden), self._target, want[:12],
                        self.order[:12],
                        [(k, self._ys.get(k), self._h.get(k)) for k in want[:12]])
        # mended, not only said: every place again from the heights known now and the
        # cards near the screen built (a lane opened empty at its end, the read posts
        # above it, 29.10); once per hole — a lane that is short at its end stays so
        if getattr(self, "_mended_at", None) != (top, self._total):
            self._mended_at = (top, self._total)
            self._lay_out()

    def _check_places(self):
        """The cards on screen measured again once the screen stands still: a card whose
        height changed without telling the watcher (a picture in, a warning opened) kept
        the place it had — a gap, or one card over another — until the lane's next
        refresh, 15–30 s later (29.10). They are few, and their heights are cached: under
        a millisecond each."""
        if not self.rows or self._paused or not self._width:
            return
        sb = self.verticalScrollBar()
        top, vh = sb.value(), self.viewport().height()
        changed = False
        for k in self.order:
            y = self._ys.get(k, 0)
            if y > top + vh:
                break
            row = self.rows[k]
            if y + row.height() < top:
                continue
            if self.strip.measured(k, self._width, self._measure(row, self._width)):
                changed = True
        if changed:
            log.debug("lane: places mended on screen")
            self._lay_out()

    def _emit_seen(self):
        self._check_places()
        self._check_holes()
        if not self.isVisible() or self.window().isMinimized():
            return
        # a window in the background isn't being read — unless the reader scrolls it
        if not self._window_active() and time.monotonic() - self._touched_at > READING_S:
            from PySide6.QtWidgets import QApplication
            log.debug("seen: not counted, the window is in the background (%s active)",
                      type(QApplication.activeWindow()).__name__)
            return
        if self._target is not None and self._target[0] != "anchor":
            log.debug("seen: not counted, on the way to %s", self._target[:2])
            return  # still on its way somewhere: what's on screen is not what's read
        # (an anchor only holds the post on top in place while pictures come in: the
        # reader sees exactly that, so it doesn't stop anything)
        anchor = self._anchor()
        if anchor is not None:
            self.stood.emit(str(anchor[0]))  # where it opens next time (LaneModel.stood)
        sb = self.verticalScrollBar()
        vtop, vh = sb.value(), self.viewport().height()
        vbot = vtop + vh
        at_end = sb.value() >= sb.maximum()
        ids = []
        glimpsed = set()
        # the cards on screen, those glimpsed before and those the scroll went past
        near = set(self._glimpsed) | self._swept
        start = self._first_below(vtop)
        for key in self.order[start:]:
            if self._top(self.rows[key]) >= vbot:
                break
            near.add(key)
        swept, self._swept = self._swept, set()
        for key in [k for k in self.order if k in near]:
            row = self.rows.get(key)
            if row is None or not row.spec.unread:
                continue
            if key in swept:
                ids.append(row.status_id)
                continue
            top = self._top(row)
            got = seen(top, top + row.height(), vtop, vbot, at_end, key in self._glimpsed)
            if got == "read":
                ids.append(row.status_id)
            elif got == "glimpsed":
                glimpsed.add(key)
        before = self._glimpsed
        self._glimpsed = (self._glimpsed & {k for k in self.order
                                             if self.rows[k].spec.unread}) | glimpsed
        # on screen, not all of it yet: still to be read (the debug theme shows it)
        for key in before ^ self._glimpsed:
            row = self.rows.get(key)
            if row is not None and hasattr(row, "card"):
                _mark(row.card, "glimpsed", key in self._glimpsed)
        if ids:
            log.debug("seen on screen: %d", len(ids))
            self.seen.emit(ids)

    restyle = False  # another theme was tried while this was out of sight

    def showEvent(self, e):
        super().showEvent(e)
        if self.restyle:
            self.restyle = False
            self.rebuild_rows()
        else:
            self._lay_out()
        self._seen_timer.start()
