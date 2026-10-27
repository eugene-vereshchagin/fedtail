"""The main GTK window: lanes on the left with their unread counts, the lane or thread
on the right (a tab each, the lanes' own tab first), a status line at the bottom.

Stage 1 of docs/en/dev/gtk.md. What a card needs from the window goes through `Ctx` (like
qt/window.py ViewContext), so cards never import the window.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ...core import lanes as lanes_mod
from ...i18n import _
from ...model import real
from ...version import NAME
from .. import richtext
from ..common import results, sidebar
from ..common.links import Links
from . import login
from .activity import ActivityLane, RequestsLane
from .card import Card
from .gi_setup import Gdk, Gio, GLib, Gtk, Pango, forget, gtk_version, tip
from .lane import LaneView, y_in

log = logging.getLogger(__name__)

BADGE_KIND = {"replies": "hot", "to_me": "hot",
              "bots": "quiet", "activity": "quiet"}  # as qt/window.py
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

    def show_images(self, media, index=0):
        from . import viewer
        return viewer.show(self.win, media, index)

    def save_media(self, m):
        self.win.save_media(m)


class LaneRow(Gtk.ListBoxRow):
    def __init__(self, name, title, theme=None, icon=None):
        super().__init__()
        self.name = name
        box = Gtk.Box(spacing=6)
        if theme is not None:  # the lane's picture, as the theme has it
            from .. import iconpack
            from . import icons
            pic = icons.image(iconpack.lane_picture(name, icon), theme,
                              int(theme.shape.get("icon_size", 18) or 18)) \
                if icons.pictures(theme) else None
            if pic is not None:
                box.append(pic)
            elif icons.pictures(theme):
                spacer = Gtk.Box()
                spacer.set_size_request(int(theme.shape.get("icon_size", 18) or 18), -1)
                box.append(spacer)
        lab = Gtk.Label(label=title, xalign=0)
        lab.set_hexpand(True)
        lab.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(lab)
        what = _("tip_" + name) if not name.startswith("list:") else ""
        if what and what != "tip_" + name:  # what the lane is, as Qt's sidebar says
            tip(self, what)
        self.badge = Gtk.Label(valign=Gtk.Align.CENTER)  # a pill, not a row-high oval
        self.badge.add_css_class("ft-badge")
        if name in BADGE_KIND:
            self.badge.add_css_class(BADGE_KIND[name])
        self.badge.set_visible(False)
        box.append(self.badge)
        self.set_child(box)

    def set_count(self, n, fresh=0):
        """The unread count; fresh: of them, what the last update brought — a smaller
        "+56" in the pill, the words on hover."""
        self.badge.set_visible(n > 0)
        text = sidebar.badge_text(n)
        if fresh and n:
            self.badge.set_markup(f"{text} <small>+{fresh}</small>")
        else:
            self.badge.set_text(text)
        self.badge.set_tooltip_text(sidebar.fresh_words(fresh) if fresh and n else None)


class SectionRow(Gtk.ListBoxRow):
    """A group's title in the sidebar: not a lane; a click folds the group away, and
    folded it shows how many are unread in it."""

    def __init__(self, group, text, names, plus=None):
        super().__init__(selectable=False, activatable=True)
        self.group, self.names = group, list(names)
        box = Gtk.Box(spacing=6)
        box.set_margin_top(8)
        self.mark = Gtk.Label(label="▾")
        self.mark.add_css_class("ft-account")
        box.append(self.mark)
        lab = Gtk.Label(label=text, xalign=0)
        lab.add_css_class("ft-account")
        lab.add_css_class("caption-heading")
        lab.set_hexpand(True)
        box.append(lab)
        self.badge = Gtk.Label(valign=Gtk.Align.CENTER)  # a pill, not a row-high oval
        self.badge.add_css_class("ft-badge")
        self.badge.set_visible(False)
        box.append(self.badge)
        if plus is not None:  # Lists: + makes a new one
            b = Gtk.Button(label="+")
            b.add_css_class("flat")
            tip(b, _("list_new"))
            b.connect("clicked", lambda _b: plus())
            box.append(b)
        self.set_child(box)

    def show_fold(self, folded, unread):
        self.mark.set_text("▸" if folded else "▾")
        self.badge.set_visible(folded and unread > 0)
        self.badge.set_text(sidebar.badge_text(unread))


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app, core, view, bridge, theme):
        super().__init__(application=app, title="fedtail")
        self.core, self.view, self.bridge, self.theme = core, view, bridge, theme
        self.app = app
        # ui.layout = "split": the lanes in a roster window of their own (split.py);
        # this window is the messages window — no sidebar, a tab per lane or talk, the
        # input line at the bottom
        self.split_mode = core.cfg["ui"].get("layout") in ("split", "qip")
        self.roster = self.dock = self.author_bar = None
        self.agent_face = self.tab_rows = None
        self.lane_tabs = {}      # split: lane name -> its page (the LaneView)
        self.cfg = core.cfg
        self.add_css_class("fedtail")
        from .images import Images
        self.images = Images(view, bridge)
        self.ctx = Ctx(self.cfg, view, theme, bridge, self, images=self.images)
        self.links = Links(view, self)  # what fedtail: links do (common/links.py)
        self.cmdline = None
        from .notify import Notifier
        self.notifier = Notifier(self, app)
        from ..common.sound import Sounds
        self.sounds = Sounds(self.cfg, theme.id, bell=self._beep)  # common/sound.py
        self.lane_views = {}     # name -> LaneView
        self.lane_rows = {}      # name -> LaneRow
        self.sections = {}       # group -> SectionRow
        self.threads = {}        # root post id -> page widget
        self.accounts = {}       # account id -> page widget
        self.quitting = False
        bridge.on_event = self.on_event
        bridge.on_error = lambda text: self.status(_("error", err=text))
        self.set_default_size(*self._saved_size())

        self.extra_tabs = {}     # key -> page: people, trends, search, a tag
        self.columns = None      # lanes side by side (❯), or None
        self.hints_on = False    # ≡ → What's this?
        if self.view.get_state("full_width"):  # ↔ as left last time
            self._column_width = self.cfg["ui"]["max_width"] or 760
            self.cfg["ui"]["max_width"] = 0
        from .menu import MainMenu
        self.menu = MainMenu(self)
        if own_titlebar(self.cfg):  # GNOME and kin: a header bar, the title in it
            self.set_titlebar(Gtk.HeaderBar())

        # the sidebar, as Qt's: who I am with ≡ ↔ ❯, Write, the search, the lanes,
        # the version at the foot
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        side.add_css_class("ft-sidebar")
        side.set_size_request(240, -1)  # the header's own needs widen it (width_chars)
        side.append(self._me_head())
        write = Gtk.Button(label=self.theme.word("compose", _("write")))  # as in Qt
        write.add_css_class("ft-primary")
        write.add_css_class("suggested-action")
        write.add_css_class("ft-write")
        write.connect("clicked", lambda _b: self.compose())
        for m in ("start", "end"):
            getattr(write, "set_margin_" + m)(8)
        side.append(write)
        self.search = Gtk.SearchEntry(placeholder_text=_("search_side"))
        self.search.connect("activate", lambda e: self.open_search(e.get_text()))
        tip(self.search, _("search_side_tip"))
        for m in ("start", "end"):
            getattr(self.search, "set_margin_" + m)(8)
        side.append(self.search)
        self.sidebar = Gtk.ListBox()
        self.sidebar.add_css_class("ft-sidebar")
        self.sidebar.add_css_class("navigation-sidebar")
        self.sidebar.connect("row-selected", self._lane_selected)
        self.sidebar.connect("row-activated", self._row_activated)
        side_scroll = Gtk.ScrolledWindow(vexpand=True)
        side_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        side_scroll.set_child(self.sidebar)
        side.append(side_scroll)
        self.footer = Gtk.Label(xalign=0, label=self._footer_text())
        self.footer.add_css_class("ft-muted")
        self.footer.add_css_class("caption")
        # a long build (a dev one, "dirty") ends in "…", never widens the sidebar — a
        # wrapped one told GTK two least heights ("Expect overlapping widgets")
        self.footer.set_ellipsize(Pango.EllipsizeMode.END)
        for m in ("start", "end", "bottom"):
            getattr(self.footer, "set_margin_" + m)(8)
        foot_click = Gtk.GestureClick()
        foot_click.connect("released", lambda *_a: self.about())
        self.footer.add_controller(foot_click)
        tip(self.footer, _("about"))
        side.append(self.footer)

        self.stack = Gtk.Stack()
        self.curtain = self._build_curtain()  # every lane closed (Esc), as Qt's
        self.stack.add_named(self.curtain, "__curtain__")
        self.tabs = Gtk.Notebook()
        self.tabs.set_scrollable(True)
        self.tabs.set_show_tabs(False)
        self.tabs.append_page(self.stack, Gtk.Label(label=_("gtk_lanes")))
        self.tabs.connect("switch-page", lambda *_a: GLib.idle_add(self._tab_switched))
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_start_child(side)
        # the lanes and, under them, the command line: beside the sidebar, as in Qt
        self.right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        from .announce import AnnounceBar
        from .find import FindBar
        self.announce_bar = AnnounceBar(self)  # the server's announcements, as in Qt
        self.right.append(self.announce_bar)
        self.find_bar = FindBar(self)  # Ctrl+F, over the lanes
        self.right.append(self.find_bar)
        self.tabs.set_vexpand(True)
        self.right.append(self.tabs)
        paned.set_end_child(self.right)
        if self.split_mode:
            self.right.remove(self.tabs)
            paned.set_end_child(None)
            paned.set_start_child(None)
            paned = self._split_area(side)
        bar = self.read_write if self.split_mode else paned
        bar.set_resize_start_child(False)
        bar.set_shrink_start_child(False)
        bar.set_position(272)

        # the status bar: whose this window is at the left, what happens, and in the
        # debugging mode how the window is drawn at the right
        self.status_line = Gtk.Label(xalign=0, hexpand=True)
        self.status_line.add_css_class("ft-status")
        self.status_line.set_ellipsize(Pango.EllipsizeMode.END)
        self.profile_label = Gtk.Label(xalign=0)
        self.profile_label.add_css_class("ft-muted")
        # a narrow window: the bar's words give way ("…") instead of holding it wide
        # (the sync mark beside them took the window past 600 px)
        self.profile_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.profile_label.set_width_chars(8)
        tip(self.profile_label, _("footer_profile_tip"))
        bar = Gtk.Box(spacing=12)
        bar.add_css_class("ft-statusbar")
        for m in ("start", "end"):
            getattr(bar, "set_margin_" + m)(6)
        bar.append(self.profile_label)
        bar.append(self.status_line)
        # sync with my other devices (or that there is none: off without sync.url)
        # slow mode on: when the next batch comes ("slow · next at 14:30")
        self.slow_label = Gtk.Label(xalign=1)
        self.slow_label.add_css_class("ft-muted")
        self.slow_label.set_visible(False)
        bar.append(self.slow_label)
        GLib.timeout_add_seconds(30, lambda: (self._slow_text(), True)[1])
        self.sync_label = Gtk.Label(xalign=1)
        self.sync_label.add_css_class("ft-muted")
        bar.append(self.sync_label)
        corner = self._debug_corner()
        self.corner_label = None
        if corner:
            lab = Gtk.Label(label=corner)
            lab.add_css_class("ft-muted")
            lab.set_ellipsize(Pango.EllipsizeMode.START)
            tip(lab, _("debug_corner_tip"))
            bar.append(lab)
            self.corner_label = lab
        self._profile_text()
        self._sync_text()
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.add_css_class("fedtail-main")
        # the editor comes over the window's middle (as Qt's), not as a window of its own
        self.overlay = Gtk.Overlay()
        self.overlay.set_child(paned)
        self.overlay.set_vexpand(True)
        self.composer = None
        self.viewer = None
        self.player = None  # a video over the window (player.py)
        self.help_panel = None
        outer.append(self.overlay)
        if self.cfg["ui"]["command_line"]:
            from .cmdline import CommandLine
            self.cmdline = CommandLine(self)
            (outer if self.split_mode else self.right).append(self.cmdline)
            if self.split_mode and self.cfg["ui"].get("dock_commands", True):
                self.cmdline.set_visible(False)  # the input line takes the commands
        outer.append(bar)
        self.set_child(outer)

        self._shortcuts()
        self.connect("notify::is-active", lambda *_a: self._activated())
        self.connect("close-request", self._close_request)
        self.connect("destroy", self._stop)

    # ---- the split layout ---------------------------------------------------------------
    def _split_area(self, side):
        """The messages window: tabs above (a lane, a thread, a profile, a talk each),
        over a lane whose post is under the pointer, the input line below — a bar
        between them drags (as in QIP). The sidebar is the roster's, in its own window."""
        from . import split
        side.set_visible(False)  # (kept: its rows count what the tabs say)
        self.stack.set_visible(False)  # a hidden page: the notebook shows no tab for it
        self.dock = split.InputDock(self)
        reading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        mode = split.split.faces_mode(self.cfg, self.theme.shape)
        self.agent_face = None
        if mode == "qip":  # over a lane: the author under the pointer, in one line
            self.author_bar = split.AuthorBar(self)
            reading.append(self.author_bar)
        self.tabs.set_vexpand(True)
        if mode == "agent":  # the Agent: their face in a column beside the posts
            beside = Gtk.Box(vexpand=True)
            self.tabs.set_hexpand(True)
            beside.append(self.tabs)
            self.agent_face = split.AgentFace(self)
            beside.append(self.agent_face)
            reading.append(beside)
        else:
            reading.append(self.tabs)
        rw = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        rw.set_start_child(reading)
        rw.set_end_child(self.dock)
        rw.set_resize_end_child(False)
        rw.set_shrink_end_child(False)
        rw.set_resize_start_child(True)
        self.read_write = rw

        def low(paned, _p):  # the input line as small as it goes, the posts the rest
            if not getattr(paned, "placed", False) and paned.get_property("max-position") > 0:
                paned.placed = True
                paned.set_position(paned.get_property("max-position"))
        rw.connect("notify::max-position", low)
        self.roster = split.RosterWindow(self, self.app)
        self._pointer_y = None
        # the tabs in as many rows as they take, over everything (as in Qt)
        from .tabrows import TabRows
        self.tabs.set_show_tabs(False)
        self.tab_rows = TabRows(self.tabs, hidden=(self.stack,),
                                wrap=self.theme.shape.get("tab_rows", "wrap") == "wrap")
        # the last tab closed: the messages window goes, the roster stays (as Qt's)
        self.tabs.connect("page-removed", lambda *_a: GLib.idle_add(self._maybe_go))
        area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        area.append(self.tab_rows)
        rw.set_vexpand(True)
        area.append(rw)
        return area

    def select_lane(self, name):
        """A lane in front: its row in the sidebar (and so its tab, in the split layout)."""
        row = self.lane_rows.get(name)
        if row is None:
            return
        if self.sidebar.get_selected_row() is row:
            self._lane_selected(self.sidebar, row)
        else:
            self.sidebar.select_row(row)

    def _lane_tab(self, name):
        """split: the lane in a tab of its own (made the first time; ✕ puts it away, its
        place and filters kept for when it opens again)."""
        lv = self._lane_view(name)
        if name not in self.lane_tabs:
            if lv.get_parent() is self.stack:
                self.stack.remove(lv)
            lv.set_visible(True)
            label = Gtk.Box(spacing=4)
            text = Gtk.Label(label=self.lane_title(name))
            text.set_ellipsize(Pango.EllipsizeMode.END)
            text.set_width_chars(min(len(self.lane_title(name)) + 4, 20))
            text.set_max_width_chars(28)
            label.append(text)
            label.text = text
            close = Gtk.Button(icon_name="window-close-symbolic")
            close.add_css_class("flat")
            tip(close, _("close_tab"))
            close.connect("clicked", lambda _b, n=name: self.close_lane_tab(n))
            label.append(close)
            self.tabs.append_page(lv, label)
            self.tabs.set_tab_reorderable(lv, True)
            self.lane_tabs[name] = lv
            self._watch_pointer(lv)
        self.tabs.set_current_page(self.tabs.page_num(lv))
        self.update_badges()
        return lv

    def _maybe_go(self):
        if self.roster is not None and not self.quitting and self.get_visible() and \
                not self.tab_rows.pages():
            self.set_visible(False)
        return GLib.SOURCE_REMOVE

    def close_lane_tab(self, name):
        lv = self.lane_tabs.pop(name, None)
        if lv is None:
            return
        self.tabs.remove_page(self.tabs.page_num(lv))
        self.stack.add_named(lv, name)
        if hasattr(lv, "hidden"):
            lv.hidden()

    def open_talk(self, account):
        """Our private talk with someone, a tab of its own (the split layout)."""
        from . import split
        key = "talk:" + account.id
        page = self.extra_tabs.get(key)
        if page is None:
            page = split.TalkPage(self, account)
            tab = Gtk.Box(spacing=4)
            tab.append(Gtk.Label(label=page.title))
            close = Gtk.Button(icon_name="window-close-symbolic")
            close.add_css_class("flat")
            tip(close, _("close_tab"))
            close.connect("clicked", lambda _b: self.close_extra(key))
            tab.append(close)
            self.tabs.append_page(page, tab)
            self.extra_tabs[key] = page
        self.tabs.set_current_page(self.tabs.page_num(page))
        return page

    def write_to(self, account):
        """A private message to someone: the input line and a talk in the split layout,
        else the editor with "@them ", direct."""
        if self.dock is not None:
            self.present()
            self.open_talk(account)
            self.dock.write_to(account)
            return
        panel = self.compose(text="@" + account.handle + " ")
        if panel is not None:
            panel._set_vis("direct")

    def _watch_pointer(self, lv):
        """The author bar (or the Agent's face) follows the post under the pointer, or,
        scrolled by keys or the wheel without it, the lowest one wholly on screen."""
        if (self.author_bar is None and self.agent_face is None) or \
                not hasattr(lv, "list"):
            return
        motion = Gtk.EventControllerMotion()

        def moved(_c, _x, y):
            self._pointer_y = y
            self._follow_author(lv)
        motion.connect("motion", moved)
        motion.connect("leave", lambda *_a: setattr(self, "_pointer_y", None))
        lv.list.add_controller(motion)
        lv.adj.connect("value-changed", lambda _a: self._follow_author(lv))

    def _follow_author(self, lv=None):
        """Whose face and name the bar over a lane (QIP) or the column beside it (the
        Agent) shows: the author under the pointer; in a talk whom I talk to; in a
        thread whom I answer."""
        from . import split
        if self.author_bar is None and self.agent_face is None:
            return
        page = self.tabs.get_nth_page(self.tabs.get_current_page())
        if lv is not None and lv is not page:
            return
        me = self.view.me
        target = self.dock.target if self.dock else None
        if getattr(page, "who", None) is not None:
            who = page.who
        elif hasattr(page, "rows"):
            who = split.split.other_side(split.post_at(page, self._pointer_y), me, target)
        else:
            who = split.split.other_side(None, me, target)
        if self.author_bar is not None:
            self.author_bar.set_who(who if hasattr(page, "rows") else None)
        if self.agent_face is not None:
            self.agent_face.set_who(who)

    def _shortcuts(self):
        """The same keys as the Qt window where it has the thing: Ctrl+L the command line,
        Ctrl+N write, Ctrl+F find, F5 refresh, Ctrl+W a thread's tab, Ctrl+Q quit. (Never
        F1: it sits next to Esc.)"""
        ctl = Gtk.ShortcutController()
        ctl.set_scope(Gtk.ShortcutScope.GLOBAL)

        def add(trigger, fn):
            ctl.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string(trigger),
                                              Gtk.CallbackAction.new(lambda *_a: (fn(), True)[1])))
        add("<Control>l", lambda: self.cmdline is not None and self.cmdline.entry.grab_focus())
        add("<Control>n", self.compose)
        add("<Control>f", self.find_bar.open)
        add("<Control>k", self.search.grab_focus)  # the sidebar's search, as in Qt
        add("F5", self.view.refresh_by_hand)
        add("<Control>q", self.close)
        add("<Control>w", self._close_current_tab)
        self.add_controller(ctl)
        keys = Gtk.EventControllerKey()  # Esc and Enter, as Qt's (ui.esc)
        keys.connect("key-pressed", self._key)
        self.add_controller(keys)
        # pictures dropped anywhere on the window start a new post with them (as Qt's)
        from . import dropin
        dropin.add_drop(self, lambda: self.view.paths.data_dir, self._dropped)

    def _dropped(self, paths):
        c = self.composer
        if c is None or c.closed or c.edit:
            c = self.compose_panel()
        if c is not None:
            c.add_paths(paths)

    def _key(self, _ctl, keyval, _code, state):
        """Esc closes what's on top; the last one closes every lane behind a curtain
        (ui.esc = "curtain"; "tray": the window goes; "off": nothing). Enter on the
        curtain opens the last lane."""
        mods = state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK |
                        Gdk.ModifierType.SHIFT_MASK)
        if Gdk.KEY_1 <= keyval <= Gdk.KEY_9 and mods in self._number_mods():
            names = list(self.lane_rows)  # Alt+N (ui.number_keys): the N-th lane
            n = keyval - Gdk.KEY_1
            if n < len(names):
                self.select_lane(names[n])
            return True
        if mods:
            return False
        mode = self.cfg["ui"].get("esc", "curtain")
        # what's over the window goes first, wherever the keyboard's focus is (the card
        # clicked to open a picture kept it, and Esc closed the lane under the viewer)
        if keyval == Gdk.KEY_Escape:
            for over in (getattr(self, "viewer", None), getattr(self, "player", None)):
                if over is not None and not getattr(over, "closed", False):
                    over.close()
                    return True
        if keyval == Gdk.KEY_Escape and mode != "off":
            if self.find_bar.get_visible():
                self.find_bar.close_bar()
            elif self.tabs.get_current_page() > 0:
                self._close_current_tab()
            elif mode == "tray":
                self.hide_away()
            elif not self.curtain_shown():
                self.close_all()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and self.curtain_shown() and \
                not isinstance(self.get_focus(), (Gtk.Text, Gtk.TextView)):
            name = self.view.get_state("lane") or self._start_lane()
            if name in self.lane_rows:
                self.sidebar.select_row(self.lane_rows[name])
                return True
        return False

    def _number_mods(self):
        alt, ctrl = Gdk.ModifierType.ALT_MASK, Gdk.ModifierType.CONTROL_MASK
        return {"alt": (alt,), "ctrl": (ctrl,), "both": (alt, ctrl)}.get(
            self.cfg["ui"].get("number_keys", "alt"), (alt,))

    # ---- the curtain: every lane closed ------------------------------------------------
    def _build_curtain(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                      valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        box.add_css_class("ft-view")
        from importlib import resources
        try:
            pic = resources.files("fedtail").joinpath("data/icons/fedtail.png")
            self._still = Gdk.Texture.new_from_filename(str(pic))
            icon = Gtk.Image.new_from_paintable(self._still)
            icon.set_pixel_size(96)
            box.append(icon)
            self.curtain_icon = icon
        except (GLib.Error, OSError):
            pass
        title = Gtk.Label(label=_("curtain_title"))
        title.add_css_class("ft-lane-title")
        title.add_css_class("title-2")
        box.append(title)
        self.curtain_info = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER,
                                      max_width_chars=60)
        self.curtain_info.add_css_class("ft-muted")
        box.append(self.curtain_info)
        hint = Gtk.Label(label=_("curtain_hint"))
        hint.add_css_class("ft-muted")
        box.append(hint)
        return box

    def curtain_shown(self):
        return self.stack.get_visible_child() is getattr(self, "curtain", None)

    def _swing_frames(self):
        """The swinging opossum's frames as textures with their times (ms), read once
        from the sheet tools/swing_frames.py lays out (GTK 4 draws no GIF itself);
        [] where it can't be read — the opossum then just stands."""
        frames = getattr(self, "_swing", None)
        if frames is not None:
            return frames
        frames = self._swing = []
        try:
            import json
            from importlib import resources

            from gi.repository import GdkPixbuf
            icons = resources.files("fedtail").joinpath("data/icons")
            facts = json.loads(icons.joinpath("fedtail-swing.json").read_text("utf-8"))
            sheet = GdkPixbuf.Pixbuf.new_from_file(str(icons.joinpath("fedtail-swing.png")))
            side, cols = int(facts["side"]), int(facts["cols"])
            for i, ms in enumerate(facts["ms"]):
                part = sheet.new_subpixbuf((i % cols) * side, (i // cols) * side, side, side)
                frames.append((Gdk.Texture.new_for_pixbuf(part), max(20, int(ms))))
        except Exception as e:  # noqa: BLE001 — no GdkPixbuf, a file missing: it stands
            log.info("curtain: no swinging opossum (%s)", e)
            frames.clear()
        return frames

    def _curtain_swing(self):
        """The curtain's opossum swings while the lanes are being updated (a poll round
        on), and stands still otherwise — as Qt's."""
        icon = getattr(self, "curtain_icon", None)
        if icon is None:
            return
        try:
            busy = bool((self.view.poll_state() or {}).get("busy"))
        except Exception:  # noqa: BLE001 — a core that doesn't say
            busy = False
        busy = busy and self.curtain_shown() and self.cfg["ui"].get("app_icon") != "bubble"
        if busy:
            self._swing_ending = False  # busy again before the swing ran out: it goes on
        if busy and not getattr(self, "_swing_on", False):
            frames = self._swing_frames()
            if not frames:
                return
            self._swing_on, self._swing_at = True, 0

            def step():
                if not getattr(self, "_swing_on", False):
                    return False
                if getattr(self, "_swing_ending", False) and \
                        self._swing_at % len(frames) == 0:
                    # the round is over and the swing ran to its end (where the sticker
                    # stands still): it stops here, not mid-swing
                    self._swing_on = self._swing_ending = False
                    icon.set_from_paintable(self._still)
                    return False
                tex, ms = frames[self._swing_at % len(frames)]
                icon.set_from_paintable(tex)
                self._swing_at += 1
                GLib.timeout_add(ms, step)
                return False
            step()
        elif not busy and getattr(self, "_swing_on", False):
            if self.curtain_shown():
                self._swing_ending = True  # the swing runs out first (step above)
            else:
                self._swing_on = self._swing_ending = False
                icon.set_from_paintable(self._still)

    def close_all(self):
        """Esc: no lane, thread or profile on screen; nothing gets marked read, so
        whatever comes meanwhile waits, counted on the left."""
        self.find_bar.close_bar()
        current = self.stack.get_visible_child()
        if current is not None and hasattr(current, "hidden"):
            current.hidden()
        self.stack.set_visible_child(self.curtain)
        self.tabs.set_current_page(0)
        self.sidebar.unselect_all()
        self.view.set_active_lane(None)
        self.view.set_active_lanes([])
        self._curtain_text()
        self._curtain_swing()
        log.info("all lanes closed (Esc)")

    def _curtain_text(self, numbers=None):
        numbers = numbers if numbers is not None else sidebar.counts(self.view,
                                                                    self.lane_rows)
        waiting = [(self.lane_title(n), numbers[n]) for n in self.lane_rows if numbers.get(n)]
        self.curtain_info.set_text(
            _("curtain_waiting", items=", ".join(f"{t} — {c}" for t, c in waiting))
            if waiting else _("curtain_empty"))

    # ---- the head of the sidebar ---------------------------------------------------------
    def _me_head(self):
        """My face and name (a click: my profile; a right click: the other accounts),
        and ≡ the menu, ↔ posts across the width, ❯ lanes side by side."""
        from .card import Avatar
        head = Gtk.Box(spacing=8)
        for m in ("start", "end", "top"):
            getattr(head, "set_margin_" + m)(8)
        self.me_face = Gtk.Box()
        head.append(self.me_face)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        self.me_name = Gtk.Label(xalign=0)
        self.me_name.add_css_class("ft-name")
        self.me_name.set_ellipsize(Pango.EllipsizeMode.END)
        self.who = Gtk.Label(xalign=0)
        self.who.add_css_class("ft-muted")
        self.who.set_ellipsize(Pango.EllipsizeMode.END)
        for lab in (self.me_name, self.who):  # a name never cut down to "М…": the
            lab.set_width_chars(7)            # sidebar grows instead (a wider ≡ ▾)
        names.append(self.me_name)
        names.append(self.who)
        head.append(names)
        for w in (self.me_face, names):
            left = Gtk.GestureClick(button=1)
            left.connect("released", lambda *_a: self.my_profile())
            w.add_controller(left)
            right = Gtk.GestureClick(button=3)
            right.connect("pressed", lambda _g, _n, x, y, w=w: self._accounts_popup(w, x, y))
            w.add_controller(right)
            tip(w, _("my_profile") + "\n" + _("accounts_tip"))
        from .menu import button
        self.menu_btn = button(self, self.menu)
        head.append(self.menu_btn)
        self.wide_btn = Gtk.ToggleButton(label="↔")
        self.wide_btn.set_active(not self.cfg["ui"]["max_width"])
        tip(self.wide_btn, _("full_width_tip"))
        self.wide_btn.connect("toggled", lambda b: self.set_full_width(b.get_active()))
        head.append(self.wide_btn)
        self.columns_btn = Gtk.ToggleButton(label="❯")
        tip(self.columns_btn, _("columns_tip"))
        self.columns_btn.connect("toggled", lambda b: self.set_columns(b.get_active()))
        head.append(self.columns_btn)
        self._dress_head()
        for b in head:
            if isinstance(b, Gtk.Button):
                b.add_css_class("flat")
                b.set_valign(Gtk.Align.CENTER)
        self._Avatar = Avatar
        return head

    def _show_me(self):
        me = self.view.me
        if me is None:
            return
        # the theme's words, as in Qt (terminal: "mira@fedtail:~$")
        words = getattr(self.theme, "words", {}) or {}
        fields = dict(display_name=me.name or me.username, username=me.username,
                      acct=me.handle)
        try:
            title = words.get("account_title", "{display_name}").format(**fields)
            sub = words.get("account_subtitle", "@{acct}").format(**fields)
        except (KeyError, IndexError, ValueError):
            title, sub = me.name or me.username or me.handle, "@" + me.handle
        self.me_name.set_text(title)
        self.who.set_text(sub)
        while (c := self.me_face.get_first_child()) is not None:
            self.me_face.remove(c)
        if self.theme.shape.get("sidebar_avatar", True):  # terminal: none, as in Qt
            self.me_face.append(self._Avatar(self.ctx, me, 40))
        self._profile_text()
        self.set_title(f"{NAME} — @{me.handle}")

    def _accounts_popup(self, w, x, y):
        pop = Gtk.PopoverMenu.new_from_model(self.menu.accounts_model())
        pop.set_parent(w)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        pop.set_pointing_to(rect)
        pop.connect("closed", lambda p: GLib.idle_add(p.unparent))
        pop.popup()

    def _footer_text(self):
        """Version and build, then who made it — as at the foot of Qt's sidebar."""
        from ... import version
        info = version.info()
        build = info["version"] + (f" · {info['date']}" if info["date"] else "")
        return f"fedtail {build}\n" + _("made_by").replace("<br>", "\n")

    def _slow_text(self):
        """How fresh the lanes are and slow mode, by the sync line: "⟳ updating the
        lanes…", "updated at 14:32 · slow · next at 14:45"."""
        label = getattr(self, "slow_label", None)
        if label is None:
            return
        text = sidebar.status_words(self.view)
        label.set_text(text)
        label.set_visible(bool(text))

    def _sync_text(self):
        """"⇅ 21:40" / "⇅ off" / "⇅ !" in the status bar, the details as its tooltip."""
        from ..common import syncline
        text, tip_text = syncline.bar(self.view)
        self.sync_label.set_text(text)
        self.sync_label.set_tooltip_text(tip_text)

    def _profile_text(self):
        """"default: @me@server ★" at the left of the status bar."""
        from ...core import paths
        me = self.view.paths.profile
        who = ""
        if self.view.me is not None:
            host = (self.view.auth or {}).get("server", "").split("://")[-1].rstrip("/")
            acct = self.view.me.handle
            who = "@" + acct + (f"@{host}" if host and "@" not in acct else "")
        text = f"{me}: {who}" if who else me
        self.profile_label.set_text(text + (" ★" if me == paths.main_profile() else ""))

    def _dress_head(self):
        """≡ ↔ ❯ with the theme's pictures (or the desktop's, or the glyphs)."""
        from . import icons
        t = self.theme
        # as Qt's: a third bigger than the lanes' pictures, 26 px at most
        px = min(26, round(int(t.shape.get("icon_size", 18) or 18) * 4 / 3))
        icons.dress(self.menu_btn, "menu", t, glyph="≡", size=px)
        icons.dress(self.wide_btn, "wide", t, glyph="↔", size=px)
        icons.dress(self.columns_btn, "columns", t, glyph="❯", size=px)

    def _debug_corner(self):
        """In the debugging mode: how the window is drawn — theme, GTK, libadwaita,
        the display's kind, the scale, the build."""

        from ... import diag
        from . import gi_setup
        if not diag.is_on():
            return ""
        from ..common import corner
        from . import scale
        display = Gdk.Display.get_default()
        kind = type(display).__name__.replace("Gdk", "").replace("Display", "") \
            if display is not None else ""
        # the family the theme's CSS gives (the desktop's when none), the desktop's size —
        # written as Qt writes it: "Open Sans 10pt"
        settings = Gtk.Settings.get_default()
        desk = (settings.get_property("gtk-font-name") or "") if settings else ""
        fam, _sp, size = desk.rpartition(" ")
        if not size.replace(".", "").isdigit():
            fam, size = desk, ""
        font = " ".join(x for x in (getattr(self.theme, "font_family", "") or fam,
                                    f"{size}pt" if size else "") if x)
        return corner.text(self.theme.id, "GTK " + ".".join(str(x) for x in gtk_version()),
                           "libadwaita" if gi_setup.Adw is not None else "GTK", font, kind,
                           (self.get_scale_factor() or 1) * scale.gtk_dpi() / scale.BASE)

    # ---- ≡ the menu: what its items do ---------------------------------------------------
    def read_current_lane(self):
        lv = self.lane_views.get(self._current_lane())
        if lv is not None and hasattr(lv, "mark_all_read"):
            lv.mark_all_read()

    def my_profile(self):
        me = self.view.me
        if me is not None:
            self.open_account(me.id)

    def open_path(self, path):
        from ...sysenv import open_external
        uri = Gio.File.new_for_path(str(path)).get_uri()
        if open_external(uri):
            return
        try:
            Gio.AppInfo.launch_default_for_uri(uri, None)
        except GLib.Error as e:
            self.status(_("error", err=e.message))

    def themes_dir(self):
        return _themes_dir()

    def open_logs(self):
        from ... import diag
        self.open_path(diag.logs_dir(self.view.paths))

    def silence(self, tab="filters"):
        from . import dialogs
        return dialogs.silence(self, tab)

    def show_filtered(self):
        from . import dialogs
        return dialogs.filtered(self)

    def show_scheduled(self):
        if self.cfg["post"].get("scheduled_to_draft"):  # the place, with "To the editor"
            return self.open_place("scheduled")
        from . import dialogs
        return dialogs.scheduled(self)

    def show_server_info(self):
        from . import dialogs
        return dialogs.server_info(self)

    def federation_status(self):
        from . import dialogs
        return dialogs.federation(self)

    def open_help(self, page="index", anchor=""):
        """≡ → Help: a panel over the lanes, as the editor (and as in Qt)."""
        from . import help as helppanel
        return helppanel.open_help(self, page, anchor)

    def open_suggestions(self):
        from . import people
        return people.open_people(self, "suggestions", _("suggestions_title"),
                                  self.view.suggestions,
                                  dismiss=lambda a: self.call(self.view.dismiss_suggestion(a)))

    def open_directory(self, local):
        from . import people
        key = "directory_local" if local else "directory_title"
        return people.open_people(self, key, _(key),
                                  lambda cur: self.view.directory(cur, local))

    def open_trends(self):
        from . import people
        return people.open_trends(self)

    def open_search(self, query):
        from ...core import taggroups
        from . import people
        spec = taggroups.parse((query or "").strip())
        if spec:  # several tags: a lane of them, not a search (as Qt)
            return people.open_tag_group(self, spec)
        return people.open_search(self, query)

    def open_tag(self, tag):
        from . import people
        return people.open_tag(self, tag)

    def close_extra(self, key):
        page = self.extra_tabs.pop(key, None)
        if page is not None:
            self._drop_tab(page)
        self._tab_switched()

    def new_list(self, add=None):
        """A new list (add: someone to put in it at once)."""
        from . import dialogs
        dialogs.ask_text(self, _("list_new").rstrip("…"), _("list_name_q"),
                         lambda title: self.call(self.view.create_list(title, add=add),
                                                 lambda x: self.status(
                                                     _("list_created", title=x.title))))

    def lane_menu(self, row):
        from . import lists
        return lists.lane_menu(self, row)

    def open_place(self, name, arg="", tab=""):
        """A place of common/places.py in a window of its own (gtk/place.py): collections,
        and any place the windows have no widget of their own for."""
        from .place import PlaceWindow
        return PlaceWindow(self, name, arg, tab)

    def _place(self, name, arg="", tab=""):  # common/profile.py's word for it
        return self.open_place(name, arg, tab)

    def open_lists(self, account):
        """"Add to list" from common/profile.py: the popover by what has the focus (the
        profile's own button opens it by itself, at the button)."""
        anchor = self.get_focus() or getattr(self, "status_line", None)
        if anchor is not None:
            self.lists_popover(account, anchor)  # it pops up by itself

    def lists_popover(self, account, anchor):
        """"Add to list" for someone: the lists, ticked where they are (gtk/lists.py)."""
        from . import lists
        return lists.popover(self, account, anchor)

    def test_notification(self):
        self.status(_("debug_notify_sent", backend=self.notifier.test()))

    def debug_stacks(self):
        from ... import diag
        diag.dump_stacks("asked from the menu")
        diag.log_stats()
        self.status(_("debug_stacks_done"))

    def debug_census(self):
        from ... import diag
        s = diag.check_now(int(self.cfg["debug"].get("rss_warn_mb", 1500)), objects=True)
        self.status(_("debug_census_done", rss=s["rss_mb"], objects=s["py_objects"]))

    def debug_trim(self):
        from ... import diag
        freed = diag.trim_memory()
        log.info("memory: %s MB given back (from the menu)", freed)
        self.status(_("debug_trim_none") if freed is None else _("debug_trim_done", mb=freed))

    def debug_snapshot(self):
        from ... import diag, leaks
        try:
            out = leaks.snapshot(diag.logs_dir(self.view.paths))
        except (OSError, RuntimeError) as e:
            self.error(e)
            return
        self.status(_("debug_snapshot_done", path=str(out)), seconds=15)

    def bug_report(self):
        from ... import diag
        try:
            diag.log_stats()
            out = diag.bug_report(self.view.paths, cfg=self.cfg)
        except OSError as e:
            self.error(e)
            return
        self.status(_("debug_report_done", path=str(out)), seconds=15)
        self.open_path(out.parent)
        self.send_report(out)

    def send_report(self, out):
        """Into debug.report_repo too, if one is set (fedtail/reportsend.py), in the
        background — as Qt's."""
        from ... import reportsend
        repo = self.cfg["debug"].get("report_repo", "")
        if not repo:
            return
        self.status(_("bugreport_sending", repo=repo))
        self.bridge.call(
            self.core.submit(reportsend.send_report, out, self.cfg, self.view.paths.data_dir),
            ok=lambda where: self.status(_("bugreport_sent", where=where), seconds=15),
            fail=lambda err: self.status(_("bugreport_send_failed", repo=repo, err=err),
                                         seconds=30))

    def report_issue(self):
        """"Report a bug on GitHub…" (gtk/issue.py), as Qt's."""
        from .issue import IssueWindow
        IssueWindow(self).present()

    def set_hints(self, on):
        from . import gi_setup
        self.hints_on = gi_setup.HINTS["on"] = bool(on)
        if on:  # how it works, once it's on (as Qt says)
            self.status(_("whats_this_on"), seconds=8)

    def _beep(self):
        """The "bell" sound of the terminal-looking themes: the display's own beep."""
        display = Gdk.Display.get_default()
        if display is not None:
            display.beep()

    def try_theme(self, name):
        """Another theme for this run (the config stays): the window restyled, the
        lanes drawn anew in its words."""
        from . import theme as themes
        if name == self.theme.id:
            return
        old = self.theme.id
        theme = themes.apply(self.cfg, name)
        self.theme = self.ctx.theme = theme
        self.sounds.set_theme(theme.id)
        if getattr(self, "corner_label", None) is not None:  # the corner says which, now
            self.corner_label.set_text(self._debug_corner())
        log.info("theme tried: %s (was %s, config says %s)", theme.id, old,
                 self.cfg["ui"]["theme"])
        current = self._current_lane()
        columns = self.columns is not None
        if columns:
            self.set_columns(False)
        # split: the lanes' tabs drawn anew too, in their places, the one in front kept
        front = self.tabs.get_nth_page(self.tabs.get_current_page())
        tabbed = [(self.tabs.page_num(lv), n) for n, lv in self.lane_tabs.items()]
        front_lane = next((n for n, lv in self.lane_tabs.items() if lv is front), None)
        for lv in list(self.lane_tabs.values()):
            self.tabs.remove_page(self.tabs.page_num(lv))
        self.lane_tabs = {}
        for lv in self.lane_views.values():
            if hasattr(lv, "stop"):
                lv.stop()
            if lv.get_parent() is self.stack:
                self.stack.remove(lv)
        self.lane_views = {}
        for at, name in sorted(tabbed):
            lv = self._lane_tab(name)
            self.tabs.reorder_child(lv, at)
        self._rebuild_sidebar()
        if front_lane is not None:
            self.tabs.set_current_page(self.tabs.page_num(self.lane_tabs[front_lane]))
            self.lane_tabs[front_lane].shown()
        elif front is not None and self.tabs.page_num(front) >= 0:
            self.tabs.set_current_page(self.tabs.page_num(front))
        if current in self.lane_rows and not self.split_mode:
            self._lane_selected(self.sidebar, self.lane_rows[current])
        if columns:
            self.set_columns(True)
        if getattr(self, "menu_btn", None) is not None:
            self._dress_head()
        for part in (self.dock, self.author_bar, self.roster):  # their pictures anew
            if part is not None and hasattr(part, "dress"):
                part.dress()
        for w in theme.warnings:
            self.error(w)
        self.status(_("theme_tried", name=theme.id, configured=self.cfg["ui"]["theme"]),
                    seconds=12)

    def switch_profile(self, name):
        """The other account in its own window; this one closes (ui.switch_closes)."""
        from ...core import profiles
        if name == self.view.paths.profile:
            return
        log.info("switching to profile %s", name)
        profiles.launch(name)
        if self.cfg["ui"].get("switch_closes", True):
            GLib.timeout_add(300, lambda: (self.close(), False)[1])

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
        GLib.timeout_add(200, lambda: (self.quit_app(), False)[1])

    def open_settings(self, query=""):
        """The settings window (gtk/settings.py; what it shows: common/settings.py)."""
        from .settings import SettingsWindow
        win = getattr(self, "_settings", None)
        if win is None or not win.get_visible():
            win = self._settings = SettingsWindow(self)
        if query:
            win.search.set_text(query)
        win.present()

    def add_account(self):
        from ...core import paths as paths_module
        from ...core import profiles
        from . import dialogs
        taken = {p["name"] for p in profiles.listing()}

        def made(name):
            if name in taken or name in profiles.NOT_PROFILES or \
                    not paths_module._PROFILE_RE.match(name):
                self.error(_("account_bad_name", name=name))
                return
            self.switch_profile(name)  # a new profile starts with the login window
        dialogs.ask_text(self, _("account_add"), _("account_add_q"), made)

    def make_main(self):
        from ...core import paths
        paths.set_main(self.view.paths.profile)
        log.info("main profile: %s (from the menu)", self.view.paths.profile)
        self._profile_text()
        self.status(_("made_main", profile=self.view.paths.profile))

    def relogin(self):
        """Log in to this same account anew; the old token stays until the new one is in."""
        auth = self.view.auth or {}
        if not auth:
            return
        acct = "@" + (self.view.auth_handle or "?")

        def go():
            login.LoginDialog(self, self._connect,
                              expect=(auth["server"], self.view.auth_handle)).present()
        self.confirm(_("relogin_title"), _("relogin_q", acct=acct).replace("<br>", "\n"), go)

    def log_out(self):
        """Forget this profile's token; the window goes over to another account logged
        in (the ★ moves with it), or, none left, to the login."""
        from ...core import profiles
        me = self.view.paths.profile
        mine = self.view.me
        acct = "@" + (mine.handle if mine else self.view.auth_handle or me)
        others = [p for p in profiles.listing() if p["logged_in"] and p["name"] != me]
        main = profiles.paths.main_profile()
        text = [_("logout_q", acct=acct)]
        target = None
        if others:
            target = next((p for p in others if p["name"] == main), others[0])
            if me == main:
                text.append(_("logout_main_moves", to=profiles.label(target)))
            text.append(_("logout_switch", to=profiles.label(target)))
        else:
            text.append(_("logout_last"))

        def go():
            log.info("logout: profile %s", me)
            self.core.logout()
            profiles.hand_over_main(me)
            if target:
                profiles.launch(target["name"])
                GLib.timeout_add(300, lambda: (self.close(), False)[1])
            else:
                self.start()
        self.confirm(_("logout_title"), "\n\n".join(text).replace("<br>", "\n"), go,
                     yes=_("logout_yes"))

    def about(self):
        """About fedtail: the same cards as Qt's (gtk/about.py, common/about.py)."""
        from .about import show
        show(self)

    # ---- ↔ and ❯ ------------------------------------------------------------------------
    def set_full_width(self, on):
        """Posts across the whole width, or in a column of ui.max_width (remembered for
        the next start; the config's value stays what it is)."""
        if not hasattr(self, "_column_width"):
            self._column_width = self.cfg["ui"]["max_width"] or 760
        self.cfg["ui"]["max_width"] = 0 if on else self._column_width
        self.view.set_state("full_width", bool(on))
        for lv in self.lane_views.values():
            if hasattr(lv, "apply_width"):
                lv.apply_width()
        log.info("posts: %s", "full width" if on else f"{self._column_width} px column")

    def set_columns(self, on):
        """Lanes side by side (the same lane views move over, each keeping its place
        and filters), or one at a time."""
        from ..common import columns as cols
        on = bool(on)
        if self.columns_btn.get_active() != on:
            self.columns_btn.set_active(on)  # comes back here through toggled
            return
        if on == (self.columns is not None):
            return
        if on:
            titles = {x.title: "list:" + x.id for x in self.view.lists}
            names = cols.start_names(self.cfg, self.view.get_state("columns"),
                                     list(self.lane_rows), titles)
            self.columns = Columns(self)
            for name in names:
                self.columns.add(name, self._lane_view(name))
            self.stack.add_named(self.columns, "__columns__")
            self.stack.set_visible_child(self.columns)
            self.tabs.set_current_page(0)
            self.tabs.set_tab_label(self.stack, Gtk.Label(label=_("columns")))  # as Qt's
            self.view.set_active_lanes(names)
            log.info("columns: %s", ", ".join(names))
        else:
            focused = self.columns.focused
            for name, lv in self.columns.release():
                self.stack.add_named(lv, name)
            self.stack.remove(self.columns)
            self.columns = None
            self.tabs.set_tab_label(self.stack, Gtk.Label(label=_("gtk_lanes")))
            self.view.set_active_lanes([])
            log.info("columns off")
            row = self.lane_rows.get(focused or self._current_lane())
            if row is not None:
                self._lane_selected(self.sidebar, row)

    def columns_changed(self):
        if self.columns is not None:
            self.view.set_state("columns", self.columns.names())
            self.view.set_active_lanes(self.columns.names())

    def close_column(self, name):
        if self.columns is None or len(self.columns.order) <= 1:
            return  # the last one stays: ❯ goes back to one lane
        lv = self.columns.drop(name)
        if lv is not None:
            self.stack.add_named(lv, name)
        self.columns_changed()

    def _toggle_pin(self, page, title, close):
        """ui.pin_tabs: a pinned tab has no ✕, and Esc / Ctrl+W pass it by."""
        page._ft_pinned = not getattr(page, "_ft_pinned", False)
        text = title.get_label().removeprefix("📌 ")
        title.set_label(("📌 " + text) if page._ft_pinned else text)
        close.set_visible(not page._ft_pinned)
        title.set_tooltip_text(_("tab_unpin" if page._ft_pinned else "tab_pin") + " — " +
                               _("right_click"))
        self.status(_("tab_pinned") if page._ft_pinned else _("tab_unpinned"))

    def _close_current_tab(self):
        page = self.tabs.get_nth_page(self.tabs.get_current_page())
        if getattr(page, "_ft_pinned", False):
            self.status(_("tab_pinned_stays"))
            return
        root = next((r for r, p in self.threads.items() if p is page), None)
        if root is not None:
            self.close_thread(root)
        acc = next((a for a, p in self.accounts.items() if p is page), None)
        if acc is not None:
            self.close_account(acc)

    # ---- start -----------------------------------------------------------------------
    def start(self):
        if getattr(self, "tray", None) is None and self.cfg["ui"].get("tray", True):
            from . import tray
            self.tray = tray.make(self)  # (None: the desktop shows no tray)
        if not self.core.logged_in:
            login.LoginDialog(self, self._connect).present()
            return
        self._connect()

    def _connect(self):
        self.status(_("connecting"), seconds=0)
        self.bridge.call(self.view.connect(), self._connected, self._connect_failed)

    def _connect_failed(self, err):
        """As Qt: a token no longer taken — said, and the login from scratch; the server
        not answering — said, and again in 20 s."""
        err = str(err)
        if "HTTP 401" in err or "HTTP 403" in err:
            self.alert(_("auth_failed_title"), _("auth_failed"))
            self.view.logout()
            self.start()
            return
        self.status(_("server_down", err=err), seconds=0)
        def again():
            if not self.quitting and self.get_visible():  # (not a window closed since)
                self._connect()
            return GLib.SOURCE_REMOVE
        GLib.timeout_add_seconds(20, again)

    def alert(self, title, text):
        """A message with OK, as Qt's QMessageBox.warning (never blocks)."""
        dlg = Gtk.AlertDialog()
        dlg.set_message(title)
        dlg.set_detail(text)
        dlg.show(self)

    def _connected(self, _me):
        self._show_me()
        me = self.view.me
        # until the first round is in, the bar says whose window it is and that the
        # lanes are coming (as Qt's)
        self._hello = _("connected", acct=me.handle if me else "?",
                        server=(self.view.auth or {}).get("server", "")) if me else ""
        self._waiting_text = f"{self._hello} · {_('first_poll')}" if self._hello \
            else _("first_poll")
        self.status(self._waiting_text, seconds=0)
        if self.view.new_options:  # the config doesn't mention new options yet
            GLib.timeout_add_seconds(9, lambda: (self.status(
                _("new_options", n=len(self.view.new_options)), seconds=30),
                GLib.SOURCE_REMOVE)[1])
        problem = getattr(self.notifier, "problem", "")
        if problem and self.cfg["notify"].get("enabled", True):
            self._after_first_poll = problem
        if self.roster is not None:
            self.roster.present()
            self.roster.refresh()
        self._rebuild_sidebar()
        if self.cfg["ui"].get("open_columns"):
            self.set_columns(True)
        self.view.start_polling()
        self.announce_bar.start()

    def _rebuild_sidebar(self):
        current = self._current_lane()
        while (row := self.sidebar.get_first_child()) is not None:
            self.sidebar.remove(row)
        self.lane_rows = {}
        self.sections = {}       # group -> SectionRow
        by_name = self.view.lane_by_name
        folded = sidebar.folded(self.view)
        for group, names in sidebar.groups(self.view, self.cfg):
            # lanes that aren't status streams: only Activity and follow requests are known
            names = [n for n in names if n in by_name and
                     (by_name[n].source is not None or n in SPECIAL)]
            if not names:
                continue
            if group:
                head = SectionRow(group, _("lists_header") if group == "lists"
                                  else _("grp_" + group), names,
                                  plus=self.new_list if group == "lists" else None)
                self.sections[group] = head
                self.sidebar.append(head)
            for name in names:
                title = self.view.lane_title(name) or _("lane_" + _base(name))
                row = LaneRow(name, title, self.theme, self.view.lane_icon(name))
                row.set_visible(group not in folded)
                right = Gtk.GestureClick(button=3)  # a list's menu, as Qt's sidebar
                right.connect("pressed", lambda *_a, r=row: self.lane_menu(r))
                row.add_controller(right)
                self.lane_rows[name] = row
                self.sidebar.append(row)
        self.update_badges()
        start = current or self._start_lane()
        if start == "none" and not current:  # ui.start_lane: every lane closed
            self.close_all()
        elif start in self.lane_rows:
            self.sidebar.select_row(self.lane_rows[start])

    def _start_lane(self):
        want = self.cfg["ui"].get("start_lane") or "last"
        if want == "none":
            return want
        if want == "last":
            want = self.view.get_state("lane") or "home"
        return want if want in self.lane_rows else next(iter(self.lane_rows), None)

    # ---- lanes -------------------------------------------------------------------------
    def current_lane_view(self):
        """The lane in front: a lane's tab (split), or the lane chosen in the sidebar."""
        page = self.tabs.get_nth_page(self.tabs.get_current_page())
        if isinstance(page, LaneView):
            return page
        return self.lane_views.get(self._current_lane() or "")

    def _current_lane(self):
        row = self.sidebar.get_selected_row()
        return row.name if isinstance(row, LaneRow) else None

    def _lane_selected(self, _box, row):
        if not isinstance(row, LaneRow):
            return
        name = row.name
        if self.split_mode:
            lv = self._lane_tab(name)
            self.view.set_active_lane(name)
            self.view.set_state("lane", name)
            lv.shown()
            return
        if self.columns is not None:  # in columns: that column (added if not there)
            self.stack.set_visible_child(self.columns)  # (behind the curtain, maybe)
            if name not in self.columns.frames:
                self.columns.add(name, self._lane_view(name))
                self.columns_changed()
            self.columns.focus(name)
            self.tabs.set_current_page(0)
            self.view.set_active_lane(name)
            self.view.set_state("lane", name)
            self.lane_views[name].shown()
            return
        lv = self._lane_view(name)
        before = self.stack.get_visible_child()
        if before is not lv and hasattr(before, "hidden"):
            before.hidden()
        self.stack.set_visible_child(lv)
        self.tabs.set_current_page(0)
        self.view.set_active_lane(name)
        self.view.set_state("lane", name)
        lv.shown()

    def _lane_view(self, name):
        """The lane's view, made the first time (in the stack until a column takes it)."""
        lv = self.lane_views.get(name)
        if lv is None:
            title = self.lane_title(name)
            lv = SPECIAL[name](self) if name in SPECIAL else LaneView(self.ctx, name, title)
            self.lane_views[name] = lv
            self.stack.add_named(lv, name)
        return lv

    def lane_title(self, name):
        return self.view.lane_title(name) or _("lane_" + _base(name))

    def lane_on_screen(self, name):
        if self.split_mode:
            lv = self.lane_tabs.get(name)
            return lv is not None and \
                self.tabs.get_nth_page(self.tabs.get_current_page()) is lv
        if self.columns is not None:
            return self.tabs.get_current_page() == 0 and name in self.columns.frames
        return self.tabs.get_current_page() == 0 and self._current_lane() == name

    def update_badges(self):
        numbers = sidebar.counts(self.view, self.lane_rows)
        for name, row in self.lane_rows.items():
            row.set_count(numbers[name], sidebar.fresh(self.view, name) if numbers[name] else 0)
        self._slow_text()
        if self.curtain_shown():
            self._curtain_text(numbers)
        if getattr(self, "tray", None) is not None:  # how much is new, on the tray too
            self.tray.set_count(self.get_title() or "fedtail", sum(numbers.values()))
        folded = sidebar.folded(self.view)
        for group, head in self.sections.items():
            head.show_fold(group in folded, sum(numbers.get(n, 0) for n in head.names))
        for name, lv in self.lane_tabs.items():  # split: "Лента (3)" on the lane's tab
            label = self.tabs.get_tab_label(lv)
            n = numbers.get(name, 0)
            if label is not None and hasattr(label, "text"):
                label.text.set_text(self.lane_title(name) + (f" ({n})" if n else ""))
        if self.roster is not None:
            self.roster.refresh_soon()

    def _row_activated(self, _box, row):
        """A section's title clicked: it folds away (or comes back), as in Qt."""
        if not isinstance(row, SectionRow):
            return
        on = sidebar.fold(self.view, row.group)
        for name in row.names:
            if name in self.lane_rows:
                self.lane_rows[name].set_visible(not on)
        self.update_badges()

    def _activated(self):
        if self.is_active():
            lv = self.lane_views.get(self._current_lane())
            if lv is not None:
                lv.window_activated()

    def _tab_switched(self):
        if self.split_mode:  # the tabs are the conversations: always shown
            page = self.tabs.get_nth_page(self.tabs.get_current_page())
            if self.dock is not None and page is not None:
                self.dock.follow(page)
            if self.author_bar is not None:
                self.author_bar.set_visible(hasattr(page, "rows"))
            self._follow_author()
            name = next((n for n, lv in self.lane_tabs.items() if lv is page), None)
            if name is not None:
                self.view.set_active_lane(name)
            return GLib.SOURCE_REMOVE
        self.tabs.set_show_tabs(self.tabs.get_n_pages() > 1)
        return GLib.SOURCE_REMOVE

    # ---- core events ------------------------------------------------------------------
    def on_event(self, name, payload):
        if getattr(getattr(self.core, "store", None), "closed", False):
            return  # queued before the exit, come after the database closed
        if name == "sync_changed":
            self._sync_text()
        elif name == "poll_state":  # a round began or ended: "updating…" / "updated at"
            self._slow_text()
            self._curtain_swing()
        elif name == "read_changed":  # marks only: no lane is rebuilt for them
            for lname, lv in self.lane_views.items():
                if lname in SPECIAL:
                    continue
                if lv.get_mapped() and hasattr(lv, "apply_read"):
                    lv.apply_read(payload or ())
                else:
                    lv.dirty = True
            self.update_badges()
        elif name in ("lanes_updated", "parents", "arrived"):
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
            for page in self.extra_tabs.values():  # split: the talks take theirs in
                if hasattr(page, "add_sent"):
                    page.refresh()
            self.update_badges()
        elif name == "thread_grew":  # replies from other servers, or asked again
            for key, page in list(self.threads.items()):
                posts = getattr(page, "posts", None) or []
                if key == payload or (posts and posts[0].id == payload):
                    self.reload_thread(key)
        elif name == "status_updated" and payload is not None:
            self._post_changed(payload)
        elif name == "status_deleted":
            self.status(_("deleted"), seconds=4)
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
        elif name == "sound":
            self.sounds.play(payload, focused=self.is_active())
        elif name == "lists_changed":
            self._rebuild_sidebar()
        elif name == "me_updated" and self.view.me is not None:
            self._show_me()
        elif name == "error":
            self.status(_("error", err=payload))
        elif name == "first_poll_done":
            if self.status_line.get_text() == getattr(self, "_waiting_text", None):
                self.status(getattr(self, "_hello", ""), seconds=5)
            later = getattr(self, "_after_first_poll", "")
            if later:
                self._after_first_poll = ""
                self.status(later, seconds=30)
        elif name == "rate_limited":  # once, with when; not an error per lane
            self.status(results.rate_text(payload), seconds=20)
        elif name == "auth_failed":
            self.alert(_("auth_failed_title"), _("auth_failed"))
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
        page.posts = []
        self.threads[root] = page
        from .threadhead import ThreadHead
        page.head = ThreadHead(self, root)  # as Qt's: what it is, Subscribe, Refresh
        box.append(page.head)

        def got(items):
            ctx = Ctx(self.cfg, self.view, self.theme, self.bridge, self, in_thread=True,
                      images=self.images)
            posts = [it.post for it in items]
            page.posts = posts
            if self.dock is not None and \
                    self.tabs.get_nth_page(self.tabs.get_current_page()) is page:
                self.dock.follow(page)
            unread = self.view.unread(posts)
            short = self.view.short_ids(posts)
            focus = None
            for it in items:
                card = Card(ctx, it.post.id, it.post, unread=it.post.id in unread,
                            short_id=short.get(it.post.id), depth=it.depth,
                            number=it.number)
                if it.post.id == root:
                    card.add_css_class("ft-focus")
                    if len(items) > 1:
                        card.mark(_("came_from"))  # as Qt: where the reader came from
                    focus = card
                box.append(card)
            if items:
                title.set_text(_("thread") + ": " + _short(items[0].post))
                page.head.show(posts, short)
            # read as it opens — unless read.mark_read = "manual" (as Qt's thread: the
            # behaviour check of 23.10 found GTK marking a thread read regardless)
            if unread and self.cfg["read"]["mark_read"] != "manual":
                self.view.mark_read(sorted(unread))
            if focus is not None:
                GLib.idle_add(lambda: (_scroll_to(page, box, focus), GLib.SOURCE_REMOVE)[1])
        self.bridge.call(self.view.thread(root), got,
                         lambda err: title.set_text(_("load_failed", err=err)))

    def reload_thread(self, root):
        """The thread anew from the server, in the same place among the tabs."""
        page = self.threads.get(root)
        at = self.tabs.page_num(page) if page is not None else -1
        self.close_thread(root)
        self.open_thread(root)
        page = self.threads.get(root)
        if page is not None and at >= 0:
            self.tabs.reorder_child(page, at)

    def close_thread(self, root):
        page = self.threads.pop(root, None)
        if page is not None:
            self._drop_tab(page)
        self._tab_switched()

    def _drop_tab(self, page):
        """A tab closed: the page out of the notebook, and its handlers — the page's and
        its title's (the × button's) — let go of (gi_setup.forget): the title stayed
        alive, button and all, a tab at a time (the tabs stress test, 26.10)."""
        label = self.tabs.get_tab_label(page)
        self.tabs.remove_page(self.tabs.page_num(page))
        forget(page)  # its cards' handlers held them alive
        forget(label)

        def empty():  # after forget's own pass: the title's insides let go of too —
            child = label.get_first_child()  # something in GTK keeps the box itself
            while child is not None:
                nxt = child.get_next_sibling()
                label.remove(child)
                child = nxt
            return GLib.SOURCE_REMOVE
        if isinstance(label, Gtk.Box):
            GLib.idle_add(empty)

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
        tip(close, _("close_tab"))
        close.connect("clicked", lambda _b: close_fn())
        tab.append(close)
        if self.cfg["ui"].get("pin_tabs"):  # a right click on the tab: pinned, or not
            pin = Gtk.GestureClick(button=3)
            pin.connect("pressed", lambda *_a: self._toggle_pin(page, title, close))
            tab.add_controller(pin)
            title.set_tooltip_text(_("tab_pin") + " — " + _("right_click"))
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
            posts_head = Gtk.Label(label=_("profile_posts"), xalign=0)
            posts_head.add_css_class("ft-account")
            posts_head.add_css_class("caption-heading")
            posts_head.set_margin_top(8)
            box.append(posts_head)
            from .profileposts import ProfilePosts
            page.posts_part = ProfilePosts(self, box, acc)  # pinned, pages, their server
        self.call(self.view.account(acc_id), got_account,
                  lambda err: title.set_text(_("load_failed", err=err)))

    def _moved_banner(self, new):
        """The account moved: where to, with "open" and "follow there" — as in Qt."""
        box = Gtk.Box(spacing=8)
        box.add_css_class("ft-ctx")
        text = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        text.set_markup(_("moved_to", acct=GLib.markup_escape_text("@" + new.handle)))
        box.append(text)
        go = Gtk.Button(label=_("moved_open"))
        go.connect("clicked", lambda _b: self.open_account(new.id))
        box.append(go)
        follow = Gtk.Button(label=_("moved_follow"))
        follow.add_css_class("ft-primary")
        follow.connect("clicked", lambda _b: self.call(
            self.view.follow(new.id),
            lambda _r: self.status(_("followed_now", acct="@" + new.handle))))
        box.append(follow)
        return box

    def close_account(self, acc_id):
        page = self.accounts.pop(acc_id, None)
        if page is not None:
            self._drop_tab(page)
        self._tab_switched()

    def _profile_head(self, acc, own):
        from .card import Avatar, link_markup, name_of
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        head.add_css_class("ft-card")
        banner_url = acc.header_static or acc.header
        if banner_url and self.images is not None and "missing" not in banner_url:
            banner = Gtk.Picture()  # the profile's banner, as on its page
            banner.set_can_shrink(True)
            banner.set_content_fit(Gtk.ContentFit.COVER)
            banner.set_size_request(-1, 140)
            banner.add_css_class("ft-thumb")
            self.images.get(banner_url, banner.set_paintable, owner=banner)
            head.append(banner)
        if acc.moved and self.cfg["feed"].get("show_moved", True):
            head.append(self._moved_banner(acc.moved))
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
        from .gi_setup import side_by_side, wrap_box
        face = Avatar(self.ctx, acc, 64)
        # the face and the words beside it: not a horizontal box (GTK 4.18 asks a box's
        # least height of its wrapping lines at their least width: measure.py)
        head.append(side_by_side(face, names, 10))
        meta = Gtk.Label(xalign=0, wrap=True)
        meta.add_css_class("ft-muted")
        names.append(meta)
        # the buttons, as Qt's (common/profile.py: which, in what order, what they do);
        # too many for a line: they wrap
        buttons = wrap_box(spacing=6, row_spacing=6)
        note = Gtk.Label(xalign=0, wrap=True)
        note.add_css_class("ft-muted")
        note.set_visible(False)
        tip(note, _("note_tip"))
        state = {"rel": None, "software": ""}

        def fill(rel):
            from ..common import profile as prof
            state["rel"] = rel
            since = rel is not None and rel.following and \
                self.view.followed_since(acc.id, rel)
            bits = prof.meta(acc, rel, self.theme.date, since or None,
                             state["software"])[1:]  # (the @ is above)
            meta.set_text(" · ".join(bits))
            meta.set_visible(bool(bits))
            while (c := buttons.get_first_child()) is not None:
                buttons.remove(c)
            for act in prof.actions(acc, rel, own, self.cfg, self.view.supports, lists=True,
                                    collections=True):
                b = Gtk.Button(label=act.label)
                if act.primary:
                    b.add_css_class("ft-primary")
                if act.tip:
                    tip(b, act.tip)
                if act.key == "lists":
                    b.set_label(act.label + " ▾")
                    b.connect("clicked", lambda b: self.lists_popover(acc, b))
                else:
                    b.connect("clicked", lambda _b, k=act.key: prof.do(
                        k, acc, state["rel"], self.view, self, fill))
                buttons.append(b)
            line = prof.note_line(rel, own)
            note.set_text(line)
            note.set_visible(bool(line))
        if own:
            fill(None)
        else:
            self.call(self.view.relationship(acc.id), fill, lambda _e: fill(None))
        from urllib.parse import urlparse
        host = urlparse(acc.url or acc.uri or "").hostname or ""
        if host:  # what their server runs (feed.server_info), on the meta line, as Qt

            def software(name):
                if name:
                    state["software"] = name
                    fill(state["rel"])
            self.call(self.view.server_software(host), software, lambda _e: None)
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
        extra = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        head.append(extra)  # whom of mine they're followed by, their tags and people
        head.append(buttons)
        head.append(note)

        def links_line(words, items, more=0):
            from .card import link_markup as lm
            row = Gtk.Label(xalign=0, wrap=True)
            row.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            row.set_markup(words + ", ".join(lm(u, t) for u, t in items) +
                           (" " + GLib.markup_escape_text(_("act_more", n=more))
                            if more > 0 else ""))
            row.connect("activate-link", lambda _l, u: (self.on_link(u), True)[1])
            extra.append(row)

        def familiar(people):
            people = [a for a in people or () if getattr(a, "id", None)]
            if people:
                text = GLib.markup_escape_text(_("familiar", who="\x00")).split("\x00")
                row_items = [(f"fedtail:account/{a.id}", "@" + a.handle) for a in people[:5]]
                links_line(text[0], row_items, len(people) - 5)

        def featured(got):
            got = got or {}
            tags = [(f"fedtail:tag/{t.name}", "#" + t.name) for t in got.get("tags") or ()
                    if getattr(t, "name", None)]
            people = [(f"fedtail:account/{a.id}", "@" + a.handle)
                      for a in got.get("people") or () if getattr(a, "id", None)]
            for key, items in (("featured_tags", tags), ("featured_people", people)):
                if items:
                    links_line(f"<b>{GLib.markup_escape_text(_(key))}</b> ", items)
        if not own and self.view.supports("familiar"):
            self.call(self.view.familiar(acc.id), familiar, lambda _e: None)
        if self.cfg["feed"].get("profile_featured", True):
            self.call(self.view.featured(acc.id), featured, lambda _e: None)
        return head

    # ---- links: common/links.py asks these ---------------------------------------------
    def on_link(self, uri):
        self.links.open(uri)

    def call(self, future, ok=None, fail=None):
        return self.bridge.call(future, ok, fail or self.error)

    def read_whole(self, st):
        """📄 The whole text from the author's server (an article, an event)."""
        from . import postinfo
        return postinfo.read_whole(self, st)

    def edit_profile(self):
        """My profile edited: name, bio, fields, pictures, who may follow."""
        from .profiledit import ProfileEditor
        return ProfileEditor(self)

    def ask_text(self, title, question, then, text="", allow_empty=False):
        from .dialogs import ask_text
        return ask_text(self, title, question, then, text, allow_empty=allow_empty)

    def choose(self, title, text, options, done, check=None):
        """One of a few (common/timed.py: how long a mute lasts, posts only)."""
        from .dialogs import choose
        self._asking = choose(self, title, text, options, done, check=check)  # (tests)
        return self._asking

    def open_people(self, acc, which):
        """Whom someone follows, or who follows them: a tab of people."""
        from .people import open_people
        return open_people(self, f"people:{which}:{acc.id}",
                           _("people_" + which, acct=acc.handle),
                           lambda cur: self.view.people(acc.id, which, cur))

    # ---- what a post's ⋯ opens (common/links.py asks; gtk/postinfo.py shows) ----------
    def show_history(self, st):
        from . import postinfo
        return postinfo.show_history(self, st)

    def report(self, st):
        from . import postinfo
        return postinfo.report(self, st)

    def open_reactions(self, st, kind):
        from . import postinfo
        return postinfo.open_reactions(self, st, kind)

    def open_link_posts(self, url):
        from . import postinfo
        return postinfo.open_link_posts(self, url)

    def ask_remote_lane(self):
        """≡ → Another server's lane…: which server, then its tab."""
        from ...core.remote import server_host
        from . import dialogs

        def go(text):
            host = server_host(text)
            if not host:
                self.error(_("remote_public_bad", text=text))
                return
            self.open_remote_lane(host)
        dialogs.ask_text(self, _("remote_public").rstrip("…"), _("remote_public_q"), go)

    def open_remote_lane(self, host):
        from . import postinfo
        return postinfo.open_remote_lane(self, host)

    def open_quotes(self, post):
        from . import postinfo
        return postinfo.open_quotes(self, post)

    def read_up_to(self, sid):
        from . import postinfo
        return postinfo.read_up_to(self, sid)

    def error(self, text):
        self.status(_("error", err=text))

    def confirm(self, title, text, then, yes=""):
        """Ask; then() on yes (yes: the button's own word, "Log out"). GTK's dialogs
        answer later, so this never blocks."""
        dlg = Gtk.AlertDialog()
        dlg.set_message(title)
        dlg.set_detail(text)
        dlg.set_buttons([_("gtk_no"), yes or _("gtk_yes")])
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
        if self.dock is not None and not (invite or edit or quote) and \
                self.view.me is not None and not (text and reply_to):
            # the split layout: a reply or a new post goes into the input line
            self.present()
            if isinstance(reply_to, str):
                reply_to = self.view.by_id(reply_to)
            if reply_to is not None:
                self.dock.reply_to(real(reply_to))
            elif text:
                self.dock.start_with(text)
            else:
                self.dock.text.grab_focus()
            return None
        return self.compose_panel(reply_to, invite, edit, quote, text)

    def quote_reply(self, st, text, whole=False):
        """Reply quoting `text` (post.quote_prefix): into the reply to this post that is
        open already — where its cursor is, to answer sentence by sentence — or a new
        one (as Qt's)."""
        if self.view.me is None:
            return None
        st = real(st)
        c = self.composer
        if c is not None and c.reply_to is not None and c.reply_to.id == st.id and \
                not c.edit and not c.invite:
            c.insert_quote(text, whole)
            return c
        panel = self.compose_panel(reply_to=st)
        if panel is not None:
            panel.insert_quote(text, whole, at_end=True)
        return panel

    def compose_panel(self, reply_to=None, invite=False, edit=None, quote=None, text=""):
        """The full editor, whatever the layout."""
        from .compose import ComposeWindow
        if self.view.me is None:
            return None
        if self.composer is not None and self.cfg["ui"].get("compose", "inline") == "inline":
            self.composer.close()  # one at a time: its text waits as a draft first
        panel = ComposeWindow(self, reply_to=reply_to, invite=invite, edit=edit, quote=quote,
                              text=text)
        return panel.open()

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
        if self.dock is not None:
            self.dock.put_alias(alias)
            return
        if self.cmdline is not None:
            self.cmdline.put_alias(alias)

    def resolve_link(self, url):
        """A fediverse link: the post here when the server knows it, else outside."""
        self.status(_("resolving", url=url))

        def got(found):
            from ...model import Account, Post, Share
            if isinstance(found, (Post, Share)):
                self.open_thread(found)
            elif isinstance(found, Account):
                self.open_account(found.id)
            else:
                self.status(_("resolve_browser"), seconds=4)
                self.open_url(url)
                return
            self.status("")
        self.call(self.view.resolve(url), got, lambda _e: self.open_url(url))

    def play_media(self, media, index=0):
        """A video, a gifv or a sound: the player over the window (ui.video_player)."""
        from . import player
        return player.show(self, media, index)

    def save_media(self, m):
        """A picture or a video to ui.save_dir, as Qt's save_image."""
        url = m.url or m.remote_url or m.preview
        if not url:
            return
        from ...core import saving
        self.call(self.images.save(url, saving.save_dir(self.cfg)),
                  lambda p: self.status(_("saved_to", path=str(p))),
                  lambda e: self.error(_("save_failed", err=e)))

    def open_url(self, url):
        if not richtext.openable(url):
            log.warning("not opened (scheme not allowed): %.80s", url)
            self.status(_("link_refused"), seconds=6)
            return
        from ...sysenv import open_external
        if open_external(url):
            return
        try:
            Gio.AppInfo.launch_default_for_uri(url, None)
        except GLib.Error as e:
            self.status(_("error", err=e.message))

    # ---- misc --------------------------------------------------------------------------
    def status(self, text, seconds=10):
        """A line at the bottom for a while (as Qt's status bar), then gone."""
        self.status_line.set_text(text or "")
        if getattr(self, "_status_timer", 0):
            GLib.source_remove(self._status_timer)
            self._status_timer = 0
        if text and seconds:
            def clear():
                self._status_timer = 0
                self.status_line.set_text("")
                return GLib.SOURCE_REMOVE
            self._status_timer = GLib.timeout_add_seconds(seconds, clear)

    def _saved_size(self):
        size = self.view.get_state("gtk_window") or ""
        try:
            w, h = (int(x) for x in size.split("x"))
            return max(w, 480), max(h, 360)
        except ValueError:
            return 1000, 720

    def quit_app(self):
        """≡ → Quit: all of fedtail, whichever window asked (in the split layout closing
        the messages window only hides it)."""
        self.quitting = True
        self.close()
        app = self.get_application()
        if app is not None:
            app.quit()

    def _close_request(self, _win):
        if getattr(self, "tray", None) is not None and self.cfg["ui"].get(
                "close_to_tray", True) and not self.quitting:
            self.hide_away()  # to the tray, as Qt's (ui.close_to_tray)
            return True
        if self.roster is not None and not self.quitting and self.roster.get_visible():
            self.set_visible(False)  # the messages window goes; the roster stays (QIP)
            return True
        w, h = self.get_default_size()
        if w > 0 and h > 0:
            self.view.set_state("gtk_window", f"{w}x{h}")
        if self.columns is not None:
            self.columns_changed()
        self.quitting = True
        self._stop()
        if getattr(self, "tray", None) is not None:
            self.tray.close()
            self.tray = None
        if self.roster is not None and self.roster.get_visible():
            self.roster.close()
        return False

    # ---- the tray ---------------------------------------------------------------------
    def hide_away(self):
        """Off the screen at once: to the tray if there is one, else minimized."""
        if getattr(self, "tray", None) is None:
            self.minimize()
            return
        if self.roster is not None:
            self.roster.set_visible(False)
        self.set_visible(False)

    def show_from_tray(self):
        if self.roster is not None:
            self.roster.present()
        self.present()

    def toggle_from_tray(self):
        """A click on the tray icon: away if it's in front, else back (as Qt's)."""
        shown = self.roster.get_visible() if self.roster is not None else \
            self.get_visible() and self.is_active()
        if shown:
            self.hide_away()
        else:
            self.show_from_tray()

    def _stop(self, *_a):
        if self.composer is not None:  # what was typed waits as a draft
            self.composer.close()
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


def _themes_dir():
    from .. import themefile
    d = themefile.user_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


class Columns(Gtk.ScrolledWindow):
    """Lanes side by side (❯, or ui.layout = "columns"): each a column with ‹ › to
    move it and ✕ to drop it; sideways scrolling when they don't fit. The lane views
    are the window's own: they keep their place and filters across the switch."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.row = Gtk.Box(spacing=1)
        self.set_child(self.row)
        self.frames = {}   # lane name -> its column
        self.order = []
        self.focused = None

    def names(self):
        return list(self.order)

    def add(self, name, lv, at=None):
        if name in self.frames:
            return
        parent = lv.get_parent()
        if parent is self.win.stack:
            self.win.stack.remove(lv)
        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        frame.add_css_class("ft-column")
        frame.set_size_request(int(self.win.cfg["ui"].get("column_width", 460)), -1)
        bar = Gtk.Box(spacing=2)
        for text, key, step in (("‹", "column_left", -1), ("›", "column_right", 1)):
            b = Gtk.Button(label=text)
            b.add_css_class("flat")
            tip(b, _(key))
            b.connect("clicked", lambda _b, n=name, s=step: self.move(n, s))
            bar.append(b)
        bar.append(Gtk.Box(hexpand=True))
        close = Gtk.Button(label="✕")
        close.add_css_class("flat")
        tip(close, _("column_close"))
        close.connect("clicked", lambda _b, n=name: self.win.close_column(n))
        bar.append(close)
        frame.append(bar)
        lv.set_vexpand(True)
        frame.append(lv)
        click = Gtk.GestureClick()
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", lambda *_a, n=name: self._focused(n))
        frame.add_controller(click)
        self.frames[name] = frame
        at = len(self.order) if at is None else max(0, min(at, len(self.order)))
        self.order.insert(at, name)
        before = self.frames[self.order[at - 1]] if at > 0 else None
        self.row.insert_child_after(frame, before)
        if self.focused is None:
            self.focused = name
        lv.shown()

    def drop(self, name):
        frame = self.frames.pop(name, None)
        if frame is None:
            return None
        self.order.remove(name)
        lv = self.win.lane_views.get(name)
        if lv is not None and lv.get_parent() is frame:
            frame.remove(lv)
        self.row.remove(frame)
        if self.focused == name:
            self.focused = self.order[0] if self.order else None
        return lv

    def move(self, name, step):
        if name not in self.order:
            return
        i = self.order.index(name)
        j = max(0, min(len(self.order) - 1, i + step))
        if i == j:
            return
        self.order.insert(j, self.order.pop(i))
        frame = self.frames[name]
        before = self.frames[self.order[j - 1]] if j > 0 else None
        self.row.reorder_child_after(frame, before)
        self.win.columns_changed()

    def release(self):
        out = []
        for name in list(self.order):
            lv = self.drop(name)
            if lv is not None:
                out.append((name, lv))
        return out

    def focus(self, name):
        if name in self.frames:
            self._focused(name)
            frame = self.frames[name]
            GLib.idle_add(lambda: (self._show(frame), False)[1])

    def _show(self, frame):
        ok, rect = frame.compute_bounds(self.row) if hasattr(frame, "compute_bounds") \
            else (False, None)
        if ok:
            adj = self.get_hadjustment()
            x = rect.get_x()
            if x < adj.get_value() or x + rect.get_width() > adj.get_value() + \
                    adj.get_page_size():
                adj.set_value(max(0, x))

    def _focused(self, name):
        self.focused = name
        self.win.view.set_active_lane(name)
