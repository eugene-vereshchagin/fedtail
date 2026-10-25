"""Do the four interfaces offer the same things? (The registry of what isn't the same,
and why, is docs/src/parity.toml; check() holds it against the code, tests/test_parity.py
runs it.) A map from the code: every word of
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
# a key named as data ((("census", "debug_census"), …) then _(key)): any literal with an
# underscore that is an i18n key counts too; one-word keys ("close") only through _()
KEY_LIT = re.compile(r"""["']([a-z][a-z0-9]*_[a-z0-9_]+)["']""")
# keys built from a prefix (_("lane_" + name)): the prefix is enough to say "uses them"
PREFIX_PY = re.compile(r"""["']([a-z][a-z0-9_]*_)["']\s*\+""")  # key = "quote_" + state
COMMON_IMPORT = re.compile(r"""(?:from\s+\.\.common(?:\.(\w+))?\s+import\s+"""
                           r"""(\([^)]*\)|[\w ,]+))|(?:common\.(\w+))""")


def files(paths):
    for p in paths:
        for f in sorted((ROOT / p).rglob("*")):
            if f.suffix in (".py", ".js") and "__pycache__" not in f.parts:
                yield f


def keys_in(f):
    text = f.read_text("utf-8", errors="replace")
    found = set(KEY_PY.findall(text)) | set(KEY_LIT.findall(text)) | \
        (set(KEY_JS.findall(text)) if f.suffix == ".js" else set())
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
        used, todo = set(), list(common_used(texts))
        while todo:  # what common's modules use in turn (places → activity) counts too
            m = todo.pop()
            if m in used:
                continue
            used.add(m)
            text = common[m][2]
            inner = set(re.findall(r"from\s+\.(\w+)\s+import", text)) | {
                x.strip().split()[0] for grp in re.findall(r"from\s+\.\s+import\s+([\w, ]+)",
                                                           text) for x in grp.split(",")
                if x.strip()}
            todo += [x for x in inner if x in common and x not in used]
        for m in used:
            keys |= common[m][0]
            prefixes |= common[m][1]
        keys |= {k for k in known if any(k.startswith(p) for p in prefixes)}
        out[fe] = {k for k in keys if k in known and not k.startswith(OWN)}
    return out


STATUSES = ("has", "partly", "no", "na")
REGISTRY = ROOT / "docs" / "src" / "parity.toml"


def registry(path=REGISTRY):
    import tomllib
    with open(path, "rb") as f:
        return tomllib.load(f)


def status(cap, fe):
    return cap.get(fe, "has")


FEATURES = ROOT / "docs" / "src" / "features"


def features():
    """Every feature of docs/src/features/*.toml: [(file name, feature)]."""
    import tomllib
    out = []
    for f in sorted(FEATURES.glob("*.toml")):
        with open(f, "rb") as fh:
            out += [(f.name, x) for x in tomllib.load(fh).get("feature", [])]
    return out


def _android_note(where, item, st, problems):
    if st not in STATUSES:
        problems.append(f"{where}: android = {st!r}; one of {', '.join(STATUSES)}")
    elif st != "has":
        for lang in ("ru", "en"):
            if not (item.get("android_note") or {}).get(lang):
                problems.append(f"{where}: android_note.{lang} — say why")


def check_android(reg=None, feats=None):
    """The phone's column (android/ has its own screens and words, so the check by i18n
    keys doesn't reach it — it is said by hand): every capability of the registry and
    every feature the desktop has (or has in part) says the phone's status, and why when
    it isn't "has", in both languages. [] when all is said."""
    reg = registry() if reg is None else reg
    feats = features() if feats is None else feats
    problems = []
    for cap in reg.get("capability", []):
        if "android" not in cap:
            problems.append(f"{cap.get('id', '?')}: android — say the phone's status")
            continue
        _android_note(cap.get("id", "?"), cap, cap["android"], problems)
    for name, f in feats:
        if f.get("status") not in ("has", "partly"):
            continue
        where = f"{name}: {f.get('id', '?')}"
        if "android" not in f:
            problems.append(f"{where}: android — say the phone's status")
            continue
        _android_note(where, f, f["android"], problems)
    return problems


def check(reg=None, have=None):
    """What the registry (docs/src/parity.toml) and the code disagree on: a word one
    interface shows and another doesn't, explained nowhere; an interface marked "has"
    without the words of its capability; one marked "no" that has them all (done:
    say so); notes missing; unknown words. [] when they agree."""
    from fedtail import i18n
    reg = registry() if reg is None else reg
    have = collect() if have is None else have
    known = set(i18n._STRINGS["ru"])
    caps, wordings = reg.get("capability", []), reg.get("wording", [])
    problems, explained = [], {fe: set() for fe in have}
    ids = set()
    for cap in caps:
        cid = cap.get("id", "?")
        if cid in ids:
            problems.append(f"{cid}: the id is used twice")
        ids.add(cid)
        for k in cap.get("keys", []):
            if k not in known:
                problems.append(f"{cid}: no such word {k!r}")
        statuses = {fe: status(cap, fe) for fe in have}
        for fe, st in statuses.items():
            if st not in STATUSES:
                problems.append(f"{cid}: {fe} = {st!r}; one of {', '.join(STATUSES)}")
                continue
            keys = set(cap.get("keys", []))
            if st == "has":
                lost = sorted(keys - have[fe])
                if lost:
                    problems.append(f"{cid}: {fe} is marked \"has\" but doesn't show "
                                    + ", ".join(lost))
            else:
                explained[fe] |= keys
                if st == "no" and keys and keys <= have[fe]:
                    problems.append(f"{cid}: {fe} is marked \"no\" but shows every word "
                                    "of it — done? mark it \"has\"")
        if any(st != "has" for st in statuses.values()):
            for lang in ("ru", "en"):
                if not (cap.get("note") or {}).get(lang):
                    problems.append(f"{cid}: note.{lang} — say why")
        for lang in ("ru", "en"):
            if not (cap.get("name") or {}).get(lang):
                problems.append(f"{cid}: name.{lang} missing")
    for w in wordings:
        for k in w.get("keys", []):
            if k not in known:
                problems.append(f"wording: no such word {k!r}")
        for fe in w.get("in", []):
            if fe not in have:
                problems.append(f"wording: no interface {fe!r}")
                continue
            explained[fe] |= set(w.get("keys", []))
        for lang in ("ru", "en"):
            if not (w.get("why") or {}).get(lang):
                problems.append(f"wording {w.get('keys', ['?'])[:2]}: why.{lang} missing")
    every = set().union(*have.values())
    for fe, words in have.items():
        for k in sorted(every - words - explained[fe]):
            shown_by = ", ".join(x for x in have if k in have[x])
            problems.append(f"{k}: {shown_by} show it, {fe} doesn't — add it to {fe} or "
                            f"explain in docs/src/parity.toml")
    return problems


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
    problems = check(have=have)
    lines += ["## docs/src/parity.toml against the code", "",
              "agree" if not problems else f"{len(problems)} problems:", ""]
    lines += [f"- {p}" for p in problems] + [""]
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
