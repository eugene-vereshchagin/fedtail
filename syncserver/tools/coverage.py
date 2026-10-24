"""Line coverage of fedtail_sync.py by its own tests, with nothing installed: Python's
sys.monitoring (3.12+) notes each line the tests run; the lines that could run come
from the compiled code (co_lines). A line marked "# pragma: no cover" — and the
block it opens — doesn't count.

    python3 syncserver/tools/coverage.py                  # the report
    python3 syncserver/tools/coverage.py --fail-under 100 # and exit 1 below that

Lines, not branches. The tests run as `unittest discover` would run them.
"""

import argparse
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # syncserver/
TARGET = HERE / "fedtail_sync.py"
TOOL_ID = 4


def possible_lines(path):
    """{line: text} of the lines holding code, those under a no-cover pragma left out."""
    text = path.read_text("utf-8").splitlines()
    code = compile("\n".join(text) + "\n", str(path), "exec")
    lines, stack = set(), [code]
    while stack:
        c = stack.pop()
        lines |= {ln for *_x, ln in c.co_lines() if ln}
        stack += [k for k in c.co_consts if hasattr(k, "co_lines")]
    skip, i = set(), 0
    while i < len(text):
        if "# pragma: no cover" in text[i]:
            indent = len(text[i]) - len(text[i].lstrip())
            skip.add(i + 1)
            j = i + 1
            while j < len(text) and (not text[j].strip() or
                                     len(text[j]) - len(text[j].lstrip()) > indent):
                skip.add(j + 1)
                j += 1
            i = j
        else:
            i += 1
    return {ln: text[ln - 1] for ln in lines - skip if 0 < ln <= len(text)}


def run(verbosity=1):
    """Run the tests while counting. → (lines run, unittest result)."""
    if not hasattr(sys, "monitoring"):
        sys.exit("needs Python 3.12+ (sys.monitoring)")
    hits, name = set(), str(TARGET)
    mon = sys.monitoring
    mon.use_tool_id(TOOL_ID, "fedtail-sync-coverage")

    def line(code, ln):
        if code.co_filename != name:
            return mon.DISABLE
        hits.add(ln)
        return None
    mon.register_callback(TOOL_ID, mon.events.LINE, line)
    mon.set_events(TOOL_ID, mon.events.LINE)
    try:
        sys.path.insert(0, str(HERE))
        suite = unittest.defaultTestLoader.discover(str(HERE / "tests"), top_level_dir=str(HERE))
        result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    finally:
        mon.set_events(TOOL_ID, 0)
        mon.free_tool_id(TOOL_ID)
    return hits, result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--fail-under", type=float, default=0, help="percent; exit 1 below it")
    a = p.parse_args(argv)
    hits, result = run()
    possible = possible_lines(TARGET)
    missed = sorted(set(possible) - hits)
    pct = 100 * (len(possible) - len(missed)) / len(possible)
    print(f"\nfedtail_sync.py: {len(possible) - len(missed)}/{len(possible)} lines, {pct:.1f} %")
    for ln in missed:
        print(f"  not run: {ln:4d}  {possible[ln].strip()}")
    if not result.wasSuccessful():
        return 1
    if pct < a.fail_under:
        print(f"below {a.fail_under:g} %")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
