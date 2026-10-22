"""Everything the dev tools can check, in one go, on this machine: the tests, a walk
through every interface that can run here (Qt, GTK, the terminal, the web) with
screenshots, every menu and the window at every size, how fast the windows are, and
whether the four interfaces offer the same things. Then — if this machine has a
logged-in fedtail — the same on your own account (a copy, read-only).

    python3 tools/selfcheck.py --night         # all of it, for the night (1–3 hours)
    python3 tools/selfcheck.py                 # the fake server only (20–40 minutes)
    python3 tools/selfcheck.py --quick         # a few themes, one layout (3–5 minutes)
    python3 tools/selfcheck.py --only qt,web   # some steps: tests qt bench gtk tui web parity
    python3 tools/selfcheck.py --real          # and your account too (--real=PROFILE)
    python3 tools/selfcheck.py --only gallery  # the site's and the docs' pictures only
    python3 tools/selfcheck.py --clean         # after Ctrl+C: the unfinished runs gone
    python3 tools/selfcheck.py --clean all     # every run here

Your account (--real, and --night when a profile is logged in): a copy of the
profile's config, login and database in a temporary folder; only GET goes to the
server — nothing is posted, liked, followed or marked read there (tools/real.py). Its
screenshots are blurred (the layout stays, the words don't) unless --no-blur; the
terminal's have their letters masked.

What can't run here (no PySide6, no GTK, no Textual, no Playwright) is skipped and said
so. At the end: report.md in the folder and one zip of all of it, to send back.
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
STEPS = ("tests", "qt", "bench", "gtk", "tui", "web", "parity", "gallery")


def probe(code):
    """Whether this Python can do it (in a child: a crash in a binding stays there)."""
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       timeout=120, cwd=ROOT, env=env())
    if r.returncode == 0:
        return True, r.stdout.strip()
    last = r.stderr.strip().splitlines()
    return False, last[-1] if last else ""


def env():
    e = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    e["PYTHONPATH"] = str(ROOT) + os.pathsep + e.get("PYTHONPATH", "")
    return e


def has_display():
    return os.name == "nt" or sys.platform == "darwin" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


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
        try:
            with open(log, "w", encoding="utf-8") as f:
                code = subprocess.run(list(wrap) + [py or sys.executable] + args,
                                      cwd=ROOT, env=env(),
                                      stdout=f, stderr=subprocess.STDOUT,
                                      timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
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


def clean(where, everything):
    """Runs that didn't finish (stopped, killed, a crash: no zip, or INTERRUPTED in
    it) — or, with everything, every run here — and the tools' temporary folders."""
    gone = []
    for d in sorted(where.glob("selfcheck-*")):
        if d.is_dir():
            unfinished = (d / "INTERRUPTED").exists() or not d.with_suffix(".zip").exists()
            if everything or unfinished:
                shutil.rmtree(d, ignore_errors=True)
                gone.append(d.name + "/")
        elif d.suffix == ".zip" and everything:
            d.unlink()
            gone.append(d.name)
    n = clean_temp()
    print("removed: " + (", ".join(gone) or "no runs") + f"; temporary folders: {n}")
    left = sorted(p.name for p in where.glob("selfcheck-*"))
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
    ap.add_argument("out", nargs="?", help="the folder (default: selfcheck-DATE here)")
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
        return clean(Path(a.out or ".").resolve(), a.clean == "all")
    if a.night and a.quick:
        ap.error("--night or --quick, not both")
    pace = a.pace if a.pace is not None else (2.0 if a.night else 1.0)
    only = set((a.only or ",".join(STEPS)).split(","))
    out = Path(a.out or "selfcheck-" + time.strftime("%Y%m%d-%H%M")).resolve()
    out.mkdir(parents=True, exist_ok=True)
    stale = [d.name for d in out.parent.glob("selfcheck-*") if d.is_dir() and d != out and
             ((d / "INTERRUPTED").exists() or not d.with_suffix(".zip").exists())]
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
            run.wrap = [xvfb, "-a", "-s", "-screen 0 1920x1080x24"]
            print("windows: on xvfb (the night: the screen locks)")
        elif a.night:
            print("windows: on this desktop — no xvfb-run (sudo apt install xvfb): keep "
                  "the screen from locking for the night, or the benches mean nothing")
        native = (has_display() or bool(run.wrap)) and not a.offscreen

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
        if "parity" in only:  # after the walks: their menus go side by side
            run.step("parity", ["tools/parity.py", str(out / "parity.md")], timeout=300)
        # the gallery (tools/gallery.py): with --night, or asked by --only gallery
        if "gallery" in only and (a.night or a.only):
            run.step("gallery", ["tools/gallery.py", str(out / "gallery")], timeout=1800,
                     py=web_py, note="the site's and the docs' pictures (built-in themes only)")

        # ---- your own account -------------------------------------------------------------
        if real_profile:
            flag = [f"--real={real_profile}"]
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
    clean_temp(started)
    report(run, out, facts)
    archive = out.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(out.parent))
    print(f"\nreport: {out / 'report.md'}\nto send back: {archive}")
    return 0 if all(r[1] in ("ok", "skipped") for r in run.rows) else 1


if __name__ == "__main__":
    sys.exit(main())
