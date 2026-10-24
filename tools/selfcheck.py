"""Everything the dev tools can check, in one go, on this machine: the tests, a walk
through every interface that can run here (Qt, GTK, the terminal, the web) with
screenshots, every menu and the window at every size, how fast the windows are, and
whether the four interfaces offer the same things. Then — if this machine has a
logged-in fedtail — the same on your own account (a copy, read-only).

    python3 tools/selfcheck.py --night         # all of it, for the night (1–3 hours)
    python3 tools/selfcheck.py                 # the fake server only (20–40 minutes)
    python3 tools/selfcheck.py --quick         # a few themes, one layout (3–5 minutes)
    python3 tools/selfcheck.py --only qt,web   # some steps: tests qt bench gtk tui web
                                               #   behaviour parity
    python3 tools/selfcheck.py --real          # and your account too (--real=PROFILE)
    python3 tools/selfcheck.py --only gallery  # the site's and the docs' pictures (only so)
    python3 tools/selfcheck.py --clean         # after Ctrl+C: the unfinished runs gone
    python3 tools/selfcheck.py --clean all     # every run here

Your account (--real, and --night when a profile is logged in): a copy of the
profile's config, login and database in a temporary folder; only GET goes to the
server — nothing is posted, liked, followed or marked read there (tools/real.py). Its
screenshots are blurred (the layout stays, the words don't) unless --no-blur; the
terminal's have their letters masked.

What can't run here (no PySide6, no GTK, no Textual, no Playwright) is skipped and said
so. Each run is a folder of its own: ~/fedtail_log/DATE_TIME/ (on Windows
%USERPROFILE%/fedtail_log/DATE_TIME/) — every step's pictures and logs, report.md, and
in the same folder the zip of all of it, to send back.
Works on Linux, Windows and macOS (GTK: Linux only)."""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS = ("tests", "windows", "qt", "bench", "gtk", "tui", "web", "behaviour", "tabs",
         "themes", "parity", "gallery")


def probe(code):
    """Whether this Python can do it (in a child: a crash in a binding stays there)."""
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       timeout=120, cwd=ROOT, env=env())
    if r.returncode == 0:
        return True, r.stdout.strip()
    last = r.stderr.strip().splitlines()
    return False, last[-1] if last else ""


COVERAGE = []  # the night run: [folder] every Python of every step leaves its lines in


def env():
    e = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
             FEDTAIL_SOUND=os.environ.get("FEDTAIL_SOUND", "off"))  # no chimes all night
    e["PYTHONPATH"] = str(ROOT) + os.pathsep + e.get("PYTHONPATH", "")
    if COVERAGE:  # tools/covhook/sitecustomize.py: each process notes the lines it ran
        e["PYTHONPATH"] = str(ROOT / "tools" / "covhook") + os.pathsep + e["PYTHONPATH"]
        e["FEDTAIL_COVERAGE"] = str(COVERAGE[0])
    return e


def has_display():
    return os.name == "nt" or sys.platform == "darwin" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def kill_tree(proc):
    """A step and everything it started (xvfb-run, the tool, its children)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, timeout=30, check=False)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


class Run:
    def __init__(self, out):
        self.out = out
        self.rows = []
        self.wrap = ()  # every window on a display of its own (the night: xvfb-run)

    def step(self, name, args, timeout, folder=None, note="", py=None, wrap=None):
        wrap = self.wrap if wrap is None else wrap
        log = self.out / f"{name}.log"
        print(f"→ {name} …", flush=True)
        t0 = time.monotonic()
        with open(log, "w", encoding="utf-8") as f:
            # each step a process group of its own, and the whole group goes when its
            # time is up or the run is stopped: killing only the child left the tool
            # under xvfb-run running for hours, a window nobody saw (23.10: five tours
            # of the night still alive at six in the evening)
            group = {"creationflags": 0x00000200} if os.name == "nt" else \
                {"start_new_session": True}  # CREATE_NEW_PROCESS_GROUP
            proc = subprocess.Popen(list(wrap) + [py or sys.executable] + args, cwd=ROOT,
                                    env=env(), stdout=f, stderr=subprocess.STDOUT, **group)
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                kill_tree(proc)
                code = "timeout"
            except BaseException:  # Ctrl+C, the terminal closed: the step goes too
                kill_tree(proc)
                raise
        took = time.monotonic() - t0
        problems = ""
        if folder is not None and (folder / "errors.txt").exists():
            text = (folder / "errors.txt").read_text("utf-8").strip()
            problems = "" if text == "none" else text
        state = "ok" if code == 0 and not problems else f"problems (exit {code})"
        print(f"  {state}, {took:.0f} s", flush=True)
        self.rows.append((name, state, took, note, problems, log, folder))

    def skip(self, name, why):
        print(f"→ {name}: skipped — {why}", flush=True)
        self.rows.append((name, "skipped", 0, why, "", None, None))


def tail(path, n):
    try:
        lines = path.read_text("utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n:])


def test_failures(log):
    """The names of the tests that failed or erred, and the slowest ones (unittest -v
    and --durations)."""
    try:
        text = log.read_text("utf-8", errors="replace")
    except OSError:
        return []
    bad = re.findall(r"^(test\w+ \([\w.]+\)) \.\.\. .*?(FAIL|ERROR)$", text, re.M | re.S)
    heads = re.findall(r"^(?:FAIL|ERROR): (test\w+ \([\w.]+\))", text, re.M)
    slow = re.search(r"Slowest test durations\n-+\n(.*?)(?:\n\n|\Z)", text, re.S)
    hang = re.search(r"Timeout \(\d+:\d+:\d+\)!.*?(?:\n\n|\Z)", text, re.S)
    out = [f"failed: {h}" for h in dict.fromkeys(heads or [b[0] for b in bad])]
    if hang:
        out.append("HUNG — where (faulthandler):\n" + hang.group(0)[:4000])
    if slow:
        out.append("the slowest:\n" + slow.group(1)[:2000])
    return out


def report(run, out, facts, interrupted=False):
    md = ["# fedtail self-check", ""]
    if interrupted:
        md += ["**STOPPED BY HAND — not a result: the failures below may be the stop "
               "itself.**", ""]
    md += [f"- {k}: {v}" for k, v in facts]
    md += ["", "| step | result | time | |", "|---|---|---|---|"]
    for name, state, took, note, *_ in run.rows:
        md.append(f"| {name} | {state} | {took:.0f} s | {note} |")
    for name, state, _, _, problems, log, folder in run.rows:
        if state == "skipped":
            continue
        md += ["", f"## {name}", ""]
        if problems:
            md += ["Problems (errors.txt):", "", "```", problems[:8000], "```", ""]
        if name == "tests":
            md += ["```", "\n\n".join(test_failures(log)) or "all passed", "```", ""]
        for extra in ("sizes.txt", "leaks.txt", "notes.txt"):
            f = folder / extra if folder else None
            if f is not None and f.exists() and f.read_text("utf-8").strip():
                md += [f"{extra}:", "", "```", f.read_text("utf-8")[:5000], "```", ""]
        if name.startswith("bench") or state != "ok":
            md += ["Log, the end:", "", "```", tail(log, 160 if name.startswith("bench")
                                                   else 40), "```"]
    behaviour = out / "behaviour.md"
    if behaviour.exists():
        md += ["", "## behaviour (all of it in behaviour.md)", "",
               behaviour.read_text("utf-8")[:6000]]
    parity = out / "parity.md"
    if parity.exists():
        head = parity.read_text("utf-8").split("\n## ", 1)[0]
        md += ["", "## parity (all of it in parity.md)", "", head]
    (out / "report.md").write_text("\n".join(md) + "\n", "utf-8")


# ---- your own account's screenshots: blurred -----------------------------------------
def blur(folder):
    """The words in the screenshots of your own feed made unreadable, the layout kept:
    PNGs blurred, the terminal's SVGs with their letters masked."""
    done = 0
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        Image = None  # noqa: N806
    for p in folder.rglob("*.png"):
        if Image is None:
            p.unlink()  # no Pillow to blur with: not kept at all
            continue
        try:
            im = Image.open(p)
            im.filter(ImageFilter.GaussianBlur(3.2)).save(p)
            done += 1
        except OSError:
            p.unlink()
    for p in folder.rglob("*.svg"):
        t = p.read_text("utf-8", errors="replace")
        t = re.sub(r"(<text[^>]*>)(.*?)(</text>)",
                   lambda m: m.group(1) + _mask(m.group(2)) + m.group(3), t,
                   flags=re.S)
        p.write_text(t, "utf-8")
        done += 1
    return done


def _mask(markup):
    """Letters → ▒ in the text of markup, its tags (a <tspan>) left alone."""
    return re.sub(r"(^|>)([^<]*)", lambda m: m.group(1) + re.sub(r"\w", "▒", m.group(2)),
                  markup)


# ---- tidying up ------------------------------------------------------------------------
# the temporary folders the tools make (each a fake profile; with --real a copy of your
# login and database): gone after a run, and by --clean after a run that was killed
TEMP_PREFIXES = ("fedtail-tour-", "fedtail-web-", "fedtail-tui-", "fedtail-bench-",
                 "fedtail-qtbench-", "fedtail-gallery-", "fedtail-shots-",
                 "fedtail-gtk-shots-")


def clean_temp(since=None):
    """The tools' temporary folders (made since `since`, or all of them)."""
    n = 0
    for p in Path(tempfile.gettempdir()).iterdir():
        try:
            if p.is_dir() and p.name.startswith(TEMP_PREFIXES) and \
                    (since is None or p.stat().st_mtime >= since - 5):
                shutil.rmtree(p, ignore_errors=True)
                n += 1
        except OSError:
            pass
    return n


LOGS = Path.home() / "fedtail_log"  # every run: a folder DATE_TIME of its own in here
STAMP = re.compile(r"\d{4}-\d\d-\d\d_\d\d-\d\d(-\d+)?$")


def zip_of(run_dir):
    return run_dir / f"fedtail-selfcheck-{run_dir.name}.zip"


def runs(where):
    """The runs' folders here: DATE_TIME (and the old selfcheck-DATE ones)."""
    return sorted(d for d in where.iterdir() if d.is_dir() and
                  (STAMP.match(d.name) or d.name.startswith("selfcheck-"))) \
        if where.is_dir() else []


def finished(d):
    return not (d / "INTERRUPTED").exists() and (
        zip_of(d).exists() or d.with_suffix(".zip").exists())


TOOLS = ("qt_tour.py", "gtk_screenshots.py", "qt_bench.py", "gtk_bench.py", "tui_check.py",
         "web_check.py", "tabs_stress.py", "behaviour.py", "windows_check.py")


def leftovers():
    """[(pid, command)] of tools of an earlier run still alive (Linux: /proc) — a step
    stopped the old way left its tool running, unseen, for hours."""
    out = []
    proc = Path("/proc")
    if not proc.is_dir():
        return out
    for d in proc.iterdir():
        if not d.name.isdigit() or int(d.name) == os.getpid():
            continue
        try:
            argv = (d / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        words = [a.decode("utf-8", "replace") for a in argv if a]
        if any(w.endswith(("tools/" + t, "tools\\" + t)) for w in words for t in TOOLS) \
                and not any(w.endswith("tools/selfcheck.py") for w in words):
            out.append((int(d.name), " ".join(words)[:160]))
    return out


def clean(where, everything):
    """Runs that didn't finish (stopped, killed, a crash: no zip, or INTERRUPTED in
    it) — or, with everything, every run here — and the tools' temporary folders."""
    gone = []
    for d in runs(where):
        if everything or not finished(d):
            shutil.rmtree(d, ignore_errors=True)
            d.with_suffix(".zip").unlink(missing_ok=True)
            gone.append(d.name + "/")
    stray = leftovers()
    import signal
    for pid, _cmd in stray:  # tools of runs stopped before: gone too
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    n = clean_temp()
    print("removed: " + (", ".join(gone) or "no runs") + f"; temporary folders: {n}"
          + (f"; tools left running by earlier runs, stopped: {len(stray)}" if stray else ""))
    left = [d.name for d in runs(where)]
    if left:
        print("kept (finished): " + ", ".join(left) + "  — --clean all removes them too")
    return 0


def logged_in(profile):
    """Whether the profile (the main one: "") has a login on this machine."""
    ok, where = probe("from fedtail.core import paths; "
                      f"p = paths.resolve({profile!r} or None); "
                      "print(p.profile if p.auth_file.exists() else '')")
    return where if ok and where else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out", nargs="?",
                    help="the run's folder (default: ~/fedtail_log/DATE_TIME)")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--night", action="store_true",
                    help="everything: every theme, every layout, maximized too, slower "
                         "waits, and your own account when one is logged in")
    ap.add_argument("--only", help="comma-separated: " + " ".join(STEPS))
    ap.add_argument("--offscreen", action="store_true",
                    help="Qt without the desktop (nothing flashes; plainer look)")
    ap.add_argument("--maximized", action="store_true", help="windows as big as the screen")
    ap.add_argument("--pace", type=float, default=None,
                    help="the Qt walk's waits that many times longer (a slow machine)")
    ap.add_argument("--real", nargs="?", const="", metavar="PROFILE",
                    help="also on your own account, read-only (the main profile, or this)")
    ap.add_argument("--no-real", action="store_true", help="--night without your account")
    ap.add_argument("--no-blur", action="store_true",
                    help="your account's screenshots as they are")
    ap.add_argument("--clean", nargs="?", const="unfinished", choices=("unfinished", "all"),
                    help="remove the runs that didn't finish (stopped by hand, killed) and "
                         "the tools' temporary folders; --clean all: every run here")
    a = ap.parse_args()
    if a.clean:
        return clean(Path(a.out).resolve() if a.out else LOGS, a.clean == "all")
    if a.night and a.quick:
        ap.error("--night or --quick, not both")
    pace = a.pace if a.pace is not None else (2.0 if a.night else 1.0)
    only = set((a.only or ",".join(STEPS)).split(","))
    if a.out:
        out = Path(a.out).expanduser().resolve()
    else:
        out = LOGS / time.strftime("%Y-%m-%d_%H-%M")
        n = 1
        while out.exists():  # two runs in one minute: each its own
            n += 1
            out = LOGS / (time.strftime("%Y-%m-%d_%H-%M") + f"-{n}")
    out.mkdir(parents=True, exist_ok=True)
    print(f"this run: {out}", flush=True)
    stray = leftovers()
    if stray:
        print(f"tools of earlier runs still running ({len(stray)}): they slow this one "
              "down and hold windows nobody sees — python3 tools/selfcheck.py --clean "
              "stops them\n  " + "\n  ".join(f"{p}: {c}" for p, c in stray), flush=True)
    stale = [d.name for d in runs(out.parent) if d != out and not finished(d)]
    if stale:
        print("unfinished runs here (not results): " + ", ".join(stale) +
              " — python3 tools/selfcheck.py --clean", flush=True)
    run = Run(out)
    started = time.time()

    def stop(*_a):  # killed, the terminal closed: as Ctrl+C
        raise KeyboardInterrupt
    import signal
    for sig in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        if hasattr(signal, sig):
            signal.signal(getattr(signal, sig), stop)
    try:

        ok_v, version = probe("import fedtail; print(getattr(fedtail, '__version__', '?'))")
        git = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True)
        qt, qt_v = probe("import PySide6, PySide6.QtCore as c; print(PySide6.__version__)")
        gtk, gtk_v = probe("import gi; gi.require_version('Gtk', '4.0'); "
                           "from gi.repository import Gtk; "
                           "print(f'{Gtk.get_major_version()}.{Gtk.get_minor_version()}')")
        tui, tui_v = probe("import textual; print(textual.__version__)")
        pil, pil_v = probe("import PIL; print(PIL.__version__)")
        pw, pw_v = probe("import playwright; from importlib.metadata import version; "
                         "print(version('playwright'))")
        # no Playwright in the system's Python (Debian: no pip there): the dev tools' own
        # environment (tools/devenv.py) runs the web walk and the gallery
        web_py = None
        if not pw:
            sys.path.insert(0, str(ROOT / "tools"))
            import devenv
            if devenv.python() is not None:
                web_py = str(devenv.python())
                pw, pw_v = True, "in " + str(devenv.where())
        want_real = a.real if a.real is not None else ("" if a.night and not a.no_real else None)
        real_profile = logged_in(want_real) if want_real is not None else ""
        facts = [("fedtail", f"{version} ({git.stdout.strip() or 'no git'})"),
                 ("Python", f"{platform.python_version()} {sys.executable}"),
                 ("system", f"{platform.platform()}"),
                 ("desktop", os.environ.get("XDG_CURRENT_DESKTOP", "") +
                  (" wayland" if os.environ.get("WAYLAND_DISPLAY") else "") +
                  (" x11" if os.environ.get("DISPLAY") else "")),
                 ("PySide6", qt_v if qt else "no"), ("GTK 4", gtk_v if gtk else "no"),
                 ("Textual", tui_v if tui else "no"), ("Pillow", pil_v if pil else "no"),
                 ("Playwright", pw_v if pw else "no"),
                 ("mode", "night" if a.night else "quick" if a.quick else "full"),
                 ("your account", (f"profile {real_profile}, read-only, screenshots "
                                   + ("as they are" if a.no_blur else "blurred"))
                  if real_profile else ("not asked" if want_real is None
                                        else "no logged-in profile here"))]
        for k, v in facts:
            print(f"{k}: {v}")
        quick = ["--quick"] if a.quick else []
        xvfb = shutil.which("xvfb-run") if sys.platform.startswith("linux") else None
        if a.night and xvfb:
            # at night the screen locks: GTK then draws a frame a second and every
            # bench waits a second a turn (the night of 22.10: 2 h, timed out), a
            # tour's shots come out empty. A display of its own never locks.
            run.wrap = [xvfb, "-a", "-s", "-screen 0 3840x2160x24"]  # room for 4K
            print("windows: on xvfb (the night: the screen locks)")
        elif a.night:
            print("windows: on this desktop — no xvfb-run (sudo apt install xvfb): keep "
                  "the screen from locking for the night, or the benches mean nothing")
        native = (has_display() or bool(run.wrap)) and not a.offscreen
        if a.night and sys.version_info >= (3, 12):
            # every step counts which lines of fedtail/ ran — the tests, the tours, the
            # windows they open; the coverage step at the end puts it together
            COVERAGE[:] = [out / "coverage" / "hits"]
            print("coverage: every step counts the lines it runs")

        # ---- the fake server --------------------------------------------------------------
        if "tests" in only:
            py = sys.version_info
            cmd = ["-X", "faulthandler", "-c",
                   "import faulthandler, sys, unittest; "
                   "faulthandler.dump_traceback_later(1500, exit=True); "  # a hang: where
                   "sys.argv = ['unittest', 'discover', '-s', 'tests', '-t', '.', '-v'"
                   + (", '--durations', '15'" if py >= (3, 12) else "") + "]; "
                   "unittest.main(module=None)"]
            # a display of their own where there's xvfb-run: on the desktop another
            # window takes the focus (or the screen locks at night) and the tests of
            # "seen in the active window" can't see anything
            xvfb = shutil.which("xvfb-run") if sys.platform.startswith("linux") else None
            run.step("tests", cmd, timeout=1800,
                     wrap=[xvfb, "-a", "-s", "-screen 0 1600x1000x24"] if xvfb else (),
                     note="xvfb" if xvfb else "this desktop")
        if "qt" in only:
            if not qt:
                run.skip("qt-tour", "no PySide6 (pip install PySide6)")
            else:
                d = out / "qt-tour"
                run.step("qt-tour", ["tools/qt_tour.py", str(d)] + quick
                         + (["--native"] if native else [])
                         + (["--maximized"] if a.maximized else [])
                         + ["--pace", str(pace)], timeout=5400, folder=d,
                         note="native" if native else "offscreen")
                if a.night and native:
                    d = out / "qt-tour-maximized"
                    run.step("qt-tour-maximized", ["tools/qt_tour.py", str(d), "--quick",
                                                   "--native", "--maximized", "--pace",
                                                   str(pace)], timeout=3600, folder=d,
                             note="maximized")
                if a.night:  # a HiDPI screen: 150 % and 200 % in the desktop's settings
                    for scale in ("1.5", "2"):
                        d = out / f"qt-tour-x{scale}"
                        run.step(f"qt-tour-x{scale}",
                                 ["tools/qt_tour.py", str(d), "--quick", "--scale", scale,
                                  "--pace", str(pace)]
                                 + (["--native"] if native else []),
                                 timeout=3600, folder=d, note=f"scale {scale}")
        if "bench" in only:
            big = ["--maximized"] if a.maximized else []
            if qt and has_display():
                run.step("bench-qt", ["tools/qt_bench.py"] +
                         (["--layout", "split", "--theme", "qip-retro"] if a.quick else [])
                         + big + (["--posts", "4000"] if a.night else []), timeout=7200)
            else:
                run.skip("bench-qt", "no PySide6" if not qt else "no desktop to measure on")
            if gtk:
                run.step("bench-gtk", ["tools/gtk_bench.py"] +
                         (["--layout", "split", "--theme", "qip-retro"] if a.quick else [])
                         + big + (["--posts", "4000"] if a.night else []), timeout=7200)
            else:
                run.skip("bench-gtk", "no GTK 4 (python3-gi, gir1.2-gtk-4.0)")
        if "gtk" in only:
            if gtk:
                d = out / "gtk-shots"
                run.step("gtk-shots", ["tools/gtk_screenshots.py", str(d)] +
                         (["system", "point", "qip-retro"] if a.quick else []), timeout=3600)
                # the window at the sizes of real screens and at shares of the screen,
                # plain, at twice the pixels, and with the text 1.5× (sizes.txt each)
                for tag, extra in (("", []), ("-x2", ["--scale", "2"]),
                                   ("-dpi1.5", ["--dpi", "1.5"]))[:1 if a.quick else 3]:
                    d = out / f"gtk-sizes{tag}"
                    run.step(f"gtk-sizes{tag}", ["tools/gtk_screenshots.py", str(d),
                                                 "system", "--sizes"] + extra,
                             timeout=1800, folder=d, note=" ".join(extra))
            else:
                run.skip("gtk-shots", "no GTK 4 (python3-gi, gir1.2-gtk-4.0)")
        if "tui" in only:
            if tui:
                d = out / "tui"
                run.step("tui", ["tools/tui_check.py", str(d)], timeout=900, folder=d,
                         note="" if pil else "no Pillow: no pictures in the terminal")
            else:
                run.skip("tui", "no Textual (pip install textual)")
        if "web" in only:
            d = out / "web"
            run.step("web", ["tools/web_check.py", str(d)], timeout=900, folder=d, py=web_py,
                     note="Playwright" if pw else "no Playwright: no walk "
                     "(python3 tools/devenv.py — once)")
        if "windows" in only and sys.platform == "win32":  # docs/WINDOWS.md, done here
            d = out / "windows"
            run.step("windows", ["tools/windows_check.py", str(d)], timeout=1200, folder=d,
                     note="docs/WINDOWS.md in a profile of its own")
        if "behaviour" in only:  # the same scenario through every interface here
            cmd = ["tools/behaviour.py", str(out / "behaviour.md")]
            wrap = run.wrap or (["xvfb-run", "-a"] if sys.platform.startswith("linux") and
                                not has_display() and shutil.which("xvfb-run") else ())
            run.step("behaviour", cmd, timeout=900, wrap=wrap)  # GTK needs a display
        if "tabs" in only:  # many tabs opened and closed, round after round: leaks, time
            rounds, many = (("3", "15") if a.quick else ("20", "40") if a.night
                            else ("6", "30"))
            for ui, have in (("qt", qt), ("gtk", gtk), ("tui", tui)):
                if not have:
                    run.skip(f"tabs-{ui}", f"no {ui}")
                    continue
                d = out / f"tabs-{ui}"
                run.step(f"tabs-{ui}", ["tools/tabs_stress.py", str(d), "--ui", ui,
                                        "--rounds", rounds, "--tabs", many]
                         + (["--native"] if ui == "qt" and native else []),
                         timeout=3600, folder=d, note=f"{rounds} rounds × {many}")
                if a.night and ui != "tui":  # the split layout's tabs are its own
                    d = out / f"tabs-{ui}-split"
                    run.step(f"tabs-{ui}-split", ["tools/tabs_stress.py", str(d), "--ui", ui,
                                                  "--rounds", "8", "--tabs", many,
                                                  "--layout", "split", "--theme", "qip-retro"]
                             + (["--native"] if ui == "qt" and native else []),
                             timeout=3600, folder=d, note="split, qip-retro")
        if "themes" in only:  # after the tours: each theme's Qt and GTK pictures compared
            if pil and (out / "qt-tour").is_dir() and (out / "gtk-shots").is_dir():
                d = out / "themes"
                run.step("themes", ["tools/theme_compare.py", str(out), str(d)],
                         timeout=900, folder=d, note="Qt and GTK side by side")
            else:
                run.skip("themes", "needs Pillow and both the Qt tour and the GTK shots")
        if "parity" in only:  # after the walks: their menus go side by side
            run.step("parity", ["tools/parity.py", str(out / "parity.md")], timeout=300)
        # the gallery (tools/gallery.py): only asked by name (--only gallery) — the
        # pictures change seldom, the night has better things to do
        if "gallery" in only and a.only:
            run.step("gallery", ["tools/gallery.py", str(out / "gallery")], timeout=1800,
                     py=web_py, note="the site's and the docs' pictures (built-in themes only)")

        # ---- your own account -------------------------------------------------------------
        if real_profile:
            flag = [f"--real={real_profile}"]
            # every step on your account waits for room in the server's rate limit first
            real_step = run.step

            def gated(name, args, *a, **k):
                if name.startswith("real-"):
                    subprocess.run([sys.executable, "tools/real.py",
                                    f"--wait={real_profile}"], cwd=ROOT, env=env(),
                                   timeout=900, check=False)
                return real_step(name, args, *a, **k)
            run.step = gated
            r = out / "real"
            r.mkdir(exist_ok=True)
            if "qt" in only and qt:
                d = r / "qt-tour"
                run.step("real-qt-tour", ["tools/qt_tour.py", str(d), "--quick"]
                         + (["--native"] if native else []) + ["--pace", str(max(pace, 2.0))]
                         + flag, timeout=3600, folder=d, note="your account")
            if "bench" in only and qt and has_display():
                for layout, theme in (("single", "system"), ("split", "qip-retro")):
                    run.step(f"real-bench-qt-{layout}",
                             ["tools/qt_bench.py", "--layout", layout, "--theme", theme] + flag,
                             timeout=1800, note="your account")
            if "bench" in only and gtk:
                run.step("real-bench-gtk", ["tools/gtk_bench.py", "--layout", "single",
                                            "--theme", "system"] + flag, timeout=1800,
                         note="your account")
            if "tui" in only and tui:
                d = r / "tui"
                run.step("real-tui", ["tools/tui_check.py", str(d)] + flag, timeout=900,
                         folder=d, note="your account")
            if "web" in only:
                d = r / "web"
                run.step("real-web", ["tools/web_check.py", str(d)] + flag, timeout=900,
                         folder=d, note="your account", py=web_py)
            if "tabs" in only:
                for ui, have in (("qt", qt), ("gtk", gtk), ("tui", tui)):
                    if have:
                        d = r / f"tabs-{ui}"
                        run.step(f"real-tabs-{ui}",
                                 ["tools/tabs_stress.py", str(d), "--ui", ui, "--rounds",
                                  "6" if a.night else "3", "--tabs", "30"] + flag
                                 + (["--native"] if ui == "qt" and native else []),
                                 timeout=3600, folder=d, note="your account")
            if not a.no_blur:
                n = blur(r)
                print(f"your account's screenshots: {n} blurred", flush=True)

    except KeyboardInterrupt:
        # stopped by hand: what is half done says nothing — no zip to send, the
        # folder marked, the temporary copies (your login among them) gone
        (out / "INTERRUPTED").write_text("stopped by hand; not a result\n", "utf-8")
        report(run, out, facts, interrupted=True)
        clean_temp(started)
        print(f"\nstopped. Nothing to send from {out}; "
              "python3 tools/selfcheck.py --clean removes it.")
        return 130
    if COVERAGE:
        COVERAGE.clear()  # the report itself is not counted
        d = out / "coverage"
        run.step("coverage", ["tools/coverage_lite.py", str(d), "--report"], timeout=900,
                 folder=d, note="lines of fedtail/ the whole night ran", wrap=())
        shutil.rmtree(d / "hits", ignore_errors=True)  # put together: lines.json has it
    clean_temp(started)
    report(run, out, facts)
    archive = zip_of(out)  # in the run's own folder, next to what it holds
    part = archive.with_suffix(".part")
    with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob("*")):
            if p.is_file() and p not in (archive, part):
                z.write(p, p.relative_to(out.parent))
    part.replace(archive)  # there only when whole: a zip here = the run finished
    # and a small one: the words only (logs, reports, menus) — what a chat takes when
    # the whole is too big, and most of what's needed to read the night
    light = archive.with_name(archive.stem + "-text.zip")
    with zipfile.ZipFile(light, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob("*")):
            if p.is_file() and p.suffix in (".md", ".txt", ".log", ".json", ".toml"):
                z.write(p, p.relative_to(out.parent))
    print(f"\nreport: {out / 'report.md'}\nto send back: {archive} "
          f"({archive.stat().st_size / 2**20:.0f} MB)\n  too big? the words only: {light} "
          f"({light.stat().st_size / 2**20:.1f} MB)")
    return 0 if all(r[1] in ("ok", "skipped") for r in run.rows) else 1


if __name__ == "__main__":
    sys.exit(main())
