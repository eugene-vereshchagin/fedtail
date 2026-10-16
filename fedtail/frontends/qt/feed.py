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
        self.header = _Header(self.theme, self.theme.word("lane_title", win.lane_title(name)))
        self.pill = QLabel()
        self.pill.setObjectName("newPill")
        self.header.h.insertWidget(1, self.pill)
        self.only_posts = None
        if name in POSTS_ONLY_LANES or name.startswith("list:"):
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
        # browse lanes (local, federated) have nothing "unread": no marks, no divider
        lazy = getattr(self.core.lane_by_name.get(self.name), "lazy", False)
        unread = set() if lazy else self.core.unread_ids(entries)
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
        self.info = QFrame()
        self.info.setObjectName("card")
        self.view.header.addWidget(self.info)
        self._info_layout = QVBoxLayout(self.info)
        self._info_layout.setContentsMargins(18, 14, 18, 14)
        self._info_layout.setSpacing(8)
        self.relation = {}
        self.reload_account()
        self.more()

    def fetch(self, max_id):
        return self.core.account_statuses(self.acc_id, max_id)

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
        top.addLayout(col, 1)
        lay.addLayout(top)

        buttons = QHBoxLayout()
        if not self.mine:
            following = self.relation.get("following")
            requested = self.relation.get("requested")
            label = _("unfollow") if following else \
                (_("follow_requested") if requested else _("follow"))
            fb = _button(label, self._toggle_follow, name="primary" if not following else "tool")
            buttons.addWidget(fb)
            buttons.addWidget(_button(_("mention"), lambda: self.win.compose(
                text=f"@{acc['acct']} ")))
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
        buttons.addWidget(_button(_("open_browser"), lambda: self.win.open_url(acc.get("url"))))
        buttons.addStretch(1)
        lay.addLayout(buttons)

    def _toggle_follow(self):
        on = not (self.relation.get("following") or self.relation.get("requested"))
        self.win.bridge.call(self.core.follow(self.acc_id, on), ok=self._relation)


class TagWidget(_PagedTab):
    """Posts with a hashtag, as your server knows them."""

    def __init__(self, win, tag):
        super().__init__(win, "#" + tag)
        self.tag = tag
        self.header.info.setText(_("tag_info"))
        self.follow_btn = self.header.add(_button(_("tag_follow"), self._toggle_follow))
        self.follow_btn.setToolTip(_("tag_follow_tip"))
        self.following = False
        win.bridge.call(self.core.tag_info(tag), ok=self._info, fail=lambda _e: None)
        self.more()

    def _info(self, t):
        self.following = bool((t or {}).get("following"))
        self.follow_btn.setText(_("tag_unfollow") if self.following else _("tag_follow"))

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
        self.btn_more.setEnabled(bool(nxt))
        if not nxt:
            self.btn_more.setText(_("no_older"))

    def apply_read(self, ids):
        pass
