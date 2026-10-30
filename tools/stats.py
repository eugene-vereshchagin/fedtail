"""fedtail in numbers, for the READMEs: how many lines each part is, how many tests, how
much of the code they run. The numbers live in docs/src/stats.toml (docs_build makes the
READMEs' part of them, docs/<lang>/parts/stats.md); this counts them anew and writes them.

    python3 tools/stats.py                    # the numbers now, beside the stored ones
    python3 tools/stats.py --write            # store them (the coverage kept as it was)
                                              # and run docs_build
    python3 tools/stats.py --write --coverage DIR   # …and the coverage of a
                                              # tools/coverage_lite.py run (its notes.txt)

Lines are lines with something on them, comments and docstrings included; the vendored
code (fedtail/_vendor) isn't fedtail's and isn't counted. The self-check's night run
writes them with its coverage (tools/selfcheck.py --night); tests/test_stats.py says when
the stored ones have drifted too far from the code.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATS = ROOT / "docs" / "src" / "stats.toml"

# part -> the files that make it (globs from the repository's root); the first part a
# file falls in has it
PARTS = {
    "qt": ["fedtail/frontends/qt/**/*.py"],
    "gtk": ["fedtail/frontends/gtk/**/*.py"],
    "tui": ["fedtail/frontends/tui/**/*.py"],
    "web": ["fedtail/frontends/web/**/*.py", "fedtail/data/web/*.js",
            "fedtail/data/web/*.css", "fedtail/data/web/*.html"],
    "common": ["fedtail/frontends/**/*.py"],  # common/ and the frontends' shared modules
    "strings": ["fedtail/i18n.py"],
    "core": ["fedtail/**/*.py"],              # core/, protocols/, model/, the rest
    "android": ["android/app/src/main/**/*.kt", "android/app/src/main/**/*.py"],
    "tests": ["tests/**/*.py", "android/app/src/androidTest/**/*.kt"],
    "tools": ["tools/**/*.py", "packaging/**/*.py"],
}
WORKING = ("core", "common", "qt", "gtk", "tui", "web", "android", "strings")
SKIP = ("_vendor", "__pycache__", "/build/", ".gradle")


def _lines(path):
    try:
        return sum(1 for line in path.read_text("utf-8").splitlines() if line.strip())
    except (OSError, UnicodeDecodeError):
        return 0


def count(root=ROOT):
    """{part: lines} and the number of tests (`def test…` in tests/: fewer than run —
    some test classes are made in loops)."""
    seen, out = set(), {}
    for part, globs in PARTS.items():
        n = 0
        for g in globs:
            for p in root.glob(g):
                rel = p.relative_to(root).as_posix()
                if rel in seen or any(s in f"/{rel}" for s in SKIP) or not p.is_file():
                    continue
                seen.add(rel)
                n += _lines(p)
        out[part] = n
    tests = sum(len(re.findall(r"^\s*def test", p.read_text("utf-8"), re.M))
                for p in (root / "tests").rglob("test_*.py"))
    return out, tests


def coverage_of(folder):
    """(the total, the tests run) of a coverage_lite run, from its notes.txt or
    report.md: (87.7, 1968); (None, None) when it says neither."""
    for name in ("notes.txt", "report.md"):
        f = Path(folder) / name
        if f.exists():
            text = f.read_text("utf-8")
            m = re.search(r"total: \**([\d.]+) %", text)
            if m:
                ran = re.search(r"tests: (\d+) run", text)
                return float(m.group(1)), int(ran.group(1)) if ran else None
    return None, None


def load(path=STATS):
    import tomllib
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def write(lines, tests, coverage, path=STATS, today=None):
    today = today or time.strftime("%Y-%m-%d")
    out = ["# fedtail in numbers: written by tools/stats.py --write (the night's self-check",
           "# does it), read by tools/docs_build.py into docs/<lang>/parts/stats.md.",
           f'counted = "{today}"', f"tests = {tests}"]
    if coverage is not None:
        out.append(f"coverage = {coverage}")
    out += ["", "[lines]"] + [f"{k} = {v}" for k, v in lines.items()]
    path.write_text("\n".join(out) + "\n", "utf-8")


def main(argv):
    lines, tests = count()
    old = load()
    cov = old.get("coverage")
    if "--coverage" in argv:
        got, ran = coverage_of(argv[argv.index("--coverage") + 1])
        if got is None:
            print("no coverage total in that folder", file=sys.stderr)
            return 2
        cov, tests = got, ran or tests  # what ran: subtests' classes made in loops too
    for k, v in lines.items():
        print(f"{k:10} {v:7}  (stored {old.get('lines', {}).get(k, '—')})")
    print(f"{'(tests)':10} {tests:7}  (stored {old.get('tests', '—')})")
    print(f"{'coverage':10} {cov if cov is not None else '—'} %")
    if "--write" in argv:
        write(lines, tests, cov)
        print(f"wrote {STATS.relative_to(ROOT)}; the READMEs' part anew:")
        import subprocess
        return subprocess.call([sys.executable, str(ROOT / "tools" / "docs_build.py")])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
