"""Many tabs opened and closed, again and again: threads, profiles, hashtags — in the Qt
window, the GTK window and the terminal (where a tab is a screen pushed and popped).
Each round: time to open them all, time to close, what is left alive afterwards
(widgets, Python objects, the memory of the process). What grows round after round is
a leak; an exception anywhere is an error.

    python3 tools/tabs_stress.py OUT_DIR --ui qt|gtk|tui [--rounds 6] [--tabs 30]
                                 [--layout single|split] [--real[=PROFILE]] [--churn]

--churn: no tabs — what a window open for a day goes through instead: each round new
posts arrive (replies, threads, boosts), the poll runs, every lane is opened in turn,
all is read. What stays behind round after round is the leak of a long session (Qt, GTK).

--real: your own account, read-only (tools/real.py): the posts, people and tags of
your home lane. Writes OUT_DIR/report.md, errors.txt ("none" when all went well)."""

from __future__ import annotations

import argparse
import gc
import logging
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import real  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="fedtail-tabs-")
REAL = real.snapshot(_tmp)  # before XDG_* point at the temporary folder
os.environ["XDG_CONFIG_HOME"] = str(Path(_tmp) / "config")
os.environ["XDG_DATA_HOME"] = str(Path(_tmp) / "data")

ERRORS, ROWS, NOTES = [], [], []
ARGS = {"rounds": 0}
# a round's leftovers may grow a little (caches warm up); past this, round after
# round, it is a leak
GROW_WIDGETS = 40
GROW_MB = 60


class Catch(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            text = self.format(record)
            if REAL and real.READ_ONLY in text:
                return
            ERRORS.append("log: " + text[-3000:])


def hook(kind, value, tb):
    text = "".join(traceback.format_exception(kind, value, tb))
    if REAL and real.READ_ONLY in text:
        return
    ERRORS.append("exception: " + text[-4000:])


def rss_mb():
    """The process's memory now (MB), or 0 where it can't be told."""
    try:
        import psutil
        return psutil.Process().memory_info().rss / 2**20
    except ImportError:
        pass
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 2**20
    except (OSError, ValueError, AttributeError):
        pass
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                    (n, ctypes.c_size_t) for n in (
                        "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                        "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                        "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
            return pmc.WorkingSetSize / 2**20
        except Exception:  # noqa: BLE001
            pass
    return 0.0


# ---- what to open ------------------------------------------------------------------------
def fake_core():
    from fedtail.core import auth, config, paths
    from fedtail.core.app import Core
    from tests import fakes
    from tests.fakes import FakeApi, acct, status
    FakeApi.world = w = fakes.World()
    people = [acct(f"P{i}", f"person{i}@example.org") for i in range(25)]
    prev = None
    for i in range(1, 160):
        who = people[i % len(people)]
        if i % 4 == 0 and prev is not None:  # threads of a few posts
            st = status(f"{i:04d}", who, prev["id"], prev["account"]["id"], minute=i,
                        vis="public", text=f"ответ {i} #tag{i % 12}")
        else:
            st = status(f"{i:04d}", who, minute=i, vis="public",
                        text=f"пост {i} #tag{i % 12} " + "слово " * (i % 7 + 2))
        st["tags"] = [{"name": f"tag{i % 12}", "url": f"https://example.test/tags/tag{i % 12}"}]
        w.add(st, home=True)
        prev = st
    cfg, _ = config.validate({"feed": {"first_run_mark_read": False}})
    p = paths.resolve("tabs", config=str(Path(_tmp) / "c.toml"), data=str(Path(_tmp) / "d"))
    auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
    core = Core(cfg, p, api_class=FakeApi)
    core._origin_json = lambda url: None
    return core, cfg


def make_core(ui=None):
    if REAL:
        cfg = real.config(REAL, ui)
        return real.core(REAL, cfg), cfg
    core, cfg = fake_core()
    if ui:
        cfg["ui"].update(ui)
    return core, cfg


def targets(core, n):
    """[(kind, what)]: threads, profiles, tags in turn — n of them, all different."""
    from fedtail.core.view import View
    from fedtail.model import real as real_post
    view = View(core)
    posts, people, tags = [], [], []
    for _sid, e in view.entries("home"):
        p = real_post(e)
        if p is None:
            continue
        posts.append(p.id)
        if p.author is not None and p.author.id not in people:
            people.append(p.author.id)
        for t in p.tags or ():
            if t.lower() not in tags:
                tags.append(t.lower())
    if not tags:
        tags = ["fediverse", "mastodon", "linux", "python"]
    out, pools = [], [("thread", posts), ("account", people), ("tag", tags)]
    i = 0
    while len(out) < n and any(p for _k, p in pools):
        kind, pool = pools[i % 3]
        if pool:
            out.append((kind, pool.pop(0)))
        i += 1
    return out


CHURN = {"n": 0}


def churn_round(core, per_round=40):
    """New posts on the fake server, as a busy day brings them: posts, replies into
    threads, boosts; then one poll."""
    from tests.fakes import FakeApi, acct, status
    w = FakeApi.world
    people = [acct(f"P{i}", f"person{i}@example.org") for i in range(25)]
    have = list(w.statuses.values())
    for _ in range(per_round):
        CHURN["n"] += 1
        i = 1000 + CHURN["n"]
        who = people[i % len(people)]
        if i % 5 == 0 and have:  # a boost of something older
            old = have[i % len(have)]
            st = dict(status(f"b{i}", who, minute=i % 60, vis="public"), reblog=old)
        elif i % 3 == 0 and have:
            par = have[-1 - i % min(len(have), 30)]
            st = status(f"{i:05d}", who, par["id"], par["account"]["id"], minute=i % 60,
                        vis="public", text=f"ответ {i}")
        else:
            st = status(f"{i:05d}", who, minute=i % 60, vis="public",
                        text=f"пост {i} #tag{i % 12} https://example.org/{i} " + "слово " * 5)
            st["tags"] = [{"name": f"tag{i % 12}",
                           "url": f"https://example.test/tags/tag{i % 12}"}]
            if i % 4 == 0:
                st["media_attachments"] = [{"id": f"m{i}", "type": "image",
                                            "url": f"https://example.test/m{i}.png",
                                            "preview_url": f"https://example.test/p{i}.png"}]
        w.add(st, home=True, mention=(i % 7 == 0))
        have.append(st)
    core.poll_once()


def connected(core, pump):
    """Wait for the connection (your account: the server may be slow): the tabs
    opened before it would all fail with "connecting"."""
    end = time.monotonic() + 60
    while time.monotonic() < end:
        if core.api is not None and core.me is not None:
            return True
        pump(0.1)
    ERRORS.append("not connected in 60 s")
    return False


TYPES = {}  # round → Counter of the Python objects' types alive after it


def type_census():
    from collections import Counter
    def name(o):
        t = type(o)
        mod = t.__dict__.get("__module__", "") if isinstance(t.__dict__.get("__module__"),
                                                            str) else ""
        return (mod.split(".")[0] + "." if mod else "") + t.__qualname__
    return Counter(name(o) for o in gc.get_objects())


def note_round(ui, rnd, opened, t_open, t_close, alive, objs, mb):
    ROWS.append((ui, rnd, opened, t_open, t_close, alive, objs, mb))
    if rnd == 2 or rnd == ARGS["rounds"]:
        TYPES[rnd] = type_census()
    print(f"  round {rnd:2d}: {opened} tabs, open {t_open:6.1f} s, close {t_close:5.1f} s, "
          f"widgets {alive}, objects {objs}, {mb:.0f} MB", flush=True)


def holders(kind_name, roots=(), depth=6, samples=2):
    """Why the objects of a kind are still alive: the chains of what refers to a few of
    them, as far as `depth` steps (what grows from round to round, said where it is)."""
    import inspect
    def loose(o):  # a widget no window shows any more (live ones aren't the leak)
        try:
            return o.get_root() is None
        except Exception:  # noqa: BLE001 — not a widget
            return True
    found = [o for o in gc.get_objects() if type(o).__name__ == kind_name
             and loose(o)][:samples]
    out = []
    ignore = {id(found)}

    def label(o):
        t = type(o).__name__
        if isinstance(o, dict):
            keys = list(o)[:6]
            return f"dict{keys}"
        if inspect.isfunction(o):
            return f"function {o.__qualname__} ({o.__code__.co_filename.rsplit('/', 1)[-1]}:" \
                   f"{o.__code__.co_firstlineno})"
        if t == "cell":
            return "cell"
        if isinstance(o, (list, tuple)):
            return f"{t}[{len(o)}: " + ", ".join(label(x) if not isinstance(x, (list, tuple, dict))
                                                 else type(x).__name__ for x in o[:4]) + "]"
        if inspect.ismethod(o):
            return f"method {o.__func__.__qualname__}"
        return t
    for obj in found:
        direct = [r for r in gc.get_referrers(obj) if id(r) not in ignore
                  and not inspect.isframe(r)]
        out.append(f"{kind_name} is referred to by: " + ", ".join(label(r) for r in direct[:8]))
        chain, cur = [], obj
        seen = {id(obj)}
        for _ in range(depth):
            got = gc.get_referrers(cur)
            ignore.add(id(got))
            refs = [r for r in got if id(r) not in ignore
                    and id(r) not in seen and not inspect.isframe(r)
                    and r is not chain]
            ignore.add(id(refs))
            if not refs:
                chain.append("(nothing in Python: held from C)")
                break
            # the most telling one: a dict of an object, a function, a list
            refs.sort(key=lambda r: (0 if inspect.isfunction(r) else 1 if isinstance(r, dict)
                                     else 2))
            cur = refs[0]
            seen.add(id(cur))
            chain.append(label(cur) + (f" (+{len(refs) - 1} more)" if len(refs) > 1 else ""))
        try:  # a widget: how many references C has on it, and whom it hangs on
            chain.append(f"[gref {obj.__grefcount__}, parent "
                         f"{type(obj.get_parent()).__name__}]")
        except Exception:  # noqa: BLE001
            pass
        out.append(f"{kind_name} ← " + " ← ".join(chain))
    return out


def judge(ui):
    rows = [r for r in ROWS if r[0] == ui]
    if len(rows) < 3:
        return
    base = rows[1]  # the first round warms the caches up
    last = rows[-1]
    if 2 in TYPES and last[1] in TYPES and last[1] != 2:
        grew = TYPES[last[1]] - TYPES[2]
        if grew:  # what is left behind, by kind: where a leak is
            NOTES.append(f"{ui}: objects that grew, rounds 2…{last[1]}: "
                         + ", ".join(f"{k} +{v}" for k, v in grew.most_common(15)))
            ours = [k for k, v in grew.most_common(40) if k.startswith("fedtail.") and v > 50]
            for k in ours[:4]:  # and who holds them
                NOTES.extend(f"{ui}: {line}" for line in holders(k.split(".", 1)[1]))
    if last[5] - base[5] > GROW_WIDGETS:
        ERRORS.append(f"{ui}: widgets left after closing grow round after round: "
                      f"{base[5]} → {last[5]} (rounds 2…{last[1]}) — a leak")
    if base[7] and last[7] - base[7] > GROW_MB:
        ERRORS.append(f"{ui}: memory grows round after round: {base[7]:.0f} → "
                      f"{last[7]:.0f} MB — a leak?")
    slow = max(r[3] for r in rows[1:])
    if slow > 3 * max(rows[1][3], 0.5):
        ERRORS.append(f"{ui}: opening got slower: round 2 {rows[1][3]:.1f} s, "
                      f"the slowest {slow:.1f} s")


# ---- Qt ----------------------------------------------------------------------------------
def run_qt(a):
    if not a.native:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    from fedtail.frontends.qt import theme as themes
    from fedtail.frontends.qt.bridge import Bridge
    from fedtail.frontends.qt.window import MainWindow
    app = QApplication.instance() or QApplication([])

    def pump(sec):
        end = time.monotonic() + sec
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)

    def until(cond, limit):
        end = time.monotonic() + limit
        while time.monotonic() < end and not cond():
            app.processEvents()
            time.sleep(0.01)

    core, cfg = make_core({"theme": a.theme, "layout": a.layout})
    win = MainWindow(core, Bridge(core), themes.apply(app, cfg))
    if not REAL:
        win.images.get = lambda url, cb, *x, **k: None  # no pictures: no network
    if win.tray is not None:
        win.tray.hide()
    win.tray = None
    win.resize(1280, 860)
    win.show()
    win.start()
    pump(2.0 if REAL else 0.5)
    connected(core, pump)
    core.poll_once()
    pump(3.0 if REAL else 1.0)
    todo = targets(core, a.tabs)
    NOTES.append(f"qt ({a.layout}, {a.theme}): {len(todo)} tabs a round — "
                 + ", ".join(f"{k} {sum(1 for x in todo if x[0] == k)}"
                             for k in ("thread", "account", "tag")))
    wait = 1.5 if REAL else 0.15
    if a.churn:
        lanes = [lane.name for lane in core.lanes if not lane.lazy]
        for rnd in range(1, a.rounds + 1):
            t0 = time.monotonic()
            try:
                churn_round(core)
                pump(0.3)
                for name in lanes:
                    win.select_lane(name)
                    pump(0.1)
                for name in lanes:  # all read, as a reader gets through the day
                    core.mark_read([st["id"] for _i, st in core.lane_entries(name)])
                pump(0.3)
            except Exception:  # noqa: BLE001
                ERRORS.append("qt churn: " + traceback.format_exc(limit=6))
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            pump(0.3)
            gc.collect()
            note_round("qt", rnd, len(lanes), time.monotonic() - t0, 0.0,
                       len(app.allWidgets()), len(gc.get_objects()), rss_mb())
        win.quitting = True
        win.hide()
        core.shutdown()
        judge("qt")
        return
    for rnd in range(1, a.rounds + 1):
        t0 = time.monotonic()
        for kind, what in todo:
            try:
                {"thread": win.open_thread, "account": win.open_account,
                 "tag": win.open_tag}[kind](what)
            except Exception:  # noqa: BLE001
                ERRORS.append(f"qt open {kind} {what}: " + traceback.format_exc(limit=6))
            pump(wait)
        until(lambda: False, 1.0)
        t_open = time.monotonic() - t0
        opened = len(win.extra_tabs())
        if rnd == 1 and opened < len(todo) * 0.8:
            ERRORS.append(f"qt: {len(todo)} tabs asked, {opened} opened")
        t0 = time.monotonic()
        for w in list(win.extra_tabs())[::-1 if rnd % 2 else 1]:  # both ways round
            try:
                win.close_tab(win.tabs.indexOf(w))
            except Exception:  # noqa: BLE001
                ERRORS.append("qt close: " + traceback.format_exc(limit=6))
            app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        pump(0.5)
        t_close = time.monotonic() - t0
        if win.extra_tabs():
            ERRORS.append(f"qt round {rnd}: {len(win.extra_tabs())} tabs still open")
        gc.collect()
        note_round("qt", rnd, opened, t_open, t_close, len(app.allWidgets()),
                   len(gc.get_objects()), rss_mb())
    win.quitting = True
    win.hide()
    core.shutdown()
    judge("qt")


# ---- GTK ---------------------------------------------------------------------------------
def run_gtk(a):
    from fedtail import i18n
    from fedtail.core.view import View
    from fedtail.frontends.gtk import gi_setup
    gi_setup.load_adwaita("off")
    from fedtail.frontends.gtk import theme as themes
    from fedtail.frontends.gtk.bridge import Bridge
    from fedtail.frontends.gtk.gi_setup import GLib
    from fedtail.frontends.gtk.window import MainWindow
    i18n.setup("ru")
    ctx = GLib.MainContext.default()

    def pump(sec):
        end = time.monotonic() + sec
        while time.monotonic() < end:
            while ctx.pending():
                ctx.iteration(False)
            time.sleep(0.005)

    def count(widget):
        n, child = 1, widget.get_first_child()
        while child is not None:
            n += count(child)
            child = child.get_next_sibling()
        return n

    core, cfg = make_core({"theme": a.theme, "layout": a.layout, "adwaita": "off"})
    view = View(core)
    win = MainWindow(None, core, view, Bridge(view), themes.apply(cfg))
    if not REAL:
        def no_net(*_x, **_k):
            raise OSError("tabs_stress: no network")
        win.images.http.get = no_net
    win.set_default_size(1280, 860)
    win.present()
    win.start()
    pump(2.0 if REAL else 0.5)
    connected(core, pump)
    core.poll_once()
    pump(3.0 if REAL else 1.0)
    todo = targets(core, a.tabs)
    NOTES.append(f"gtk ({a.layout}, {a.theme}): {len(todo)} tabs a round")
    wait = 1.5 if REAL else 0.15
    base_pages = win.tabs.get_n_pages()

    def extra():
        return len(win.threads) + len(win.accounts) + len(getattr(win, "extra_tabs", {}))
    if a.churn:
        lanes = [lane.name for lane in core.lanes if not lane.lazy]
        for rnd in range(1, a.rounds + 1):
            t0 = time.monotonic()
            try:
                churn_round(core)
                pump(0.3)
                for name in lanes:
                    win.select_lane(name)
                    pump(0.1)
                for name in lanes:
                    core.mark_read([st["id"] for _i, st in core.lane_entries(name)])
                pump(0.3)
            except Exception:  # noqa: BLE001
                ERRORS.append("gtk churn: " + traceback.format_exc(limit=6))
            gc.collect()
            note_round("gtk", rnd, len(lanes), time.monotonic() - t0, 0.0, count(win),
                       len(gc.get_objects()), rss_mb())
        core.shutdown()
        judge("gtk")
        return
    for rnd in range(1, a.rounds + 1):
        t0 = time.monotonic()
        for kind, what in todo:
            try:
                {"thread": win.open_thread, "account": win.open_account,
                 "tag": win.open_tag}[kind](what)
            except Exception:  # noqa: BLE001
                ERRORS.append(f"gtk open {kind} {what}: " + traceback.format_exc(limit=6))
            pump(wait)
        pump(1.0)
        t_open = time.monotonic() - t0
        opened = extra()
        if rnd == 1 and opened < len(todo) * 0.8:
            ERRORS.append(f"gtk: {len(todo)} tabs asked, {opened} opened")
        t0 = time.monotonic()
        try:
            for root in list(win.threads):
                win.close_thread(root)
                pump(0.0)
            for acc in list(win.accounts):
                win.close_account(acc)
                pump(0.0)
            for key in list(getattr(win, "extra_tabs", {})):
                win.close_extra(key)
                pump(0.0)
        except Exception:  # noqa: BLE001
            ERRORS.append("gtk close: " + traceback.format_exc(limit=6))
        pump(0.5)
        t_close = time.monotonic() - t0
        if win.tabs.get_n_pages() != base_pages:
            ERRORS.append(f"gtk round {rnd}: {win.tabs.get_n_pages() - base_pages} "
                          "tabs still open")
        gc.collect()
        note_round("gtk", rnd, opened, t_open, t_close, count(win),
                   len(gc.get_objects()), rss_mb())
    core.shutdown()
    judge("gtk")


# ---- the terminal ------------------------------------------------------------------------
def run_tui(a):
    import asyncio
    import collections

    from fedtail import i18n
    i18n.setup("ru")

    async def walk():
        from textual.widget import Widget

        from fedtail.frontends.tui.app import FedtailApp
        core, _cfg = make_core()
        app = FedtailApp(core)
        if not REAL:
            from concurrent.futures import Future
            app.core.media_bytes = lambda url: (f := Future(), f.set_result(None))[0]
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause(1.0 if REAL else 0.3)
            for _ in range(600):  # the connection first: a profile opened before it fails
                if core.api is not None and core.me is not None:
                    break
                await pilot.pause(0.1)
            else:
                ERRORS.append("tui: not connected in 60 s")
            await asyncio.get_running_loop().run_in_executor(None, core.poll_once)
            await pilot.pause(2.0 if REAL else 0.5)
            todo = targets(core, a.tabs)
            NOTES.append(f"tui: {len(todo)} screens a round")
            base = len(app.screen_stack)
            for rnd in range(1, a.rounds + 1):
                t0 = time.monotonic()
                for kind, what in todo:
                    try:
                        app.open_thing({"thread": {"thread": what}, "account":
                                        {"account": what},
                                        "tag": {"page": "tag", "arg": what}}[kind])
                    except Exception:  # noqa: BLE001
                        ERRORS.append(f"tui open {kind} {what}: "
                                      + traceback.format_exc(limit=6))
                    await pilot.pause(1.0 if REAL else 0.08)
                await pilot.pause(0.5)
                t_open = time.monotonic() - t0
                opened = len(app.screen_stack) - base
                if rnd == 1 and opened < len(todo) * 0.8:
                    ERRORS.append(f"tui: {len(todo)} screens asked, {opened} opened")
                t0 = time.monotonic()
                while len(app.screen_stack) > base:
                    try:
                        app.pop_screen()
                    except Exception:  # noqa: BLE001
                        ERRORS.append("tui close: " + traceback.format_exc(limit=6))
                        break
                    await pilot.pause(0.01)
                await pilot.pause(0.5)
                t_close = time.monotonic() - t0
                gc.collect()
                ws = [o for o in gc.get_objects() if isinstance(o, Widget)]
                alive = sum(1 for o in ws if o.is_attached)
                loose = collections.Counter(type(o).__name__ for o in ws
                                            if not o.is_attached)
                if rnd == a.rounds and loose:  # nobody of ours holds them: said, not judged
                    NOTES.append("tui: widgets detached but not freed at the end: "
                                 + ", ".join(f"{k} {v}" for k, v in loose.most_common(6)))
                note_round("tui", rnd, opened, t_open, t_close, alive,
                           len(gc.get_objects()), rss_mb())
        core.shutdown()
    asyncio.run(walk())
    judge("tui")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out", nargs="?", default="tabs-stress")
    ap.add_argument("--ui", choices=("qt", "gtk", "tui"), required=True)
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--tabs", type=int, default=30)
    ap.add_argument("--layout", default="single")
    ap.add_argument("--theme", default="system")
    ap.add_argument("--native", action="store_true", help="Qt: on the screen, not offscreen")
    ap.add_argument("--real", nargs="?", const="", help="your account (tools/real.py)")
    ap.add_argument("--churn", action="store_true",
                    help="a long session instead of tabs: posts arrive, lanes switch")
    a = ap.parse_args()
    if a.churn and REAL:
        ap.error("--churn makes posts on the fake server: not with --real")
    ARGS["rounds"] = a.rounds
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    catch = Catch()
    catch.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    logging.getLogger().addHandler(catch)
    logging.getLogger().setLevel(logging.WARNING)
    sys.excepthook = hook
    print(f"tabs: {a.ui}, {a.rounds} rounds of {a.tabs}"
          + (" — your account" if REAL else ""), flush=True)
    t0 = time.monotonic()
    try:
        {"qt": run_qt, "gtk": run_gtk, "tui": run_tui}[a.ui](a)
    except Exception:  # noqa: BLE001
        ERRORS.append(traceback.format_exc())
    md = [f"# {'A long session' if a.churn else 'Tabs opened and closed'}: {a.ui}", "",
          f"{'your account' if REAL else 'the fake server'} · {a.rounds} rounds · "
          f"{time.monotonic() - t0:.0f} s in all", ""] + [f"- {n}" for n in NOTES] + [
        "", "| round | tabs | open, s | close, s | widgets left | objects | MB |",
        "|---|---|---|---|---|---|---|"]
    for _ui, rnd, opened, t_open, t_close, alive, objs, mb in ROWS:
        md.append(f"| {rnd} | {opened} | {t_open:.1f} | {t_close:.1f} | {alive} | "
                  f"{objs} | {mb:.0f} |")
    md += ["", f"Problems: {len(ERRORS)}"]
    (out / "report.md").write_text("\n".join(md) + "\n", "utf-8")
    (out / "errors.txt").write_text("\n\n".join(ERRORS) + "\n" if ERRORS else "none\n",
                                    "utf-8")
    print(f"{len(ERRORS)} problems; {out / 'report.md'}")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
