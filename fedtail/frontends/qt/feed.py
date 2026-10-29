"""Scrollable lists of posts: lanes, threads, accounts; plus follow requests.

The one rule here: nothing moves under the reader. Every update keeps the
first visible post at the same place on screen, and images reserve their
space before they load.
"""

import logging
import time
import weakref
from dataclasses import replace

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ... import diag
from ...i18n import _
from ...model import Relationship
from ...model import real as real_entry
from ...model.text import snippet, snippet_html
from ..common import activity, timed
from ..common.lane import MEDIA_KINDS, LaneModel
from ..common.lane import MediaFilter as MediaChoice
from ..richtext import plain_tip
from .card import CardSpec, make_spec
from .feedview import READING_S, FeedView  # noqa: F401 — the list of cards, for all
from .gone import clear
from .text import display_name, esc

log = logging.getLogger(__name__)


THEME = None  # set by the window: whose pictures the lanes' buttons get
COMPACT_HEADERS = False  # set by the window in the split layout: slim lane headers


class MediaFilter:
    """The funnel next to Refresh: show only posts with pictures, gifs, video… —
    for this run only (never saved: posts that vanish after a restart drive one mad).
    on_change() redraws the view. What it keeps is state's (common/lane.py)."""

    def __init__(self, header, on_change, state=None):
        from PySide6.QtWidgets import QMenu
        self.state = state or MediaChoice()
        self.on_change = on_change
        self.btn = _button("", lambda: None, icon="filter", tip=_("media_filter_tip"))
        if self.btn.icon().isNull():
            self.btn.setText("⏷ " + _("media_filter"))
        menu = QMenu(self.btn)
        self.actions = {}
        # the menu's actions reach back only weakly: a closed tab's filter and its tab
        # would otherwise hold each other through the connections (the tabs stress
        # test: four QActions and a tab's Python side left behind with every tab)
        me = weakref.ref(self)
        for kind in MEDIA_KINDS:
            a = menu.addAction(_("filter_" + kind))
            a.setCheckable(True)
            a.setChecked(True)
            a.toggled.connect(lambda on, k=kind, me=me: me() and me()._toggle(k, on))
            self.actions[kind] = a
        menu.addSeparator()
        # boosts apart from the kinds: someone who boosts a lot hides their own posts
        b = menu.addAction(_("filter_boosts"))
        b.setCheckable(True)
        b.setChecked(True)
        b.toggled.connect(lambda on, me=me: me() and me()._toggle_boosts(on))
        self.actions["boosts"] = b
        menu.addSeparator()
        menu.addAction(_("filter_all"), lambda me=me: me() and me().reset())
        self.btn.setMenu(menu)
        from PySide6.QtWidgets import QToolButton
        if isinstance(self.btn, QToolButton):
            self.btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        header.add(self.btn)

    def active(self):
        return self.state.active()

    def keeps(self, entry):
        return self.state.keeps(entry)

    def _toggle_boosts(self, on):
        self.state.boosts = on
        self._toggle("text", "text" in self.state.wanted)  # restyle and redraw

    def _toggle(self, kind, on):
        self.state.toggle(kind, on)
        self.btn.setProperty("active", "true" if self.active() else "false")
        self.btn.style().unpolish(self.btn)
        self.btn.style().polish(self.btn)
        self.on_change()

    def reset(self):
        for a in self.actions.values():
            a.blockSignals(True)
            a.setChecked(True)
            a.blockSignals(False)
        self.state.reset()
        self._toggle("text", True)


def _button(text, slot, name="tool", icon=None, tip=None):
    b = QPushButton(text)
    b.setObjectName(name)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    # focus by Tab only, never by a click: a clicked button inside the feed that then
    # waits disabled ("older…") handed the focus to the next card, and the scroll jumped
    # to show it; and j / k stay with the feed after a click
    b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    if icon:
        from . import icons
        ic = icons.icon(icon, THEME) if THEME is not None else QIcon()
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

    def __init__(self, text="", keep=0):
        super().__init__()
        self._full = ""
        self._tip = ""
        self._keep = keep  # this many letters stay however tight it gets ("Л…" said nothing)
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
        QLabel.setToolTip(self, plain_tip("\n\n".join(parts)))  # names, titles: not ours

    def text(self):
        return self._full

    def _elide(self):
        if self._keep:
            fm = self.fontMetrics()
            least = min(fm.horizontalAdvance(self._full) + 4,
                        fm.horizontalAdvance(self._full[:self._keep] + "…") + 4)
            if self.minimumWidth() != max(40, least):
                self.setMinimumWidth(max(40, least))
        shown = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight,
                                              max(self.width(), 40))
        QLabel.setText(self, shown)
        self._show_tip()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def changeEvent(self, e):  # noqa: N802 — a theme's font: measured anew
        super().changeEvent(e)
        if e.type() == e.Type.FontChange:
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
        # two rows: everything in the first; the second takes the choices (all / posts
        # only / new, feed / conversations) when even a short first row won't fit
        self.v = QVBoxLayout(self)
        self.h = QHBoxLayout()
        self.h2 = QHBoxLayout()
        self.h.setContentsMargins(0, 0, 0, 0)
        self.h2.setContentsMargins(0, 0, 0, 0)
        self.v.addLayout(self.h)
        self.v.addLayout(self.h2)
        if COMPACT_HEADERS:  # the split layout: a slim strip under the author's bar
            self.setProperty("slim", "true")
            self.v.setContentsMargins(12, 3, 8, 3)
            self.v.setSpacing(3)
            self.h.setSpacing(6)
            self.h2.setSpacing(6)
        else:
            self.v.setContentsMargins(28, 12, 20, 12)
            self.v.setSpacing(8)
            self.h.setSpacing(12)
            self.h2.setSpacing(12)
        # a long title or a long note must never make the window wider: they give way
        self.title = _ElidedLabel(title, keep=8)
        self.title.setObjectName("laneTitle")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.h.addWidget(self.title, 3)
        self.info = _ElidedLabel()
        self.info.setObjectName("laneInfo")
        self.info.setTextFormat(Qt.TextFormat.PlainText)
        self.h.addWidget(self.info, 2)

        # a narrow window: the header gives way instead of holding the window wide (the
        # tour of 23.10: no lane narrower than 860–1350 px, by theme and font) — first
        # the pictures' buttons drop their words, then the words' buttons keep only
        # their glyph ("↓ To new" → "↓"), then the note goes
        self.setMinimumWidth(160)
        self._words = {}  # button → (its words, its tooltip) as made
        self._segs = []   # the choices: (widget, its place in the first row)
        self._level = 0

    def add(self, w):
        # the split layout: a button with a picture shows only the picture, its words
        # in the tooltip — a row of words over every lane was a heap of buttons
        if COMPACT_HEADERS and isinstance(w, QPushButton) and not w.icon().isNull() \
                and w.text() and w.objectName() != "seg":
            w.setToolTip(w.toolTip() or w.text())
            w.setText("")
        if isinstance(w, _Segmented):
            self._segs.append((w, self.h.count()))
        self.h.addWidget(w)
        if isinstance(w, QPushButton) and w.text() and w.objectName() != "seg":
            self._words[w] = (w.text(), w.toolTip())
        return w

    def _apply(self, level):
        for b, (text, tip) in self._words.items():
            if level >= 1 and not b.icon().isNull():
                b.setText("")
                b.setToolTip(tip or text)
            elif level >= 2 and " " in text and len(text.split(" ", 1)[0]) <= 2:
                b.setText(text.split(" ", 1)[0])  # the glyph that leads the words
                b.setToolTip(tip or text)
            else:
                b.setText(text)
                b.setToolTip(tip)
        self.info.setVisible(level < 3)
        below = level >= 4  # the choices on a row of their own
        for w, at in self._segs:
            if below and self.h.indexOf(w) >= 0:
                self.h.removeWidget(w)
                self.h2.addWidget(w)
            elif not below and self.h2.indexOf(w) >= 0:
                self.h2.removeWidget(w)
                self.h.insertWidget(min(at, self.h.count()), w)
        if below and self.h2.count() == len(self._segs):
            self.h2.addStretch(1)
        elif not below:
            while self.h2.count():  # the stretch, if any
                self.h2.takeAt(0)
        self._level = level

    def _need(self):
        m = self.v.contentsMargins()
        return max(self.h.sizeHint().width(), self.h2.sizeHint().width()) + \
            m.left() + m.right()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not self._words and not self._segs:
            return
        width = self.width()
        level = 0
        for level in range(5):  # the fullest that fits
            self._apply(level)
            if self._need() <= width:
                break


class LaneWidget(QWidget):
    def __init__(self, win, name):
        super().__init__()
        # the core as the model (core.view): what comes from it is Post, Account…
        self.win, self.core, self.name = win, win.ctx.view, name
        self.cfg = self.core.cfg
        self.theme = win.theme
        self.newest_first = self.cfg["feed"]["order"] == "newest_first"
        self.positioned = False
        self.dirty = False
        self.unloaded = False  # its cards let go while it was hidden (ui.unload_hidden_minutes)
        self.empty_note = None  # "the server gives this lane empty" (live feeds off)
        # what it shows and how (common/lane.py): the filters, the divider, the cards
        self.lm = LaneModel(self.core, name, lambda n: self.theme.word(
            "separator", _("new_below"), n=n))
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
        options = [(k, *self.lm.filter_words(k)) for k in self.lm.filters]
        self.filter_seg = None
        if len(options) > 1:
            self.filter_seg = _Segmented(options, self.lm.current_filter(), self.set_filter,
                                         self.theme.shape["posts_only"])
            self.header.add(self.filter_seg)
        self.view_seg = None
        if self.lm.conversations_offered():
            self.view_seg = _Segmented(
                [("feed", _("view_feed"), _("view_feed_tip")),
                 ("conversations", _("conv_mode"), _("conv_mode_tip"))],
                "conversations" if self.core.choice(f"conversations.{name}") else "feed",
                self.set_view, self.theme.shape["posts_only"])
            self.header.add(self.view_seg)
        self.btn_first = self.header.add(_button("↓ " + _("to_new"), self.jump_first_unread,
                                                 tip=_("to_new_tip")))
        self.btn_all = self.header.add(_button(_("mark_all_read"), self.mark_all_read,
                                               icon="mark_read"))
        self.media_filter = MediaFilter(self.header, lambda: self.refresh(force=True),
                                        self.lm.media)
        # a lane of events only (Activity…): "Clear" — every notification, on the server
        self.clear_btn = None
        if self.lm.events_only():
            self.clear_btn = self.header.add(_button(_("activity_clear"), self._clear,
                                                     icon="clear",
                                                     tip=_("activity_clear_tip")))
            self.clear_btn.setVisible(self.core.supports("dismiss"))
        self.header.add(_button("", self.refresh_now, icon="refresh",
                                tip=_("refresh") + " (F5)"))
        lay.addWidget(self.header)
        self.view = FeedView(win.ctx)
        self.view.windowed = True
        self.view.seen.connect(self._seen)
        self.view.stood.connect(lambda key, end: self.positioned and self.lm.stood(key, end))
        lay.addWidget(self.view, 1)
        # "loading…" over the lane while it's being drawn: the click switches at once,
        # the drawing comes after (a lane of a few hundred cards takes a moment)
        from .loading import LoadingPlate
        self.plate = LoadingPlate(_("loading"), self)  # the swinging opossum beside it
        self.plate.hide()
        self.btn_older = _button(_("older_down") if self.newest_first else _("older_up"),
                                 self.load_older, name="older")
        (self.view.footer if self.newest_first else self.view.header).addWidget(self.btn_older)
        # nothing older to fetch in a lane of events only (they come with the poll), as GTK
        self.btn_older.setVisible(not self.unread_only_on() and not self.lm.events_only())
        # reading.older_ahead: the "older" end in sight — the core fetches a page itself
        self.view.verticalScrollBar().valueChanged.connect(self._older_in_sight)

    # ---- what to show, and how ---------------------------------------------------
    @property
    def separator(self):
        """(key of the first unread when the lane opened, count) — or None."""
        return self.lm.separator

    @separator.setter
    def separator(self, value):
        self.lm.separator = value

    def set_filter(self, which):
        """"all", "posts" (no replies) or "unread" — one at a time. The button turns at
        once; the lane is redrawn right after (it can take a moment with many posts)."""
        if self.filter_seg is not None:
            self.filter_seg.select(which)
        _busy(lambda: self._apply_filter(which), self)

    def _apply_filter(self, which):
        self.lm.set_filter(which)
        self.positioned = False  # a different list: start over at the first unread
        # older history is read: not with "unread only"; a lane of events only has none
        self.btn_older.setVisible(which != "unread" and not self.lm.events_only())
        self.refresh(force=True)
        self._initial_position()
        self.win.update_badges()

    def set_view(self, which):
        """"feed" or "conversations" (one card per conversation)."""
        if self.view_seg is not None:
            self.view_seg.select(which)
        _busy(lambda: self._apply_view(which), self)

    def _apply_view(self, which):
        self.lm.set_conversations(which == "conversations")
        self.positioned = False
        self.refresh(force=True)

    def _seen(self, ids):
        events = [i for i in ids if str(i).startswith("event:")]
        ids = self.lm.read(ids)  # a conversation card seen = its new messages seen;
        if events:                # an event's row seen: the events up to it (core)
            self.view.set_unread(events, False)
        if ids:
            self.core.mark_read(ids)

    def unread_only_on(self):
        return self.filter_seg is not None and self.filter_seg.current == "unread"

    def hideEvent(self, e):
        # left the lane: what got read meanwhile goes the next time it opens
        if self.lm.left():
            self.positioned = False
            self.dirty = True
        minutes = self.cfg["ui"].get("unload_hidden_minutes", 0)
        if minutes:
            self._unload_timer.start(int(minutes * 60_000))
        super().hideEvent(e)

    def _unload(self):
        """Out of sight long (unload_hidden_minutes) or shown before the lanes kept
        (keep_hidden_lanes, common/lanekeep.py): its cards go (a card is a score of
        widgets, its pictures a megabyte each at screen size: a few hundred of them held
        over a gigabyte in a client kept open for days). Opening it again draws it anew,
        at the first unread. → False: it can't go now (on screen, or the lane in front)."""
        if self.isVisible():
            return False
        if self.win.stack.currentWidget() is self:
            return False  # the lane in front, only out of sight with the window: kept
        if not self.view.order:
            return True
        n = len(self.view.order)
        self.view.clear()
        self.positioned = False
        self.separator = None
        self.unloaded = True
        self.dirty = True
        log.info("lane %s unloaded: %d cards let go", self.name, n)
        diag.trim_soon("a lane unloaded")
        return True

    def refresh_now(self):
        self.core.refresh_by_hand()

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
        built = self.lm.build(self.positioned)
        specs = built.specs
        held_before, self._held = getattr(self, "_held", 0), built.held
        if self.filter_seg is not None or self.lm.media.active() or built.held or held_before:
            self.header.info.setText(built.info)  # "N new — Refresh shows them" (hold)
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
        empty = built.empty
        if empty and self.empty_note is None:
            # in the lane itself, big and wrapped: the header's info line is small and
            # gives way to the buttons
            self.empty_note = QLabel(_("browse_empty"))
            self.empty_note.setObjectName("emptyNote")
            self.empty_note.setWordWrap(True)
            self.empty_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
            f = self.empty_note.font()
            f.setPointSizeF(f.pointSizeF() * 1.25)
            self.empty_note.setFont(f)
            self.empty_note.setContentsMargins(24, 48, 24, 24)
            self.view.header.addWidget(self.empty_note)
        if self.empty_note is not None:
            self.empty_note.setVisible(empty)
        # a browse lane just opened (Federated, Local), its server not answered yet:
        # "loading…" with the opossum, not an empty lane
        waiting = bool(getattr(self.core, "lane_waiting", lambda _n: False)(self.name)) and \
            not any(s.entry is not None for s in specs)
        if waiting or getattr(self, "_waiting", False):
            self._waiting = waiting
            self.show_plate(waiting)
        log.debug("lane %s drawn: %d rows, %d unread, %.0f ms", self.name, len(specs),
                  built.unread, (time.monotonic() - t0) * 1000)

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
        if self.lm.read_on_open():  # read.mark_read (common/lane.py decides)
            QTimer.singleShot(0, self.mark_all_read)

    def _start_key(self, specs):
        """Where reading starts (as _initial_position goes there): the cards around it
        are the ones built first."""
        return self.lm.start_key(specs)

    def _initial_position(self):
        if self.positioned or not self.view.order or not self.view.isVisible():
            return
        self.positioned = True
        key, where = self.lm.start(self.view.model)
        if key is not None and self.view.has(key):
            self.view.scroll_to(key, where)
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
        if getattr(self.core.lane_by_name.get(self.name), "events", False):
            self.core.mark_activity_seen()  # its events seen too

    def capabilities_changed(self):
        """The server answered for a feature: "Clear" as it can now, the rows' × tips."""
        if self.clear_btn is not None:
            self.clear_btn.setVisible(self.core.supports("dismiss"))
        if getattr(self.core.lane_by_name.get(self.name), "events", False):
            self.refresh()

    def _clear(self):
        """Every notification gone, on the server too (a lane of events only)."""
        from PySide6.QtWidgets import QMessageBox
        if QMessageBox.question(self, _("activity_clear"), _("activity_clear_q")) \
                == QMessageBox.StandardButton.Yes:
            self.win.bridge.call(self.core.clear_activity(), fail=self.win.error)

    def load_older(self):
        self.btn_older.setEnabled(False)
        self.win.bridge.call(self.core.load_older(self.name),
                             ok=lambda n: self._older_done(n),
                             fail=lambda e: (self.btn_older.setEnabled(True), self.win.error(e)))

    def _older_in_sight(self, value):
        """Within a screen of the "older" end: ask the core (core.older_ahead decides —
        the setting, one at a time, none after an empty page)."""
        if not self.btn_older.isVisible() or not self.btn_older.isEnabled():
            return
        bar = self.view.verticalScrollBar()
        screen = self.view.viewport().height()
        near = value >= bar.maximum() - screen if self.newest_first else value <= screen
        if not near:
            return
        fut = self.core.older_ahead(self.name)
        if fut is not None:
            self.btn_older.setEnabled(False)
            self.btn_older.setText(_("loading"))
            self.win.bridge.call(fut, ok=self._older_done,
                                 fail=lambda e: self.btn_older.setEnabled(True))

    def _older_done(self, n):
        self.btn_older.setEnabled(True)
        self.btn_older.setText(_("no_older") if not n else
                               _("older_down") if self.newest_first else _("older_up"))

    def apply_read(self, ids):
        self.view.set_unread(ids, False)
        if self.isVisible():
            self.update_strip()

    def apply_seen(self, mark):
        """Events seen up to `mark` (one mark for every lane): their rows lose the unread
        mark in place — no lane rebuilt. Rebuilding every event lane at each mark froze
        the window while one read Activity by scrolling (28.10)."""
        keys = [k for k, sort in self.lm.event_sorts.items() if sort and sort <= mark]
        if keys:
            self.view.set_unread(keys, False)
        if self.isVisible():
            self.update_strip()

    def update_strip(self):
        # the store has the last word: a post marked read by any road (another lane,
        # a thread, another client) loses its mark here too, so "N new" never lies
        ids = [s.entry.id for s in self.view.model  # (a conversation card speaks for
               if s.unread and s.entry is not None and not str(s.key).startswith("conv:")]
        read = self.core.read_ids(ids)
        if read:
            self.view.set_unread(read, False)
        n = len(self.view.unread_keys())
        self.pill.setText(_("new_n", n=n))
        self.pill.setVisible(bool(n))
        # greyed, not hidden: buttons that come and go make the others jump about
        self.btn_all.setEnabled(bool(n))
        # nothing new: it still works — to the newest end of the lane
        self.btn_first.setToolTip(_("to_new_tip") if n else _("to_end_tip"))


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
    def __init__(self, win, sid, at="post"):
        super().__init__()
        self.win, self.core = win, win.ctx.view
        self.focus_id = sid
        self.at = at  # where it stands once loaded: the post, or "first_unread"
        self.items = []
        self.title = _("thread_loading")
        self.info_text = ""
        self.loaded = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.header = _Header(win.theme)
        self.root, self.posts = None, []
        self.sub_btn = self.header.add(_button(_("sub_thread"), self._toggle_sub,
                                               icon="subs", tip=_("sub_tip")))
        self.sub_btn.setCheckable(True)
        self.sub_btn.setEnabled(False)
        self.cw_open = False  # "open every CW": a thread with warnings only
        self.cw_btn = self.header.add(_button(_("cw_all_show"), self._all_cw,
                                              tip=_("cw_all_tip")))
        self.cw_btn.hide()
        self.header.add(_button("", self.reload, icon="refresh", tip=_("refresh")))
        lay.addWidget(self.header)
        self.view = FeedView(win.ctx)
        self.view.seen.connect(self._seen)
        lay.addWidget(self.view, 1)
        from .loading import LoadingPlate
        self.plate = LoadingPlate(_("thread_loading"), self)  # till the thread is drawn
        self.plate.hide()
        self.statuses = set()
        self.reload()

    def _plate(self, on, text=None):
        if text is not None:
            self.plate.setText(text)
        if on:
            self.plate.adjustSize()
            self.plate.move(max(0, (self.width() - self.plate.width()) // 2),
                            self.header.sizeHint().height() + 24)
            self.plate.raise_()
        self.plate.setVisible(on)

    def resizeEvent(self, e):  # noqa: N802 — the plate stays in the middle
        super().resizeEvent(e)
        if not self.plate.isHidden():
            self._plate(True)

    def showEvent(self, e):  # noqa: N802 — sized only now (a tab made before it's shown)
        super().showEvent(e)
        if not self.plate.isHidden():
            self._plate(True)

    def _seen(self, ids):
        from ..common.lane import seen_read
        ids = seen_read(self.core.cfg, ids)
        if ids:
            self.core.mark_read(ids)

    def reload(self, quiet=False):
        if not quiet:
            self.header.info.setText(_("loading"))
            if not self.loaded:  # nothing drawn yet: the plate, with the opossum
                self._plate(True, _("thread_loading"))

        def failed(e):
            self._plate(False)
            self.header.info.setText(_("load_failed", err=e))
        self.win.bridge.call(self.core.thread(self.focus_id), ok=self._loaded, fail=failed)

    def show_progress(self, step):
        """threads.thread_progress: the header says how fetching replies goes; once done
        (a few seconds later) it says the thread's own line again."""
        from ..common.progress import thread_words
        words = thread_words(step)
        if not self.loaded and words:  # still waiting ("remote"): the plate says how it goes
            self._plate(True, _("thread_loading") + " " + words)
        base = self.info_text if self.loaded else _("loading")
        self.header.info.setText(base + (" · " + words if words and base else words))
        if step and step.get("stage") in ("done", "failed"):
            QTimer.singleShot(8500, self, lambda: self.header.info.setText(self.info_text)
                              if self.loaded else None)

    def _all_cw(self):
        """Every content warning in the thread opened (or closed) at once."""
        self.cw_open = not self.cw_open
        self.cw_btn.setText(_("cw_all_hide") if self.cw_open else _("cw_all_show"))
        for row in self.view.rows.values():
            card = getattr(row, "card", row)
            set_cw = getattr(card, "set_cw", None) or getattr(row, "set_cw", None)
            if set_cw is not None:
                set_cw(self.cw_open)

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

    def _loaded(self, items):
        """items: [ThreadItem] in reading order, the root first."""
        self._plate(False)
        if not self.loaded:  # the first time: where it was asked to stand
            self.focus_id = self.core.thread_focus(self.focus_id, items, self.at)
        self.items = items
        posts = [n.post for n in items]
        self.statuses = {p.id for p in posts}
        unread = self.core.unread(posts)
        short = self.core.short_ids(posts)
        specs = [make_spec(self.core, n.post.id, n.post, depth=n.depth,
                           number=n.number or None, in_thread=True,
                           focus=(n.post.id == self.focus_id and len(items) > 1),
                           unread=n.post.id in unread,
                           extra={"short_id": short.get(n.post.id)}) for n in items]
        self.view.set_specs(specs, keep_position=self.loaded)
        root = posts[0] if posts else None
        self.root, self.posts = root, posts
        dock = getattr(self.win, "dock", None)
        if dock is not None and self.win.tabs.currentWidget() is self:
            dock.follow(self)  # the input line answers its newest post
        if root is None:
            return
        self.update_sub_button()
        self.cw_btn.setVisible(any(p.warning or p.filtered for p in posts))
        self.title = f"{root.author.username}: {snippet(root, 30)}"
        self.header.title.setText(snippet(root, 60))
        self.info_text = _("thread_info", n=len(items) - 1) + \
            (f" · #{short[root.id]}" if short.get(root.id) else "")
        self.header.info.setText(self.info_text)
        self._why_it_reaches_me(posts)
        self.win.retitle(self)
        if not self.loaded:
            self.loaded = True
            self.view.scroll_to(self.focus_id, "top")

    def _why_it_reaches_me(self, posts):
        """Not subscribed, yet the comments come? Say why: the server puts replies
        between people you follow into Home."""
        self.header.info.setToolTip("")
        if self.root is None or self.core.subscribed(self.root):
            return
        authors = [p.author for p in posts]

        def show(followed):
            if not followed or self.core.subscribed(self.root):
                return
            names = ", ".join("@" + a.handle.split("@")[0] for a in followed[:3])
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
        self.win, self.core = win, win.ctx.view
        self.title = title
        self.items = []  # Post | Share, newest first
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.header = _Header(win.theme, title)
        lay.addWidget(self.header)
        self.view = FeedView(win.ctx)
        lay.addWidget(self.view, 1)
        self.btn_more = _button(_("older_down"), self.more, name="older")
        self.view.footer.addWidget(self.btn_more)
        me = weakref.ref(self)  # weakly: the filter must not keep a closed tab alive
        self.media_filter = MediaFilter(self.header, lambda: me() and me().render())

    def shown(self, entries):
        """The posts the funnel lets through."""
        return [e for e in entries if self.media_filter.keeps(e)]

    def fetch(self, max_id):  # -> future with a page of statuses
        raise NotImplementedError

    def more(self):
        self.btn_more.setEnabled(False)
        max_id = self.items[-1].id if self.items else None
        self.win.bridge.call(self.fetch(max_id), ok=self._page,
                             fail=lambda e: (self.btn_more.setEnabled(True), self.win.error(e)))

    def _page(self, page):
        known = {e.id for e in self.items}
        self.items += [e for e in page if e.id not in known]
        self.btn_more.setEnabled(bool(page))
        if not page:
            self.btn_more.setText(_("no_older"))
        self.core.ensure_parents(page)
        self.render()

    def render(self):
        items = self.shown(self.items)
        short = self.core.short_ids(items)
        parents = self.core.parents(items)
        specs = [make_spec(self.core, e.id, e, parent=parents.get(e.id),
                           extra={"short_id": short.get(real_entry(e).id)})
                 for e in items]
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
        self.acc = None  # Account
        me = self.core.me
        self.mine = me is not None and acc_id == me.id
        if self.mine:
            self.header.add(_button(_("edit_profile"), win.edit_profile, icon="edit"))
        # who this is: a block of its own, not one more post — the banner, a tinted
        # card with an accent edge, and a "Posts" heading under it
        self.info = QFrame()
        self.info.setObjectName("profileCard")
        self.info.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.view.header.addWidget(self.info)
        self._info_layout = QVBoxLayout(self.info)
        self._info_layout.setContentsMargins(20, 16, 20, 18)
        self._info_layout.setSpacing(10)
        self.show = timed.profile_show(self.core.cfg)  # posts / all / media (the switch)
        self.view.header.addWidget(self._posts_heading())
        self.relation = Relationship()  # between me and them, as last heard
        self._first_page = None
        self._origin_asked = False
        self._older_origin = False  # my server's pages ran out: further back from theirs
        self._origin_next = None
        self._mine_done = False
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
        top = {e.id for e in self.pinned}
        rest = self.shown([e for e in self.items if e.id not in top and self._keeps(e)])
        pinned = self.shown(self.pinned)
        short = self.core.short_ids(pinned + rest)
        parents = self.core.parents(pinned + rest)
        specs = [make_spec(self.core, "pin:" + e.id, e, parent=parents.get(e.id),
                           extra={"short_id": short.get(real_entry(e).id), "pinned": True})
                 for e in pinned]
        specs += [make_spec(self.core, e.id, e, parent=parents.get(e.id),
                            extra={"short_id": short.get(real_entry(e).id)}) for e in rest]
        self.view.set_specs(specs, keep_position=True)

    def fetch(self, max_id):
        return self.core.account_posts(self.acc_id, max_id, show=self.show)

    # ---- posts / posts and replies / media ------------------------------------------
    def _posts_heading(self):
        """"Posts" and, beside it, which of them: three buttons, as other clients have."""
        from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QWidget
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        posts = QLabel(_("profile_posts"))
        posts.setObjectName("sectionTitle")
        lay.addWidget(posts)
        lay.addSpacing(12)
        self.show_group = QButtonGroup(row)
        self.show_buttons = {}
        for key, label in timed.profile_shows():
            b = _button(label, lambda _c=False, k=key: self.set_show(k),
                        tip=_("profile_show_tip"))
            b.setCheckable(True)
            b.setChecked(key == self.show)
            self.show_group.addButton(b)
            self.show_buttons[key] = b
            lay.addWidget(b)
        lay.addStretch(1)
        return row

    def set_show(self, show):
        """Another kind of posts: everything read again from the top."""
        self.show_buttons[show].setChecked(True)
        if show == self.show:
            return
        self.show = show
        self.items, self._first_page = [], None
        self._origin_asked = self._older_origin = self._mine_done = False
        self._origin_next = None
        self.btn_more.setText(_("older_down"))
        self.btn_more.setToolTip("")
        self.render()
        self.more()

    def _keeps(self, e):
        return timed.keeps(e, self.show, self.acc_id)

    def _page(self, page):
        if self._first_page is None:
            self._first_page = page
        super()._page(page)
        self._from_origin()
        if not page:
            self._mine_done = True
            self._offer_origin()

    def _remote_host(self):
        handle = self.acc.handle if self.acc else ""
        if "@" not in handle or not self.core.cfg["feed"].get("remote_profiles", True):
            return ""
        return handle.split("@", 1)[1]

    def _offer_origin(self):
        """My server has nothing older: the button now reads further back from their
        own server."""
        host = self._remote_host()
        if not host or self._older_origin:
            return
        self._older_origin = True
        self.btn_more.setText(_("older_from_origin", host=host))
        self.btn_more.setToolTip(_("older_from_origin_tip", host=host))
        self.btn_more.setEnabled(True)

    def more(self):
        if not self._older_origin:
            self.btn_more.setEnabled(False)
            max_id = self.items[-1].id if self.items else None
            want = self.show  # a page for a kind switched away from meanwhile: dropped
            self.win.bridge.call(self.fetch(max_id),
                                 ok=lambda page: want == self.show and self._page(page),
                                 fail=lambda e: (self.btn_more.setEnabled(True),
                                                 self.win.error(e)))
            return None
        host = self._remote_host()
        self.btn_more.setEnabled(False)
        self.btn_more.setText(_("origin_asking", host=host))
        have = [real_entry(e).uri for e in self.items if real_entry(e).uri]

        shown = [0]

        def listed(r):
            # the addresses come fast; my server fetching each post is the slow part
            # (seconds a post), so they come in a few at a time and show as they come
            uris, self._origin_next = r
            if not uris:
                return done()
            self.btn_more.setText(_("origin_fetching", n=0, total=len(uris), host=host))
            step(list(uris), len(uris))

        def step(left, total):
            batch, rest = left[:4], left[4:]

            def got(entries):
                known = {e.id for e in self.items}
                new = [e for e in entries if e.id not in known]
                shown[0] += len(new)
                if new:
                    self.items = sorted(self.items + new, key=lambda e: e.sort, reverse=True)
                    self.core.ensure_parents(new)
                    self.render()
                if rest:
                    self.btn_more.setText(_("origin_fetching", n=total - len(rest),
                                            total=total, host=host))
                    step(rest, total)
                else:
                    done()
            self.win.bridge.call(self.core.resolve_statuses(batch), ok=got, fail=failed)

        def done():
            if self._origin_next:
                self.btn_more.setText(_("older_from_origin", host=host))
                self.btn_more.setEnabled(True)
            else:
                self.btn_more.setText(_("no_older"))
            self.win.statusBar().showMessage(
                _("origin_got", n=shown[0], host=host) + " · " + _("older_from_origin_note"),
                8000)

        def failed(e):
            self.btn_more.setText(_("older_from_origin", host=host))
            self.btn_more.setEnabled(True)
            self.win.error(e)
        self.win.bridge.call(self.core.older_from_origin(self.acc, self._origin_next, have,
                                                         resolve=False),
                             ok=listed, fail=failed)

    def _from_origin(self):
        """Someone from another server mine knows little about (fewer posts here than
        their profile counts): read their newest from their own server."""
        acc, page = self.acc, self._first_page
        if self._origin_asked or acc is None or page is None or "@" not in acc.handle:
            return
        if not self.core.cfg["feed"].get("remote_profiles", True):
            return
        if len(page) >= min(acc.posts, self.core.cfg["feed"]["page_size"]):
            return  # my server has them
        self._origin_asked = True
        host = acc.handle.split("@", 1)[1]
        self.header.info.setText(self.header.info.text() + " · " +
                                 _("origin_asking", host=host))
        have = [real_entry(e).uri for e in self.items]

        def got(entries):
            known = {e.id for e in self.items}
            new = [e for e in entries if e.id not in known]
            self.items = sorted(self.items + new, key=lambda e: e.sort, reverse=True)
            info = self.header.info.text().replace(" · " + _("origin_asking", host=host), "")
            self.header.info.setText(info + (" · " + _("origin_got", n=len(new), host=host)
                                             if new else ""))
            if new:
                self.core.ensure_parents(new)
                self.render()
        self.win.bridge.call(self.core.posts_from_origin(acc, have), ok=got,
                             fail=lambda _e: None)

    def reload_account(self, tries=None):
        """Who this is, from the server: asked again when it fails, answers oddly or
        doesn't answer, and "Retry" in the head after the last try (common/patient.py,
        the same for every window; a tab stayed "@…" until a restart, 27.10)."""
        from ..common.patient import Patient
        if getattr(self, "_patient", None) is None:
            def say(text):
                self.header.info.setText(text)

            def give_up(text):
                self.header.info.setText(text)
                if getattr(self, "_retry_btn", None) is None:
                    def again(_c=False):
                        self._retry_btn.hide()
                        self._patient.again()
                    self._retry_btn = self.header.add(_button(_("profile_retry"), again))
                self._retry_btn.show()
                diag.dump_stacks(f"profile {self.acc_id}: the account doesn't come")
            self._patient = Patient(
                lambda: self.core.account(self.acc_id),
                lambda fut, ok, fail: self.win.bridge.call(fut, ok=ok, fail=fail),
                lambda sec, fn: QTimer.singleShot(int(sec * 1000), self, fn),
                ok=self._account, say=say, give_up=give_up,
                good=lambda acc: acc is not None and bool(getattr(acc, "handle", None)),
                what=f"profile {self.acc_id}")
        self._patient.start(tries)
        if not self.mine:
            self.win.bridge.call(self.core.relationship(self.acc_id), ok=self._relation)

    def show_info(self):
        """Clicking the name of the person whose tab this is: back to their card."""
        self.view.verticalScrollBar().setValue(0)
        _flash(self.info)

    def _relation(self, rel):
        self.relation = rel if isinstance(rel, Relationship) else Relationship()
        if self.acc:
            self._fill()

    def _account(self, acc):
        self.acc = acc
        if getattr(self, "_retry_btn", None) is not None:
            self._retry_btn.hide()
        self.title = "@" + acc.handle
        counts = " · ".join((_("posts_n", n=acc.posts), _("followers_n", n=acc.followers),
                             _("following_n", n=acc.following)))
        self.header.title.setText(acc.name or acc.username)
        self.header.info.setText(" · ".join(x for x in (f"@{acc.handle}", counts) if x))
        self.win.retitle(self)
        self._fill()
        self._from_origin()
        if not hasattr(self, "software"):  # what their server runs (feed.server_info)
            from urllib.parse import urlparse
            host = urlparse(acc.url or acc.uri).hostname or ""
            self.software = ""
            if host:
                self.win.bridge.call(self.core.server_software(host), ok=self._software,
                                     fail=lambda _e: None)
        if self._mine_done:  # the empty page came before who this is
            self._offer_origin()
        if not self.mine and self.core.supports("familiar"):
            self.win.bridge.call(self.core.familiar(self.acc_id), ok=self._familiar,
                                 fail=lambda _e: None)

    def _software(self, name):
        if name:
            self.software = name
            self._fill()

    def _familiar(self, accounts):
        self.familiar = accounts or []
        if self.familiar and self.acc:
            self._fill()

    def _fill(self):
        from .text import clean
        acc, lay, theme = self.acc, self._info_layout, self.win.theme
        rel = self.relation
        in_app = self.core.cfg["ui"]["links_in_app"]
        clear(lay)
        header = acc.header_static
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
        if acc.moved and self.core.cfg["feed"].get("show_moved", True):
            lay.addWidget(self._moved_banner(acc.moved))
        name = QLabel(esc(acc.name or acc.username))
        name.setObjectName("profileName")
        lay.addWidget(name)
        top = QHBoxLayout()
        top.setSpacing(14)
        avatar = QLabel()
        avatar.setFixedSize(72, 72)
        from .card import _round
        self.win.images.face(acc.avatar_static, 72,
                             lambda pm, w=avatar: w.setPixmap(_round(pm, 72)))
        top.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(6)
        bits = [f"@{esc(acc.handle)}"]
        if acc.bot:
            bits.append(_("bot"))
        if acc.locked:
            bits.append("🔒 " + _("acc_locked"))
        if acc.created:
            bits.append(_("acc_since", date=acc.created.strftime("%d.%m.%Y")))
        if rel.followed_by:
            bits.append("<b>" + _("acc_follows_you") + "</b>")
        if getattr(self, "software", ""):
            bits.append("🖥 " + esc(self.software))
        since = rel.following and self.core.followed_since(acc.id, rel)
        if since:
            bits.append(esc(_("acc_followed_since", when=self.win.theme.date(since))))
        meta = QLabel(" · ".join(bits))
        meta.setObjectName("muted")
        meta.setTextFormat(Qt.TextFormat.RichText)
        col.addWidget(meta)
        note = self.core.in_app_html(acc.note) if in_app else acc.note
        bio = QLabel(clean(note, theme.css("link")))
        bio.setTextFormat(Qt.TextFormat.RichText)
        bio.setWordWrap(True)
        bio.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        bio.linkActivated.connect(self.win.on_link)
        col.addWidget(bio)
        for f in acc.fields:
            value = self.core.in_app_html(f.value) if in_app else f.value
            row = QLabel(f'<b>{esc(f.name)}</b>: {clean(value, theme.css("link"))}'
                         + (" ✓" if f.verified else ""))
            row.setTextFormat(Qt.TextFormat.RichText)
            row.setWordWrap(True)
            row.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            row.linkActivated.connect(self.win.on_link)
            col.addWidget(row)
        from .text import link
        tags = [link("tag", t.name, "#" + esc(t.name), theme.css("link"))
                + (f" <small>({int(t.posts)})</small>" if t.posts else "")
                for t in self.featured.get("tags") or [] if t.name]
        people = [link("account", a.id, "@" + esc(a.handle), theme.css("link"))
                  for a in self.featured.get("people") or [] if a.id]
        known = [link("account", a.id, "@" + esc(a.handle), theme.css("link"))
                 for a in self.familiar[:5] if a.id]
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

        from ..common import profile as prof
        from .flow import FlowLayout
        buttons = FlowLayout(spacing=8)  # too many for one line: they wrap, not shrink
        # the buttons are common/profile.py's — the same in GTK, the terminal and the web;
        # what they do too (prof.do through the window's link host), but for the private
        # note (several lines here) and the lists (a menu on the button)
        for act in prof.actions(acc, rel, self.mine, self.core.cfg, self.core.supports,
                                lists=self.win.ctx.fill_list_menu is not None,
                                collections=True):
            if act.key == "edit_profile":
                continue  # in the header already
            name = "primary" if act.primary else "tool"
            if act.key == "lists":
                from PySide6.QtWidgets import QMenu
                lb = _button(act.label, lambda: None)
                menu = QMenu(lb)
                menu.aboutToShow.connect(lambda m=menu: self.win.ctx.fill_list_menu(m, acc))
                lb.setMenu(menu)
                buttons.addWidget(lb)
                continue
            if act.key == "note":
                fn = self.edit_note
            else:
                fn = (lambda _c=False, k=act.key: prof.do(
                    k, self.acc, self.relation, self.win.ctx.view, self.win.links.host,
                    self._button_done))
            buttons.addWidget(_button(act.label, fn, name=name, tip=act.tip or None))
        lay.addLayout(buttons)
        from ...model.text import note_text
        note = note_text(rel.note).strip()
        if note and not self.mine:
            label = QLabel("📝 " + esc(note).replace("\n", "<br>"))
            label.setObjectName("muted")
            label.setWordWrap(True)
            label.setToolTip(_("note_tip"))
            lay.addWidget(label)

    def _button_done(self, rel):
        """A profile button done (common/profile.py): the relation as it is now."""
        if isinstance(rel, Relationship):
            self._relation(rel)
        else:
            self.reload_account()

    def edit_note(self):
        """My private note on this person — only I see it, on my server."""
        from PySide6.QtWidgets import QInputDialog

        from ...model.text import note_text
        old = self.relation.note
        text, ok = QInputDialog.getMultiLineText(self, _("note_title", acct=self.acc.handle),
                                                 _("note_tip"), note_text(old))
        if ok:
            self.win.bridge.call(self.core.set_note(self.acc_id, text.strip(), old),
                                 ok=lambda r: self._relation(
                                     r if isinstance(r, Relationship) else self.relation),
                                 fail=self.win.error)

    def _moved_banner(self, new):
        """The account moved: where to, with "open" and "follow there"."""
        box = QFrame()
        box.setObjectName("card")
        h = QHBoxLayout(box)
        h.setContentsMargins(12, 8, 12, 8)
        text = QLabel(_("moved_to", acct="@" + esc(new.handle)))
        text.setTextFormat(Qt.TextFormat.RichText)
        text.setWordWrap(True)
        h.addWidget(text, 1)
        h.addWidget(_button(_("moved_open"), lambda: self.win.open_account(new.id)))
        if self.relation.following:
            h.addWidget(_button(_("moved_follow"), lambda: self.win.bridge.call(
                self.core.follow(new.id), ok=lambda _r: self.win.statusBar().showMessage(
                    _("followed_now", acct="@" + new.handle), 6000),
                fail=self.win.error), name="primary"))
        return box


class TagGroupWidget(_PagedTab):
    """Several hashtags at once — any of them, "+" ones all, "-" ones none (typed into
    the search); "＋ to lanes" keeps it in the sidebar, group "Tags"."""

    def __init__(self, win, spec):
        from ...core import taggroups
        self.spec = taggroups.normal(spec)
        self.key = taggroups.key(self.spec)
        super().__init__(win, self.key)
        self.header.info.setText(_("tags_info"))
        lane = taggroups.lane_name(self.spec)
        if lane not in self.core.lane_by_name:
            self.save_btn = self.header.add(_button(_("tags_save"), self._save,
                                                    tip=_("tags_save_tip")))
        self.more()

    def fetch(self, max_id):
        return self.core.tag_group_timeline(self.spec, max_id)

    def _save(self):
        self.save_btn.setEnabled(False)

        def done(name):
            self.save_btn.hide()
            self.win.statusBar().showMessage(_("tags_saved", tags=self.key), 6000)
            QTimer.singleShot(300, self, lambda: self.win.select_lane(name))
        self.win.bridge.call(self.core.save_tag_group(self.spec), ok=done,
                             fail=lambda e: (self.save_btn.setEnabled(True), self.win.error(e)))


class TagWidget(_PagedTab):
    """Posts with a hashtag, as your server knows them — or, with `by`, as one author
    writes it (a click on a tag in their post, feed.tag_click = "author": Point's tags
    are each blog's own), "#tag everywhere" on top."""

    def __init__(self, win, tag, by=None):
        super().__init__(win, "#" + tag)
        self.tag, self.by = tag, by
        self.header.info.setText(_("tag_by_author_line") if by else _("tag_info"))
        if by:
            self.header.add(_button(_("tag_everywhere"), lambda: win.open_tag(tag),
                                    tip=_("tag_everywhere_tip")))
            self.header.add(_button(_("tui_profile"), lambda: win.open_account(by)))
            win.bridge.call(self.core.account(by), ok=self._author, fail=lambda _e: None)
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
        # one tag kept as a lane of its own, in the sidebar's "Tags" (as a group of them)
        self.header.add(tag_lanes_button(win, tag))
        # muted in one click: into the server's filter of muted hashtags (Core.mute_tag)
        self.mute_btn = self.header.add(_button("", self._toggle_mute, tip=_("tag_mute_tip")))
        self._show_mute()
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

    def _show_mute(self):
        self.mute_btn.setText(_("tag_unmute_btn") if self.core.tag_muted(self.tag)
                              else _("tag_mute_btn"))

    def _toggle_mute(self):
        on = not self.core.tag_muted(self.tag)
        self.mute_btn.setEnabled(False)
        self.win.bridge.call(
            self.core.mute_tag(self.tag, on),
            ok=lambda _r: (self.mute_btn.setEnabled(True), self._show_mute(),
                           self.win.statusBar().showMessage(
                               _("tag_muted_msg" if on else "tag_unmuted_msg", tag=self.tag),
                               6000)),
            fail=lambda e: (self.mute_btn.setEnabled(True), self.win.error(e)))

    def _info(self, t):
        self.following = bool(t and t.following)
        self.follow_btn.setText(_("tag_unfollow") if self.following else _("tag_follow"))

    def _toggle_follow(self):
        self.win.bridge.call(self.core.follow_tag(self.tag, not self.following), ok=self._info,
                             fail=self.win.error)

    def _author(self, acc):
        if acc is not None:
            self.title = f"#{self.tag} · @{acc.handle}"
            self.header.title.setText(self.title)
            self.win.retitle(self)

    def fetch(self, max_id):
        if self.by:
            return self.core.account_posts(self.by, max_id, show="tag:" + self.tag)
        return self.core.tag_timeline(self.tag, max_id)




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


# the Activity lane's words and grouping are shared with GTK (common/activity.py)
_notice_text = activity.notice_text


class AccountRow(QFrame):
    """A person in a list (search results, followers): face, name, a line of
    bio, and a Follow button that knows the current state. acc: an Account,
    relation: a Relationship (or None: not known)."""

    def __init__(self, win, acc, relation=None):
        super().__init__()
        self.win, self.core, self.acc = win, win.ctx.view, acc
        self.relation = relation if isinstance(relation, Relationship) else Relationship()
        self.setObjectName("card")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 14, 10)
        h.setSpacing(12)
        avatar = QLabel()
        avatar.setFixedSize(40, 40)
        from .card import _round
        win.images.face(acc.avatar_static, 40, lambda pm, w=avatar: w.setPixmap(_round(pm, 40)))
        h.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        name = QLabel(f'<a href="fedtail:account/{esc(acc.id)}" style="text-decoration:none;'
                      f'color:{win.theme.c["text"].name()};"><b>{display_name(acc)}</b></a>'
                      f' <span style="color:{win.theme.c["muted"].name()};">@{esc(acc.handle)}'
                      f'{" · " + _("bot") if acc.bot else ""}</span>')
        name.setTextFormat(Qt.TextFormat.RichText)
        name.linkActivated.connect(win.on_link)
        col.addWidget(name)
        note = snippet_html(acc.note, 160)
        if note:
            bio = QLabel(esc(note))
            bio.setObjectName("muted")
            bio.setWordWrap(True)
            col.addWidget(bio)
        counts = " · ".join((_("posts_n", n=acc.posts), _("followers_n", n=acc.followers)))
        if counts or self.relation.followed_by:
            extra = QLabel(counts + (" · <b>" + _("acc_follows_you") + "</b>"
                                     if self.relation.followed_by else ""))
            extra.setObjectName("muted")
            extra.setTextFormat(Qt.TextFormat.RichText)
            col.addWidget(extra)
        h.addLayout(col, 1)
        self.btn = None
        me = self.core.me
        if me is None or acc.id != me.id:
            self.btn = _button("", self._toggle)
            h.addWidget(self.btn, 0, Qt.AlignmentFlag.AlignTop)
            self._paint()

    def _paint(self):
        r = self.relation
        self.btn.setText(_("unfollow") if r.following else
                         _("follow_requested") if r.requested else _("follow"))
        self.btn.setObjectName("tool" if r.following or r.requested else "primary")
        self.btn.style().unpolish(self.btn)
        self.btn.style().polish(self.btn)

    def _toggle(self):
        on = not (self.relation.following or self.relation.requested)
        self.btn.setEnabled(False)

        def done(rel):
            self.relation = rel if isinstance(rel, Relationship) else Relationship()
            self.btn.setEnabled(True)
            self._paint()
        self.win.bridge.call(self.core.follow(self.acc.id, on), ok=done,
                             fail=lambda e: (self.btn.setEnabled(True), self.win.error(e)))


def tag_lanes_button(win, tag):
    """"＋ to lanes ▾" beside a tag's Follow: a lane of its own, or into a lane of tags
    kept in the sidebar (common/taglanes.py)."""
    from PySide6.QtWidgets import QMenu

    from ..common import taglanes
    view = win.ctx.view
    b = _button(_("tags_lanes_menu"), lambda: None, tip=_("tags_lanes_tip"))
    menu = QMenu(b)

    def fill():
        menu.clear()
        for key, words, on in taglanes.choices(view, tag):
            act = menu.addAction(words)
            act.setEnabled(on)
            act.triggered.connect(lambda _c=False, k=key, w=words: go(k, w))
    menu.aboutToShow.connect(fill)
    b.setMenu(menu)

    def go(key, words):
        def done(name):
            title = view.lane_title(name) or name
            win.statusBar().showMessage(
                _("tags_saved", tags="#" + tag) if key == taglanes.OWN
                else _("tags_added", tag=tag, lane=title), 6000)
            QTimer.singleShot(300, win, lambda: win.select_lane(name))
        win.bridge.call(taglanes.apply(view, key, tag), ok=done, fail=win.error)
    return b


class TagRow(QFrame):
    """#tag with how many people used it lately, Follow tag, and a click to open it.
    tag: a Tag."""

    def __init__(self, win, tag):
        super().__init__()
        self.win, self.core, self.tag = win, win.ctx.view, tag
        self.setObjectName("card")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 8, 14, 8)
        people = tag.people
        label = QLabel(f'<a href="fedtail:tag/{esc(tag.name)}" style="text-decoration:none;'
                       f'color:{win.theme.c["link"].name()};"><b>#{esc(tag.name)}</b></a>'
                       + (f' <span style="color:{win.theme.c["muted"].name()};">· '
                          f'{_("tag_people", n=people)}</span>' if people else ""))
        label.setTextFormat(Qt.TextFormat.RichText)
        label.linkActivated.connect(win.on_link)
        h.addWidget(label, 1)
        self.btn = _button("", self._toggle)
        h.addWidget(self.btn)
        h.addWidget(tag_lanes_button(win, tag.name))  # into the sidebar's Tags
        self._paint()

    def _paint(self):
        on = bool(self.tag.following)
        self.btn.setText(_("tag_unfollow") if on else _("tag_follow"))
        self.btn.setToolTip(_("tag_follow_tip"))

    def _toggle(self):
        on = not self.tag.following
        self.btn.setEnabled(False)

        def done(t):
            now = t.following if t is not None and t.following is not None else on
            self.tag = replace(self.tag, following=now)
            self.btn.setEnabled(True)
            self._paint()
        self.win.bridge.call(self.core.follow_tag(self.tag.name, on), ok=done,
                             fail=lambda e: (self.btn.setEnabled(True), self.win.error(e)))


class SearchWidget(QWidget):
    """Finding new sources: people (by name, @user@server or a profile link),
    hashtags and posts, with Follow right there. With an empty query it shows the
    tags you follow."""

    def __init__(self, win, query=""):
        super().__init__()
        self.win, self.core = win, win.ctx.view
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
        self.edit.installEventFilter(self)
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

    def eventFilter(self, obj, e):
        """Enter in the search field searches and stops there: a line edit lets the key
        go on to its parents, and up there Enter means other things (open a post, go
        back to the lane)."""
        if obj is self.edit and e.type() == QEvent.Type.KeyPress and \
                e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.run(self.edit.text())
            return True
        return super().eventFilter(obj, e)

    def _section(self, text):
        lab = QLabel(text)
        lab.setObjectName("listsHeader")
        self.box_lay.addWidget(lab)

    def run(self, query):
        query = query.strip()
        from ...core import taggroups
        spec = taggroups.parse(query)
        if spec:  # several tags: a lane of them, not a search
            self.win.open_tag_group(spec)
            return
        clear(self.box_lay)
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
                self.box_lay.addWidget(AccountRow(self.win, a, res["relations"].get(a.id)))
        if tags:
            self._section(_("search_tags"))
            for t in tags:
                self.box_lay.addWidget(TagRow(self.win, t))
        if sts:
            self._section(_("search_posts"))
            short = self.core.short_ids(sts)
            parents = self.core.parents(sts)
            self.view.set_specs([make_spec(self.core, e.id, e, parent=parents.get(e.id),
                                           extra={"short_id": short.get(real_entry(e).id)})
                                 for e in sts], keep_position=False)

    def apply_read(self, ids):
        pass


class PeopleWidget(QWidget):
    """Whom someone follows, or who follows them — a way to find people through
    people you know. Each with a Follow button."""

    def __init__(self, win, acc, which):
        super().__init__()
        self.win, self.core, self.acc, self.which = win, win.ctx.view, acc, which
        self.acc_id = acc.id
        self.title = _("people_" + which, acct=acc.handle)
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
            self.box_lay.addWidget(AccountRow(self.win, a, res["relations"].get(a.id)))
        self.count += len(res["accounts"])
        self.header.info.setText(_("people_shown", n=self.count))
        self.next = nxt
        self.shown_ids = getattr(self, "shown_ids", set()) | {a.id for a in res["accounts"]}
        if res.get("total") is not None:
            self.header.info.setText(_("people_shown", n=self.count) + " · " +
                                     _("people_origin_total", n=res["total"]))
        self.btn_more.setEnabled(bool(nxt))
        if nxt:
            return
        host = self.acc.handle.split("@", 1)[1] if "@" in self.acc.handle else ""
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
