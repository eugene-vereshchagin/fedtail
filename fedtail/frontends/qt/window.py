"""Main window: lanes on the left, tabs (lane / threads / accounts) on the right."""

import logging
from dataclasses import dataclass
from urllib.parse import unquote

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QImage, QKeySequence, QShortcut
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
from . import feed as feed_module
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
from .viewer import ImageOverlay

log = logging.getLogger(__name__)

# icons from the desktop theme (Breeze names); emoji are missing from many fonts
LANE_ICON = {"people": "system-users", "comments": "mail-replied",
             "mentions": "mail-mark-important", "subs": "mail-thread-watch",
             "bots": "applications-system",
             "mine": "document-edit", "local": "go-home", "global": "applications-internet",
             "requests": "list-add-user", "list": "view-list-details",
             "activity": "rating", "bookmarks": "bookmarks"}


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
        self.badge.setText(str(n) if n < 1000 else "999+")
        self.badge.setVisible(bool(n))


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


class MainWindow(QMainWindow):
    def __init__(self, core, bridge, theme):
        super().__init__()
        self.core, self.bridge, self.theme = core, bridge, theme
        self.cfg = core.cfg
        self.images = Images(core, bridge)
        self.ctx = ViewContext(self.cfg, theme, self.images, self.on_link, self.open_url,
                               self.show_images)
        self.ctx.subscribed = core.subscribed
        self.ctx.save_image = self.save_image
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
        self.setAcceptDrops(True)
        geo = core.get_state("geometry")
        if geo:
            self.restoreGeometry(bytes.fromhex(geo))
        else:
            self.resize(1150, 850)

    # ---- layout -------------------------------------------------------------------
    def _build(self):
        self.tray = None
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
            QShortcut(QKeySequence(seq), self).activated.connect(fn)
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

    def _app_menu(self):
        m = QMenu(self)
        m.addAction(_("write") + "\tCtrl+N", lambda: self.compose())
        m.addAction(_("refresh") + "\tF5", self.refresh)
        m.addAction(_("search_title") + "\tCtrl+K", lambda: self.open_search(""))
        m.addAction(_("silence_title") + "…", lambda: SilenceDialog(self).exec())
        m.addAction(_("my_profile"), self.open_my_profile)
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
        last = self.core.get_state("lane")
        if last in self.lane_items:
            self.select_lane(last)
        else:  # the first time: Home, not whatever happens to be on top
            self.select_lane("people" if "people" in self.lane_items else self.lane_order[0])
        self.core.start_polling()

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

    def _section_header(self, title, plus=False):
        head = QListWidgetItem()
        head.setFlags(Qt.ItemFlag.NoItemFlags)
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(10, 14, 4, 2)
        label = QLabel(self.theme.word("lane", title))
        label.setObjectName("listsHeader")
        h.addWidget(label, 1)
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
                self._section_header(_("lists_header"), plus=True)
            elif not names:
                continue
            elif group:
                self._section_header(_("grp_" + group))
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
        # lanes of lists that are gone
        for name in [n for n in self.lane_widgets if n.startswith("list:")
                     and n not in self.core.lane_by_name]:
            w = self.lane_widgets.pop(name)
            self.stack.removeWidget(w)
            w.deleteLater()
        self.lanes.blockSignals(False)
        if current:
            if current in self.lane_items:
                self.select_lane(current)
                self.lane_items[current].set_current(True)
            else:
                self.select_lane("people" if "people" in self.lane_items
                                 else self.lane_order[0])
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
                ok=lambda _r, on=on: self.statusBar().showMessage(
                    _("list_added" if on else "list_removed"), 4000)))
        if self.core.lists:
            menu.addSeparator()
        menu.addAction(_("list_new"), lambda: self.new_list(add=account["id"]))

    def _lane_clicked(self, cur, _prev):
        if not cur or not self.core.me:
            return
        name = cur.data(Qt.ItemDataRole.UserRole)
        if name is None:
            return
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
                w.refresh()
            self.lane_widgets[name] = w
            self.stack.addWidget(w)
        self.stack.setCurrentWidget(w)
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.stack))
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

    def select_lane(self, name):
        for i in range(self.lanes.count()):
            if self.lanes.item(i).data(Qt.ItemDataRole.UserRole) == name:
                if self.lanes.currentRow() == i:
                    # already the current row (e.g. after rows were removed under it):
                    # no change signal will come, so show the lane ourselves
                    self._lane_clicked(self.lanes.item(i), None)
                else:
                    self.lanes.setCurrentRow(i)

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
            if name in ("comments", "mentions", "subs", "requests"):
                total += n
            item.set_count(n)
        if getattr(self, "curtain", None) is not None and self.curtain_shown():
            self._curtain_text()
        if self.tray:
            base = self.windowTitle()
            self.tray.setToolTip(_("tray_new", title=base, n=total) if total else base)

    # ---- events from the core ---------------------------------------------------------
    def on_event(self, name, payload):
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
                if hasattr(w, "view"):
                    w.view.refresh_from_store(self.core.store)
        elif name == "status_deleted":
            for w in list(self.lane_widgets.values()) + self.extra_tabs():
                if hasattr(w, "view"):
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

    def _add_tab(self, w, title):
        i = self.tabs.addTab(w, title)
        self.tabs.setCurrentIndex(i)

    def open_thread(self, sid):
        st = self.core.store.get_status(sid)
        if st:
            sid = real(st)["id"]
        for w in self.extra_tabs():
            if isinstance(w, ThreadWidget) and sid in w.statuses:
                self.tabs.setCurrentWidget(w)
                w.focus_on(sid)
                return
        self._add_tab(ThreadWidget(self, sid), _("thread_loading"))

    def open_account(self, acc_id):
        for w in self.extra_tabs():
            if isinstance(w, AccountWidget) and w.acc_id == acc_id:
                if self.tabs.currentWidget() is w:
                    w.show_info()  # already here: back up to who this is
                else:
                    self.tabs.setCurrentWidget(w)
                return
        self._add_tab(AccountWidget(self, acc_id), "@…")

    def open_search(self, query=""):
        for w in self.extra_tabs():
            if isinstance(w, SearchWidget):
                self.tabs.setCurrentWidget(w)
                w.edit.setText(query)
                w.run(query)
                return
        self._add_tab(SearchWidget(self, query), _("search_title"))

    def open_people(self, acc, which):
        for w in self.extra_tabs():
            if isinstance(w, PeopleWidget) and w.acc_id == acc["id"] and w.which == which:
                self.tabs.setCurrentWidget(w)
                return
        w = PeopleWidget(self, acc, which)
        self._add_tab(w, w.title)

    def open_tag(self, tag):
        for w in self.extra_tabs():
            if isinstance(w, TagWidget) and w.tag.lower() == tag.lower():
                self.tabs.setCurrentWidget(w)
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
        self.tabs.removeTab(i)
        w.deleteLater()

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
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def on_link(self, url):
        if not url.startswith("fedtail:"):
            self.open_url(url)
            return
        action, _sep, arg = url[len("fedtail:"):].partition("/")
        st = self.core.store.get_status(arg) if action not in ("account", "tag", "resolve") \
            else None
        if action == "tag":
            self.open_tag(unquote(arg))
        elif action == "resolve":
            self.resolve_link(unquote(arg))
        elif action == "thread":
            self.open_thread(arg)
        elif action == "account":
            self.open_account(arg)
        elif st is None:
            self.error(_("not_in_cache"))
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
        elif action == "delete":
            if QMessageBox.question(self, _("delete_q_title"),
                                    _("delete_q", text=snippet(st, 200))) \
                    == QMessageBox.StandardButton.Yes:
                self.bridge.call(self.core.delete(st))

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
            out = diag.bug_report(self.core.paths)
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
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.curtain_shown():
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
        self.core.set_state("geometry", bytes(self.saveGeometry()).hex())
        if self.tray:
            self.hide()
        else:
            self.showMinimized()

    def closeEvent(self, e):
        self.core.set_state("geometry", bytes(self.saveGeometry()).hex())
        if self.tray and self.cfg["ui"]["close_to_tray"] and not self.quitting:
            self.hide()
            e.ignore()
            return
        super().closeEvent(e)
        QApplication.quit()

    def quit(self):
        self.quitting = True
        self.close()
        QApplication.quit()
