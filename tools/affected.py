"""The tests a change can break, not all two thousand: picked by what the change touches,
so a run takes a minute or two instead of eight. The full run stays for a batch before it
is pushed and for the night's self-check.

    python3 tools/affected.py               # what isn't committed yet
    python3 tools/affected.py --since REF   # and the commits since REF (e.g. @{u}, HEAD~3)
    python3 tools/affected.py --list        # only say which, don't run them

A test is picked when
  * it names a changed module, or a function, class or event the diff touches (a word in
    its source — tests call what they test by name);
  * it covers the changed area: an interface's folder → that interface's tests, the web
    page's script → the web tests, a doc or an example config → the docs' tests;
  * always: the layering, parity and docs checks (a second together), and the scenario
    through every interface (tests/test_behaviour.py) when the core or an interface changed.
GUI tests run under xvfb-run with Qt offscreen: no window opens on the screen."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

ALWAYS = ["test_layering", "test_parity", "test_dev_docs", "test_pure"]
# a path's start → the tests of that area (fnmatch-like: a prefix of the test's name, or
# a part of it after "*")
AREAS = [
    ("fedtail/frontends/qt/", ["test_qt_", "test_kde", "test_parity_common"]),
    ("fedtail/frontends/gtk/", ["test_gtk_", "test_pango", "test_parity_common"]),
    ("fedtail/frontends/tui/", ["*tui", "test_parity_common"]),
    ("fedtail/frontends/web/", ["test_web", "test_cov_web", "test_parity_web",
                                "test_cov_gaps_web", "test_places_api"]),
    ("fedtail/data/web/", ["test_web", "test_cov_web", "test_parity_web", "test_cov_gaps_web"]),
    ("fedtail/frontends/common/", ["test_common", "test_cov_common_", "test_places",
                                   "test_parity_common"]),
    ("fedtail/frontends/cli", ["test_cli", "test_cov_cli"]),
    ("fedtail/core/sync/", ["test_sync"]),
    ("fedtail/core/store", ["test_store", "test_cov_core_store"]),
    ("fedtail/protocols/", ["test_protocols", "test_cov_protocol", "test_api"]),
    ("fedtail/i18n.py", ["test_i18n", "test_android_strings"]),
    ("fedtail/diag.py", ["test_diag", "test_cov_diag", "test_debug_context"]),
    ("fedtail/data/help/", ["test_help"]),
    ("fedtail/data/themes/", ["test_themes", "test_palette"]),
    ("fedtail/data/config.example", ["test_config", "test_settings"]),
    ("fedtail/core/config", ["test_config", "test_settings"]),
    ("docs/", ["test_help", "test_windows_doc"]),
    ("android/", ["test_android_"]),
    ("tools/", ["test_covhook", "test_push_probe", "test_vendor"]),
]
# words too common to tell anything: every test says them
COMMON = {"__init__", "app", "api", "window", "view", "core", "main", "model", "text",
          "card", "lane", "feed", "links", "store", "places", "common", "test", "run",
          "start", "stop", "load", "show", "open", "close", "get", "set", "put", "update",
          "refresh", "reload", "post", "status", "draw", "render", "setUp", "tearDown"}
DEF = re.compile(r"^[+-]\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)")
HUNK = re.compile(r"^@@ [^@]* @@\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)")
EVENT = re.compile(r"""^[+-].*\b(?:emit|on)\(\s*["']([a-z_]+)["']""")
JSFN = re.compile(r"^[+-]\s*(?:async\s+)?function\s+([A-Za-z_]\w*)")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=False).stdout


def changed(since):
    """(paths changed, the diff's text): what isn't committed, and since `since` if given."""
    ranges = [["HEAD"]] + ([[since, "HEAD"]] if since else [])
    paths, diff = set(), ""
    for r in ranges:
        paths |= set(git("diff", "--name-only", *r).split())
        diff += git("diff", "-U0", *r)
    paths |= set(git("ls-files", "--others", "--exclude-standard").split())
    return sorted(p for p in paths if (ROOT / p).exists() or p.startswith("tests/")), diff


def modules_of(paths):
    """The changed modules, by the dotted name a test imports them by."""
    out = set()
    for p in paths:
        if p.endswith(".py") and p.startswith("fedtail/"):
            parts = Path(p).with_suffix("").parts
            out.add(".".join(parts[:-1] if parts[-1] == "__init__" else parts))
    return out


def words_of(diff):
    """The names a test would say: the functions, classes, events and script functions
    the diff touches (a test's own names aside: a changed test runs anyway)."""
    words = set()
    for line in diff.splitlines():
        for rx in (DEF, HUNK, EVENT, JSFN):
            m = rx.match(line)
            if m:
                words.add(m.group(1))
    return {w for w in words if len(w) > 3 and w not in COMMON
            and not w.startswith("test_") and not w.endswith("Test")}


def all_tests():
    return sorted(p.stem for p in TESTS.glob("test_*.py"))


def by_area(paths, tests):
    out = set()
    for p in paths:
        for start, pats in AREAS:
            if not p.startswith(start):
                continue
            for pat in pats:
                if pat.startswith("*"):
                    out |= {t for t in tests if pat[1:] in t}
                else:
                    out |= {t for t in tests if t.startswith(pat)}
    return out


def by_words(words, tests):
    """Tests that say any of the words; a word an eighth of the tests say is noise."""
    src = {t: (TESTS / f"{t}.py").read_text("utf-8") for t in tests}
    out = set()
    for w in words:
        rx = re.compile(r"\b" + re.escape(w) + r"\b")
        hit = {t for t, text in src.items() if rx.search(text)}
        if len(hit) <= len(tests) // 8:
            out |= hit
    return out


def by_imports(modules, tests):
    """Tests that import a changed module (by its dotted name, or `from pkg import it`);
    one an eighth of the tests import is noise, as a word is."""
    out = set()
    for mod in modules:
        pkg, _, name = mod.rpartition(".")
        rx = re.compile(r"^\s*(?:import\s+" + re.escape(mod) + r"\b|from\s+" + re.escape(mod) +
                        r"\s+import|from\s+" + re.escape(pkg) + r"\s+import\s+[^#\n]*\b" +
                        re.escape(name) + r"\b)", re.M)
        hit = {t for t in tests if rx.search((TESTS / f"{t}.py").read_text("utf-8"))}
        if len(hit) <= len(tests) // 8:  # Core, the fakes: everyone's — the words tell
            out |= hit
    return out


def pick(paths, diff):
    """{test module: why} for this change."""
    tests = all_tests()
    why = {t: "always" for t in ALWAYS if t in tests}
    for t in sorted(by_area(paths, tests)):
        why.setdefault(t, "area")
    for t in sorted(by_imports(modules_of(paths), tests)):
        why.setdefault(t, "imports it")
    for t in sorted(by_words(words_of(diff), tests)):
        why.setdefault(t, "names it")
    for p in paths:  # a test changed: it runs
        if p.startswith("tests/test_") and p.endswith(".py") and Path(p).stem in tests:
            why[Path(p).stem] = "changed"
    if any(p.startswith(("fedtail/core/", "fedtail/frontends/", "fedtail/data/web/"))
           for p in paths):
        why.setdefault("test_behaviour", "core or an interface")
    return why


def run(names):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env.pop("WAYLAND_DISPLAY", None)
    cmd = [sys.executable, "-m", "unittest", *(f"tests.{n}" for n in names)]
    if shutil.which("xvfb-run") and os.name != "nt":
        cmd = ["xvfb-run", "-a", *cmd]
    return subprocess.run(cmd, cwd=ROOT, env=env, check=False).returncode


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--since", help="also the commits since this ref (@{u}, HEAD~3…)")
    ap.add_argument("--list", action="store_true", help="say which, don't run")
    a = ap.parse_args(argv)
    paths, diff = changed(a.since)
    if not paths:
        print("nothing changed")
        return 0
    why = pick(paths, diff)
    total = len(all_tests())
    print(f"{len(paths)} files changed → {len(why)} of {total} test modules:")
    for t, reason in sorted(why.items(), key=lambda x: (x[1], x[0])):
        print(f"  {t:32} {reason}")
    if a.list:
        return 0
    return run(sorted(why))


if __name__ == "__main__":
    sys.exit(main())
