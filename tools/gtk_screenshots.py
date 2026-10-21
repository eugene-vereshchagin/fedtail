"""Render the GTK window with made-up data and save PNG screenshots, one per theme
given (all by default), light and dark.

    xvfb-run -a python3 tools/gtk_screenshots.py OUT_DIR [THEME ...]

The GTK twin of tools/screenshots.py (docs/GTK.md); the made-up world is a small one
of its own until the Qt tool's moves into a module both can use.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp(prefix="fedtail-gtk-shots-")
os.environ["XDG_CONFIG_HOME"] = str(Path(_tmp) / "config")
os.environ["XDG_DATA_HOME"] = str(Path(_tmp) / "data")

from fedtail import i18n  # noqa: E402
from fedtail.core import auth, config, paths  # noqa: E402
from fedtail.core.app import Core  # noqa: E402
from fedtail.core.view import View  # noqa: E402
from fedtail.frontends import themefile  # noqa: E402
from fedtail.frontends.gtk import theme as themes  # noqa: E402
from fedtail.frontends.gtk.bridge import Bridge  # noqa: E402
from fedtail.frontends.gtk.gi_setup import GLib, Gtk  # noqa: E402
from fedtail.frontends.gtk.window import MainWindow  # noqa: E402
from tests import fakes  # noqa: E402
from tests.fakes import ME, FakeApi, acct, status  # noqa: E402

KOT = acct("K", "kot@kot.example")
KOT["display_name"] = "Кот Учёный"
OSTAP = acct("O", "ostap@vivaldi.example")
OSTAP["display_name"] = "Остап"
NEWS = acct("N", "weather_news", bot=True)
NEWS["display_name"] = "Погода на побережье"


def world():
    w = fakes.World()
    mine = w.add(status("100", ME, minute=1, vis="public",
                        text="<p>Переезжаю с Drive2 на свою ноду. Кто уже, как оно?</p>"),
                 home=True)
    w.add(status("101", KOT, mine["id"], "ME", minute=3,
                 text="<p>@mira перед тем как менять — проверь, что <b>экспорт</b> "
                      "забирает и картинки.</p><blockquote><p>Кто уже, как оно?</p>"
                      "</blockquote><p>Я переехал, <a href=\"https://kot.example/a\">"
                      "вот заметка</a>.</p>"), home=True, mention=True)
    w.add(status("102", OSTAP, minute=8, vis="unlisted",
                 text="<p>Десять лет на Point, а руки всё помнят:</p><ul><li>#a3f — ответ"
                      "</li><li>! — рекомендация</li></ul>"), home=True)
    cw = status("103", KOT, minute=12, text="<p>Под катом.</p>")
    cw["spoiler_text"] = "спойлер про сериал"
    w.add(cw, home=True)
    w.add(status("104", NEWS, minute=20, vis="public",
                 text="<p>Сильный порывистый ветер до 20 м/с на побережье.</p>"), home=True)
    w.add(status("105", OSTAP, minute=25, text="<p>А <code>~~это~~</code> ~~зачёркнуто~~"
                                                "</p>"), home=True)
    return w


def pump(seconds):
    ctx = GLib.MainContext.default()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while ctx.pending():
            ctx.iteration(False)
        time.sleep(0.01)


def shoot(win, path):
    """The window as a PNG: GTK renders it into a texture, no window manager needed."""
    paintable = Gtk.WidgetPaintable.new(win)
    w, h = win.get_width(), win.get_height()
    snap = Gtk.Snapshot()
    paintable.snapshot(snap, w, h)
    node = snap.to_node()
    renderer = win.get_native().get_renderer()
    texture = renderer.render_texture(node, None)
    texture.save_to_png(str(path))


def run(out, theme_name, dark):
    tmp = Path(tempfile.mkdtemp(dir=_tmp))
    FakeApi.world = world()
    cfg, _w = config.validate({"feed": {"first_run_mark_read": False},
                               "ui": {"theme": theme_name, "frontend": "gtk",
                                      "start_lane": "home", "adwaita": "off"}})
    p = paths.resolve("shots", config=str(tmp / "c.toml"), data=str(tmp / "d"))
    auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
    core = Core(cfg, p, api_class=FakeApi)
    core._origin_json = lambda url: None
    Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", dark)
    view = View(core)
    win = MainWindow(None, core, view, Bridge(view), themes.apply(cfg))
    win.set_default_size(1000, 700)
    win.present()
    win.start()
    pump(1.0)
    core.poll_once()
    pump(1.5)
    name = f"gtk-{theme_name}-{'dark' if dark else 'light'}.png"
    shoot(win, out / name)
    win.destroy()
    core.shutdown()
    print(out / name)


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "out")
    out.mkdir(parents=True, exist_ok=True)
    names = sys.argv[2:] or sorted(p.stem for p in themefile.BUILTIN_DIR.glob("*.toml"))
    i18n.setup("ru")
    for name in names:
        for dark in (False, True):
            run(out, name, dark)
    return 0


if __name__ == "__main__":
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        sys.exit(subprocess.call(["xvfb-run", "-a", sys.executable] + sys.argv))
    sys.exit(main())
