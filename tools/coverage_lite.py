"""Line coverage of fedtail without anything installed: Python's own sys.monitoring
(3.12+) notes each line of fedtail/ the tests run; the lines that could run are taken
from the compiled code of every module (co_lines), so a module no test imports counts
too, at 0 %.

    python3 tools/coverage_lite.py [OUT_DIR] [-- unittest args]

Runs `unittest discover tests` (or the given test modules), then writes
OUT_DIR (default coverage)/report.md — by package and by file, the least covered first —
and lines.json ({file: [lines never run]}) for a closer look. Lines, not branches;
slower than coverage.py by a little, and needs nothing else.

Windows and GUI-less machines: Qt and GTK tests skip themselves there, and their code
counts as not run — the report says which toolkits were present."""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "fedtail"
TOOL = sys.monitoring.COVERAGE_ID if hasattr(sys, "monitoring") else None


def possible_lines(path):
    """Lines of a module that hold code (what co_lines names, in every code object)."""
    try:
        code = compile(path.read_text("utf-8"), str(path), "exec")
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return set()
    out, todo = set(), [code]
    while todo:
        c = todo.pop()
        out.update(line for _s, _e, line in c.co_lines() if line)
        todo.extend(k for k in c.co_consts if hasattr(k, "co_lines"))
    # the docstring and `def`/`class` lines run on import: they are there, not "code"
    return out


def main():
    if TOOL is None:
        print("needs Python 3.12+ (sys.monitoring)")
        return 2
    argv = sys.argv[1:]
    extra = argv[argv.index("--") + 1:] if "--" in argv else []
    argv = argv[:argv.index("--")] if "--" in argv else argv
    out = Path(argv[0]) if argv else ROOT / "coverage"
    out.mkdir(parents=True, exist_ok=True)

    hit = defaultdict(set)
    prefix = str(PKG) + os.sep
    mon = sys.monitoring

    def on_line(code, line):
        f = code.co_filename
        if f.startswith(prefix):
            hit[f].add(line)
        return mon.DISABLE  # once a line is seen it costs nothing more

    def on_start(code, _offset):
        if not code.co_filename.startswith(prefix):
            return mon.DISABLE  # code outside fedtail: no line events for it
        return None

    mon.use_tool_id(TOOL, "fedtail-coverage")
    mon.register_callback(TOOL, mon.events.LINE, on_line)
    mon.register_callback(TOOL, mon.events.PY_START, on_start)
    mon.set_events(TOOL, mon.events.LINE | mon.events.PY_START)
    # threads started later are covered too: sys.monitoring is process-wide
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    t0 = time.time()
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(extra) if extra else \
        loader.discover("tests", top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=0, stream=sys.stderr).run(suite)
    mon.set_events(TOOL, 0)
    mon.free_tool_id(TOOL)
    took = time.time() - t0

    rows, missing = [], {}
    for path in sorted(PKG.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        can = possible_lines(path)
        if not can:
            continue
        ran = hit.get(str(path), set()) & can
        rel = str(path.relative_to(ROOT))
        rows.append((rel, len(can), len(ran)))
        missing[rel] = sorted(can - ran)

    def pct(a, b):
        return 100.0 * a / b if b else 100.0
    groups = defaultdict(lambda: [0, 0])
    for rel, can, ran in rows:
        parts = rel.split("/")
        key = "/".join(parts[:3]) if parts[1] == "frontends" and len(parts) > 3 else \
            "/".join(parts[:2]) if len(parts) > 2 else rel
        groups[key][0] += can
        groups[key][1] += ran
    total_can = sum(r[1] for r in rows)
    total_ran = sum(r[2] for r in rows)
    have = []
    for mod, name in (("PySide6", "Qt"), ("gi", "GTK"), ("textual", "Textual")):
        try:
            __import__(mod)
            have.append(name)
        except Exception:  # noqa: BLE001
            pass
    md = ["# Line coverage (tools/coverage_lite.py)", "",
          f"- total: **{pct(total_ran, total_can):.1f} %** ({total_ran} of {total_can} lines)",
          f"- tests: {result.testsRun} run, {len(result.failures) + len(result.errors)} "
          f"failed, {len(result.skipped)} skipped, {took:.0f} s",
          f"- toolkits here: {', '.join(have) or 'none'} (the others' code counts as not run)",
          "", "## By part", "", "| part | lines | run | % |", "|---|---|---|---|"]
    for key, (can, ran) in sorted(groups.items(), key=lambda kv: pct(kv[1][1], kv[1][0])):
        md.append(f"| {key} | {can} | {ran} | {pct(ran, can):.0f} |")
    md += ["", "## By file, the least covered first (100 % left out)", "",
           "| file | lines | run | % |", "|---|---|---|---|"]
    for rel, can, ran in sorted(rows, key=lambda r: (pct(r[2], r[1]), -r[1])):
        if ran < can:
            md.append(f"| {rel} | {can} | {ran} | {pct(ran, can):.0f} |")
    (out / "report.md").write_text("\n".join(md) + "\n", "utf-8")
    # the summary for the self-check's report (it shows a step's notes.txt)
    cut = md.index("## By file, the least covered first (100 % left out)")
    (out / "notes.txt").write_text("\n".join(md[2:cut]) + "\n", "utf-8")
    (out / "lines.json").write_text(json.dumps(missing, indent=0), "utf-8")
    print("\n".join(md[:8]))
    print(out / "report.md")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
