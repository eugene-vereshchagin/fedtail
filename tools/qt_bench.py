"""How fast the Qt window is, measured as tools/gtk_bench.py measures the GTK one: the
start, opening lanes, scrolling a long lane, the ≡ menu, the editor, themes, the split
layout's roster and tabs — on a fake server with a few thousand posts, no network.

For every scenario: how long it took, the longest the event loop stood still (what the
hand feels as a freeze) and how many turns of it took over 100 ms.

    python3 tools/qt_bench.py                      # every layout, the themes below
    python3 tools/qt_bench.py --layout split --theme qip-retro --posts 3000
    python3 tools/qt_bench.py --profile            # and where the time went (cProfile)

The desktop's own Qt platform is used (the real style, fonts, accessibility): that's
what is being measured. Windows flash on the screen; your config and data are not
touched."""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

THEMES = ("system", "point", "qip-retro", "mra")
LAYOUTS = ("single", "columns", "split")
SLOW_MS = 100


class Meter:
    """Runs the event loop, timing each turn of it."""

    def __init__(self, app):
        self.app = app
        self.rows = []
        self.worst, self.slow, self.turns = 0.0, 0, 0

    def _turn(self, d):
        self.worst = max(self.worst, d)
        self.slow += d * 1000 > SLOW_MS
        self.turns += 1

    def run(self, seconds=0.0, until=None, limit=30.0):
        t0 = time.monotonic()
        end = t0 + (seconds if until is None else limit)
        while time.monotonic() < end:
            a = time.monotonic()
            self.app.processEvents()
            self._turn(time.monotonic() - a)
            if until is not None and until():
                break
            time.sleep(0.004)
        return time.monotonic() - t0

    def scenario(self, name, fn):
        self.worst, self.slow, self.turns = 0.0, 0, 0
        t0 = time.monotonic()
        try:
            done = fn()
        except Exception as e:  # noqa: BLE001 — the scenario is reported, the rest goes on
            print(f"  {name:<34} FAILED: {type(e).__name__}: {e}", flush=True)
            return
        if self.turns == 0:
            self._turn(time.monotonic() - t0)
        self.run(1.0 if done is None else 0.0, until=done)
        total = time.monotonic() - t0
        self.rows.append((name, total, self.worst, self.slow))
        print(f"  {name:<34} {total * 1000:8.0f} ms   worst {self.worst * 1000:6.0f} ms   "
              f"slow turns {self.slow:3d}", flush=True)


def scroll(meter, bar, to_top):
    """The scroll bar to its top or end a page at a time, 60 times a second."""
    still = 0
    for _ in range(400):
        v = bar.value()
        bar.setValue(v - bar.pageStep() if to_top else v + bar.pageStep())
        meter.run(0.016)
        if bar.value() == v:
            still += 1
            if still > 40:
                break
        else:
            still = 0
    return lambda: True


def run(layout, theme, posts, profile):
    tmp = tempfile.mkdtemp(prefix="fedtail-qtbench-")
    os.environ["XDG_CONFIG_HOME"] = str(Path(tmp) / "config")
    os.environ["XDG_DATA_HOME"] = str(Path(tmp) / "data")
    from PySide6.QtWidgets import QApplication

    from fedtail import i18n
    from fedtail.core import auth, config, paths
    from fedtail.core.app import Core
    from fedtail.frontends.qt import theme as themes
    from fedtail.frontends.qt.bridge import Bridge
    from fedtail.frontends.qt.window import MainWindow
    from tests.fakes import FakeApi
    from tools.gtk_bench import fake_media, world
    i18n.setup("ru")
    app = QApplication.instance() or QApplication([])
    FakeApi.world = world(posts)
    cfg, _ = config.validate({
        "feed": {"first_run_mark_read": False},
        "ui": {"start_lane": "home", "theme": theme, "layout": layout,
               "columns": ["home", "mentions", "local"] if layout == "columns" else []}})
    p = paths.resolve("bench", config=str(Path(tmp) / "c.toml"), data=str(Path(tmp) / "d"))
    auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
    prof = None
    if profile:
        import cProfile
        prof = cProfile.Profile()
        prof.enable()
    meter = Meter(app)
    print(f"\nQt · {layout} · {theme} · {posts} posts", flush=True)
    state = {}

    def start():
        from PySide6.QtGui import QPixmap
        core = Core(cfg, p, api_class=FakeApi)
        core._origin_json = lambda url: None
        # the home lane: all of the server's posts at once (as after days of polling)
        every = sorted(FakeApi.world.statuses.values(), key=lambda x: x["id"])
        lane_entries = core.lane_entries
        core.lane_entries = lambda lane, *a, **k: [(x["id"], x) for x in every] \
            if lane == "home" else lane_entries(lane, *a, **k)
        win = MainWindow(core, Bridge(core), themes.apply(app, cfg))

        def picture(url, cb, *a, **k):
            pm = QPixmap()
            pm.loadFromData(fake_media(url))
            cb(pm)
        win.images.get = picture
        win.tray = None
        win.resize(1200, 800)
        win.show()
        win.start()
        state.update(core=core, win=win)
        return lambda: bool(core.me)
    meter.scenario("start: window, connected", start)
    win, core = state["win"], state["core"]

    def first_poll():
        core.poll_once()
        win.select_lane("home")
        return lambda: "home" in win.lane_widgets
    meter.scenario("first poll, home lane on screen", first_poll)
    meter.scenario("settle (pictures, faces)", lambda: None)

    lane = win.lane_widgets.get("home")
    view = getattr(lane, "view", None)
    if view is not None:
        bar = view.verticalScrollBar()
        meter.scenario("scroll home to the end", lambda: scroll(meter, bar, False))
        meter.scenario("scroll home back to the top", lambda: scroll(meter, bar, True))

    for name in ("mentions", "local", "replies"):
        def open_lane(name=name):
            win.select_lane(name)
            return lambda: win.lane_on_screen(name)
        meter.scenario(f"open lane {name}", open_lane)

    def menu():
        m = win._app_menu()
        m.popup(win.mapToGlobal(win.rect().center()))
        meter.run(0.4)
        m.close()
        m.deleteLater()
        return None
    meter.scenario("open the ≡ menu", menu)

    def compose():
        win.compose()
        return None
    meter.scenario("open the editor", compose)

    def close_editor():
        from fedtail.frontends.qt.compose import Compose
        for c in win.findChildren(Compose):
            c.reject()
        return None
    meter.scenario("close the editor", close_editor)

    if getattr(win, "roster", None) is not None:
        meter.scenario("roster: refresh", lambda: (win.roster.refresh(), None)[1])

    for other in [t for t in ("nord", "qip-retro", "system") if t != theme][:2]:
        meter.scenario(f"try theme {other}", lambda o=other: (win.try_theme(o), None)[1])

    if prof is not None:
        prof.disable()
        import pstats
        for key, n in (("cumulative", 45), ("tottime", 30)):
            out = io.StringIO()
            pstats.Stats(prof, stream=out).sort_stats(key).print_stats(n)
            print(out.getvalue())
    win.quitting = True
    if getattr(win, "roster", None) is not None:
        win.roster.close()
    win.hide()
    core.shutdown()
    return meter.rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--layout", choices=LAYOUTS)
    ap.add_argument("--theme")
    ap.add_argument("--posts", type=int, default=2000)
    ap.add_argument("--profile", action="store_true")
    a = ap.parse_args()
    if a.layout and a.theme:
        run(a.layout, a.theme, a.posts, a.profile)
        return 0
    for layout in ([a.layout] if a.layout else LAYOUTS):
        for theme in ([a.theme] if a.theme else THEMES):
            subprocess.call([sys.executable, __file__, "--layout", layout, "--theme", theme,
                             "--posts", str(a.posts)] + (["--profile"] if a.profile else []))
    return 0


if __name__ == "__main__":
    sys.exit(main())
