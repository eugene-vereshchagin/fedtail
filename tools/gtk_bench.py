"""How fast the GTK window is, measured: the start, opening lanes, scrolling a long lane
end to end, trying themes, the editor, and in the split layout the roster and the tabs —
on a fake server with a few thousand posts of every kind (pictures, warnings, links,
boosts, replies, long texts), no network.

For every scenario: how long it took, the longest the main loop stood still (what the
hand feels as a freeze) and how many turns of it took over 100 ms.

    python3 tools/gtk_bench.py                     # every layout, the themes below
    python3 tools/gtk_bench.py --layout split --theme qip-retro --posts 3000
    python3 tools/gtk_bench.py --profile           # and where the time went (cProfile)

Run it on the desktop you use: the accessibility bus, the fonts and the GPU are half
of what makes a window slow, and none of them are the same under Xvfb. Each layout and
theme runs in a process of its own; your config and data are not touched."""

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

THEMES = ("system", "nord", "qip-retro", "mra")
LAYOUTS = ("single", "columns", "split")
SLOW_MS = 100


# ---- the fake server's content ------------------------------------------------------------
def _png(w, h, rgb):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), rgb).save(buf, "PNG")
    return buf.getvalue()


def world(n):
    """A server with n posts in the home lane, people, mentions, replies."""
    from tests import fakes
    from tests.fakes import ME, acct, status
    w = fakes.World()
    people = [acct(f"P{i}", f"user{i}@srv{i % 7}.example", bot=(i % 13 == 0))
              for i in range(40)]
    for i, p in enumerate(people):
        p["display_name"] = f"Человек {i} :blobcat:"
        p["avatar_static"] = f"https://img.example/av/{i}.png"
    words = ("федиверс", "картошка", "Тбилиси", "сервер", "KDE", "GTK", "поезд", "кот")
    for i in range(n):
        who = people[i % len(people)]
        text = " ".join(words[(i + k) % len(words)] for k in range(8 + i % 40))
        if i % 5 == 0:
            text += ' <a href="https://example.org/page">https://example.org/page</a>'
        if i % 7 == 0:
            text += " <b>жирно</b> и <i>курсив</i> #тег @mira"
        s = status(f"{i:06d}", who, minute=i % 59, vis=("public", "unlisted", "private")[i % 3],
                   text=text)
        s["created_at"] = (f"2099-10-{1 + i // 1440 % 28:02d}T{i // 60 % 24:02d}:"
                           f"{i % 60:02d}:00.000Z")
        if i % 4 == 0:
            s["media_attachments"] = [
                {"id": f"m{i}-{k}", "type": "image", "url": f"https://img.example/{i}-{k}.png",
                 "preview_url": f"https://img.example/{i}-{k}s.png",
                 "description": "картинка" if k else "",
                 "meta": {"original": {"width": 800 + 100 * k, "height": 600}}}
                for k in range(1 + i % 3)]
        if i % 9 == 0:
            s["spoiler_text"] = "осторожно"
        s["replies_count"], s["favourites_count"], s["reblogs_count"] = i % 5, i % 11, i % 3
        if i % 6 == 0 and i:
            s["in_reply_to_id"] = f"{i - 1:06d}"
            s["in_reply_to_account_id"] = people[(i - 1) % len(people)]["id"]
        w.add(s, home=True, mention=(i % 25 == 0))
    w.add(status("999999", ME, minute=1, text="мой пост"), home=True)
    return w


def fake_media(url, *_a, **_k):
    """Every picture the window asks for: a small PNG, its colour from the address."""
    h = sum(url.encode()) % 200
    return _png(64, 48, (40 + h // 2, 90, 160 - h // 3))


class _Answer:
    def __init__(self, data):
        self.content, self.status_code, self.headers = data, 200, {"Content-Type": "image/png"}

    def raise_for_status(self):
        pass

    def iter_content(self, _n):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


# ---- measuring --------------------------------------------------------------------------
class Meter:
    """Runs the main loop, timing each turn of it."""

    def __init__(self):
        from fedtail.frontends.gtk.gi_setup import GLib
        self.ctx = GLib.MainContext.default()
        self.rows = []
        self.worst, self.slow, self.turns = 0.0, 0, 0

    def _turn(self, d):
        self.worst = max(self.worst, d)
        self.slow += d * 1000 > SLOW_MS
        self.turns += 1

    def run(self, seconds=0.0, until=None, limit=30.0):
        """Turn the loop for `seconds`, or until until() (at most `limit`)."""
        t0 = time.monotonic()
        end = t0 + (seconds if until is None else limit)
        while time.monotonic() < end:
            while self.ctx.pending():
                a = time.monotonic()
                self.ctx.iteration(False)
                self._turn(time.monotonic() - a)
            if until is not None and until():
                break
            time.sleep(0.004)
        return time.monotonic() - t0

    def scenario(self, name, fn):
        """fn() starts it (it may turn the loop itself) and returns a "done?" function
        (or None: then the loop runs a second more)."""
        self.worst, self.slow, self.turns = 0.0, 0, 0
        t0 = time.monotonic()
        done = fn()
        if self.turns == 0:  # all of it in one go: that's one long turn
            self._turn(time.monotonic() - t0)
        self.run(1.0 if done is None else 0.0, until=done)
        total = time.monotonic() - t0
        self.rows.append((name, total, self.worst, self.slow))
        print(f"  {name:<34} {total * 1000:8.0f} ms   worst {self.worst * 1000:6.0f} ms   "
              f"slow turns {self.slow:3d}", flush=True)


def scroll(meter, lv, to_top):
    """The lane to its top or its end a screen at a time, 60 times a second, as a hand
    would — waiting at the edge for more to come in, until nothing more does."""
    adj = lv.adj
    still = 0
    for _ in range(400):  # a few hundred posts: enough to see how it goes
        v = adj.get_value()
        nxt = max(adj.get_lower(), v - adj.get_page_size()) if to_top else \
            min(adj.get_upper() - adj.get_page_size(), v + adj.get_page_size())
        adj.set_value(nxt)
        meter.run(0.016)
        if abs(adj.get_value() - v) < 1:
            still += 1
            if still > 40:  # ~0.7 s at the edge and nothing came in
                break
        else:
            still = 0
    return lambda: True


# ---- a run: one layout, one theme ------------------------------------------------------------
def run(layout, theme, posts, profile):
    tmp = tempfile.mkdtemp(prefix="fedtail-bench-")
    os.environ["XDG_CONFIG_HOME"] = str(Path(tmp) / "config")
    os.environ["XDG_DATA_HOME"] = str(Path(tmp) / "data")
    from fedtail import i18n
    from fedtail.core import auth, config, paths
    from fedtail.core.app import Core
    from fedtail.core.view import View
    from fedtail.frontends.gtk import gi_setup
    from fedtail.frontends.gtk import theme as themes
    from fedtail.frontends.gtk.bridge import Bridge
    from fedtail.frontends.gtk.window import MainWindow
    from tests.fakes import FakeApi
    gi_setup.load_adwaita("off")
    i18n.setup("ru")
    FakeApi.world = world(posts)
    cfg, _ = config.validate({
        "feed": {"first_run_mark_read": False},
        "ui": {"start_lane": "home", "adwaita": "off", "theme": theme, "layout": layout,
               "columns": ["home", "mentions", "local"] if layout == "columns" else []}})
    p = paths.resolve("bench", config=str(Path(tmp) / "c.toml"), data=str(Path(tmp) / "d"))
    auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
    prof = None
    if profile:
        import cProfile
        prof = cProfile.Profile()
        prof.enable()
    meter = Meter()
    print(f"\n{layout} · {theme} · {posts} posts", flush=True)
    state = {}

    def start():
        core = Core(cfg, p, api_class=FakeApi)
        core._origin_json = lambda url: None
        view = View(core)
        view.media_bytes = lambda url, *a, **k: fake_media(url)
        # the home lane: all of the server's posts at once (as after days of polling),
        # not the first page a fresh account gets
        from fedtail.protocols.mastodon import adapter
        every = sorted(FakeApi.world.statuses.values(), key=lambda x: x["id"])
        big = [(x["id"], adapter.post(x, "bench")) for x in every]
        entries = view.entries
        view.entries = lambda lane: big if lane == "home" else entries(lane)
        win = MainWindow(None, core, view, Bridge(view), themes.apply(cfg))
        win.images.http.get = lambda url, *a, **k: _Answer(fake_media(url))
        win.set_default_size(1200, 800)
        win.present()
        win.start()
        state.update(core=core, view=view, win=win)
        return lambda: bool(win.lane_rows)
    meter.scenario("start: window, connected", start)
    win, core = state["win"], state["core"]

    def first_poll():
        core.poll_once()
        return lambda: _home(win) is not None and getattr(_home(win), "positioned", False)
    meter.scenario("first poll, home lane on screen", first_poll)
    meter.scenario("settle (pictures, faces)", lambda: None)

    lv = _home(win)
    if lv is not None and hasattr(lv, "adj"):
        meter.scenario("scroll home to the end", lambda: scroll(meter, lv, False))
        meter.scenario("scroll home back to the top", lambda: scroll(meter, lv, True))

    for lane in ("mentions", "local", "replies"):
        if lane in win.lane_rows:
            def open_lane(lane=lane):
                win.select_lane(lane)
                view = (win.lane_tabs if win.split_mode else win.lane_views).get(lane)
                return lambda: win.lane_on_screen(lane) and (
                    view is None or getattr(view, "positioned", True))
            meter.scenario(f"open lane {lane}", open_lane)

    def menu():
        btn = getattr(win, "menu_btn", None)
        if btn is not None and btn.get_mapped():
            btn.popup()
            meter.run(0.4)
            btn.popdown()
        return None
    meter.scenario("open the ≡ menu", menu)

    def compose():
        state["composer"] = win.compose()
        return None
    meter.scenario("open the editor", compose)
    if state["composer"] is not None:  # (split: the input line, nothing to close)
        meter.scenario("close the editor", lambda: (state["composer"].close(), None)[1])

    if layout == "split" and win.roster is not None:
        meter.scenario("roster: refresh", lambda: (win.roster.refresh(), None)[1])
        for name in ("mentions", "local"):
            meter.scenario(f"tab: open {name}", lambda n=name: (win.roster.open(n), None)[1])
        meter.scenario("tabs: switch around", lambda: _switch_tabs(meter, win))

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
    win.close()
    core.shutdown()
    return meter.rows


def _home(win):
    return win.lane_tabs.get("home") if win.split_mode else win.lane_views.get("home")


def _switch_tabs(meter, win):
    n = win.tabs.get_n_pages()
    for i in range(n * 2):
        win.tabs.set_current_page(i % n)
        meter.run(0.1)
    return None


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
            args = [sys.executable, __file__, "--layout", layout, "--theme", theme,
                    "--posts", str(a.posts)] + (["--profile"] if a.profile else [])
            subprocess.call(args)
    return 0


if __name__ == "__main__":
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        sys.exit(subprocess.call(["xvfb-run", "-a", sys.executable] + sys.argv))
    sys.exit(main())
