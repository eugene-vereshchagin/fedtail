"""Main window: lanes on the left, tabs (lane / threads / accounts) on the right."""

from dataclasses import dataclass

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QTabBar,
    QTabWidget,
)

from ... import __version__
from ...core.model import real, snippet
from ...i18n import _
from .compose import Compose
from .feed import AccountWidget, LaneWidget, RequestsWidget, ThreadWidget
from .images import Images
from .login import LoginDialog
from .viewer import ImageOverlay

# icons from the desktop theme (Breeze names); emoji are missing from many fonts
LANE_ICON = {"people": "system-users", "comments": "mail-replied",
             "mentions": "mail-mark-important", "bots": "applications-system",
             "mine": "document-edit", "local": "go-home",
             "requests": "list-add-user"}


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


class MainWindow(QMainWindow):
    def __init__(self, core, bridge, theme):
        super().__init__()
        self.core, self.bridge, self.theme = core, bridge, theme
        self.cfg = core.cfg
        self.images = Images(core, bridge)
        self.ctx = ViewContext(self.cfg, theme, self.images, self.on_link, self.open_url,
                               self.show_images)
        self.lane_widgets = {}
        self.quitting = False
        bridge.on_error = self.error
        bridge.event.connect(self.on_event)
        bridge.raise_requested.connect(self.show_raise)

        title = "fedtail" if core.paths.profile == "default" else \
            f"fedtail [{core.paths.profile}]"
        self.base_title = title
        self.setWindowTitle(title)
        self.setWindowIcon(QIcon.fromTheme("fedtail", QIcon.fromTheme("internet-mail")))
        self._build()
        geo = core.get_state("geometry")
        if geo:
            self.restoreGeometry(bytes.fromhex(geo))
        else:
            self.resize(1150, 850)

    # ---- layout -------------------------------------------------------------------
    def _build(self):
        self.tray = None
        self.sidebar = QListWidget()
        self.sidebar.setMinimumWidth(170)
        self.sidebar.setMaximumWidth(280)
        for lane in self.core.lanes:
            it = QListWidgetItem(QIcon.fromTheme(LANE_ICON.get(lane.name, "")), "")
            it.setData(Qt.ItemDataRole.UserRole, lane.name)
            self.sidebar.addItem(it)
        self.sidebar.currentItemChanged.connect(self._lane_clicked)
        self.update_badges()

        self.stack = QStackedWidget()
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.addTab(self.stack, "")
        self.tabs.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
        self.tabs.tabCloseRequested.connect(self.close_tab)

        split = QSplitter()
        split.addWidget(self.sidebar)
        split.addWidget(self.tabs)
        split.setStretchFactor(1, 1)
        split.setSizes([210, 940])
        self.setCentralWidget(split)

        a_new = QAction(QIcon.fromTheme("document-new"), _("write"), self)
        a_new.setShortcut(QKeySequence("Ctrl+N"))
        a_new.triggered.connect(lambda: self.compose())
        a_ref = QAction(QIcon.fromTheme("view-refresh"), _("refresh"), self)
        a_ref.setShortcut(QKeySequence("F5"))
        a_ref.triggered.connect(self.refresh)
        tb = self.addToolBar("main")
        tb.setObjectName("main")
        tb.setMovable(False)
        tb.addAction(a_new)
        tb.addAction(a_ref)

        m = self.menuBar().addMenu(_("menu_file"))
        m.addAction(a_new)
        m.addAction(a_ref)
        m.addSeparator()
        m.addAction(_("open_config"), lambda: self.open_url(
            QUrl.fromLocalFile(str(self.core.paths.config_file)).toString()))
        m.addAction(_("open_data"), lambda: self.open_url(
            QUrl.fromLocalFile(str(self.core.paths.data_dir)).toString()))
        m.addAction(_("relogin"), self.relogin)
        m.addSeparator()
        a_quit = m.addAction(_("quit"), self.quit)
        a_quit.setShortcut(QKeySequence("Ctrl+Q"))
        h = self.menuBar().addMenu(_("menu_help"))
        h.addAction(_("about"), self.about)

        QShortcut(QKeySequence("Ctrl+W"), self).activated.connect(
            lambda: self.close_tab(self.tabs.currentIndex()))
        for i in range(min(9, self.sidebar.count())):
            QShortcut(QKeySequence(f"Alt+{i + 1}"), self).activated.connect(
                lambda r=i: self.sidebar.setCurrentRow(r))

        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            menu = QMenu(self)
            menu.addAction(_("show"), self.show_raise)
            menu.addAction(_("write"), lambda: self.compose())
            menu.addSeparator()
            menu.addAction(_("quit"), self.quit)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self._tray_click)
            self.tray.messageClicked.connect(self._notification_clicked)
            self.tray.setToolTip(self.windowTitle())
            self.tray.show()
        self._notify_lane = None

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
        self.sidebar.setCurrentRow(row)
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

    def select_lane(self, name):
        for i in range(self.sidebar.count()):
            if self.sidebar.item(i).data(Qt.ItemDataRole.UserRole) == name:
                self.sidebar.setCurrentRow(i)

    def update_badges(self):
        total = 0
        for i in range(self.sidebar.count()):
            it = self.sidebar.item(i)
            name = it.data(Qt.ItemDataRole.UserRole)
            if not self.core.me:
                n = 0
            elif name == "requests":
                n = len(self.core.follow_requests)
            else:
                n = self.core.unread_count(name)
            if name in ("comments", "mentions", "requests"):
                total += n
            badge = f"  ({n})" if n else ""
            it.setText(f"{_('lane_' + name)}{badge}")
            f = it.font()
            f.setBold(bool(n))
            it.setFont(f)
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
        if not (self.tray and self.cfg["ui"]["notifications"]):
            return
        if self.isActiveWindow():
            return
        lane, st = items[0]
        self._notify_lane = lane
        head = _("notify_comment") if lane == "comments" else _("notify_mention")
        who = real(st)["account"]["acct"]
        more = _("notify_more", n=len(items) - 1) if len(items) > 1 else ""
        self.tray.showMessage(f"{head}: {who}{more}", snippet(st, 200), self.windowIcon(), 8000)

    def _notification_clicked(self):
        self.show_raise()
        if self._notify_lane:
            self.select_lane(self._notify_lane)

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

    def compose(self, reply_to=None):
        if not self.core.me:
            return
        Compose(self, reply_to).show()

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
