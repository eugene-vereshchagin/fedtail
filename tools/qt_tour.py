"""A walk through the Qt window on a fake server, saving what it sees: every theme in
the single window and (the messengers') in the split layout, every menu — ≡, its
submenus, the accounts, a post's ⋯ — with the list of what's in it, and every window
the ≡ menu opens (Silence, Scheduled, the server, the federation, help, people…).
Whatever goes wrong on the way — an exception, an error on the status bar, a warning in
the log — goes to errors.txt; menus.txt is the inventory of every menu.

    python3 tools/qt_tour.py OUT_DIR [--quick] [--native]

--native: the desktop's own Qt platform (the real fonts, style and icons, windows flash
on the screen); without it, offscreen (nothing shows, the look is plainer)."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
NATIVE = "--native" in sys.argv
if NATIVE:  # (tools/screenshots.py, imported below, would make it offscreen)
    os.environ["QT_QPA_PLATFORM"] = os.environ.get("QT_QPA_PLATFORM") or (
        "windows" if os.name == "nt" else
        "wayland" if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY")
        else "xcb")
else:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_tmp = tempfile.mkdtemp(prefix="fedtail-tour-")
os.environ["XDG_CONFIG_HOME"] = str(Path(_tmp) / "config")
os.environ["XDG_DATA_HOME"] = str(Path(_tmp) / "data")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from fedtail import i18n  # noqa: E402
from fedtail.core import auth, config, paths  # noqa: E402
from fedtail.core.app import Core  # noqa: E402
from tests.fakes import FakeApi  # noqa: E402
from tools import screenshots as shots  # noqa: E402  (its world and pictures)

ERRORS, MENUS = [], []
SPLIT_THEMES = ("system", "qip-retro", "qip-modern", "mra", "mra-blue", "psi")


def pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def save(widget, out, name):
    try:
        widget.adjustSize() if isinstance(widget, QMenu) else None
        widget.grab().save(str(Path(out) / f"{name}.png"))
    except Exception as e:  # noqa: BLE001
        ERRORS.append(f"{name}: can't grab: {e}")


def inventory(menu, title, depth=0):
    """Every item of a menu and its submenus, as lines."""
    lines = []
    for a in menu.actions():
        if a.isSeparator():
            lines.append("  " * depth + "—")
            continue
        flags = ("" if a.isEnabled() else " [off]") + (" [✓]" if a.isChecked() else "")
        lines.append("  " * depth + a.text().replace("\t", "  ") + flags)
        sub = a.menu()
        if sub is not None:
            sub.aboutToShow.emit()  # filled when it opens
            lines += inventory(sub, a.text(), depth + 1)
    if depth == 0:
        MENUS.append(f"== {title}\n" + "\n".join(lines) + "\n")
    return lines


def shoot_menu(menu, out, name):
    menu.aboutToShow.emit()
    save(menu, out, name)
    inventory(menu, name)
    for i, a in enumerate(a for a in menu.actions() if a.menu() is not None):
        sub = a.menu()
        sub.aboutToShow.emit()
        save(sub, out, f"{name}-sub{i}")


def closing_modals(app, out, name, fn):
    """Call fn; whatever window it opens — modal (exec) or not — is saved and closed."""
    before = {id(w) for w in app.topLevelWidgets() if w.isVisible()}
    shot = []

    def close_modal():
        w = app.activeModalWidget() or app.activePopupWidget()
        if w is not None:
            save(w, out, name)
            shot.append(1)
            w.close()
    timer = QTimer()
    timer.setInterval(700)
    timer.timeout.connect(close_modal)
    timer.start()
    try:
        fn()
    except Exception:  # noqa: BLE001
        ERRORS.append(f"{name}: " + traceback.format_exc(limit=6))
    pump(app, 1.2)
    timer.stop()
    for w in app.topLevelWidgets():
        if w.isVisible() and id(w) not in before and not isinstance(w, QMenu):
            if not shot:
                save(w, out, name)
                shot.append(1)
            w.close()
    pump(app, 0.2)


def make_window(app, theme_name, layout, label):
    from fedtail.frontends.qt import theme as themes
    from fedtail.frontends.qt.bridge import Bridge
    from fedtail.frontends.qt.window import MainWindow
    FakeApi.world = shots.world()
    cfg, _ = config.validate({"ui": {"theme": theme_name, "layout": layout},
                              "feed": {"first_run_mark_read": False}})
    data = Path(_tmp) / f"profile-{label}"
    p = paths.resolve(label, config=str(data / "c.toml"), data=str(data))
    auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
    core = Core(cfg, p, api_class=FakeApi)
    core._origin_json = lambda url: None
    theme = themes.apply(app, cfg)
    win = MainWindow(core, Bridge(core), theme)
    win.images.get = lambda url, cb, *a, **k: cb(shots.make_pixmap(url))
    win.tray = None
    win.resize(1280, 860)
    win.show()
    win.start()
    pump(app, 1.0)
    core.poll_once()
    pump(app, 1.0)
    win.select_lane("home")
    pump(app, 1.5)
    return core, win


def close_window(app, core, win):
    win.quitting = True
    if getattr(win, "roster", None) is not None:
        win.roster.close()
    win.hide()
    core.shutdown()
    win.deleteLater()
    pump(app, 0.3)


def tour_menus(app, out, core, win):
    """The ≡ menu and all it opens, the accounts, a post's ⋯."""
    shoot_menu(win._app_menu(), out, "menu-main")
    shoot_menu(win.accounts_menu(), out, "menu-accounts")
    from fedtail.frontends.qt.card import PostRow
    cards = [c for c in win.findChildren(PostRow) if c.isVisible()]
    if cards:
        menu = cards[0].ensure_menu()
        if menu is not None:
            shoot_menu(menu, out, "menu-post")
    else:
        ERRORS.append("no post card on screen for the ⋯ menu")
    from fedtail.frontends.qt.silence import SilenceDialog
    for name, fn in (("dlg-silence", lambda: SilenceDialog(win, "filters").exec()),
                     ("dlg-scheduled", win.show_scheduled),
                     ("dlg-filtered", win.show_filtered),
                     ("dlg-server", win.show_server_info),
                     ("dlg-federation", win.federation_status),
                     ("dlg-help", win.open_help),
                     ("tab-suggestions", win.open_suggestions),
                     ("tab-directory", lambda: win.open_directory(False)),
                     ("tab-trends", win.open_trends),
                     ("tab-search", lambda: win.open_search("o")),
                     ("dlg-profile", win.edit_profile),
                     ("compose", lambda: win.compose()),
                     ("about", win.about)):
        closing_modals(app, out, name, fn)
        if name.startswith("tab-"):
            save(win, out, name)
            win.close_tab(win.tabs.currentIndex())
            pump(app, 0.3)


def main():
    import logging
    out = Path(next((a for a in sys.argv[1:] if not a.startswith("--")), "qt-tour"))
    out.mkdir(parents=True, exist_ok=True)
    quick = "--quick" in sys.argv

    class Keep(logging.Handler):
        def emit(self, record):
            ERRORS.append("log: " + self.format(record))
    keep = Keep(logging.WARNING)
    keep.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(keep)
    old_hook = sys.excepthook

    def hook(t, v, tb):  # an exception inside a Qt slot: kept, the walk goes on
        ERRORS.append("exception: " + "".join(traceback.format_exception(t, v, tb, limit=8)))
        old_hook(t, v, tb)
    sys.excepthook = hook
    i18n.setup("ru")
    app = QApplication.instance() or QApplication([])
    if not NATIVE:
        app.setStyle("Fusion")
    from fedtail.frontends import themefile
    themes = ("system", "point", "qip-retro") if quick else tuple(themefile.available())
    first = True
    for name in themes:
        for layout in ("single",) + (("split",) if name in SPLIT_THEMES else ()):
            label = f"{name}-{layout}"
            t0 = time.monotonic()
            try:
                core, win = make_window(app, name, layout, label)
            except Exception:  # noqa: BLE001
                ERRORS.append(f"{label}: " + traceback.format_exc(limit=8))
                continue
            save(win, out, label)
            if win.roster is not None:
                win.roster.refresh()
                pump(app, 0.4)
                save(win.roster, out, label + "-roster")
            msg = win.statusBar().currentMessage()
            if msg.startswith(("Ошибка", "Error")):
                ERRORS.append(f"{label}: on the status bar: {msg}")
            if first:  # the menus and the windows: once is enough
                tour_menus(app, out, core, win)
                first = False
            close_window(app, core, win)
            print(f"{label}: {time.monotonic() - t0:.1f} s", flush=True)
    (out / "menus.txt").write_text("\n".join(MENUS), "utf-8")
    (out / "errors.txt").write_text("\n\n".join(ERRORS) + "\n" if ERRORS else "none\n",
                                    "utf-8")
    print(f"{len(ERRORS)} problems; {out}")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
