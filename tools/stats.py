"""The program in numbers, for the READMEs' "In numbers" / "В цифрах": lines of code by
kind, commits, releases, and the tokens spent making it — counted anew at every release
(docs/en/dev/ci.md, "Making a release"), between the <!-- stats --> markers.

    python3 tools/stats.py            # count, update docs/src/tokens.json and the READMEs
    python3 tools/stats.py --check    # only say whether the READMEs hold these numbers

The tokens come from Claude Code's logs of this checkout on this machine
(~/.claude/projects/<the checkout's path>*/…jsonl, sub-agents too). Claude Code deletes
logs after a month, so each session's sums are kept in docs/src/tokens.json — a session
once counted stays counted after its log is gone. Only numbers go there: a session's id,
its first and last time, its tokens; never a word of what was said."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs" / "src" / "tokens.json"
READMES = {"en": ROOT / "README.md", "ru": ROOT / "README.ru.md"}
SYNC = ROOT.parent / "fedtail-syncserver" / "fedtail_sync.py"
BEGIN, END = "<!-- stats -->", "<!-- /stats -->"
GENERATED = {f"docs/{lang}/{name}.md" for lang in ("en", "ru")
             for name in ("features", "comparison", "config")}
KINDS = ("python", "tests", "kotlin", "web", "tools", "docs")


def _git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                          check=True).stdout


def kind_of(path):
    """Which line of the table a tracked file counts in (None: not counted)."""
    p = Path(path)
    if path in GENERATED or p.parts[:2] == ("fedtail", "_vendor"):
        return None
    if p.suffix == ".py":
        if p.parts[0] == "tests":
            return "tests"
        return "tools" if p.parts[0] in ("tools", "packaging", ".github") else "python"
    if p.suffix == ".kt":
        return "kotlin"
    if p.suffix in (".js", ".css", ".html") and p.parts[:3] == ("fedtail", "data", "web"):
        return "web"
    if p.suffix in (".yml", ".yaml") and p.parts[0] in (".github", "packaging"):
        return "tools"
    if p.suffix == ".md":
        return "docs"
    return None


def lines_of(path):
    try:
        with open(path, encoding="utf-8") as f:
            return sum(1 for _ in f)
    except (OSError, UnicodeDecodeError):
        return 0


def code():
    """{kind: lines} of the tracked files; commits, releases, the first commit's date."""
    out = dict.fromkeys(KINDS, 0)
    for path in _git("ls-files").splitlines():
        k = kind_of(path)
        if k:
            out[k] += lines_of(ROOT / path)
    commits = int(_git("rev-list", "--count", "HEAD").strip())
    tags = [t for t in _git("tag", "--list", "v*").split() if t]
    sys.path.insert(0, str(ROOT))
    from fedtail import __version__
    if "dev" not in __version__ and f"v{__version__}" not in tags:
        tags.append(f"v{__version__}")  # the release being made: tagged by CI after this
    first = _git("log", "--reverse", "--format=%ad", "--date=short").split()[0]
    return out, commits, len(tags), first


# ---- tokens ------------------------------------------------------------------------
def log_dirs(home=None):
    """Claude Code's folders of this checkout (its notes' and worktrees' too)."""
    base = (Path(home) if home else Path.home()) / ".claude" / "projects"
    name = re.sub(r"[^A-Za-z0-9]", "-", str(ROOT))
    return sorted(p for p in base.glob(name + "*") if p.is_dir()) if base.is_dir() else []


def sessions(dirs):
    """{session id: {first, last, input, output, cache_write, cache_read, models}} from the
    logs there — each API answer once (it is written over several lines)."""
    seen, out = set(), {}
    for d in dirs:
        for f in sorted(d.rglob("*.jsonl")):
            for line in open(f, encoding="utf-8", errors="replace"):
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                msg = rec.get("message") if isinstance(rec, dict) else None
                if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
                    continue
                key = (msg.get("id"), rec.get("requestId"))
                if key in seen:
                    continue
                seen.add(key)
                sid = str(rec.get("sessionId") or f.stem)
                s = out.setdefault(sid, {"first": "", "last": "", "input": 0, "output": 0,
                                         "cache_write": 0, "cache_read": 0, "models": {}})
                u = msg["usage"]
                s["input"] += int(u.get("input_tokens") or 0)
                s["output"] += int(u.get("output_tokens") or 0)
                s["cache_write"] += int(u.get("cache_creation_input_tokens") or 0)
                s["cache_read"] += int(u.get("cache_read_input_tokens") or 0)
                model = str(msg.get("model") or "?")
                if not model.startswith("<"):
                    s["models"][model] = s["models"].get(model, 0) + int(
                        u.get("output_tokens") or 0)
                t = str(rec.get("timestamp") or "")[:10]
                if t:
                    s["first"] = min(s["first"] or t, t)
                    s["last"] = max(s["last"], t)
    return out


def merged(ledger, found):
    """The ledger with what the logs say now: a session in the logs is counted anew (it
    may have grown), one whose log is gone keeps what was counted."""
    out = dict(ledger)
    for sid, s in found.items():
        old = out.get(sid)
        if old is None or s["output"] + s["cache_read"] >= old["output"] + old["cache_read"]:
            out[sid] = s
    return dict(sorted(out.items(), key=lambda kv: (kv[1]["first"], kv[0])))


def totals(ledger):
    t = {k: sum(s[k] for s in ledger.values())
         for k in ("input", "output", "cache_write", "cache_read")}
    models = {}
    for s in ledger.values():
        for m, n in s["models"].items():
            models[m] = models.get(m, 0) + n
    t["since"] = min((s["first"] for s in ledger.values() if s["first"]), default="")
    t["until"] = max((s["last"] for s in ledger.values()), default="")
    t["model"] = max(models, key=models.get) if models else ""
    t["share"] = models[t["model"]] / max(1, sum(models.values())) if models else 0
    return t


# ---- the words -------------------------------------------------------------------------
MONTHS = {"en": ("January", "February", "March", "April", "May", "June", "July", "August",
                 "September", "October", "November", "December"),
          "ru": ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
                 "сентября", "октября", "ноября", "декабря")}


def day(iso, lang, year=True):
    y, m, d = (int(x) for x in iso.split("-"))
    words = f"{d} {MONTHS['en'][m - 1]} {y}" if lang == "en" else \
        f"{d} {MONTHS['ru'][m - 1]} {y} года"
    return words if year else words.rsplit(" ", 2 if lang == "ru" else 1)[0]


def num(n, lang):
    """1 133 / 1 133: thousands apart by a thin space, as the READMEs had them."""
    return f"{n:,}".replace(",", " " if lang == "ru" else " ")


def approx(n, lang):
    """~87 000: rounded to a hundred (a thousand above ten thousand)."""
    step = 1000 if n >= 10_000 else 100
    return "~" + num(round(n / step) * step, lang)


def big(n, lang):
    """2.3 billion / 2,3 миллиарда; 16.5 million / 16,5 миллиона."""
    for size, en, ru in ((10**9, "billion", ("миллиард", "миллиарда", "миллиардов")),
                         (10**6, "million", ("миллион", "миллиона", "миллионов"))):
        if n >= size:
            x = round(n / size, 2 if n < 10 * size and size == 10**9 else 1)
            text = f"{x:g}"
            if lang == "en":
                return f"{text} {en}"
            whole = int(x)
            form = ru[1] if x != whole else (ru[0] if whole % 10 == 1 and whole % 100 != 11
                                             else ru[1] if whole % 10 in (2, 3, 4)
                                             and whole % 100 not in (12, 13, 14) else ru[2])
            return f"{text.replace('.', ',')} {form}"
    return num(n, lang)


def model_name(m):
    """claude-opus-5-5 → Claude Opus."""
    parts = m.split("-")
    return " ".join(p.capitalize() for p in parts[:2]) if len(parts) > 1 else m


def text(lang, kinds, commits, releases, first, today, tok, sync_lines):
    code_total = sum(v for k, v in kinds.items() if k != "docs")
    every = sum(tok[k] for k in ("input", "output", "cache_write", "cache_read")) if tok else 0
    rows = {"en": [("the program in Python (core, Qt, GTK, terminal, web server, the "
                    "phone's bridge)", "python"), ("tests", "tests"),
                   ("the Android app in Kotlin", "kotlin"),
                   ("the web page (JS, CSS, HTML)", "web"),
                   ("tools, packaging, CI", "tools"),
                   ("docs in Markdown, Russian and English", "docs")],
            "ru": [("программа на Python (ядро, Qt, GTK, терминал, веб-сервер, мост "
                    "телефона)", "python"), ("тесты", "tests"),
                   ("приложение для Android на Kotlin", "kotlin"),
                   ("веб-страница (JS, CSS, HTML)", "web"),
                   ("инструменты, сборка пакетов, CI", "tools"),
                   ("документация на Markdown, по-русски и по-английски", "docs")]}[lang]
    table = "\n".join(f"| {words} | {approx(kinds[k], lang)} |" for words, k in rows)
    gone = tok and tok["since"] > first
    if lang == "en":
        out = [f"As of {day(today, lang)}, counted at the release "
               f"(the first commit: {day(first, lang)}):", "",
               "| What | Lines |", "|---|---|", table, "",
               f"Some {approx(code_total, lang)[1:]} lines of code without the docs"
               + (f"; the sync server (its own repository) adds {approx(sync_lines, lang)[1:]}"
                  " more" if sync_lines else "")
               + f". {num(commits, lang)} commits, {releases} releases."]
        if tok:
            out += ["", f"Tokens, from Claude Code's logs since {day(tok['since'], lang)}"
                    + (" (the earlier logs are gone, so the real total is higher)" if gone
                       else "")
                    + f": about {big(every, lang)}"
                    f" processed — of them {big(tok['cache_read'], lang)} read from the prompt"
                    f" cache, {big(tok['cache_write'], lang)} written to it,"
                    f" {big(tok['output'], lang)} generated."
                    + (f" Nearly all of it {model_name(tok['model'])}." if tok["share"] > .9
                       else f" Mostly {model_name(tok['model'])}." if tok["model"] else "")]
    else:
        out = [f"На {day(today, lang)}, пересчитано при релизе "
               f"(первый коммит — {day(first, lang)}):", "",
               "| Что | Строк |", "|---|---|", table, "",
               f"Всего около {approx(code_total, lang)[1:]} строк кода без документации"
               + (f"; сервер синхронизации (отдельный репозиторий) — ещё "
                  f"{approx(sync_lines, lang)[1:]}" if sync_lines else "")
               + f". Коммитов — {num(commits, lang)}, релизов — {releases}."]
        if tok:
            out += ["", f"Токены — по журналам Claude Code с {day(tok['since'], lang, False)}"
                    + (" (журналы раньше уже не хранятся, так что на самом деле больше)"
                       if gone else "")
                    + f": около {big(every, lang)}"
                    f" обработано — из них {big(tok['cache_read'], lang)} прочитано из кеша"
                    f" промптов, {big(tok['cache_write'], lang)} записано в него,"
                    f" {big(tok['output'], lang)} сгенерировано."
                    + (f" Почти всё — {model_name(tok['model'])}." if tok["share"] > .9
                       else f" Больше всего — {model_name(tok['model'])}." if tok["model"]
                       else "")]
    return "\n".join(out)


def put(readme, body):
    """body between the markers of readme's text."""
    s = readme
    a, b = s.index(BEGIN) + len(BEGIN), s.index(END)
    return s[:a] + "\n" + body + "\n" + s[b:]


def main(argv=None):
    import datetime
    argv = sys.argv[1:] if argv is None else argv
    kinds, commits, releases, first = code()
    ledger = json.loads(LEDGER.read_text("utf-8")) if LEDGER.exists() else {}
    ledger = merged(ledger, sessions(log_dirs()))
    tok = totals(ledger) if ledger else None
    sync_lines = lines_of(SYNC) if SYNC.exists() else 0
    today = datetime.date.today().isoformat()
    changed = []
    for lang, path in READMES.items():
        old = path.read_text("utf-8")
        new = put(old, text(lang, kinds, commits, releases, first, today, tok, sync_lines))
        if new != old:
            changed.append(path.name)
            if "--check" not in argv:
                path.write_text(new, "utf-8")
    if "--check" in argv:
        print("stale: " + ", ".join(changed) if changed else "current")
        return 1 if changed else 0
    LEDGER.write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + "\n", "utf-8")
    print(f"{commits} commits, {releases} releases; "
          + ", ".join(f"{k} {v}" for k, v in kinds.items())
          + (f"; {len(ledger)} sessions" if ledger else "; no token logs here"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
