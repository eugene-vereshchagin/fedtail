"""GTK 4 frontend (PyGObject), libadwaita when there is one: docs/en/dev/gtk.md.

Stage 1 — the frame: log in, lanes with their counts, posts as cards, threads in tabs,
reading marks, the theme files. Writing, pictures, the post menu and the rest come
stage by stage; until then the Qt window is the full one.
"""

import logging
import signal
import sys

from . import gi_setup  # here, so a missing GTK is told at load time (frontends.load)

log = logging.getLogger("fedtail")


def screen_reader_on():
    """Is a screen reader running (org.a11y.Status.ScreenReaderEnabled on the session
    bus)? No bus, no answer in a moment: no."""
    from .gi_setup import Gio, GLib
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        got = bus.call_sync("org.a11y.Bus", "/org/a11y/bus",
                            "org.freedesktop.DBus.Properties", "Get",
                            GLib.Variant("(ss)", ("org.a11y.Status", "ScreenReaderEnabled")),
                            None, Gio.DBusCallFlags.NONE, 300, None)
        return bool(got.unpack()[0])
    except Exception as e:  # noqa: BLE001 — no bus, no a11y service: nobody listens
        log.debug("screen reader: %s", e)
        return False


def accessibility(mode):
    """ui.accessibility: GTK talks to the accessibility bus — always ("on"), never
    ("off"), or only while a screen reader is on ("auto"). KDE keeps that bus up with
    nobody reading, and GTK 4 then makes an accessible object on it for every widget:
    the ≡ menu took 2 s to open, a lane's cards their share too. GTK reads GTK_A11Y when
    it makes its first widget — this runs before. Returns whether it's on."""
    import os
    if os.environ.get("GTK_A11Y"):  # set by hand: as it says
        return os.environ["GTK_A11Y"].lower() != "none"
    on = mode == "on" or (mode == "auto" and screen_reader_on())
    if not on:
        os.environ["GTK_A11Y"] = "none"
    return on


def run(core, instance, argv):
    a11y = accessibility(core.cfg["ui"].get("accessibility", "auto"))
    from .gi_setup import Gio, GLib, Gtk
    if gi_setup.gtk_version()[:2] < gi_setup.MIN_GTK:
        need, have = gi_setup.MIN_GTK, gi_setup.gtk_version()
        print(f"fedtail: the GTK interface needs GTK {need[0]}.{need[1]} or newer "
              f"(have {'.'.join(map(str, have))})", file=sys.stderr)
        return 3
    Adw = gi_setup.load_adwaita(core.cfg["ui"].get("adwaita", "auto"))
    from ...core.view import View
    from ...desktop import desktop_id
    from . import theme as themes
    from .bridge import Bridge
    from .window import MainWindow
    app_id = desktop_id(core.paths.profile)  # Wayland finds the .desktop entry by it
    GLib.set_prgname("fedtail")  # X11: WM_CLASS, as the entry's StartupWMClass says
    # fedtail has its own single-instance socket: GTK must not make a second one
    flags = Gio.ApplicationFlags.NON_UNIQUE
    app = (Adw.Application if Adw else Gtk.Application)(application_id=app_id, flags=flags)
    view = View(core)
    bridge = Bridge(view)
    state = {}
    from . import diagnostics
    stop_diag = diagnostics.install(core.cfg)  # a frozen window: its stacks in the log

    def activate(_app):
        from . import scale
        scale.apply()  # the desktop's 125 % on X11, before anything is measured
        theme = themes.apply(core.cfg)
        win = MainWindow(app, core, view, bridge, theme)
        state["win"] = win
        log.info("GTK %d.%d.%d, libadwaita %s, theme %s (%s), from %s, accessibility %s",
                 *gi_setup.gtk_version(),
                 f"{Adw.get_major_version()}.{Adw.get_minor_version()}" if Adw
                 else "none", theme.id, "dark" if theme.dark else "light",
                 "one-file build" if getattr(sys, "frozen", False) else "source",
                 ("on" if a11y else "off (ui.accessibility)") +
                 ("" if a11y or Gtk.Button().get_at_context() is None
                  else " — but GTK made one anyway (GTK_A11Y not taken)"))

        # the split layout starts with the roster only (as Qt's): the messages window
        # comes when something in it is opened
        front = win.roster if win.roster is not None else win

        def message(msg):
            GLib.idle_add(lambda: (front.present(), GLib.SOURCE_REMOVE)[1])
        instance.listen(message)
        front.present()

        def warm_menu():
            # the first ≡ menu GTK builds took 1.5–2 s on KDE (each later one: ms) — a
            # cost paid once per run; paid here, after start, in parts that the log
            # names, so the first click opens at once (and the slow part shows itself)
            import time

            from gi.repository import Gdk
            steps = []
            t = time.monotonic()
            it = Gtk.IconTheme.get_for_display(win.get_display())
            for name in ("pan-end-symbolic", "object-select-symbolic", "go-previous-symbolic"):
                it.has_icon(name)
            steps.append(("icon theme " + (it.get_theme_name() or "?"), time.monotonic() - t))
            t = time.monotonic()
            Gtk.accelerator_get_label(Gdk.KEY_q, Gdk.ModifierType.CONTROL_MASK)
            steps.append(("key names", time.monotonic() - t))
            for btn, make in list(getattr(win.menu, "buttons", ())):
                t = time.monotonic()
                make(btn)  # its popover, made now — the click finds it ready
                steps.append(("a menu", time.monotonic() - t))
            total = sum(x for _n, x in steps)
            (log.info if total > 0.2 else log.debug)(
                "menus warmed in %.0f ms: %s", total * 1000,
                ", ".join(f"{n} {x * 1000:.0f} ms" for n, x in steps))
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(1500, warm_menu)
        GLib.idle_add(lambda: (win.start(), GLib.SOURCE_REMOVE)[1])

    app.connect("activate", activate)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT,
                         lambda: (app.quit(), GLib.SOURCE_REMOVE)[1])
    try:
        return app.run(argv[:1])
    finally:
        stop_diag()
        core.shutdown()
