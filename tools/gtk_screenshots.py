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
    for a in (KOT, OSTAP, NEWS, ME):
        a["avatar_static"] = f"https://example.test/a/{a['id']}.png"
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
    pic = status("104", KOT, minute=20, vis="public",
                 text="<p>Сильный порывистый ветер до 20 м/с на побережье.</p>")
    pic["media_attachments"] = [{"type": "image", "url": "https://example.test/m/sea.png",
                                 "preview_url": "https://example.test/m/sea_s.png",
                                 "description": "Волны у причала"}]
    w.add(pic, home=True)
    w.add(status("105", OSTAP, minute=25, text="<p>А <code>~~это~~</code> ~~зачёркнуто~~"
                                                "</p>"), home=True)
    return w


def png(w, h, rgb):
    """A plain PNG of one colour (the made-up avatars and pictures), no Pillow needed."""
    import struct
    import zlib
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + \
            struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


FACES = {"K": (0xd9, 0xc7, 0xa3), "O": (0x5a, 0x3d, 0x5c), "N": (0x2f, 0x6f, 0x8f),
         "ME": (0x8a, 0x3c, 0x3c)}


def fake_media(url):
    """View.media_bytes without the network: a face per person, a picture per post."""
    from concurrent.futures import Future
    f = Future()
    key = url.rsplit("/", 1)[-1].split(".")[0]
    if key in FACES:
        f.set_result(png(48, 48, FACES[key]))
    else:
        f.set_result(png(320, 180, (0x6f, 0x9a, 0x6a)))
    return f


class _Answer:
    """A streamed HTTP answer, as core.remote reads one."""
    is_redirect = False

    def __init__(self, data):
        self.data = data
        self.headers = {"Content-Type": "image/png"}

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, _size):
        yield self.data

    def close(self):
        pass


def fake_get(url, timeout=None, **_kw):
    return _Answer(fake_media(url).result())


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


def run(out, theme_name, dark, extras=False, layout="single"):
    tmp = Path(tempfile.mkdtemp(dir=_tmp))
    FakeApi.world = world()
    cfg, _w = config.validate({"feed": {"first_run_mark_read": False},
                               "ui": {"theme": theme_name, "frontend": "gtk",
                                      "start_lane": "home", "adwaita": "off",
                                      "layout": layout}})
    p = paths.resolve("shots", config=str(tmp / "c.toml"), data=str(tmp / "d"))
    auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
    core = Core(cfg, p, api_class=FakeApi)
    core._origin_json = lambda url: None
    Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", dark)
    view = View(core)
    view.media_bytes = fake_media
    win = MainWindow(None, core, view, Bridge(view), themes.apply(cfg))
    win.images.http.get = fake_get  # the picture cache: no network either
    win.set_default_size(1000, 700)
    win.present()
    win.start()
    pump(1.0)
    core.poll_once()
    pump(1.5)
    name = f"gtk-{theme_name}-{'dark' if dark else 'light'}" + \
        ("" if layout == "single" else f"-{layout}") + ".png"
    shoot(win, out / name)
    lane = win.lane_views.get("home")
    if lane is not None:  # and the lane's end: the picture, the newest posts
        lane.adj.set_value(lane.adj.get_upper())
        pump(0.6)
        shoot(win, out / name.replace(".png", "-end.png"))
    if extras:
        shoot_extras(win, out, name.replace(".png", ""))
    if win.roster is not None:  # the split layout: the roster beside it
        shoot(win.roster, out / name.replace(".png", "-roster.png"))
        win.quitting = True
    win.close()
    win.destroy()
    core.shutdown()
    print(out / name)


def shoot_extras(win, out, stem):
    """The rest of the window, for one theme: the editor over the lanes, the columns,
    the menu's windows (Silence, the server, help), the preview."""
    def others():
        return [w for w in Gtk.Window.list_toplevels() if w is not win and w.get_visible()]

    def shot_last(tag):
        pump(0.6)
        for w in others():
            shoot(w, out / f"{stem}-{tag}.png")
            w.close()
        pump(0.2)
    dlg = win.compose()
    dlg.buffer.set_text("Черновик: **жирное**, #тег и @kot — Markdown работает.")
    pump(0.6)
    shoot(win, out / f"{stem}-compose.png")
    dlg.preview()
    shot_last("preview")
    dlg.close()
    win.columns_btn.set_active(True)
    pump(1.0)
    shoot(win, out / f"{stem}-columns.png")
    win.columns_btn.set_active(False)
    pump(0.3)
    win.menu.model()  # (made when ≡ opens: what needs a login is enabled then)
    for action, tag in (("filters", "silence"), ("server", "server")):
        win.activate_action("win." + action, None)
        shot_last(tag)
    panel = win.open_help()  # a panel over the lanes, as the editor
    pump(0.6)
    shoot(win, out / f"{stem}-help.png")
    panel.close()
    pics = [m for lv in win.lane_views.values() for card in getattr(lv, "rows", {}).values()
            for m in getattr(getattr(card, "post", None), "media", ()) if m.kind == "image"]
    if pics:  # the viewer over the window
        from fedtail.frontends.gtk import viewer
        v = viewer.show(win, pics, 0)
        pump(1.0)
        shoot(win, out / f"{stem}-viewer.png")
        v.close()


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "out")
    out.mkdir(parents=True, exist_ok=True)
    names = sys.argv[2:] or sorted(p.stem for p in themefile.BUILTIN_DIR.glob("*.toml"))
    i18n.setup("ru")
    for i, name in enumerate(names):
        for dark in (False, True):
            run(out, name, dark, extras=(i == 0 and dark))
        if i == 0:
            run(out, name, True, layout="split")
    return 0


if __name__ == "__main__":
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        sys.exit(subprocess.call(["xvfb-run", "-a", sys.executable] + sys.argv))
    sys.exit(main())
