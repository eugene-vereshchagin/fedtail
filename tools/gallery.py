"""The pictures for the site's gallery and the docs: every interface of fedtail on the
same made-up world (tools/showcase.py) — Qt in its themes and layouts, a thread, the
editor, the picture viewer, the menu, the messengers' two windows side by side; GTK
light and dark; the terminal; the web on a desktop and a phone. Built-in themes only:
your own are tested by the other tools, never published.

    python3 tools/gallery.py OUT_DIR                  # all it can here
    python3 tools/gallery.py OUT_DIR --only qt,web    # some: qt gtk tui web

OUT_DIR gets the PNGs and gallery.toml — for each picture its interface, its title and
a line about it in Russian and English, in the gallery's order (the site and the docs
read that). Qt runs on the desktop's own platform when there is one (the real fonts).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SIZE = (1280, 800)

# (file, interface, title ru, title en, line ru, line en) — the gallery's order
PICTURES = [
    ("qt-system", "Qt", "KDE, как дома", "At home in KDE",
     "Тема system: цвета, шрифты и значки рабочего стола; деление «дальше новое».",
     "The system theme: the desktop's colours, fonts and icons; the \"new below\" mark."),
    ("qt-night", "Qt", "Ночь", "Night", "Тёмная тема со своими значками.",
     "A dark theme with its own icons."),
    ("qt-point", "Qt", "Как на Point", "Like Point",
     "Тема point: point.im десятых годов.", "The point theme: point.im of the 2010s."),
    ("qt-terminal", "Qt", "Терминал", "Terminal", "Зелёное на чёрном, моноширинное.",
     "Green on black, monospace."),
    ("qt-thread", "Qt", "Тред деревом", "A thread as a tree",
     "Ответы под ответами, как на Point.", "Replies under replies, as on Point."),
    ("qt-columns", "Qt", "Ленты рядом", "Lanes side by side",
     "Раскладка columns: несколько лент колонками.", "The columns layout."),
    ("qt-compose", "Qt", "Новый пост", "Writing",
     "Редактор: Markdown, картинки, кто увидит.", "The editor: Markdown, pictures, who sees it."),
    ("qt-viewer", "Qt", "Картинки", "Pictures", "Просмотр поверх окна.",
     "The viewer over the window."),
    ("qt-menu", "Qt", "Меню", "The menu", "Всё, что не помещается в кнопки.",
     "All that doesn't fit the buttons."),
    ("qt-qip-retro", "Qt", "Как в QIP", "Like QIP",
     "Раскладка split: список контактов и окно разговора, тема qip-retro.",
     "The split layout: the roster and a conversation window, the qip-retro theme."),
    ("qt-mra", "Qt", "Как в Агенте", "Like the Agent",
     "Та же раскладка в теме mra.", "The same layout in the mra theme."),
    ("gtk-light", "GTK", "GTK, светлая", "GTK, light", "Для GNOME и всех, кто на GTK.",
     "For GNOME and everyone on GTK."),
    ("gtk-dark", "GTK", "GTK, тёмная", "GTK, dark", "Тёмный вариант рабочего стола.",
     "The desktop's dark variant."),
    ("gtk-nord", "GTK", "GTK, nord", "GTK, nord", "Темы те же, что в Qt.",
     "The same themes as in Qt."),
    ("tui-home", "TUI", "В терминале", "In a terminal",
     "Textual: ленты, клавиши, картинки прямо в терминале.",
     "Textual: lanes, keys, pictures right in the terminal."),
    ("tui-thread", "TUI", "Тред в терминале", "A thread in a terminal",
     "Тот же тред деревом.", "The same thread, as a tree."),
    ("web-desktop", "web", "В браузере", "In a browser",
     "Веб-интерфейс: для другого компьютера в доме.",
     "The web interface: for another computer in the house."),
    ("web-dark", "web", "В браузере, тёмный", "In a browser, dark",
     "Подстраивается под тему системы.", "Follows the system's theme."),
    ("web-phone", "web", "С телефона", "From a phone", "Та же страница на телефоне.",
     "The same page on a phone."),
]


def fresh_env(tag):
    tmp = Path(tempfile.mkdtemp(prefix=f"fedtail-gallery-{tag}-"))
    os.environ["XDG_CONFIG_HOME"] = str(tmp / "config")
    os.environ["XDG_DATA_HOME"] = str(tmp / "data")
    return tmp


def make_core(tmp, ui, label):
    from fedtail.core import auth, config, paths
    from fedtail.core.app import Core
    from tests.fakes import FakeApi
    from tools import showcase
    FakeApi.world = showcase.world()
    cfg, _ = config.validate({"ui": ui, "feed": {"first_run_mark_read": False}})
    p = paths.resolve(label, config=str(tmp / label / "c.toml"), data=str(tmp / label))
    auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
    core = Core(cfg, p, api_class=FakeApi)
    core._origin_json = lambda url: None
    return core


# ---- Qt ------------------------------------------------------------------------------------
def part_qt(out):
    native = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) or \
        os.name == "nt" or sys.platform == "darwin"
    if not native:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    tmp = fresh_env("qt")
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication

    from fedtail import i18n
    from fedtail.frontends.qt import theme as themes
    from fedtail.frontends.qt import translate_qt
    from fedtail.frontends.qt.bridge import Bridge
    from fedtail.frontends.qt.window import MainWindow
    from tools import showcase
    i18n.setup("ru")
    app = QApplication.instance() or QApplication([])
    translate_qt(app)

    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)

    def pixmap(url):
        pm = QPixmap()
        pm.loadFromData(showcase.picture_png(url))
        return pm

    def window(theme, layout="single"):
        core = make_core(tmp, {"theme": theme, "layout": layout}, f"{theme}-{layout}")
        win = MainWindow(core, Bridge(core), themes.apply(app, core.cfg))
        win.images.get = lambda url, cb, *a, **k: cb(pixmap(url))
        if win.tray is not None:
            win.tray.hide()
        win.tray = None
        win.resize(*SIZE)
        win.show()
        win.start()
        pump(1.0)
        core.poll_once()
        core.mark_read(["100", "101", "102", "103"])  # the "new below" mark shows
        win.select_lane("home")
        lane = win.lane_widgets.get("home")
        if lane is not None:
            lane.positioned = False
            lane.separator = None
            lane.refresh(force=True)
        pump(2.0)
        return core, win

    def close(core, win):
        win.quitting = True
        if win.roster is not None:
            win.roster.close()
        win.hide()
        core.shutdown()
        win.deleteLater()
        pump(0.3)

    def save(pm, name):
        pm.save(str(out / f"{name}.png"))
        print("saved", name, flush=True)

    def backdrop(parts, gap=24, pad=32):
        """Windows side by side on a quiet backdrop (two windows, a window and its
        menu): [(pixmap, (x, y)) or pixmap]."""
        placed, x = [], pad
        for p in parts:
            if isinstance(p, tuple):
                placed.append(p)
            else:
                placed.append((p, (x, pad)))
                x += p.width() + gap
        w = max(pos[0] + pm.width() for pm, pos in placed) + pad
        h = max(pos[1] + pm.height() for pm, pos in placed) + pad
        canvas = QPixmap(w, h)
        p = QPainter(canvas)
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor("#3a4452"))
        g.setColorAt(1, QColor("#1f252e"))
        p.fillRect(canvas.rect(), g)
        for pm, pos in placed:
            p.drawPixmap(QPoint(*pos), pm)
        p.end()
        return canvas

    for theme, name in (("system", "qt-system"), ("night", "qt-night"),
                        ("point", "qt-point"), ("terminal", "qt-terminal")):
        core, win = window(theme)
        save(win.grab(), name)
        if theme == "system":
            win.on_link("fedtail:thread/102")
            pump(1.5)
            save(win.grab(), "qt-thread")
            win.close_tab(win.tabs.currentIndex())
            win.select_lane("home")
            pump(0.5)
            from fedtail.frontends.qt.compose import Compose
            dlg = Compose(win, core.store.get_status("103"))
            dlg.text.setPlainText("Блок питания берите **с запасом**, проверено. #железо")
            dlg.show()
            pump(0.6)
            save(backdrop([win.grab(), (dlg.grab(), (220, 140))]), "qt-compose")
            dlg.reject()
            pics = list(win.ctx.view.by_id("104").media)
            win.show_images(pics, 0)
            pump(0.8)
            save(win.grab(), "qt-viewer")
            from fedtail.frontends.qt.viewer import ImageOverlay
            for w in win.findChildren(ImageOverlay):
                w.close_viewer()
            menu = win._app_menu()
            menu.aboutToShow.emit()
            menu.adjustSize()
            save(backdrop([win.grab(), (menu.grab(), (32 + 200, 32 + 56))]), "qt-menu")
            menu.deleteLater()
        close(core, win)
    core, win = window("system", "columns")
    win.resize(1500, 820)
    pump(1.0)
    save(win.grab(), "qt-columns")
    close(core, win)
    for theme, name in (("qip-retro", "qt-qip-retro"), ("mra", "qt-mra")):
        core, win = window(theme, "split")
        win.resize(980, 720)
        if win.roster is not None:
            win.roster.refresh()
            win.roster.resize(300, 720)
            pump(0.6)
            save(backdrop([win.roster.grab(), win.grab()]), name)
        close(core, win)
    del Qt


# ---- GTK -----------------------------------------------------------------------------------
def part_gtk(out):
    from fedtail import i18n
    from tools import gtk_screenshots as g
    i18n.setup("ru")
    tmp = Path(tempfile.mkdtemp(prefix="fedtail-gallery-gtk-"))
    g.run(tmp, "system", False)
    g.run(tmp, "system", True)
    g.run(tmp, "nord", True)
    for src, name in (("gtk-system-light.png", "gtk-light"), ("gtk-system-dark.png", "gtk-dark"),
                      ("gtk-nord-dark.png", "gtk-nord")):
        if (tmp / src).exists():
            (out / f"{name}.png").write_bytes((tmp / src).read_bytes())
            print("saved", name, flush=True)


# ---- the terminal -------------------------------------------------------------------------
def part_tui(out):
    import asyncio
    from concurrent.futures import Future
    tmp = fresh_env("tui")
    from fedtail import i18n
    from fedtail.frontends.tui.app import FedtailApp, ThreadScreen
    from tools import showcase
    i18n.setup("ru")
    core = make_core(tmp, {}, "tui")

    async def walk():
        app = FedtailApp(core)

        def media(url):
            f = Future()
            f.set_result(showcase.picture_png(url))
            return f
        app.core.media_bytes = media
        async with app.run_test(size=(132, 40)) as pilot:
            core.poll_once()
            for _ in range(60):
                await pilot.pause(0.1)
                if app.lane is not None:
                    break
            await pilot.pause(1.5)
            app.save_screenshot("tui-home.svg", str(out))
            posts = app.query_one("#posts")
            posts.focus()
            ids = [getattr(getattr(i, "entry", None), "id", "") for i in posts.children]
            posts.index = ids.index("102") if "102" in ids else 0
            await pilot.press("enter")
            for _ in range(60):
                await pilot.pause(0.1)
                if isinstance(app.screen, ThreadScreen):
                    break
            await pilot.pause(1.0)
            app.save_screenshot("tui-thread.svg", str(out))
            await pilot.press("escape")
            await pilot.press("q")
    asyncio.run(walk())
    core.shutdown()
    svg_to_png(out, ["tui-home", "tui-thread"])


def svg_to_png(out, names):
    """The terminal's SVGs as PNGs, through a browser (Playwright); without one the
    SVGs stay (a browser opens them, the site can show them as they are)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("no Playwright: the terminal's pictures stay SVG", flush=True)
        return
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": 1400, "height": 1000}, device_scale_factor=2)
        for n in names:
            svg = out / f"{n}.svg"
            if not svg.exists():
                continue
            page.goto(svg.resolve().as_uri())
            page.locator("svg").first.screenshot(path=str(out / f"{n}.png"))
            print("saved", n, flush=True)
        b.close()


# ---- the web --------------------------------------------------------------------------------
def part_web(out):
    import threading
    tmp = fresh_env("web")
    from playwright.sync_api import sync_playwright

    from fedtail import i18n
    from fedtail.frontends.web import server as web
    from tools import showcase
    i18n.setup("ru")
    core = make_core(tmp, {}, "web")
    core.connect().result()
    core.poll_once()
    core.mark_read(["100", "101", "102", "103"])
    key = web.load_key(core.paths.data_dir)
    srv = web.make_server(core, "127.0.0.1", 0, key)
    srv.handle_error = lambda *a: None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            for name, size, scheme, scale in (("web-desktop", SIZE, "light", 1.5),
                                              ("web-dark", SIZE, "dark", 1.5),
                                              ("web-phone", (390, 844), "light", 3)):
                page = b.new_page(viewport={"width": size[0], "height": size[1]},
                                  device_scale_factor=scale, color_scheme=scheme)
                page.route(lambda url: not url.startswith(base),
                           lambda route: route.fulfill(status=200, content_type="image/png",
                                                       body=showcase.picture_png(
                                                           route.request.url)))
                page.goto(base + "/?k=" + key)
                page.wait_for_selector("#posts article", timeout=15000)
                page.wait_for_timeout(1200)
                page.screenshot(path=str(out / f"{name}.png"))
                print("saved", name, flush=True)
                page.close()
            b.close()
    finally:
        srv.shutdown()
        core.shutdown()


# ---- all of it ------------------------------------------------------------------------------
def manifest(out):
    lines = ["# fedtail's gallery: written by tools/gallery.py, read by the site and the docs",
             "# (the order is the gallery's)", ""]
    for name, ui, tr, te, lr, le in PICTURES:
        f = next((out / f"{name}.{ext}" for ext in ("png", "svg")
                  if (out / f"{name}.{ext}").exists()), None)
        if f is None:
            continue
        q = lambda s: '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'  # noqa: E731
        lines += ["[[picture]]", f"file = {q(f.name)}", f"ui = {q(ui)}",
                  f"title_ru = {q(tr)}", f"title_en = {q(te)}",
                  f"text_ru = {q(lr)}", f"text_en = {q(le)}", ""]
    (out / "gallery.toml").write_text("\n".join(lines), "utf-8")


PARTS = {"qt": part_qt, "gtk": part_gtk, "tui": part_tui, "web": part_web}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(args[0] if args else "gallery").resolve()
    out.mkdir(parents=True, exist_ok=True)
    if "--part" in sys.argv:  # one interface, in a process of its own
        PARTS[sys.argv[sys.argv.index("--part") + 1]](out)
        return 0
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv \
        else [p for p in PARTS if not (p == "gtk" and os.name == "nt")]  # no GTK there
    env = dict(os.environ, PYTHONUTF8="1", PYTHONPATH=str(ROOT) + os.pathsep +
               os.environ.get("PYTHONPATH", ""))
    failed = []
    for part in only:
        cmd = [sys.executable, __file__, str(out), "--part", part]
        if part == "gtk" and not (os.environ.get("DISPLAY") or
                                  os.environ.get("WAYLAND_DISPLAY")) and os.name != "nt":
            cmd = ["xvfb-run", "-a"] + cmd
        print(f"→ {part}", flush=True)
        if subprocess.call(cmd, cwd=ROOT, env=env) != 0:
            failed.append(part)
            print(f"  {part}: failed (or not installed here)", flush=True)
    manifest(out)
    print(f"{out}: " + ", ".join(sorted(p.name for p in out.glob("*.png"))))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
