"""The ≡ menu of the GTK window — the Qt window's, item for item: for the tender and
sensitive, scheduled posts, find people, account and server, the config, themes and
data folders, try a theme, debugging, help, what's this, about, quit.

The model is made anew each time it opens (accounts and themes change), the actions
("win.<name>") once. What each item does lives in the window, the dialogs and the
core, as in Qt."""

from __future__ import annotations

import logging

from ...i18n import _
from .gi_setup import Gio, GLib, Gtk, tip

log = logging.getLogger(__name__)


def _item(menu, label, action, target=None, accel=None):
    it = Gio.MenuItem.new(label, None)
    if target is None:
        it.set_detailed_action("win." + action)
    else:
        it.set_action_and_target_value("win." + action, GLib.Variant("s", target))
    if accel:
        it.set_attribute_value("accel", GLib.Variant("s", accel))
    menu.append_item(it)


class MainMenu:
    """The actions on the window and the menu model, made when the button opens."""

    def __init__(self, win):
        self.win = win
        self.buttons = []  # (MenuButton, make) of every ≡ made from this menu
        a = self._act
        a("write", win.compose)
        a("refresh", win.view.poll_now)
        a("readall", win.read_current_lane)
        a("filters", lambda: win.silence("filters"))
        a("muted", lambda: win.silence("muted"))
        a("blocked", lambda: win.silence("blocked"))
        a("domains", lambda: win.silence("domains"))
        a("filtered", win.show_filtered)
        a("scheduled", win.show_scheduled)
        a("suggestions", win.open_suggestions)
        a("directory", lambda: win.open_directory(False))
        a("directory_local", lambda: win.open_directory(True))
        a("trends", win.open_trends)
        a("profile", win.my_profile)
        a("server", win.show_server_info)
        a("add_account", win.add_account)
        a("make_main", win.make_main)
        a("relogin", win.relogin)
        a("logout", win.log_out)
        a("config", lambda: win.open_path(win.view.paths.config_file))
        a("themes", lambda: win.open_path(win.themes_dir()))
        a("data", lambda: win.open_path(win.view.paths.data_dir))
        a("federation", win.federation_status)
        a("logs", win.open_logs)
        a("report", win.bug_report)
        a("test_notify", win.test_notification)
        a("test_sound", lambda: win.status(win.sounds.test()))
        a("stacks", win.debug_stacks)
        a("census", win.debug_census)
        a("trim", win.debug_trim)
        a("snapshot", win.debug_snapshot)
        a("help", win.open_help)
        a("about", win.about)
        # after the menu has gone: quitting from inside the popover's own click left the
        # window up (the tray's Quit, which runs later, always worked)
        a("quit", lambda: GLib.idle_add(lambda: (win.quit_app(), GLib.SOURCE_REMOVE)[1]))
        self._arg("switch", win.switch_profile)
        self._arg("theme", win.try_theme)
        self._toggle("merged", lambda: bool(getattr(win.core, "others", None)),
                     win.set_merged)
        from ... import leaks
        self._toggle("tracing", leaks.tracing,
                     lambda on: leaks.start_tracing() if on else leaks.stop_tracing())
        self._toggle("whats_this", lambda: win.hints_on, win.set_hints)

    def _act(self, name, fn):
        act = Gio.SimpleAction.new(name, None)
        act.connect("activate", lambda _a, _p: fn())
        self.win.add_action(act)

    def _arg(self, name, fn):
        act = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
        act.connect("activate", lambda _a, v: fn(v.get_string()))
        self.win.add_action(act)

    def _toggle(self, name, now, fn):
        act = Gio.SimpleAction.new_stateful(name, None, GLib.Variant("b", bool(now())))

        def flip(a, _p):
            on = not a.get_state().get_boolean()
            a.set_state(GLib.Variant("b", on))
            fn(on)
        act.connect("activate", flip)
        self.win.add_action(act)
        setattr(self, "_now_" + name, (act, now))

    def _sync(self):
        for name in ("merged", "tracing", "whats_this"):
            act, now = getattr(self, "_now_" + name)
            act.set_state(GLib.Variant("b", bool(now())))

    def enable(self, name, on):
        act = self.win.lookup_action(name)
        if act is not None:
            act.set_enabled(bool(on))

    # ---- the model ---------------------------------------------------------------------
    def model(self):
        self._sync()
        win, cfg = self.win, self.win.cfg
        top = Gio.Menu()

        first = Gio.Menu()
        tender = Gio.Menu()
        if cfg["ui"].get("arts_mode"):
            note = Gio.Menu()
            _item(note, _("tender_arts"), "noop")
            tender.append_section(None, note)
        lines = Gio.Menu()
        for action, key in (("filters", "silence_filters"), ("muted", "silence_muted"),
                            ("blocked", "silence_blocked"), ("domains", "tender_domains")):
            _item(lines, _(key) + "…", action)
        tender.append_section(None, lines)
        if cfg["notify"].get("filtered", "off") != "off":
            more = Gio.Menu()
            _item(more, _("filtered_title") + "…", "filtered")
            tender.append_section(None, more)
        first.append_submenu(_("tender_menu"), tender)
        if cfg["post"].get("schedule", True):
            _item(first, _("scheduled_title") + "…", "scheduled")
        people = Gio.Menu()
        supports = win.ctx.supports
        trends = any(supports("trends_" + k) for k in ("statuses", "tags", "links"))
        for feature, label, action in (
                ("suggestions", _("suggestions_title"), "suggestions"),
                ("directory", _("directory_title"), "directory"),
                ("directory", _("directory_local"), "directory_local"),
                ("trends", _("trends_title"), "trends")):
            if supports(feature) and (feature != "trends" or trends):
                _item(people, label, action)
        if people.get_n_items():
            first.append_submenu(_("menu_people"), people)
        first.append_submenu(_("accounts"), self.accounts_model())
        top.append_section(None, first)

        files = Gio.Menu()
        _item(files, _("open_config"), "config")
        _item(files, _("open_themes"), "themes")
        files.append_submenu(_("try_theme"), self._themes())
        _item(files, _("open_data"), "data")
        top.append_section(None, files)

        dbg = Gio.Menu()
        one = Gio.Menu()
        for action, key in (("federation", "debug_federation"), ("logs", "debug_logs"),
                            ("report", "debug_report"), ("test_notify", "debug_notify"),
                            ("test_sound", "debug_sound"), ("stacks", "debug_stacks")):
            _item(one, _(key), action)
        dbg.append_section(None, one)
        two = Gio.Menu()
        for action, key in (("census", "debug_census"), ("trim", "debug_trim"),
                            ("tracing", "debug_tracing"), ("snapshot", "debug_snapshot")):
            _item(two, _(key), action)
        from ... import leaks
        self.enable("snapshot", leaks.tracing())
        dbg.append_section(None, two)
        debug = Gio.Menu()
        debug.append_submenu(_("debug_menu"), dbg)
        top.append_section(None, debug)

        helps = Gio.Menu()
        _item(helps, _("help_title"), "help")
        _item(helps, _("whats_this"), "whats_this")
        _item(helps, _("about"), "about")
        top.append_section(None, helps)
        last = Gio.Menu()
        _item(last, _("quit"), "quit", accel="<Control>q")
        top.append_section(None, last)
        return top

    def accounts_model(self):
        """The accounts (profiles), checked the one this window is; my profile, the
        server; all in one window; add one; make this the main one; log in anew; out."""
        from ...core import paths, profiles
        win = self.win
        m = Gio.Menu()
        who = Gio.Menu()
        me = win.view.paths.profile
        for p in profiles.listing():
            label = profiles.label(p) + (" ★" if p.get("main") else "") + \
                ("" if p["logged_in"] else "  " + _("not_logged_in"))
            if p["name"] == me:
                label = "✓ " + label
            _item(who, label, "switch", target=p["name"])
        m.append_section(None, who)
        mine = Gio.Menu()
        _item(mine, _("my_profile"), "profile")
        _item(mine, _("server_info") + "…", "server")
        _item(mine, _("accounts_merge"), "merged")
        self.enable("merged", not win.cfg["ui"].get("merge"))
        _item(mine, _("account_add"), "add_account")
        m.append_section(None, mine)
        danger = Gio.Menu()
        alone = not getattr(win.core, "others", None)
        if me != paths.main_profile():
            _item(danger, _("make_main"), "make_main")
        _item(danger, _("relogin"), "relogin")
        _item(danger, _("logout"), "logout")
        for name in ("relogin", "logout"):
            self.enable(name, alone and bool(win.view.auth))
        self.enable("profile", win.view.me is not None)
        self.enable("server", win.view.me is not None)
        m.append_section(None, danger)
        return m

    def _themes(self):
        from .. import themefile
        win = self.win
        m = Gio.Menu()
        configured = win.cfg["ui"]["theme"]
        for name in themefile.for_layout(win.cfg, keep=(configured, win.theme.id)):
            label = ("✓ " if name == win.theme.id else "") + name + \
                ("  · " + _("theme_in_config") if name == configured else "")
            _item(m, label, "theme", target=name)
        return m


def signature(model):
    """What a menu model says, as a tuple: equal ones need no new popover."""
    out = []
    for i in range(model.get_n_items()):
        attrs = []
        it = model.iterate_item_attributes(i)
        while it.next():
            attrs.append((it.get_name(), str(it.get_value())))
        links = []
        it = model.iterate_item_links(i)
        while it.next():
            links.append((it.get_name(), signature(it.get_value())))
        out.append((tuple(sorted(attrs)), tuple(links)))
    return tuple(out)


def button(win, menu, icon="open-menu-symbolic", accounts_only=False):
    """A ≡ button that makes its menu when opened — the first time, and again only when
    something in it changed (an account, a theme): GTK builds a popover of the whole
    model, submenus and all, and on KDE (its accessibility bus) that took most of a
    second each time, and five at the start when it was made ahead."""
    b = Gtk.MenuButton(icon_name=icon)
    tip(b, _("accounts") if accounts_only else _("menu"))
    made = [None]
    asked = [0.0]  # when this opening was asked for (the popover reports when it shows)

    def shown(_p):
        import time
        log.info("menu on screen %.0f ms after it was asked for",
                 (time.monotonic() - asked[0]) * 1000)

    def make(btn):
        import time
        t = asked[0] = time.monotonic()
        model = menu.accounts_model() if accounts_only else menu.model()
        sig = signature(model)
        t_model = time.monotonic() - t
        built = sig != made[0]
        t_set = 0.0
        if built:
            made[0] = sig
            t1 = time.monotonic()
            btn.set_menu_model(model)
            t_set = time.monotonic() - t1
            pop = btn.get_popover()
            if pop is not None:
                pop.connect("map", shown)
        took = time.monotonic() - t
        (log.info if took > 0.2 else log.debug)(
            "menu made in %.0f ms (model %.0f ms, %s%s)", took * 1000, t_model * 1000,
            "built anew" if built else "as before",
            f", GTK's popover {t_set * 1000:.0f} ms" if built else "")
    b.set_create_popup_func(make)
    # made ahead after start (gtk/__init__.warm_menu): built on the click, the first one
    # froze for 1.5 s on KDE, and the click's release, handled after the freeze, closed
    # the menu it had just opened — it took a second click (the split layout's ≡)
    getattr(menu, "buttons", []).append((b, make))
    return b
