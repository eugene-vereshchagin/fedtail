"""Everything the dev tools can check, in one go, on this machine: the tests, a walk
through every interface that can run here (Qt, GTK, the terminal, the web) with
screenshots and the inventory of the menus, and how fast the windows are. Your config
and data are not touched: each step runs on a fake server in a temporary folder.

    python3 tools/selfcheck.py                 # all of it (10–30 minutes)
    python3 tools/selfcheck.py --quick         # a few themes, one layout (3–5 minutes)
    python3 tools/selfcheck.py --only qt,web   # some of the steps: tests qt bench gtk tui web

What can't run here (no PySide6, no GTK, no Textual, no browser) is skipped and said
so. At the end: report.md in the folder and one zip of all of it, to send back.
Works on Linux, Windows and macOS (GTK: Linux only)."""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS = ("tests", "qt", "bench", "gtk", "tui", "web")


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

    def step(self, name, args, timeout, folder=None, note=""):
        log = self.out / f"{name}.log"
        print(f"→ {name} …", flush=True)
        t0 = time.monotonic()
        try:
            with open(log, "w", encoding="utf-8") as f:
                code = subprocess.run([sys.executable] + args, cwd=ROOT, env=env(),
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
        self.rows.append((name, state, took, note, problems, log))

    def skip(self, name, why):
        print(f"→ {name}: skipped — {why}", flush=True)
        self.rows.append((name, "skipped", 0, why, "", None))


def tail(path, n):
    try:
        lines = path.read_text("utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n:])


def report(run, out, facts):
    md = ["# fedtail self-check", ""]
    md += [f"- {k}: {v}" for k, v in facts]
    md += ["", "| step | result | time | |", "|---|---|---|---|"]
    for name, state, took, note, _, _ in run.rows:
        md.append(f"| {name} | {state} | {took:.0f} s | {note} |")
    for name, state, _, _, problems, log in run.rows:
        if state == "skipped":
            continue
        md += ["", f"## {name}", ""]
        if problems:
            md += ["Problems (errors.txt):", "", "```", problems[:6000], "```", ""]
        if name.startswith("bench") or name == "tests" or state != "ok":
            md += ["Log, the end:", "", "```", tail(log, 120 if name.startswith("bench")
                                                   else 40), "```"]
    (out / "report.md").write_text("\n".join(md) + "\n", "utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out", nargs="?", help="the folder (default: selfcheck-DATE here)")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--only", help="comma-separated: " + " ".join(STEPS))
    ap.add_argument("--offscreen", action="store_true",
                    help="Qt without the desktop (nothing flashes; plainer look)")
    a = ap.parse_args()
    only = set((a.only or ",".join(STEPS)).split(","))
    out = Path(a.out or "selfcheck-" + time.strftime("%Y%m%d-%H%M")).resolve()
    out.mkdir(parents=True, exist_ok=True)
    run = Run(out)

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
    facts = [("fedtail", f"{version} ({git.stdout.strip() or 'no git'})"),
             ("Python", f"{platform.python_version()} {sys.executable}"),
             ("system", f"{platform.platform()}"),
             ("desktop", os.environ.get("XDG_CURRENT_DESKTOP", "") +
              (" wayland" if os.environ.get("WAYLAND_DISPLAY") else "") +
              (" x11" if os.environ.get("DISPLAY") else "")),
             ("PySide6", qt_v if qt else "no"), ("GTK 4", gtk_v if gtk else "no"),
             ("Textual", tui_v if tui else "no"), ("Pillow", pil_v if pil else "no"),
             ("Playwright", pw_v if pw else "no")]
    for k, v in facts:
        print(f"{k}: {v}")

    if "tests" in only:
        run.step("tests", ["-m", "unittest", "discover", "-s", "tests", "-t", "."],
                 timeout=1800)
    if "qt" in only:
        if not qt:
            run.skip("qt-tour", "no PySide6 (pip install PySide6)")
        else:
            d = out / "qt-tour"
            native = has_display() and not a.offscreen
            run.step("qt-tour", ["tools/qt_tour.py", str(d)] + (["--quick"] if a.quick else [])
                     + (["--native"] if native else []), timeout=1800, folder=d,
                     note="native" if native else "offscreen")
    if "bench" in only:
        if qt and has_display():
            run.step("bench-qt", ["tools/qt_bench.py"] +
                     (["--layout", "split", "--theme", "qip-retro"] if a.quick else []),
                     timeout=3600)
        else:
            run.skip("bench-qt", "no PySide6" if not qt else "no desktop to measure on")
        if gtk:
            run.step("bench-gtk", ["tools/gtk_bench.py"] +
                     (["--layout", "split", "--theme", "qip-retro"] if a.quick else []),
                     timeout=3600)
        else:
            run.skip("bench-gtk", "no GTK 4 (python3-gi, gir1.2-gtk-4.0)")
    if "gtk" in only:
        if gtk:
            d = out / "gtk-shots"
            run.step("gtk-shots", ["tools/gtk_screenshots.py", str(d)] +
                     (["system", "point", "qip-retro"] if a.quick else []), timeout=1800)
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
        run.step("web", ["tools/web_check.py", str(d)], timeout=900, folder=d,
                 note="Playwright" if pw else "no Playwright: one screenshot at most "
                 "(pip install playwright && playwright install chromium)")

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
