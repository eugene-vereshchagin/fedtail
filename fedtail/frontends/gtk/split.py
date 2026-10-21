"""The split layout in GTK (ui.layout = "split", or --layout split), as the Qt window
has it (docs/LAYOUTS.md): the roster — a window of its own with the lanes, followed
threads, private talks and people, as a messenger's contact list — and the main window
as the messages window: a tab per lane, thread, profile or talk, the author of the post
under the pointer in a bar over a lane, and an input line at the bottom that answers
what's in front (or writes a new post, or a private message in a talk).

What the rows say, what the input line starts with, whose face goes where, when what's
typed is a command — common/roster.py and common/split.py, shared with Qt."""

from __future__ import annotations

import logging

from ...i18n import _
from ...model import Scheduled, real
from ..common import compose as rules
from ..common import roster as rrules
from ..common import split
from ..common.actions import vis_word
from .gi_setup import GLib, Gtk, Pango, set_markup, tip
from .icons import nobody

log = logging.getLogger(__name__)

FACE = 40          # the face beside the input line
REFRESH_MS = 300   # bursts of events: one roster rebuild


# ---- the roster ---------------------------------------------------------------------------
class RosterRow(Gtk.ListBoxRow):
    def __init__(self, roster, item, group):
        super().__init__()
        self.roster, self.key, self.group = roster, rrules.row_key(item), group
        self.item = None
        box = Gtk.Box(spacing=8)
        for m in ("start", "end"):
            getattr(box, "set_margin_" + m)(6)
        box.set_margin_top(3)
        box.set_margin_bottom(3)
        own = {"person": "status", "talk": "talk", "thread": "thread"}.get(item.kind)
        from .. import iconpack
        from . import icons
        t = roster.win.theme
        pic = icons.image(own, t) if own else None  # a flower for a person, as in QIP
        if pic is None and icons.pictures(t):  # else the lane's picture
            kind = {"thread": "subs", "talk": "direct", "person": "direct"}.get(
                item.kind, (item.key or "").split(":")[0])
            pic = icons.image(iconpack.lane_picture(kind), t)
        if pic is not None:
            pic.set_valign(Gtk.Align.START)
            pic.set_margin_top(2)
            box.append(pic)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        top = Gtk.Box(spacing=6)
        self.name = Gtk.Label(xalign=0, hexpand=True)
        self.name.set_ellipsize(Pango.EllipsizeMode.END)
        top.append(self.name)
        self.badge = Gtk.Label()
        self.badge.add_css_class("ft-badge")
        top.append(self.badge)
        col.append(top)
        self.status = Gtk.Label(xalign=0)
        self.status.add_css_class("ft-muted")
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        col.append(self.status)
        self.line = Gtk.Label(xalign=0)
        self.line.add_css_class("ft-muted")
        self.line.set_ellipsize(Pango.EllipsizeMode.END)
        col.append(self.line)
        box.append(col)
        self.face = Gtk.Box()
        box.append(self.face)
        self._face_url = None
        self.set_child(box)
        self.update_item(item)

    def update_item(self, item):
        self.item = item
        roster = self.roster
        compact = roster.look["compact"]
        faces = roster.win.theme.shape.get("roster_rows") == "faces" and not compact
        new = item.unread > 0
        esc = GLib.markup_escape_text(item.title)
        markup = f"<b>{esc}</b>" if new else esc
        set_markup(self.name, markup)
        self.badge.set_text(str(item.unread) if item.unread < 1000 else "999+")
        self.badge.set_visible(new)
        line, tip_text, status = rrules.lines(item, faces)
        self.line.set_text(line)
        self.line.set_visible(bool(line) and not compact)
        self.status.set_text(status)
        self.status.set_visible(bool(status))
        tip(self, rrules.tip(item))
        url = rrules.face_url(item)
        if url != self._face_url and not compact:
            self._face_url = url
            while (c := self.face.get_first_child()) is not None:
                self.face.remove(c)
            who = item.who if item.who is not None else \
                (item.last.author if item.last is not None else None)
            if who is not None:
                from .card import Avatar
                self.face.append(Avatar(roster.win.ctx, who, 28))
        self.face.set_visible(not compact)

    def matches(self, text):
        return rrules.matches(self.item, self.line.get_text(), text)


class RosterHead(Gtk.ListBoxRow):
    """A group's title: "▾ Ленты (2/5)"; a click folds it."""

    def __init__(self, roster, group):
        super().__init__(selectable=False)
        self.roster, self.group = roster, group.name
        self.label = Gtk.Label(xalign=0)
        self.label.add_css_class("ft-account")
        self.label.set_margin_top(6)
        self.label.set_margin_start(6)
        self.set_child(self.label)
        tip(self, _("group_fold_tip"))
        self.show_counts(group, group.name in roster.folded)

    def show_counts(self, group, folded):
        title, lit, n = rrules.group_counts(group)
        word = rrules.group_word(self.roster.win.theme.words, lit)
        dot = self.roster.win.theme.c["dot"].css()
        text = word.format(arrow="▸" if folded else "▾",
                           title=GLib.markup_escape_text(title),
                           lit=f'<span foreground="{dot}">{lit}</span>', n=n)
        set_markup(self.label, text)


class RosterWindow(Gtk.Window):
    """The roster: a window of its own beside the messages window. A double click (or
    Enter) opens; the search filters, Enter there opens the only one found or searches
    the server; ≡, the accounts and how it looks at the bottom."""

    def __init__(self, win, app=None):
        super().__init__(title=_("roster_title"))
        if app is not None:
            self.set_application(app)
        self.win = win
        self.add_css_class("fedtail")
        self.add_css_class("ft-roster")
        # ≡ here is the main window's menu: its actions ("win.…") work from here too
        self.insert_action_group("win", win)
        from .gi_setup import Gio
        own = Gio.SimpleActionGroup()
        for name, fn in (("open", lambda: self.open(self._menu_key)),
                         ("read", lambda: self.read_all(self._menu_key))):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", lambda _a, _p, fn=fn: fn())
            own.add_action(act)
        self.insert_action_group("roster", own)
        self._menu_key = None
        size = (win.view.get_state("gtk_roster") or "").split("x")
        try:
            self.set_default_size(max(220, int(size[0])), max(320, int(size[1])))
        except (ValueError, IndexError):
            self.set_default_size(300, 680)
        self.rows, self.heads = {}, {}
        self.folded = rrules.folded(win.view)
        self.look = rrules.look(win.view)
        self._shape = None
        self._timer = 0
        self._computing = self._again = False
        self._mutuals_asked = False
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for m in ("top", "bottom", "start", "end"):
            getattr(v, "set_margin_" + m)(6)
        # who I am: face, name, @address, what's new in Activity
        self.head = Gtk.Box(spacing=8)
        self.me_face = Gtk.Box()
        self.head.append(self.me_face)
        who = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        self.me_name = Gtk.Label(xalign=0)
        self.me_name.add_css_class("ft-name")
        self.me_name.set_ellipsize(Pango.EllipsizeMode.END)
        who.append(self.me_name)
        self.me_handle = Gtk.Label(xalign=0)
        self.me_handle.add_css_class("ft-muted")
        self.me_handle.set_ellipsize(Pango.EllipsizeMode.END)
        who.append(self.me_handle)
        self.news = Gtk.Label(xalign=0)
        self.news.connect("activate-link", lambda _l, _u: (self.open("activity"), True)[1])
        who.append(self.news)
        self.head.append(who)
        v.append(self.head)
        self.search = Gtk.SearchEntry(placeholder_text=_("roster_search"))
        tip(self.search, _("roster_search_tip"))
        self.search.connect("search-changed", lambda e: self._filter(e.get_text()))
        self.search.connect("activate", lambda _e: self._search_enter())
        v.append(self.search)
        self.list = Gtk.ListBox()
        self.list.add_css_class("ft-sidebar")
        self.list.add_css_class("navigation-sidebar")
        self.list.set_activate_on_single_click(False)  # a double click opens, as in QIP
        self.list.connect("row-activated", self._activated)
        right = Gtk.GestureClick(button=3)
        right.connect("pressed", self._menu)
        self.list.add_controller(right)
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_child(self.list)
        v.append(sc)
        # at the bottom, as in every messenger: the menu, the accounts, how it looks
        self.bottom = Gtk.Box(spacing=4)
        from .menu import button
        self.menu_btn = button(win, win.menu)
        self.bottom.append(self.menu_btn)
        self.account_btn = button(win, win.menu, accounts_only=True)
        self.account_btn.set_icon_name("")
        self.account_btn.set_label(_("accounts"))
        self.account_btn.set_hexpand(True)
        self.bottom.append(self.account_btn)
        self.look_btn = Gtk.MenuButton(label="⚙", always_show_arrow=False)
        tip(self.look_btn, _("roster_look"))
        self.look_btn.set_popover(self._look_popover())
        self.bottom.append(self.look_btn)
        self.dress()
        v.append(self.bottom)
        self.set_child(v)
        self._apply_look()
        self.connect("close-request", self._close_request)

    # ---- contents ------------------------------------------------------------------
    def refresh_soon(self):
        if not self._timer:
            self._timer = GLib.timeout_add(REFRESH_MS, self._refresh_now)

    def _refresh_now(self):
        self._timer = 0
        self.refresh_in_background()
        return GLib.SOURCE_REMOVE

    def refresh_in_background(self):
        """Worked out in the core's threads (it reads every lane), shown when done."""
        view = self.win.view
        if view.me is None:
            return self.refresh()
        if self._computing:
            self._again = True
            return None
        self._computing = True

        def done(groups):
            self._computing = False
            self._show(groups)
            if self._again:
                self._again = False
                self.refresh_soon()

        def failed(e):
            self._computing = False
            log.info("roster: %s", e)
        self.win.bridge.call(self.win.core.submit(view.roster), done, failed)
        return None

    def refresh(self):
        view = self.win.view
        self._show(view.roster() if view.me is not None else [])

    def _show(self, groups):
        view = self.win.view
        self._show_me()
        if view.me is not None and not self._mutuals_asked:
            self._mutuals_asked = True  # whom to write to: asked once a day
            self.win.bridge.call(view.refresh_mutuals(), lambda _n: self.refresh_soon(),
                                 lambda e: log.info("mutuals: %s", e))
        shape = [(g.name, tuple(rrules.row_key(i) for i in g.items)) for g in groups]
        if shape != self._shape:
            self._build(groups)
            self._shape = shape
        for g in groups:
            head = self.heads.get(g.name)
            if head is not None:
                head.show_counts(g, g.name in self.folded)
            for item in g.items:
                row = self.rows.get(rrules.row_key(item))
                if row is not None:
                    row.update_item(item)
        self._filter(self.search.get_text())

    def _build(self, groups):
        while (c := self.list.get_first_child()) is not None:
            self.list.remove(c)
        self.rows, self.heads = {}, {}
        for g in groups:
            if not g.items:
                continue
            head = RosterHead(self, g)
            self.heads[g.name] = head
            self.list.append(head)
            for item in g.items:
                row = RosterRow(self, item, g.name)
                self.rows[row.key] = row
                self.list.append(row)

    def dress(self):
        """Pictures on the bottom buttons (ui.additional_icons); again after a theme."""
        from . import icons
        t = self.win.theme
        icons.dress(self.menu_btn, "menu", t, words=_("menu"), glyph="≡")
        icons.dress(self.look_btn, "settings", t, glyph="⚙")
        self._dress_account()

    def _dress_account(self):
        from . import icons
        icons.dress(self.account_btn, "accounts", self.win.theme,
                    words=getattr(self, "_account_word", _("accounts")))

    def _show_me(self):
        me = self.win.view.me
        if me is None:
            self.me_name.set_text(_("roster_offline"))
            self.me_handle.set_text("")
            self.news.set_text("")
            return
        self.me_name.set_text(me.name or me.username or me.handle)
        self.me_handle.set_text("@" + me.handle)
        self._account_word = "@" + me.handle.partition("@")[0]
        self._dress_account()
        try:
            n = int(self.win.view.activity_unread() or 0)
        except Exception:  # noqa: BLE001
            n = 0
        text = _("roster_news", n=n) if n else _("roster_no_news")
        set_markup(self.news, f'<a href="fedtail:activity">{GLib.markup_escape_text(text)}</a>')
        if getattr(self, "_my_face", None) != me.avatar_static:
            self._my_face = me.avatar_static
            while (c := self.me_face.get_first_child()) is not None:
                self.me_face.remove(c)
            from .card import Avatar
            self.me_face.append(Avatar(self.win.ctx, me, 44))

    def _filter(self, text):
        for head in self.heads.values():
            head.set_visible(self.look["groups"] or bool(text))
        for row in self.rows.values():
            folded = row.group in self.folded and self.look["groups"]
            row.set_visible(not rrules.hidden(row.item, row.line.get_text(), text, folded,
                                              self.look))

    def toggle(self, group):
        self.folded ^= {group}
        self.win.view.set_state("roster_folded", sorted(self.folded))
        self.refresh()

    # ---- acting --------------------------------------------------------------------
    def _activated(self, _list, row):
        if isinstance(row, RosterHead):
            self.toggle(row.group)
        elif isinstance(row, RosterRow):
            self.open(row.key)

    def open(self, key):
        """A row chosen: its lane, thread or talk in front in the messages window."""
        kind, ident = rrules.what(key)
        win = self.win
        win.present()
        if kind == "lane":
            win.select_lane(key)
        elif kind == "person":
            row = self.rows.get(key)
            if row is not None and row.item.who is not None:
                win.write_to(row.item.who)
        else:
            win.open_thread(ident)

    def _search_enter(self):
        text = self.search.get_text()
        shown = [k for k, r in self.rows.items() if r.matches(text)]
        if len(shown) == 1:
            self.open(shown[0])
        elif text.strip():
            self.win.present()
            self.win.open_search(text.strip())
        self.search.set_text("")

    def _menu(self, _g, _n, x, y):
        row = self.list.get_row_at_y(int(y))
        from .gi_setup import Gdk, Gio
        model = Gio.Menu()
        model.append_section(None, Gio.Menu())
        if isinstance(row, RosterRow):
            self._menu_key = row.key
            model.append(_("roster_open"), "roster.open")
            if row.item.unread:
                model.append(_("mark_all_read"), "roster.read")
        pop = Gtk.PopoverMenu.new_from_model(model)
        pop.set_parent(self.list)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        pop.set_pointing_to(rect)
        pop.connect("closed", lambda p: GLib.idle_add(p.unparent))
        if model.get_n_items():
            pop.popup()

    def read_all(self, key):
        view = self.win.view
        row = self.rows.get(key)
        ids = rrules.read_ids(view, key, row.item if row is not None else None)
        if ids:
            view.mark_read(ids)

    # ---- how it looks ----------------------------------------------------------------
    def _look_popover(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for key in ("compact", "header", "search", "bottom", "only_new", "groups"):
            b = Gtk.CheckButton(label=_("roster_look_" + key), active=bool(self.look[key]))
            b.connect("toggled", lambda c, k=key: self.set_look(k, c.get_active()))
            box.append(b)
        pop = Gtk.Popover()
        pop.set_child(box)
        return pop

    def set_look(self, key, on):
        self.look[key] = bool(on)
        self.win.view.set_state("roster_look", self.look)
        if key == "compact":
            self._shape = None  # the rows built anew
        self._apply_look()
        self.refresh()

    def _apply_look(self):
        self.head.set_visible(self.look["header"])
        self.search.set_visible(self.look["search"])
        self.bottom.set_visible(self.look["bottom"])

    def _close_request(self, _w):
        w, h = self.get_default_size()
        if w > 0 and h > 0:
            self.win.view.set_state("gtk_roster", f"{w}x{h}")
        if not self.win.quitting:  # the roster closed: fedtail closes (as QIP did)
            self.win.quitting = True
            self.win.close()
        return False


# ---- the input line -------------------------------------------------------------------
class InputDock(Gtk.Box):
    """At the bottom of the messages window: what's typed answers the thread in front
    (the post I came for), writes privately in a talk, or makes a new post; a Point-style
    command ("#a3f text", "! #a3f") goes to the command line. Ctrl+Enter sends (a
    command: plain Enter)."""

    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.win = win
        self.add_css_class("ft-dock")
        for m in ("top", "bottom", "start", "end"):
            getattr(self, "set_margin_" + m)(6)
        self.target = None      # the Post answered; None: a new post
        self._prefill = ""
        self._about = _("dock_new")
        self._to = None
        self.media = []         # [(path, description)]
        self.language = None    # None: post.language
        view = win.view
        self.visibility = "public"
        try:
            self.visibility = view.reply_visibility(None)
        except Exception:  # noqa: BLE001 — not connected yet
            pass
        bar = Gtk.Box(spacing=2)
        self.vis_btn = Gtk.MenuButton()
        tip(self.vis_btn, _("web_visibility"))
        pop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        from ...model import VISIBILITIES
        for v in VISIBILITIES:
            b = Gtk.Button(label=vis_word(v))
            b.add_css_class("flat")
            b.connect("clicked", lambda _b, x=v: (self.set_visibility(x),
                                                  self.vis_btn.popdown()))
            pop_box.append(b)
        pop = Gtk.Popover()
        pop.set_child(pop_box)
        self.vis_btn.set_popover(pop)
        bar.append(self.vis_btn)
        self.cw_btn = Gtk.ToggleButton(label="CW")
        tip(self.cw_btn, _("dock_cw"))
        self.cw_btn.connect("toggled", lambda b: self._cw_toggled(b.get_active()))
        bar.append(self.cw_btn)
        self.attach_btn = Gtk.Button(label=_("dock_attach_word"))
        tip(self.attach_btn, _("dock_attach"))
        self.attach_btn.connect("clicked", lambda _b: self._attach())
        bar.append(self.attach_btn)
        self.lang_btn = Gtk.MenuButton(label=_("dock_lang_default"))
        tip(self.lang_btn, _("dock_language"))
        self.lang_btn.set_create_popup_func(self._fill_languages)
        bar.append(self.lang_btn)
        for b in (self.vis_btn, self.cw_btn, self.attach_btn, self.lang_btn):
            b.add_css_class("flat")
        self.about = Gtk.Label(xalign=0, hexpand=True)
        self.about.add_css_class("ft-muted")
        self.about.set_ellipsize(Pango.EllipsizeMode.END)
        bar.append(self.about)
        self.count = Gtk.Label()
        self.count.add_css_class("ft-muted")
        bar.append(self.count)
        self.append(bar)
        self.cw = Gtk.Entry(placeholder_text=_("dock_cw"))
        self.cw.set_visible(False)
        self.append(self.cw)
        row = Gtk.Box(spacing=6)
        self.text = Gtk.TextView()
        self.text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text.add_css_class("ft-compose-text")
        for m in ("top", "bottom", "left", "right"):
            getattr(self.text, f"set_{m}_margin")(6)
        sc = Gtk.ScrolledWindow(hexpand=True)
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_min_content_height(FACE + 8)
        sc.set_child(self.text)
        sc.add_css_class("ft-compose-frame")
        row.append(sc)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.face = Gtk.Box(halign=Gtk.Align.CENTER, vexpand=True, valign=Gtk.Align.CENTER)
        click = Gtk.GestureClick()
        click.connect("released", lambda *_a: self._to is not None and
                      self.win.open_account(self._to.id))
        self.face.add_controller(click)
        side.append(self.face)
        self.send_btn = Gtk.Button(label=_("dock_send"))
        self.send_btn.add_css_class("suggested-action")
        self.send_btn.add_css_class("ft-primary")
        tip(self.send_btn, _("dock_send") + " (Ctrl+Enter)")
        self.send_btn.connect("clicked", lambda _b: self.send())
        side.append(self.send_btn)
        row.append(side)
        self.append(row)
        self.suggest = Gtk.Label(xalign=0)
        self.suggest.add_css_class("ft-muted")
        self.suggest.set_visible(False)
        self.append(self.suggest)
        self.buffer = self.text.get_buffer()
        self.buffer.connect("changed", lambda _b: self._count())
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._key)
        self.text.add_controller(keys)
        self.dress()
        self._say()
        self._count()

    # ---- what it answers ---------------------------------------------------------------
    def _text(self):
        return self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(),
                                    False)

    def _set_text(self, text):
        self.buffer.set_text(text)
        self.buffer.place_cursor(self.buffer.get_end_iter())

    def _typed(self):
        return self._text().strip() != self._prefill.strip()

    def follow(self, page):
        """The tab in front changed: a thread is answered (the post I came for, else its
        newest), a talk written to privately, anything else — a new post."""
        if self._typed():
            return  # words of mine on their way: they keep whom they answer
        who = getattr(page, "who", None)
        if who is not None:
            self.write_to(who, focus=False)
            return
        posts = getattr(page, "posts", None) or []
        focus = getattr(page, "focus_id", None)
        post = next((p for p in posts if p.id == focus), None) or \
            (max(posts, key=lambda p: (p.created is not None, p.created or 0))
             if posts else None)
        self.set_target(post)

    def reply_to(self, post):
        """Reply (the card's button): this post answered here, not in a window."""
        self.target = None
        self.set_target(post, fresh=not self._typed())
        self.text.grab_focus()

    def write_to(self, account, focus=True):
        """A private message to someone: "@them ", direct."""
        self.target = None
        self.set_target(None, fresh=True)
        start = split.private_start(account)
        self._prefill = start.prefill
        self._set_text(self._prefill)
        self.set_visibility(start.visibility)
        self.show_whom(start.whom)
        self._about = start.about
        self._say()
        if focus:
            self.text.grab_focus()

    def start_with(self, text):
        self.target = None
        self.set_target(None, fresh=True)
        self._set_text(text)
        self.text.grab_focus()

    def set_target(self, post, fresh=None):
        if post is not None and self.target is not None and post.id == self.target.id:
            return
        self.target = post
        if fresh is None:
            fresh = not self._typed()
        start = split.reply_start(self.win.view, post)
        if fresh:
            self._prefill = start.prefill
            self._set_text(self._prefill)
            self.visibility = start.visibility
            self._show_visibility()
        self.show_whom(start.whom)
        self._about = start.about
        self._say()

    def show_whom(self, account):
        """The face beside the line: whom this goes to (QIP), or mine (the Agent)."""
        me = self.win.view.me
        account = split.face(split.faces_mode(self.win.cfg, self.win.theme.shape), account,
                             me)
        self._to = account
        while (c := self.face.get_first_child()) is not None:
            self.face.remove(c)
        if account is not None:
            from .card import Avatar
            self.face.append(Avatar(self.win.ctx, account, FACE))
            tip(self.face, "@" + account.handle)
        else:  # nobody yet: the pack's silhouette, if pictures are on
            stand_in = nobody(self.win.theme, FACE)
            if stand_in is not None:
                self.face.append(stand_in)
        self.face.set_visible(self.face.get_first_child() is not None)

    def _say(self):
        self.about.set_text(split.about_line(self._about, self.visibility))

    def set_visibility(self, vis):
        self.visibility = vis
        self._say()
        self._show_visibility()

    def _show_visibility(self):
        from ..common.actions import vis_picture
        from . import icons
        icons.dress(self.vis_btn, vis_picture(self.visibility), self.win.theme, words="▾",
                    glyph=vis_word(self.visibility).split(" ", 1)[0])
        tip(self.vis_btn, f"{_('web_visibility')}: {vis_word(self.visibility)}")

    def dress(self):
        """Pictures on the buttons, or words (ui.additional_icons); again after a theme."""
        from . import icons
        t = self.win.theme
        icons.dress(self.cw_btn, "warning", t, glyph="CW")
        n = f" {len(self.media)}" if self.media else ""
        icons.dress(self.attach_btn, "attach", t, words=n.strip(),
                    glyph=_("dock_attach_word") + n)
        icons.dress(self.send_btn, "send", t, words=_("dock_send"))
        self._show_visibility()

    def _cw_toggled(self, on):
        self.cw.set_visible(on)
        if on:
            self.cw.grab_focus()

    def _fill_languages(self, btn):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        codes = [None] + rules.languages(self.win.cfg)
        for code in codes:
            b = Gtk.Button(label=_("dock_lang_default") if code is None else code)
            b.add_css_class("flat")
            b.connect("clicked", lambda _b, c=code: (self._set_language(c), btn.popdown()))
            box.append(b)
        pop = Gtk.Popover()
        pop.set_child(box)
        btn.set_popover(pop)

    def _set_language(self, code):
        self.language = code
        self.lang_btn.set_label(code or _("dock_lang_default"))

    def _attach(self):
        """Pictures or a video for the next post; pressed again: what was chosen goes."""
        if self.media:
            self.media = []
            self.dress()
            return
        dlg = Gtk.FileDialog(title=_("dock_attach"))

        def done(d, res):
            try:
                files = d.open_multiple_finish(res)
            except GLib.Error:
                return
            self.media = [(files.get_item(i).get_path(), "")
                          for i in range(min(4, files.get_n_items()))]
            self.dress()
        dlg.open_multiple(self.get_root(), None, done)

    def command(self):
        return split.command(self._text(), self._prefill, self.win.cfg)

    def _count(self):
        cmd = self.command()
        self._suggest()
        if cmd is not None:  # what Enter will do, as the command line says it
            from ..common.commands import preview
            self.about.set_text(preview(self.win.view, cmd))
            self.count.set_text("")
            self.send_btn.set_sensitive(True)
            return
        self._say()
        try:
            limit = self.win.view.caps.max_characters or 500
        except Exception:  # noqa: BLE001
            limit = 500
        n = len(self._text())
        self.count.set_text(f"{n}/{limit}")
        self.send_btn.set_sensitive(0 < n <= limit and self._typed())

    def _suggest(self):
        it = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        start = it.copy()
        start.set_line_offset(0)
        sigil, word = rules.token_at_end(self.buffer.get_text(start, it, False))
        items = rules.suggestions(self.win.view, sigil, word) if sigil else []
        self._offer = (sigil, word, items) if rules.worth_offering(items, word) else None
        self.suggest.set_visible(self._offer is not None)
        if self._offer:
            self.suggest.set_text("Tab: " + "  ".join(label for _i, label in items[:6]))

    def _complete(self):
        if not getattr(self, "_offer", None):
            return False
        _sigil, word, items = self._offer
        it = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        start = it.copy()
        start.backward_chars(len(word) + 1)
        self.buffer.delete(start, it)
        self.buffer.insert_at_cursor(items[0][0] + " ")
        return True

    def put_alias(self, alias):
        text = self._text()
        if text.strip() == self._prefill.strip():
            text = ""
        self._set_text(rules.put_alias(text, alias))
        self.text.grab_focus()

    def _key(self, _ctl, keyval, _code, state):
        from .gi_setup import Gdk
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and \
                (state & Gdk.ModifierType.CONTROL_MASK or self.command() is not None):
            self.send()
            return True
        if keyval == Gdk.KEY_Tab and self._complete():
            return True
        return False

    # ---- sending -------------------------------------------------------------------------
    def send(self):
        win = self.win
        cmd = self.command()
        if cmd is not None:  # run by the command line, as typed there
            from ..common.commands import Commands
            fut, msg = Commands(win.view).run(cmd, reply_to=None, unknown_as_post=True)
            if msg:
                win.status(msg)
            if fut is not None:
                win.call(fut, lambda r: r and win.status(str(r)) if isinstance(r, str)
                         else None)
            self._set_text("")
            self._prefill = ""
            self.follow(win.tabs.get_nth_page(win.tabs.get_current_page()))
            return
        text = self._text()
        if not text.strip() or not self.send_btn.get_sensitive():
            return
        target = self.target
        warning = self.cw.get_text().strip() if self.cw_btn.get_active() else ""
        self.send_btn.set_sensitive(False)
        log.info("dock: %s", "reply to " + target.id if target else "new post")
        kw = {"language": self.language} if self.language else {}
        if self.media:
            kw["media"] = list(self.media)

        def sent(st):
            self.media = []
            self.dress()
            self._set_text("")
            self._prefill = ""
            self.cw.set_text("")
            self.cw_btn.set_active(False)
            self.target = None
            page = win.tabs.get_nth_page(win.tabs.get_current_page())
            if isinstance(page, TalkPage) and st is not None and not isinstance(st, Scheduled):
                page.add_sent(st)
            win.status(_("sent"))
            self.follow(page)

        def failed(err):
            self._count()
            win.error(err)
        win.call(win.view.post(text, self.visibility, target, warning, **kw), sent, failed)


# ---- over a lane: the author of the post under the pointer ------------------------------
class AuthorBar(Gtk.Box):
    """Over a lane (shape.faces = "qip"): whose post is under the pointer — the face,
    the name, how we stand — with Follow (one width, it never jumps), Write, Profile."""

    def __init__(self, win):
        super().__init__(spacing=8)
        self.win = win
        self.who = None
        self.add_css_class("ft-lane-header")
        self.face = Gtk.Box()
        self.append(self.face)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        self.name = Gtk.Label(xalign=0)
        self.name.add_css_class("ft-name")
        self.name.set_ellipsize(Pango.EllipsizeMode.END)
        names.append(self.name)
        self.about = Gtk.Label(xalign=0)
        self.about.add_css_class("ft-muted")
        self.about.set_ellipsize(Pango.EllipsizeMode.END)
        names.append(self.about)
        self.append(names)
        self.follow_btn = Gtk.Button(label=_("follow"))
        self.follow_btn.connect("clicked", lambda _b: self._follow())
        self._following = False
        self.append(self.follow_btn)
        self.write_btn = Gtk.Button(label="✉")
        tip(self.write_btn, _("faces_private"))
        self.write_btn.connect("clicked", lambda _b: self.who and win.write_to(self.who))
        self.append(self.write_btn)
        self.profile_btn = Gtk.Button(label="👤")
        tip(self.profile_btn, _("faces_profile"))
        self.profile_btn.connect("clicked", lambda _b: self.who and win.open_account(self.who.id))
        self.append(self.profile_btn)
        self._asked = set()
        self._steady = False
        self.dress()
        self.set_who(None)

    def dress(self):
        """Pictures on the buttons, or the glyphs (ui.additional_icons)."""
        from . import icons
        t = self.win.theme
        icons.dress(self.write_btn, "talk", t, glyph="✉")
        icons.dress(self.profile_btn, "profile", t, glyph="👤")
        self._steady = False
        self._dress_follow(self._following)

    def _dress_follow(self, on):
        from . import icons
        icons.dress(self.follow_btn, "unfollow" if on else "follow", self.win.theme,
                    words=_("unfollow") if on else _("follow"))

    def _steady_width(self):
        """Follow and Unfollow differ in length: the button keeps the longer's width."""
        if self._steady:
            return
        widths = []
        self.follow_btn.set_size_request(-1, -1)
        for on in (False, True):
            self._dress_follow(on)
            widths.append(self.follow_btn.measure(Gtk.Orientation.HORIZONTAL, -1)[1])
        self.follow_btn.set_size_request(max(widths), -1)
        self._dress_follow(self._following)
        self._steady = True

    def set_who(self, who):
        same = (who is None and self.who is None) or \
            (who is not None and self.who is not None and who.id == self.who.id)
        for b in (self.follow_btn, self.write_btn, self.profile_btn):
            b.set_visible(who is not None)
        if same and who is not None:
            return
        self.who = who
        while (c := self.face.get_first_child()) is not None:
            self.face.remove(c)
        if who is None:
            self.name.set_text("")
            self.about.set_text("")
            stand_in = nobody(self.win.theme, 36)  # a grey silhouette while nobody's there
            if stand_in is not None:
                self.face.append(stand_in)
            return
        from .card import Avatar
        self.face.append(Avatar(self.win.ctx, who, 36))
        self.name.set_text(who.name or who.username or who.handle)
        self._steady_width()
        self._show_relation()

    def _show_relation(self):
        who, view = self.who, self.win.view
        rel = view.relation_known(who.id)
        if rel is None and who.id not in self._asked:
            self._asked.add(who.id)
            self.win.call(view.relationship(who.id),
                          lambda _r, w=who: self.who is w and self._show_relation(),
                          lambda _e: None)
        bits = ["@" + who.handle]
        if rel is not None:
            if rel.followed_by:
                bits.append(_("faces_follows_me"))
            elif rel.requested:
                bits.append(_("faces_requested"))
        self.about.set_text(" · ".join(bits))
        on = bool(rel and (rel.following or rel.requested))
        self._following = on
        self._dress_follow(on)
        self.follow_btn.set_sensitive(rel is not None)

    def _follow(self):
        who = self.who
        if who is None:
            return
        self.follow_btn.set_sensitive(False)
        self.win.call(self.win.view.follow(who.id, not getattr(self, "_following", False)),
                      lambda _r: self.who is who and self._show_relation())


# ---- a private talk ---------------------------------------------------------------------
class TalkPage(Gtk.ScrolledWindow):
    """A private talk with one person, as a messenger has it: their private messages
    with me and mine with them, nobody else's (common/split.py talk_with); its tab is
    theirs and the input line writes to them, privately."""

    def __init__(self, win, account):
        super().__init__()
        self.win, self.who = win, account
        self.title = "✉ " + (account.name or account.username or account.handle)
        self.add_css_class("ft-view")
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.box = Gtk.ListBox()
        self.box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.box.add_css_class("ft-feed")
        self.box.set_margin_start(8)
        self.box.set_margin_end(8)
        self.set_child(self.box)
        self.sent = {}
        self._key = None
        self.refresh()

    def add_sent(self, post):
        self.sent[post.id] = post
        self._key = None
        self.refresh()

    def refresh(self):
        from .card import Card
        view = self.win.view
        if "direct" not in view.lane_by_name:
            return
        mine = split.talk_with(view, view.entries("direct"), self.who.handle)
        have = {e.id for _i, e in mine}
        mine += [(None, p) for pid, p in self.sent.items() if pid not in have]
        mine.sort(key=lambda x: (x[1].created is not None, x[1].created or 0))
        unread = view.unread([e for _i, e in mine])
        key = (tuple(e.id for _i, e in mine), tuple(sorted(unread)))
        if key == self._key:
            return
        self._key = key
        while (c := self.box.get_first_child()) is not None:
            self.box.remove(c)
        for _i, e in mine:
            self.box.append(Card(self.win.ctx, e.id, e, unread=e.id in unread))
        if not mine:
            self.box.append(Gtk.Label(label=_("talk_empty")))
        if unread and self.win.cfg["read"]["mark_read"] != "manual":
            view.mark_read(sorted(unread))
        GLib.idle_add(lambda: (self.get_vadjustment().set_value(
            self.get_vadjustment().get_upper()), False)[1])

    @property
    def posts(self):
        return []


def post_at(lv, y=None):
    """The post a reader of a lane looks at: under the pointer (y in the list's
    coordinates), else the lowest one wholly on screen — where a reader of a messenger's
    log looks."""
    if y is not None:
        for k in lv.order:
            card = lv.rows[k]
            top = lv._y(card)
            if top is not None and top <= y < top + card.get_height():
                return real(card.entry)
    vtop = lv.adj.get_value()
    vbot = vtop + lv.adj.get_page_size()
    best = None
    for k in lv.order:
        card = lv.rows[k]
        top = lv._y(card)
        if top is None:
            continue
        if top >= vtop and top + card.get_height() <= vbot:
            best = card
        elif top > vbot:
            break
    return real(best.entry) if best is not None else None


AGENT_FACE = 88


class AgentFace(Gtk.Box):
    """The Mail.ru Agent's column beside the posts (shape.faces = "agent"): the other
    side's face, big, in a frame, the name under it, a click — the profile. In a thread
    whom I answer, in a talk whom I talk to, over a lane the author under the pointer."""

    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.win, self.who = win, None
        self.add_css_class("ft-agent-face")
        self.set_size_request(AGENT_FACE + 16, -1)
        for m in ("top", "bottom", "start", "end"):
            getattr(self, "set_margin_" + m)(8)
        self.face = Gtk.Box(halign=Gtk.Align.CENTER)
        self.face.set_size_request(AGENT_FACE, AGENT_FACE)
        self.face.add_css_class("ft-face-frame")
        click = Gtk.GestureClick()
        click.connect("released", lambda *_a: self._profile())
        self.face.add_controller(click)
        self.append(self.face)
        self.name = Gtk.Label(xalign=0.5)
        self.name.add_css_class("ft-name")
        self.name.set_ellipsize(Pango.EllipsizeMode.END)
        self.name.set_max_width_chars(12)
        self.append(self.name)
        self.link = Gtk.Label(xalign=0.5)
        self.link.connect("activate-link", lambda _l, _u: (self._profile(), True)[1])
        self.append(self.link)

    def set_who(self, who):
        if who is not None and self.who is not None and who.id == self.who.id:
            return
        if who is None and self.who is None:
            return
        self.who = who
        while (c := self.face.get_first_child()) is not None:
            self.face.remove(c)
        if who is None:
            self.name.set_text("")
            self.link.set_text("")
            stand_in = nobody(self.win.theme, AGENT_FACE)
            if stand_in is not None:
                self.face.append(stand_in)
            return
        from .card import Avatar
        self.face.append(Avatar(self.win.ctx, who, AGENT_FACE))
        name = who.name or who.username or who.handle
        self.name.set_text(name)
        tip(self.name, name)
        self.link.set_markup(f'<a href="#">{GLib.markup_escape_text(_("faces_profile"))}</a>')

    def _profile(self):
        if self.who is not None:
            self.win.open_account(self.who.id)
