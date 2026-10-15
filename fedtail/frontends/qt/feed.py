"""Scrollable lists of posts: lanes, threads, accounts; plus follow requests.

The one rule here: nothing moves under the reader. Every update keeps the
first visible post at the same place on screen, and images reserve their
space before they load.
"""

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core.model import real, snippet
from ...i18n import _
from .card import CardSpec, PostRow, SeparatorRow
from .text import display_name, esc

POSTS_ONLY_LANES = ("people", "bots", "mine", "local")


class FeedView(QScrollArea):
    seen = Signal(list)  # status ids the reader has actually seen

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.setObjectName("feed")
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
        self.rows = {}
        self.order = []
        self._seen_timer = QTimer(self, singleShot=True, interval=350)
        self._seen_timer.timeout.connect(self._emit_seen)
        sb = self.verticalScrollBar()
        sb.valueChanged.connect(lambda _v: self._seen_timer.start())
        # Word-wrapped posts get their real height only after Qt lays them out,
        # sometimes several passes later. So "where to stand" is kept as a target
        # and re-applied every time the scroll range changes, until the reader
        # touches the scroll or things have been quiet for a while.
        self._target = None
        self._target_timer = QTimer(self, singleShot=True, interval=1500)
        self._target_timer.timeout.connect(self._drop_target)
        sb.rangeChanged.connect(lambda *_: self._apply_target())
        sb.actionTriggered.connect(lambda _a: self._drop_target())

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
        self._drop_target()
        super().wheelEvent(e)

    def keyPressEvent(self, e):
        self._drop_target()
        super().keyPressEvent(e)

    # ---- content ------------------------------------------------------------------
    def set_specs(self, specs, keep_position=True):
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
        if key in self.rows:
            self._set_target(("row", key, where))

    def scroll_to_end(self, end=True):
        self._set_target(("end", end))

    def set_unread(self, status_ids, unread=False):
        ids = set(status_ids)
        for row in self.rows.values():
            if row.status_id in ids:
                row.set_unread(unread)

    def refresh_from_store(self, store):
        for row in self.rows.values():
            if row.status_id is None:
                continue
            fresh = store.get_status(row.status_id)
            if fresh and fresh != row.spec.status:
                row.update_spec(CardSpec(**{**row.spec.__dict__, "status": fresh}))

    def remove_status(self, sid):
        rows = [self.rows[k] for k in self.order]
        keep = [r.spec for r in rows if r.status_id is None or
                (r.real_id != sid and r.status_id != sid)]
        if len(keep) != len(self.order):
            self.set_specs(keep)

    def unread_keys(self):
        return [k for k in self.order if self.rows[k].spec.unread]

    # ---- what the reader saw --------------------------------------------------------
    def _emit_seen(self):
        if not self.isVisible() or not self.window().isActiveWindow():
            return
        if self._target is not None:
            return  # still settling: what's on screen now is not what the reader sees
        sb = self.verticalScrollBar()
        vtop, vh = sb.value(), self.viewport().height()
        vbot = vtop + vh
        at_end = sb.value() >= sb.maximum()
        ids = []
        for key in self.order:
            row = self.rows[key]
            if not row.spec.unread:
                continue
            top = self._top(row)
            bottom = top + row.height()
            fully = top >= vtop - 2 and bottom <= vbot + 2
            tall_and_done = row.height() > vh and bottom <= vbot + 2 and bottom > vtop
            tail = at_end and top < vbot and bottom > vtop
            if fully or tall_and_done or tail:
                ids.append(row.status_id)
        if ids:
            self.seen.emit(ids)

    def showEvent(self, e):
        super().showEvent(e)
        self._seen_timer.start()


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
    b.clicked.connect(slot)
    return b


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
        self.title = QLabel(title)
        self.title.setObjectName("laneTitle")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.h.addWidget(self.title)
        self.info = QLabel()
        self.info.setObjectName("laneInfo")
        self.info.setTextFormat(Qt.TextFormat.PlainText)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.h.addWidget(self.info, 1)

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
        self.separator = None  # (key of the first unread when the lane opened, count)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.header = _Header(self.theme, self.theme.word("lane_title", _("lane_" + name)))
        self.pill = QLabel()
        self.pill.setObjectName("newPill")
        self.header.h.insertWidget(1, self.pill)
        self.only_posts = None
        if name in POSTS_ONLY_LANES:
            self._posts_only_control()
        self.btn_first = self.header.add(_button(_("to_new"), self.jump_first_unread,
                                                 icon="go-down"))
        self.btn_all = self.header.add(_button(_("mark_all_read"), self.mark_all_read,
                                               icon="mail-mark-read"))
        self.header.add(_button("", self.refresh_now, icon="view-refresh",
                                tip=_("refresh") + " (F5)"))
        lay.addWidget(self.header)
        self.view = FeedView(win.ctx)
        self.view.seen.connect(self._seen)
        lay.addWidget(self.view, 1)
        self.btn_older = _button(_("older_down") if self.newest_first else _("older_up"),
                                 self.load_older, name="older")
        (self.view.footer if self.newest_first else self.view.header).addWidget(self.btn_older)

    def _posts_only_control(self):
        on = self.core.posts_only(self.name)
        if self.theme.shape["posts_only"] == "check":
            box = QCheckBox(self.theme.word("lane", _("posts_only")).strip())
            box.setObjectName("check")
            box.setChecked(on)
            box.setToolTip(_("posts_only_tip"))
            box.toggled.connect(self._toggle_posts_only)
            self.only_posts = box
            self.header.add(box)
            return
        group = QWidget()
        g = QHBoxLayout(group)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(0)
        self._seg_all = QPushButton(_("show_all"))
        self._seg_posts = QPushButton(_("posts_only"))
        for b, pos in ((self._seg_all, "first"), (self._seg_posts, "last")):
            b.setObjectName("seg")
            b.setProperty("pos", pos)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            g.addWidget(b)
        self._seg_posts.setToolTip(_("posts_only_tip"))
        (self._seg_posts if on else self._seg_all).setChecked(True)
        self._seg_all.clicked.connect(lambda: self._set_seg(False))
        self._seg_posts.clicked.connect(lambda: self._set_seg(True))
        self.only_posts = _SegProxy(self)
        self.header.add(group)

    def _set_seg(self, on):
        self._seg_all.setChecked(not on)
        self._seg_posts.setChecked(on)
        if on != self.core.posts_only(self.name):
            self._toggle_posts_only(on)

    def _seen(self, ids):
        if self.cfg["read"]["mark_read"] == "on_scroll":
            self.core.mark_read(ids)

    def _toggle_posts_only(self, on):
        self.core.set_posts_only(self.name, on)
        self.positioned = False  # a different list: start over at the first unread
        self.separator = None
        self.refresh(force=True)
        self._initial_position()
        self.win.update_badges()

    def refresh_now(self):
        self.core.poll_now()

    def refresh(self, force=False):
        # hidden lanes only remember that they are stale; they catch up when shown
        if not self.isVisible() and not force and self.positioned:
            self.dirty = True
            return
        self.dirty = False
        entries = self.core.lane_entries(self.name)
        unread = self.core.unread_ids(entries)
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
        if self.name in ("comments", "mentions"):
            self.core.check_my_replies(statuses)
        if unknown:
            self.core.ensure_parents(unknown)
        # "new below": fixed where the reader stood when the lane opened
        if self.separator is None and not self.positioned:
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
            self.view.set_specs(specs, keep_position=False)
            if self.isVisible():
                self._initial_position()
        else:
            jump = self.cfg["feed"]["on_new"] == "jump_to_newest"
            had = set(self.view.order)
            self.view.set_specs(specs, keep_position=True)
            if jump and any(s.key not in had for s in specs):
                self.view.scroll_to_end(not self.newest_first)
        self.update_strip()

    def showEvent(self, e):
        super().showEvent(e)
        if self.dirty:
            self.refresh()
        if not self.positioned:
            QTimer.singleShot(0, self._initial_position)
        if self.cfg["read"]["mark_read"] == "on_open":
            QTimer.singleShot(0, self.mark_all_read)

    def _initial_position(self):
        if self.positioned or not self.view.order:
            return
        self.positioned = True
        unread = self.view.unread_keys()
        if self.cfg["feed"]["start_at"] == "first_unread" and unread:
            if self.newest_first:
                self.view.scroll_to(unread[-1], "bottom")
            elif "__sep__" in self.view.rows:
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
        ids = [self.view.rows[k].status_id for k in self.view.unread_keys()]
        self.core.mark_read(ids)

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
        n = len(self.view.unread_keys())
        self.pill.setText(_("new_n", n=n))
        self.pill.setVisible(bool(n))
        self.btn_all.setVisible(bool(n))


class _SegProxy:
    """Lets tests and the window treat the segmented control like a checkbox."""

    def __init__(self, lane):
        self.lane = lane

    def isChecked(self):
        return self.lane._seg_posts.isChecked()

    def setChecked(self, on):
        self.lane._set_seg(on)


class ThreadWidget(QWidget):
    def __init__(self, win, sid):
        super().__init__()
        self.win, self.core = win, win.core
        self.focus_id = sid
        self.title = _("thread_loading")
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

    def reload(self):
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
        self.header.info.setText(_("thread_info", n=len(nodes) - 1) +
                                 (f" · #{short[root['id']]}" if short.get(root["id"]) else ""))
        self.win.retitle(self)
        if not self.loaded:
            self.loaded = True
            self.view.scroll_to(self.focus_id, "top")

    def apply_read(self, ids):
        self.view.set_unread(ids, False)


class AccountWidget(QWidget):
    def __init__(self, win, acc_id):
        super().__init__()
        self.win, self.core = win, win.core
        self.acc_id = acc_id
        self.title = "@…"
        self.items = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.header = _Header(win.theme, "@…")
        lay.addWidget(self.header)
        self.view = FeedView(win.ctx)
        lay.addWidget(self.view, 1)
        self.btn_more = _button(_("older_down"), self.more, name="older")
        self.view.footer.addWidget(self.btn_more)
        win.bridge.call(self.core.account(acc_id), ok=self._account)
        self.more()

    def _account(self, acc):
        self.title = "@" + acc["acct"]
        note = snippet({"content": acc.get("note", "")}, 200)
        self.header.title.setText(acc.get("display_name") or acc["username"])
        self.header.info.setText(f"@{acc['acct']} — {note}" if note else f"@{acc['acct']}")
        self.win.retitle(self)

    def more(self):
        self.btn_more.setEnabled(False)
        max_id = self.items[-1]["id"] if self.items else None
        self.win.bridge.call(self.core.account_statuses(self.acc_id, max_id), ok=self._page,
                             fail=lambda e: (self.btn_more.setEnabled(True), self.win.error(e)))

    def _page(self, page):
        self.items += page
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
