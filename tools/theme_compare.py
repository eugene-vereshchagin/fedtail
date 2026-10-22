"""Each theme in the Qt window and in the GTK one, side by side: the pictures the
self-check took (qt-tour/<theme>-single.png, gtk-shots/gtk-<theme>-light|dark.png) put
next to each other, and their main colours compared — what share of one window is
painted in colours the other doesn't have. The web page and the terminal have no
themes of their own yet: when they do, they come in here too.

    python3 tools/theme_compare.py SELFCHECK_OUT [OUT_DIR]

Writes OUT_DIR (default SELFCHECK_OUT/themes)/report.md, pairs/<theme>.png and
errors.txt (a theme missing on one side isn't a problem; a picture that can't be
read is)."""

from __future__ import annotations

import re
import sys
import traceback
from pathlib import Path

DIFFER = 12.0  # % of the window in colours the other side lacks: worth a look
COLOURS = 8


def main_colours(img):
    """[(share 0…1, (r, g, b))] of a picture, the biggest first."""
    small = img.convert("RGB")
    small.thumbnail((480, 480))
    q = small.quantize(COLOURS, method=2)  # fast octree: the same on every machine
    pal = q.getpalette()
    total = small.width * small.height
    out = []
    for count, idx in sorted(q.getcolors(COLOURS * 2) or [], reverse=True):
        out.append((count / total, tuple(pal[idx * 3: idx * 3 + 3])))
    return out


def dist(a, b):
    return (sum((x - y) ** 2 for x, y in zip(a, b, strict=False)) ** 0.5) / 441.7 * 100


def missing(mine, theirs):
    """How much of `mine` (in % of the window) is in colours far from all of theirs,
    weighted by how far: 0 — the same colours, 100 — nothing alike."""
    return sum(share * min(dist(c, t) for _s, t in theirs) for share, c in mine)


def swatch(colours, w, h):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    x = 0
    for share, c in colours:
        step = max(1, round(share * w))
        d.rectangle([x, 0, x + step, h], fill=c)
        x += step
    return im


def pair(qt_png, gtk_png, out_png, qc, gc):
    from PIL import Image
    a, b = Image.open(qt_png).convert("RGB"), Image.open(gtk_png).convert("RGB")
    h = 520
    a = a.resize((max(1, a.width * h // a.height), h))
    b = b.resize((max(1, b.width * h // b.height), h))
    sheet = Image.new("RGB", (a.width + b.width + 12, h + 40), "white")
    sheet.paste(a, (0, 0))
    sheet.paste(b, (a.width + 12, 0))
    sheet.paste(swatch(qc, a.width, 36), (0, h + 4))
    sheet.paste(swatch(gc, b.width, 36), (a.width + 12, h + 4))
    sheet.save(out_png)


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    src = Path(args[0])
    out = Path(args[1]) if len(args) > 1 else src / "themes"
    (out / "pairs").mkdir(parents=True, exist_ok=True)
    errors, rows, alone = [], [], []
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        (out / "errors.txt").write_text("no Pillow (pip install pillow)\n", "utf-8")
        return 2
    gtk = {}
    for f in sorted((src / "gtk-shots").glob("gtk-*.png")):
        m = re.fullmatch(r"gtk-(.+)-(light|dark)\.png", f.name)
        if m:
            gtk.setdefault(m.group(1), f)
    qt = {}
    for f in sorted((src / "qt-tour").glob("*-single.png")):
        name = f.name[:-len("-single.png")]
        if "-" not in name or name in gtk:
            qt[name] = f
    for name in sorted(set(qt) | set(gtk)):
        if name not in qt or name not in gtk:
            alone.append(f"{name}: only in {'Qt' if name in qt else 'GTK'}")
            continue
        try:
            from PIL import Image
            qc = main_colours(Image.open(qt[name]))
            gc = main_colours(Image.open(gtk[name]))
            score = (missing(qc, gc) + missing(gc, qc)) / 2
            pair(qt[name], gtk[name], out / "pairs" / f"{name}.png", qc, gc)
            rows.append((score, name, qc[0][1] if qc else None, gc[0][1] if gc else None))
        except Exception:  # noqa: BLE001
            errors.append(f"{name}: " + traceback.format_exc(limit=4))
    rows.sort(reverse=True)

    def hexc(c):
        return "#{:02x}{:02x}{:02x}".format(*c) if c else "—"
    md = ["# Themes: Qt and GTK side by side", "",
          f"{len(rows)} themes in both; differ = the share of the window in colours the "
          f"other lacks, weighted by how far (0 — alike; over {DIFFER:.0f} — look at "
          "pairs/<theme>.png). The windows show different moments, so a few % is the "
          "content, not the theme.", "",
          "| theme | differ, % | Qt's main colour | GTK's main colour | |",
          "|---|---|---|---|---|"]
    for score, name, qm, gm in rows:
        md.append(f"| {name} | {score:.1f} | {hexc(qm)} | {hexc(gm)} | "
                  f"{'**look**' if score > DIFFER else ''} |")
    if alone:
        md += ["", "Only on one side:", ""] + [f"- {x}" for x in alone]
    md += ["", "The web page and the terminal: no themes of their own yet."]
    (out / "report.md").write_text("\n".join(md) + "\n", "utf-8")
    (out / "errors.txt").write_text("\n\n".join(errors) + "\n" if errors else "none\n",
                                    "utf-8")
    print("\n".join(md[:8 + min(len(rows), 12)]))
    print(f"{len(errors)} problems; {out / 'report.md'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
