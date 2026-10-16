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
from tests import fakes  # noqa: E402
from tests.fakes import ME, FakeApi, acct, status  # noqa: E402

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

KOT = acct("K", "kot@mastodon.ml")
KOT["display_name"] = "Кот Учёный"
ARSEN = acct("A", "arsen@gts.example")
ARSEN["display_name"] = "Арсен"
OSTAP = acct("O", "ostap@vivaldi.example")
OSTAP["display_name"] = "Остап"
NEWS = acct("N", "georgia_news", bot=True)
NEWS["display_name"] = "Новости Грузии"
AVATAR_COLORS = {"K": ("#d9c7a3", "К"), "A": ("#2f4f6f", "А"), "O": ("#5a3d5c", "О"),
                 "N": ("#7a3b2e", "Н"), "ME": ("#3b4a3f", "В")}
for a in (KOT, ARSEN, OSTAP, NEWS, ME):
    a["avatar_static"] = f"https://img.example/avatar/{a['id']}"


def _recent(w):
    """Give the made-up posts today's dates, so cards show times, not years."""
    from datetime import UTC, datetime, timedelta
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    for st in w.statuses.values():
        minute = int(st["created_at"][14:16])
        st["created_at"] = (now - timedelta(minutes=60 - minute)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z")
    for n in w.notifications:
        n["created_at"] = n["status"]["created_at"]


def world():
    w = fakes.World()
    t = lambda m: m  # minutes since 10:00 keep the order readable
    router = w.add(status("100", ME, minute=t(1), text="Роутер второй раз за неделю отвалился, "
                          "похоже, пора его менять. Кто что посоветует под OpenWrt, "
                          "чтобы без танцев?"), home=True)
    w.add(status("101", KOT, "100", "ME", minute=t(3), text="@veresk перед тем как менять — "
                 "протри контакты и поставь умную розетку на мониторинг. У меня ровно так же "
                 "было: дело оказалось в блоке питания."), home=True, mention=True)
    mine = w.add(status("102", ME, "101", "K", minute=t(5), text="@kot а розетку какую взял? "
                        "Чтобы без облака, сразу в Home Assistant."), home=True)
    w.add(status("103", KOT, mine["id"], "ME", minute=t(8), text="@veresk обычную на Zigbee, "
                 "прошитую. Облака там нет вообще."), home=True, mention=True)
    pic = status("104", ARSEN, minute=t(12), vis="public",
                 text="Есть в Грузии точки, откуда видно одновременно и Турцию, и Россию, и "
                      "весь Кавказ. Высота 2600 метров, дорога — только на полном приводе.")
    pic["media_attachments"] = [{"type": "image", "url": "https://img.example/full/mountains",
                                 "preview_url": "https://img.example/small/mountains",
                                 "description": "Горный хребет на закате",
                                 "meta": {"original": {"width": 1600, "height": 900}}}]
    pic["favourites_count"], pic["favourited"], pic["reblogs_count"] = 5, True, 1
    w.add(pic, home=True)
    w.add(status("105", ME, "104", "A", minute=t(14), text="@arsen с Шатили в ясную погоду "
                 "видно, да. Но дорогу размыло."), home=True)
    w.add(status("106", OSTAP, minute=t(18), vis="unlisted", text="Десять лет на Point, а "
                 "потом раз — и все разбежались кто куда. Хорошо, что хоть треды теперь снова "
                 "деревом."), home=True)
    w.add(status("107", NEWS, minute=t(20), vis="public", text="Сильный порывистый ветер "
                 "уже второй день на черноморском побережье. #georgia_news"), home=True)
    w.add(status("108", OSTAP, "100", "ME", minute=t(25), text="@veresk а я свой просто "
                 "перевернул вверх ногами — перестал греться. Десять лет работает."),
          home=True, mention=True)
    w.statuses["106"]["poll"] = {
        "id": "P1", "expired": False, "multiple": False, "voted": True, "own_votes": [0],
        "votes_count": 23, "voters_count": 23, "expires_at": "2099-01-01T12:00:00Z",
        "options": [{"title": "GoToSocial", "votes_count": 12},
                    {"title": "Mastodon", "votes_count": 7},
                    {"title": "обратно на Point", "votes_count": 4}]}
    w.requests = [OSTAP]
    router = w.statuses.get("100")
    for i, (kind, who) in enumerate((("favourite", KOT), ("favourite", ARSEN),
                                     ("favourite", OSTAP), ("reblog", ARSEN),
                                     ("follow", OSTAP)), 1):
        w.act(f"act{i}", kind, who, router if kind != "follow" else None, minute=i)
    w.lists = {"L1": {"title": "Новости", "exclusive": True, "members": {NEWS["id"]}},
               "L2": {"title": "Мемасики", "exclusive": True, "members": set()}}
    del router
    _recent(w)
    return w


def make_pixmap(url, _max_side=0):
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


def shoot(widget, out, name):
    path = Path(out) / f"{name}.png"
    widget.grab().save(str(path))
    print("saved", path)


def run(app, out, label, palette, theme_name, extras):
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
    cfg, _ = config.validate({"ui": {"theme": theme_name},
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
    win.select_lane("people")
    lane = win.lane_widgets["people"]
    lane.positioned = False
    lane.separator = None
    lane.refresh(force=True)
    pump(app, 2.0)  # the lane stands on "new below" by itself
    shoot(win, out, f"{label}-people")

    win.select_lane("comments")
    pump(app, 1.5)
    shoot(win, out, f"{label}-comments")

    win.on_link("fedtail:thread/102")
    pump(app, 1.5)
    shoot(win, out, f"{label}-thread")

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
        win.select_lane("people")
        pump(app, 0.5)
        pics = core.store.get_status("104")["media_attachments"]
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
        win.lane_widgets["people"].view.scroll_to("106", "top")
        pump(app, 1.0)
        shoot(win, out, f"{label}-poll")
        win.select_lane("activity")
        pump(app, 1.0)
        shoot(win, out, f"{label}-activity")
        win.open_search("o")
        pump(app, 1.2)
        shoot(win, out, f"{label}-search")
        win.close_tab(win.tabs.currentIndex())
        win.select_lane("people")
        from fedtail.frontends.qt.profile import ProfileDialog
        dlg = ProfileDialog(win)
        dlg.show()
        pump(app, 1.0)
        shoot(dlg, out, f"{label}-profile")
        dlg.reject()

    win.quitting = True
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
    for name in ("point", "juick", "juick-classic", "night", "paper", "contrast",
                 "pink", "nord", "solarized"):
        run(app, out, name, BREEZE_LIGHT, name, set())


if __name__ == "__main__":
    main()
