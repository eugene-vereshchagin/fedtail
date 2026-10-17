"""Main window: lanes on the left, tabs (lane / threads / accounts) on the right."""

import logging
import sys
import time
from dataclasses import dataclass
from urllib.parse import unquote

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QIcon, QImage, QKeySequence, QShortcut
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
from ...core.model import real, snippet
from ...i18n import _
from .. import themefile
from . import badge
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
    TagWidget,
    ThreadWidget,
)
from .find import FindBar
from .images import Images
from .login import LoginDialog
from .notify import Notifier, icon_path
from .profile import ProfileDialog
from .silence import SilenceDialog
from .social import AccountsWidget, QuotesWidget, ServerInfoDialog, TrendsWidget
from .viewer import ImageOverlay

log = logging.getLogger(__name__)

# icons from the desktop theme (Breeze names); emoji are missing from many fonts
LANE_ICON = {"people": "system-users", "comments": "mail-replied",
             "mentions": "mail-mark-important", "subs": "mail-thread-watch",
             "bots": "applications-system",
             "mine": "document-edit", "local": "go-home", "global": "applications-internet",
             "requests": "list-add-user", "list": "view-list-details",
             "activity": "rating", "bookmarks": "bookmarks", "direct": "mail-message",
             "favourites": "starred-symbolic"}


BADGE_KIND = {"comments": "hot", "bots": "quiet", "activity": "quiet"}


class LaneItem(QWidget):
    """A lane in the sidebar: icon, name, unread badge."""

    def __init__(self, name, theme, number, title=None):
        super().__init__()
        self.name, self.theme = name, theme
        self.title = title or _("lane_" + name)
        self.current = False
        tip = _("tip_" + name) if not name.startswith("list:") else ""
        tip = "" if tip == "tip_" + name else tip
        self.setToolTip(" ".join(x for x in (tip, f"(Alt+{number})" if number <= 9 else "") if x))
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(10)
        if theme.shape["lane_icons"]:
            icon = QLabel()
            ic = QIcon.fromTheme(LANE_ICON.get(name.split(":")[0], ""))
            if not ic.isNull():
                icon.setPixmap(ic.pixmap(18, 18))
            icon.setFixedWidth(18)
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

    def set_count(self, n):
        self.count = n
        self.badge.setText(str(n) if n < 1000 else "999+")
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
    me_id: str = ""
    subscribed: object = None  # status -> is its thread followed
    fill_list_menu: object = None  # (QMenu, account) -> fill "add to list"
    save_image: object = None      # media attachment -> save it to disk
    vote: object = None            # (status, [option indexes]) -> vote in its poll
    refresh_poll: object = None    # set when "refresh" next to a poll's results works
    translate: object = None       # (status, done(translation)) -> ask the server
    supports: object = lambda _feature: True  # can my server do this (core.supports)
    play_video: object = None      # media attachment -> play it (or open in the browser)
    loop_gifv: object = None       # (label, attachment, fit) -> loop a gifv in its card
    audio_bar: object = None       # attachment -> a small audio player widget


class MainWindow(QMainWindow):
    def __init__(self, core, bridge, theme):
        super().__init__()
        self.core, self.bridge, self.theme = core, bridge, theme
        self.cfg = core.cfg
        self.images = Images(core, bridge)
        self.ctx = ViewContext(self.cfg, theme, self.images, self.on_link, self.open_url,
                               self.show_images)
        self.ctx.subscribed = core.subscribed
        self.ctx.supports = core.supports
        self.ctx.play_video = self.play_video
        from . import player
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
        self.lane_widgets = {}
        self.quitting = False
        bridge.on_error = self.error
        bridge.event.connect(self.on_event)
        bridge.raise_requested.connect(self.show_raise)

        title = "fedtail" if core.paths.profile == "default" else \
            f"fedtail [{core.paths.profile}]"
        self.base_title = title
        self.setWindowTitle(title)
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
        row.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setTabBarAutoHide(True)  # one tab: no tab bar at all
        self.tabs.addTab(self.stack, "")
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
        rv.addWidget(self.cmdline)
        self.tabs.currentChanged.connect(lambda _i: self.find_bar.view_changed())
        self.stack.currentChanged.connect(lambda _i: self.find_bar.view_changed())
        # the right side is either the tabs or the curtain (all lanes closed: Esc)
        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(right)
        self.curtain = self._build_curtain()
        self.right_stack.addWidget(self.curtain)
        row.addWidget(self.right_stack, 1)
        self.setCentralWidget(central)
        self.menuBar().hide()

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

        if QSystemTrayIcon.isSystemTrayAvailable():
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
        self.notifier.clicked.connect(self._notification_clicked)
        self.notifier.failed.connect(lambda why: self.error(_("notify_failed", err=why)))
        if self.notifier.problem:
            QTimer.singleShot(4000, lambda: self.statusBar().showMessage(
                self.notifier.problem, 20000))

    def _build_sidebar(self):
        t = self.theme
        feed_module.ICONS = bool(t.shape["icons"])
        side = QWidget()
        side.setObjectName("sidebar")
        side.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        side.setFixedWidth(272)
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
        self.account_name = QLabel(self.base_title)
        self.account_name.setObjectName("accountName")
        self.account_sub = QLabel("")
        self.account_sub.setObjectName("accountSub")
        names.addWidget(self.account_name)
        names.addWidget(self.account_sub)
        acc.addLayout(names, 1)
        menu_btn = QToolButton()
        menu_btn.setObjectName("menu")
        menu_btn.setToolTip(_("menu"))
        ic = QIcon.fromTheme("application-menu", QIcon.fromTheme("open-menu-symbolic")) \
            if t.shape["icons"] else QIcon()
        if ic.isNull():
            menu_btn.setText("≡")
        else:
            menu_btn.setIcon(ic)
        menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_btn.setMenu(self._app_menu())
        acc.addWidget(menu_btn, 0, Qt.AlignmentFlag.AlignTop)
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
            info = version.info()
            build = info["version"] + (f" · {info['date']}" if info["date"] else "")
            self.footer = QLabel(f"fedtail {build}<br>{_('made_by')}")
            self.footer.setObjectName("sideFooter")
            self.footer.setWordWrap(True)
            self.footer.setCursor(Qt.CursorShape.PointingHandCursor)
            self.footer.setToolTip(_("about"))
            self.footer.installEventFilter(self)
            v.addWidget(self.footer)
        self.sidebar = self.lanes  # older name, still used around
        self.update_badges()
        return side

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
        for p in profiles.listing():
            a = m.addAction(profiles.label(p) + ("" if p["logged_in"] else
                                                 "  " + _("not_logged_in")))
            a.setCheckable(True)
            a.setChecked(p["name"] == me)
            if p["name"] == me:
                a.setEnabled(False)
            else:
                a.triggered.connect(lambda _c=False, n=p["name"]: self.switch_profile(n))
        m.addSeparator()
        merged = m.addAction(_("accounts_merge"))
        merged.setCheckable(True)
        merged.setChecked(bool(getattr(self.core, "others", None)))
        merged.setToolTip(_("accounts_merge_tip"))
        merged.setEnabled(not self.cfg["ui"]["merge"])  # the config decides then
        merged.toggled.connect(self.set_merged)
        m.addAction(_("account_add"), self.add_profile)

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
        from ...core import profiles
        primary = getattr(self.core, "primary", self.core)
        primary.set_state("merge", ["all"] if on else [])
        log.info("merge %s: restarting", "on" if on else "off")
        profiles.launch(primary.paths.profile, after=1.5)
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
        m.addAction(_("write") + "\tCtrl+N", lambda: self.compose())
        m.addAction(_("refresh") + "\tF5", self.refresh)
        m.addAction(_("search_title") + "\tCtrl+K", lambda: self.open_search(""))
        m.addAction(_("silence_title") + "…", lambda: SilenceDialog(self).exec())
        if self.cfg["notify"]["filtered"] != "off":
            m.addAction(_("filtered_title") + "…", self.show_filtered)
        if self.cfg["post"].get("schedule", True):
            m.addAction(_("scheduled_title") + "…", self.show_scheduled)
        m.addAction(_("my_profile"), self.open_my_profile)
        people = m.addMenu(_("menu_people"))
        trends = any(self.core.supports("trends_" + k) for k in ("statuses", "tags", "links"))
        for feature, label, slot in (
                ("suggestions", _("suggestions_title"), self.open_suggestions),
                ("directory", _("directory_title"), lambda: self.open_directory(False)),
                ("directory", _("directory_local"), lambda: self.open_directory(True)),
                ("trends", _("trends_title"), self.open_trends)):
            if self.core.supports(feature) and (feature != "trends" or trends):
                people.addAction(label, slot)
        people.setEnabled(not people.isEmpty())
        m.addAction(_("server_info") + "…", self.show_server_info)
        m.addMenu(self.accounts_menu(m))
        m.addAction(_("edit_profile"), self.edit_profile)
        m.addSeparator()
        m.addAction(_("open_config"), lambda: self.open_url(
            QUrl.fromLocalFile(str(self.core.paths.config_file)).toString()))
        m.addAction(_("open_themes"), lambda: self.open_url(
            QUrl.fromLocalFile(str(themefile.user_dir())).toString()))
        m.addAction(_("open_data"), lambda: self.open_url(
            QUrl.fromLocalFile(str(self.core.paths.data_dir)).toString()))
        m.addSeparator()
        dbg = m.addMenu(_("debug_menu"))
        dbg.addAction(_("debug_logs"), lambda: self.open_url(
            QUrl.fromLocalFile(str(diag.logs_dir(self.core.paths))).toString()))
        dbg.addAction(_("debug_report"), self.bug_report)
        dbg.addAction(_("debug_notify"), lambda: self.statusBar().showMessage(
            _("debug_notify_sent", backend=self.notifier.test()), 8000))
        dbg.addAction(_("debug_stacks"), lambda: (diag.dump_stacks("asked from the menu"),
                                                  diag.log_stats(),
                                                  self.statusBar().showMessage(
                                                      _("debug_stacks_done"), 5000)))
        m.addAction(_("relogin"), self.relogin)
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
            self.open_account(self.core.me["id"])

    def edit_profile(self):
        if self.core.me:
            ProfileDialog(self).exec()

    def _connected(self, me):
        self._show_me(me)
        for w in self.theme.warnings:
            self.error(w)
        self.statusBar().showMessage(_("connected", acct=me["acct"],
                                       server=self.core.auth["server"]), 8000)
        self._after_connect(me)

    def _show_me(self, me):
        self.ctx.me_id = me["id"]
        t = self.theme
        fields = {"display_name": me.get("display_name") or me["username"],
                  "username": me["username"], "acct": me["acct"]}
        self.account_name.setText(t.words["account_title"].format(**fields))
        self.account_sub.setText(t.words["account_subtitle"].format(**fields))
        if t.shape["sidebar_avatar"]:
            self.images.get(me.get("avatar_static") or me.get("avatar"),
                            lambda pm: self.account_avatar.setPixmap(_round(pm, 44)))

    def _after_connect(self, me):
        if self.core.new_options:
            QTimer.singleShot(8500, lambda: self.statusBar().showMessage(
                _("new_options", n=len(self.core.new_options)), 30_000))
        tip = f"{self.base_title} — @{me['acct']}"
        self.setWindowTitle(tip)
        if self.tray:
            self.tray.setToolTip(tip)
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
            name = "people" if "people" in self.lane_items else self.lane_order[0]
        self.select_lane(name)

    def _connect_failed(self, err):
        if "HTTP 401" in err or "HTTP 403" in err:
            QMessageBox.warning(self, _("auth_failed_title"), _("auth_failed"))
            self.relogin()
            return
        self.statusBar().showMessage(_("server_down", err=err))
        QTimer.singleShot(20_000, self.start)

    def relogin(self):
        self.core.logout()
        self.start()

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
        if self.cfg["ui"]["sidebar_groups"]:
            groups = lanes_module.grouped(self.core.lanes)
        else:
            groups = [(None, [x.name for x in self.core.lanes if not lanes_module.is_list(x.name)]),
                      ("lists", [x.name for x in self.core.lanes if lanes_module.is_list(x.name)])]
        titles = {x["id"]: x for x in self.core.lists}
        for group, names in groups:
            if group == "lists":
                if not self.cfg["lists"]["enabled"]:
                    continue
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
                w = LaneItem(name, self.theme, len(self.lane_order) + 1,
                             title=lst["title"] if lst else None)
                if lst and lst.get("exclusive"):
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
                self.select_lane("people" if "people" in self.lane_items
                                 else self.lane_order[0], show=False)
        self.update_badges()

    def _lane_menu(self, pos):
        it = self.lanes.itemAt(pos)
        name = it.data(Qt.ItemDataRole.UserRole) if it else None
        m = QMenu(self)
        if name and name.startswith("list:"):
            lid = name[len("list:"):]
            x = next((x for x in self.core.lists if x["id"] == lid), None)
            if x is None:
                return
            m.addAction(_("list_rename"), lambda: self.rename_list(x))
            ex = m.addAction(_("list_exclusive"))
            ex.setCheckable(True)
            ex.setChecked(bool(x.get("exclusive")))
            ex.setToolTip(_("list_exclusive_tip"))
            ex.toggled.connect(lambda on: self.bridge.call(
                self.core.update_list(x["id"], x["title"], on)))
            m.addSeparator()
            m.addAction(_("list_delete"), lambda: self.delete_list(x))
        elif self.cfg["lists"]["enabled"]:
            m.addAction(_("list_new"), lambda: self.new_list())
        else:
            return
        m.exec(self.lanes.mapToGlobal(pos))

    def new_list(self, add=None):
        title, ok = QInputDialog.getText(self, _("list_new").rstrip("…"), _("list_name_q"))
        if ok and title.strip():
            self.bridge.call(self.core.create_list(title.strip(), add=add),
                             ok=lambda x: self.statusBar().showMessage(
                                 _("list_created", title=x["title"]), 5000))

    def rename_list(self, x):
        title, ok = QInputDialog.getText(self, _("list_rename"), _("list_name_q"),
                                         text=x["title"])
        if ok and title.strip() and title.strip() != x["title"]:
            self.bridge.call(self.core.update_list(x["id"], title.strip(), x.get("exclusive")))

    def delete_list(self, x):
        if QMessageBox.question(self, _("list_delete"), _("list_delete_q", title=x["title"])) \
                == QMessageBox.StandardButton.Yes:
            self.bridge.call(self.core.delete_list(x["id"]))

    def fill_list_menu(self, menu, account):
        """"Add to list" submenu of a post: every list, ticked where the author is."""
        menu.clear()
        inside = self.core.lists_of(account["id"])
        for x in self.core.lists:
            a = menu.addAction(x["title"])
            a.setCheckable(True)
            a.setChecked(x["id"] in inside)
            a.toggled.connect(lambda on, lid=x["id"], acc=account["id"]: self.bridge.call(
                self.core.set_in_list(lid, acc, on),
                ok=lambda r, on=on: self.statusBar().showMessage(
                    _("list_pending") if r == "pending" else
                    _("list_added" if on else "list_removed"), 6000),
                fail=self.error))
        if self.core.lists:
            menu.addSeparator()
        menu.addAction(_("list_new"), lambda: self.new_list(add=account["id"]))

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
        self.stack.setCurrentWidget(w)
        if show:
            self.tabs.setCurrentIndex(self.tabs.indexOf(self.stack))
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

    def current_lane(self):
        """The lane on screen, or None when a thread/profile tab is in front."""
        if self.tabs.currentWidget() is not self.stack:
            return None
        w = self.stack.currentWidget()
        return getattr(w, "name", None)

    # ---- folding sections of the sidebar -----------------------------------------------
    def folded_groups(self):
        return set(self.core.get_state("folded_groups") or [])

    def fold_group(self, group, fold=None):
        folded = self.folded_groups()
        fold = (group not in folded) if fold is None else fold
        (folded.add if fold else folded.discard)(group)
        self.core.set_state("folded_groups", sorted(folded))
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
        total = 0
        for name, item in getattr(self, "lane_items", {}).items():
            if not self.core.me:
                n = 0
            elif name == "requests":
                n = len(self.core.follow_requests)
            elif name == "activity":
                n = self.core.activity_unread()
            elif getattr(self.core.lane_by_name.get(name), "lazy", False):
                n = 0  # browse lanes have no "unread"
            else:
                n = self.core.unread_count(name)
            if name in self.cfg["ui"]["icon_count"]:
                total += n
            item.set_count(n)
        for g in getattr(self, "group_heads", {}):
            self._show_fold(g)
        if getattr(self, "curtain", None) is not None and self.curtain_shown():
            self._curtain_text()
        if self.tray:
            base = self.windowTitle()
            self.tray.setToolTip(_("tray_new", title=base, n=total) if total else base)
            if total != getattr(self, "_tray_count", 0):
                self.tray.setIcon(badge.icon_with_count(self.windowIcon(), total,
                                                        self.theme.c["hot"].name()))
        self._tray_count = total
        if self.launcher:
            self.launcher.set(total)

    # ---- events from the core ---------------------------------------------------------
    def on_event(self, name, payload):
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
        if name == "lanes_updated":
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
                        real(w.root)["id"] == payload:
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
                w.apply_read(payload)
            self.update_badges()
        elif name == "status_updated":
            for w in list(self.lane_widgets.values()) + self.extra_tabs():
                if getattr(w, "view", None) is not None:  # Activity has none
                    w.view.refresh_status(self.core.store, payload)
        elif name == "status_deleted":
            for w in list(self.lane_widgets.values()) + self.extra_tabs():
                if getattr(w, "view", None) is not None:
                    w.view.remove_status(payload)
            self.statusBar().showMessage(_("deleted"), 4000)
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
        if self.curtain_shown():
            self.right_stack.setCurrentIndex(0)
        self.tabs.setCurrentWidget(w)

    def _add_tab(self, w, title):
        log.info("tab opened: %s", type(w).__name__)
        i = self.tabs.addTab(w, title)
        if self.curtain_shown():  # a tab opened from the curtain: show it, not the curtain
            self.right_stack.setCurrentIndex(0)
        self.tabs.setCurrentIndex(i)

    def open_thread(self, sid):
        st = self.core.store.get_status(sid)
        if st:
            sid = real(st)["id"]
        for w in self.extra_tabs():
            if isinstance(w, ThreadWidget) and sid in w.statuses:
                self._front(w)
                w.focus_on(sid)
                return
        self._add_tab(ThreadWidget(self, sid), _("thread_loading"))

    def open_account(self, acc_id):
        for w in self.extra_tabs():
            if isinstance(w, AccountWidget) and w.acc_id == acc_id:
                if self.tabs.currentWidget() is w and not self.curtain_shown():
                    w.show_info()  # already here: back up to who this is
                else:
                    self._front(w)
                return
        self._add_tab(AccountWidget(self, acc_id), "@…")

    def open_search(self, query=""):
        for w in self.extra_tabs():
            if isinstance(w, SearchWidget):
                self._front(w)
                w.edit.setText(query)
                w.run(query)
                return
        self._add_tab(SearchWidget(self, query), _("search_title"))

    def open_people(self, acc, which):
        for w in self.extra_tabs():
            if isinstance(w, PeopleWidget) and w.acc_id == acc["id"] and w.which == which:
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
        from urllib.parse import urlparse

        from ...core import counters
        s = real(st)
        title = _("who_" + kind, text=snippet(s, 30))
        origin = counters.origin_api_url(s, (self.core.auth or {}).get("server", ""))
        kw = {}
        if origin and self.cfg["feed"].get("remote_people", True):
            kw = {"origin": lambda have: self.core.who_reacted_from_origin(st, kind, have),
                  "origin_label": _("people_more_from", host=urlparse(origin).hostname)}
        self.open_accounts(f"{kind}:{s['id']}", title,
                           lambda cur: self.core.who_reacted(st, kind, cur), **kw)

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
        self.bridge.call(self.core.server_info(),
                         ok=lambda info: ServerInfoDialog(self, info).exec(), fail=self.error)

    def open_quotes(self, st):
        for w in self.extra_tabs():
            if isinstance(w, QuotesWidget) and w.status["id"] == real(st)["id"]:
                self._front(w)
                return
        w = QuotesWidget(self, st)
        self._add_tab(w, w.title)

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
            elif found[0] == "status":
                self.statusBar().clearMessage()
                self.open_thread(real(found[1])["id"])
            else:
                self.statusBar().clearMessage()
                self.open_account(found[1]["id"])
        self.bridge.call(self.core.resolve(url), ok=done,
                         fail=lambda _e: (self.statusBar().clearMessage(), self.open_url(url)))

    def retitle(self, w):
        i = self.tabs.indexOf(w)
        if i >= 0:
            self.tabs.setTabText(i, w.title if len(w.title) < 40 else w.title[:39] + "…")
            self.tabs.setTabToolTip(i, w.title)

    def close_tab(self, i):
        w = self.tabs.widget(i)
        if w is None or w is self.stack:
            return
        log.info("tab closed: %s", type(w).__name__)
        self.tabs.removeTab(i)
        w.deleteLater()

    def vote(self, st, choices):
        sid = real(st)["id"]
        self.bridge.call(self.core.vote(st, choices),
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
        view = self.current_view()
        specs = [s for s in (view.model if view is not None else []) if s.status]
        at = next((i for i, s in enumerate(specs) if s.status.get("id") == sid), None)
        if at is None:
            self.core.mark_read([sid])
            return
        older = specs[:at + 1] if self.cfg["feed"]["order"] == "oldest_first" else specs[at:]
        self.core.mark_read([s.status["id"] for s in older if s.unread])

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
    def open_url(self, url):
        from .opener import open_link
        open_link(url)

    def on_link(self, url):
        if not url.startswith("fedtail:"):
            log.info("link: browser (%s)", QUrl(url).host() or "?")
            self.open_url(url)
            return
        action, _sep, arg = url[len("fedtail:"):].partition("/")
        log.info("action %s %s", action, arg if action not in ("tag", "resolve") else "…")
        st = self.core.store.get_status(arg) \
            if action not in ("account", "tag", "resolve", "alias") else None
        if action == "alias":  # a post's #abc: into the command line
            self.cmdline.put_alias(arg)
        elif action == "tag":
            self.open_tag(unquote(arg))
        elif action == "resolve":
            self.resolve_link(unquote(arg))
        elif action == "thread":
            self.open_thread(arg)
        elif action == "account":
            self.open_account(arg)
        elif st is None:
            self.error(_("not_in_cache"))
        elif action == "poll":
            self.bridge.call(self.core.refresh_poll(st), fail=self.error)
        elif action == "reply":
            self.compose(st)
        elif action == "edit":
            Compose(self, edit=st).show()
        elif action == "history":
            self.show_history(st)
        elif action in ("mute", "block"):
            acc = real(st)["account"]
            if action == "block" and QMessageBox.question(
                    self, _("block"), _("block_q", acct=acc["acct"])) \
                    != QMessageBox.StandardButton.Yes:
                return
            call = self.core.mute if action == "mute" else self.core.block
            self.bridge.call(call(acc["id"], True), ok=lambda _r: self.statusBar().showMessage(
                _(action + "d_msg", acct=acc["acct"]), 6000))
        elif action == "bookmark":
            on = not real(st).get("bookmarked")
            self.bridge.call(self.core.bookmark(st, on), ok=lambda _s: self.statusBar().showMessage(
                _("bookmarked" if on else "unbookmarked"), 4000))
        elif action == "fav":
            self.bridge.call(self.core.favourite(st))
        elif action == "boost":
            self.bridge.call(self.core.boost(st))
        elif action == "open":
            s = real(st)
            self.open_url(s.get("url") or s.get("uri"))
        elif action in ("sub", "unsub"):
            sub = action == "sub"
            self.bridge.call((self.core.subscribe if sub else self.core.unsubscribe)(st),
                             ok=lambda _r: self.statusBar().showMessage(
                                 _("subbed" if sub else "unsubbed"), 6000))
        elif action == "report":
            self.report(st)
        elif action == "blockdomain":
            domain = real(st)["account"]["acct"].partition("@")[2]
            if domain and QMessageBox.question(
                    self, _("block_domain", domain=domain), _("block_domain_q", domain=domain)) \
                    == QMessageBox.StandardButton.Yes:
                self.bridge.call(self.core.block_domain(domain, True),
                                 ok=lambda _d: self.statusBar().showMessage(
                                     _("domain_blocked", domain=domain), 6000),
                                 fail=self.error)
        elif action == "quote":
            Compose(self, quote=st).show()
        elif action == "readone":
            self.core.mark_read([arg])
        elif action == "readupto":
            self.read_up_to(arg)
        elif action in ("favourited_by", "reblogged_by"):
            self.open_reactions(st, action)
        elif action in ("mutethread", "unmutethread"):
            on = action == "mutethread"
            self.bridge.call(self.core.mute_thread(st, on),
                             ok=lambda _s: self.statusBar().showMessage(
                                 _("thread_muted" if on else "thread_unmuted"), 5000),
                             fail=self.error)
        elif action == "quotes":
            self.open_quotes(st)
        elif action == "revokequote":
            q = real(st).get("quote") or {}
            mine = q.get("quoted_status")
            if mine and QMessageBox.question(
                    self, _("revoke_quote"),
                    _("revoke_quote_q", acct=real(st)["account"]["acct"])) \
                    == QMessageBox.StandardButton.Yes:
                self.bridge.call(self.core.revoke_quote(mine, st),
                                 ok=lambda _s: self.statusBar().showMessage(
                                     _("quote_taken_back"), 5000),
                                 fail=self.error)
        elif action in ("pin", "unpin"):
            on = action == "pin"
            self.bridge.call(self.core.pin(st, on), ok=lambda _s: self.statusBar().showMessage(
                _("pinned_msg" if on else "unpinned_msg"), 4000), fail=self.error)
        elif action == "delete":
            if QMessageBox.question(self, _("delete_q_title"),
                                    _("delete_q", text=snippet(st, 200))) \
                    == QMessageBox.StandardButton.Yes:
                self.bridge.call(self.core.delete(st))

    def play_video(self, m, items=None):
        """A video or a gifv: over the window (ui.video_player), or in the browser.
        items: all the videos and gifs of the post, to go between them there."""
        from . import player
        if self.cfg["ui"].get("video_player", "internal") == "internal" and \
                player.available():
            player.VideoOverlay(self, self.ctx, m, loop=m.get("type") == "gifv",
                                items=items)
        else:
            self.open_url(player.media_url(m))

    def show_images(self, media, index):
        if self.cfg["ui"]["image_viewer"] == "browser":
            m = media[index]
            self.open_url(m.get("url") or m.get("remote_url"))
            return
        ImageOverlay(self, self.ctx, media, index)

    def answer_follow(self, acc_id, approve):
        self.bridge.call(self.core.answer_follow(acc_id, approve))

    def compose(self, reply_to=None, attach=(), text=""):
        if not self.core.me:
            return
        Compose(self, reply_to, attach, text).show()

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

    def translate_post(self, st, done):
        """Ask the server for a translation; done(result) in the card, or an error."""
        if not self.core.caps.translation:
            self.error(_("translate_none"))
            return
        self.bridge.call(self.core.translate(st), ok=done, fail=self.error)

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
            for s in items:
                text = (s.get("params") or {}).get("text") or ""
                it = QListWidgetItem(f"{self.theme.date(s.get('scheduled_at', ''))} — "
                                     f"{text[:120]}")
                it.setData(Qt.ItemDataRole.UserRole, s["id"])
                lst.addItem(it)
            if not items:
                lst.addItem(_("scheduled_none"))

        def load():
            self.bridge.call(self.core.scheduled(), ok=fill, fail=self.error)

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
        acc = real(st)["account"]
        dlg = QDialog(self)
        dlg.setWindowTitle(_("report_title", acct=acc["acct"]))
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
        why = QPlainTextEdit()
        why.setPlaceholderText(_("report_why"))
        lay.addWidget(why, 1)
        remote = "@" in acc["acct"]
        fwd = QCheckBox(_("report_forward", host=acc["acct"].split("@")[-1]))
        fwd.setChecked(remote and self.cfg["post"].get("report_forward", True))
        fwd.setVisible(remote)
        lay.addWidget(fwd)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        send = buttons.addButton(_("report_send"), QDialogButtonBox.ButtonRole.AcceptRole)
        send.setObjectName("primary")
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)

        def go():
            dlg.accept()
            self.bridge.call(self.core.report(st, why.toPlainText().strip(), fwd.isChecked(),
                                              kind.currentData()),
                             ok=lambda _r: self.statusBar().showMessage(_("report_sent"), 6000),
                             fail=self.error)
        send.clicked.connect(go)
        dlg.show()
        return dlg

    def show_history(self, st):
        """The versions of an edited post, oldest first, as the server keeps them."""
        from PySide6.QtWidgets import QTextBrowser

        from .text import clean
        dlg = QDialog(self)
        dlg.setWindowTitle(_("history_title"))
        dlg.resize(560, 480)
        lay = QVBoxLayout(dlg)
        view = QTextBrowser()
        view.setOpenLinks(False)
        lay.addWidget(view)
        view.setPlainText(_("loading"))

        def got(versions):
            parts = []
            for i, v in enumerate(versions, 1):
                when = self.theme.date(v.get("created_at", ""))
                cw = f"<p><i>⚠ {v['spoiler_text']}</i></p>" if v.get("spoiler_text") else ""
                parts.append(f"<h4>{_('history_version', n=i)} · {when}</h4>{cw}"
                             f"{clean(v.get('content', ''), self.theme.css('link'))}")
            view.setHtml("<hr>".join(parts) or _("history_none"))
        self.bridge.call(self.core.history(st), ok=got,
                         fail=lambda e: view.setPlainText(_("load_failed", err=e)))
        dlg.show()

    def after_post(self, st, reply_to):
        self.statusBar().showMessage(_("sent"), 4000)
        if reply_to:
            for w in self.extra_tabs():
                if isinstance(w, ThreadWidget) and reply_to["id"] in w.statuses:
                    w.reload()
        else:
            self.open_thread(st["id"])

    # ---- window -------------------------------------------------------------------------
    def error(self, err):
        self.statusBar().showMessage(_("error", err=err), 10_000)

    def save_image(self, media):
        url = media.get("url") or media.get("remote_url") or media.get("preview_url")
        if not url:
            return
        from ...core import saving
        self.bridge.call(self.images.save(url, saving.save_dir(self.cfg)),
                         ok=lambda p: self.statusBar().showMessage(_("saved_to", path=str(p)),
                                                                   8000),
                         fail=lambda e: self.error(_("save_failed", err=e)))

    def bug_report(self):
        try:
            diag.log_stats()
            out = diag.bug_report(self.core.paths, cfg=self.cfg)
        except OSError as e:
            self.error(e)
            return
        self.statusBar().showMessage(_("debug_report_done", path=str(out)), 15000)
        self.open_url(QUrl.fromLocalFile(str(out.parent)).toString())

    def about(self):
        import platform

        from PySide6 import __version__ as pyside

        info = version.info()
        lines = [_("about_text", version=info["version"])]
        if info["commit"]:
            lines.append(_("about_build", commit=info["commit"], date=info["date"]))
        lines.append(_("about_env", py=platform.python_version(), qt=pyside))
        lines.append(_("made_by_long"))
        if self.core.me:
            lines.append(_("about_profile", profile=self.core.paths.profile,
                           acct="@" + self.core.me["acct"], server=self.core.auth["server"]))
        QMessageBox.about(self, "fedtail", "<br>".join(lines))

    def show_raise(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
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
            self.select_lane(self.core.get_state("lane") or "people")
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

    def curtain_shown(self):
        return self.right_stack.currentWidget() is self.curtain

    def close_all(self):
        """Esc: no lane, thread or profile on screen; nothing gets marked read, so
        whatever comes meanwhile waits, counted on the left."""
        self.find_bar.close_bar()
        for w in self.findChildren(ImageOverlay):
            w.close_viewer()
        self.curtain_icon.setPixmap(QIcon(icon_path()).pixmap(96, 96))
        self.right_stack.setCurrentWidget(self.curtain)
        self.lanes.blockSignals(True)
        self.lanes.setCurrentItem(None)
        self.lanes.clearSelection()
        self.lanes.blockSignals(False)
        for item in self.lane_items.values():
            item.set_current(False)
        self.core.set_active_lane(None)
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
        if self.tray and self.cfg["ui"]["close_to_tray"] and not self.quitting:
            self.hide()
            e.ignore()
            return
        super().closeEvent(e)
        QApplication.quit()

    def _debug_corner(self):
        """In the debugging mode, the right end of the status bar says how this
        window is drawn: theme, style, font, Qt platform, scale, build."""
        from ... import diag
        if not diag.is_on():
            return
        app = QApplication.instance()
        screen = app.primaryScreen()
        f = app.font()
        bits = [_("debug_theme", theme=self.theme.id), app.style().name(),
                f"{f.family()} {f.pointSizeF():g}pt", app.platformName()]
        if screen:
            bits.append(f"{screen.devicePixelRatio() * 100:g}%")
        bits.append("onefile" if getattr(sys, "frozen", False) else "source")
        label = QLabel(" · ".join(bits))
        label.setObjectName("muted")
        label.setToolTip(_("debug_corner_tip"))
        self.statusBar().addPermanentWidget(label)

    @staticmethod
    def _geometry_key():
        """The window's size and place, kept apart for the one-file build: its Qt may
        scale differently from the system's, and one would stretch the other's window."""
        return "geometry.onefile" if getattr(sys, "frozen", False) else "geometry"

    def quit(self):
        self.quitting = True
        self.close()
        QApplication.quit()
