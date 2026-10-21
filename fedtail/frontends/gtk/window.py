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
from ..common.links import Links
from . import login
from .activity import ActivityLane, RequestsLane
from .card import Card
from .gi_setup import Gio, GLib, Gtk, Pango
from .lane import LaneView, y_in

log = logging.getLogger(__name__)

BADGE_KIND = {"replies": "hot", "bots": "quiet", "activity": "quiet"}  # as qt/window.py
SPECIAL = {"activity": ActivityLane, "requests": RequestsLane}  # lanes that aren't posts


@dataclass
class Ctx:
    """What a card or a lane needs from the window."""
    cfg: dict
    view: object
    theme: object
    bridge: object
    win: object = None
    in_thread: bool = False
    images: object = None
    extra: dict = field(default_factory=dict)

    @property
    def me_id(self):
        me = self.view.me
        return me.id if me is not None else None

    def supports(self, what):
        try:
            return bool(self.view.supports(what))
        except Exception:  # noqa: BLE001 — not connected yet
            return False

    def subscribed(self, entry):
        return self.view.subscribed(entry)

    def thread_quiet(self, entry):
        return self.view.thread_quiet(entry)

    def on_link(self, uri):
        self.win.on_link(uri)

    def open_url(self, url):
        self.win.open_url(url)

    def open_thread(self, post):
        self.win.open_thread(post)

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
        from .images import Images
        self.images = Images(view, bridge)
        self.ctx = Ctx(self.cfg, view, theme, bridge, self, images=self.images)
        self.links = Links(view, self)  # what fedtail: links do (common/links.py)
        self.cmdline = None
        from .notify import Notifier
        self.notifier = Notifier(self, app)
        self.lane_views = {}     # name -> LaneView
        self.lane_rows = {}      # name -> LaneRow
        self.threads = {}        # root post id -> page widget
        self.accounts = {}       # account id -> page widget
        self.quitting = False
        bridge.on_event = self.on_event
        bridge.on_error = lambda text: self.status(_("error", err=text))
        self.set_default_size(*self._saved_size())

        refresh = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh.set_tooltip_text(_("refresh"))
        refresh.connect("clicked", lambda _b: self.view.poll_now())
        write = Gtk.Button(label=_("write"))
        write.add_css_class("ft-primary")
        write.add_css_class("suggested-action")
        write.connect("clicked", lambda _b: self.compose())
        self.who = Gtk.Label()
        self.who.add_css_class("ft-muted")
        toolbar = None
        if own_titlebar(self.cfg):
            header = Gtk.HeaderBar()
            header.pack_start(write)
            header.pack_start(refresh)
            header.pack_end(self.who)
            self.set_titlebar(header)
        else:  # the desktop draws the frame (KDE, XFCE…): the buttons get a bar of their own
            toolbar = Gtk.Box(spacing=6)
            toolbar.add_css_class("toolbar")
            refresh.add_css_class("flat")
            toolbar.append(write)
            toolbar.append(refresh)
            spacer = Gtk.Box()
            spacer.set_hexpand(True)
            toolbar.append(spacer)
            self.who.set_margin_end(8)
            toolbar.append(self.who)

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
        if toolbar is not None:
            outer.append(toolbar)
        paned.set_vexpand(True)
        outer.append(paned)
        if self.cfg["ui"]["command_line"]:
            from .cmdline import CommandLine
            self.cmdline = CommandLine(self)
            outer.append(self.cmdline)
        outer.append(self.status_line)
        self.set_child(outer)

        self._shortcuts()
        self.connect("notify::is-active", lambda *_a: self._activated())
        self.connect("close-request", self._close_request)
        self.connect("destroy", self._stop)

    def _shortcuts(self):
        """The same keys as the Qt window where it has the thing: Ctrl+L the command line,
        Ctrl+N write, F5 refresh, Ctrl+W a thread's tab, Ctrl+Q quit. (Never F1: it sits
        next to Esc.)"""
        ctl = Gtk.ShortcutController()
        ctl.set_scope(Gtk.ShortcutScope.GLOBAL)

        def add(trigger, fn):
            ctl.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string(trigger),
                                              Gtk.CallbackAction.new(lambda *_a: (fn(), True)[1])))
        add("<Control>l", lambda: self.cmdline is not None and self.cmdline.entry.grab_focus())
        add("<Control>n", self.compose)
        add("F5", self.view.poll_now)
        add("<Control>q", self.close)
        add("<Control>w", self._close_current_tab)
        self.add_controller(ctl)

    def _close_current_tab(self):
        page = self.tabs.get_nth_page(self.tabs.get_current_page())
        root = next((r for r, p in self.threads.items() if p is page), None)
        if root is not None:
            self.close_thread(root)
        acc = next((a for a, p in self.accounts.items() if p is page), None)
        if acc is not None:
            self.close_account(acc)

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
            # lanes that aren't status streams: only Activity and follow requests are known
            names = [n for n in names if n in by_name and
                     (by_name[n].source is not None or n in SPECIAL)]
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
            lv = SPECIAL[name](self) if name in SPECIAL else LaneView(self.ctx, name, title)
            self.lane_views[name] = lv
            self.stack.add_named(lv, name)
        before = self.stack.get_visible_child()
        if before is not lv and hasattr(before, "hidden"):
            before.hidden()
        self.stack.set_visible_child(lv)
        self.tabs.set_current_page(0)
        self.view.set_active_lane(name)
        self.view.set_state("lane", name)
        lv.shown()

    def lane_title(self, name):
        return self.view.lane_title(name) or _("lane_" + _base(name))

    def lane_on_screen(self, name):
        return self.tabs.get_current_page() == 0 and self._current_lane() == name

    def update_badges(self):
        for name, row in self.lane_rows.items():
            try:
                if name == "activity":
                    row.set_count(int(self.view.activity_unread() or 0))
                elif name == "requests":
                    row.set_count(len(self.view.follow_requests() or ()))
                else:
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
                if lname in SPECIAL:
                    continue
                if changed is None or lname in changed:
                    # only the lane on screen catches up now; the others when shown
                    if lv.get_mapped():
                        lv.refresh()
                    else:
                        lv.dirty = True
            self.update_badges()
        elif name == "status_updated" and payload is not None:
            self._post_changed(payload)
        elif name == "status_deleted":
            for lv in self.lane_views.values():
                if lv.get_mapped():
                    lv.refresh()
                else:
                    lv.dirty = True
        elif name in ("activity_updated", "activity_seen", "requests_updated"):
            lname = "requests" if name == "requests_updated" else "activity"
            lv = self.lane_views.get(lname)
            if lv is not None and name != "activity_seen":
                if lv.get_mapped():
                    lv.refresh()
                else:
                    lv.dirty = True
            self.update_badges()
        elif name == "prefetch":  # pictures of posts just come: to disk, ahead of time
            self.images.prefetch(payload)
        elif name == "prefetch_video":  # their videos too (feed.prefetch = "all")
            self.images.prefetch_video(payload)
        elif name == "notify":
            self.notifier.notify(payload)
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

    # ---- posts -------------------------------------------------------------------------
    def _post_changed(self, got):
        for lv in self.lane_views.values():
            lv.update_post(real(got))
        for page in self.threads.values():
            for card in _cards(page):
                if real(card.entry).id == real(got).id:
                    card.update(real(got))

    def open_thread(self, post):
        """A thread in a tab of its own; post: a Post, a Share or a post id."""
        root = real(post).id if not isinstance(post, str) else post
        page = self.threads.get(root)
        if page is not None:
            self.tabs.set_current_page(self.tabs.page_num(page))
            return
        page, box, title = self._new_tab(_("thread_loading"),
                                         lambda: self.close_thread(root))
        page.focus_id = root
        self.threads[root] = page

        def got(items):
            ctx = Ctx(self.cfg, self.view, self.theme, self.bridge, self, in_thread=True,
                      images=self.images)
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

    def _new_tab(self, text, close_fn):
        """A tab after the lanes: a scrolled list of cards; (page, list, title label)."""
        page = Gtk.ScrolledWindow()
        page.add_css_class("ft-view")
        page.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = Gtk.ListBox()
        box.set_selection_mode(Gtk.SelectionMode.NONE)
        box.add_css_class("ft-feed")
        box.set_margin_start(8)
        box.set_margin_end(8)
        page.set_child(box)
        tab = Gtk.Box(spacing=4)
        title = Gtk.Label(label=text)
        title.set_width_chars(10)  # an ellipsized label asks for nothing: give it room
        title.set_max_width_chars(24)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        tab.append(title)
        close = Gtk.Button(icon_name="window-close-symbolic")
        close.add_css_class("flat")
        close.connect("clicked", lambda _b: close_fn())
        tab.append(close)
        n = self.tabs.append_page(page, tab)
        self.tabs.set_tab_reorderable(page, True)
        self.tabs.set_current_page(n)
        self._tab_switched()
        return page, box, title

    # ---- profiles ----------------------------------------------------------------------
    def open_account(self, acc_id):
        """A profile in a tab: the face, name, bio, counts, Follow and Mention, the posts."""
        page = self.accounts.get(acc_id)
        if page is not None:
            self.tabs.set_current_page(self.tabs.page_num(page))
            return
        page, box, title = self._new_tab(_("loading"), lambda: self.close_account(acc_id))
        self.accounts[acc_id] = page
        me = self.view.me
        own = me is not None and me.id == acc_id

        def got_account(acc):
            if acc is None:
                title.set_text(_("load_failed", err="?"))
                return
            title.set_text("@" + acc.handle)
            box.append(self._profile_head(acc, own))
            self.call(self.view.account_posts(acc_id), got_posts)

        def got_posts(posts):
            short = self.view.short_ids(posts)
            for p in posts:
                box.append(Card(self.ctx, p.id, p, short_id=short.get(real(p).id)))
        self.call(self.view.account(acc_id), got_account,
                  lambda err: title.set_text(_("load_failed", err=err)))

    def close_account(self, acc_id):
        page = self.accounts.pop(acc_id, None)
        if page is not None:
            self.tabs.remove_page(self.tabs.page_num(page))
        self._tab_switched()

    def _profile_head(self, acc, own):
        from .card import Avatar, link_markup, name_of
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        head.add_css_class("ft-card")
        top = Gtk.Box(spacing=10)
        top.append(Avatar(self.ctx, acc, 64))
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        name = Gtk.Label(label=name_of(acc), xalign=0)
        name.add_css_class("ft-name")
        name.add_css_class("title-3")
        names.append(name)
        handle = Gtk.Label(xalign=0, selectable=True)
        handle.set_markup(link_markup(acc.url or "", "@" + acc.handle))
        handle.connect("activate-link", lambda _l, u: (self.open_url(u), True)[1])
        handle.add_css_class("ft-muted")
        names.append(handle)
        counts = Gtk.Label(xalign=0, label=" · ".join((
            _("posts_n", n=acc.posts), _("followers_n", n=acc.followers),
            _("following_n", n=acc.following))))
        counts.add_css_class("ft-muted")
        names.append(counts)
        names.set_hexpand(True)
        top.append(names)
        buttons = Gtk.Box(spacing=6)
        buttons.set_valign(Gtk.Align.START)
        if not own:
            follow = Gtk.Button(label=_("follow"))
            follow.add_css_class("ft-primary")
            follow.set_sensitive(False)
            buttons.append(follow)

            def show(rel):
                on = bool(rel and (rel.following or rel.requested))
                follow.set_label(_("unfollow") if on else _("follow"))
                follow.set_sensitive(True)
                follow.following = on

            def toggle(_b):
                follow.set_sensitive(False)
                self.call(self.view.follow(acc.id, not getattr(follow, "following", False)),
                          show, lambda e: (follow.set_sensitive(True), self.error(e)))
            follow.connect("clicked", toggle)
            self.call(self.view.relationship(acc.id), show,
                      lambda _e: follow.set_sensitive(True))
            mention = Gtk.Button(label=_("mention"))
            mention.connect("clicked", lambda _b: self.compose(text=f"@{acc.handle} "))
            buttons.append(mention)
        top.append(buttons)
        head.append(top)
        if acc.note:
            from .. import pango
            bio = Gtk.Label(xalign=0, wrap=True, selectable=False)
            bio.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            bio.set_markup(pango.markup(self.view.in_app_html(acc.note)))
            bio.connect("activate-link", lambda _l, u: (self.on_link(u), True)[1])
            head.append(bio)
        for f in acc.fields:
            from .. import pango
            row = Gtk.Label(xalign=0, wrap=True)
            row.set_markup(f"<b>{GLib.markup_escape_text(f.name)}</b>  " +
                           ("✓ " if f.verified else "") + pango.markup(f.value))
            row.connect("activate-link", lambda _l, u: (self.on_link(u), True)[1])
            head.append(row)
        return head

    # ---- links: common/links.py asks these ---------------------------------------------
    def on_link(self, uri):
        self.links.open(uri)

    def call(self, future, ok=None, fail=None):
        return self.bridge.call(future, ok, fail or self.error)

    def error(self, text):
        self.status(_("error", err=text))

    def confirm(self, title, text, then):
        """Ask; then() on yes. GTK's dialogs answer later, so this never blocks."""
        dlg = Gtk.AlertDialog()
        dlg.set_message(title)
        dlg.set_detail(text)
        dlg.set_buttons([_("gtk_no"), _("gtk_yes")])
        dlg.set_cancel_button(0)
        dlg.set_default_button(1)

        def done(d, res):
            try:
                if d.choose_finish(res) == 1:
                    then()
            except GLib.Error:
                pass  # dismissed
        dlg.choose(self, None, done)
        self._asking = dlg  # (tests answer it)
        return dlg

    def compose(self, reply_to=None, invite=False, edit=None, quote=None, text=""):
        from .compose import ComposeWindow
        if self.view.me is None:
            return None
        win = ComposeWindow(self, reply_to=reply_to, invite=invite, edit=edit, quote=quote,
                            text=text)
        win.present()
        return win

    def redrafted(self, d):
        """The deleted post back in the editor, as it was typed (d: a Redraft)."""
        parent = self.view.by_id(d.reply_to) if d.reply_to else None
        win = self.compose(reply_to=parent)
        if win is not None:
            win.fill(d.text, d.warning, d.visibility, d.language)
        if d.media:
            self.status(_("redraft_media", n=d.media))

    def copy_handle(self, handle):
        handle = "@" + handle.lstrip("@")
        self.get_clipboard().set(handle)
        self.status(_("handle_copied", handle=handle))

    def put_alias(self, alias):
        if self.cmdline is not None:
            self.cmdline.put_alias(alias)

    def resolve_link(self, url):
        """A fediverse link: the post here when the server knows it, else outside."""
        def got(found):
            from ...model import Account, Post, Share
            if isinstance(found, (Post, Share)):
                self.open_thread(found)
            elif isinstance(found, Account):
                self.open_account(found.id)
            else:
                self.open_url(url)
        self.call(self.view.resolve(url), got, lambda _e: self.open_url(url))

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
        self._stop()
        return False

    def _stop(self, *_a):
        for lv in self.lane_views.values():
            lv.stop()
        self.images.shutdown()


# desktops whose windows draw their own title bar (client-side decorations): there the
# GTK header bar is at home; elsewhere the desktop's frame is (and stays usable even if
# fedtail hangs: a frozen header bar can hold the pointer, as it did on KDE)
CSD_DESKTOPS = ("gnome", "budgie", "pantheon", "unity", "phosh")


def own_titlebar(cfg):
    """ui.gtk_headerbar: "on", "off", or "auto" — on with libadwaita or in GNOME and
    its kin, off in KDE, XFCE, MATE, Cinnamon and the rest."""
    import os

    from . import gi_setup
    mode = cfg["ui"].get("gtk_headerbar", "auto")
    if mode != "auto":
        return mode == "on"
    if gi_setup.Adw is not None:
        return True
    desk = (os.environ.get("XDG_CURRENT_DESKTOP") or "").lower()
    return any(d in desk for d in CSD_DESKTOPS)


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
