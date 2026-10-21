"""Render the real Qt window with made-up data and save PNG screenshots.

    QT_QPA_PLATFORM=offscreen python3 tools/screenshots.py OUT_DIR

CI runs this on every push and publishes the pictures to the `screenshots`
branch, so the look can be checked without running the app.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_tmp = tempfile.mkdtemp(prefix="fedtail-shots-")
os.environ["XDG_CONFIG_HOME"] = str(Path(_tmp) / "config")
os.environ["XDG_DATA_HOME"] = str(Path(_tmp) / "data")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPalette,
    QPixmap,
)
from PySide6.QtWidgets import QApplication  # noqa: E402

from fedtail import i18n  # noqa: E402
from fedtail.core import auth, config, paths  # noqa: E402
from fedtail.core.app import Core  # noqa: E402
from tests.fakes import FakeApi  # noqa: E402

BREEZE_LIGHT = {"Window": "#eff0f1", "Base": "#fcfcfc", "AlternateBase": "#f7f7f7",
                "Text": "#232629", "WindowText": "#232629", "Button": "#fcfcfc",
                "ButtonText": "#232629", "Highlight": "#3daee9", "HighlightedText": "#ffffff",
                "Link": "#2980b9", "PlaceholderText": "#6e7175", "Mid": "#bcc0c4",
                "ToolTipBase": "#f7f7f7", "ToolTipText": "#232629"}
BREEZE_DARK = {"Window": "#202326", "Base": "#141618", "AlternateBase": "#1d1f22",
               "Text": "#fcfcfc", "WindowText": "#fcfcfc", "Button": "#292c30",
               "ButtonText": "#fcfcfc", "Highlight": "#3daee9", "HighlightedText": "#fcfcfc",
               "Link": "#1d99f3", "PlaceholderText": "#8d9196", "Mid": "#4d5257",
               "ToolTipBase": "#292c30", "ToolTipText": "#fcfcfc"}

from tools.showcase import (  # noqa: E402 — the world every screenshot shows
    AVATAR_COLORS,
    world,
)


def make_pixmap(url, _max_side=0):
    url = url or ""
    if "/avatar/" in url:
        color, letter = AVATAR_COLORS.get(url.rsplit("/", 1)[1], ("#777", "?"))
        pm = QPixmap(88, 88)
        pm.fill(QColor(color))
        p = QPainter(pm)
        p.setPen(QColor("#ffffff"))
        f = QFont()
        f.setPixelSize(40)
        f.setBold(True)
        p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, letter)
        p.end()
        return pm
    pm = QPixmap(1600, 900)
    p = QPainter(pm)
    g = QLinearGradient(0, 0, 0, 900)
    for stop, col in ((0, "#cfd9e2"), (0.45, "#9fb2c3"), (0.7, "#5f7486"), (1, "#3d4c59")):
        g.setColorAt(stop, QColor(col))
    p.fillRect(QRectF(0, 0, 1600, 900), g)
    p.setBrush(QColor("#2c3843"))
    p.setPen(Qt.PenStyle.NoPen)
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPolygonF
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in
                             ((0, 900), (0, 620), (300, 420), (520, 560), (820, 300),
                              (1100, 520), (1350, 380), (1600, 560), (1600, 900))]))
    p.end()
    return pm


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


ERRORS = []
LOGGED = []


def shoot(widget, out, name):
    path = Path(out) / f"{name}.png"
    widget.grab().save(str(path))
    print("saved", path)
    win = widget.window()
    bar = getattr(win, "statusBar", None)
    msg = bar().currentMessage() if bar else ""
    if msg.startswith(("Ошибка", "Error")):  # a screenshot of an error is a bug found
        ERRORS.append(f"{name}: {msg}")


def run(app, out, label, palette, theme_name, extras, layout="single"):
    from fedtail.frontends.qt import theme as themes
    from fedtail.frontends.qt.bridge import Bridge
    from fedtail.frontends.qt.compose import Compose, save_image
    from fedtail.frontends.qt.window import MainWindow

    pal = QPalette()
    for role, col in palette.items():
        pal.setColor(getattr(QPalette.ColorRole, role), QColor(col))
    app.setPalette(pal)
    f = QFont("Noto Sans")
    f.setPointSize(10)
    app.setFont(f)

    FakeApi.world = world()
    cfg, _ = config.validate({"ui": {"theme": theme_name, "layout": layout},
                              "feed": {"first_run_mark_read": False}})
    data = Path(_tmp) / f"profile-{label}"
    p = paths.resolve(label, config=str(data / "c.toml"), data=str(data))
    auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
    core = Core(cfg, p, api_class=FakeApi)
    theme = themes.apply(app, cfg)
    bridge = Bridge(core)
    win = MainWindow(core, bridge, theme)
    win.images.get = lambda url, cb, *a, **k: cb(make_pixmap(url))
    win.tray = None
    win.resize(1280, 860)
    win.show()
    win.start()
    pump(app, 1.0)
    core.poll_once()
    # some of it is already read, so the "new below" divider shows
    core.mark_read(["100", "101", "102", "103"])
    win.select_lane("home")
    lane = win.lane_widgets["home"]
    lane.positioned = False
    lane.separator = None
    lane.refresh(force=True)
    pump(app, 2.0)  # the lane stands on "new below" by itself
    shoot(win, out, f"{label}-people")

    win.select_lane("replies")
    pump(app, 1.5)
    shoot(win, out, f"{label}-comments")

    win.on_link("fedtail:thread/102")
    pump(app, 1.5)
    shoot(win, out, f"{label}-thread")
    if win.roster is not None:  # ui.layout = "split": the roster window beside it
        win.roster.refresh()
        pump(app, 0.5)
        shoot(win.roster, out, f"{label}-roster")

    if "extras" in extras:
        pic = QImage(320, 200, QImage.Format.Format_RGB32)
        pic.fill(QColor("#7fa7c9"))
        dlg = Compose(win, core.store.get_status("103"), attach=[save_image(core, pic)])
        dlg.text.setPlainText("Блок питания берите с запасом, проверено.")
        dlg.show()
        pump(app, 0.5)
        shoot(dlg, out, f"{label}-compose")
        dlg.reject()
        win.close_tab(win.tabs.currentIndex())
        win.select_lane("home")
        pump(app, 0.5)
        pics = list(win.ctx.view.by_id("104").media)  # the model's Media
        win.show_images(pics, 0)
        pump(app, 0.8)
        shoot(win, out, f"{label}-viewer")
        from fedtail.frontends.qt.viewer import ImageOverlay
        for w in win.findChildren(ImageOverlay):
            w.close_viewer()
        win.find_bar.open()
        win.find_bar.edit.setText("кот")
        win.find_bar.search(jump=True)
        pump(app, 1.0)
        shoot(win, out, f"{label}-find")
        win.find_bar.close_bar()
        win.lane_widgets["home"].view.scroll_to("106", "top")
        pump(app, 1.0)
        shoot(win, out, f"{label}-poll")
        win.select_lane("activity")
        pump(app, 1.0)
        shoot(win, out, f"{label}-activity")
        win.on_link("fedtail:account/" + core.store.get_status("104")["account"]["id"])
        pump(app, 1.2)
        shoot(win, out, f"{label}-account")
        win.close_tab(win.tabs.currentIndex())
        win.open_search("o")
        pump(app, 1.2)
        shoot(win, out, f"{label}-search")
        win.close_tab(win.tabs.currentIndex())
        win.select_lane("home")
        from fedtail.frontends.qt.profile import ProfileDialog
        dlg = ProfileDialog(win)
        dlg.show()
        pump(app, 1.0)
        shoot(dlg, out, f"{label}-profile")
        dlg.reject()

    win.quitting = True
    if win.roster is not None:
        win.roster.close()
    win.hide()
    core.shutdown()
    win.deleteLater()
    pump(app, 0.3)


def icon_sheet(out):
    """The icon in every theme's colours at panel, launcher and big sizes,
    on light and dark backgrounds."""
    from fedtail.frontends import iconart, themefile
    names = themefile.available()
    sizes = [22, 48, 128]
    cell = sum(sizes) + 24 * (len(sizes) + 1)
    row_h = 128 + 40
    sheet = QImage(cell * 2, row_h * len(names), QImage.Format.Format_ARGB32)
    p = QPainter(sheet)
    tmp = Path(tempfile.mkdtemp())
    for r, name in enumerate(names):
        data, _w = themefile.load(name)
        c = iconart.colors(data.get("icon"), "#2a86c4", "#e8702a")
        f = tmp / f"{name}.svg"
        f.write_text(iconart.svg(c), "utf-8")
        icon = QIcon(str(f))
        for col, bg in enumerate(("#eff0f1", "#202326")):
            x0, y0 = col * cell, r * row_h
            p.fillRect(x0, y0, cell, row_h, QColor(bg))
            p.setPen(QColor("#888"))
            p.drawText(x0 + 8, y0 + 16, name)
            x = x0 + 24
            for size in sizes:
                p.drawPixmap(x, y0 + 28 + 128 - size, icon.pixmap(size, size))
                x += size + 24
    p.end()
    sheet.save(str(out / "icon.png"))


def main():
    import logging
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr,
                        format="%(levelname)s %(name)s: %(message)s")

    class Keep(logging.Handler):
        def emit(self, record):
            LOGGED.append(self.format(record))
    keep = Keep(logging.WARNING)
    keep.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(keep)
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "screenshots")
    out.mkdir(parents=True, exist_ok=True)
    i18n.setup("ru")
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    # offscreen Qt has no desktop integration: tell it where icon themes live
    QIcon.setThemeSearchPaths(["/usr/share/icons"] + QIcon.themeSearchPaths())
    QIcon.setThemeName("breeze")
    print("icons:", QIcon.themeName(), "go-home" if QIcon.hasThemeIcon("go-home") else "MISSING")
    icon_sheet(out)
    run(app, out, "light", BREEZE_LIGHT, "system", {"extras"})
    run(app, out, "dark", BREEZE_DARK, "system", set())
    run(app, out, "terminal", BREEZE_LIGHT, "terminal", set())
    run(app, out, "split", BREEZE_LIGHT, "system", set(), layout="split")
    for name in ("qip-retro", "qip-modern", "mra", "mra-blue", "mra-green",
                 "mra-violet", "psi"):
        run(app, out, name, BREEZE_LIGHT, name, set(), layout="split")
    for name in ("point", "juick", "juick-classic", "bnw", "night", "paper", "contrast",
                 "pink", "nord", "solarized"):
        run(app, out, name, BREEZE_LIGHT, name, set())
    # what went wrong goes next to the pictures (CI publishes the folder), and fails the run
    (out / "errors.txt").write_text("\n".join(ERRORS + LOGGED) + "\n" if ERRORS else "none\n")
    if ERRORS:
        print("errors on screen:\n  " + "\n  ".join(ERRORS), file=sys.stderr)


if __name__ == "__main__":
    main()
