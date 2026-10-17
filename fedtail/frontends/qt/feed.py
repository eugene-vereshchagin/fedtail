"""Scrollable lists of posts: lanes, threads, accounts; plus follow requests.

The one rule here: nothing moves under the reader. Every update keeps the
first visible post at the same place on screen, and images reserve their
space before they load.
"""

import logging
import time

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ... import diag
from ...core.model import real, snippet
from ...i18n import _
from .card import CardSpec, PostRow, SeparatorRow
from .card import _set_prop as _mark
from .text import display_name, esc

log = logging.getLogger(__name__)

POSTS_ONLY_LANES = ("people", "bots", "mine", "local")
# where Feed | Conversations means something: lanes made of replies, many of them to the
# same few threads. In Home almost every post is a conversation of its own — the two
# views would look the same there, so the switch isn't offered.
CONVERSATION_LANES = ("comments", "mentions", "subs")


class FeedView(QScrollArea):
    seen = Signal(list)  # status ids the reader has actually seen

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.setObjectName("feed")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # j / k and friends
        self.cursor_key = None
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("feedBody")
        outer = QHBoxLayout(body)
        outer.setContentsMargins(0, 0, 0, 0)
        self.column = QWidget()
        outer.addWidget(self.column, 0, Qt.AlignmentFlag.AlignHCenter)
        self.col = QVBoxLayout(self.column)
        self.col.setContentsMargins(10, 10, 10, 10)
        self.col.setSpacing(8)
        self.header = QVBoxLayout()
        self.footer = QVBoxLayout()
        self.col.addLayout(self.header)
        self.col.addLayout(self.footer)
        self.col.addStretch(1)
        self.setWidget(body)
        self.rows = {}    # key -> card, for the cards built (see "the window" below)
        self.order = []   # their keys, top to bottom
        # A lane can hold hundreds of posts; building a card for each one at once froze
        # the window for seconds. A windowed view (lanes) keeps them all as specs and
        # builds cards only around the place reading is at, more as the reader scrolls
        # near an edge. No guessed heights: cards added above the screen are held in
        # place by the same anchor that holds it when new posts come in.
        self.model = []       # every spec, top to bottom
        self.windowed = False  # set by lanes; threads and profiles build everything
        self.build_at_once = 40      # cards built at first (feed.build_at_once)
        self._grow_timer = QTimer(self, singleShot=True, interval=30)
        self._grow_timer.timeout.connect(self._grow)
        self._seen_timer = QTimer(self, singleShot=True, interval=350)
        self._seen_timer.timeout.connect(self._emit_seen)
        # while the feed keeps moving the quiet moment never comes: look every so often
        # anyway, so posts that went by under the reader's eyes count too
        self._seen_tick = QTimer(self, singleShot=True, interval=300)
        self._seen_tick.timeout.connect(self._emit_seen)
        self._glimpsed = set()  # unread rows that have been on screen at some point
        self._touched_at = 0.0  # when the reader last scrolled by hand (monotonic)
        sb = self.verticalScrollBar()
        sb.valueChanged.connect(self._scrolled)
        # Word-wrapped posts get their real height only after Qt lays them out,
        # sometimes several passes later. So "where to stand" is kept as a target
        # and re-applied every time the scroll range changes, until the reader
        # touches the scroll or things have been quiet for a while.
        self._target = None
        self._target_timer = QTimer(self, singleShot=True, interval=1500)
        self._target_timer.timeout.connect(self._drop_target)
        sb.rangeChanged.connect(lambda *_: self._apply_target())
        sb.actionTriggered.connect(lambda _a: self._touched())

    # ---- geometry ---------------------------------------------------------------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        maxw = self.ctx.cfg["ui"]["max_width"]
        w = self.viewport().width()
        self.column.setFixedWidth(min(w, maxw) if maxw else w)
        self._seen_timer.start()

    def _settle(self):
        self.col.activate()
        self.widget().layout().activate()

    def _top(self, row):
        return row.mapTo(self.widget(), QPoint(0, 0)).y()

    def _anchor(self):
        v = self.verticalScrollBar().value()
        for key in self.order:
            row = self.rows[key]
            top = self._top(row)
            if top + row.height() > v:
                return key, top - v
        return None

    # ---- scroll targets -------------------------------------------------------------
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
        self._settle()
        sb = self.verticalScrollBar()
        kind = t[0]
        if kind == "end":
            value = sb.maximum() if t[1] else 0
        else:
            row = self.rows.get(t[1])
            if row is None:
                self._target = None
                return
            top = self._top(row)
            if kind == "anchor":
                value = top - t[2]
            elif t[2] == "bottom":
                value = top + row.height() - self.viewport().height() + 10
            else:
                value = top - 6
        sb.setValue(max(0, value))
        self._target_timer.start()  # still settling: keep the target a bit longer

    def wheelEvent(self, e):
        self._touched()
        super().wheelEvent(e)

    def _touched(self):
        """The reader moved the feed (wheel, keys, scroll bar): what comes on screen now
        is being read, even in a window without focus (KDE scrolls those too)."""
        self._touched_at = time.monotonic()
        self._drop_target()

    def _window_active(self):
        return self.window().isActiveWindow()

    def _scrolled(self, _value):
        self._seen_timer.start()
        if not self._seen_tick.isActive():
            self._seen_tick.start()
        self._grow_soon()

    # j / k between posts; r f b m o act on the one under the cursor (ui.post_keys)
    POST_KEYS = {Qt.Key.Key_R: "reply", Qt.Key.Key_F: "fav", Qt.Key.Key_B: "boost",
                 Qt.Key.Key_M: "bookmark", Qt.Key.Key_O: "thread",
                 Qt.Key.Key_Return: "thread", Qt.Key.Key_Enter: "thread"}

    def keyPressEvent(self, e):
        plain = e.modifiers() in (Qt.KeyboardModifier.NoModifier,
                                  Qt.KeyboardModifier.KeypadModifier)
        if plain and self.ctx.cfg["ui"].get("post_keys", True) and self._post_key(e.key()):
            e.accept()
            return
        self._touched()
        super().keyPressEvent(e)

    def _posts(self):
        return [k for k in self.order if getattr(self.rows[k], "spec", None) is not None
                and self.rows[k].spec.status]

    def _post_key(self, key):
        posts = self._posts()
        if not posts:
            return False
        if key in (Qt.Key.Key_J, Qt.Key.Key_K):
            if self.cursor_key not in posts:
                # start from the post at the top of the screen
                top = self.verticalScrollBar().value()
                at = next((k for k in posts if self._top(self.rows[k]) + self.rows[k].height()
                           > top + 4), posts[0])
                nxt = at
            else:
                i = posts.index(self.cursor_key) + (1 if key == Qt.Key.Key_J else -1)
                nxt = posts[max(0, min(len(posts) - 1, i))]
            self.put_cursor(nxt)
            return True
        action = self.POST_KEYS.get(key)
        if action is None or self.cursor_key not in posts:
            return False
        st = real(self.rows[self.cursor_key].spec.status)
        self.ctx.on_link(f"fedtail:{action}/{st['id']}")
        return True

    def put_cursor(self, key):
        old = self.rows.get(self.cursor_key)
        if old is not None and hasattr(old, "card"):
            _mark(old.card, "keyed", False)
        self.cursor_key = key
        row = self.rows.get(key)
        if row is not None and hasattr(row, "card"):
            _mark(row.card, "keyed", True)
            self.scroll_to(key, "top")

    # ---- content ------------------------------------------------------------------
    def set_specs(self, specs, keep_position=True, around=None):
        """Show these specs. A windowed view builds cards only for some of them: around
        `around` (a key) when it starts over, else the stretch already built, grown to
        the ends it touched (new posts at the end the reader stands at come in)."""
        old_keys = [s.key for s in self.model]
        self.model = list(specs)
        if self._all_at_once():
            window = self.model
        else:
            window = self._window(keep_position, around, old_keys)
        # no painting while cards come and go: one paint at the end
        self.setUpdatesEnabled(False)
        try:
            self._set_specs(window, keep_position)
        finally:
            self.setUpdatesEnabled(True)
        self._grow_soon()

    def _all_at_once(self):
        n = self.build_at_once
        return not self.windowed or not n or len(self.model) <= 2 * n

    def _window(self, keep_position, around, old_keys):
        keys = [s.key for s in self.model]
        index = {k: i for i, k in enumerate(keys)}
        have = [index[k] for k in self.order if k in index]
        if keep_position and have:
            lo, hi = min(have), max(have) + 1
            if self.order and old_keys and self.order[0] == old_keys[0]:
                lo = 0  # it reached the top: what came in above comes in too
            if self.order and old_keys and self.order[-1] == old_keys[-1]:
                hi = len(keys)  # …and the bottom
            return self.model[lo:hi]
        c = index.get(around, len(keys) - 1)
        before = max(4, self.build_at_once // 4)
        lo = max(0, c - before)
        hi = min(len(keys), lo + self.build_at_once)
        lo = max(0, hi - self.build_at_once)
        return self.model[lo:hi]

    def keys(self):
        """Every key shown or to be shown (built or not)."""
        return [s.key for s in self.model]

    def has(self, key):
        return any(s.key == key for s in self.model)

    def _grow_soon(self):
        if not self._all_at_once():
            self._grow_timer.start()

    def _grow(self):
        """The reader is near the top or the bottom of the cards built: build some more
        there — a few at a time, so the window stays responsive meanwhile."""
        if self._all_at_once() or not self.order or not self.isVisible():
            return
        keys = self.keys()
        index = {k: i for i, k in enumerate(keys)}
        if self.order[0] not in index or self.order[-1] not in index:
            return
        lo, hi = index[self.order[0]], index[self.order[-1]] + 1
        sb = self.verticalScrollBar()
        reach = self.viewport().height() * 2
        step = max(8, self.build_at_once // 2)
        new_lo, new_hi = lo, hi
        if lo > 0 and sb.value() < reach:
            new_lo = max(0, lo - step)
        elif hi < len(keys) and sb.value() > sb.maximum() - reach:
            new_hi = min(len(keys), hi + step)
        if (new_lo, new_hi) == (lo, hi):
            return
        t = time.monotonic()
        self.setUpdatesEnabled(False)
        try:
            self._set_specs(self.model[new_lo:new_hi], keep_position=True)
        finally:
            self.setUpdatesEnabled(True)
        log.debug("feed: %d more cards built (%d of %d), %.0f ms",
                  (lo - new_lo) + (new_hi - hi), new_hi - new_lo, len(keys),
                  (time.monotonic() - t) * 1000)
        self._grow_timer.start()  # still near an edge? the next few

    def _bring(self, key):
        """Make sure the card of key is built: if it isn't, build the window around it
        instead of the one there was. True if it is there now."""
        if key in self.rows:
            return True
        if not self.has(key):
            return False
        self.setUpdatesEnabled(False)
        try:
            self._set_specs(self._window(False, key, []), keep_position=False)
        finally:
            self.setUpdatesEnabled(True)
        self._grow_soon()
        return key in self.rows

    def _set_specs(self, specs, keep_position=True):
        anchor = self._anchor() if keep_position else None
        keys = [s.key for s in specs]
        wanted = set(keys)
        for key in [k for k in self.order if k not in wanted]:
            row = self.rows.pop(key)
            self.col.removeWidget(row)
            row.deleteLater()
        old = [k for k in self.order if k in wanted]
        kept_in_new_order = [k for k in keys if k in self.rows]
        if old != kept_in_new_order:  # order changed: lay everything out again
            for k in old:
                self.col.removeWidget(self.rows[k])
        base = 1  # index 0 is the header layout
        relayout = old != kept_in_new_order
        for i, spec in enumerate(specs):
            row = self.rows.get(spec.key)
            if row is None:
                row = (SeparatorRow if spec.extra.get("separator") else PostRow)(spec, self.ctx)
                self.rows[spec.key] = row
                self.col.insertWidget(base + i, row)
            else:
                row.update_spec(spec)
                if relayout:
                    self.col.insertWidget(base + i, row)
        self.order = keys
        if anchor and anchor[0] in self.rows:
            # keep the post that was on top exactly where it was
            if self._target is None or self._target[0] == "anchor":
                self._set_target(("anchor", anchor[0], anchor[1]))
            else:
                self._apply_target()
        self._seen_timer.start()

    def clear(self):
        self.set_specs([], keep_position=False)

    def scroll_to(self, key, where="top"):
        if self._bring(key):
            self._set_target(("row", key, where))

    def scroll_to_end(self, end=True):
        if self.model and not self._all_at_once():
            self._bring(self.model[-1 if end else 0].key)
        self._set_target(("end", end))

    def set_unread(self, status_ids, unread=False):
        ids = set(status_ids)
        for spec in self.model:  # cards not built yet too: they're built as they are now
            if spec.status and spec.status.get("id") in ids:
                spec.unread = unread
        for row in self.rows.values():
            if row.status_id in ids:
                row.set_unread(unread)

    def refresh_status(self, store, st):
        """One post changed (a like, a boost, an edit): only its cards are redone. Going
        through every card asks the database for each, and with a few hundred cards
        open that froze the window for seconds after every click."""
        if not st or not st.get("id"):
            self.refresh_from_store(store)
            return
        ids = {st["id"], real(st)["id"]}
        for i, spec in enumerate(self.model):
            if not spec.status or (spec.status.get("id") not in ids and
                                   real(spec.status).get("id") not in ids):
                continue
            fresh = store.get_status(spec.status["id"])
            if not fresh or fresh == spec.status:
                continue
            new = CardSpec(**{**spec.__dict__, "status": fresh})
            self.model[i] = new
            row = self.rows.get(spec.key)
            if row is not None:
                row.update_spec(new)

    def refresh_from_store(self, store):
        for row in self.rows.values():
            if row.status_id is None:
                continue
            fresh = store.get_status(row.status_id)
            if fresh and fresh != row.spec.status:
                row.update_spec(CardSpec(**{**row.spec.__dict__, "status": fresh}))

    def remove_status(self, sid):
        keep = [s for s in self.model if not s.status or
                (s.status.get("id") != sid and real(s.status).get("id") != sid)]
        if len(keep) != len(self.model):
            self.set_specs(keep)

    def unread_keys(self):
        """Unread, built or not, top to bottom."""
        return [s.key for s in self.model if s.unread]

    def unread_status_ids(self):
        return [s.status["id"] for s in self.model if s.unread and s.status]

    # ---- what the reader saw --------------------------------------------------------
    def _emit_seen(self):
        if not self.isVisible() or self.window().isMinimized():
            return
        # a window in the background isn't being read — unless the reader scrolls it
        if not self._window_active() and time.monotonic() - self._touched_at > READING_S:
            return
        if self._target is not None and self._target[0] != "anchor":
            return  # still on its way somewhere: what's on screen is not what's read
        # (an anchor only holds the post on top in place while pictures come in: the
        # reader sees exactly that, so it doesn't stop anything)
        sb = self.verticalScrollBar()
        vtop, vh = sb.value(), self.viewport().height()
        vbot = vtop + vh
        at_end = sb.value() >= sb.maximum()
        ids = []
        glimpsed = set()
        for key in self.order:
            row = self.rows[key]
            if not row.spec.unread:
                continue
            top = self._top(row)
            bottom = top + row.height()
            on_screen = top < vbot and bottom > vtop
            fully = top >= vtop - 2 and bottom <= vbot + 2
            tall_and_done = row.height() > vh and bottom <= vbot + 2 and bottom > vtop
            tail = at_end and on_screen
            # it was on screen and the reader went on past it: read, though it was never
            # all on screen at a moment the feed stood still
            passed = bottom <= vtop + 2 and key in self._glimpsed
            if fully or tall_and_done or tail or passed:
                ids.append(row.status_id)
            elif on_screen:
                glimpsed.add(key)
        self._glimpsed = (self._glimpsed & {k for k in self.order
                                             if self.rows[k].spec.unread}) | glimpsed
        if ids:
            log.debug("seen on screen: %d", len(ids))
            self.seen.emit(ids)

    def showEvent(self, e):
        super().showEvent(e)
        self._seen_timer.start()
        self._grow_soon()


READING_S = 5  # s after a scroll by hand that a window without focus still counts as read

ICONS = True  # set from the theme by the window: dark custom themes want words only


def _button(text, slot, name="tool", icon=None, tip=None):
    b = QPushButton(text)
    b.setObjectName(name)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if icon:
        ic = QIcon.fromTheme(icon) if ICONS else QIcon()
        if not ic.isNull():
            b.setIcon(ic)
        elif not text:
            b.setText(tip or "")
    if tip:
        b.setToolTip(tip)
    b.setAccessibleName(text or tip or "")
    b.clicked.connect(slot)
    return b


class _ElidedLabel(QLabel):
    """One line that gives way: when there's no room it ends in "…" (the whole text
    in the tooltip) instead of pushing the window wider."""

    def __init__(self, text=""):
        super().__init__()
        self._full = ""
        self._tip = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(40)
        self.setText(text)

    def setText(self, text):  # noqa: N802 — Qt's name
        self._full = text or ""
        self._elide()

    def setToolTip(self, tip):  # noqa: N802 — Qt's name
        """An explanation of its own, shown under the whole text when that's cut."""
        self._tip = tip or ""
        self._show_tip()

    def _show_tip(self):
        cut = QLabel.text(self) != self._full
        parts = [self._full] if cut else []
        if self._tip:
            parts.append(self._tip)
        QLabel.setToolTip(self, "\n\n".join(parts))

    def text(self):
        return self._full

    def _elide(self):
        shown = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight,
                                              max(self.width(), 40))
        QLabel.setText(self, shown)
        self._show_tip()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def sizeHint(self):  # noqa: N802
        hint = super().sizeHint()
        hint.setWidth(self.fontMetrics().horizontalAdvance(self._full) + 4)
        return hint


class _Header(QWidget):
    """Title line above a lane, a thread or an account."""

    def __init__(self, theme, title=""):
        super().__init__()
        self.setObjectName("laneHeader")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.theme = theme
        self.h = QHBoxLayout(self)
        self.h.setContentsMargins(28, 12, 20, 12)
        self.h.setSpacing(12)
        # a long title or a long note must never make the window wider: they give way
        self.title = _ElidedLabel(title)
        self.title.setObjectName("laneTitle")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.h.addWidget(self.title, 3)
        self.info = _ElidedLabel()
        self.info.setObjectName("laneInfo")
        self.info.setTextFormat(Qt.TextFormat.PlainText)
        self.h.addWidget(self.info, 2)

    def add(self, w):
        self.h.addWidget(w)
        return w


class LaneWidget(QWidget):
    def __init__(self, win, name):
        super().__init__()
        self.win, self.core, self.name = win, win.core, name
        self.cfg = self.core.cfg
        self.theme = win.theme
        self.newest_first = self.cfg["feed"]["order"] == "newest_first"
        self.positioned = False
        self.dirty = False
        self.unloaded = False  # its cards let go while it was hidden (ui.unload_hidden_minutes)
        self.separator = None  # (key of the first unread when the lane opened, count)
        self._unload_timer = QTimer(self, singleShot=True)
        self._unload_timer.timeout.connect(self._unload)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.header = _Header(self.theme, self.theme.word("lane_title", win.lane_title(name)))
        self.pill = QLabel()
        self.pill.setObjectName("newPill")
        self.header.h.insertWidget(1, self.pill)
        # what to show: everything / posts only / what's unread — one control, so the
        # three sit together; how: as a feed / as conversations — another
        lazy = getattr(self.core.lane_by_name.get(name), "lazy", False)
        self.has_posts_only = name in POSTS_ONLY_LANES or name.startswith("list:")
        self._kept = None  # "Unread": item keys on screen while the lane is open
        self._conv_members = {}  # top status id -> member status ids (conversations view)
        options = [("all", _("show_all"), _("show_all_tip"))]
        if self.has_posts_only:
            options.append(("posts", _("posts_only"), _("posts_only_tip")))
        if not lazy:
            options.append(("unread", _("unread_only"), _("unread_only_tip")))
        self.filter_seg = None
        if len(options) > 1:
            self.filter_seg = _Segmented(options, self._current_filter(), self.set_filter,
                                         self.theme.shape["posts_only"])
            self.header.add(self.filter_seg)
        self.view_seg = None
        if name in CONVERSATION_LANES:
            self.view_seg = _Segmented(
                [("feed", _("view_feed"), _("view_feed_tip")),
                 ("conversations", _("conv_mode"), _("conv_mode_tip"))],
                "conversations" if self.core.choice(f"conversations.{name}") else "feed",
                self.set_view, self.theme.shape["posts_only"])
            self.header.add(self.view_seg)
        self.btn_first = self.header.add(_button("↓ " + _("to_new"), self.jump_first_unread,
                                                 tip=_("to_new_tip")))
        self.btn_all = self.header.add(_button(_("mark_all_read"), self.mark_all_read,
                                               icon="mail-mark-read"))
        self.header.add(_button("", self.refresh_now, icon="view-refresh",
                                tip=_("refresh") + " (F5)"))
        lay.addWidget(self.header)
        self.view = FeedView(win.ctx)
        self.view.windowed = True
        self.view.build_at_once = int(self.cfg["feed"].get("build_at_once", 40))
        self.view.seen.connect(self._seen)
        lay.addWidget(self.view, 1)
        # "loading…" over the lane while it's being drawn: the click switches at once,
        # the drawing comes after (a lane of a few hundred cards takes a moment)
        self.plate = QLabel(_("loading"), self)
        self.plate.setObjectName("loadingPlate")
        self.plate.hide()
        self.btn_older = _button(_("older_down") if self.newest_first else _("older_up"),
                                 self.load_older, name="older")
        (self.view.footer if self.newest_first else self.view.header).addWidget(self.btn_older)
        self.btn_older.setVisible(not self.unread_only_on())

    # ---- what to show, and how ---------------------------------------------------
    def _current_filter(self):
        if self.has_posts_only and self.core.posts_only(self.name):
            return "posts"
        if self.core.choice(f"unread_only.{self.name}"):
            return "unread"
        return "all"

    def set_filter(self, which):
        """"all", "posts" (no replies) or "unread" — one at a time. The button turns at
        once; the lane is redrawn right after (it can take a moment with many posts)."""
        if self.filter_seg is not None:
            self.filter_seg.select(which)
        _busy(lambda: self._apply_filter(which), self)

    def _apply_filter(self, which):
        if self.has_posts_only and self.core.posts_only(self.name) != (which == "posts"):
            self.core.set_posts_only(self.name, which == "posts")
        self.core.set_choice(f"unread_only.{self.name}", which == "unread")
        self._kept = None
        self.positioned = False  # a different list: start over at the first unread
        self.separator = None
        self.btn_older.setVisible(which != "unread")  # older history is read: not here
        self.refresh(force=True)
        self._initial_position()
        self.win.update_badges()

    def set_view(self, which):
        """"feed" or "conversations" (one card per conversation)."""
        if self.view_seg is not None:
            self.view_seg.select(which)
        _busy(lambda: self._apply_view(which), self)

    def _apply_view(self, which):
        self.core.set_choice(f"conversations.{self.name}", which == "conversations")
        self.separator = None
        self.positioned = False
        self.refresh(force=True)

    def _seen(self, ids):
        if self.cfg["read"]["mark_read"] == "on_scroll":
            # a conversation card seen = its new messages seen
            ids = [m for i in ids for m in self._conv_members.get(i, [i])]
            self.core.mark_read(ids)

    def unread_only_on(self):
        return self.filter_seg is not None and self.filter_seg.current == "unread"

    def hideEvent(self, e):
        # left the lane: what got read meanwhile goes the next time it opens
        if self.unread_only_on():
            self._kept = None
            self.positioned = False
            self.dirty = True
        minutes = self.cfg["ui"].get("unload_hidden_minutes", 0)
        if minutes:
            self._unload_timer.start(int(minutes * 60_000))
        super().hideEvent(e)

    def _unload(self):
        """Long out of sight: its cards go (a card is a score of widgets, its pictures
        a megabyte each at screen size: a few hundred of them held over a gigabyte in a
        client kept open for days). Opening it again draws it anew, at the first unread."""
        if self.isVisible() or not self.view.order:
            return
        if self.win.stack.currentWidget() is self:
            return  # the lane in front, only out of sight with the window: keep it as is
        n = len(self.view.order)
        self.view.clear()
        self.positioned = False
        self.separator = None
        self.unloaded = True
        self.dirty = True
        log.info("lane %s unloaded: %d cards let go", self.name, n)

    def conversations_on(self):
        return self.view_seg is not None and self.view_seg.current == "conversations"

    def refresh_now(self):
        self.core.poll_now()

    def refresh(self, force=False):
        # hidden lanes only remember that they are stale; they catch up when shown
        if not self.isVisible() and not force and (self.positioned or self.unloaded):
            self.dirty = True
            return
        with diag.busy(f"lane {self.name}: draw"):
            self._refresh()

    def _refresh(self):
        self.dirty = False
        self.unloaded = False
        t0 = time.monotonic()
        entries = self.core.lane_entries(self.name)
        # browse lanes (local, federated) have nothing "unread": no marks, no divider
        lazy = getattr(self.core.lane_by_name.get(self.name), "lazy", False)
        unread = set() if lazy else self.core.unread_ids(entries)
        if self.unread_only_on():
            fresh = {item for item, st in entries if st["id"] in unread}
            self._kept = fresh if self._kept is None else self._kept | fresh
            entries = [e for e in entries if e[0] in self._kept]
            self.header.info.setText(_("unread_only_info", n=len(fresh)) if self._kept
                                     else _("unread_only_none"))
        elif self.filter_seg is not None:
            self.header.info.setText("")
        statuses = [st for _, st in entries]
        parents = self.core.parents_for(statuses)
        answers = self.core.my_replies(statuses)
        short = self.core.short_ids(statuses)
        specs, unknown = [], []
        for item_id, st in entries:
            parent = parents.get(st["id"])
            if parent is None and real(st).get("in_reply_to_id"):
                unknown.append(st)
            specs.append(CardSpec(key=item_id, status=st, parent=parent, unread=st["id"] in unread,
                                  extra={"my_replies": answers.get(real(st)["id"], []),
                                         "short_id": short.get(real(st)["id"])}))
        if self.conversations_on():
            specs = self._conversation_specs(entries, unread, parents, answers, short)
        if self.name in ("comments", "mentions"):
            self.core.check_my_replies(statuses)
        if unknown:
            self.core.ensure_parents(unknown)
        # "new below": fixed where the reader stood when the lane opened
        if self.separator is None and not self.positioned and not self.unread_only_on():
            first = next((s for s in specs if s.unread), None)
            if first is not None and any(not s.unread for s in specs):
                self.separator = (first.key, sum(1 for s in specs if s.unread))
        if self.separator and any(s.key == self.separator[0] for s in specs):
            i = next(i for i, s in enumerate(specs) if s.key == self.separator[0])
            text = self.theme.word("separator", _("new_below"), n=self.separator[1])
            specs.insert(i, CardSpec(key="__sep__", status={}, extra={"separator": text}))
        if self.newest_first:
            specs.reverse()
        if not self.positioned:
            self.view.set_specs(specs, keep_position=False, around=self._start_key(specs))
            if self.isVisible() and self.view.isVisible():
                # after the layout has settled (long posts take several passes), the
                # same way as when a drawn lane is shown
                QTimer.singleShot(0, self._initial_position)
        else:
            jump = self.cfg["feed"]["on_new"] == "jump_to_newest"
            had = set(self.view.keys())
            self.view.set_specs(specs, keep_position=True)
            if jump and any(s.key not in had for s in specs):
                self.view.scroll_to_end(not self.newest_first)
        self.update_strip()
        lane = self.core.lane_by_name.get(self.name)
        if lazy and not specs and lane is not None and \
                lane.source in getattr(self.core, "browse_empty", ()):
            self.header.info.setText(_("browse_empty"))
        elif lazy and self.filter_seg is None:
            self.header.info.setText("")
        log.debug("lane %s drawn: %d rows, %d unread, %.0f ms", self.name, len(specs),
                  len(unread), (time.monotonic() - t0) * 1000)

    def _conversation_specs(self, entries, unread, parents, answers, short):
        """One card per conversation: its top post, with a line about the rest."""
        from ...core.threads import conversations
        groups = conversations(entries, self.core.store.get_status, unread)
        tops = [g["top"] for g in groups]
        more_short = self.core.short_ids(tops)
        self._conv_members = {g["top"]["id"]: [m["id"] for m in g["members"]] for g in groups}
        specs = []
        for g in groups:
            top = g["top"]
            specs.append(CardSpec(
                key="conv:" + g["key"], status=top,
                parent=parents.get(top["id"]) or self.core.parent_of(top),
                unread=g["unread"] > 0,
                extra={"my_replies": answers.get(real(top)["id"], []),
                       "short_id": more_short.get(real(top)["id"]) or
                       short.get(real(top)["id"]),
                       "conversation": g}))
        return specs

    def show_plate(self, on=True):
        if on:
            self.plate.adjustSize()
            self.plate.move(max(0, (self.width() - self.plate.width()) // 2),
                            self.header.height() + 24)
            self.plate.raise_()
        self.plate.setVisible(on)

    def draw_shown(self):
        """Just switched to: let the switch and "loading…" show, then draw."""
        t = time.monotonic()
        self.show_plate()
        self.win.repaint()  # paints now, without running other events in between
        # a lane drawn for the first time is filled hidden and then shown, so Qt lays
        # all its cards out at once and "where reading stopped" lands where it should
        first = not self.positioned
        if first:
            self.view.hide()
        try:
            self.refresh(force=True)
        finally:
            if first:
                self.view.show()
                QTimer.singleShot(0, self._initial_position)
            self.show_plate(False)
        log.debug("lane %s on screen in %.0f ms", self.name, (time.monotonic() - t) * 1000)

    def _catch_up(self):
        if self.dirty and self.isVisible():
            self.draw_shown()

    def showEvent(self, e):
        super().showEvent(e)
        self._unload_timer.stop()
        if self.dirty:
            # stale since it was last on screen: show it as it was, "loading…" on top,
            # and redraw right after the switch has painted
            self.show_plate()
            QTimer.singleShot(0, self._catch_up)
        if not self.positioned:
            QTimer.singleShot(0, self._initial_position)
        if self.cfg["read"]["mark_read"] == "on_open":
            QTimer.singleShot(0, self.mark_all_read)

    def _start_key(self, specs):
        """Where reading starts (as _initial_position goes there): the cards around it
        are the ones built first."""
        if not specs:
            return None
        unread = [s.key for s in specs if s.unread]
        if self.cfg["feed"]["start_at"] == "first_unread" and unread:
            if self.newest_first:
                return unread[-1]
            if any(s.key == "__sep__" for s in specs):
                return "__sep__"
            return unread[0]
        return specs[0].key if self.newest_first else specs[-1].key

    def _initial_position(self):
        if self.positioned or not self.view.order or not self.view.isVisible():
            return
        self.positioned = True
        unread = self.view.unread_keys()
        if self.cfg["feed"]["start_at"] == "first_unread" and unread:
            if self.newest_first:
                self.view.scroll_to(unread[-1], "bottom")
            elif self.view.has("__sep__"):
                self.view.scroll_to("__sep__", "top")
            else:
                self.view.scroll_to(unread[0], "top")
        else:
            self.view.scroll_to_end(not self.newest_first)

    def jump_first_unread(self):
        unread = self.view.unread_keys()
        if unread:
            if self.newest_first:
                self.view.scroll_to(unread[-1], "bottom")
            else:
                self.view.scroll_to(unread[0], "top")
        else:
            self.view.scroll_to_end(not self.newest_first)

    def mark_all_read(self):
        self.core.mark_read(self.view.unread_status_ids())

    def load_older(self):
        self.btn_older.setEnabled(False)
        self.win.bridge.call(self.core.load_older(self.name),
                             ok=lambda n: self._older_done(n),
                             fail=lambda e: (self.btn_older.setEnabled(True), self.win.error(e)))

    def _older_done(self, n):
        self.btn_older.setEnabled(True)
        if not n:
            self.btn_older.setText(_("no_older"))

    def apply_read(self, ids):
        self.view.set_unread(ids, False)
        if self.isVisible():
            self.update_strip()

    def update_strip(self):
        # the store has the last word: a post marked read by any road (another lane,
        # a thread, another client) loses its mark here too, so "N new" never lies
        ids = [s.status["id"] for s in self.view.model  # (a conversation card speaks for
               if s.unread and s.status and not str(s.key).startswith("conv:")]  # many)
        read = self.core.store.read_set(ids) if ids else set()
        if read:
            self.view.set_unread(read, False)
        n = len(self.view.unread_keys())
        self.pill.setText(_("new_n", n=n))
        self.pill.setVisible(bool(n))
        # greyed, not hidden: buttons that come and go make the others jump about
        self.btn_all.setEnabled(bool(n))
        self.btn_first.setEnabled(bool(n))


def _busy(fn, lane=None):
    """Let the pressed button paint first (and "loading…" over the lane, if given),
    then do the slow part under a wait cursor."""
    from PySide6.QtWidgets import QApplication

    if lane is not None:
        lane.show_plate()

    def run():
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            fn()
        finally:
            QApplication.restoreOverrideCursor()
            if lane is not None:
                try:
                    lane.show_plate(False)
                except RuntimeError:  # the lane is gone
                    pass
    QTimer.singleShot(0, run)


class _Segmented(QWidget):
    """A choice of a few: buttons stuck together, one pressed — or, in themes with
    shape.posts_only = "check", a row of round marks (terminal, juick)."""

    def __init__(self, options, current, on_pick, style="segmented"):
        super().__init__()
        self.current = current
        self.buttons = {}
        h = QHBoxLayout(self)
        # marks need air around the group, or two groups read as one row of choices
        h.setContentsMargins(0 if style == "segmented" else 14, 0, 0, 0)
        h.setSpacing(0 if style == "segmented" else 12)
        for i, (key, text, tip) in enumerate(options):
            if style == "check":
                b = QRadioButton(text)
                b.setObjectName("check")
                b.setAutoExclusive(False)  # select() does it, the same for both looks
            else:
                b = QPushButton(text)
                b.setObjectName("seg")
                b.setProperty("pos", "first" if i == 0 else
                              "last" if i == len(options) - 1 else "middle")
            b.setCheckable(True)
            b.setChecked(key == current)
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: on_pick(k))
            h.addWidget(b)
            self.buttons[key] = b

    def select(self, key):
        self.current = key
        for k, b in self.buttons.items():
            b.setChecked(k == key)

class ThreadWidget(QWidget):
    def __init__(self, win, sid):
        super().__init__()
        self.win, self.core = win, win.core
        self.focus_id = sid
        self.title = _("thread_loading")
        self.info_text = ""
        self.loaded = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.header = _Header(win.theme)
        self.root = None
        self.sub_btn = self.header.add(_button(_("sub_thread"), self._toggle_sub,
                                               icon="mail-thread-watch", tip=_("sub_tip")))
        self.sub_btn.setCheckable(True)
        self.sub_btn.setEnabled(False)
        self.header.add(_button("", self.reload, icon="view-refresh", tip=_("refresh")))
        lay.addWidget(self.header)
        self.view = FeedView(win.ctx)
        self.view.seen.connect(self._seen)
        lay.addWidget(self.view, 1)
        self.statuses = set()
        self.reload()

    def _seen(self, ids):
        if self.core.cfg["read"]["mark_read"] != "manual":
            self.core.mark_read(ids)

    def reload(self, quiet=False):
        if not quiet:
            self.header.info.setText(_("loading"))
        self.win.bridge.call(self.core.thread(self.focus_id), ok=self._loaded,
                             fail=lambda e: self.header.info.setText(_("load_failed", err=e)))

    def update_sub_button(self):
        if self.root is None:
            return
        on = self.core.subscribed(self.root)
        self.sub_btn.blockSignals(True)
        self.sub_btn.setChecked(on)
        self.sub_btn.blockSignals(False)
        self.sub_btn.setText(_("subscribed") if on else _("sub_thread"))
        if on and self.info_text:
            self.header.info.setText(self.info_text)
            self.header.info.setToolTip("")
        self.sub_btn.setEnabled(True)

    def _toggle_sub(self):
        if self.root is None:
            return
        self.sub_btn.setEnabled(False)
        on = self.core.subscribed(self.root)
        job = (self.core.unsubscribe if on else self.core.subscribe)(self.root)
        self.win.bridge.call(job, ok=lambda _r: self.win.statusBar().showMessage(
            _("unsubbed" if on else "subbed"), 6000),
            fail=lambda e: (self.win.error(e), self.update_sub_button()))

    def focus_on(self, sid):
        self.focus_id = sid
        for row in self.view.rows.values():
            focus = row.status_id == sid
            if row.spec.focus != focus:
                row.update_spec(CardSpec(**{**row.spec.__dict__, "focus": focus}))
        self.view.scroll_to(sid, "top")

    def _loaded(self, nodes):
        self.statuses = {n.status["id"] for n in nodes}
        unread = self.core.unread_ids([(n.status["id"], n.status) for n in nodes])
        short = self.core.short_ids([n.status for n in nodes])
        specs = [CardSpec(key=n.status["id"], status=n.status, depth=n.depth,
                          number=n.number or None, in_thread=True,
                          focus=(n.status["id"] == self.focus_id and len(nodes) > 1),
                          unread=n.status["id"] in unread,
                          extra={"short_id": short.get(n.status["id"])}) for n in nodes]
        self.view.set_specs(specs, keep_position=self.loaded)
        root = nodes[0].status
        self.root = root
        self.update_sub_button()
        self.title = f'{real(root)["account"]["username"]}: {snippet(root, 30)}'
        self.header.title.setText(snippet(root, 60))
        self.info_text = _("thread_info", n=len(nodes) - 1) + \
            (f" · #{short[root['id']]}" if short.get(root["id"]) else "")
        self.header.info.setText(self.info_text)
        self._why_it_reaches_me(nodes)
        self.win.retitle(self)
        if not self.loaded:
            self.loaded = True
            self.view.scroll_to(self.focus_id, "top")

    def _why_it_reaches_me(self, nodes):
        """Not subscribed, yet the comments come? Say why: the server puts replies
        between people you follow into Home."""
        self.header.info.setToolTip("")
        if self.root is None or self.core.subscribed(self.root):
            return
        authors = [real(n.status)["account"] for n in nodes]

        def show(followed):
            if not followed or self.core.subscribed(self.root):
                return
            names = ", ".join("@" + a["acct"].split("@")[0] for a in followed[:3])
            more = len(followed) - 3
            if more > 0:
                names += " " + _("and_more", n=more)
            self.header.info.setText(self.info_text + " · " + _("thread_via_home",
                                                                 names=names))
            self.header.info.setToolTip(_("thread_via_home_tip"))
        self.win.bridge.call(self.core.followed_among(authors), ok=show,
                             fail=lambda e: None)

    def apply_read(self, ids):
        self.view.set_unread(ids, False)


class _PagedTab(QWidget):
    """A tab with a server timeline read page by page (a profile, a hashtag)."""

    def __init__(self, win, title):
        super().__init__()
        self.win, self.core = win, win.core
        self.title = title
        self.items = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.header = _Header(win.theme, title)
        lay.addWidget(self.header)
        self.view = FeedView(win.ctx)
        lay.addWidget(self.view, 1)
        self.btn_more = _button(_("older_down"), self.more, name="older")
        self.view.footer.addWidget(self.btn_more)

    def fetch(self, max_id):  # -> future with a page of statuses
        raise NotImplementedError

    def more(self):
        self.btn_more.setEnabled(False)
        max_id = self.items[-1]["id"] if self.items else None
        self.win.bridge.call(self.fetch(max_id), ok=self._page,
                             fail=lambda e: (self.btn_more.setEnabled(True), self.win.error(e)))

    def _page(self, page):
        known = {st["id"] for st in self.items}
        self.items += [st for st in page if st["id"] not in known]
        self.btn_more.setEnabled(bool(page))
        if not page:
            self.btn_more.setText(_("no_older"))
        self.core.ensure_parents(page)
        self.render()

    def render(self):
        short = self.core.short_ids(self.items)
        specs = [CardSpec(key=st["id"], status=st, parent=self.core.parent_of(st),
                          extra={"short_id": short.get(real(st)["id"])})
                 for st in self.items]
        self.view.set_specs(specs, keep_position=True)

    def apply_read(self, ids):
        pass


class AccountWidget(_PagedTab):
    """Someone's profile inside the app: who they are (bio, fields, counts, since
    when, whether they follow you), what you can do (follow, mention, put in a
    list, open in the browser), and their posts below."""

    def __init__(self, win, acc_id):
        super().__init__(win, "@…")
        self.acc_id = acc_id
        self.acc = None
        self.mine = bool(self.core.me) and acc_id == self.core.me["id"]
        if self.mine:
            self.header.add(_button(_("edit_profile"), win.edit_profile, icon="document-edit"))
        # who this is: a block of its own, not one more post — the banner, a tinted
        # card with an accent edge, and a "Posts" heading under it
        self.info = QFrame()
        self.info.setObjectName("profileCard")
        self.info.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.view.header.addWidget(self.info)
        self._info_layout = QVBoxLayout(self.info)
        self._info_layout.setContentsMargins(20, 16, 20, 18)
        self._info_layout.setSpacing(10)
        posts = QLabel(_("profile_posts"))
        posts.setObjectName("sectionTitle")
        self.view.header.addWidget(posts)
        self.relation = {}
        self._first_page = None
        self._origin_asked = False
        self.pinned = []
        self.featured = {}
        self.familiar = []  # of the people I follow, who follows this one
        self.reload_account()
        self.more()
        if self.core.cfg["feed"].get("profile_pinned", True):
            self.win.bridge.call(self.core.pinned(self.acc_id), ok=self._pinned,
                                 fail=lambda _e: None)
        if self.core.cfg["feed"].get("profile_featured", True):
            self.win.bridge.call(self.core.featured(self.acc_id), ok=self._featured,
                                 fail=lambda _e: None)

    def _featured(self, got):
        self.featured = got or {}
        if self.acc and (self.featured.get("tags") or self.featured.get("people")):
            self._fill()

    def _pinned(self, statuses):
        self.pinned = statuses or []
        if self.pinned:
            self.render()

    def render(self):
        """Pinned posts first (marked 📌), then the rest by time."""
        top = {st["id"] for st in self.pinned}
        rest = [st for st in self.items if st["id"] not in top]
        short = self.core.short_ids(self.pinned + rest)
        specs = [CardSpec(key="pin:" + st["id"], status=st, parent=self.core.parent_of(st),
                          extra={"short_id": short.get(real(st)["id"]), "pinned": True})
                 for st in self.pinned]
        specs += [CardSpec(key=st["id"], status=st, parent=self.core.parent_of(st),
                           extra={"short_id": short.get(real(st)["id"])}) for st in rest]
        self.view.set_specs(specs, keep_position=True)

    def fetch(self, max_id):
        return self.core.account_statuses(self.acc_id, max_id)

    def _page(self, page):
        if self._first_page is None:
            self._first_page = page
        super()._page(page)
        self._from_origin()

    def _from_origin(self):
        """Someone from another server mine knows little about (fewer posts here than
        their profile counts): read their newest from their own server."""
        acc, page = self.acc, self._first_page
        if self._origin_asked or acc is None or page is None or "@" not in acc.get("acct", ""):
            return
        if not self.core.cfg["feed"].get("remote_profiles", True):
            return
        if len(page) >= min(acc.get("statuses_count") or 0, self.core.cfg["feed"]["page_size"]):
            return  # my server has them
        self._origin_asked = True
        host = acc["acct"].split("@", 1)[1]
        self.header.info.setText(self.header.info.text() + " · " +
                                 _("origin_asking", host=host))
        have = [st.get("uri") for st in self.items]

        def got(statuses):
            known = {st["id"] for st in self.items}
            new = [st for st in statuses if st["id"] not in known]
            self.items = sorted(self.items + new, key=lambda st: st.get("created_at", ""),
                                reverse=True)
            info = self.header.info.text().replace(" · " + _("origin_asking", host=host), "")
            self.header.info.setText(info + (" · " + _("origin_got", n=len(new), host=host)
                                             if new else ""))
            if new:
                self.core.ensure_parents(new)
                self.render()
        self.win.bridge.call(self.core.posts_from_origin(acc, have), ok=got,
                             fail=lambda _e: None)

    def reload_account(self):
        self.win.bridge.call(self.core.account(self.acc_id), ok=self._account)
        if not self.mine:
            self.win.bridge.call(self.core.relationship(self.acc_id), ok=self._relation)

    def show_info(self):
        """Clicking the name of the person whose tab this is: back to their card."""
        self.view.verticalScrollBar().setValue(0)
        _flash(self.info)

    def _relation(self, rel):
        self.relation = rel or {}
        if self.acc:
            self._fill()

    def _account(self, acc):
        self.acc = acc
        self.title = "@" + acc["acct"]
        counts = " · ".join(_(key, n=acc[field]) for key, field in
                            (("posts_n", "statuses_count"), ("followers_n", "followers_count"),
                             ("following_n", "following_count")) if field in acc)
        self.header.title.setText(acc.get("display_name") or acc["username"])
        self.header.info.setText(" · ".join(x for x in (f"@{acc['acct']}", counts) if x))
        self.win.retitle(self)
        self._fill()
        self._from_origin()
        if not self.mine and self.core.supports("familiar"):
            self.win.bridge.call(self.core.familiar(self.acc_id), ok=self._familiar,
                                 fail=lambda _e: None)

    def _familiar(self, accounts):
        self.familiar = accounts or []
        if self.familiar and self.acc:
            self._fill()

    def _fill(self):
        from ...core import links
        from .text import clean
        acc, lay, theme = self.acc, self._info_layout, self.win.theme
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                _clear(item.layout())
        header = acc.get("header_static") or acc.get("header") or ""
        if header and not header.endswith("/missing.png"):
            banner = QLabel()
            banner.setObjectName("profileBanner")
            banner.setFixedHeight(120)
            banner.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

            def got(pm, w=banner):
                try:
                    width = max(w.width(), 400)
                    scaled = pm.scaled(width, 120, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                       Qt.TransformationMode.SmoothTransformation)
                    x = max(0, (scaled.width() - width) // 2)
                    w.setPixmap(scaled.copy(x, max(0, (scaled.height() - 120) // 2), width, 120))
                except RuntimeError:  # the card was rebuilt meanwhile
                    pass
            self.win.images.get(header, got)
            lay.addWidget(banner)
        name = QLabel(esc(acc.get("display_name") or acc["username"]))
        name.setObjectName("profileName")
        lay.addWidget(name)
        top = QHBoxLayout()
        top.setSpacing(14)
        avatar = QLabel()
        avatar.setFixedSize(72, 72)
        from .card import _round
        self.win.images.get(acc.get("avatar_static") or acc.get("avatar"),
                            lambda pm, w=avatar: w.setPixmap(_round(pm, 72)))
        top.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(6)
        bits = [f"@{esc(acc['acct'])}"]
        if acc.get("bot"):
            bits.append(_("bot"))
        if acc.get("locked"):
            bits.append("🔒 " + _("acc_locked"))
        if acc.get("created_at"):
            y, m, d = acc["created_at"][:10].split("-")
            bits.append(_("acc_since", date=f"{d}.{m}.{y}"))
        if self.relation.get("followed_by"):
            bits.append("<b>" + _("acc_follows_you") + "</b>")
        meta = QLabel(" · ".join(bits))
        meta.setObjectName("muted")
        meta.setTextFormat(Qt.TextFormat.RichText)
        col.addWidget(meta)
        note = acc.get("note") or ""
        if self.core.cfg["ui"]["links_in_app"]:
            note = links.in_app(note)
        bio = QLabel(clean(note, theme.css("link")))
        bio.setTextFormat(Qt.TextFormat.RichText)
        bio.setWordWrap(True)
        bio.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        bio.linkActivated.connect(self.win.on_link)
        col.addWidget(bio)
        for f in acc.get("fields") or []:
            value = f.get("value", "")
            if self.core.cfg["ui"]["links_in_app"]:
                value = links.in_app(value)
            row = QLabel(f'<b>{esc(f.get("name", ""))}</b>: {clean(value, theme.css("link"))}'
                         + (" ✓" if f.get("verified_at") else ""))
            row.setTextFormat(Qt.TextFormat.RichText)
            row.setWordWrap(True)
            row.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            row.linkActivated.connect(self.win.on_link)
            col.addWidget(row)
        from .text import link
        tags = [link("tag", t["name"], "#" + esc(t["name"]), theme.css("link"))
                + (f" <small>({int(t['statuses_count'])})</small>"
                   if t.get("statuses_count") else "")
                for t in self.featured.get("tags") or [] if t.get("name")]
        people = [link("account", a["id"], "@" + esc(a["acct"]), theme.css("link"))
                  for a in self.featured.get("people") or [] if a.get("id")]
        known = [link("account", a["id"], "@" + esc(a["acct"]), theme.css("link"))
                 for a in self.familiar[:5] if a.get("id")]
        if known:
            more = len(self.familiar) - len(known)
            row = QLabel(_("familiar", who=", ".join(known) +
                           (" " + _("act_more", n=more) if more > 0 else "")))
            row.setObjectName("featured")
            row.setTextFormat(Qt.TextFormat.RichText)
            row.setWordWrap(True)
            row.linkActivated.connect(self.win.on_link)
            col.addWidget(row)
        for key, items in (("featured_tags", tags), ("featured_people", people)):
            if items:
                row = QLabel(f"<b>{_(key)}</b> " + ", ".join(items))
                row.setObjectName("featured")
                row.setTextFormat(Qt.TextFormat.RichText)
                row.setWordWrap(True)
                row.linkActivated.connect(self.win.on_link)
                col.addWidget(row)
        top.addLayout(col, 1)
        lay.addLayout(top)

        from .flow import FlowLayout
        buttons = FlowLayout(spacing=8)  # too many for one line: they wrap, not shrink
        if not self.mine:
            following = self.relation.get("following")
            requested = self.relation.get("requested")
            label = _("unfollow") if following else \
                (_("follow_requested") if requested else _("follow"))
            fb = _button(label, self._toggle_follow, name="primary" if not following else "tool")
            buttons.addWidget(fb)
            if following:
                bell = self.relation.get("notifying")
                buttons.addWidget(_button("🔔 " + (_("bell_off") if bell else _("bell_on")),
                                          self._toggle_bell, tip=_("bell_tip")))
            buttons.addWidget(_button(_("mention"), lambda: self.win.compose(
                text=f"@{acc['acct']} ")))
            buttons.addWidget(_button(_("unmute") if self.relation.get("muting") else _("mute"),
                                      self._toggle_mute))
            buttons.addWidget(_button(_("unblock") if self.relation.get("blocking")
                                      else _("block"), self._toggle_block))
            if self.relation.get("followed_by") and self.core.supports("remove_follower"):
                buttons.addWidget(_button(_("remove_follower"), self._remove_follower))
            if following and self.core.supports("endorse"):
                buttons.addWidget(_button(
                    _("unendorse") if self.relation.get("endorsed") else _("endorse"),
                    self._toggle_endorse, tip=_("endorse_tip")))
            if self.win.ctx.fill_list_menu is not None:
                from PySide6.QtWidgets import QMenu
                lb = _button(_("add_to_list"), lambda: None)
                menu = QMenu(lb)
                menu.aboutToShow.connect(lambda m=menu: self.win.ctx.fill_list_menu(m, acc))
                lb.setMenu(menu)
                buttons.addWidget(lb)
        for which, field in (("following", "following_count"), ("followers", "followers_count")):
            if acc.get(field):
                buttons.addWidget(_button(_(f"people_{which}_n", n=acc[field]),
                                          lambda _c=False, w=which: self.win.open_people(acc, w)))
        if not self.mine:
            buttons.addWidget(_button(_("note_edit"), self.edit_note))
        buttons.addWidget(_button(_("open_browser"), lambda: self.win.open_url(acc.get("url"))))
        lay.addLayout(buttons)
        note = (self.relation.get("note") or "").strip()
        if note and not self.mine:
            label = QLabel("📝 " + esc(note).replace("\n", "<br>"))
            label.setObjectName("muted")
            label.setWordWrap(True)
            label.setToolTip(_("note_tip"))
            lay.addWidget(label)

    def edit_note(self):
        """My private note on this person — only I see it, on my server."""
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getMultiLineText(self, _("note_title", acct=self.acc["acct"]),
                                                 _("note_tip"), self.relation.get("note") or "")
        if ok:
            self.win.bridge.call(self.core.set_note(self.acc_id, text.strip()),
                                 ok=lambda r: self._relation(dict(self.relation,
                                                                  note=text.strip())),
                                 fail=self.win.error)

    def _toggle_bell(self):
        on = not self.relation.get("notifying")
        self.win.bridge.call(self.core.notify_posts(self.acc_id, on),
                             ok=lambda r: self._relation(dict(self.relation, notifying=on,
                                                              **(r or {}))),
                             fail=self.win.error)

    def _toggle_mute(self):
        on = not self.relation.get("muting")
        self.win.bridge.call(self.core.mute(self.acc_id, on),
                             ok=lambda r: self._relation(dict(self.relation, muting=on,
                                                              **(r or {}))))

    def _toggle_block(self):
        on = not self.relation.get("blocking")
        if on:
            from PySide6.QtWidgets import QMessageBox
            if QMessageBox.question(self, _("block"), _("block_q", acct=self.acc["acct"])) \
                    != QMessageBox.StandardButton.Yes:
                return
        self.win.bridge.call(self.core.block(self.acc_id, on),
                             ok=lambda r: self._relation(dict(self.relation, blocking=on,
                                                              **(r or {}))))

    def _toggle_follow(self):
        on = not (self.relation.get("following") or self.relation.get("requested"))
        self.win.bridge.call(self.core.follow(self.acc_id, on), ok=self._relation)

    def _remove_follower(self):
        from PySide6.QtWidgets import QMessageBox
        if QMessageBox.question(self, _("remove_follower"),
                                _("remove_follower_q", acct=self.acc["acct"])) \
                != QMessageBox.StandardButton.Yes:
            return
        acct = self.acc["acct"]

        def done(r):
            self._relation(dict(self.relation, followed_by=False, **(r or {})))
            self.win.statusBar().showMessage(_("follower_removed", acct=acct), 6000)
        self.win.bridge.call(self.core.remove_follower(self.acc_id), ok=done,
                             fail=self.win.error)

    def _toggle_endorse(self):
        on = not self.relation.get("endorsed")
        self.win.bridge.call(self.core.endorse(self.acc_id, on),
                             ok=lambda r: self._relation(dict(self.relation, endorsed=on,
                                                              **(r or {}))),
                             fail=self.win.error)


class TagWidget(_PagedTab):
    """Posts with a hashtag, as your server knows them."""

    def __init__(self, win, tag):
        super().__init__(win, "#" + tag)
        self.tag = tag
        self.header.info.setText(_("tag_info"))
        self.follow_btn = self.header.add(_button(_("tag_follow"), self._toggle_follow))
        self.follow_btn.setToolTip(_("tag_follow_tip"))
        self.following = False
        self.featured = None  # is it on my profile (featured tags); None: not known yet
        self.feature_btn = None
        if self.core.supports("featured_tags"):
            self.feature_btn = self.header.add(_button(_("tag_feature"), self._toggle_feature,
                                                       tip=_("tag_feature_tip")))
            self.feature_btn.setEnabled(False)
            win.bridge.call(self.core.featured_tag_names(), ok=self._featured,
                            fail=lambda _e: self.feature_btn.hide())
        win.bridge.call(self.core.tag_info(tag), ok=self._info, fail=lambda _e: None)
        self.more()

    def _featured(self, names):
        self.featured = self.tag.lower() in (names or set())
        self.feature_btn.setText(_("tag_unfeature") if self.featured else _("tag_feature"))
        self.feature_btn.setEnabled(True)

    def _toggle_feature(self):
        on = not self.featured
        self.feature_btn.setEnabled(False)
        self.win.bridge.call(self.core.feature_tag(self.tag, on),
                             ok=lambda _r: self._featured({self.tag.lower()} if on else set()),
                             fail=lambda e: (self.feature_btn.setEnabled(True),
                                             self.win.error(e)))

    def _info(self, t):
        self.following = bool((t or {}).get("following"))
        self.follow_btn.setText(_("tag_unfollow") if self.following else _("tag_follow"))

    def _toggle_mute(self):
        on = not self.relation.get("muting")
        self.win.bridge.call(self.core.mute(self.acc_id, on),
                             ok=lambda r: self._relation(dict(self.relation, muting=on,
                                                              **(r or {}))))

    def _toggle_block(self):
        on = not self.relation.get("blocking")
        if on:
            from PySide6.QtWidgets import QMessageBox
            if QMessageBox.question(self, _("block"), _("block_q", acct=self.acc["acct"])) \
                    != QMessageBox.StandardButton.Yes:
                return
        self.win.bridge.call(self.core.block(self.acc_id, on),
                             ok=lambda r: self._relation(dict(self.relation, blocking=on,
                                                              **(r or {}))))

    def _toggle_follow(self):
        self.win.bridge.call(self.core.follow_tag(self.tag, not self.following), ok=self._info,
                             fail=self.win.error)

    def fetch(self, max_id):
        return self.core.tag_timeline(self.tag, max_id)


def _clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear(item.layout())


def _flash(w):
    """Draw the eye to a widget for a moment (the focus style of a card)."""
    w.setProperty("focus", "true")
    w.style().unpolish(w)
    w.style().polish(w)

    def off():
        try:
            w.setProperty("focus", "false")
            w.style().unpolish(w)
            w.style().polish(w)
        except RuntimeError:
            pass
    QTimer.singleShot(1200, off)


class RequestsWidget(QScrollArea):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setObjectName("feed")
        self.body = QWidget()
        self.body.setObjectName("feedBody")
        self.lay = QVBoxLayout(self.body)
        self.lay.setContentsMargins(28, 20, 28, 20)
        self.lay.setSpacing(10)
        self.setWidget(self.body)
        self.refresh()

    def refresh(self):
        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        reqs = self.win.core.follow_requests
        if not reqs:
            self.lay.addWidget(QLabel(_("no_requests")))
        for acc in reqs:
            card = QFrame()
            card.setObjectName("card")
            v = QVBoxLayout(card)
            v.setContentsMargins(18, 14, 18, 14)
            name = QLabel(f'<b>{display_name(acc)}</b> @{esc(acc["acct"])} — '
                          f'<a href="{esc(acc.get("url", ""))}">{_("profile")} ↗</a>')
            name.setOpenExternalLinks(True)
            v.addWidget(name)
            note = QLabel(esc(snippet({"content": acc.get("note", "")}, 300)))
            note.setWordWrap(True)
            note.setObjectName("muted")
            v.addWidget(note)
            h = QHBoxLayout()
            h.addWidget(_button(_("approve"), lambda _c=False, a=acc["id"]:
                                self.win.answer_follow(a, True), icon="dialog-ok"))
            h.addWidget(_button(_("reject"), lambda _c=False, a=acc["id"]:
                                self.win.answer_follow(a, False), icon="dialog-cancel"))
            h.addStretch(1)
            v.addLayout(h)
            self.lay.addWidget(card)
        self.lay.addStretch(1)

    def apply_read(self, ids):
        pass


class ActivityWidget(QWidget):
    """Who favourited, boosted, followed: one row per post and kind, the names
    gathered, like a phone's notification shade. Seen once it's on screen."""

    MAX_NAMES = 3

    def __init__(self, win):
        super().__init__()
        self.win, self.core = win, win.core
        self.view = None  # not a FeedView: Ctrl+F has nothing to do here
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.header = _Header(win.theme, win.theme.word("lane_title", _("lane_activity")))
        self.header.add(_button(_("mark_all_read"), self.core.mark_activity_seen,
                                icon="mail-mark-read"))
        if self.core.supports("dismiss"):
            self.header.add(_button(_("activity_clear"), self._clear, icon="edit-clear-all",
                                    tip=_("activity_clear_tip")))
        lay.addWidget(self.header)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setObjectName("feed")
        body = QWidget()
        body.setObjectName("feedBody")
        outer = QHBoxLayout(body)
        outer.setContentsMargins(0, 0, 0, 0)
        self.column = QWidget()
        self.column.setMaximumWidth(win.cfg["ui"]["max_width"] or 16777215)
        outer.addWidget(self.column, 1)
        self.lay = QVBoxLayout(self.column)
        self.lay.setContentsMargins(20, 14, 20, 14)
        self.lay.setSpacing(8)
        self.scroll.setWidget(body)
        lay.addWidget(self.scroll, 1)
        self._seen_timer = QTimer(self, singleShot=True, interval=1500)
        self._seen_timer.timeout.connect(self._mark_seen)
        self.refresh()

    @staticmethod
    def groups(entries):
        """Neighbouring entries of one kind about one post become one row."""
        out = []
        for e in entries:
            key = (e["type"], (e.get("status") or {}).get("id"))
            if out and out[-1]["key"] == key:
                out[-1]["entries"].append(e)
            else:
                out.append({"key": key, "entries": [e]})
        return out

    def refresh(self):
        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        seen = self.core.activity_seen_mark()
        entries = self.core.activity_entries()
        if not entries:
            self.lay.addWidget(QLabel(_("activity_none")))
        for g in self.groups(entries):
            self.lay.addWidget(self._row(g, any(e["sort"] > seen for e in g["entries"])))
        self.lay.addStretch(1)
        if self.isVisible():
            self._seen_timer.start()

    def _row(self, group, unread):
        es = group["entries"]
        kind = es[0]["type"]
        st = es[0].get("status")
        card = QFrame()
        card.setObjectName("card")
        card.setProperty("unread", "true" if unread else "false")
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 10, 16, 10)
        v.setSpacing(4)
        names = list(dict.fromkeys(
            f'<a href="fedtail:account/{esc(e["account"]["id"])}" style="text-decoration:none;'
            f'color:{self.win.theme.c["text"].name()};"><b>{display_name(e["account"])}</b></a>'
            for e in es))
        more = len(names) - self.MAX_NAMES
        who = ", ".join(names[:self.MAX_NAMES]) + \
            (" " + _("act_more", n=more) if more > 0 else "")
        top = QLabel(f'{who} <span style="color:{self.win.theme.c["muted"].name()};">— '
                     f'{_("act_" + kind) if kind in ACT_KINDS else kind}</span>')
        top.setTextFormat(Qt.TextFormat.RichText)
        top.setWordWrap(True)
        top.linkActivated.connect(self.win.on_link)
        if self.core.supports("dismiss"):
            line = QHBoxLayout()
            line.addWidget(top, 1)
            x = QPushButton("×")
            x.setObjectName("tool")
            x.setFixedWidth(28)
            x.setToolTip(_("activity_dismiss_tip"))
            x.clicked.connect(lambda _c=False, ids=[e["id"] for e in es]: self._dismiss(ids))
            line.addWidget(x, 0, Qt.AlignmentFlag.AlignTop)
            v.addLayout(line)
        else:
            v.addWidget(top)
        if st:
            post = QLabel(f'<a href="fedtail:thread/{esc(real(st)["id"])}" '
                          f'style="text-decoration:none;color:{self.win.theme.c["muted"].name()};">'
                          f'«{esc(snippet(st, 160))}»</a>')
            post.setTextFormat(Qt.TextFormat.RichText)
            post.setWordWrap(True)
            post.setCursor(Qt.CursorShape.PointingHandCursor)
            post.linkActivated.connect(self.win.on_link)
            v.addWidget(post)
        return card

    def _mark_seen(self):
        if self.isVisible() and self.window().isActiveWindow():
            self.core.mark_activity_seen()

    def _dismiss(self, ids):
        """A row gone: each notification in it, here and on the server."""
        for nid in ids:
            self.win.bridge.call(self.core.dismiss_activity(nid), fail=self.win.error)

    def _clear(self):
        from PySide6.QtWidgets import QMessageBox
        if QMessageBox.question(self, _("activity_clear"), _("activity_clear_q")) \
                == QMessageBox.StandardButton.Yes:
            self.win.bridge.call(self.core.clear_activity(), fail=self.win.error)

    def showEvent(self, e):
        super().showEvent(e)
        self._seen_timer.start()

    def apply_read(self, ids):
        pass


ACT_KINDS = ("favourite", "reblog", "follow", "poll", "update", "status")


class AccountRow(QFrame):
    """A person in a list (search results, followers): face, name, a line of
    bio, and a Follow button that knows the current state."""

    def __init__(self, win, acc, relation=None):
        super().__init__()
        self.win, self.core, self.acc = win, win.core, acc
        self.relation = relation or {}
        self.setObjectName("card")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 14, 10)
        h.setSpacing(12)
        avatar = QLabel()
        avatar.setFixedSize(40, 40)
        from .card import _round
        win.images.get(acc.get("avatar_static") or acc.get("avatar"),
                       lambda pm, w=avatar: w.setPixmap(_round(pm, 40)))
        h.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        name = QLabel(f'<a href="fedtail:account/{esc(acc["id"])}" style="text-decoration:none;'
                      f'color:{win.theme.c["text"].name()};"><b>{display_name(acc)}</b></a>'
                      f' <span style="color:{win.theme.c["muted"].name()};">@{esc(acc["acct"])}'
                      f'{" · " + _("bot") if acc.get("bot") else ""}</span>')
        name.setTextFormat(Qt.TextFormat.RichText)
        name.linkActivated.connect(win.on_link)
        col.addWidget(name)
        note = snippet({"content": acc.get("note", "")}, 160)
        if note:
            bio = QLabel(esc(note))
            bio.setObjectName("muted")
            bio.setWordWrap(True)
            col.addWidget(bio)
        counts = " · ".join(_(key, n=acc[field]) for key, field in
                            (("posts_n", "statuses_count"), ("followers_n", "followers_count"))
                            if field in acc)
        if counts or self.relation.get("followed_by"):
            extra = QLabel(counts + (" · <b>" + _("acc_follows_you") + "</b>"
                                     if self.relation.get("followed_by") else ""))
            extra.setObjectName("muted")
            extra.setTextFormat(Qt.TextFormat.RichText)
            col.addWidget(extra)
        h.addLayout(col, 1)
        self.btn = None
        if not self.core.me or acc["id"] != self.core.me["id"]:
            self.btn = _button("", self._toggle)
            h.addWidget(self.btn, 0, Qt.AlignmentFlag.AlignTop)
            self._paint()

    def _paint(self):
        r = self.relation
        self.btn.setText(_("unfollow") if r.get("following") else
                         _("follow_requested") if r.get("requested") else _("follow"))
        self.btn.setObjectName("tool" if r.get("following") or r.get("requested") else "primary")
        self.btn.style().unpolish(self.btn)
        self.btn.style().polish(self.btn)

    def _toggle(self):
        on = not (self.relation.get("following") or self.relation.get("requested"))
        self.btn.setEnabled(False)

        def done(rel):
            self.relation = rel or {}
            self.btn.setEnabled(True)
            self._paint()
        self.win.bridge.call(self.core.follow(self.acc["id"], on), ok=done,
                             fail=lambda e: (self.btn.setEnabled(True), self.win.error(e)))


class TagRow(QFrame):
    """#tag with how many people used it lately, Follow tag, and a click to open it."""

    def __init__(self, win, tag):
        super().__init__()
        self.win, self.core, self.tag = win, win.core, tag
        self.setObjectName("card")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 8, 14, 8)
        people = sum(int(d.get("accounts", 0)) for d in (tag.get("history") or [])[:7])
        label = QLabel(f'<a href="fedtail:tag/{esc(tag["name"])}" style="text-decoration:none;'
                       f'color:{win.theme.c["link"].name()};"><b>#{esc(tag["name"])}</b></a>'
                       + (f' <span style="color:{win.theme.c["muted"].name()};">· '
                          f'{_("tag_people", n=people)}</span>' if people else ""))
        label.setTextFormat(Qt.TextFormat.RichText)
        label.linkActivated.connect(win.on_link)
        h.addWidget(label, 1)
        self.btn = _button("", self._toggle)
        h.addWidget(self.btn)
        self._paint()

    def _paint(self):
        on = bool(self.tag.get("following"))
        self.btn.setText(_("tag_unfollow") if on else _("tag_follow"))
        self.btn.setToolTip(_("tag_follow_tip"))

    def _toggle(self):
        on = not self.tag.get("following")
        self.btn.setEnabled(False)

        def done(t):
            self.tag = dict(self.tag, following=bool((t or {}).get("following", on)))
            self.btn.setEnabled(True)
            self._paint()
        self.win.bridge.call(self.core.follow_tag(self.tag["name"], on), ok=done,
                             fail=lambda e: (self.btn.setEnabled(True), self.win.error(e)))


class SearchWidget(QWidget):
    """Finding new sources: people (by name, @user@server or a profile link),
    hashtags and posts, with Follow right there. With an empty query it shows the
    tags you follow."""

    def __init__(self, win, query=""):
        super().__init__()
        self.win, self.core = win, win.core
        self.title = _("search_title")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.header = _Header(win.theme, _("search_title"))
        lay.addWidget(self.header)
        self.view = FeedView(win.ctx)
        lay.addWidget(self.view, 1)
        from PySide6.QtWidgets import QLineEdit
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(_("search_placeholder"))
        self.edit.setClearButtonEnabled(True)
        self.edit.returnPressed.connect(lambda: self.run(self.edit.text()))
        self.view.header.addWidget(self.edit)
        self.box = QWidget()
        self.box_lay = QVBoxLayout(self.box)
        self.box_lay.setContentsMargins(0, 0, 0, 0)
        self.box_lay.setSpacing(8)
        self.view.header.addWidget(self.box)
        self.edit.setText(query)
        self.run(query)

    def focus(self):
        self.edit.setFocus()
        self.edit.selectAll()

    def _section(self, text):
        lab = QLabel(text)
        lab.setObjectName("listsHeader")
        self.box_lay.addWidget(lab)

    def run(self, query):
        query = query.strip()
        _clear(self.box_lay)
        self.view.set_specs([], keep_position=False)
        if not query:
            self.header.info.setText(_("search_hint"))
            self.win.bridge.call(self.core.followed_tags(), ok=self._followed_tags)
            return
        self.title = _("search_title") + ": " + query
        self.win.retitle(self)
        self.header.info.setText(_("searching"))
        self.win.bridge.call(self.core.search(query), ok=self._results,
                             fail=lambda e: self.header.info.setText(_("load_failed", err=e)))

    def _followed_tags(self, tags):
        if tags:
            self._section(_("followed_tags"))
            for t in tags:
                self.box_lay.addWidget(TagRow(self.win, t))

    def _results(self, res):
        accs, tags, sts = res["accounts"], res["hashtags"], res["statuses"]
        self.header.info.setText(_("search_found", people=len(accs), tags=len(tags),
                                   posts=len(sts)) if accs or tags or sts else _("search_none"))
        if accs:
            self._section(_("search_people"))
            for a in accs:
                self.box_lay.addWidget(AccountRow(self.win, a, res["relations"].get(a["id"])))
        if tags:
            self._section(_("search_tags"))
            for t in tags:
                self.box_lay.addWidget(TagRow(self.win, t))
        if sts:
            self._section(_("search_posts"))
            short = self.core.short_ids(sts)
            self.view.set_specs([CardSpec(key=st["id"], status=st, parent=self.core.parent_of(st),
                                          extra={"short_id": short.get(real(st)["id"])})
                                 for st in sts], keep_position=False)

    def apply_read(self, ids):
        pass


class PeopleWidget(QWidget):
    """Whom someone follows, or who follows them — a way to find people through
    people you know. Each with a Follow button."""

    def __init__(self, win, acc, which):
        super().__init__()
        self.win, self.core, self.acc, self.which = win, win.core, acc, which
        self.acc_id = acc["id"]
        self.title = _("people_" + which, acct=acc["acct"])
        self.next = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.header = _Header(win.theme, self.title)
        lay.addWidget(self.header)
        self.view = FeedView(win.ctx)
        lay.addWidget(self.view, 1)
        self.box = QWidget()
        self.box_lay = QVBoxLayout(self.box)
        self.box_lay.setContentsMargins(0, 0, 0, 0)
        self.box_lay.setSpacing(8)
        self.view.header.addWidget(self.box)
        self.btn_more = _button(_("older_down"), self.more, name="older")
        self.view.footer.addWidget(self.btn_more)
        self.count = 0
        self.from_origin = False
        self.shown_ids = set()
        self.more()

    def more(self):
        self.btn_more.setEnabled(False)
        self.win.bridge.call(self.core.people(self.acc_id, self.which, self.next), ok=self._page,
                             fail=lambda e: (self.btn_more.setEnabled(True), self.win.error(e)))

    def _page(self, got):
        res, nxt = got
        for a in res["accounts"]:
            self.box_lay.addWidget(AccountRow(self.win, a, res["relations"].get(a["id"])))
        self.count += len(res["accounts"])
        self.header.info.setText(_("people_shown", n=self.count))
        self.next = nxt
        self.shown_ids = getattr(self, "shown_ids", set()) | {a["id"] for a in res["accounts"]}
        if res.get("total") is not None:
            self.header.info.setText(_("people_shown", n=self.count) + " · " +
                                     _("people_origin_total", n=res["total"]))
        self.btn_more.setEnabled(bool(nxt))
        if nxt:
            return
        host = self.acc["acct"].split("@", 1)[1] if "@" in self.acc["acct"] else ""
        if host and not self.from_origin and \
                self.core.cfg["feed"].get("remote_people", True):
            # my server knows only part of them: the rest is on theirs
            self.from_origin = True
            self.btn_more.setText(_("people_more_from", host=host))
            self.btn_more.setEnabled(True)
            self.btn_more.clicked.disconnect()
            self.btn_more.clicked.connect(self._ask_origin)
        else:
            self.btn_more.setText(_("no_older"))

    def _ask_origin(self):
        self.btn_more.setEnabled(False)
        self.btn_more.setText(_("loading"))
        self.win.bridge.call(
            self.core.people_from_origin(self.acc, self.which, self.shown_ids), ok=self._page,
            fail=lambda e: (self.btn_more.setText(_("no_older")), self.win.error(e)))

    def apply_read(self, ids):
        pass
