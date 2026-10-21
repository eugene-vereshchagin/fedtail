"""GTK 4 frontend (PyGObject), libadwaita when there is one: docs/GTK.md.

Stage 1 — the frame: log in, lanes with their counts, posts as cards, threads in tabs,
reading marks, the theme files. Writing, pictures, the post menu and the rest come
stage by stage; until then the Qt window is the full one.
"""

import logging
import signal
import sys

from . import gi_setup  # here, so a missing GTK is told at load time (frontends.load)

log = logging.getLogger("fedtail")


def run(core, instance, argv):
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
        theme = themes.apply(core.cfg)
        win = MainWindow(app, core, view, bridge, theme)
        state["win"] = win
        log.info("GTK %d.%d.%d, libadwaita %s, theme %s (%s), from %s",
                 *gi_setup.gtk_version(),
                 f"{Adw.get_major_version()}.{Adw.get_minor_version()}" if Adw
                 else "none", theme.id, "dark" if theme.dark else "light",
                 "one-file build" if getattr(sys, "frozen", False) else "source")

        def message(msg):
            GLib.idle_add(lambda: (win.present(), GLib.SOURCE_REMOVE)[1])
        instance.listen(message)
        win.present()
        GLib.idle_add(lambda: (win.start(), GLib.SOURCE_REMOVE)[1])

    app.connect("activate", activate)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT,
                         lambda: (app.quit(), GLib.SOURCE_REMOVE)[1])
    try:
        return app.run(argv[:1])
    finally:
        stop_diag()
        core.shutdown()
