"""Do the four interfaces *do* the same? The scenario of tests/scenario.py — open a lane,
the ⋯ menu, like, boost, a thread, follow a thread, reply, a profile, follow someone,
delete, the command line, read up to here, all read — through each interface's own way
in (tests/drivers.py), held against what frontends/common says should happen; and
whether each window has every place a link may ask for. Writes a table:

    python3 tools/behaviour.py OUT.md

An interface whose toolkit isn't here is "not run" (Qt: PySide6, GTK: python3-gi and a
display, the terminal: Textual). Exit code 1 when any that ran differs."""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp(prefix="fedtail-behaviour-")
os.environ.setdefault("XDG_CONFIG_HOME", str(Path(_tmp) / "config"))
os.environ.setdefault("XDG_DATA_HOME", str(Path(_tmp) / "data"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def short(x, n=70):
    s = str(x)
    return s if len(s) <= n else s[:n - 1] + "…"


def main():
    out = Path(next((a for a in sys.argv[1:] if not a.startswith("-")), "behaviour.md"))
    from fedtail import i18n
    i18n.setup("en")
    from tests import drivers, scenario, test_behaviour
    ref = scenario.run(drivers.Reference())
    lines = ["# Behaviour: the same scenario in every interface", "",
             "Each step through the interface's own way in, held against frontends/common "
             "(tests/scenario.py). ✓ — the same; ✗ — differs (below); — — not run here.", ""]
    names = ["web", "tui", "qt", "gtk"]
    results, why_not = {}, {}
    for d in [drivers.Web()] + [getattr(drivers, k)() for k in ("Tui", "Qt", "Gtk")
                                if getattr(drivers, k, None) is not None
                                and getattr(drivers, k).can_run()]:
        try:
            results[d.name] = scenario.compare(ref, scenario.run(d))
        except Exception:  # noqa: BLE001 — a driver that broke is a finding too
            results[d.name] = [("(run)", "", traceback.format_exc(limit=6))]
    for k in ("Tui", "Qt", "Gtk"):
        cls = getattr(drivers, k, None)
        if cls is None:
            why_not[k.lower()] = "no driver yet"
        elif not cls.can_run():
            why_not[k.lower()] = cls.why_not()
    steps = [s[0] for s in scenario.STEPS] + ["done:" + k for k in ref.done]
    lines += ["| step | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for sid in steps + ["(run)"]:
        cells = []
        for n in names:
            if n not in results:
                cells.append("—")
                continue
            bad = [d for d in results[n] if d[0] == sid]
            cells.append("✗" if bad else "✓")
        if sid == "(run)" and all(c != "✗" for c in cells):
            continue
        lines.append(f"| {sid} | " + " | ".join(cells) + " |")
    lines.append("")
    for n, why in why_not.items():
        lines.append(f"- {n}: not run — {why}")
    lines.append("")
    differs = 0
    for n, diffs in results.items():
        if not diffs:
            continue
        differs += len(diffs)
        lines += [f"## {n}: {len(diffs)} differences", "", "| step | common | " + n + " |",
                  "|---|---|---|"]
        for sid, want, got in diffs:
            lines.append(f"| {sid} | {short(want)} | {short(got, 400)} |")
        lines.append("")
    gaps = {k: v for k, v in test_behaviour.host_gaps().items() if v}
    lines += ["## Places a link may ask for, missing in a window", ""]
    lines += [f"- {k}: {', '.join(v)}" for k, v in gaps.items()] or ["none"]
    lines.append("")
    out.write_text("\n".join(lines), "utf-8")
    print("\n".join(lines[:40]))
    return 1 if differs or gaps else 0


if __name__ == "__main__":
    sys.exit(main())
