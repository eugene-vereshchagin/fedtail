"""docs/WINDOWS.md, done on this Windows: every command of the page that can run without a
person — in order, in a profile of its own (APPDATA and LOCALAPPDATA point at a
temporary folder: your own fedtail, its shortcut and its logs aren't touched).

    py -3.13 tools/windows_check.py OUT_DIR              # the page, but the tests
    py -3.13 tools/windows_check.py OUT_DIR --tests      # and the whole test run too
    python3 tools/windows_check.py --dry-run             # anywhere: what it would do

What a person does by hand (winget, git clone, opening Explorer, watching a log, the
window itself, the self-check) is said and skipped. Writes OUT_DIR/report.md and
errors.txt ("none" when all went well); the self-check runs it on Windows."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "WINDOWS.md"
SKIP = {  # what a person does: (the first words) → why it isn't run here
    ("winget",): "installs Python and git: done already, this runs in them",
    ("git", "clone"): "the checkout this runs from",
    ("cd",): "the checkout this runs from",
    ("git", "pull"): "would change the checkout under the run",
    ("explorer",): "opens a window",
    ("Get-Content",): "follows the log until stopped",
    ("Remove-Item",): "the environment of this run is its own",
}


def commands():
    """The page's PowerShell lines, as words, in order (the English half repeats the
    Russian one: once is enough)."""
    out, seen = [], set()
    text = DOC.read_text("utf-8")
    for block in re.findall(r"```powershell\n(.*?)```", text, re.S):
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line in seen:
                continue
            seen.add(line)
            out.append(line)
    return out


def plan(line):
    """(what to run as argv, or None; why not / what it checks)."""
    if line.startswith("$env:"):
        return None, "environment: set for each command here"
    words = shlex.split(line, posix=False)
    for head, why in SKIP.items():
        if tuple(words[:len(head)]) == head:
            return None, why
    if words[0] == "git" and words[1:] == ["--version"]:
        return ["git", "--version"], "git is there"
    if words[0] != "py":
        return None, "not a command of fedtail's"
    rest = words[1:]
    if rest and rest[0].startswith("-3"):
        rest = rest[1:]
    if rest == ["--version"]:
        return [sys.executable, "--version"], "Python is there"
    if rest[:3] == ["-m", "pip", "install"]:
        pkgs = [x for x in rest[3:] if not x.startswith("-")]
        mods = {"PySide6-Essentials": "PySide6", "requests": "requests",
                "textual": "textual", "cryptography": "cryptography"}
        code = "; ".join(f"import {mods.get(p, p)}" for p in pkgs)
        return [sys.executable, "-c", code], "the packages are installed: " + " ".join(pkgs)
    if rest == ["-m", "fedtail"]:
        return [sys.executable, "-m", "fedtail", "--version"], \
            "starts (the window itself: by hand)"
    if "tools/windows_check.py" in rest:
        return None, "this very check"
    if "tools/devenv.py" in rest or any("selfcheck" in x for x in rest):
        return None, "the self-check: run by hand (it runs this, too)"
    if "unittest" in rest:
        return [sys.executable] + rest, "the tests, as CI runs them on Windows"
    return [sys.executable] + rest, "as written"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    with_tests = "--tests" in sys.argv
    out = Path(args[0] if args else "windows-check")
    lines, errors = ["# docs/WINDOWS.md, done here", "",
                     f"Python {sys.version.split()[0]} · {sys.platform}", "",
                     "| command | what | result |", "|---|---|---|"], []
    if sys.platform != "win32" and not dry:
        print("not Windows: --dry-run shows what it would do")
        return 0
    tmp = tempfile.mkdtemp(prefix="fedtail-windows-")
    home = Path(tmp) / "home"  # the bug report goes to the home folder: this one
    home.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, APPDATA=str(Path(tmp) / "Roaming"),
               LOCALAPPDATA=str(Path(tmp) / "Local"), USERPROFILE=str(home), HOME=str(home),
               PYTHONIOENCODING="utf-8", QT_QPA_PLATFORM="offscreen")
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME"):
        env.pop(var, None)
    for line in commands():
        argv, why = plan(line)
        if argv is None:
            lines.append(f"| `{line}` | {why} | skipped |")
            continue
        if "unittest" in argv and not with_tests:
            lines.append(f"| `{line}` | {why} | skipped (--tests) |")
            continue
        if dry:
            lines.append(f"| `{line}` | {why} | would run `{' '.join(argv[1:])}` |")
            continue
        t0 = time.monotonic()
        try:
            r = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               timeout=3600 if "unittest" in argv else 300)
            ok, said = r.returncode == 0, (r.stdout + r.stderr).strip()
        except (OSError, subprocess.TimeoutExpired) as e:
            ok, said = False, str(e)
        took = time.monotonic() - t0
        lines.append(f"| `{line}` | {why} | {'ok' if ok else 'FAILED'}, {took:.0f} s |")
        if not ok:
            errors.append(f"$ {line}\n{said[-4000:]}")
        if "--install-desktop" in argv and ok:  # the shortcut is where the page says
            link = Path(env["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/fedtail.lnk"
            if not link.exists():
                errors.append(f"$ {line}\nno {link}")
        if "--bug-report" in argv and ok and "tar.gz" not in said:
            errors.append(f"$ {line}\nthe report's path wasn't said:\n{said[-1000:]}")
    lines += ["", f"Profile folders of this run: {tmp}"]
    if not dry:
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.md").write_text("\n".join(lines) + "\n", "utf-8")
        (out / "errors.txt").write_text("\n\n".join(errors) + "\n" if errors else "none\n",
                                        "utf-8")
    print("\n".join(lines))
    if errors:
        print(f"\n{len(errors)} problems: {out / 'errors.txt'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
