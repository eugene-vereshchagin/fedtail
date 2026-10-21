"""The main GTK window: lanes on the left with their unread counts, the lane or thread
on the right (a tab each, the lanes' own tab first), a status line at the bottom.

Stage 1 of docs/GTK.md. What a card needs from the window goes through `Ctx` (like
qt/window.py ViewContext), so cards never import the window.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ...core import lanes as lanes_mod
from ...i18n import _
from ...model import real
from .. import richtext
from . import login
from .card import Card
from .gi_setup import Gio, GLib, Gtk, Pango
from .lane import LaneView, y_in

log = logging.getLogger(__name__)

BADGE_KIND = {"replies": "hot", "bots": "quiet", "activity": "quiet"}  # as qt/window.py


@dataclass
class Ctx:
    """What a card or a lane needs from the window."""
    cfg: dict
    view: object
    theme: object
    bridge: object
    win: object = None
    in_thread: bool = False
    extra: dict = field(default_factory=dict)

    def on_link(self, uri):
        self.win.on_link(uri)

    def open_url(self, url):
        self.win.open_url(url)

    def open_thread(self, post):
        self.win.open_thread(post)

    def act(self, what, post):
        self.win.act(what, post)

    def status(self, text):
        self.win.status(text)


class LaneRow(Gtk.ListBoxRow):
    def __init__(self, name, title):
        super().__init__()
        self.name = name
        box = Gtk.Box(spacing=6)
        lab = Gtk.Label(label=title, xalign=0)
        lab.set_hexpand(True)
        lab.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(lab)
        self.badge = Gtk.Label()
        self.badge.add_css_class("ft-badge")
        if name in BADGE_KIND:
            self.badge.add_css_class(BADGE_KIND[name])
        self.badge.set_visible(False)
        box.append(self.badge)
        self.set_child(box)

    def set_count(self, n):
        self.badge.set_visible(n > 0)
        self.badge.set_text(str(n) if n < 1000 else "999+")


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app, core, view, bridge, theme):
        super().__init__(application=app, title="fedtail")
        self.core, self.view, self.bridge, self.theme = core, view, bridge, theme
        self.cfg = core.cfg
        self.add_css_class("fedtail")
        self.ctx = Ctx(self.cfg, view, theme, bridge, self)
        self.lane_views = {}     # name -> LaneView
        self.lane_rows = {}      # name -> LaneRow
        self.threads = {}        # root post id -> page widget
        self.quitting = False
        bridge.on_event = self.on_event
        bridge.on_error = lambda text: self.status(_("error", err=text))
        self.set_default_size(*self._saved_size())

        header = Gtk.HeaderBar()
        refresh = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh.set_tooltip_text(_("refresh"))
        refresh.connect("clicked", lambda _b: self.view.poll_now())
        header.pack_start(refresh)
        self.who = Gtk.Label()
        self.who.add_css_class("ft-muted")
        header.pack_end(self.who)
        self.set_titlebar(header)

        self.sidebar = Gtk.ListBox()
        self.sidebar.add_css_class("ft-sidebar")
        self.sidebar.add_css_class("navigation-sidebar")
        self.sidebar.connect("row-selected", self._lane_selected)
        side_scroll = Gtk.ScrolledWindow()
        side_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        side_scroll.set_child(self.sidebar)
        side_scroll.add_css_class("ft-sidebar")
        side_scroll.set_size_request(200, -1)

        self.stack = Gtk.Stack()
        self.tabs = Gtk.Notebook()
        self.tabs.set_scrollable(True)
        self.tabs.set_show_tabs(False)
        self.tabs.append_page(self.stack, Gtk.Label(label=_("gtk_lanes")))
        self.tabs.connect("switch-page", lambda *_a: GLib.idle_add(self._tab_switched))

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_start_child(side_scroll)
        paned.set_end_child(self.tabs)
        paned.set_resize_start_child(False)
        paned.set_shrink_start_child(False)
        paned.set_position(220)

        self.status_line = Gtk.Label(xalign=0)
        self.status_line.add_css_class("ft-status")
        self.status_line.set_ellipsize(Pango.EllipsizeMode.END)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.add_css_class("fedtail-main")
        paned.set_vexpand(True)
        outer.append(paned)
        outer.append(self.status_line)
        self.set_child(outer)

        self.connect("notify::is-active", lambda *_a: self._activated())
        self.connect("close-request", self._close_request)

    # ---- start -----------------------------------------------------------------------
    def start(self):
        if not self.core.logged_in:
            login.LoginDialog(self, self._connect).present()
            return
        self._connect()

    def _connect(self):
        self.status(_("loading"))
        self.bridge.call(self.view.connect(), self._connected,
                         lambda err: self.status(_("error", err=err)))

    def _connected(self, _me):
        me = self.view.me
        if me is not None:
            self.who.set_text("@" + me.handle)
        self.status("")
        self._rebuild_sidebar()
        self.view.start_polling()

    def _rebuild_sidebar(self):
        current = self._current_lane()
        while (row := self.sidebar.get_first_child()) is not None:
            self.sidebar.remove(row)
        self.lane_rows = {}
        by_name = self.view.lane_by_name
        if self.cfg["ui"]["sidebar_groups"]:
            groups = lanes_mod.grouped(self.view.lanes)
        else:  # as qt/window.py: the lanes, then the lists
            groups = [(None, [x.name for x in self.view.lanes if not lanes_mod.is_list(x.name)]),
                      ("lists", [x.name for x in self.view.lanes if lanes_mod.is_list(x.name)])]
        for group, names in groups:
            # follow requests and activity aren't status streams: not in GTK yet
            names = [n for n in names if n in by_name and by_name[n].source is not None]
            if not names or (group == "lists" and not self.cfg["lists"]["enabled"]):
                continue
            if group:
                self.sidebar.append(_section(_("lists_header") if group == "lists"
                                             else _("grp_" + group)))
            for name in names:
                title = self.view.lane_title(name) or _("lane_" + _base(name))
                row = LaneRow(name, title)
                self.lane_rows[name] = row
                self.sidebar.append(row)
        self.update_badges()
        start = current or self._start_lane()
        if start in self.lane_rows:
            self.sidebar.select_row(self.lane_rows[start])

    def _start_lane(self):
        want = self.cfg["ui"].get("start_lane") or "last"
        if want == "last":
            want = self.view.get_state("lane") or "home"
        return want if want in self.lane_rows else next(iter(self.lane_rows), None)

    # ---- lanes -------------------------------------------------------------------------
    def _current_lane(self):
        row = self.sidebar.get_selected_row()
        return row.name if isinstance(row, LaneRow) else None

    def _lane_selected(self, _box, row):
        if not isinstance(row, LaneRow):
            return
        name = row.name
        lv = self.lane_views.get(name)
        if lv is None:
            title = self.view.lane_title(name) or _("lane_" + _base(name))
            lv = LaneView(self.ctx, name, title)
            self.lane_views[name] = lv
            self.stack.add_named(lv, name)
        self.stack.set_visible_child(lv)
        self.tabs.set_current_page(0)
        self.view.set_active_lane(name)
        self.view.set_state("lane", name)
        lv.refresh()
        GLib.idle_add(lambda: (lv.refresh() if not lv.positioned else None,
                               GLib.SOURCE_REMOVE)[1])

    def update_badges(self):
        for name, row in self.lane_rows.items():
            try:
                row.set_count(self.view.unread_count(name))
            except Exception:  # noqa: BLE001 — a lane the core doesn't count
                row.set_count(0)

    def _activated(self):
        if self.is_active():
            lv = self.lane_views.get(self._current_lane())
            if lv is not None:
                lv.window_activated()

    def _tab_switched(self):
        self.tabs.set_show_tabs(self.tabs.get_n_pages() > 1)
        return GLib.SOURCE_REMOVE

    # ---- core events ------------------------------------------------------------------
    def on_event(self, name, payload):
        if name in ("lanes_updated", "parents", "read_changed", "arrived"):
            changed = payload if name == "lanes_updated" and isinstance(payload, dict) else None
            for lname, lv in self.lane_views.items():
                if changed is None or lname in changed:
                    if lv.get_mapped() or changed is not None:
                        lv.refresh()
            self.update_badges()
        elif name == "status_updated":
            post = payload
            for lv in self.lane_views.values():
                lv.update_post(real(post))
        elif name == "status_deleted":
            for lv in self.lane_views.values():
                lv.refresh()
        elif name == "lists_changed":
            self._rebuild_sidebar()
        elif name == "me_updated" and self.view.me is not None:
            self.who.set_text("@" + self.view.me.handle)
        elif name == "error":
            self.status(_("error", err=payload))
        elif name == "rate_limited":
            self.status(str(payload))
        elif name == "auth_failed":
            server = (self.view.auth or {}).get("server", "")
            acct = self.view.auth_handle
            login.LoginDialog(self, self._connect,
                              expect=(server, acct) if server and acct else None).present()

    # ---- actions ------------------------------------------------------------------------
    def act(self, what, post):
        fn = {"like": self.view.like, "share": self.view.share}[what]
        self.bridge.call(fn(post), lambda got: got and self._post_changed(got),
                         lambda err: self.status(_("error", err=err)))

    def _post_changed(self, got):
        for lv in self.lane_views.values():
            lv.update_post(real(got))
        for page in self.threads.values():
            for card in _cards(page):
                if real(card.entry).id == real(got).id:
                    card.update(real(got))

    def open_thread(self, post):
        root = real(post).id
        page = self.threads.get(root)
        if page is not None:
            self.tabs.set_current_page(self.tabs.page_num(page))
            return
        page = Gtk.ScrolledWindow()
        page.add_css_class("ft-view")
        page.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = Gtk.ListBox()
        box.set_selection_mode(Gtk.SelectionMode.NONE)
        box.add_css_class("ft-feed")
        box.set_margin_start(8)
        box.set_margin_end(8)
        page.set_child(box)
        page.focus_id = root
        self.threads[root] = page
        tab = Gtk.Box(spacing=4)
        title = Gtk.Label(label=_("thread_loading"))
        title.set_max_width_chars(24)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        tab.append(title)
        close = Gtk.Button(icon_name="window-close-symbolic")
        close.add_css_class("flat")
        close.connect("clicked", lambda _b: self.close_thread(root))
        tab.append(close)
        n = self.tabs.append_page(page, tab)
        self.tabs.set_tab_reorderable(page, True)
        self.tabs.set_current_page(n)
        self._tab_switched()

        def got(items):
            ctx = Ctx(self.cfg, self.view, self.theme, self.bridge, self, in_thread=True)
            posts = [it.post for it in items]
            unread = self.view.unread(posts)
            short = self.view.short_ids(posts)
            focus = None
            for it in items:
                card = Card(ctx, it.post.id, it.post, unread=it.post.id in unread,
                            short_id=short.get(it.post.id), depth=it.depth,
                            number=it.number)
                if it.post.id == root:
                    card.add_css_class("ft-focus")
                    focus = card
                box.append(card)
            if items:
                title.set_text(_("thread") + ": " + _short(items[0].post))
            if unread:
                self.view.mark_read(sorted(unread))
            if focus is not None:
                GLib.idle_add(lambda: (_scroll_to(page, box, focus), GLib.SOURCE_REMOVE)[1])
        self.bridge.call(self.view.thread(root), got,
                         lambda err: title.set_text(_("load_failed", err=err)))

    def close_thread(self, root):
        page = self.threads.pop(root, None)
        if page is not None:
            self.tabs.remove_page(self.tabs.page_num(page))
        self._tab_switched()

    # ---- links -------------------------------------------------------------------------
    def on_link(self, uri):
        if uri.startswith("fedtail:"):
            action, _sep, arg = uri[len("fedtail:"):].partition("/")
            if action == "thread":
                post = self.view.by_id(arg)
                if post is not None:
                    self.open_thread(post)
                    return
            if action == "resolve" and richtext.openable(arg):
                self.open_url(arg)
                return
            self.status(_("gtk_not_yet"))
            return
        self.open_url(uri)

    def open_url(self, url):
        if not richtext.openable(url):
            log.warning("not opened (scheme not allowed): %.80s", url)
            return
        from ...sysenv import open_external
        if open_external(url):
            return
        try:
            Gio.AppInfo.launch_default_for_uri(url, None)
        except GLib.Error as e:
            self.status(_("error", err=e.message))

    # ---- misc --------------------------------------------------------------------------
    def status(self, text):
        self.status_line.set_text(text or "")

    def _saved_size(self):
        size = self.view.get_state("gtk_window") or ""
        try:
            w, h = (int(x) for x in size.split("x"))
            return max(w, 480), max(h, 360)
        except ValueError:
            return 1000, 720

    def _close_request(self, _win):
        w, h = self.get_default_size()
        if w > 0 and h > 0:
            self.view.set_state("gtk_window", f"{w}x{h}")
        self.quitting = True
        return False


def _section(text):
    """A group's title in the sidebar: not a lane, can't be chosen."""
    row = Gtk.ListBoxRow(selectable=False, activatable=False)
    lab = Gtk.Label(label=text, xalign=0)
    lab.add_css_class("ft-account")
    lab.add_css_class("caption-heading")
    lab.set_margin_top(8)
    row.set_child(lab)
    return row


def _base(name):
    """lane_<name> strings exist for the built-in lanes; lists and tag lanes have titles."""
    return lanes_mod.canonical(name) if hasattr(lanes_mod, "canonical") else name


def _short(post):
    from ...model.text import snippet
    return snippet(post, 30) or "@" + post.author.handle


def _cards(page):
    box = page.get_child()
    if isinstance(box, Gtk.Viewport):
        box = box.get_child()
    child = box.get_first_child() if box is not None else None
    while child is not None:
        inner = child.get_child() if isinstance(child, Gtk.ListBoxRow) else child
        if isinstance(inner, Card):
            yield inner
        child = child.get_next_sibling()


def _scroll_to(page, box, widget):
    y = y_in(widget, box)
    if y is not None:
        page.get_vadjustment().set_value(max(0, y - 40))
