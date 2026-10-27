"""Main window: lanes on the left, tabs (lane / threads / accounts) on the right."""

import logging
import sys
import time
from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QGuiApplication,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QTabBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ... import diag, version
from ...core import lanes as lanes_module
from ...i18n import _
from ...model import Account, Post, Relationship, Share
from ...model import real as real_entry
from ...model.text import snippet
from .. import iconpack, themefile
from ..common import results, sidebar
from ..common.links import Links
from ..common.sound import Sounds
from . import badge
from . import card as card_module
from . import feed as feed_module
from .announce import AnnounceBar
from .card import _round
from .cmdline import CommandBar
from .compose import Compose, media_paths, save_image
from .feed import (
    AccountWidget,
    ActivityWidget,
    LaneWidget,
    PeopleWidget,
    RequestsWidget,
    SearchWidget,
    TagGroupWidget,
    TagWidget,
    ThreadWidget,
)
from .find import FindBar
from .hints import HintMode
from .images import Images
from .login import LoginDialog
from .notify import Notifier, icon_path
from .opener import open_path
from .profile import ProfileDialog
from .silence import SilenceDialog
from .social import (
    AccountsWidget,
    LinkPostsWidget,
    QuotesWidget,
    RemoteLaneWidget,
    ServerInfoDialog,
    TrendsWidget,
)
from .viewer import ImageOverlay

log = logging.getLogger(__name__)
_AVATAR_CORNERS = {"circle": -1, "square": 0, "rounded": 6}  # shape.avatar_shape → px

# icons from the desktop theme (Breeze names); emoji are missing from many fonts

BADGE_KIND = {"replies": "hot", "to_me": "hot", "bots": "quiet", "activity": "quiet"}



def _tags_key(g):
    from ...core import taggroups
    return taggroups.key(g)


def pop_menu(menu, btn, above=False):
    """A menu from a button: under it, or above it (buttons at a window's bottom, as
    the roster's), its left edge at the button's."""
    y = -menu.sizeHint().height() if above else btn.height()
    menu.exec(btn.mapToGlobal(QPoint(0, y)))


def list_open(rel, inside):
    """May the "add to list" ticks be used: someone I follow (or asked to), or already
    in a list (taking out is always fine). Not yet known (None): no."""
    if inside:
        return True
    return rel is not None and bool(rel.following or rel.requested)

class LaneItem(QWidget):
    """A lane in the sidebar: icon, name, unread badge."""

    def __init__(self, name, theme, number, title=None, icon=None):
        super().__init__()
        self.name, self.theme = name, theme
        self.title = title or _("lane_" + name)
        self.current = False
        tip = _("tip_" + name) if not name.startswith("list:") else ""
        tip = "" if tip == "tip_" + name else tip
        tip = " ".join(x for x in (tip, f"(Alt+{number})" if number <= 9 else "") if x)
        if name in lanes_module.LANES:  # the word to find it by in the config
            tip = "\n".join(x for x in (tip, _("lane_codeword", name=name)) if x)
        self.setToolTip(tip)
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(10)
        from . import icons as pictures
        if pictures.pictures(theme):
            icon = QLabel()
            px = int(theme.shape.get("icon_size", 18) or 18)
            ic = pictures.icon(iconpack.lane_picture(name, icon), theme, px)
            if not ic.isNull():
                icon.setPixmap(ic.pixmap(px, px))
            icon.setFixedWidth(px)
            h.addWidget(icon)
        self.label = QLabel()
        self.label.setObjectName("laneName")
        h.addWidget(self.label, 1)
        self.badge = QLabel()
        self.badge.setObjectName("badge")
        self.badge.setProperty("kind", BADGE_KIND.get(name, "normal"))
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setMinimumWidth(24)
        h.addWidget(self.badge)
        self.set_count(0)
        self._render()

    def _render(self):
        key = "lane_selected" if self.current else "lane"
        self.label.setText(self.theme.word(key, self.title))
        self.label.setProperty("current", "true" if self.current else "false")
        self.label.style().unpolish(self.label)
        self.label.style().polish(self.label)

    def set_current(self, on):
        if on != self.current:
            self.current = on
            self._render()

    def set_count(self, n, fresh=0):
        """The unread count; fresh: of them, what the last update brought — a smaller
        "+56" in the pill, the words on hover."""
        self.count = n
        text = str(n) if n < 1000 else "999+"
        if fresh and n:
            text = f"{text} <small>+{fresh}</small>"
        self.badge.setText(text)
        self.badge.setToolTip(sidebar.fresh_words(fresh) if fresh and n else "")
        self.badge.setVisible(bool(n))


class GroupHeader(QWidget):
    """A section title in the sidebar; a click folds the section away (its lanes
    hidden, their unread summed up next to the title) — for screenshots, or for
    lists that are nobody's business."""

    def __init__(self, title, on_toggle):
        super().__init__()
        self.on_toggle = on_toggle
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(_("group_fold_tip"))
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 14, 4, 2)
        h.setSpacing(6)
        self.arrow = QLabel()
        self.arrow.setObjectName("listsHeader")
        h.addWidget(self.arrow)
        self.label = QLabel(title)
        self.label.setObjectName("listsHeader")
        h.addWidget(self.label, 1)
        self.badge = QLabel()
        self.badge.setObjectName("badge")
        self.badge.setProperty("kind", "normal")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setMinimumWidth(24)
        h.addWidget(self.badge)
        self.layout_ = h
        self.set_folded(False, 0)

    def set_folded(self, folded, count):
        self.arrow.setText("▸" if folded else "▾")
        self.badge.setText(str(count) if count < 1000 else "999+")
        self.badge.setVisible(folded and count > 0)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.on_toggle()
            e.accept()
            return
        super().mousePressEvent(e)


@dataclass
class ViewContext:
    """What a post card needs from the window."""
    cfg: dict
    theme: object
    images: Images
    on_link: object
    open_url: object
    show_images: object
    view: object = None   # core.view.View: the model the cards are drawn from
    me_id: str = ""
    # every post, account and attachment here is fedtail.model's (Post | Share, Account,
    # Media), never a server's JSON
    subscribed: object = None  # post -> is its thread followed
    thread_quiet: object = None  # post -> is its thread muted here (core/subs.py)
    fill_list_menu: object = None  # (QMenu, Account) -> fill "add to list"
    save_image: object = None      # Media -> save it to disk
    vote: object = None            # (Post, [option indexes]) -> vote in its poll
    refresh_poll: object = None    # set when "refresh" next to a poll's results works
    translate: object = None       # (Post, done({"lang", "provider", "html"})) -> ask
    supports: object = lambda _feature: True  # can my server do this (core.supports)
    play_video: object = None      # Media -> play it (or open in the browser)
    loop_gifv: object = None       # (label, Media, fit) -> loop a gifv in its card
    audio_bar: object = None       # Media -> a small audio player widget
    long_form: object = None       # post -> the whole of it from the author's server
    act_as: object = None          # post -> [(account tag, "@acct")] that could act on it
    do_act_as: object = None       # (post, tag, "fav" | "boost" | "reply") -> do it
    quote_reply: object = None     # (post, text, whole) -> reply quoting the text


class _LinkHost:
    """What common/links.py asks of the window, the Qt way: blocking questions, the
    status bar, the Compose dialog."""

    def __init__(self, win):
        self.win = win

    def call(self, future, ok=None, fail=None):
        return self.win.bridge.call(future, ok=ok, fail=fail)

    def status(self, text):
        self.win.statusBar().showMessage(text, 6000)

    def error(self, text):
        self.win.error(text)

    def confirm(self, title, text, then):
        if QMessageBox.question(self.win, title, text) == QMessageBox.StandardButton.Yes:
            then()

    def compose(self, reply_to=None, invite=False, edit=None, quote=None, text=None):
        if edit is not None or invite or quote is not None:
            Compose(self.win, reply_to=reply_to, invite=invite, edit=edit, quote=quote).show()
        else:
            self.win.compose(reply_to, text=text or "")

    def put_alias(self, alias):
        self.win.cmdline.put_alias(alias)

    def _place(self, name, arg="", tab=""):
        """A place of common/places.py (collections, a profile's details…): its window."""
        self.win.open_place(name, arg, tab)

    def open_lists(self, acc):
        """"Add to list" (common/profile.py): the lists menu at the pointer."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self.win)
        self.win.fill_list_menu(menu, acc)
        menu.popup(QCursor.pos())

    def ask_text(self, title, question, then, text="", allow_empty=False):
        """A line to type (common/profile.py: a private note, the languages in Home)."""
        from PySide6.QtWidgets import QInputDialog
        got, ok = QInputDialog.getText(self.win, title, question, text=text)
        if ok and (got.strip() or allow_empty):
            then(got)

    def choose(self, title, text, options, done, check=None):
        """One of a few (common/timed.py: how long a mute lasts, posts only)."""
        from .dialogs import choose
        return choose(self.win, title, text, options, done, check=check)

    def redrafted(self, d):
        self.win._redrafted(d)

    def __getattr__(self, name):  # open_thread, open_account, report… — the window's own
        return getattr(self.win, name)


class MainWindow(QMainWindow):
    def __init__(self, core, bridge, theme):
        super().__init__()
        self.core, self.bridge, self.theme = core, bridge, theme
        self.cfg = core.cfg
        wide = core.get_state("full_width")  # ≡ → full width, as left last time
        if wide is not None:
            self._column_width = self.cfg["ui"]["max_width"] or 760
            self.cfg["ui"]["max_width"] = 0 if wide else self._column_width
        self.images = Images(core, bridge)
        from . import player
        player.set_cache(self.images)  # videos played from disk once they're there
        self.ctx = ViewContext(self.cfg, theme, self.images, self.on_link, self.open_url,
                               self.show_images)
        from ...core.view import View
        self.ctx.view = View(core)
        self.links = Links(self.ctx.view, _LinkHost(self))  # what fedtail: links do
        self.ctx.subscribed = lambda e: core.subscribed(self.ctx.view.raw(e))
        quiet = getattr(core, "thread_quiet", None)
        self.ctx.thread_quiet = (lambda e: quiet(self.ctx.view.raw(e))) if quiet else None
        self.ctx.quote_reply = self.quote_reply
        self.ctx.supports = core.supports
        self.ctx.play_video = self.play_video
        from . import player
        player.choose_decoding(self.cfg["ui"].get("video_decode", "software"))
        if self.cfg["ui"].get("video_player", "internal") == "internal" and player.available():
            if self.cfg["ui"].get("gifv", "play") == "play":
                self.ctx.loop_gifv = player.InlineLoop
            self.ctx.audio_bar = player.AudioBar
        self.ctx.save_image = self.save_image
        self.ctx.vote = self.vote
        self.ctx.refresh_poll = True
        self.ctx.translate = self.translate_post if self.cfg["feed"].get("translate", True) \
            else None
        if self.cfg["lists"]["enabled"]:
            self.ctx.fill_list_menu = self.fill_list_menu
        if hasattr(core, "act_as") and self.cfg["ui"].get("act_as", True):
            self.ctx.act_as = lambda e: core.act_accounts(self.ctx.view.raw(e))
            self.ctx.do_act_as = self.act_as
        self.ctx.long_form = self.read_whole \
            if self.cfg["feed"].get("long_form", True) else None
        self.lane_widgets = {}
        self.columns = None  # the lanes side by side, while they are (columns.py)
        self.quitting = False
        bridge.on_error = self.error
        bridge.event.connect(self.on_event)
        bridge.raise_requested.connect(self.show_raise)
        bridge.open_requested.connect(self.open_from_outside)

        self._set_title()
        self.setWindowIcon(QIcon(icon_path()))
        self._build()
        self._debug_corner()
        self.setAcceptDrops(True)
        geo = core.get_state(self._geometry_key())
        if geo:
            self.restoreGeometry(bytes.fromhex(geo))
        else:
            self.resize(1150, 850)
        log.info("window %dx%d at %d,%d (%s)", self.width(), self.height(), self.x(), self.y(),
                 "restored" if geo else "first time")

    # ---- layout -------------------------------------------------------------------
    def _build(self):
        self.tray = None
        from ...desktop import desktop_id
        self.launcher = badge.Launcher(desktop_id(self.core.paths.profile)) \
            if self.cfg["ui"]["icon_count"] else None
        central = QWidget()
        central.setObjectName("central")
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        # the sidebar and the rest: its edge drags (a long name needs room), the width is
        # remembered while ui.sidebar_width stays what it was
        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.setObjectName("sideSplit")
        self.split.setChildrenCollapsible(False)
        self.split.setHandleWidth(4)
        self.split.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        split_layout = self.cfg["ui"].get("layout") in ("split", "qip")
        feed_module.COMPACT_HEADERS = split_layout  # slim lane headers under the author's bar
        # one tab: no tab bar at all — but in the split layout the tabs are the
        # messages window's conversations, each with its ×, the lanes' one too
        self.tabs.setTabBarAutoHide(not split_layout)
        self.tabs.addTab(self.stack, "")
        if not split_layout:
            self.tabs.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        self.announce_bar = AnnounceBar(self)
        rv.addWidget(self.announce_bar)
        rv.addWidget(self.tabs, 1)
        self.find_bar = FindBar(self)
        rv.addWidget(self.find_bar)
        self.cmdline = CommandBar(self)
        self.cmdline.setVisible(self.cfg["ui"]["command_line"])
        # "What's this?": longer hints on hover — for the session from the menu, or from
        # the start with ui.whats_this (no shortcut: F1 / Shift+F1 sit next to Esc)
        self.hints = HintMode(self, self.cfg["ui"].get("whats_this", False))
        self.help_panel = None
        rv.addWidget(self.cmdline)
        self.tabs.currentChanged.connect(lambda _i: self.find_bar.view_changed())
        self.stack.currentChanged.connect(lambda _i: self.find_bar.view_changed())
        # the right side is either the tabs or the curtain (all lanes closed: Esc)
        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(right)
        self.curtain = self._build_curtain()
        self.right_stack.addWidget(self.curtain)
        self.split.addWidget(self.right_stack)
        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([self._sidebar_width(), 10_000])
        self._side_save = QTimer(self)  # a drag moves it a hundred times: save once
        self._side_save.setSingleShot(True)
        self._side_save.setInterval(500)
        self._side_save.timeout.connect(self._sidebar_moved)
        self.split.splitterMoved.connect(lambda _pos, _i: self._side_save.start())
        row.addWidget(self.split, 1)
        self.setCentralWidget(central)
        # ui.layout = "split": the lanes in a roster window of their own (roster.py); this
        # window is the messages window — no sidebar, the lanes and threads in tabs
        self.roster = self.dock = self.author_bar = self.msg_tabs = None
        self.agent_face = None
        self.lane_now = None
        if self.cfg["ui"].get("layout") in ("split", "qip"):
            from .dock import InputDock
            from .roster import RosterWindow
            self.split.widget(0).hide()
            self.roster = RosterWindow(self)
            # tabs of its own above, the input line below, a bar that drags between them
            # (as in QIP); over a lane's posts who wrote the one under the cursor (dock.py)
            from .dock import AuthorBar, MessageTabs
            self.dock = InputDock(self)
            self.msg_tabs = MessageTabs(self)
            # the bar above says which is in front; the hidden one must not ask for room
            # either (Qt counts its tabs into the window's width: the window grew a tab
            # at a time instead of the tabs going into a second row)
            inner = self.tabs.tabBar()
            inner.setUsesScrollButtons(True)
            inner.setElideMode(Qt.TextElideMode.ElideRight)
            inner.setExpanding(False)
            inner.setMaximumSize(0, 0)
            inner.hide()
            self.tabs.currentChanged.connect(lambda _i: self.msg_tabs.sync())
            if self.cfg["ui"].get("dock_commands", True):
                self.cmdline.hide()  # the input line takes the commands (Ctrl+L: still here)
            at = rv.indexOf(self.tabs)
            rv.removeWidget(self.tabs)
            reading = QWidget()
            rl = QVBoxLayout(reading)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(0)
            from .dock import AgentFace, faces_mode
            mode = faces_mode(self)
            if mode == "qip":  # over a lane: the author under the cursor, in one line
                self.author_bar = AuthorBar(self)
                rl.addWidget(self.author_bar)
            if mode == "agent":  # the Agent: their face in a column beside the posts
                beside = QHBoxLayout()
                beside.setContentsMargins(0, 0, 0, 0)
                beside.setSpacing(0)
                beside.addWidget(self.tabs, 1)
                self.agent_face = AgentFace(self)
                beside.addWidget(self.agent_face)
                rl.addLayout(beside, 1)
            else:
                rl.addWidget(self.tabs, 1)
            self.read_write = QSplitter(Qt.Orientation.Vertical)
            self.read_write.setObjectName("readWrite")
            self.read_write.setChildrenCollapsible(False)
            self.read_write.setHandleWidth(6)
            self.read_write.addWidget(reading)
            self.read_write.addWidget(self.dock)
            self.read_write.setStretchFactor(0, 1)
            self.read_write.setStretchFactor(1, 0)
            rv.insertWidget(at, self.msg_tabs)
            rv.insertWidget(at + 1, self.read_write, 1)
            self.read_write.setSizes([10_000, 1])  # the input line as small as it goes
            self.tabs.currentChanged.connect(lambda _i: self.dock.follow(
                self.tabs.currentWidget()))
        self.menuBar().hide()
        # left in the status bar: which profile this is and who (★ the main one)
        self.profile_label = QLabel()
        self.profile_label.setObjectName("muted")
        self.profile_label.setToolTip(_("footer_profile_tip"))
        self.statusBar().addWidget(self.profile_label)
        # a message comes over the left of the bar: the profile's name steps aside for it
        # and back (QStatusBar is meant to do that itself, but a label shown again — a
        # theme tried, the window restyled — stayed under the message, both unreadable)
        self.statusBar().messageChanged.connect(
            lambda msg: self.profile_label.setVisible(not msg))
        self._profile_text()
        # right in the status bar, always seen: sync with my other devices (or that
        # there is none — it is a service of its own, off without sync.url)
        # slow mode on: when the next batch comes ("slow · next at 14:30")
        self.slow_label = QLabel()
        self.slow_label.setObjectName("muted")
        self.statusBar().addPermanentWidget(self.slow_label)
        self.sync_label = QLabel()
        self.sync_label.setObjectName("muted")
        self.statusBar().addPermanentWidget(self.sync_label)
        self._sync_text()
        self._slow_text()
        self._slow_timer = QTimer(self)
        self._slow_timer.timeout.connect(self._slow_text)
        self._slow_timer.start(30_000)

        for seq, fn in (("Ctrl+N", lambda: self.compose()), ("F5", self.refresh),
                        ("Ctrl+Q", self.quit),
                        ("Ctrl+W", lambda: self.close_tab(self.tabs.currentIndex())),
                        (QKeySequence.StandardKey.Find, self.find_bar.open),
                        ("Ctrl+K", lambda: (self.search_box.setFocus(),
                                            self.search_box.selectAll())),
                        ("Ctrl+L", lambda: (self.cmdline.show(), self.cmdline.focus())),
                        (QKeySequence.StandardKey.FindNext, lambda: self.find_bar.step(1)),
                        (QKeySequence.StandardKey.FindPrevious,
                         lambda: self.find_bar.step(-1))):
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(fn)
            # two owners of one key make Qt run neither; say so and run ours anyway
            key = sc.key().toString()
            sc.activatedAmbiguously.connect(
                lambda f=fn, k=key: (log.warning("ambiguous shortcut %s", k), f()))
        for i in range(9):  # Alt+N: the N-th lane as the sidebar shows them
            QShortcut(QKeySequence(f"Alt+{i + 1}"), self).activated.connect(
                lambda r=i: r < len(self.lane_order) and self.select_lane(self.lane_order[r]))

        if self.cfg["ui"].get("tray", True) and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            menu = QMenu(self)
            menu.addAction(_("show"), self.show_raise)
            menu.addAction(_("write"), lambda: self.compose())
            menu.addSeparator()
            menu.addAction(_("quit"), self.quit)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self._tray_click)
            self.tray.setToolTip(self.windowTitle())
            self.tray.show()
        self.notifier = Notifier(self)
        # the theme's sounds (common/sound.py); "bell" themes beep the Qt way
        self.sounds = Sounds(self.cfg, self.theme.id, bell=QApplication.beep)
        self.notifier.clicked.connect(self._notification_clicked)
        self.notifier.failed.connect(lambda why: self.error(_("notify_failed", err=why)))
        if self.notifier.problem:
            QTimer.singleShot(4000, lambda: self.statusBar().showMessage(
                self.notifier.problem, 20000))

    def _build_sidebar(self):
        t = self.theme
        feed_module.THEME = t
        card_module.AVATAR_RADIUS = _AVATAR_CORNERS.get(t.shape.get("avatar_shape"), -1)
        side = QWidget()
        side.setObjectName("sidebar")
        side.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        side.setMinimumWidth(180)
        side.setMaximumWidth(640)
        v = QVBoxLayout(side)
        v.setContentsMargins(14, 16, 14, 14)
        v.setSpacing(16)

        acc = QHBoxLayout()
        acc.setSpacing(12)
        self.account_avatar = QLabel()
        self.account_avatar.setFixedSize(44, 44)
        self.account_avatar.setVisible(bool(t.shape["sidebar_avatar"]))
        acc.addWidget(self.account_avatar)
        names = QVBoxLayout()
        names.setSpacing(0)
        # cut with "…" (all of it in the tooltip) when the buttons beside take the room:
        # clipped, the terminal theme's "mira@fedtail:~$" read "mi"
        self.account_name = feed_module._ElidedLabel(self.base_title, keep=6)
        self.account_name.setObjectName("accountName")
        self.account_sub = feed_module._ElidedLabel("", keep=6)
        self.account_sub.setObjectName("accountSub")
        for w in (self.account_name, self.account_sub):
            w.setTextFormat(Qt.TextFormat.PlainText)
        names.addWidget(self.account_name)
        names.addWidget(self.account_sub)
        acc.addLayout(names, 1)
        # ≡ the menu, ↔ posts across the full width (remembered), ❯ lanes side by side
        # (for now; the start: as ui.layout says). One size, icons from one set — or all
        # three as glyphs — each centred: a menu's own popup arrow would push it aside,
        # so ≡ opens its menu by a plain click.
        menu_btn = self._side_button("menu", "≡", _("menu"))
        menu_btn.clicked.connect(lambda: self._pop_app_menu(menu_btn))
        self.wide_btn = self._side_button("wide", "↔", _("full_width_tip"),
                                          drawn=self._arrows_icon)
        self.wide_btn.setCheckable(True)
        self.wide_btn.setChecked(not self.cfg["ui"]["max_width"])
        self.wide_btn.toggled.connect(self.set_full_width)
        self.columns_btn = self._side_button("columns", "❯", _("columns_tip"))
        self.columns_btn.setCheckable(True)
        self.columns_btn.toggled.connect(self.set_columns)
        for b in (menu_btn, self.wide_btn, self.columns_btn):
            acc.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        # a right click on who I am: the other accounts (profiles), to switch to
        for w in (self.account_avatar, self.account_name, self.account_sub):
            w.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            w.customContextMenuRequested.connect(
                lambda pos, w=w: self.accounts_menu().exec(w.mapToGlobal(pos)))
            w.setToolTip(_("accounts_tip"))
        v.addLayout(acc)
        # my avatar and name open my profile
        for w in (self.account_avatar, self.account_name, self.account_sub):
            w.setCursor(Qt.CursorShape.PointingHandCursor)
            w.setToolTip(_("my_profile"))
            w.installEventFilter(self)

        compose = QPushButton(t.word("compose", _("write")))
        compose.setObjectName("compose")
        compose.setCursor(Qt.CursorShape.PointingHandCursor)
        compose.setToolTip(_("write") + " (Ctrl+N)")
        compose.clicked.connect(lambda: self.compose())
        v.addWidget(compose)
        # finding new people and tags: Enter opens the Search tab (Ctrl+K gets here)
        self.search_box = QLineEdit()
        self.search_box.setObjectName("sideSearch")
        self.search_box.setPlaceholderText(_("search_side"))
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setToolTip(_("search_side_tip"))
        self.search_box.returnPressed.connect(
            lambda: (self.open_search(self.search_box.text()), self.search_box.clear()))
        v.addWidget(self.search_box)

        self.lanes = QListWidget()
        self.lanes.setObjectName("lanes")
        self.lanes.setFrameShape(QFrame.Shape.NoFrame)
        self.lanes.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.lane_items = {}
        self.lane_order = []
        self.lanes.currentItemChanged.connect(self._lane_clicked)
        # a click on the lane already chosen: no change signal, but its tab comes forward
        self.lanes.itemClicked.connect(lambda it: self._lane_clicked(it, None, show=True))
        self._show_lane_tab = False
        self.lanes.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.lanes.customContextMenuRequested.connect(self._lane_menu)
        self._rebuild_sidebar()
        v.addWidget(self.lanes, 1)
        if self.cfg["ui"]["sidebar_footer"]:
            self.footer = QLabel()
            self._footer_text()
            self.footer.setObjectName("sideFooter")
            self.footer.setWordWrap(True)
            self.footer.setCursor(Qt.CursorShape.PointingHandCursor)
            self.footer.installEventFilter(self)
            v.addWidget(self.footer)
        self.sidebar = self.lanes  # older name, still used around
        self.update_badges()
        return side

    def _side_button(self, picture, glyph, tip, drawn=None):
        """A square button at the top of the sidebar: the theme's picture (the
        desktop's, or drawn() when the desktop has none to fit), else — or with a theme
        without pictures — the glyph; centred either way."""
        b = QToolButton()
        b.setObjectName("menu")
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedSize(32, 32)
        # the buttons' pictures fill them as the desktop's toolbars do (18 of 32 px looked
        # lost): a third bigger than the lanes', 26 at most
        px = min(26, round(int(self.theme.shape.get("icon_size", 18) or 18) * 4 / 3))
        b.setIconSize(QSize(px, px))
        from . import icons
        ic = icons.icon(picture, self.theme, px)
        if ic.isNull() and drawn and icons.how(self.theme) == "desktop":
            ic = drawn(px)
        if ic.isNull():
            b.setText(glyph)
            # one glyph in a 32 px square: the theme's button padding would ask 36 for it
            # and cut it (Windows, monospace themes: the tour's "button cut")
            b.setStyleSheet("QToolButton#menu { padding: 0px; }")
        else:
            b.setIcon(ic)
        return b

    def _arrows_icon(self, size):
        """<-> in the sidebar's text colour, a line icon of the same weight as the
        theme's: no icon theme has a plain one for "full width"."""
        ratio = self.devicePixelRatioF() or 1.0
        pm = QPixmap(round(size * ratio), round(size * ratio))
        pm.setDevicePixelRatio(ratio)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self.theme.c["sidebar_text"], 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        y, left, right, head = size / 2, 2.5, size - 2.5, size * 0.22
        p.drawLine(QPointF(left, y), QPointF(right, y))
        for x, d in ((left, 1), (right, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + d * head, y - head))
            p.drawLine(QPointF(x, y), QPointF(x + d * head, y + head))
        p.end()
        return QIcon(pm)

    def _sidebar_width(self):
        """ui.sidebar_width, or the width dragged to while the config said the same."""
        want = self.cfg["ui"]["sidebar_width"]
        got = self.core.get_state("sidebar_width")
        if isinstance(got, dict) and got.get("cfg") == want and isinstance(got.get("width"), int):
            return got["width"]
        return want

    def _sidebar_moved(self):
        width = self.split.sizes()[0]
        self.core.set_state("sidebar_width", {"cfg": self.cfg["ui"]["sidebar_width"],
                                              "width": width})
        log.info("sidebar width %d", width)

    def _slow_text(self):
        """How fresh the lanes are and slow mode, at the right of the status bar:
        "⟳ updating the lanes…", "updated at 14:32 · slow · next at 14:45"."""
        text = sidebar.status_words(self.ctx.view)
        self.slow_label.setText(text)
        self.slow_label.setVisible(bool(text))

    def _sync_text(self):
        """"⇅ 21:40" / "⇅ off" / "⇅ !" at the right of the status bar."""
        from ..common import syncline
        text, tip = syncline.bar(self.core)
        self.sync_label.setText(text)
        self.sync_label.setToolTip(tip)

    def _profile_text(self):
        """"default: @me@server ★" at the left of the status bar."""
        from ...core import paths
        me = self.core.paths.profile
        who = ""
        if self.core.me:
            host = (self.core.auth or {}).get("server", "").split("://")[-1].rstrip("/")
            acct = self.ctx.view.me.handle
            who = "@" + acct + (f"@{host}" if host and "@" not in acct else "")
        text = f"{me}: {who}" if who else me
        self.profile_label.setText(text + (" ★" if me == paths.main_profile() else ""))

    def _tender_menu(self, parent):
        """"For the tender and sensitive": everything that hides people and words —
        word filters, mutes, blocks, blocked servers, filtered notifications. With
        arts_mode on, a line on top says what still works."""
        t = QMenu(_("tender_menu"), parent)
        t.setToolTipsVisible(True)
        if self.cfg["ui"]["arts_mode"]:
            note = t.addAction(_("tender_arts"))
            note.setEnabled(False)
            note.setToolTip(_("tender_arts_tip"))
            t.addSeparator()
        for tab, key in (("filters", "silence_filters"), ("muted", "silence_muted"),
                         ("blocked", "silence_blocked"), ("domains", "tender_domains")):
            t.addAction(_(key) + "…", lambda _c=False, x=tab: SilenceDialog(self, x).exec())
        if self.cfg["notify"]["filtered"] != "off":
            t.addSeparator()
            t.addAction(_("filtered_title") + "…", self.show_filtered)
        return t

    def _try_theme_menu(self, parent):
        """≡ → Try a theme: any theme at once, for this run; ui.theme in the config is
        what the next start brings."""
        t = QMenu(_("try_theme"), parent)
        t.setToolTip(_("try_theme_tip"))
        t.setToolTipsVisible(True)
        configured = self.cfg["ui"]["theme"]
        for name in themefile.for_layout(self.cfg, keep=(configured, self.theme.id)):
            label = name + ("  · " + _("theme_in_config") if name == configured else "")
            act = t.addAction(label, lambda n=name: self.try_theme(n))
            act.setCheckable(True)
            act.setChecked(name == self.theme.id)
        return t

    def try_theme(self, name):
        """Restyle the running window in another theme; the config stays as it is."""
        from . import notify as notify_module
        from . import theme as themes
        if name == self.theme.id:
            return
        app = QApplication.instance()
        old = self.theme
        # the videos and the gifs looping in cards stopped first: their players went
        # with the cards below while still decoding — and Qt fell over (23.10)
        from . import player as player_module
        player_module.stop_all(self)
        app.processEvents()  # the players' last frames delivered, to nobody harmed
        # Qt restyles every widget there is, seen or not: the lanes out of sight let
        # their cards go first (drawn anew when opened), or a trial took seconds
        for w in self.lane_widgets.values():
            if isinstance(w, LaneWidget):
                w._unload()
        # and the cards on screen go too, built again in the new theme right after:
        # restyled first and then thrown away, they cost seconds (columns: 6–9 s)
        from .feed import FeedView
        held = {}
        for view in self.findChildren(FeedView):
            if view.isVisible() and view.order:
                held[view] = view.let_go_rows()
        # what deleteLater() let go is still alive (and would be restyled) until the
        # event loop comes round: gone now
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        t0 = time.monotonic()
        theme = themes.apply(app, self.cfg, name)
        log.info("theme tried: %s (was %s, config says %s), restyled in %.0f ms", theme.id,
                 old.id, self.cfg["ui"]["theme"], (time.monotonic() - t0) * 1000)
        self._retheme(old, theme, held)
        if self.cfg["ui"]["themed_icon"] and self.cfg["ui"].get("app_icon") == "bubble":
            notify_module.use_theme_icon(theme, self.core.paths.cache_dir)
            self.setWindowIcon(QIcon(icon_path()))
            app.setWindowIcon(QIcon(icon_path()))
            if self.tray:
                self.tray.setIcon(self.windowIcon())
                self._tray_drawn = None  # the count drawn on the new one below
            self.update_badges()
        for w in theme.warnings:
            self.error(w)
        self.statusBar().showMessage(
            _("theme_tried", name=theme.id, configured=self.cfg["ui"]["theme"]), 12_000)

    def _retheme(self, old, theme, held=None):
        """Everything drawn in the old theme, drawn again in the new one: the sidebar
        built anew, every card rebuilt where it stands, the titles reworded."""
        self.theme = theme
        if getattr(self, "sounds", None) is not None:  # and its sounds from now on
            self.sounds.set_theme(theme.id)
        self.ctx.theme = theme
        feed_module.THEME = theme
        card_module.AVATAR_RADIUS = _AVATAR_CORNERS.get(theme.shape.get("avatar_shape"), -1)
        for w in self.findChildren(QWidget):
            if getattr(w, "theme", None) is old:
                w.theme = theme
        # the sidebar: built again, at the width it had, the same lane chosen
        current = self.lanes.currentItem()
        current = current.data(Qt.ItemDataRole.UserRole) if current else None
        sizes = self.split.sizes()
        old_side = self.split.widget(0)
        old_side.hide()
        old_side.setParent(None)
        old_side.deleteLater()
        # insertWidget, not replaceWidget: PySide gives the splitter ownership only
        # through insert/add — a sidebar handed to replaceWidget belonged to nobody and
        # Python deleted it as soon as this line was done (the panel vanished)
        self.side_panel = self._build_sidebar()
        self.split.insertWidget(0, self.side_panel)
        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes(sizes)
        if self.roster is not None:
            self.side_panel.hide()  # the split layout has the roster instead
        self.columns_btn.blockSignals(True)
        self.columns_btn.setChecked(self.columns is not None)
        self.columns_btn.blockSignals(False)
        if self.core.me:
            self._show_me(self.core.me)
        if current in self.lane_items:
            self.lanes.blockSignals(True)
            for i in range(self.lanes.count()):
                if self.lanes.item(i).data(Qt.ItemDataRole.UserRole) == current:
                    self.lanes.setCurrentRow(i)
            self.lanes.blockSignals(False)
            self.lane_items[current].set_current(True)
        # the lanes' titles, then every card
        for name, w in self.lane_widgets.items():
            header = getattr(w, "header", None)
            if header is not None and isinstance(w, LaneWidget):
                header.title.setText(theme.word("lane_title", self.lane_title(name)))
        from .feed import FeedView
        held = held or {}
        for view in self.findChildren(FeedView):
            if view in held:
                view.bring_back_rows(held[view])
            elif view.isVisible() or not view.order:
                view.rebuild_rows()
            else:
                view.restyle = True  # rebuilt when it comes into sight
        self.update_badges()
        if self.roster is not None:
            self.roster.dress()
            self.roster._shape = None  # rows built anew: their pictures in its colours
            self.roster.refresh()
        for w in (self.dock, self.author_bar):
            if w is not None:
                w.dress()

    def _pop_app_menu(self, btn, above=False):
        m = self._app_menu()
        pop_menu(m, btn, above)
        m.deleteLater()

    def _set_title(self):
        """"FedTail" for the main profile, "FedTail [work]" for another one."""
        from ...core import paths
        me = self.core.paths.profile
        name = version.NAME
        self.base_title = name if me == paths.main_profile() else f"{name} [{me}]"
        self.setWindowTitle(self.base_title)

    def _footer_text(self):
        """Version and build, then who made it."""
        info = version.info()
        build = info["version"] + (f" · {info['date']}" if info["date"] else "")
        self.footer.setText(f"{version.NAME} {build}<br>{_('made_by')}")
        self.footer.setToolTip(_("about"))

    # ---- accounts: one profile each, switched by starting the other one ------------------
    def accounts_menu(self, parent=None):
        m = QMenu(parent or self)
        m.setTitle(_("accounts"))
        m.aboutToShow.connect(lambda: self._fill_accounts(m))
        self._fill_accounts(m)
        return m

    def _fill_accounts(self, m):
        from ...core import profiles
        m.clear()
        me = self.core.paths.profile
        listed = profiles.listing()
        for p in listed:
            a = m.addAction(profiles.label(p) + (" ★" if p.get("main") else "")
                            + ("" if p["logged_in"] else "  " + _("not_logged_in")))
            a.setCheckable(True)
            a.setChecked(p["name"] == me)
            if p["name"] == me:
                a.setEnabled(False)
            else:
                a.triggered.connect(lambda _c=False, n=p["name"]: self.switch_profile(n))
        if listed:  # (a menu that starts with a line looks broken)
            m.addSeparator()
        m.addAction(_("my_profile"), self.open_my_profile).setEnabled(bool(self.core.me))
        m.addAction(_("server_info") + "…", self.show_server_info).setEnabled(
            bool(self.core.me))
        merged = m.addAction(_("accounts_merge"))
        merged.setCheckable(True)
        merged.setChecked(bool(getattr(self.core, "others", None)))
        merged.setToolTip(_("accounts_merge_tip"))
        merged.setEnabled(not self.cfg["ui"]["merge"])  # the config decides then
        merged.toggled.connect(self.set_merged)
        m.addAction(_("account_add"), self.add_profile)
        # what this profile can do with its own login: dangerous things last, with a
        # question first; in the all-in-one window they'd mix the accounts up, so not there
        m.addSeparator()
        alone = not getattr(self.core, "others", None)
        if me != profiles.paths.main_profile():
            m.addAction(_("make_main"), self.make_main).setToolTip(_("make_main_tip"))
        again = m.addAction(_("relogin"), self.relogin)
        again.setEnabled(alone and bool(self.core.auth))
        out = m.addAction(_("logout"), self.log_out)
        out.setEnabled(alone and bool(self.core.auth))
        m.setToolTipsVisible(True)

    def make_main(self):
        from ...core import paths
        paths.set_main(self.core.paths.profile)
        log.info("main profile: %s (from the menu)", self.core.paths.profile)
        self._set_title()
        self._profile_text()
        self.statusBar().showMessage(_("made_main", profile=self.core.paths.profile), 8000)

    def switch_profile(self, name):
        """The other account in its own window, with its own theme and config; this
        one closes (ui.switch_closes) — its unread stays counted for next time."""
        from ...core import profiles
        log.info("switching to profile %s", name)
        profiles.launch(name)
        if self.cfg["ui"]["switch_closes"]:
            QTimer.singleShot(300, self.quit)

    def set_merged(self, on):
        """All accounts in one window or not: remembered, then fedtail restarts."""
        primary = getattr(self.core, "primary", self.core)
        primary.set_state("merge", ["all"] if on else [])
        log.info("merge %s: restarting", "on" if on else "off")
        self.restart()

    def restart(self):
        """fedtail again, the same profile: once this process has gone."""
        import os

        from ...core import profiles
        primary = getattr(self.core, "primary", self.core)
        profiles.launch(primary.paths.profile, after=0.5, wait_for=os.getpid())
        QTimer.singleShot(200, self.quit)

    def add_profile(self):
        from ...core import paths as paths_module
        from ...core import profiles
        taken = {p["name"] for p in profiles.listing()}
        name, ok = QInputDialog.getText(self, _("account_add"), _("account_add_q"))
        name = name.strip()
        if not ok or not name:
            return
        if name in taken or name in profiles.NOT_PROFILES or \
                not paths_module._PROFILE_RE.match(name):
            QMessageBox.warning(self, _("account_add"), _("account_bad_name", name=name))
            return
        self.switch_profile(name)  # a new profile starts with the login window

    def _app_menu(self):
        m = QMenu(self)
        m.addMenu(self._tender_menu(m))
        if self.cfg["post"].get("schedule", True):
            m.addAction(_("scheduled_title") + "…", self.show_scheduled)
        m.addAction(_("slow_title") + "…", lambda: self.open_place("slow"))
        people = m.addMenu(_("menu_people"))
        trends = any(self.core.supports("trends_" + k) for k in ("statuses", "tags", "links"))
        for feature, label, slot in (
                ("suggestions", _("suggestions_title"), self.open_suggestions),
                ("directory", _("directory_title"), lambda: self.open_directory(False)),
                ("directory", _("directory_local"), lambda: self.open_directory(True)),
                ("trends", _("trends_title"), self.open_trends)):
            if self.core.supports(feature) and (feature != "trends" or trends):
                people.addAction(label, slot)
        if self.core.supports("collections"):  # Mastodon 4.6: people put forward together
            people.addAction(_("collections_mine") + "…", lambda: self.open_place("collections"))
        remote = people.addAction(_("remote_public"), self.ask_remote_lane)
        remote.setToolTip(_("remote_public_tip"))
        people.setToolTipsVisible(True)
        people.setEnabled(not people.isEmpty())
        m.addMenu(self.accounts_menu(m))
        m.addSeparator()
        m.addAction(_("settings"), self.open_settings)
        m.addAction(_("le_title") + "…", lambda: self.open_place("lanes"))
        m.addAction(_("open_config"), lambda: open_path(self.core.paths.config_file))
        m.addAction(_("open_themes"), lambda: open_path(themefile.user_dir()))
        m.addMenu(self._try_theme_menu(m))
        m.addAction(_("open_data"), lambda: open_path(self.core.paths.data_dir))
        m.addSeparator()
        dbg = m.addMenu(_("debug_menu"))
        dbg.addAction(_("debug_federation"), self.federation_status)
        dbg.addAction(_("debug_logs"), lambda: open_path(diag.logs_dir(self.core.paths)))
        dbg.addAction(_("debug_log_title") + "…", lambda: self.open_place("log"))
        dbg.addAction(_("debug_report"), self.bug_report)
        dbg.addAction(_("debug_notify"), lambda: self.statusBar().showMessage(
            _("debug_notify_sent", backend=self.notifier.test()), 8000))
        dbg.addAction(_("debug_sound"), lambda: self.statusBar().showMessage(
            self.sounds.test(), 8000))
        dbg.addAction(_("debug_stacks"), lambda: (diag.dump_stacks("asked from the menu"),
                                                  diag.log_stats(),
                                                  self.statusBar().showMessage(
                                                      _("debug_stacks_done"), 5000)))
        # hunting a leak: what grows, where the memory is, give the free part back
        dbg.addSeparator()
        dbg.addAction(_("debug_census"), self.debug_census)
        dbg.addAction(_("debug_trim"), self.debug_trim)
        from ... import leaks
        tracing = dbg.addAction(_("debug_tracing"))
        tracing.setCheckable(True)
        tracing.setChecked(leaks.tracing())
        tracing.setToolTip(_("debug_tracing_tip"))
        tracing.toggled.connect(lambda on: leaks.start_tracing() if on else leaks.stop_tracing())
        snap = dbg.addAction(_("debug_snapshot"), self.debug_snapshot)
        snap.setEnabled(leaks.tracing())
        dbg.setToolTipsVisible(True)
        m.addSeparator()
        m.addAction(_("help_title"), self.open_help)
        whats = m.addAction(_("whats_this"))
        whats.setCheckable(True)
        whats.setChecked(self.hints.on)
        whats.setToolTip(_("whats_this_tip"))
        whats.toggled.connect(self.hints.set_on)
        m.setToolTipsVisible(True)
        m.addAction(_("issue_menu"), self.report_issue)
        m.addAction(_("about"), self.about)
        m.addSeparator()
        m.addAction(_("quit") + "\tCtrl+Q", self.quit)
        return m

    # ---- startup --------------------------------------------------------------------
    def start(self):
        if not self.core.logged_in:
            if LoginDialog(self).exec() != QDialog.DialogCode.Accepted:
                self.quit()
                return
        self.statusBar().showMessage(_("connecting"))
        self.bridge.call(self.core.connect(), ok=self._connected, fail=self._connect_failed)

    def eventFilter(self, obj, e):
        if e.type() == e.Type.MouseButtonRelease:
            if obj in (self.account_avatar, self.account_name, self.account_sub):
                self.open_my_profile()
                return True
            if obj is getattr(self, "footer", None):
                self.about()
                return True
        return super().eventFilter(obj, e)

    def open_my_profile(self):
        if self.core.me:
            self.open_account(self.ctx.view.me.id)

    def edit_profile(self):
        if self.core.me:
            ProfileDialog(self).exec()

    def _connected(self, me):
        self._show_me(me)
        for w in self.theme.warnings:
            self.error(w)
        # until the first round of polling is in, the bar says so (a slow connection
        # would otherwise show empty lanes and nothing else)
        self._hello = _("connected", acct=self.ctx.view.acc(me).handle,
                        server=self.core.auth["server"])
        self._waiting_text = f"{self._hello} · {_('first_poll')}"
        self.statusBar().showMessage(self._waiting_text)
        self._after_connect(me)

    def _show_me(self, me):
        me = me if isinstance(me, Account) else self.ctx.view.acc(me)
        self.ctx.me_id = me.id
        self._profile_text()
        t = self.theme
        # the theme's words name them as the server does
        fields = dict(display_name=me.name or me.username, username=me.username,
                      acct=me.handle)
        self.account_name.setText(t.words["account_title"].format(**fields))
        self.account_sub.setText(t.words["account_subtitle"].format(**fields))
        if t.shape["sidebar_avatar"]:
            self.images.get(me.avatar_static or me.avatar,
                            lambda pm: self.account_avatar.setPixmap(_round(pm, 44)))

    def _after_connect(self, me):
        if self.core.new_options:
            QTimer.singleShot(8500, lambda: self.statusBar().showMessage(
                _("new_options", n=len(self.core.new_options)), 30_000))
        tip = f"{self.base_title} — @{self.ctx.view.acc(me).handle}"
        self.setWindowTitle(tip)
        if self.tray:
            self.tray.setToolTip(tip)
        if self.cfg["ui"].get("open_columns") and self.lane_order:
            self.set_columns(True)
        self._open_start_lane()
        self.core.start_polling()
        self.announce_bar.start()
        if self.cfg["notify"]["filtered"] == "remind":
            QTimer.singleShot(12_000, self._remind_filtered)

    def _open_start_lane(self):
        """ui.start_lane: "none" — every lane closed behind the curtain (nothing gets
        read by just starting; Enter opens the last one); "last" — the lane of last
        time; or a lane by name."""
        want = self.cfg["ui"]["start_lane"]
        if want == "none":
            self.close_all()
            return
        name = self.core.get_state("lane") if want == "last" else want
        if name not in self.lane_items:  # the first time, or a lane that's off
            name = "home" if "home" in self.lane_items else self.lane_order[0]
        self.select_lane(name)

    def _connect_failed(self, err):
        if "HTTP 401" in err or "HTTP 403" in err:
            QMessageBox.warning(self, _("auth_failed_title"), _("auth_failed"))
            self.core.logout()  # the token is dead anyway: the login window, from scratch
            self.start()
            return
        self.statusBar().showMessage(_("server_down", err=err))
        QTimer.singleShot(20_000, self.start)

    def relogin(self):
        """Log in to this same account anew (new permissions, a token revoked on the
        server). The old token stays until the new one is in; cancel changes nothing,
        another account is refused."""
        auth = self.core.auth or {}
        if not auth:
            return
        acct = "@" + (self.ctx.view.auth_handle or "?")
        if QMessageBox.question(self, _("relogin_title"), _("relogin_q", acct=acct)) \
                != QMessageBox.StandardButton.Yes:
            return
        log.info("login anew: asked")
        if LoginDialog(self, expect=(auth["server"], self.ctx.view.auth_handle)).exec() \
                == QDialog.DialogCode.Accepted:
            log.info("login anew: done, reconnecting")
            self.start()

    def log_out(self):
        """Forget this profile's token. The main profile hands its ★ to another one
        logged in; the window goes over to that one, or (none left) to the login."""
        from ...core import profiles
        me = self.core.paths.profile
        mine = self.ctx.view.me
        acct = "@" + (mine.handle if mine else self.ctx.view.auth_handle or me)
        others = [p for p in profiles.listing() if p["logged_in"] and p["name"] != me]
        main = profiles.paths.main_profile()
        text = [_("logout_q", acct=acct)]
        if others:
            target = next((p for p in others if p["name"] == main), others[0])
            if me == main:
                text.append(_("logout_main_moves", to=profiles.label(target)))
            text.append(_("logout_switch", to=profiles.label(target)))
        else:
            target = None
            text.append(_("logout_last"))
        box = QMessageBox(QMessageBox.Icon.Warning, _("logout_title"), "<br><br>".join(text),
                          QMessageBox.StandardButton.Cancel, self)
        go = box.addButton(_("logout_yes"), QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is not go:
            return
        log.info("logout: profile %s", me)
        self.core.logout()
        profiles.hand_over_main(me)
        if target:
            profiles.launch(target["name"])
            QTimer.singleShot(300, self.quit)
        else:
            self._set_title()
            self.start()  # the login window; cancel there closes fedtail

    # ---- lanes ------------------------------------------------------------------------
    # ---- lists in the sidebar -----------------------------------------------------------
    def lane_title(self, name):
        return self.core.lane_title(name) or _("lane_" + name)

    def _rebuild_lists(self):
        self._rebuild_sidebar()

    def _section_header(self, title, group, plus=False):
        head = QListWidgetItem()
        head.setFlags(Qt.ItemFlag.NoItemFlags)
        box = GroupHeader(self.theme.word("lane", title), lambda g=group: self.fold_group(g))
        self.group_heads[group] = box
        h = box.layout_
        if plus:
            btn = QToolButton()
            btn.setObjectName("menu")
            btn.setText("+")
            btn.setToolTip(_("list_new"))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda: self.new_list())
            h.addWidget(btn)
        head.setSizeHint(box.sizeHint())
        self.lanes.addItem(head)
        self.lanes.setItemWidget(head, box)

    def _rebuild_sidebar(self):
        """The lanes on the left, in sections (Reading, Lists, For me, More) or as
        one list (ui.sidebar_groups = false). Rebuilt when the lists change."""
        current = self.lanes.currentItem()
        current = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.lanes.blockSignals(True)
        self.lanes.clear()
        self.lane_items = {}
        self.lane_order = []
        self.group_heads, self.group_rows = {}, {}
        groups = sidebar.groups(self.ctx.view, self.cfg)
        titles = {x.id: x for x in self.ctx.view.lists}
        for group, names in groups:
            if group == "lists":
                self._section_header(_("lists_header"), group, plus=True)
            elif not names:
                continue
            elif group:
                self._section_header(_("grp_" + group), group)
            self.group_rows[group] = names
            for name in names:
                it = QListWidgetItem()
                it.setData(Qt.ItemDataRole.UserRole, name)
                lst = titles.get(name[len("list:"):]) if lanes_module.is_list(name) else None
                # a list's title, a tag lane's or a free lane's own; None — the built-in word
                title = lst.title if lst else self.core.lane_title(name)
                w = LaneItem(name, self.theme, len(self.lane_order) + 1, title=title,
                             icon=self.core.lane_icon(name))
                if lst and lst.exclusive:
                    w.setToolTip(_("list_exclusive_tip"))
                it.setSizeHint(w.sizeHint())
                self.lanes.addItem(it)
                self.lanes.setItemWidget(it, w)
                self.lane_items[name] = w
                self.lane_order.append(name)
                it.setHidden(group in self.folded_groups())
        # lanes of lists that are gone
        for name in [n for n in self.lane_widgets if n.startswith("list:")
                     and n not in self.core.lane_by_name]:
            if self.columns is not None:
                self.columns.drop(name)
            w = self.lane_widgets.pop(name)
            self.stack.removeWidget(w)
            w.deleteLater()
        self.lanes.blockSignals(False)
        for g in self.group_heads:
            self._show_fold(g)
        if current:
            # the sidebar rebuilt (lists changed…): the lane is chosen again, but a
            # search, thread or profile tab in front stays in front
            if current in self.lane_items:
                self.select_lane(current, show=False)
                self.lane_items[current].set_current(True)
            else:
                self.select_lane("home" if "home" in self.lane_items
                                 else self.lane_order[0], show=False)
        self.update_badges()

    def _lane_menu(self, pos):
        it = self.lanes.itemAt(pos)
        name = it.data(Qt.ItemDataRole.UserRole) if it else None
        m = QMenu(self)
        if name and name.startswith("list:"):
            lid = name[len("list:"):]
            lists = self.ctx.view.lists
            x = next((x for x in lists if x.id == lid), None)
            if x is None:
                return
            m.addAction(_("list_people"), lambda: self.open_list_people(x))
            up = m.addAction(_("list_up"), lambda: self.bridge.call(
                self.core.submit(self.core.move_list, x.id, -1)))
            down = m.addAction(_("list_down"), lambda: self.bridge.call(
                self.core.submit(self.core.move_list, x.id, 1)))
            ids = [y.id for y in lists]
            up.setEnabled(ids.index(x.id) > 0)
            down.setEnabled(ids.index(x.id) < len(ids) - 1)
            m.addSeparator()
            m.addAction(_("list_rename"), lambda: self.rename_list(x))
            ex = m.addAction(_("list_exclusive"))
            ex.setCheckable(True)
            ex.setChecked(x.exclusive)
            ex.setToolTip(_("list_exclusive_tip"))
            ex.toggled.connect(lambda on: self.bridge.call(
                self.core.update_list(x.id, x.title, on)))
            self._replies_menu(m, x)
            m.addSeparator()
            m.addAction(_("list_delete"), lambda: self.delete_list(x))
        elif name and name.startswith("tags:"):
            g = next((g for g in self.core.tag_groups
                      if f"tags:{_tags_key(g)}" == name), None)
            drop = m.addAction(_("tags_drop"), lambda: self.bridge.call(
                self.core.drop_tag_group(name)))
            if g is not None and not g.get("saved"):
                drop.setEnabled(False)
                drop.setToolTip(_("tags_in_config"))
            elif g is not None:
                home = m.addAction(_("tags_in_home"))
                home.setCheckable(True)
                home.setChecked(not g.get("not_in_home"))
                home.setToolTip(_("tags_in_home_tip"))
                home.toggled.connect(lambda on: self.bridge.call(
                    self.core.set_tag_group_in_home(name, on)))
                m.setToolTipsVisible(True)
        elif self.cfg["lists"]["enabled"]:
            m.addAction(_("list_new"), lambda: self.new_list())
        if name and not name.startswith(("list:", "tags:")) and \
                name in self.core.lane_by_name and name not in ("activity", "requests"):
            m.addAction(_("le_edit_lane"), lambda: self.open_place("lane", name))
        if name:
            m.addAction(_("le_title") + "…", lambda: self.open_place("lanes"))
        if m.isEmpty():
            return
        m.exec(self.lanes.mapToGlobal(pos))

    def _replies_menu(self, m, x):
        """Whose replies the list's lane shows (the server's replies_policy): a submenu
        of three, the list's own ticked."""
        from PySide6.QtGui import QActionGroup

        from ..common import timed
        sub = m.addMenu(_("replies_policy"))
        sub.setToolTipsVisible(True)
        sub.menuAction().setToolTip(_("replies_policy_tip"))
        group = QActionGroup(sub)
        now = x.replies or "list"  # the server's default when it doesn't say
        for key, label in timed.replies_policies():
            a = sub.addAction(label)
            a.setCheckable(True)
            a.setChecked(key == now)
            a.setToolTip(_("replies_policy_tip"))
            group.addAction(a)
            a.triggered.connect(lambda _c=False, k=key: k != now and self.bridge.call(
                self.core.update_list(x.id, x.title, x.exclusive, replies_policy=k)))
        return sub

    def open_list_people(self, x):
        """Who is in a list, a tab of people; each can be taken out right there."""
        def out(acc_id):
            return self.core.set_in_list(x.id, acc_id, False)
        self.open_accounts(f"list-people:{x.id}", _("list_people_title", title=x.title),
                           lambda _cursor: self.core.list_people(x.id), dismiss=out,
                           dismiss_label=_("list_take_out"))

    def new_list(self, add=None):
        title, ok = QInputDialog.getText(self, _("list_new").rstrip("…"), _("list_name_q"))
        if ok and title.strip():
            self.bridge.call(self.ctx.view.create_list(title.strip(), add=add),
                             ok=lambda x: self.statusBar().showMessage(
                                 _("list_created", title=x.title), 5000))

    def rename_list(self, x):
        title, ok = QInputDialog.getText(self, _("list_rename"), _("list_name_q"),
                                         text=x.title)
        if ok and title.strip() and title.strip() != x.title:
            self.bridge.call(self.core.update_list(x.id, title.strip(), x.exclusive))

    def delete_list(self, x):
        if QMessageBox.question(self, _("list_delete"), _("list_delete_q", title=x.title)) \
                == QMessageBox.StandardButton.Yes:
            self.bridge.call(self.core.delete_list(x.id))

    def fill_list_menu(self, menu, account):
        """"Add to list" submenu of a post: every list, ticked where the author is. A
        server takes only people I follow into lists: for someone else the lists stay
        dead (not clickable at all) under "follow first", with Follow right there. Until
        the server says which it is, they are dead too — never "as if followed"."""
        try:
            menu.clear()
        except RuntimeError:  # the post's menu was made anew under it: this one's gone
            return
        inside = self.core.lists_of(account.id)
        note = menu.addAction(_("list_follow_first"))
        note.setEnabled(False)
        follow = menu.addAction(_("follow"))
        follow.triggered.connect(lambda _c=False, a=account: self._follow_from_menu(a))
        head = menu.addSeparator()
        list_actions = []
        lists = self.ctx.view.lists
        for x in lists:
            a = menu.addAction(x.title)
            list_actions.append(a)
            a.setCheckable(True)
            a.setChecked(x.id in inside)
            a.toggled.connect(lambda on, act=a, lid=x.id, acc=account.id:
                              self._list_toggled(act, lid, acc, on))
        if lists:
            menu.addSeparator()
        list_actions.append(menu.addAction(_("list_new"),
                                           lambda: self.new_list(add=account.id)))

        def apply(rel):
            try:
                ok = list_open(rel, inside)
                for a in list_actions:
                    a.setEnabled(ok)
                note.setText(_("list_follow_first") if rel is not None else
                             _("list_checking"))
                for a in (note, head):
                    a.setVisible(not ok)
                follow.setVisible(not ok and rel is not None)
            except RuntimeError:  # the menu closed meanwhile
                pass
        rel = self.ctx.view.relation_known(account.id)  # a Relationship, or None
        apply(rel)
        if rel is None:
            self.bridge.call(self.ctx.view.relationship(account.id), ok=apply,
                             fail=lambda _e: apply(Relationship()))

    def _list_toggled(self, action, list_id, acc_id, on):
        try:
            if not action.isEnabled():  # a dead tick: nothing goes to the server
                return
        except RuntimeError:
            return
        self.bridge.call(
            self.core.set_in_list(list_id, acc_id, on),
            ok=lambda r: self.statusBar().showMessage(
                _("list_pending") if r == "pending" else
                _("list_added" if on else "list_removed"), 6000),
            fail=self.error)

    def _follow_from_menu(self, account):
        self.bridge.call(self.ctx.view.follow(account.id), ok=lambda rel: self.statusBar(
            ).showMessage(_("followed_now", acct="@" + account.handle)
                          if rel.following else _("follow_asked_list"), 6000),
                         fail=self.error)

    def _lane_clicked(self, cur, _prev, show=False):
        """A lane chosen. Its tab comes to the front only when I chose it (a click, keys
        in the sidebar, Alt+N, start-up) — never because the sidebar changed under it
        while I'm reading a search, a thread or a profile."""
        if not cur or not self.core.me:
            return
        show = show or self._show_lane_tab or self.lanes.hasFocus() or \
            self.tabs.currentWidget() is self.stack
        name = cur.data(Qt.ItemDataRole.UserRole)
        if name is None:
            return
        log.info("lane opened: %s", name)
        if self.curtain_shown():
            self.right_stack.setCurrentIndex(0)
        w = self._lane_widget(name)
        if self.columns is not None:
            self._show_in_columns(name, w, show)
            return
        if self.stack.indexOf(w) < 0:
            self.stack.addWidget(w)
        self.stack.setCurrentWidget(w)
        self.lane_now = name
        if show:
            self.tabs.setCurrentIndex(self.tabs.indexOf(self.stack))
            if self.msg_tabs is not None and self.isVisible():
                self.msg_tabs.lane_opened(name)  # a tab of its own above
        else:
            log.info("lane %s chosen behind the %s tab", name,
                     type(self.tabs.currentWidget()).__name__)
        if isinstance(w, LaneWidget) and w.dirty:
            w.draw_shown()
        if isinstance(w, LaneWidget) and show:
            w.view.setFocus()  # j / k work right away
        self.tabs.setTabText(self.tabs.indexOf(self.stack), self.lane_title(name))
        self.core.set_state("lane", name)
        self.core.set_active_lane(name)
        for lane_name, item in self.lane_items.items():
            item.set_current(lane_name == name)

    def _lane_widget(self, name):
        w = self.lane_widgets.get(name)
        if w is None:
            if name == "requests":
                w = RequestsWidget(self)
            elif name == "activity":
                w = ActivityWidget(self)
            else:
                w = LaneWidget(self, name)
                w.dirty = True  # drawn right after the switch, under "loading…"
            self.lane_widgets[name] = w
            self.stack.addWidget(w)
        return w

    # ---- columns side by side (ui.layout, ❯) --------------------------------------------
    def set_columns(self, on):
        """Lanes side by side, or one at a time. The same lane widgets move over, so
        each keeps its place and its filters."""
        on = bool(on)
        if self.columns_btn.isChecked() != on:
            self.columns_btn.setChecked(on)  # comes back here through toggled
            return
        if on == (self.columns is not None):
            return
        from .columns import ColumnsArea, start_names
        if on:
            titles = {x.title: "list:" + x.id for x in self.ctx.view.lists}
            names = start_names(self.cfg, self.core.get_state("columns"), self.lane_order,
                                titles)
            self.columns = ColumnsArea(self)
            for name in names:
                self.columns.add(name, self._lane_widget(name))
            self.stack.addWidget(self.columns)
            self.stack.setCurrentWidget(self.columns)
            focus = self.core.get_state("lane")
            self.columns.focus(focus if focus in names else names[0])
            self._columns_shown()
            log.info("columns: %s", ", ".join(names))
        else:
            focused = self.columns.focused
            for _name, w in self.columns.release():
                self.stack.addWidget(w)
            self.stack.removeWidget(self.columns)
            self.columns.deleteLater()
            self.columns = None
            self.core.set_active_lanes([])
            log.info("columns off")
            if focused:
                self.select_lane(focused)

    def _show_in_columns(self, name, w, show):
        if name not in self.columns.frames:
            self.columns.add(name, w)
            self.columns_changed()
        self.stack.setCurrentWidget(self.columns)
        if show:
            self.tabs.setCurrentIndex(self.tabs.indexOf(self.stack))
        self.columns.focus(name, keys=show)
        if isinstance(w, LaneWidget) and w.dirty:
            w.draw_shown()
        self.core.set_state("lane", name)
        self.column_focused(name)
        self._columns_shown()

    def _columns_shown(self):
        self.tabs.setTabText(self.tabs.indexOf(self.stack), _("columns"))
        self.core.set_active_lanes(self.columns.names())

    def column_focused(self, name):
        """The column in focus: the one the sidebar marks, and the one keys go to."""
        self.core.set_active_lane(name)
        for lane_name, item in self.lane_items.items():
            item.set_current(lane_name == name)

    def columns_changed(self):
        if self.columns is not None:
            self.core.set_state("columns", self.columns.names())
            self.core.set_active_lanes(self.columns.names())

    def close_column(self, name):
        if self.columns is None or len(self.columns.order) <= 1:
            return  # the last one stays: ❯ goes back to one lane
        w = self.columns.drop(name)
        if w is not None:
            self.stack.addWidget(w)
        self.columns_changed()
        if self.columns.focused:
            self.column_focused(self.columns.focused)

    def lane_on_screen(self, name):
        if self.columns is not None and self.tabs.currentWidget() is self.stack \
                and not self.curtain_shown():
            return name in self.columns.frames
        return self.current_lane() == name

    def current_lane(self):
        """The lane on screen, or None when a thread/profile tab is in front."""
        if self.tabs.currentWidget() is not self.stack:
            return None
        w = self.stack.currentWidget()
        return getattr(w, "name", None)

    # ---- folding sections of the sidebar -----------------------------------------------
    def folded_groups(self):
        return sidebar.folded(self.ctx.view)

    def fold_group(self, group, fold=None):
        fold = sidebar.fold(self.ctx.view, group, fold)
        names = set(self.group_rows.get(group, ()))
        for i in range(self.lanes.count()):
            it = self.lanes.item(i)
            if it.data(Qt.ItemDataRole.UserRole) in names:
                it.setHidden(fold)
        self._show_fold(group)
        log.info("sidebar section %s %s", group, "folded" if fold else "unfolded")

    def _show_fold(self, group):
        head = self.group_heads.get(group)
        if head is None:
            return
        total = sum(self.lane_items[n].count for n in self.group_rows.get(group, ())
                    if n in self.lane_items)
        head.set_folded(group in self.folded_groups(), total)

    def select_lane(self, name, show=True):
        """Choose a lane; show=False: behind whatever tab is in front."""
        self._show_lane_tab = show
        try:
            for i in range(self.lanes.count()):
                if self.lanes.item(i).data(Qt.ItemDataRole.UserRole) == name:
                    if self.lanes.currentRow() == i:
                        # already the current row (e.g. after rows were removed under
                        # it): no change signal will come, so show the lane ourselves
                        self._lane_clicked(self.lanes.item(i), None)
                    else:
                        self.lanes.setCurrentRow(i)
        finally:
            self._show_lane_tab = False

    def update_badges(self):
        items = getattr(self, "lane_items", {})
        numbers = sidebar.counts(self.ctx.view, items)
        total = sidebar.icon_total(self.ctx.view, self.cfg, numbers)
        for name, item in items.items():
            item.set_count(numbers[name], sidebar.fresh(self.ctx.view, name)
                           if numbers[name] else 0)
        if getattr(self, "slow_label", None) is not None:
            self._slow_text()
        for g in getattr(self, "group_heads", {}):
            self._show_fold(g)
        if getattr(self, "curtain", None) is not None and self.curtain_shown():
            self._curtain_text()
        if self.tray:
            base = self.windowTitle()
            self.tray.setToolTip(_("tray_new", title=base, n=total) if total else base)
            # drawn anew when the number or the icon under it changed: a theme tried
            # puts the plain icon back, and the same number never drew it again
            drawn = (total, self.windowIcon().cacheKey(), self.theme.c["hot"].name())
            if drawn != getattr(self, "_tray_drawn", None):
                self._tray_drawn = drawn
                self.tray.setIcon(badge.icon_with_count(self.windowIcon(), total,
                                                        self.theme.c["hot"].name()))
                log.debug("tray icon: %d", total)
        self._tray_count = total
        if self.launcher:
            self.launcher.set(total)
        if getattr(self, "roster", None) is not None:
            self.roster.refresh_soon()

    # ---- events from the core ---------------------------------------------------------
    def on_event(self, name, payload):
        if getattr(getattr(self.core, "store", None), "closed", False):
            return  # an event queued before the exit, come after the database closed
        t = time.monotonic()
        try:
            with diag.busy(f"event {name}"):
                self._on_event(name, payload)
        finally:
            ms = (time.monotonic() - t) * 1000
            if ms > 300:
                log.warning("event %s took %.0f ms in the window", name, ms)
            elif ms > 50:
                log.debug("event %s: %.0f ms", name, ms)

    def _on_event(self, name, payload):
        if name == "sync_changed":
            self._sync_text()
        elif name == "poll_state":  # a round began or ended: "updating…" / "updated at"
            self._slow_text()
            self._curtain_swing()
        elif name == "lanes_updated":
            for lane in payload:
                w = self.lane_widgets.get(lane)
                if isinstance(w, LaneWidget):
                    w.refresh()
            self.update_badges()
        elif name == "arrived":
            # an open thread someone just answered in takes the answer in by itself
            for w in self.extra_tabs():
                if isinstance(w, ThreadWidget) and w.loaded and any(
                        sid not in w.statuses and parent in w.statuses
                        for sid, parent in payload):
                    w.reload(quiet=True)
        elif name == "thread_grew":  # replies fetched from other servers
            for w in self.extra_tabs():
                if isinstance(w, ThreadWidget) and w.root is not None and \
                        w.root.id == payload:
                    w.reload(quiet=True)
        elif name == "parents":
            for w in self.lane_widgets.values():
                if isinstance(w, LaneWidget):
                    w.refresh()
            for w in self.extra_tabs():
                if isinstance(w, AccountWidget):
                    w.render()
        elif name == "read_changed":
            for w in list(self.lane_widgets.values()) + self.extra_tabs():
                apply = getattr(w, "apply_read", None)  # a tab without read marks: none
                if apply is not None:
                    apply(payload)
            self.update_badges()
        elif name == "status_updated":
            changed = self.ctx.view.entry(payload) if isinstance(payload, dict) and \
                payload.get("id") else None
            for w in list(self.lane_widgets.values()) + self.extra_tabs():
                if getattr(w, "view", None) is not None:  # Activity has none
                    w.view.refresh_status(changed)
        elif name == "status_deleted":
            for w in list(self.lane_widgets.values()) + self.extra_tabs():
                if getattr(w, "view", None) is not None:
                    w.view.remove_status(payload)
            self.statusBar().showMessage(_("deleted"), 4000)
        elif name == "first_poll_done":
            if self.statusBar().currentMessage() == getattr(self, "_waiting_text", None):
                self.statusBar().showMessage(self._hello, 5000)
        elif name == "rate_limited":
            # the server asks to wait: once, with when, not an error per lane
            self.statusBar().showMessage(results.rate_text(payload), 20_000)
        elif name == "capabilities_changed":
            # the server answered for a feature: what offers it shows or hides now
            for w in list(self.lane_widgets.values()) + self.extra_tabs():
                fn = getattr(w, "capabilities_changed", None)
                if fn is not None:
                    fn()
        elif name == "me_updated":
            self._show_me(payload)
            for w in self.extra_tabs():
                if isinstance(w, AccountWidget) and w.mine:
                    w.reload_account()
            self.statusBar().showMessage(_("profile_saved"), 5000)
        elif name in ("activity_updated", "activity_seen"):
            w = self.lane_widgets.get("activity")
            if w:
                w.refresh()
            self.update_badges()
        elif name == "lists_changed":
            self._rebuild_lists()
            # who is hidden where may have changed (lists.hide_members): lanes redraw
            for w in self.lane_widgets.values():
                if isinstance(w, LaneWidget):
                    w.refresh()
            self.update_badges()
        elif name == "subs_changed":
            for w in self.extra_tabs():
                if isinstance(w, ThreadWidget):
                    w.update_sub_button()
        elif name == "requests_updated":
            w = self.lane_widgets.get("requests")
            if w:
                w.refresh()
            self.update_badges()
        elif name == "notify":
            self._notify(payload)
        elif name == "sound":
            self.sounds.play(payload, focused=self.isActiveWindow())
        elif name == "prefetch":  # pictures of posts just come: to disk, ahead of time
            self.images.prefetch(payload)
        elif name == "prefetch_video":  # their videos too (feed.prefetch = "all")
            self.images.prefetch_video(payload)
        elif name == "error":
            self.statusBar().showMessage(_("error", err=payload), 10_000)
        elif name == "auth_failed":
            QMessageBox.warning(self, _("auth_failed_title"), _("auth_failed"))
            self.relogin()

    def _notify(self, items):
        self.notifier.notify(items)

    def _notification_clicked(self, note):
        self.show_raise()
        if note.thread:
            self.open_thread(note.thread)
        else:
            self.select_lane(note.lane)

    # ---- tabs ---------------------------------------------------------------------------
    def extra_tabs(self):
        return [self.tabs.widget(i) for i in range(self.tabs.count())
                if self.tabs.widget(i) is not self.stack]

    def _front(self, w):
        """An open tab to the front — and out from under the curtain, if it's down."""
        lifted = self.curtain_shown()
        if lifted:
            self.right_stack.setCurrentIndex(0)
        self.tabs.setCurrentWidget(w)
        log.info("tab to the front: %s%s", type(w).__name__,
                 " (curtain lifted)" if lifted else "")

    def set_full_width(self, on):
        """Posts across the whole width, or in a column of ui.max_width (remembered for
        the next start; the config's value stays what it is)."""
        if not hasattr(self, "_column_width"):
            self._column_width = self.cfg["ui"]["max_width"] or 760
        self.cfg["ui"]["max_width"] = 0 if on else self._column_width
        self.core.set_state("full_width", bool(on))
        from .feed import FeedView
        for view in self.findChildren(FeedView):
            view.apply_width()
        log.info("posts: %s", "full width" if on else f"{self._column_width} px column")

    def _add_tab(self, w, title):
        lifted = self.curtain_shown()
        log.info("tab opened: %s%s", type(w).__name__, " (curtain lifted)" if lifted else "")
        i = self.tabs.addTab(w, title)
        if lifted:  # a tab opened from the curtain: show it, not the curtain
            self.right_stack.setCurrentIndex(0)
        self.tabs.setCurrentIndex(i)

    def open_thread(self, sid):
        post = self.ctx.view.by_id(sid)
        if post:
            sid = post.id  # a boost's id: the post inside
        for w in self.extra_tabs():
            if isinstance(w, ThreadWidget) and sid in w.statuses:
                self._front(w)
                w.focus_on(sid)
                return
        self._add_tab(ThreadWidget(self, sid), _("thread_loading"))

    def close_all_tabs(self):
        """Every tab of the messages window closed (ui.split_tabs = "close"): threads,
        profiles, talks go, the lanes' tabs too; the window stays hidden."""
        for w in self.extra_tabs():
            self.tabs.removeTab(self.tabs.indexOf(w))
            w.deleteLater()
        if self.msg_tabs is not None:
            self.msg_tabs._busy = True
            try:
                while self.msg_tabs.count():
                    self.msg_tabs.removeTab(0)
            finally:
                self.msg_tabs._busy = False

    def open_talk(self, account):
        """Our private talk with someone, a tab of its own (the split layout)."""
        from .dock import TalkWidget
        for w in self.extra_tabs():
            if isinstance(w, TalkWidget) and w.who.id == account.id:
                self._front(w)
                return w
        w = TalkWidget(self, account)
        self._add_tab(w, w.title)
        return w

    def open_place(self, name, arg="", tab=""):
        """A place of common/places.py in a window of its own (qt/place.py): collections,
        and any place the windows have no widget of their own for."""
        from .place import PlaceDialog
        dlg = PlaceDialog(self, name, arg, tab)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.show()
        return dlg

    def open_account(self, acc_id):
        for w in self.extra_tabs():
            if isinstance(w, AccountWidget) and w.acc_id == acc_id:
                if self.tabs.currentWidget() is w and not self.curtain_shown():
                    log.info("profile %s: already in front, back to the top", acc_id)
                    w.show_info()  # already here: back up to who this is
                else:
                    self._front(w)
                return
        self._add_tab(AccountWidget(self, acc_id), "@…")

    def open_tag_group(self, spec):
        """Several hashtags as one tab (from the search); saved ones live in the sidebar."""
        from ...core import taggroups
        lane = taggroups.lane_name(spec)
        if lane in self.lane_items:
            self.select_lane(lane)
            return
        for w in self.extra_tabs():
            if isinstance(w, TagGroupWidget) and w.key == taggroups.key(spec):
                self._front(w)
                return
        w = TagGroupWidget(self, spec)
        self._add_tab(w, w.title)

    def open_search(self, query=""):
        from ...core import taggroups
        spec = taggroups.parse(query.strip())
        if spec:
            self.open_tag_group(spec)
            return
        for w in self.extra_tabs():
            if isinstance(w, SearchWidget):
                self._front(w)
                w.edit.setText(query)
                w.run(query)
                return
        self._add_tab(SearchWidget(self, query), _("search_title"))

    def open_people(self, acc, which):
        """Whom an Account follows, or who follows them."""
        for w in self.extra_tabs():
            if isinstance(w, PeopleWidget) and w.acc_id == acc.id and w.which == which:
                self._front(w)
                return
        w = PeopleWidget(self, acc, which)
        self._add_tab(w, w.title)

    def open_accounts(self, key, title, fetch, **kw):
        """A tab with a list of people (who liked, suggestions, the directory…)."""
        for w in self.extra_tabs():
            if isinstance(w, AccountsWidget) and w.key == key:
                self._front(w)
                return
        w = AccountsWidget(self, key, title, fetch, **kw)
        self._add_tab(w, title)

    def open_reactions(self, st, kind):
        """Who liked (kind="favourited_by") or boosted ("reblogged_by") a post: as my
        server knows, then — for a post from elsewhere — as its own server knows."""
        title = _("who_" + kind, text=snippet(st, 30))
        host = self.ctx.view.origin_host(st)
        kw = {}
        if host and self.cfg["feed"].get("remote_people", True):
            kw = {"origin": lambda have: self.ctx.view.who_reacted_from_origin(st, kind, have),
                  "origin_label": _("people_more_from", host=host)}
        self.open_accounts(f"{kind}:{st.id}", title,
                           lambda cur: self.ctx.view.who_reacted(st, kind, cur), **kw)

    def open_suggestions(self):
        self.open_accounts("suggestions", _("suggestions_title"), self.core.suggestions,
                           dismiss=self.core.dismiss_suggestion)

    def open_directory(self, local):
        key = "directory_local" if local else "directory_title"
        self.open_accounts(key, _(key), lambda cur: self.core.directory(cur, local))

    def open_trends(self):
        for w in self.extra_tabs():
            if isinstance(w, TrendsWidget):
                self._front(w)
                w.reload()
                return
        w = TrendsWidget(self)
        self._add_tab(w, w.title)

    def show_server_info(self):
        self.bridge.call(self.ctx.view.server_info(),
                         ok=lambda info: ServerInfoDialog(self, info).exec(), fail=self.error)

    def open_quotes(self, post):
        post = self._post(post)
        for w in self.extra_tabs():
            if isinstance(w, QuotesWidget) and w.status.id == post.id:
                self._front(w)
                return
        w = QuotesWidget(self, post)
        self._add_tab(w, w.title)

    def open_link_posts(self, url):
        """Who else shared this link: a tab of their posts (common/links.py asks)."""
        for w in self.extra_tabs():
            if isinstance(w, LinkPostsWidget) and w.url == url:
                self._front(w)
                return
        w = LinkPostsWidget(self, url)
        self._add_tab(w, w.title)

    def ask_remote_lane(self):
        """≡ → Another server's lane…: which server, then its tab."""
        from ...core.remote import server_host
        text, ok = QInputDialog.getText(self, _("remote_public").rstrip("…"),
                                        _("remote_public_q"))
        if not ok or not text.strip():
            return
        host = server_host(text)
        if not host:
            self.error(_("remote_public_bad", text=text.strip()))
            return
        self.open_remote_lane(host)

    def open_remote_lane(self, host):
        """Another server's public lane in a tab (one per server)."""
        for w in self.extra_tabs():
            if isinstance(w, RemoteLaneWidget) and w.host == host:
                self._front(w)
                return w
        w = RemoteLaneWidget(self, host)
        self._add_tab(w, w.title)
        return w

    def open_tag(self, tag):
        for w in self.extra_tabs():
            if isinstance(w, TagWidget) and w.tag.lower() == tag.lower():
                self._front(w)
                return
        self._add_tab(TagWidget(self, tag), "#" + tag)

    def resolve_link(self, url):
        """A fediverse address: find it through my server and open it here."""
        self.statusBar().showMessage(_("resolving", url=url), 10000)

        def done(found):
            if not found:
                self.statusBar().showMessage(_("resolve_browser"), 4000)
                self.open_url(url)
            elif isinstance(found, Account):
                self.statusBar().clearMessage()
                self.open_account(found.id)
            else:
                self.statusBar().clearMessage()
                self.open_thread(found.id)
        self.bridge.call(self.ctx.view.resolve(url), ok=done,
                         fail=lambda _e: (self.statusBar().clearMessage(), self.open_url(url)))

    def retitle(self, w):
        i = self.tabs.indexOf(w)
        if i >= 0:
            self.tabs.setTabText(i, w.title if len(w.title) < 40 else w.title[:39] + "…")
            self.tabs.setTabToolTip(i, w.title)

    def close_tab(self, i):
        w = self.tabs.widget(i)
        if w is None or (w is self.stack and self.roster is None):
            return
        if w is self.stack:  # the split layout (Ctrl+W): the lane's tab above goes
            self.msg_tabs.close_current()
            return
        log.info("tab closed: %s", type(w).__name__)
        self.tabs.removeTab(i)
        _let_go(w)
        w.deleteLater()
        if self.msg_tabs is not None:
            self.msg_tabs.after_close()

    def vote(self, post, choices):
        sid = post.id
        self.bridge.call(self.core.vote(self.ctx.view.raw(post), choices),
                         ok=lambda _s: self.statusBar().showMessage(_("poll_voted"), 4000),
                         fail=lambda e: (self.error(e), self._rebuild_cards(sid)))

    def _rebuild_cards(self, sid):
        """Cards of this post drawn again from what they hold (after a failed action
        left a button saying "sending…")."""
        for w in list(self.lane_widgets.values()) + self.extra_tabs():
            view = getattr(w, "view", None)
            for row in (view.rows.values() if view is not None else ()):
                if row.status_id is not None and row.real_id == sid:
                    row._build()

    def read_up_to(self, sid):
        """This post and everything older in the view it's in: read."""
        from ..common.lane import read_up_to
        view = self.current_view()
        specs = [s for s in (view.model if view is not None else []) if s.entry is not None]
        self.core.mark_read(read_up_to([s.entry for s in specs], sid))

    def current_view(self):
        """The FeedView on screen: the current lane, thread or profile."""
        w = self.tabs.currentWidget()
        if w is self.stack:
            w = self.stack.currentWidget()
        return getattr(w, "view", None)

    def refresh(self):
        w = self.tabs.currentWidget()
        if isinstance(w, ThreadWidget):
            w.reload()
        self.core.poll_now()

    # ---- links & actions --------------------------------------------------------------
    def copy_handle(self, acct):
        """@user@server into the clipboard: what to paste to mention or find them."""
        from ...model.text import full_handle
        handle = full_handle(acct, (self.core.auth or {}).get("server", ""))
        if handle:
            QGuiApplication.clipboard().setText(handle)
            self.statusBar().showMessage(_("handle_copied", handle=handle), 5000)

    def open_help(self, page="index", anchor=""):
        """≡ → Help: the help panel over the lanes, at `page` — the same panel each time,
        where it was left when no page is asked for. No shortcut on purpose."""
        from .help import HelpPanel
        if not self.isVisible():  # the split layout: the help lives in the messages window
            self.show_raise()
        if self.help_panel is None:
            self.help_panel = HelpPanel(self)
        panel = self.help_panel
        if page != "index" or anchor or panel.current is None:
            panel.show_page(page, anchor)
        panel.show()
        panel.raise_()
        return panel

    def open_url(self, url):
        """Someone else's address: only the web (and mail, XMPP…); see opener."""
        from .opener import open_link
        if url and not open_link(url):
            self.statusBar().showMessage(_("link_refused"), 6000)

    def open_from_outside(self, url):
        """`fedtail open URL` (a browser, a terminal): the post or profile here, in front."""
        from urllib.parse import quote
        log.info("open from outside: %s", QUrl(url).host() or "?")
        self.show_raise()
        if url.startswith("web+ap://"):
            url = "https://" + url[len("web+ap://"):]
        self.on_link("fedtail:resolve/" + quote(url, safe=""))

    def open_when_ready(self, url, tries=60):
        """The window was started by `fedtail open URL`: open it once connected."""
        if self.core.me:
            self.open_from_outside(url)
        elif tries:
            QTimer.singleShot(500, lambda: self.open_when_ready(url, tries - 1))

    def on_link(self, url):
        """A fedtail: link (or one to the outside): common/links.py decides what it does,
        _LinkHost below is how this window answers it."""
        if not url.startswith("fedtail:"):
            log.info("link: browser (%s)", QUrl(url).host() or "?")
        self.links.open(url)

    def _post(self, x):
        """A Post from a Post, a Share or (older callers) a stored status."""
        return real_entry(x if isinstance(x, (Post, Share)) else self.ctx.view.entry(x))

    def _redrafted(self, d):
        """The deleted post back in the composer, as it was typed (d: a Redraft)."""
        parent = self.ctx.view.by_id(d.reply_to) if d.reply_to else None
        dlg = Compose(self, reply_to=parent)
        dlg.text.setPlainText(d.text)
        if d.warning:
            dlg.cw.setText(d.warning)
            dlg.cw.setVisible(True)
        i = dlg.vis.findData(d.visibility)
        if i >= 0:
            dlg.vis.setCurrentIndex(i)
        if d.language:
            dlg.set_language(d.language)
        dlg.show()
        if d.media:
            self.statusBar().showMessage(_("redraft_media", n=d.media), 8000)

    def act_as(self, st, tag, action):
        """★ / ♻ / ↩ from another account of the window: the post found on its server."""
        self.statusBar().showMessage(_("act_as_wait"), 4000)
        v = self.ctx.view

        def done(got):
            if action == "reply":
                self.compose(got)
            else:
                via = v.via(got) if got is not None else ""
                self.statusBar().showMessage(
                    _("act_as_done", acct=via or "@" + (v.me.handle if v.me else "")), 5000)
        self.bridge.call(v.act_as(self._post(st), tag, "find" if action == "reply" else action),
                         ok=done, fail=self.error)

    def read_whole(self, st):
        """📄 The whole text from the author's server: an article your server cut to a
        title and a link, an event with its time and place."""
        self.statusBar().showMessage(_("long_form_wait"), 4000)
        st = self._post(st)
        self.bridge.call(self.ctx.view.long_form(st), ok=lambda d: self._show_whole(st, d),
                         fail=self.error)

    def _show_whole(self, st, d):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser

        from ..richtext import esc, sanitize

        def fmt_time(iso):
            from datetime import datetime
            try:
                t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                return (t.astimezone() if t.tzinfo else t).strftime("%d.%m.%Y %H:%M")
            except ValueError:
                return esc(iso)
        if not d:
            self.error(_("long_form_none"))
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(d["name"] or _("long_form_title"))
        dlg.resize(min(820, self.width() - 60), min(760, self.height() - 60))
        lay = QVBoxLayout(dlg)
        parts = []
        if d["name"]:
            parts.append(f"<h2>{esc(d['name'])}</h2>")
        event = [x for x in (
            "🗓 " + " — ".join(fmt_time(t) for t in (d["start"], d["end"]) if t)
            if d["start"] else "", "📍 " + esc(d["location"]) if d["location"] else "") if x]
        if event:
            parts.append("<p><b>" + "<br>".join(event) + "</b></p>")
        if d["summary"]:
            parts.append(f"<p><i>{sanitize(d['summary'])}</i></p>")
        parts.append(sanitize(d["content"]) or esc(snippet(st, 2000)))
        view = QTextBrowser()
        view.setOpenLinks(False)
        view.anchorClicked.connect(lambda u: self.on_link(u.toString()))
        view.setHtml("".join(parts))
        lay.addWidget(view, 1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        if d["url"]:
            b = box.addButton(_("open_browser"), QDialogButtonBox.ButtonRole.ActionRole)
            b.clicked.connect(lambda: self.open_url(d["url"]))
        box.rejected.connect(dlg.reject)
        lay.addWidget(box)
        dlg.show()

    def play_video(self, m, items=None):
        """A video or a gifv: over the window (ui.video_player), or in the browser.
        items: all the videos and gifs of the post, to go between them there."""
        from . import player
        if self.cfg["ui"].get("video_player", "internal") == "internal" and \
                player.available():
            player.VideoOverlay(self, self.ctx, m, loop=m.kind == "gifv",
                                items=items)
        else:
            self.open_url(player.media_url(m))

    def show_images(self, media, index):
        if self.cfg["ui"]["image_viewer"] == "browser":
            m = media[index]
            self.open_url(m.url or m.remote_url)
            return
        ImageOverlay(self, self.ctx, media, index)

    def answer_follow(self, acc_id, approve):
        self.bridge.call(self.core.answer_follow(acc_id, approve))

    def compose(self, reply_to=None, attach=(), text=""):
        if not self.core.me:
            return
        if self.dock is not None and not attach and not (text and reply_to):
            # the split layout: a reply or a new post goes into the input line
            self.show_raise()
            if isinstance(reply_to, str):
                reply_to = self.ctx.view.by_id(reply_to)
            if reply_to is not None:
                self.dock.reply_to(self._post(reply_to))
            elif text:
                self.dock.start_with(text)
            else:
                self.dock.text.setFocus()
            return
        self.compose_window(reply_to, attach, text)

    def write_to(self, account):
        """A private message to someone: the input line in the split layout, else the
        Compose window, "@them " and direct."""
        if self.dock is not None:
            self.show_raise()
            self.open_talk(account)  # a tab of our own: only our private messages
            self.dock.write_to(account)
            return
        dlg = Compose(self, text="@" + account.handle + " ")
        i = dlg.vis.findData("direct")
        if i >= 0:
            dlg.vis.setCurrentIndex(i)
        dlg.show()

    def compose_window(self, reply_to=None, attach=(), text=""):
        """The full Compose window, whatever the layout (⤢ from the input line)."""
        if not self.core.me:
            return
        if not self.isVisible():  # a panel of the main window: the window comes too
            self.show_raise()
        Compose(self, reply_to, attach, text).show()

    def quote_reply(self, st, text, whole=False):
        """Reply quoting `text`: into the reply to this post that is already open —
        where its cursor is, to answer a post sentence by sentence — or a new one."""
        if not self.core.me:
            return
        st = self._post(st)
        for c in list(getattr(self, "open_composes", [])):
            try:
                if c.isVisible() and c.reply_to and c.reply_to.id == st.id and \
                        not c.edit and not c.invite:
                    c.insert_quote(text, whole)
                    return
            except RuntimeError:  # closed and gone
                continue
        dlg = Compose(self, reply_to=st)
        dlg.show()
        dlg.insert_quote(text, whole, at_end=True)

    # pictures dropped anywhere on the window start a new post with them
    def dragEnterEvent(self, e):
        if media_paths(e.mimeData()) or e.mimeData().hasImage():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = media_paths(e.mimeData())
        if not paths and e.mimeData().hasImage():
            saved = save_image(self.core, QImage(e.mimeData().imageData()))
            paths = [saved] if saved else []
        if paths:
            e.acceptProposedAction()
            self.compose(attach=paths)

    def translate_post(self, post, done):
        """Ask the server for a translation; done({"lang", "provider", "html"}) in the
        card, or an error."""
        if not self.core.caps.translation:
            self.error(_("translate_none"))
            return

        def got(tr):  # a Translation
            done({"lang": tr.lang, "provider": tr.provider, "html": tr.html})
        self.bridge.call(self.ctx.view.translate(post), ok=got, fail=self.error)

    def show_filtered(self):
        from .filtered import FilteredDialog
        dlg = FilteredDialog(self)
        dlg.show()
        return dlg

    def _remind_filtered(self):
        """notify.filtered = "remind": say once at start if someone is held back."""
        def got(res):
            if res and res["pending"]:
                self.statusBar().showMessage(_("filtered_waiting", n=res["pending"]), 30_000)
        self.bridge.call(self.core.filtered(), ok=got, fail=lambda _e: None)

    def show_scheduled(self):
        """Posts waiting on the server to go out at their time; any can be cancelled."""
        from PySide6.QtWidgets import QListWidget, QListWidgetItem, QPushButton
        dlg = QDialog(self)
        dlg.setWindowTitle(_("scheduled_title"))
        dlg.resize(520, 360)
        lay = QVBoxLayout(dlg)
        lst = QListWidget()
        lay.addWidget(lst, 1)
        cancel = QPushButton(_("scheduled_cancel"))
        cancel.setObjectName("tool")
        lay.addWidget(cancel)

        def fill(items):
            lst.clear()
            for s in items:  # Scheduled
                it = QListWidgetItem(f"{self.theme.date(s.at) if s.at else ''} — "
                                     f"{s.text[:120]}")
                it.setData(Qt.ItemDataRole.UserRole, s.id)
                lst.addItem(it)
            if not items:
                lst.addItem(_("scheduled_none"))

        def load():
            self.bridge.call(self.ctx.view.scheduled(), ok=fill, fail=self.error)

        def drop():
            it = lst.currentItem()
            sid = it.data(Qt.ItemDataRole.UserRole) if it else None
            if sid:
                self.bridge.call(self.core.cancel_scheduled(sid), ok=lambda _r: load(),
                                 fail=self.error)
        cancel.clicked.connect(drop)
        load()
        dlg.show()
        return dlg, lst

    def report(self, st):
        """Complain about a post to my server's moderators — with why, what kind, and
        whether the author's server should hear too."""
        from PySide6.QtWidgets import QCheckBox, QComboBox, QDialogButtonBox, QPlainTextEdit
        st = self._post(st)
        acc = st.author
        dlg = QDialog(self)
        dlg.setWindowTitle(_("report_title", acct=acc.handle))
        dlg.resize(480, 320)
        lay = QVBoxLayout(dlg)
        quote = QLabel(snippet(st, 200))
        quote.setWordWrap(True)
        quote.setObjectName("muted")
        lay.addWidget(quote)
        kind = QComboBox()
        for key in ("spam", "legal", "violation", "other"):
            kind.addItem(_("report_" + key), key)
        kind.setCurrentIndex(3)
        lay.addWidget(kind)
        # "Breaks the server's rules": which ones (the server's list, ticked)
        rules_box = QWidget()
        rules_lay = QVBoxLayout(rules_box)
        rules_lay.setContentsMargins(0, 0, 0, 0)
        rules_lay.addWidget(QLabel(_("report_rules")))
        rule_ticks = []  # (rule id, QCheckBox)
        rules_box.setVisible(False)
        lay.addWidget(rules_box)

        def got_rules(info):
            for rid, (text, _hint) in zip(info.rule_ids, info.rules, strict=False):
                box = QCheckBox(text)
                box.setToolTip(_hint or text)
                rule_ticks.append((rid, box))
                rules_lay.addWidget(box)

        def kind_changed(_i=None):
            on = kind.currentData() == "violation"
            rules_box.setVisible(on)
            if on and not rule_ticks and not dlg.rules_asked:
                dlg.rules_asked = True
                self.bridge.call(self.ctx.view.server_info(), ok=got_rules, fail=self.error)
        dlg.rules_asked = False
        kind.currentIndexChanged.connect(kind_changed)
        why = QPlainTextEdit()
        why.setPlaceholderText(_("report_why"))
        lay.addWidget(why, 1)
        remote = "@" in acc.handle
        fwd = QCheckBox(_("report_forward", host=acc.handle.split("@")[-1]))
        fwd.setChecked(remote and self.cfg["post"].get("report_forward", True))
        fwd.setVisible(remote)
        lay.addWidget(fwd)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        send = buttons.addButton(_("report_send"), QDialogButtonBox.ButtonRole.AcceptRole)
        send.setObjectName("primary")
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)

        def go():
            ids = [rid for rid, box in rule_ticks if box.isChecked()]
            if kind.currentData() == "violation" and not ids:
                self.statusBar().showMessage(_("report_rules_need"), 6000)
                return
            dlg.accept()
            self.bridge.call(self.ctx.view.report(st, why.toPlainText().strip(), fwd.isChecked(),
                                                  kind.currentData(),
                                                  **({"rule_ids": ids} if ids else {})),
                             ok=lambda _r: self.statusBar().showMessage(_("report_sent"), 6000),
                             fail=self.error)
        send.clicked.connect(go)
        dlg.kind, dlg.rule_ticks, dlg.send = kind, rule_ticks, go  # (tests)
        dlg.show()
        return dlg

    def show_history(self, st):
        """The versions of an edited post, oldest first, as the server keeps them."""
        from PySide6.QtWidgets import QTextBrowser

        from ..richtext import history_html
        dlg = QDialog(self)
        dlg.setWindowTitle(_("history_title"))
        dlg.resize(560, 480)
        lay = QVBoxLayout(dlg)
        view = QTextBrowser()
        view.setOpenLinks(False)
        lay.addWidget(view)
        view.setPlainText(_("loading"))

        def got(versions):
            view.setHtml(history_html(versions, self.theme.date, self.theme.css("link"))
                         or _("history_none"))
        self.bridge.call(self.ctx.view.history(self._post(st)), ok=got,
                         fail=lambda e: view.setPlainText(_("load_failed", err=e)))
        dlg.show()

    def after_post(self, st, reply_to):
        self.statusBar().showMessage(_("sent"), 4000)
        if reply_to:
            for w in self.extra_tabs():
                if isinstance(w, ThreadWidget) and reply_to.id in w.statuses:
                    w.reload()
        elif st is not None:
            self.open_thread(st.id)

    # ---- window -------------------------------------------------------------------------
    def error(self, err):
        self.statusBar().showMessage(_("error", err=err), 10_000)

    def save_image(self, media):
        url = media.url or media.remote_url or media.preview
        if not url:
            return
        from ...core import saving
        self.bridge.call(self.images.save(url, saving.save_dir(self.cfg)),
                         ok=lambda p: self.statusBar().showMessage(_("saved_to", path=str(p)),
                                                                   8000),
                         fail=lambda e: self.error(_("save_failed", err=e)))

    def debug_census(self):
        """Stats, trend and the census of Python objects and Qt widgets, now."""
        with diag.busy("diag: census from the menu"):
            s = diag.check_now(int(self.cfg["debug"].get("rss_warn_mb", 1500)), objects=True)
            census = getattr(self, "widget_census", None)
            if census:
                census()
        self.statusBar().showMessage(_("debug_census_done", rss=s["rss_mb"],
                                       objects=s["py_objects"]), 8000)

    def federation_status(self):
        """Debug → Federation status: how my server is doing and what keeps failing,
        here and on other servers (core.health; fedstatus draws it). One window, brought
        to the front when asked again."""
        from PySide6.QtWidgets import QDialogButtonBox

        from .social import FederationWidget
        dlg = getattr(self, "_fed_dlg", None)
        if dlg is not None and dlg.isVisible():
            dlg.raise_()
            dlg.activateWindow()
            dlg.refresh()
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(_("fed_title"))
        dlg.resize(min(980, self.width() - 40), min(760, self.height() - 40))
        lay = QVBoxLayout(dlg)
        page = FederationWidget(self)
        lay.addWidget(page, 1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(dlg.close)
        lay.addWidget(box)
        dlg.refresh = page.refresh
        dlg.page = page
        self._fed_dlg = dlg
        log.info("federation status: opened")
        dlg.show()

    def debug_trim(self):
        freed = diag.trim_memory()
        log.info("memory: %s MB given back (from the menu)", freed)
        self.statusBar().showMessage(_("debug_trim_none") if freed is None else
                                     _("debug_trim_done", mb=freed), 6000)

    def debug_snapshot(self):
        from ... import leaks
        try:
            out = leaks.snapshot(diag.logs_dir(self.core.paths))
        except (OSError, RuntimeError) as e:
            self.error(e)
            return
        self.statusBar().showMessage(_("debug_snapshot_done", path=str(out)), 15000)

    def bug_report(self):
        try:
            diag.log_stats()
            out = diag.bug_report(self.core.paths, cfg=self.cfg)
        except OSError as e:
            self.error(e)
            return
        self.statusBar().showMessage(_("debug_report_done", path=str(out)), 15000)
        open_path(out.parent)
        self.send_report(out)

    def send_report(self, out):
        """Into debug.report_repo too, if one is set (fedtail/reportsend.py): git and
        ssh take a while — in the background, the result on the status bar."""
        from ... import reportsend
        repo = self.cfg["debug"].get("report_repo", "")
        if not repo:
            return
        self.statusBar().showMessage(_("bugreport_sending", repo=repo))
        self.bridge.call(
            self.core.submit(reportsend.send_report, out, self.cfg, self.core.paths.data_dir),
            ok=lambda where: self.statusBar().showMessage(_("bugreport_sent", where=where), 15000),
            fail=lambda err: self.statusBar().showMessage(
                _("bugreport_send_failed", repo=repo, err=err), 30000))

    def report_issue(self):
        """"Report a bug on GitHub…": the scrubbed draft to read first (qt/issue.py)."""
        from .issue import IssueDialog
        IssueDialog(self).exec()

    def open_settings(self, query=""):
        """The settings window (qt/settings.py): one at a time, brought up again."""
        from .settings import SettingsDialog
        dlg = getattr(self, "_settings", None)
        try:
            open_now = dlg is not None and dlg.isVisible()
        except RuntimeError:  # closed earlier and deleted with it (27.10: a crash on
            open_now = False  # opening the settings a second time)
        if not open_now:
            dlg = self._settings = SettingsDialog(self)
        if query:
            dlg.search.setText(query)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def about(self):
        """About fedtail: cards of what it is and what it runs on (qt/about.py)."""
        from .about import AboutDialog
        dlg = AboutDialog(self)
        dlg.exec()

    def show_raise(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def showEvent(self, e):
        super().showEvent(e)
        if self.msg_tabs is not None and not self.msg_tabs.count() and self.lane_now:
            # shown from the tray with every tab closed: the lane in front gets its tab
            QTimer.singleShot(0, lambda: self.msg_tabs.lane_opened(self.lane_now)
                              if not self.msg_tabs.count() else None)
        if self.roster is not None and not self.roster.isVisible():
            self.roster.show()  # the roster comes with the window (and with the tray)
            self.roster.refresh_soon()

    def _tray_click(self, reason):
        if reason != QSystemTrayIcon.ActivationReason.Trigger:
            return
        if self.roster is not None:  # the split layout: both windows go and come back
            if self.roster.isVisible():
                self.roster.save_place()
                self.roster.hide()
                self.hide()
            else:
                self.roster.show()
                self.roster.raise_()
                self.roster.activateWindow()
            return
        if self.isVisible() and self.isActiveWindow():
            self.hide()
        else:
            self.show_raise()

    def keyPressEvent(self, e):
        # Esc closes what's on top (the picture viewer and the find bar take it
        # themselves); the last one closes all lanes behind a curtain (ui.esc).
        mode = self.cfg["ui"]["esc"]
        if e.key() == Qt.Key.Key_Escape and not e.modifiers() and mode != "off":
            if self.find_bar.isVisible():
                self.find_bar.close_bar()
            elif self.msg_tabs is not None:
                self.msg_tabs.close_current()  # split: the tab in front, as in QIP
            elif mode == "tray":
                self.hide_away()
            elif not self.curtain_shown():
                self.close_all()
            return
        from PySide6.QtWidgets import QApplication, QLineEdit, QTextEdit
        typing = isinstance(QApplication.focusWidget(), (QLineEdit, QTextEdit))
        # Enter on the curtain opens the last lane — but not the Enter of a field (the
        # sidebar search box lets its Enter go on up here after searching)
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.curtain_shown() \
                and not typing:
            log.info("Enter on the curtain: back to the lane")
            self.select_lane(self.core.get_state("lane") or "home")
            return
        super().keyPressEvent(e)

    # ---- the curtain: every lane closed, new posts pile up unread --------------------
    def _build_curtain(self):
        w = QWidget()
        w.setObjectName("feedBody")
        w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        v = QVBoxLayout(w)
        v.addStretch(2)
        self.curtain_icon = QLabel()
        self.curtain_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.curtain_icon)
        title = QLabel(_("curtain_title"))
        title.setObjectName("laneTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)
        self.curtain_info = QLabel()
        self.curtain_info.setObjectName("muted")
        self.curtain_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.curtain_info.setWordWrap(True)
        v.addWidget(self.curtain_info)
        hint = QLabel(_("curtain_hint"))
        hint.setObjectName("muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(hint)
        v.addStretch(3)
        return w

    CURTAIN_ICON = 96

    def _curtain_swing(self):
        """The curtain's opossum swings while the lanes are being updated (a poll
        round on), and stands still otherwise — "nothing new" reads as nothing new."""
        icon = getattr(self, "curtain_icon", None)
        if icon is None:
            return
        from . import notify as notify_module
        movie = getattr(self, "_swing", None)
        try:
            state = self.ctx.view.poll_state() or {}
        except Exception:  # noqa: BLE001 — a core that doesn't say (all accounts in one)
            state = {}
        busy = bool(state.get("busy")) and self.curtain_shown() and \
            notify_module.possum_style()
        if busy:
            if movie is None:
                from PySide6.QtCore import QSize
                from PySide6.QtGui import QMovie
                movie = self._swing = QMovie(notify_module.swing_path(), parent=self)
                movie.setScaledSize(QSize(self.CURTAIN_ICON, self.CURTAIN_ICON))
                movie.setCacheMode(QMovie.CacheMode.CacheAll)
            if not getattr(self, "_swinging", False):
                icon.setMovie(movie)
                self._swinging = True
            movie.start()
        else:
            if movie is not None:
                movie.stop()
            if getattr(self, "_swinging", False) or icon.pixmap().isNull():
                icon.clear()  # (setMovie(None) keeps the movie in the label)
                icon.setPixmap(QIcon(icon_path()).pixmap(self.CURTAIN_ICON,
                                                         self.CURTAIN_ICON))
                self._swinging = False

    def curtain_shown(self):
        return self.right_stack.currentWidget() is self.curtain

    def close_all(self):
        """Esc: no lane, thread or profile on screen; nothing gets marked read, so
        whatever comes meanwhile waits, counted on the left."""
        self.find_bar.close_bar()
        for w in self.findChildren(ImageOverlay):
            w.close_viewer()
        self.right_stack.setCurrentWidget(self.curtain)
        self._curtain_swing()
        self.lanes.blockSignals(True)
        self.lanes.setCurrentItem(None)
        self.lanes.clearSelection()
        self.lanes.blockSignals(False)
        for item in self.lane_items.values():
            item.set_current(False)
        self.core.set_active_lane(None)
        self.core.set_active_lanes([])
        self._curtain_text()
        log.info("all lanes closed (Esc)")

    def _curtain_text(self):
        waiting = [(self.lane_title(n), self.lane_items[n].badge.text())
                   for n in self.lane_order if self.lane_items[n].badge.isVisible()]
        self.curtain_info.setText(
            _("curtain_waiting", items=", ".join(f"{t} — {c}" for t, c in waiting))
            if waiting else _("curtain_empty"))

    def hide_away(self):
        """Off the screen at once: to the tray if there is one, else minimized."""
        self.core.set_state(self._geometry_key(), bytes(self.saveGeometry()).hex())
        if self.tray:
            self.hide()
        else:
            self.showMinimized()

    def closeEvent(self, e):
        self.core.set_state(self._geometry_key(), bytes(self.saveGeometry()).hex())
        if self.roster is not None:
            if not self.quitting and self.roster.isVisible():
                self.hide()  # the messages window goes; the roster stays, as in QIP
                if self.cfg["ui"].get("split_tabs", "keep") == "close":
                    self.close_all_tabs()  # opened again empty, from the roster
                e.ignore()
                return
            self.roster.save_place()
            self.roster.hide()
        if self.tray and self.cfg["ui"]["close_to_tray"] and not self.quitting:
            self.hide()
            e.ignore()
            return
        super().closeEvent(e)
        log.info("main window closed, leaving")
        if self.roster is not None:  # a window of its own: it goes with this one (the
            self.roster.deleteLater()  # tour found every split window's roster alive)
            self.roster = None
        self.drop_tray()
        QApplication.quit()

    def drop_tray(self):
        """The tray icon gone from the panel now. Windows keeps a dead process's icon
        until the mouse passes over it — fedtail leaves through os._exit, past Qt's own
        clean-up, so every restart left one more there."""
        if self.tray is not None:
            tray, self.tray = self.tray, None
            tray.hide()
            tray.setContextMenu(None)
            # destroyed now, not at the next turn of the loop that never comes: its
            # destructor is what unregisters it for good (NIM_DELETE on Windows, the
            # StatusNotifierItem on KDE) — hide() alone left it there on both (26.10)
            try:
                from shiboken6 import delete
                delete(tray)
            except (ImportError, RuntimeError):  # no shiboken6, or gone already
                tray.deleteLater()
            _flush_desktop()
            log.info("tray icon removed")

    def _debug_corner(self):
        """In the debugging mode, the right end of the status bar says how this
        window is drawn: theme, style, font, Qt platform, scale, build."""
        from ... import diag
        if not diag.is_on():
            return
        from PySide6 import QtCore

        from ..common import corner
        app = QApplication.instance()
        screen = app.primaryScreen()
        f = app.font()
        style = app.style()
        # (name() is "" in some PySide6 builds: the corner showed "· ·")
        style_name = style.name() or style.objectName() or type(style).__name__
        label = QLabel(corner.text(
            self.theme.id, "Qt " + QtCore.qVersion(), style_name,
            f"{f.family()} {f.pointSizeF():g}pt", app.platformName(),
            screen.devicePixelRatio() if screen else 0))
        label.setObjectName("muted")
        label.setToolTip(_("debug_corner_tip"))
        self.statusBar().addPermanentWidget(label)

    @staticmethod
    def _geometry_key():
        """The window's size and place, kept apart for the one-file build: its Qt may
        scale differently from the system's, and one would stretch the other's window."""
        return "geometry.onefile" if getattr(sys, "frozen", False) else "geometry"

    def quit(self):
        log.info("quit (tray icon: %s)", "yes" if self.tray is not None else "none")
        self.quitting = True
        self.close()
        self.drop_tray()
        QApplication.quit()


def _let_go(tab):
    """A closed tab's Python side made light before it goes: PySide keeps a tab's wrapper
    alive past its deletion through the connections of its parts (the tabs stress test:
    a profile's media filter with its menu's actions, a feed's scroll bar, every tab),
    so what it holds is dropped here — the wrapper alone is left, if anything."""
    mf = getattr(tab, "media_filter", None)
    if mf is not None:
        mf.actions = {}
        mf.on_change = lambda: None
    view = getattr(tab, "view", None)
    if view is not None and hasattr(view, "verticalScrollBar"):
        try:
            view.verticalScrollBar().valueChanged.disconnect()
        except (RuntimeError, TypeError):  # nothing connected, or gone already
            pass
        for name in ("rows", "order"):
            if isinstance(getattr(view, name, None), (dict, list)):
                setattr(view, name, type(getattr(view, name))())
    for name in ("items", "_first_page"):
        if isinstance(getattr(tab, name, None), list):
            setattr(tab, name, [])


def _flush_desktop(seconds=0.25):
    """What was just asked of the desktop (the tray icon hidden) sent out before the
    process ends: fedtail leaves through os._exit, which takes the unsent along. On KDE an
    icon that came through the X11 tray (xembed-sni-proxy) stayed in the panel until the
    mouse passed over it (split layout, quit from the roster, 26.10)."""
    from PySide6.QtGui import QGuiApplication
    app = QApplication.instance()
    if app is None:
        return
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        getattr(QGuiApplication, "sync", lambda: None)()  # the window system's queue
        time.sleep(0.02)

