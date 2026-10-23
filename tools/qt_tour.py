"""A walk through the Qt window on a fake server, saving what it sees: every theme in
the single window and (the messengers') in the split layout, every menu — ≡, its
submenus, the accounts, a post's ⋯ — with the list of what's in it, and every window
the ≡ menu opens (Silence, Scheduled, the server, the federation, help, people…).
Whatever goes wrong on the way — an exception, an error on the status bar, a warning in
the log — goes to errors.txt; menus.txt is the inventory of every menu.

Besides the ≡ menu, every menu the window has is opened: each button's that has one,
and each right click (the widgets that answer one get it, a couple of each kind).

    python3 tools/qt_tour.py OUT_DIR [--quick] [--native] [--maximized] [--pace 2]
                             [--scale 1.5] [--real[=PROFILE]]

--native: the desktop's own Qt platform (the real fonts, style and icons, windows flash
on the screen); without it, offscreen (nothing shows, the look is plainer).
--maximized: the window as big as the screen. --scale 1.5: the whole window at that
scale (QT_SCALE_FACTOR: a HiDPI screen, 125/150/200 % in the desktop's settings).
--pace: every wait that many times longer (a slow machine: pictures, icons, lanes
have time to come). --real: your own account, read-only, instead of the fake server
(tools/real.py)."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import real  # noqa: E402

NATIVE = "--native" in sys.argv
MAXIMIZED = "--maximized" in sys.argv
PACE = float(sys.argv[sys.argv.index("--pace") + 1]) if "--pace" in sys.argv else 1.0
SCALE = sys.argv[sys.argv.index("--scale") + 1] if "--scale" in sys.argv else ""
if SCALE:  # before Qt starts: the whole window drawn at that scale, as on a HiDPI screen
    os.environ["QT_SCALE_FACTOR"] = SCALE
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
if NATIVE:  # (tools/screenshots.py, imported below, would make it offscreen)
    os.environ["QT_QPA_PLATFORM"] = os.environ.get("QT_QPA_PLATFORM") or (
        "windows" if os.name == "nt" else
        "wayland" if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY")
        else "xcb")
else:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_tmp = tempfile.mkdtemp(prefix="fedtail-tour-")
REAL = real.snapshot(_tmp)  # before XDG_* point at the temporary folder
from tools import userthemes  # noqa: E402

OWN_THEMES = userthemes.bring(Path(_tmp) / "config")  # tested too, never published
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
LEAKS, LEAK_NOTES = [], []  # widgets alive after each window closed
SIZE_NOTES = []  # sizes.txt: every size, what it did
NATIVE_MENUS = []  # clicks whose menu went past the patched exec (closed by the guard)
CAUGHT = []  # menus that were exec()'d: kept here instead of waiting for a click
SEEN = set()  # (what was shot) — a menu with the same items once only
# the sizes are tried with these (a proportional font, a monospace one, the messengers)
SIZE_THEMES = ("system", "terminal", "bnw", "qip-retro", "mra")
SPLIT_THEMES = ("system", "qip-retro", "qip-modern", "mra", "mra-blue", "psi")


def pump(app, seconds):
    end = time.monotonic() + seconds * PACE
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def save(widget, out, name):
    try:
        widget.adjustSize() if isinstance(widget, QMenu) else None
        if widget.isVisible():
            pix = widget.grab()
        else:
            # a menu caught before it showed: on Windows grab() of a widget never shown
            # gives black (the night of 23.10: every menu a black box); render() paints
            # it on its own
            from PySide6.QtCore import Qt as _Qt
            from PySide6.QtGui import QPixmap
            widget.ensurePolished()
            pix = QPixmap(widget.size() * widget.devicePixelRatioF())
            pix.setDevicePixelRatio(widget.devicePixelRatioF())
            pix.fill(_Qt.GlobalColor.transparent)
            widget.render(pix)
        pix.save(str(Path(out) / f"{name}.png"))
    except Exception as e:  # noqa: BLE001
        ERRORS.append(f"{name}: can't grab: {e}")


def inventory(menu, title, depth=0, top=True):
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
            lines += inventory(sub, a.text(), depth + 1, False)
    if top:
        MENUS.append(f"== {title}\n" + "\n".join(lines) + "\n")
    return lines


def shoot_menu(menu, out, name):
    menu.aboutToShow.emit()
    key = tuple(a.text() for a in menu.actions())
    if key in SEEN:
        return
    SEEN.add(key)
    if not key:
        ERRORS.append(f"{name}: an empty menu")
    save(menu, out, name)
    inventory(menu, name)
    for i, a in enumerate(a for a in menu.actions() if a.menu() is not None):
        sub = a.menu()
        sub.aboutToShow.emit()
        save(sub, out, f"{name}-sub{i}")


def sweep(app, root, out, label):
    """Every menu under root: the buttons' (shown on a click) and the right clicks'
    (customContextMenuRequested, a point near the widget's corner; whatever menu that
    exec()s is caught). Two widgets of a kind at most: a lane has dozens of cards."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QAbstractButton, QWidget
    kinds = {}
    n = 0
    for b in root.findChildren(QAbstractButton):
        m = getattr(b, "menu", lambda: None)()
        if m is not None and b.isVisible():
            n += 1
            shoot_menu(m, out, f"{label}-btn{n}-{type(b).__name__}"
                       f"{'-' + b.objectName() if b.objectName() else ''}")
    for w in [root] + root.findChildren(QWidget):
        try:
            if w.contextMenuPolicy() != Qt.ContextMenuPolicy.CustomContextMenu or \
                    not w.isVisible():
                continue
        except RuntimeError:  # gone meanwhile: a right click before rebuilt it
            continue
        k = (type(w).__name__, w.objectName())
        if kinds.get(k, 0) >= 2:
            continue
        kinds[k] = kinds.get(k, 0) + 1
        del CAUGHT[:]
        before = {id(x) for x in app.topLevelWidgets() if x.isVisible()}
        guard = _modal_guard(app, f"right click on {k}")
        try:
            w.customContextMenuRequested.emit(QPoint(min(8, w.width() // 2),
                                                     min(8, w.height() // 2)))
        except Exception:  # noqa: BLE001
            ERRORS.append(f"right click on {k}: " + traceback.format_exc(limit=5))
        finally:
            guard.stop()
        for i, m in enumerate(list(CAUGHT)):
            shoot_menu(m, out, f"{label}-ctx-{k[0]}{'-' + k[1] if k[1] else ''}-{i}")
        for x in app.topLevelWidgets():  # a right click that opened a window: closed
            if x.isVisible() and id(x) not in before and not isinstance(x, QMenu):
                x.close()
    pump(app, 0.2)


def _modal_guard(app, what):
    """While a click is made: a window it exec()s (a question, a dialog) would wait
    for a person all night (the tour ran out of time so) — closed, and said."""
    from PySide6.QtCore import QTimer
    timer = QTimer()
    timer.setInterval(300)

    def close():
        # a menu shown by the C++ exec() itself (the patched one wasn't called: the
        # night of 23.10 every tour stood 1–1.5 h on a card's right click): kept for its
        # picture, as caught, and closed — the click returns
        from PySide6.QtWidgets import QMenu
        pops = [app.activePopupWidget()] + [
            # a menu shown without its grab (X11 on xvfb, your account's tour of 23.10:
            # an hour on a picture's right click) isn't the "active popup": any shown one
            x for x in app.topLevelWidgets() if isinstance(x, QMenu) and x.isVisible()]
        for pop in dict.fromkeys(p for p in pops if p is not None):
            if isinstance(pop, QMenu):
                CAUGHT.append(pop)
                NATIVE_MENUS.append(what)
            pop.close()
        w = app.activeModalWidget()
        if w is not None:
            ERRORS.append(f"{what}: opened a modal window ({type(w).__name__}) — closed")
            w.close()
            if hasattr(w, "reject"):
                w.reject()
    timer.timeout.connect(close)
    timer.start()
    return timer


# real screens, landscape and portrait (a monitor turned, a phone-like strip), small to 4K
SIZES = ((3840, 2160), (2560, 1440), (1920, 1080), (1600, 1200), (1366, 768),
         (1280, 1024), (1024, 768), (1080, 1920), (800, 600), (640, 480), (480, 860))
# and the window as a share of the screen it's on: maximized, a half tiled left, a
# quarter, three quarters, a half by height (a window under another)
SHARES = ((1.0, 1.0), (0.5, 1.0), (0.75, 0.75), (1.0, 0.5), (0.5, 0.5), (0.33, 1.0))


def too_wide(win):
    """Who holds the window wide: the deepest visible widgets that ask the most width
    (their minimum size hint), with the chain of their parents' names."""
    from PySide6.QtWidgets import QWidget
    rows = []
    for w in win.findChildren(QWidget):
        if not w.isVisible() or w.isWindow():
            continue
        need = max(w.minimumWidth(), w.minimumSizeHint().width())
        if need < 300:
            continue
        kids = [c for c in w.findChildren(QWidget) if c.isVisible() and
                max(c.minimumWidth(), c.minimumSizeHint().width()) >= need - 20]
        if kids:  # a child asks as much: that one is nearer the cause
            continue
        path, p = [], w
        while p is not None and p is not win and len(path) < 4:
            path.append(type(p).__name__ + (f"#{p.objectName()}" if p.objectName() else ""))
            p = p.parentWidget()
        rows.append((need, " < ".join(path)))
    rows.sort(reverse=True)
    return "; ".join(f"{n} px: {pth}" for n, pth in rows[:4]) or "(nobody in particular)"


def _in_scroll(w, top):
    """Inside a scroll area's contents (out of view there on purpose), or in a menu."""
    from PySide6.QtWidgets import QAbstractScrollArea
    p = w.parentWidget()
    while p is not None and p is not top:
        if isinstance(p, QAbstractScrollArea):
            return True
        p = p.parentWidget()
    return False


def layout_problems(win):
    """What a size does to the window: a widget sticking out of it, a button or a line
    of text cut (narrower than what it says needs), a picture button squeezed."""
    from PySide6.QtCore import QPoint, QRect, Qt
    from PySide6.QtWidgets import QAbstractButton, QLabel, QWidget
    out, seen = [], set()
    whole = win.rect()
    for w in win.findChildren(QWidget):
        if not w.isVisible() or w.width() <= 0 or w.height() <= 0 or _in_scroll(w, win):
            continue
        what = f"{type(w).__name__}{'#' + w.objectName() if w.objectName() else ''}"
        g = QRect(w.mapTo(win, QPoint(0, 0)), w.size())
        if not whole.contains(g, False) and g.intersects(whole) and \
                (g.right() - whole.right() > 2 or g.bottom() - whole.bottom() > 2):
            key = ("out", what)
            if key not in seen:
                seen.add(key)
                out.append(f"sticks out of the window: {what} {g.getRect()}")
        text = ""
        if isinstance(w, QAbstractButton):
            text = w.text()
            need = w.minimumSizeHint().width()
            if text and w.width() + 2 < need:
                key = ("button", what, text)
                if key not in seen:
                    seen.add(key)
                    out.append(f"button cut: {what} '{text}' {w.width()} < {need} px")
        elif isinstance(w, QLabel) and not w.wordWrap() and \
                w.textFormat() != Qt.TextFormat.RichText and w.pixmap().isNull():
            text = QLabel.text(w)  # what is shown (an elided label: with its "…")
            if text and "<" not in text and "\n" not in text:
                need = w.fontMetrics().horizontalAdvance(text)
                if need > w.contentsRect().width() + 3:
                    key = ("label", what, text)
                    if key not in seen:
                        seen.add(key)
                        out.append(f"text cut: {what} '{text[:40]}' needs {need} px, "
                                   f"has {w.contentsRect().width()}")
    return out


def sizes(app, out, win, label):
    """The window at the sizes of real screens (and a narrow one), a screenshot and
    what each did to the layout; then its edge dragged as a hand does, timed."""
    from PySide6.QtCore import QSize
    lines = []
    was_max = win.isMaximized()
    if was_max:
        win.showNormal()
        pump(app, 0.3)
    screen = win.screen().availableGeometry()
    asked = [(w, h, f"{w}x{h}") for w, h in SIZES] + [
        (int(screen.width() * fw), int(screen.height() * fh),
         f"{int(fw * 100)}x{int(fh * 100)}pct") for fw, fh in SHARES]
    lines.append(f"{label}: the screen {screen.width()}×{screen.height()} (logical px)"
                 + (f", scale {SCALE}" if SCALE else ""))
    for w, h, tag in asked:
        win.resize(w, h)
        pump(app, 0.6)
        got = win.size()
        name = f"size-{label}-{tag}"
        save(win, out, name)
        probs = layout_problems(win)
        note = "" if got == QSize(w, h) else \
            f" — the window would not go below {got.width()}×{got.height()}"
        lines.append(f"{label} {tag} = {w}×{h}{note}: {len(probs)} problems")
        lines += ["    " + p for p in probs[:25]]
        if got.width() > w and w >= 800:
            ERRORS.append(f"{name}: the window can't be {w} px wide (it stays "
                          f"{got.width()}): too wide — " + too_wide(win))
        for p in probs:
            if w >= 1024:  # at a real screen's size nothing should be cut
                ERRORS.append(f"{name}: {p}")
    # the edge dragged: 640 ↔ 1600, a step a frame; the slowest step is what is felt
    worst, steps, t0 = 0.0, 0, time.monotonic()
    for x in list(range(1600, 640, -32)) + list(range(640, 1601, 32)):
        a = time.monotonic()
        win.resize(x, 900)
        app.processEvents()
        worst = max(worst, time.monotonic() - a)
        steps += 1
    lines.append(f"{label} drag the edge 1600↔640: {steps} steps in "
                 f"{time.monotonic() - t0:.1f} s, the slowest {worst * 1000:.0f} ms")
    if worst > 0.25:
        ERRORS.append(f"{label}: dragging the window's edge stops for {worst * 1000:.0f} ms")
    # and the bottom edge: 1100 ↔ 360 high (a lane's end, the input line, the dock)
    worst, steps, t0 = 0.0, 0, time.monotonic()
    for y in list(range(1100, 360, -24)) + list(range(360, 1101, 24)):
        a = time.monotonic()
        win.resize(1280, y)
        app.processEvents()
        worst = max(worst, time.monotonic() - a)
        steps += 1
    win.resize(1280, 360)
    pump(app, 0.4)
    save(win, out, f"size-{label}-1280x360")
    probs = layout_problems(win)
    lines.append(f"{label} drag the bottom 1100↔360: {steps} steps in "
                 f"{time.monotonic() - t0:.1f} s, the slowest {worst * 1000:.0f} ms; "
                 f"at 360 high: {len(probs)} problems")
    lines += ["    " + p for p in probs[:25]]
    if worst > 0.25:
        ERRORS.append(f"{label}: dragging the window's bottom stops for "
                      f"{worst * 1000:.0f} ms")
    split = getattr(win, "split", None)
    if split is not None and split.count() > 1 and split.widget(0).isVisible():
        total = sum(split.sizes())
        worst, t0 = 0.0, time.monotonic()
        for x in list(range(180, 480, 10)) + list(range(480, 179, -10)):
            a = time.monotonic()
            split.setSizes([x, total - x])
            app.processEvents()
            worst = max(worst, time.monotonic() - a)
        lines.append(f"{label} drag the sidebar 180↔480: the slowest step "
                     f"{worst * 1000:.0f} ms")
    if was_max or MAXIMIZED:
        win.showMaximized()
    else:
        win.resize(1280, 860)
    pump(app, 0.5)
    SIZE_NOTES.extend(lines + [""])


def catch_menus():
    """QMenu.exec shows the menu and waits for a click: here it is kept and returns at
    once (nothing chosen)."""
    def exec_(menu, *a, **k):
        CAUGHT.append(menu)
        return None
    QMenu.exec = exec_
    QMenu.exec_ = exec_


def closing_modals(app, out, name, fn):
    """Call fn; whatever window it opens — modal (exec) or not — is saved and closed."""
    from PySide6.QtWidgets import QDialog
    before = {id(w) for w in app.topLevelWidgets() if w.isVisible()}
    # a panel set inside the window (help, ui.panels = "inside") is no top-level window
    inside = {id(w) for w in app.allWidgets() if isinstance(w, QDialog) and w.isVisible()}
    shot = []

    def close_modal():
        w = app.activeModalWidget() or app.activePopupWidget()
        if w is not None:
            save(w, out, name)
            sweep(app, w, out, name)
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
                sweep(app, w, out, name)
                shot.append(1)
            w.close()
    for w in app.allWidgets():
        if isinstance(w, QDialog) and w.isVisible() and id(w) not in inside:
            if not shot:
                save(w.window(), out, name)
                sweep(app, w, out, name)
                shot.append(1)
            w.close()
    if not shot and name == "compose":  # the editor inside the window (ui.compose)
        w = app.activeWindow()
        if w is not None:
            save(w, out, name)
            shot.append(1)
    if not shot and not name.startswith("tab-") and name != "compose":
        ERRORS.append(f"{name}: nothing opened")
    pump(app, 0.2)


def make_window(app, theme_name, layout, label):
    from fedtail.frontends.qt import theme as themes
    from fedtail.frontends.qt.bridge import Bridge
    from fedtail.frontends.qt.window import MainWindow
    ui = {"theme": theme_name, "layout": layout}
    if REAL:
        cfg = real.config(REAL, ui)
        core = real.core(REAL, cfg)
    else:
        FakeApi.world = shots.world()
        cfg, _ = config.validate({"ui": ui, "feed": {"first_run_mark_read": False}})
        data = Path(_tmp) / f"profile-{label}"
        p = paths.resolve(label, config=str(data / "c.toml"), data=str(data))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(cfg, p, api_class=FakeApi)
        core._origin_json = lambda url: None
    theme = themes.apply(app, cfg)
    win = MainWindow(core, Bridge(core), theme)
    if not REAL:
        win.images.get = lambda url, cb, *a, **k: cb(shots.make_pixmap(url))
    win.tour_tray = win.tray
    if win.tray is not None:
        win.tray.hide()
    win.tray = None
    if MAXIMIZED:
        win.showMaximized()
    else:
        win.resize(1280, 860)
        win.show()
    win.start()
    pump(app, 3.0 if REAL else 1.0)
    core.poll_once()
    pump(app, 3.0 if REAL else 1.0)
    win.select_lane("home" if "home" in win.lane_order else win.lane_order[0])
    pump(app, 4.0 if REAL else 1.5)
    return core, win


def census(app):
    from collections import Counter
    return Counter(type(w).__name__ for w in app.allWidgets())


def close_window(app, core, win, label=""):
    win.quitting = True
    if getattr(win, "roster", None) is not None:
        win.roster.close()
    win.hide()
    core.shutdown()
    win.deleteLater()
    pump(app, 0.3)
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    pump(app, 0.2)
    # a window closed: its widgets gone with it? Whatever stays is a leak — and Qt
    # restyles every widget alive at each theme tried, so a leak slows that down too
    now = census(app)
    if LEAKS:
        grew = now - LEAKS[0][1]
        LEAK_NOTES.append(f"after {label}: {sum(now.values())} widgets alive "
                          f"(+{sum(grew.values())} since the first window closed) — "
                          + ", ".join(f"{k} +{v}" for k, v in grew.most_common(8)))
    LEAKS.append((label, now))


def tour_menus(app, out, core, win):
    """The ≡ menu and all it opens, the accounts, a post's ⋯."""
    shoot_menu(win._app_menu(), out, "menu-main")
    shoot_menu(win.accounts_menu(), out, "menu-accounts")
    if win.tour_tray is not None and win.tour_tray.contextMenu() is not None:
        shoot_menu(win.tour_tray.contextMenu(), out, "menu-tray")
    sweep(app, win, out, "main")
    if getattr(win, "roster", None) is not None:
        sweep(app, win.roster, out, "roster")
    from fedtail.frontends.qt.card import PostRow
    cards = [c for c in win.findChildren(PostRow) if c.isVisible()]
    if not cards:  # the sweep's clicks may have left another lane or tab in front
        win.select_lane("home" if "home" in win.lane_order else win.lane_order[0])
        win.tabs.setCurrentIndex(0)
        pump(app, 1.5)
        cards = [c for c in win.findChildren(PostRow) if c.isVisible()]
    if cards:
        menu = cards[0].ensure_menu()
        if menu is not None:
            shoot_menu(menu, out, "menu-post")
    else:
        ERRORS.append("no post card on screen for the ⋯ menu")
    from fedtail.frontends.qt.silence import SilenceDialog
    for name, fn in (("tab-profile", lambda: win.open_account(core.me["id"])),
                     ("dlg-silence", lambda: SilenceDialog(win, "filters").exec()),
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
            sweep(app, win.tabs.currentWidget(), out, name)
            win.close_tab(win.tabs.currentIndex())
            pump(app, 0.3)


def write_out(out, done=False):
    """What the tour found so far, on disk: after each window too — a tour stopped by
    the self-check's clock (the night of 23.10: all of them) still leaves its menus,
    sizes and errors, not only its pictures."""
    errors = list(ERRORS)
    (out / "menus.txt").write_text("\n".join(MENUS), "utf-8")
    (out / "sizes.txt").write_text("\n".join(SIZE_NOTES), "utf-8")
    (out / "leaks.txt").write_text("\n".join(LEAK_NOTES) + "\n", "utf-8")
    if NATIVE_MENUS:
        (out / "native-menus.txt").write_text(
            "menus shown past the patched QMenu.exec (closed by the guard):\n"
            + "\n".join(sorted(set(NATIVE_MENUS))) + "\n", "utf-8")
    if len(LEAKS) > 3:
        grew = sum((LEAKS[-1][1] - LEAKS[0][1]).values())
        per = grew / (len(LEAKS) - 1)
        if per > 50:
            errors.append(f"leak: {per:.0f} widgets stay alive after each window is "
                          f"closed ({grew} over {len(LEAKS) - 1} windows; leaks.txt)")
    if REAL:  # what the tool's clicks would have sent: stopped on purpose
        errors = [e for e in errors if real.READ_ONLY not in e]
    if not done:
        errors.append("(unfinished: the tour is still going, or was stopped here)")
    (out / "errors.txt").write_text("\n\n".join(errors) + "\n" if errors else "none\n",
                                    "utf-8")


def main():
    import faulthandler  # stuck (selfcheck's time runs out): where, every 10 minutes
    faulthandler.dump_traceback_later(600, repeat=True)
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
    catch_menus()
    app = QApplication.instance() or QApplication([])
    from fedtail.frontends.qt import translate_qt
    translate_qt(app)
    if not NATIVE:
        app.setStyle("Fusion")
    from fedtail.frontends import themefile
    themes = ("system", "point", "qip-retro") if quick else tuple(themefile.available())
    first = True
    first_sizes = True
    for name in themes:
        split = name in SPLIT_THEMES or name in OWN_THEMES
        for layout in ("single",) + (("split",) if split else ()):
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
            if msg.startswith(("Ошибка", "Error")) and real.READ_ONLY not in msg:
                ERRORS.append(f"{label}: on the status bar: {msg}")
            if first:  # the menus and the windows: once is enough
                tour_menus(app, out, core, win)
                write_out(out)
                first = False
            if name in SIZE_THEMES or (quick and first_sizes):
                first_sizes = False
                sizes(app, out, win, label)
            elif win.roster is not None and layout == "split":
                sweep(app, win.roster, out, label + "-roster")
            close_window(app, core, win, label)
            write_out(out)
            print(f"{label}: {time.monotonic() - t0:.1f} s", flush=True)
    write_out(out, done=True)
    print(f"{len(ERRORS)} problems; {out}")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
