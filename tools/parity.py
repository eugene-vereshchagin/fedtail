"""Do the four interfaces offer the same things? A map from the code: every word of
the interface (an i18n key) that one frontend shows, and which of the others show it
too — a menu item, a button, a dialog, a message. What Qt has and the web lacks is,
most of the time, a feature the web lacks.

    python3 tools/parity.py [OUT.md]

The words a frontend takes from frontends/common/ (the ⋯ menu of a post, the lanes,
the commands…) count for each frontend that imports that module. Words that only one
interface can have (tui_*, web_*, gtk_*, qt_*, a toolkit's own) are left out.
With the walks' inventories at hand (qt-tour/menus.txt, web/notes.txt next to OUT),
the post's ⋯ menus are put side by side too."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FRONTENDS = {
    "qt": ["fedtail/frontends/qt"],
    "gtk": ["fedtail/frontends/gtk"],
    "tui": ["fedtail/frontends/tui"],
    "web": ["fedtail/frontends/web", "fedtail/data/web"],
}
OWN = ("tui_", "web_", "gtk_", "qt_", "dock_", "roster_look_", "agent_", "kde_")
KEY_PY = re.compile(r"""\b_\(\s*["']([a-z0-9_]+)["']""")
KEY_JS = re.compile(r"""\bw\(\s*["']([a-z0-9_]+)["']""")
# keys built from a prefix (_("lane_" + name)): the prefix is enough to say "uses them"
PREFIX_PY = re.compile(r"""\b_\(\s*f?["']([a-z0-9_]+_)["']\s*\+""")
COMMON_IMPORT = re.compile(r"""(?:from\s+\.\.common(?:\.(\w+))?\s+import\s+([\w, ()\n]+))|"""
                           r"""(?:common\.(\w+))""")


def files(paths):
    for p in paths:
        for f in sorted((ROOT / p).rglob("*")):
            if f.suffix in (".py", ".js") and "__pycache__" not in f.parts:
                yield f


def keys_in(f):
    text = f.read_text("utf-8", errors="replace")
    found = set(KEY_PY.findall(text)) | (set(KEY_JS.findall(text)) if f.suffix == ".js"
                                         else set())
    return found, set(PREFIX_PY.findall(text)), text


def common_used(texts):
    mods = set()
    for t in texts:
        for m in COMMON_IMPORT.finditer(t):
            if m.group(1):
                mods.add(m.group(1))
            elif m.group(2):
                mods |= {x.strip(" ()\n").split()[0] for x in m.group(2).split(",")
                         if x.strip(" ()\n")}  # "activity as act": activity
            elif m.group(3):
                mods.add(m.group(3))
    return {m for m in mods if (ROOT / "fedtail/frontends/common" / f"{m}.py").exists()}


def collect():
    from fedtail import i18n
    known = set(i18n._STRINGS["ru"])
    common = {f.stem: keys_in(f) for f in (ROOT / "fedtail/frontends/common").glob("*.py")}
    out = {}
    for fe, paths in FRONTENDS.items():
        keys, prefixes, texts = set(), set(), []
        for f in files(paths):
            k, p, t = keys_in(f)
            keys |= k
            prefixes |= p
            texts.append(t)
        for m in common_used(texts):
            keys |= common[m][0]
            prefixes |= common[m][1]
        keys |= {k for k in known if any(k.startswith(p) for p in prefixes)}
        out[fe] = {k for k in keys if k in known and not k.startswith(OWN)}
    return out


def menus_side_by_side(folder):
    """The post's ⋯ menu as the Qt walk and the web walk saw it."""
    qt = folder / "qt-tour" / "menus.txt"
    web = folder / "web" / "notes.txt"
    if not qt.exists() or not web.exists():
        return []
    q = qt.read_text("utf-8").split("== menu-post", 1)
    q = [x.strip() for x in q[1].split("\n==", 1)[0].splitlines()[1:] if x.strip()
         and x.strip() != "—"] if len(q) > 1 else []
    wline = next((x for x in web.read_text("utf-8").splitlines() if x.startswith("⋯ menu:")),
                 "")
    w = [x.strip().lstrip("❝ ").strip() for x in wline[len("⋯ menu:"):].split("|")
         if x.strip()]
    norm = lambda s: re.sub(r"[#@]\S+", "", s).strip().lower()  # noqa: E731
    lines = ["## The post's ⋯ menu: Qt (and GTK, the same code) and the web", "",
             "| Qt | web |", "|---|---|"]
    wn = {norm(x): x for x in w}
    for x in q:
        lines.append(f"| {x} | {wn.pop(norm(x), '—')} |")
    for x in wn.values():
        lines.append(f"| — | {x} |")
    return lines + [""]


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    from fedtail import i18n
    i18n.setup("ru")
    ru = i18n._STRINGS["ru"]
    have = collect()
    every = set().union(*have.values())
    lines = ["# Parity: what each interface says (from the code)", "",
             "| | " + " | ".join(have) + " |", "|---|" + "---|" * len(have),
             "| words used | " + " | ".join(str(len(v)) for v in have.values()) + " |",
             "| of all the interfaces' | " +
             " | ".join(f"{100 * len(v) // max(1, len(every))}%" for v in have.values()) +
             " |", ""]
    order = list(have)
    for a in order:
        for b in order:
            if a == b or (a, b) not in (("qt", "gtk"), ("gtk", "qt"), ("qt", "web"),
                                        ("qt", "tui"), ("gtk", "web"), ("web", "qt"),
                                        ("tui", "qt")):
                continue
            miss = sorted(have[a] - have[b])
            lines += [f"## In {a}, not in {b}: {len(miss)}", ""]
            for k in miss:
                text = str(ru.get(k, "")).replace("\n", " ")
                lines.append(f"- `{k}` — {text[:90]}")
            lines.append("")
    if out_path is not None:
        lines += menus_side_by_side(out_path.parent)
    text = "\n".join(lines) + "\n"
    if out_path:
        out_path.write_text(text, "utf-8")
        print(f"{out_path}: " + ", ".join(f"{k} {len(v)}" for k, v in have.items()))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
