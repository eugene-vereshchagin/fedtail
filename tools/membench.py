"""The memory and speed bench (docs/en/dev/memory.md, step 0): one synthetic scenario,
measured the same way before and after every step of making fedtail lighter.

The scenario: a fake server (tests/fakes.py, no network) with --posts posts in Home —
pictures in every fourth, replies, mentions, the Local and Federated lanes fed too —
fedtail's own set of lanes plus enough lanes of rules of one's own to make --lanes in
all, then --hours of polling, a few new posts every round (a day of work, squeezed).

What it says:
  * memory — USS / PSS / RSS of the process (/proc/self/smaps_rollup), and with --trace
    where Python's part of it lives (tracemalloc by package: the core, the model, the
    interface's common layer, the toolkit's own code, the standard library…). Qt's own
    C++ heap isn't seen by tracemalloc: --ui qt adds the number of widgets and the
    picture cache's size instead;
  * time — the cold start to the first lane, opening each lane, applying the lanes'
    rules anew (every lane of rules filled again from the store), and with --ui qt
    scrolling 1000 posts of Home.

    python3 tools/membench.py                         # the core and the common layer
    python3 tools/membench.py --ui qt                 # and the Qt window (offscreen)
    python3 tools/membench.py --trace --json out.json # where the memory is, as data
    python3 tools/membench.py --posts 3000 --hours 2  # smaller, faster

Your own config and data aren't touched: everything lives in a temporary folder.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ROUND_MINUTES = 5          # a poll every 5 minutes of the simulated day
NEW_PER_ROUND = 12         # posts that come with each round
SCROLL_POSTS = 1000        # --ui qt: how far Home is scrolled


# ---- memory -------------------------------------------------------------------------------
def memory():
    """{"uss_mb", "pss_mb", "rss_mb"} of this process; {} where /proc can't say (not
    Linux) — the same numbers the dev build writes into its log every few minutes
    (diag.smaps)."""
    from fedtail import diag
    out = dict(diag.smaps())
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                out["rss_mb"] = round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    return out


# where Python's memory is, by the file that allocated it
PARTS = (
    ("fedtail/core/store", "store (SQLite rows, caches)"),
    ("fedtail/core", "core"),
    ("fedtail/model", "model (Post, Account…)"),
    ("fedtail/protocols", "protocols (server JSON → model)"),
    ("fedtail/frontends/common", "interface, common layer"),
    ("fedtail/frontends/qt", "interface, Qt"),
    ("fedtail/frontends/gtk", "interface, GTK"),
    ("fedtail/", "fedtail, the rest"),
    ("tests/", "the bench's fake server"),
    ("json/", "json (parsing)"),
    ("sqlite3/", "sqlite3"),
    ("PySide6/", "PySide6 (Python side)"),
)


def split(snapshot):
    """{part: MB} of a tracemalloc snapshot, by the first frame that is ours."""
    out = {}
    for stat in snapshot.statistics("traceback"):
        name = "other"
        for frame in stat.traceback:
            f = frame.filename.replace("\\", "/")
            hit = next((label for key, label in PARTS if key in f), None)
            if hit:
                name = hit
                break
        out[name] = out.get(name, 0) + stat.size
    return {k: round(v / 1048576, 1) for k, v in sorted(out.items(), key=lambda x: -x[1])}


# ---- the scenario ---------------------------------------------------------------------------
def own_lanes(n):
    """n lanes of rules of one's own, of every kind the sets have: one source and
    several, posts and events, chips, a window, sorted by likes."""
    kinds = [
        {"source": "home", "any": [{"has": "media"}]},
        {"source": ["home", "local"], "any": [{"text": "Тбилиси"}]},
        {"source": "home", "any": [{"kind": "reply"}], "sort": "post_time"},
        {"source": "local", "read": "browse", "any": [{}], "none": [{"author": "bot"}]},
        {"source": ["home", "mentions"], "any": [{"me": "mention"}, {"text": "кот"}]},
        {"source": "home", "any": [{}], "sort": "likes"},
        {"source": "federated", "read": "browse", "any": [{"has": "media"}]},
        {"any": [{"event": ["favourite", "reblog"]}]},
        {"source": "home", "any": [{"author": "bot"}, {"kind": "boost", "switch": "b"}]},
        {"source": ["home", "local", "mentions"], "any": [{"text": "сервер"}],
         "none": [{"kind": "reply"}]},
    ]
    return [dict(kinds[i % len(kinds)], name=f"bench{i}") for i in range(n)]


def make(tmp, posts, lanes):
    from fedtail import i18n
    from fedtail.core import auth, config, paths
    from fedtail.core.app import Core
    from tests import fakes
    from tests.fakes import FakeApi
    from tools.gtk_bench import world
    i18n.setup("ru")
    w = world(posts)
    w.local.extend(list(w.statuses.values())[: posts // 4])  # Local (and Federated) too
    for i in range(posts // 50):  # likes and follows: Activity and the lanes of events
        w.act(f"a{i}", ("favourite", "reblog", "follow")[i % 3], fakes.BOB,
              w.statuses.get(f"{i:06d}"), minute=i % 59)
    FakeApi.world = w
    preset = 11  # fedtail's set (Federated, Home, … Activity) — the rest one's own
    over = {"feed": {"first_run_mark_read": False},
            "lanes": {"custom": own_lanes(max(0, lanes - preset))}}
    if IMAGE_MB:
        over["ui"] = {"image_cache_mb": IMAGE_MB}
    cfg, _ = config.validate(over)
    p = paths.resolve("bench", config=str(Path(tmp) / "c.toml"), data=str(Path(tmp) / "d"))
    auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
    core = Core(cfg, p, api_class=FakeApi)
    core._origin_json = lambda url: None
    return core, w


def seed(core, w):
    """The store as after days of polling: Home, Local, the mentions, Activity full."""
    def entries(sts):
        return [(st["id"], st, st.get("created_at", "")) for st in sts]
    core.store.put_items("home", entries(w.home))
    core.store.put_items("local", entries(w.local))
    core.store.put_items("mentions", entries([n["status"] for n in w.notifications
                                              if n.get("type") == "mention"
                                              and n.get("status")]))
    core.store.activity_put([n for n in w.notifications if n.get("type") != "mention"])


IMAGE_MB = None  # --image-mb


def pictures(core, w):
    """Every picture of the fake server already in the disk cache, as after days of
    reading (the bench has no network): real JPEGs of the sizes the posts say, so the
    window decodes and keeps them as it would — on 28.10 a real window's pictures were
    128 MB of its 550, which a bench without them never saw. Returns how many."""
    import hashlib

    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QColor, QImage
    made = {}

    def jpeg(w_, h_):
        if (w_, h_) not in made:
            img = QImage(w_, h_, QImage.Format.Format_RGB32)
            img.fill(QColor(90, 120, 160))
            data = QByteArray()
            buf = QBuffer(data)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buf, "JPEG", 80)
            made[w_, h_] = bytes(data)
        return made[w_, h_]
    urls = {}
    for st in w.statuses.values():
        av = st["account"].get("avatar_static")
        if av:
            urls[av] = (400, 400)
        for m in st.get("media_attachments") or ():
            o = (m.get("meta") or {}).get("original") or {}
            size = (o.get("width") or 800, o.get("height") or 600)
            for u in (m.get("url"), m.get("preview_url")):
                if u:
                    urls[u] = size
    d = core.paths.cache_dir
    d.mkdir(parents=True, exist_ok=True)
    for url, size in urls.items():
        (d / hashlib.sha1(url.encode()).hexdigest()).write_bytes(jpeg(*size))
    return len(urls)


def new_posts(w, k, n0):
    from tests.fakes import status
    people = [a for a in (st["account"] for st in list(w.statuses.values())[:40])]
    for i in range(k):
        st = status(f"9{n0 + i:07d}", people[i % len(people)], minute=(n0 + i) % 59,
                    text="новое " * (5 + i % 30))
        w.add(st, home=True, mention=(i % 10 == 0))


def timed(rows, name, fn):
    t = time.perf_counter()
    got = fn()
    ms = (time.perf_counter() - t) * 1000
    rows.append((name, round(ms)))
    print(f"  {name:<44} {ms:8.0f} ms", flush=True)
    return got


def run(args):
    import tracemalloc
    tmp = tempfile.mkdtemp(prefix="fedtail-membench-")
    os.environ["XDG_CONFIG_HOME"] = str(Path(tmp) / "config")
    os.environ["XDG_DATA_HOME"] = str(Path(tmp) / "data")
    if args.trace:
        tracemalloc.start(8)
    result = {"posts": args.posts, "lanes": args.lanes, "hours": args.hours, "ui": args.ui,
              "python": sys.version.split()[0], "memory": {}, "time": []}
    times = result["time"]
    result["memory"]["before"] = memory()
    print(f"\nfedtail membench · {args.posts} posts · {args.lanes} lanes · "
          f"{args.hours} h · ui {args.ui}", flush=True)

    app = win = None
    if args.ui == "qt":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

    # days of polling already behind: every post of the server stored, as it would be
    core, w = make(tmp, args.posts, args.lanes)
    seed(core, w)
    core.shutdown()

    def start():
        core, w2 = make(tmp, args.posts, args.lanes)  # a new start over that store
        core.connect().result()
        core.poll_once()
        return core, w2
    core, w = timed(times, "cold start: core, connect, first round", start)
    if args.ui == "qt":
        result["pictures_on_disk"] = pictures(core, w)
    from fedtail.core.view import View
    from fedtail.frontends.common.lane import LaneModel
    view = View(core)
    result["lanes_shown"] = len(core.lanes)
    timed(times, "first lane (Home) built", lambda: LaneModel(view, "home").build(False))
    if args.ui == "qt":
        win = timed(times, "Qt window up, Home drawn", lambda: qt_window(app, core))

    def every_lane():
        worst = 0.0
        for lane in core.lanes:
            t = time.perf_counter()
            if win is not None:
                win.select_lane(lane.name)
                pump(app)
            else:
                LaneModel(view, lane.name).build(False)
            worst = max(worst, time.perf_counter() - t)
        return worst
    worst = timed(times, f"open every lane ({len(core.lanes)})", every_lane)
    times.append(("  the slowest lane", round(worst * 1000)))
    print(f"  {'  the slowest lane':<44} {worst * 1000:8.0f} ms", flush=True)

    from fedtail.core import custom

    def rules():
        for c in core.customs:
            if c.routed:
                custom.backfill(core.store, c, core._world())
        core._lane_cache.clear()
        for lane in core.lanes:
            core.lane_entries(lane.name)
    timed(times, "lanes' rules applied anew (all of them)", rules)

    rounds = int(args.hours * 60 / ROUND_MINUTES)

    def day():
        for r in range(rounds):
            new_posts(w, NEW_PER_ROUND, r * NEW_PER_ROUND)
            core.poll_once()
            if app is not None:
                pump(app)
    timed(times, f"{args.hours:g} h of polling ({rounds} rounds)", day)
    if win is not None:
        timed(times, f"Home scrolled through {SCROLL_POSTS} posts",
              lambda: qt_scroll(app, win))
    gc.collect()
    result["memory"]["after"] = memory()
    result["counts"] = {k: v for k, v in core.diag_stats().items()
                        if isinstance(v, (int, float))}
    result["counts"]["python_objects"] = len(gc.get_objects())
    result["counts"]["modules"] = len(sys.modules)
    if win is not None:
        result["counts"].update({f"qt.{k}": v for k, v in qt_counts(app, win).items()})
        # the day above ran in minutes: ui.unload_hidden_minutes never came for the
        # lanes out of sight. What they come to once it has (the steady state of a
        # window kept open), and how much of it the C heap then gives back.
        result["memory"]["hidden_unloaded"] = qt_unloaded(app, win)
        result["counts"]["qt.widgets_unloaded"] = qt_counts(app, win)["widgets"]
        result["memory"]["after_malloc_trim"] = trimmed()
    if args.trace:
        result["memory"]["python"] = split(tracemalloc.take_snapshot())
        tracemalloc.stop()
    print("\n  memory " + "  ".join(f"{k} {v}" for k, v in result["memory"]["after"].items()))
    for state in ("hidden_unloaded", "after_malloc_trim"):
        if result["memory"].get(state):
            print(f"  memory, {state}: " + "  ".join(
                f"{k} {v}" for k, v in result["memory"][state].items()))
    for part, mb in (result["memory"].get("python") or {}).items():
        print(f"    {part:<40} {mb:8.1f} MB")
    print("  " + "  ".join(f"{k} {v}" for k, v in result["counts"].items()))
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=1), "utf-8")
    if args.md:
        Path(args.md).write_text(markdown(result), "utf-8")
    if win is not None:
        win.close()
    core.shutdown()
    return result


def markdown(r):
    """The result as the tables of docs/<lang>/dev/memory.md's baseline."""
    lines = [f"{r['posts']} posts, {r['lanes_shown']} lanes, {r['hours']:g} h, "
             f"ui {r['ui']}, Python {r['python']}", "",
             "| memory | MB |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in r["memory"].get("after", {}).items()]
    for state, words in (("hidden_unloaded", "hidden lanes unloaded"),
                         ("after_malloc_trim", "and malloc_trim(0)")):
        if r["memory"].get(state):
            lines += [f"| {k}, {words} | {v} |" for k, v in r["memory"][state].items()]
    if r["memory"].get("python"):
        lines += ["", "| Python's part, by package | MB |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in r["memory"]["python"].items()]
    lines += ["", "| time | ms |", "|---|---|"] + [f"| {k.strip()} | {v} |"
                                                    for k, v in r["time"]]
    return "\n".join(lines) + "\n"


def pump(app):
    """Let the window run a moment, as its event loop would: events handled and the
    widgets let go (deleteLater) deleted — processEvents() alone never deletes them, so
    every card let go while polling and scrolling was counted (305 cards held, 48 shown:
    6299 widgets where a running window has some 1300)."""
    from PySide6.QtCore import QCoreApplication, QEvent
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


# ---- the Qt window --------------------------------------------------------------------------
def qt_window(app, core):
    from fedtail.frontends.qt import theme as themes
    from fedtail.frontends.qt.bridge import Bridge
    from fedtail.frontends.qt.window import MainWindow
    win = MainWindow(core, Bridge(core), themes.apply(app, core.cfg))
    if win.tray is not None:
        win.tray.hide()
    win.resize(1200, 900)
    win.show()
    win.select_lane("home")
    for _ in range(50):
        app.processEvents()
    return win


def qt_scroll(app, win):
    view = win.lane_widgets["home"].view
    bar = view.verticalScrollBar()
    seen = 0
    while seen < SCROLL_POSTS:
        before = bar.value()
        bar.setValue(before + bar.pageStep())
        pump(app)
        seen += 3  # a page shows a few cards
        if bar.value() == before and before >= bar.maximum():
            break


def qt_unloaded(app, win):
    """Every lane but the one in front unloaded, as ui.unload_hidden_minutes does."""
    # Home in front, always: which lane was left there varied (1062 widgets left one
    # run, 1936 the next — 20 MB of noise between two runs of the same code)
    win.select_lane("home")
    app.processEvents()
    front = win.stack.currentWidget()
    for w in list(win.lane_widgets.values()):
        if w is not front and w.view.order:
            w.hide()
            w._unload()
    pump(app)
    gc.collect()
    return memory()


def trimmed():
    """memory() after glibc's malloc_trim(0): what freed C memory the process still
    holds without using (Linux only; {} elsewhere)."""
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        return {}
    return memory()


def qt_counts(app, win):
    from PySide6.QtWidgets import QWidget
    out = {"widgets": sum(1 for w in app.allWidgets() if isinstance(w, QWidget))}
    counts = getattr(win.images, "counts", None)
    if counts:
        out.update({k: v for k, v in counts().items() if isinstance(v, (int, float))})
    out["images_mem"] = len(win.images.mem)  # as the stats line says them
    out["images_mb"] = round(win.images.mem_bytes / 1024 / 1024, 1)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--posts", type=int, default=10000)
    ap.add_argument("--lanes", type=int, default=20)
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--ui", choices=("none", "qt"), default="none")
    ap.add_argument("--image-mb", type=int, help="ui.image_cache_mb (the default if not)")
    ap.add_argument("--trace", action="store_true", help="where Python's memory is (slower)")
    ap.add_argument("--json", help="the result as JSON into this file")
    ap.add_argument("--md", help="the result as the baseline's tables into this file")
    args = ap.parse_args(argv)
    global IMAGE_MB
    IMAGE_MB = args.image_mb
    run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
