"""Render the GTK window with made-up data and save PNG screenshots, one per theme
given (all by default), light and dark.

    xvfb-run -a python3 tools/gtk_screenshots.py OUT_DIR [THEME ...]

The GTK twin of tools/screenshots.py (docs/GTK.md), on the same made-up world
(tools/showcase.py): a theme in Qt and in GTK can be put side by side.
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
from tools import userthemes  # noqa: E402

OWN_THEMES = userthemes.bring(Path(_tmp) / "config")  # tested too, never published
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
from tests.fakes import FakeApi  # noqa: E402
from tools.showcase import picture_png, world  # noqa: E402 — the world Qt's shots show


def fake_media(url):
    """View.media_bytes without the network: the made-up world's faces and pictures."""
    from concurrent.futures import Future
    f = Future()
    f.set_result(picture_png(url))
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
    names = sys.argv[2:] or sorted(p.stem for p in themefile.BUILTIN_DIR.glob("*.toml")) \
        + OWN_THEMES
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
