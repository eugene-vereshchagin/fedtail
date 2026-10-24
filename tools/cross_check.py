"""Several self-check runs side by side — KDE (the reference), Windows, and the GTK
window of the Linux run: how each looks, what its menus say, how it behaves, which
tests and steps failed. Each run is a folder (or its zip) from tools/selfcheck.py.

    python3 tools/cross_check.py REF_RUN OTHER_RUN [...] [--out DIR]

REF_RUN is the reference (the KDE one): every other Qt window is held against it, and
so is the GTK window found in any run. Writes DIR (default cross-check)/report.md and
pictures/<theme>.png: the reference, the others and GTK in a row, with each one's
main colours under it and how far they are from the reference's."""

from __future__ import annotations

import argparse
import difflib
import re
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.theme_compare import main_colours, missing, swatch  # noqa: E402

LOOK = 12.0  # differ, %: past this a picture is worth a look


def open_run(arg, tmp):
    """A run's folder: the folder itself, or the one inside a zip."""
    p = Path(arg)
    if p.suffix == ".zip":
        dest = Path(tmp) / p.stem
        with zipfile.ZipFile(p) as z:
            z.extractall(dest)
        found = [d for d in dest.rglob("report.md") if d.parent.parent == dest]
        return found[0].parent if found else dest
    return p


class Run:
    def __init__(self, folder):
        self.dir = folder
        text = (folder / "report.md").read_text("utf-8") if (folder / "report.md").exists() \
            else ""
        self.facts = dict(re.findall(r"^- ([\w /]+): (.*)$", text, re.M))
        head = text.split("\n## ")[0]  # the steps' table, not the tables of the steps
        self.steps = {m[0]: m[1] for m in re.findall(r"^\| ([\w.-]+) \| ([^|]+?) \|", head,
                                                      re.M) if m[0] != "step"}
        self.failed = sorted(set(re.findall(r"^failed: (test\w+ \([\w.]+\))", text, re.M)))
        system = self.facts.get("system", "")
        desk = self.facts.get("desktop", "").strip()
        self.name = ("Windows" if "Windows" in system else
                     (desk.split()[0] if desk else "Linux") if "Linux" in system else
                     system.split("-")[0] or folder.name)

    def qt_shots(self):
        d = self.dir / "qt-tour"
        return {f.stem: f for f in sorted(d.glob("*.png"))} if d.is_dir() else {}

    def gtk_shot(self, theme, layout):
        d = self.dir / "gtk-shots"
        tail = "" if layout == "single" else f"-{layout}"
        for tone in ("light", "dark"):
            f = d / f"gtk-{theme}-{tone}{tail}.png"
            if f.exists():
                return f
        return None

    def menus(self):
        f = self.dir / "qt-tour" / "menus.txt"
        if not f.exists():
            return {}
        out, name = {}, None
        for line in f.read_text("utf-8").splitlines():
            if line.startswith("== "):
                name = line[3:]
                out[name] = []
            elif name is not None:
                out[name].append(line.rstrip())
        return out

    def behaviour(self):
        f = self.dir / "behaviour.md"
        if not f.exists():
            return {}
        rows = {}
        first = f.read_text("utf-8").split("\n## ")[0]  # the table, not the differences
        for m in re.findall(r"^\| ([\w:()]+) \| (.+) \|$", first, re.M):
            if m[0] != "step":
                rows[m[0]] = [c.strip() for c in m[1].split("|")]
        return rows


def row_picture(cells, out_png):
    """cells: [(label, png or None)]: one row, each scaled to one height, colours under
    each; returns [(label, differ from the first, %)]."""
    from PIL import Image, ImageDraw
    h = 460
    pics, scores, ref_cols = [], [], None
    for label, png in cells:
        if png is None:
            im = Image.new("RGB", (300, h), (250, 250, 250))
            ImageDraw.Draw(im).text((20, h // 2), f"{label}: none", fill=(120, 120, 120))
            pics.append((label, im, []))
            scores.append((label, None))
            continue
        src = Image.open(png).convert("RGB")
        cols = main_colours(src)
        im = src.resize((max(1, src.width * h // src.height), h))
        pics.append((label, im, cols))
        if ref_cols is None:
            ref_cols = cols
            scores.append((label, 0.0))
        else:
            scores.append((label, (missing(ref_cols, cols) + missing(cols, ref_cols)) / 2))
    width = sum(p[1].width for p in pics) + 12 * (len(pics) - 1)
    sheet = Image.new("RGB", (width, h + 64), "white")
    d = ImageDraw.Draw(sheet)
    x = 0
    for (label, im, cols), (_l, score) in zip(pics, scores, strict=True):
        sheet.paste(im, (x, 0))
        if cols:
            sheet.paste(swatch(cols, im.width, 28), (x, h + 4))
        note = label + ("" if score is None or score == 0 else f" · differs {score:.0f}%")
        d.text((x + 4, h + 38), note, fill=(0, 0, 0))
        x += im.width + 12
    sheet.save(out_png)
    return scores


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", default="cross-check")
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="fedtail-cross-")
    runs = [Run(open_run(r, tmp)) for r in a.runs]
    ref, others = runs[0], runs[1:]
    out = Path(a.out)
    (out / "pictures").mkdir(parents=True, exist_ok=True)
    gtk_run = next((r for r in runs if (r.dir / "gtk-shots").is_dir()), None)
    md = [f"# {ref.name} (the reference) against "
          + ", ".join(r.name for r in others) + (" and GTK" if gtk_run else ""), ""]
    for r in runs:
        md.append(f"- **{r.name}**: {r.facts.get('system', '?')} · Qt "
                  f"{r.facts.get('PySide6', '—')} · GTK {r.facts.get('GTK 4', '—')} · "
                  f"Textual {r.facts.get('Textual', '—')} · fedtail {r.facts.get('fedtail', '?')}"
                  f" · {r.dir.name}")
    # ---- the steps -----------------------------------------------------------------------
    names = list(dict.fromkeys(k for r in runs for k in r.steps))
    md += ["", "## Steps", "", "| step | " + " | ".join(r.name for r in runs) + " |",
           "|---|" + "---|" * len(runs)]
    for n in names:
        cells = [r.steps.get(n, "—") for r in runs]
        if len(set(cells)) > 1 or any(c.startswith("problems") for c in cells):
            md.append(f"| {n} | " + " | ".join(cells) + " |")
    md += ["", "## Tests that failed", ""]
    for r in runs:
        md.append(f"- {r.name}: " + (", ".join(r.failed) if r.failed else "none"))
    # ---- how it looks --------------------------------------------------------------------
    md += ["", "## How it looks: the main window, theme by theme", "",
           f"differs — the share of the window in colours the reference lacks, weighted by "
           f"how far (0 — alike; over {LOOK:.0f} — look at the picture). The windows are "
           "taken at different moments: a few % is the content.", "",
           "| theme | " + " | ".join(r.name for r in others) + (" | GTK" if gtk_run else "")
           + " | picture |", "|---|" + "---|" * (len(others) + (2 if gtk_run else 1))]
    ref_shots = ref.qt_shots()
    looked = 0
    for stem, png in ref_shots.items():
        m = re.fullmatch(r"(.+)-(single|split)", stem)
        if not m:
            continue
        theme, layout = m.groups()
        cells = [(ref.name, png)] + [(r.name, r.qt_shots().get(stem)) for r in others]
        if gtk_run:
            cells.append(("GTK", gtk_run.gtk_shot(theme, layout)))
        scores = row_picture(cells, out / "pictures" / f"{stem}.png")[1:]
        looked += 1

        def cell(score):
            if score is None:
                return "—"
            return f"**{score:.0f}**" if score > LOOK else f"{score:.0f}"
        md.append(f"| {stem} | " + " | ".join(cell(s) for _l, s in scores)
                  + f" | pictures/{stem}.png |")
    if not looked:
        md.append("| (no main-window pictures in the reference run) |")
    missing_here = sorted(set(s for r in others for s in r.qt_shots()) - set(ref_shots))
    if missing_here:
        md += ["", "Pictures the others have and the reference doesn't: "
               + ", ".join(missing_here[:40])]
    # ---- menus ---------------------------------------------------------------------------
    md += ["", "## Menus: the reference's words against each Qt window", ""]
    ref_menus = ref.menus()
    if not ref_menus:
        md.append("The reference has no menus.txt (its tour didn't get that far).")
    for r in others:
        theirs = r.menus()
        if not theirs:
            md.append(f"- {r.name}: no menus.txt")
            continue
        diffs = []
        for name in sorted(set(ref_menus) | set(theirs)):
            a, b = ref_menus.get(name), theirs.get(name)
            if a is None or b is None:
                diffs.append(f"### {name}: only in {ref.name if b is None else r.name}")
                continue
            if a != b:
                diffs += [f"### {name}", "```diff"] + [
                    x for x in difflib.unified_diff(a, b, ref.name, r.name, lineterm="",
                                                    n=1)][2:] + ["```"]
        md += [f"### {r.name}: " + (f"{len(diffs)} lines of differences" if diffs
                                    else "the same"), ""] + diffs + [""]
    # ---- behaviour -----------------------------------------------------------------------
    md += ["", "## Behaviour (tests/scenario.py in every interface of each run)", ""]
    cols = ["web", "tui", "qt", "gtk"]
    beh = {r.name: r.behaviour() for r in runs}
    steps = list(dict.fromkeys(k for b in beh.values() for k in b))
    md += ["| step | " + " | ".join(f"{r.name} {c}" for r in runs for c in cols) + " |",
           "|---|" + "---|" * (len(cols) * len(runs))]
    for s in steps:
        cells = [(beh[r.name].get(s) or ["—"] * 4)[i] if i < len(beh[r.name].get(s) or [])
                 else "—" for r in runs for i in range(4)]
        if any(c not in ("✓", "—") for c in cells):
            md.append(f"| {s} | " + " | ".join(cells) + " |")
    md.append("")
    (out / "report.md").write_text("\n".join(md) + "\n", "utf-8")
    print("\n".join(md[:60]))
    print(f"\n{out / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
