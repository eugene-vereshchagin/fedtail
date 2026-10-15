"""Main window: lanes on the left, tabs (lane / threads / accounts) on the right."""

from dataclasses import dataclass

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
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

from ... import __version__
from ...core.model import real, snippet
from ...i18n import _
from .. import themefile
from . import feed as feed_module
from .card import _round
from .compose import Compose, media_paths, save_image
from .feed import AccountWidget, LaneWidget, RequestsWidget, ThreadWidget
from .find import FindBar
from .images import Images
from .login import LoginDialog
from .notify import Notifier, icon_path
from .viewer import ImageOverlay

# icons from the desktop theme (Breeze names); emoji are missing from many fonts
LANE_ICON = {"people": "system-users", "comments": "mail-replied",
             "mentions": "mail-mark-important", "subs": "mail-thread-watch",
             "bots": "applications-system",
             "mine": "document-edit", "local": "go-home",
             "requests": "list-add-user"}


BADGE_KIND = {"comments": "hot", "bots": "quiet"}


class LaneItem(QWidget):
    """A lane in the sidebar: icon, name, unread badge."""

    def __init__(self, name, theme, number):
        super().__init__()
        self.name, self.theme = name, theme
        self.current = False
        self.setToolTip(f"Alt+{number}" if number <= 9 else "")
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(10)
        if theme.shape["lane_icons"]:
            icon = QLabel()
            ic = QIcon.fromTheme(LANE_ICON.get(name, ""))
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
        self.label.setText(self.theme.word(key, _("lane_" + self.name)))
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


class MainWindow(QMainWindow):
    def __init__(self, core, bridge, theme):
        super().__init__()
        self.core, self.bridge, self.theme = core, bridge, theme
        self.cfg = core.cfg
        self.images = Images(core, bridge)
        self.ctx = ViewContext(self.cfg, theme, self.images, self.on_link, self.open_url,
                               self.show_images)
        self.ctx.subscribed = core.subscribed
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
        self.tabs.currentChanged.connect(lambda _i: self.find_bar.view_changed())
        self.stack.currentChanged.connect(lambda _i: self.find_bar.view_changed())
        row.addWidget(right, 1)
        self.setCentralWidget(central)
        self.menuBar().hide()

        for seq, fn in (("Ctrl+N", lambda: self.compose()), ("F5", self.refresh),
                        ("Ctrl+Q", self.quit),
                        ("Ctrl+W", lambda: self.close_tab(self.tabs.currentIndex())),
                        (QKeySequence.StandardKey.Find, self.find_bar.open),
                        (QKeySequence.StandardKey.FindNext, lambda: self.find_bar.step(1)),
                        (QKeySequence.StandardKey.FindPrevious,
                         lambda: self.find_bar.step(-1))):
            QShortcut(QKeySequence(seq), self).activated.connect(fn)
        for i in range(min(9, self.lanes.count())):
            QShortcut(QKeySequence(f"Alt+{i + 1}"), self).activated.connect(
                lambda r=i: self.lanes.setCurrentRow(r))

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

        compose = QPushButton(t.word("compose", _("write")))
        compose.setObjectName("compose")
        compose.setCursor(Qt.CursorShape.PointingHandCursor)
        compose.setToolTip(_("write") + " (Ctrl+N)")
        compose.clicked.connect(lambda: self.compose())
        v.addWidget(compose)

        self.lanes = QListWidget()
        self.lanes.setObjectName("lanes")
        self.lanes.setFrameShape(QFrame.Shape.NoFrame)
        self.lanes.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.lane_items = {}
        for i, lane in enumerate(self.core.lanes):
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, lane.name)
            w = LaneItem(lane.name, t, i + 1)
            it.setSizeHint(w.sizeHint())
            self.lanes.addItem(it)
            self.lanes.setItemWidget(it, w)
            self.lane_items[lane.name] = w
        self.lanes.currentItemChanged.connect(self._lane_clicked)
        v.addWidget(self.lanes, 1)
        self.sidebar = self.lanes  # older name, still used around
        self.update_badges()
        return side

    def _app_menu(self):
        m = QMenu(self)
        m.addAction(_("write") + "\tCtrl+N", lambda: self.compose())
        m.addAction(_("refresh") + "\tF5", self.refresh)
        m.addSeparator()
        m.addAction(_("open_config"), lambda: self.open_url(
            QUrl.fromLocalFile(str(self.core.paths.config_file)).toString()))
        m.addAction(_("open_themes"), lambda: self.open_url(
            QUrl.fromLocalFile(str(themefile.user_dir())).toString()))
        m.addAction(_("open_data"), lambda: self.open_url(
            QUrl.fromLocalFile(str(self.core.paths.data_dir)).toString()))
        m.addSeparator()
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

    def _connected(self, me):
        self.ctx.me_id = me["id"]
        t = self.theme
        fields = {"display_name": me.get("display_name") or me["username"],
                  "username": me["username"], "acct": me["acct"]}
        self.account_name.setText(t.words["account_title"].format(**fields))
        self.account_sub.setText(t.words["account_subtitle"].format(**fields))
        if t.shape["sidebar_avatar"]:
            self.images.get(me.get("avatar_static") or me.get("avatar"),
                            lambda pm: self.account_avatar.setPixmap(_round(pm, 44)))
        for w in self.theme.warnings:
            self.error(w)
        self.statusBar().showMessage(_("connected", acct=me["acct"],
                                       server=self.core.auth["server"]), 8000)
        if self.core.new_options:
            QTimer.singleShot(8500, lambda: self.statusBar().showMessage(
                _("new_options", n=len(self.core.new_options)), 30_000))
        tip = f"{self.base_title} — @{me['acct']}"
        self.setWindowTitle(tip)
        if self.tray:
            self.tray.setToolTip(tip)
        last = self.core.get_state("lane")
        row = next((i for i, lane in enumerate(self.core.lanes) if lane.name == last), 0)
        self.lanes.setCurrentRow(row)
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
    def _lane_clicked(self, cur, _prev):
        if not cur or not self.core.me:
            return
        name = cur.data(Qt.ItemDataRole.UserRole)
        w = self.lane_widgets.get(name)
        if w is None:
            w = RequestsWidget(self) if name == "requests" else LaneWidget(self, name)
            self.lane_widgets[name] = w
            self.stack.addWidget(w)
            if name != "requests":
                w.refresh()
        self.stack.setCurrentWidget(w)
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.stack))
        self.tabs.setTabText(self.tabs.indexOf(self.stack), _("lane_" + name))
        self.core.set_state("lane", name)
        for lane_name, item in self.lane_items.items():
            item.set_current(lane_name == name)

    def select_lane(self, name):
        for i in range(self.lanes.count()):
            if self.lanes.item(i).data(Qt.ItemDataRole.UserRole) == name:
                self.lanes.setCurrentRow(i)

    def update_badges(self):
        total = 0
        for name, item in getattr(self, "lane_items", {}).items():
            if not self.core.me:
                n = 0
            elif name == "requests":
                n = len(self.core.follow_requests)
            else:
                n = self.core.unread_count(name)
            if name in ("comments", "mentions", "subs", "requests"):
                total += n
            item.set_count(n)
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
                self.tabs.setCurrentWidget(w)
                return
        self._add_tab(AccountWidget(self, acc_id), "@…")

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
        st = self.core.store.get_status(arg) if action not in ("account",) else None
        if action == "thread":
            self.open_thread(arg)
        elif action == "account":
            self.open_account(arg)
        elif st is None:
            self.error(_("not_in_cache"))
        elif action == "reply":
            self.compose(st)
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

    def compose(self, reply_to=None, attach=()):
        if not self.core.me:
            return
        Compose(self, reply_to, attach).show()

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

    def about(self):
        QMessageBox.about(self, "fedtail", _("about_text", version=__version__))

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
        # themselves); the last one takes the whole window off the screen.
        if e.key() == Qt.Key.Key_Escape and not e.modifiers() and self.cfg["ui"]["esc_hides"]:
            if self.find_bar.isVisible():
                self.find_bar.close_bar()
            else:
                self.hide_away()
            return
        super().keyPressEvent(e)

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
