"""Build every generated document and expand every include — the one command for docs.

    python3 tools/docs_build.py            # write everything
    python3 tools/docs_build.py --check    # exit 1 and name the files that are stale

What it builds, for each language in LANGS (Russian and English):

* ``docs/<lang>/features.md`` — every feature in tables by chapter, from
  ``docs/src/features/*.toml`` (one file a chapter, both languages side by side) and the
  page's head, ``docs/src/features/head.<lang>.md``;
* ``docs/<lang>/comparison.md`` — fedtail next to other clients, one matrix a chapter;
* ``docs/<lang>/config.md`` — every config option, from
  ``fedtail/data/config.example.<lang>.toml`` (see ``tools/config_doc.py``);
* generated parts in ``docs/<lang>/parts/``: ``features-short``, ``only-in-fedtail``,
  ``whats-new``, ``roadmap``;
* ``docs/<lang>/lanes.md`` — how to write a lane: ``docs/src/lanes/head.<lang>.md``, then
  every key of a lane and of a condition with every word it takes, the words from the core
  (``fedtail/core/atoms.py``), what each means from ``docs/src/lanes/words.toml``;
* the deep dive of the in-app help, ``fedtail/data/help/<lang>/ref/`` — copies of
  ``features.md``, ``config.md``, ``comparison.md`` and ``lanes.md``, so the help works
  offline.

Then it expands includes. Any Markdown file in the repository's documentation (the
READMEs, ``docs/``, the in-app help in ``fedtail/data/help/``) may hold::

    <!-- include: parts/principles -->
    …whatever was put here last time…
    <!-- /include -->

and the text between the markers is replaced by ``docs/<lang>/parts/principles.md``
(falling back to ``docs/en/…`` when a language has no such part). The language is the
file's own: ``README.md`` is English, ``README.ru.md`` Russian, ``docs/<lang>/`` and
``fedtail/data/help/<lang>/`` theirs; ``lang=ru`` in the marker says it outright for
anything else. ``shift=1`` pushes the part's headings one level down. The markers are
HTML comments, so GitHub shows the file as it is, and the in-app help strips them.

Links inside parts go from the repository's root (``/docs/en/features.md``): GitHub
resolves them from anywhere, the help window and the site rewrite them.
"""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import config_doc  # noqa: E402  (tools/ is not a package)

LANGS = ("ru", "en")
FEATURES = ROOT / "docs" / "src" / "features"
STATUSES = ("has", "partly", "no", "planned", "wont", "undecided")
IN_TABLES = ("has", "partly", "no", "planned")  # wont / undecided: only at the end
CLIENTS = ("Mastodon web", "Tusky", "Ivory", "Phanpy", "Elk", "Tokodon", "Ice Cubes",
           "Fedilab", "Sengi", "Megalodon", "tut", "Tuba", "Whalebird")
TEXT_FIELDS = ("name", "status_note", "config", "api", "others", "note", "size", "why",
               "details")
REF_PAGES = ("features.md", "config.md", "comparison.md", "lanes.md")  # copied into the help's ref/
CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")
VERSION = re.compile(r"^\d+\.\d+\.\d+$")

L = {
    "ru": {
        "status": {"has": "есть", "partly": "частично", "no": "нет", "planned": "в планах",
                   "wont": "не будем", "undecided": "не решено"},
        "what": "Что", "status_col": "Статус", "since": "С версии", "config": "Конфиг",
        "api": "API / протокол", "others": "У других", "note": "Заметка",
        "chapter": "Раздел", "size": "Размер", "why": "Почему", "more": "Подробнее",
        "contents": "Содержание", "in_progress": "в работе",
        "ap_title": "ActivityPub напрямую",
        "parity_title": "Пять интерфейсов",
        "parity_intro": "fedtail — это окно Qt (KDE, Windows), окно GTK (GNOME), терминал, "
                        "веб-страница и приложение для Android; ядро у них одно. Ниже — только "
                        "то, что есть не везде, и почему. ✓ — есть, ◐ — частично, — — нет, "
                        "· — там не нужно. Таблицу держит в честности тест: функция, которая "
                        "появилась или пропала в одном из компьютерных интерфейсов, без "
                        "строчки здесь не пройдёт; у телефона свои экраны и слова — его "
                        "столбец сверен по коду руками, а всё, чего на телефоне пока нет, — в "
                        "следующей главе.",
        "parity_head": ["Что", "Qt", "GTK", "Терминал", "Веб", "Android", "Почему"],
        "android_title": "Android: что на телефоне есть и чего пока нет",
        "android_intro": "Возможности из списка выше, которых в приложении для Android нет или "
                         "есть не целиком (◐ — частично, — — нет, · — телефону не нужно). "
                         "Остальное на телефоне есть.",
        "android_head": ["Что", "Android", "Почему"],
        "parity_areas": {"window": "Окно, аккаунты, вход", "reading": "Чтение",
                         "media": "Картинки и видео", "writing": "Редактор",
                         "app": "Сервер, настройки, справка, отладка"},
        "ap_intro": "Всё здесь — запросы к чужим серверам без твоего токена: там видят только "
                    "твой IP. Серверы, требующие подписи запросов (secure mode), просто "
                    "ничего не отдадут, и fedtail тихо обходится тем, что знает твой сервер.",
        "plans_title": "Планы",
        "plans_intro": "Каждая возможность приходит выключаемой, по одной, с записью здесь и "
                       "строкой в CHANGELOG. Порядок примерный: сначала дешёвое, потом "
                       "крупное.",
        "wont_title": "Не будем",
        "undecided_title": "Нет и пока не решено",
        "cmp_title": "fedtail и другие клиенты",
        "cmp_intro": "Те же возможности, что в [полном списке](/docs/ru/features.md), — "
                     "одной матрицей на главу: есть ли такое у других клиентов. ✓ — есть, "
                     "пусто — нет или неизвестно. Сведения — из README и заметок к релизам "
                     "(осень 2026 года) и общих знаний, без проверки каждого вживую; "
                     "подробности и оговорки — в столбце «У других» полного списка.",
        "cmp_marks": "У fedtail: ✓ — есть, ◐ — частично, — — нет, ⏳ — в планах.",
        "cmp_count": "Только в fedtail — **{n}** возможностей из {total} сравнённых.",
        "short_title": "Коротко обо всём, что есть",
        "only_title": "Только в fedtail",
        "new_in_progress": "**{v} (в работе):**",
        "new_release": "**{v}:**",
        "new_none": "Новых возможностей пока нет.",
    },
    "en": {
        "status": {"has": "has", "partly": "partly", "no": "no", "planned": "planned",
                   "wont": "won't do", "undecided": "not decided"},
        "what": "What", "status_col": "Status", "since": "Since", "config": "Config",
        "api": "API / protocol", "others": "Others", "note": "Note",
        "chapter": "Chapter", "size": "Size", "why": "Why", "more": "In detail",
        "contents": "Contents", "in_progress": "in progress",
        "ap_title": "ActivityPub directly",
        "parity_title": "Five interfaces",
        "parity_intro": "fedtail is a Qt window (KDE, Windows), a GTK window (GNOME), a "
                        "terminal, a web page and an Android app; they share one core. Below is "
                        "only what isn't everywhere, and why. ✓ — has it, ◐ — in part, — — no, "
                        "· — doesn't belong there. A test keeps the table honest: a function "
                        "that appears or goes in one of the desktop interfaces doesn't pass "
                        "without its line here; the phone has screens and words of its own — "
                        "its column is checked against its code by hand, and all the phone "
                        "lacks so far is in the next chapter.",
        "parity_head": ["What", "Qt", "GTK", "Terminal", "Web", "Android", "Why"],
        "android_title": "Android: what the phone has and hasn't yet",
        "android_intro": "The features of the list above that the Android app lacks or has in "
                         "part (◐ — in part, — — no, · — a phone doesn't need it). All the "
                         "rest the phone has.",
        "android_head": ["What", "Android", "Why"],
        "parity_areas": {"window": "The window, accounts, logging in", "reading": "Reading",
                         "media": "Pictures and video", "writing": "The editor",
                         "app": "The server, settings, help, debugging"},
        "ap_intro": "Everything here is a request to other servers without your token: they "
                    "see only your IP. Servers that require signed requests (secure mode) "
                    "simply give nothing, and fedtail quietly makes do with what your own "
                    "server knows.",
        "plans_title": "Plans",
        "plans_intro": "Each feature comes switchable, one at a time, with its entry here and a "
                       "line in the CHANGELOG. The order is rough: the cheap first, the big "
                       "later.",
        "wont_title": "Won't do",
        "undecided_title": "Not there and not decided",
        "cmp_title": "fedtail and other clients",
        "cmp_intro": "The features of the [full list](/docs/en/features.md), as one matrix a "
                     "chapter: whether other clients have the same. ✓ — they do, empty — "
                     "they don't or it's unknown. From their READMEs and release notes "
                     "(autumn 2026) and general knowledge, without trying each one live; the "
                     "details and remarks are in the “Others” column of the full list.",
        "cmp_marks": "fedtail: ✓ — has, ◐ — partly, — — no, ⏳ — planned.",
        "cmp_count": "Only in fedtail — **{n}** features of the {total} compared.",
        "short_title": "Everything there is, in short",
        "only_title": "Only in fedtail",
        "new_in_progress": "**{v} (in progress):**",
        "new_release": "**{v}:**",
        "new_none": "No new features yet.",
    },
}


class DocsError(Exception):
    pass


# ---- the feature sources ---------------------------------------------------------------

def _t(value, lang):
    """A text field: a plain string is the same in every language, a table has one each."""
    if value is None or isinstance(value, str):
        return value
    return value.get(lang)


def version():
    text = (ROOT / "fedtail" / "__init__.py").read_text("utf-8")
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def last_release():
    """The newest released version in the CHANGELOG (the one with a date)."""
    text = (ROOT / "CHANGELOG.md").read_text("utf-8")
    m = re.search(r"^## (\d+\.\d+\.\d+) — \d{4}-\d\d-\d\d", text, re.M)
    return m.group(1) if m else None


def _vkey(v):
    return tuple(int(x) for x in v.split("."))


def load_features(folder=FEATURES):
    """[chapter] from docs/src/features/*.toml, checked: every text in every language,
    known statuses and clients, ids unique, "since" only for what exists."""
    chapters, ids, problems = [], set(), []
    current = version().split(".dev")[0]
    for path in sorted(folder.glob("*.toml")):
        data = tomllib.loads(path.read_text("utf-8"))
        where = path.name
        for k in ("id", "title"):
            if k not in data:
                problems.append(f"{where}: no {k}")
        for lang in LANGS:
            for k in ("title", "intro"):
                if k in data and not _t(data[k], lang):
                    problems.append(f"{where}: {k} has no {lang}")
        for f in data.get("feature", []):
            fid = f.get("id", "?")
            at = f"{where}: {fid}"
            if fid in ids:
                problems.append(f"{at}: the id is taken")
            ids.add(fid)
            if f.get("status") not in STATUSES:
                problems.append(f"{at}: status {f.get('status')!r} — one of {STATUSES}")
            if "name" not in f:
                problems.append(f"{at}: no name")
            for k in TEXT_FIELDS:
                v = f.get(k)
                if v is None:
                    continue
                if isinstance(v, str):
                    if CYRILLIC.search(v):
                        problems.append(f"{at}: {k} is Russian — write {k}.ru and {k}.en")
                    continue
                for lang in LANGS:
                    if not v.get(lang):
                        problems.append(f"{at}: {k} has no {lang}")
                for lang in v:
                    if lang not in LANGS:
                        problems.append(f"{at}: {k}.{lang} — not one of {LANGS}")
            since = f.get("since")
            if f.get("status") in ("has", "partly"):
                if not since:
                    problems.append(f"{at}: since — which version has it first")
                elif not VERSION.match(since):
                    problems.append(f"{at}: since {since!r} is not X.Y.Z")
                elif _vkey(since) > _vkey(current):
                    problems.append(f"{at}: since {since} is past this version {current}")
            elif since:
                problems.append(f"{at}: since — only for what fedtail has")
            for c in f.get("clients", []):
                if c != "all" and c not in CLIENTS:
                    problems.append(f"{at}: client {c!r} — one of {CLIENTS} or \"all\"")
        data["file"] = where
        chapters.append(data)
    if problems:
        raise DocsError("docs/src/features:\n  " + "\n  ".join(problems))
    return chapters


# ---- rendering helpers ---------------------------------------------------------------

def _cell(s):
    return (s or "—").replace("\n", " ").replace("|", "\\|")


def _table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    return out


def _status(f, lang):
    s = L[lang]["status"][f["status"]]
    note = _t(f.get("status_note"), lang)
    return f"{s} — {note}" if note else s


def _anchor(title):
    return config_doc._anchor(title)


def _features(chapters, *statuses):
    for ch in chapters:
        for f in ch.get("feature", []):
            if f["status"] in statuses:
                yield ch, f


# ---- docs/<lang>/features.md --------------------------------------------------------

def render_roadmap(chapters, lang):
    t = L[lang]
    out = [f"## {t['plans_title']}", "", t["plans_intro"], ""]
    out += _table([t["what"], t["chapter"], t["config"], t["size"]],
                  [[_t(f["name"], lang), _t(ch["title"], lang), _t(f.get("config"), lang),
                    _t(f.get("size"), lang)]
                   for ch, f in _features(chapters, "planned")])
    out += ["", f"## {t['wont_title']}", ""]
    out += _table([t["what"], t["why"]],
                  [[_t(f["name"], lang), _t(f.get("why"), lang)]
                   for _, f in _features(chapters, "wont")])
    out += ["", f"## {t['undecided_title']}", ""]
    out += _table([t["what"], t["others"], t["note"]],
                  [[_t(f["name"], lang), _t(f.get("others"), lang), _t(f.get("note"), lang)]
                   for _, f in _features(chapters, "undecided")])
    return "\n".join(out) + "\n"


def render_features(chapters, lang):
    t = L[lang]
    head = (FEATURES / f"head.{lang}.md").read_text("utf-8")
    v = version()
    shown = v.split(".dev")[0] + (f" ({t['in_progress']})" if ".dev" in v else "")
    titles = [_t(ch["title"], lang) for ch in chapters]
    titles += [t["parity_title"], t["android_title"], t["ap_title"], t["plans_title"],
               t["wont_title"], t["undecided_title"]]
    contents = " · ".join(f"[{x}](#{_anchor(x)})" for x in titles)
    out = [head.replace("@VERSION@", shown).replace("@CONTENTS@", contents).rstrip(), ""]
    for ch in chapters:
        rows = [f for f in ch.get("feature", []) if f["status"] in IN_TABLES]
        out += ["---", "", f"## {_t(ch['title'], lang)}", ""]
        if ch.get("intro"):
            out += [_t(ch["intro"], lang), ""]
        cols = [k for k in ("config", "api", "others", "note") if any(k in f for f in rows)]
        head_row = [t["what"], t["status_col"], t["since"]] + [t[k] for k in cols]
        out += _table(head_row, [[_t(f["name"], lang), _status(f, lang), f.get("since")]
                                 + [_t(f.get(k), lang) for k in cols] for f in rows])
        details = [f for f in ch.get("feature", []) if f.get("details")]
        if details:
            out += ["", f"<details><summary>{t['more']}</summary>", ""]
            for f in details:
                text = _t(f["details"], lang)
                sep = "\n\n" if text.startswith(("- ", "1. ")) else " "  # a list: below
                out += [f"**{_t(f['name'], lang)}.**{sep}{text}", ""]
            out += ["</details>"]
        out.append("")
    out += ["---", "", render_parity(lang).rstrip(), ""]
    out += ["---", "", render_android(chapters, lang).rstrip(), ""]
    out += ["---", "", f"## {t['ap_title']}", "", t["ap_intro"], ""]
    out += _table([t["what"], t["status_col"], t["config"]],
                  [[_t(f["name"], lang), _status(f, lang), _t(f.get("config"), lang)]
                   for ch in chapters for f in ch.get("feature", []) if f.get("activitypub")])
    out += ["", "---", "", render_roadmap(chapters, lang)]
    return "\n".join(out).rstrip() + "\n"


PARITY_MARK = {"has": "✓", "partly": "◐", "no": "—", "na": "·"}
PARITY = ROOT / "docs" / "src" / "parity.toml"


FIVE = ("qt", "gtk", "tui", "web", "android")


def _with_android(note, android_note, lang):
    a = _t(android_note, lang)
    n = _t(note, lang)
    return " ".join(x for x in (n, f"Android: {a}" if a else "") if x)


def render_android(chapters, lang):
    """The phone's chapter: every feature the desktop has that the Android app lacks or
    has in part, by chapter, with why (docs/src/features: android, android_note)."""
    t = L[lang]
    out = [f"## {t['android_title']}", "", t["android_intro"], ""]
    for ch in chapters:
        rows = [f for f in ch.get("feature", []) if f["status"] in ("has", "partly")
                and f.get("android", "has") != "has"]
        if not rows:
            continue
        out += [f"### {_t(ch['title'], lang)}", ""]
        out += _table(t["android_head"], [[_t(f["name"], lang), PARITY_MARK[f["android"]],
                                           _t(f.get("android_note"), lang)] for f in rows])
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_parity(lang):
    """The "Five interfaces" chapter: what isn't in all of them, from docs/src/parity.toml
    (which tests/test_parity.py holds against the code)."""
    import tomllib
    t = L[lang]
    with open(PARITY, "rb") as f:
        reg = tomllib.load(f)
    out = [f"## {t['parity_title']}", "", t["parity_intro"], ""]
    caps = reg.get("capability", [])
    for area, title in t["parity_areas"].items():
        rows = [c for c in caps if c.get("area") == area
                and any(c.get(fe, "has") != "has" for fe in FIVE)]
        if not rows:
            continue
        out += [f"### {title}", ""]
        out += _table(t["parity_head"], [
            [_t(c["name"], lang)] + [PARITY_MARK[c.get(fe, "has")] for fe in FIVE]
            + [_with_android(c.get("note"), c.get("android_note"), lang)] for c in rows])
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# ---- docs/<lang>/lanes.md ----------------------------------------------------------

LANES = ROOT / "docs" / "src" / "lanes"
LANE_WORDS = {
    "ru": {"rule_keys": "Ключи ленты", "cond_keys": "Ключи условия", "words": "Слова",
           "key": "Ключ", "word": "Слово", "takes": "Что пишется", "means": "Что значит",
           "of": "Слова ключа `{k}`", "icons": "Картинки (`icon`)",
           "icons_intro": "Своя картинка темы с тем же именем берёт верх; без `icon` — "
                          "картинка ленты набора по её имени, у своей — как у списка.",
           "any_word": "любое слово", "see": "см. ниже"},
    "en": {"rule_keys": "A lane's keys", "cond_keys": "A condition's keys", "words": "Words",
           "key": "Key", "word": "Word", "takes": "What goes there", "means": "What it means",
           "of": "The words of `{k}`", "icons": "Pictures (`icon`)",
           "icons_intro": "A theme's own picture of that name wins; no `icon` — a set's lane "
                          "wears the one of its name, one's own a list's.",
           "any_word": "any word", "see": "see below"},
}


def lane_words():
    """{axis: [words]} — every word a lane's or a condition's key takes, from the core;
    a prefix ("list:", "tag:") stands for the words that start with it."""
    from fedtail.core import atoms
    out = {}
    for key, known in atoms._SET_KEYS.items():
        if known:
            out[key] = sorted(known)
    out["source"] += list(atoms.SOURCE_PREFIXES)
    out["has"] += list(atoms.HAS_PREFIXES)
    out["author"] += ["@nick@host", "domain:"]
    out["text_in"] = sorted(atoms.TEXT_IN)
    out["age_of"] = ["post", "original"]
    for key, words in atoms._RULE_WORDS.items():
        out[key] = [w for w in sorted(words) if w]
    out["switches"] = list(atoms.SWITCHES)
    return out


def lane_keys():
    """(the keys of a lane, the keys of a condition), from the core."""
    from fedtail.core import atoms
    return sorted(atoms.RULE_KEYS), sorted(atoms.CONDITION_KEYS)


def load_lane_words():
    with open(LANES / "words.toml", "rb") as f:
        return tomllib.load(f)


def _ticks(words):
    return ", ".join(f"`{w}`" for w in words)


def render_lanes(lang):
    """docs/<lang>/lanes.md: the guide's head, then every key and word."""
    from fedtail.core import atoms
    t, d = LANE_WORDS[lang], load_lane_words()
    words = lane_words()
    rule_keys, cond_keys = lane_keys()

    def takes(key):
        if key == "icon":
            return t["see"]
        if key in words:
            return _ticks(words[key]) if len(words[key]) <= 6 else t["see"]
        return _t(entry(key).get("takes"), lang) or ""

    def entry(key):
        return d["rule"].get(key) or d["condition"].get(key) or {}

    out = [(LANES / f"head.{lang}.md").read_text("utf-8").rstrip(), ""]
    for title, keys, where in ((t["rule_keys"], rule_keys, "rule"),
                               (t["cond_keys"], cond_keys, "condition")):
        out += [f"## {title}", ""]
        out += _table([t["key"], t["takes"], t["means"]],
                      [[f"`{k}`", takes(k), _t(d[where][k], lang)] for k in keys])
        out.append("")
    out += [f"## {t['words']}", ""]
    for key, ws in words.items():
        out += [f"### {t['of'].format(k=key)}", ""]
        out += _table([t["word"], t["means"]],
                      [[f"`{w}…`" if w.endswith(":") else f"`{w}`",
                        _t(d["word"][key][w], lang)] for w in ws])
        out.append("")
    out += [f"### {t['icons']}", "", t["icons_intro"], "", _ticks(atoms.LANE_ICONS), ""]
    return "\n".join(out).rstrip() + "\n"


# ---- docs/<lang>/comparison.md ------------------------------------------------------

MARK = {"has": "✓", "partly": "◐", "no": "—", "planned": "⏳"}


def render_comparison(chapters, lang):
    t = L[lang]
    out = [f"# {t['cmp_title']}", "", t["cmp_intro"], "", t["cmp_marks"], ""]
    total = only = 0
    for ch in chapters:
        rows = [f for f in ch.get("feature", [])
                if f["status"] in IN_TABLES and f.get("clients") is not None]
        if not rows:
            continue
        out += [f"## {_t(ch['title'], lang)}", ""]
        body = []
        for f in rows:
            cl = f["clients"]
            total += 1
            only += not cl
            body.append([_t(f["name"], lang), MARK[f["status"]]]
                        + ["✓" if "all" in cl or c in cl else " " for c in CLIENTS])
        out += _table([t["what"], "fedtail", *CLIENTS], body)
        out.append("")
    out += [t["cmp_count"].format(n=only, total=total)]
    return "\n".join(out) + "\n"


# ---- generated parts ----------------------------------------------------------------

def render_short(chapters, lang):
    out = []
    for ch in chapters:
        names = [_t(f["name"], lang) for f in ch.get("feature", [])
                 if f["status"] in ("has", "partly")]
        if names:
            out.append(f"- **{_t(ch['title'], lang)}:** " + " · ".join(names))
    return "\n".join(out) + "\n"


def render_only(chapters, lang):
    out = []
    for ch in chapters:
        names = [_t(f["name"], lang) for f in ch.get("feature", [])
                 if f["status"] in ("has", "partly") and f.get("clients") == []]
        if names:
            out.append(f"- **{_t(ch['title'], lang)}:** " + " · ".join(names))
    return "\n".join(out) + "\n"


def render_new(chapters, lang):
    t = L[lang]
    v = version()
    groups = []
    if ".dev" in v:
        groups.append((v.split(".dev")[0], t["new_in_progress"]))
    rel = last_release()
    if rel:
        groups.append((rel, t["new_release"]))
    out = []
    for ver, label in groups:
        names = [_t(f["name"], lang) for _, f in _features(chapters, "has", "partly")
                 if f.get("since") == ver]
        if names:
            out += [label.format(v=ver), ""] + [f"- {n}" for n in names] + [""]
    return ("\n".join(out).rstrip() if out else t["new_none"]) + "\n"


# ---- includes -------------------------------------------------------------------------

INCLUDE = re.compile(
    r"(?P<open><!-- include: (?P<name>[\w./-]+)(?P<opts>(?: \w+=\S+)*) -->)\n"
    r".*?"
    r"(?P<close><!-- /include -->)", re.S)


MARKER = re.compile(r"^<!-- /?include[^>]*-->\n", re.M)


def lang_of(path):
    rel = path.relative_to(ROOT).as_posix()
    if rel == "README.md":
        return "en"
    if rel == "README.ru.md":
        return "ru"
    for lang in LANGS:
        if rel.startswith((f"docs/{lang}/", f"fedtail/data/help/{lang}/")):
            return lang
    return None


def _part(name, lang, generated):
    for lg in (lang, "en"):
        key = ROOT / "docs" / lg / f"{name}.md"
        if key in generated:
            return generated[key]
        if key.exists():
            return key.read_text("utf-8")
    raise DocsError(f"no part {name!r} in docs/{lang}/ or docs/en/")


def _shift(text, n):
    if not n:
        return text
    return re.sub(r"(?m)^(#{1,5}) ", lambda m: "#" * (len(m.group(1)) + n) + " ", text)


def expand(text, path, generated):
    """The text with every include filled in anew."""
    def fill(m):
        opts = dict(o.split("=", 1) for o in m.group("opts").split())
        lang = opts.get("lang") or lang_of(path)
        if lang not in LANGS:
            raise DocsError(f"{path.relative_to(ROOT)}: which language? lang=ru or lang=en")
        part = _part(m.group("name"), lang, generated)
        if "/parts/" in f"/{m.group('name')}" and INCLUDE.search(part):
            raise DocsError(f"part {m.group('name')!r} includes another part: keep parts flat")
        part = MARKER.sub("", part).strip("\n")  # a whole page comes in flat
        part = _shift(part, int(opts.get("shift", 0)))
        return f"{m.group('open')}\n{part}\n{m.group('close')}"
    return INCLUDE.sub(fill, text)


def doc_files():
    files = [ROOT / "README.md", ROOT / "README.ru.md"]
    files += sorted(p for p in (ROOT / "docs").rglob("*.md") if "src" not in p.parts)
    files += sorted((ROOT / "fedtail" / "data" / "help").rglob("*.md"))
    return [p for p in files if p.exists()]


# ---- the whole build --------------------------------------------------------------------

def build():
    """{path: text} of every file this script owns, as it should be now."""
    chapters = load_features()
    out = {}
    for lang in LANGS:
        d = ROOT / "docs" / lang
        out[d / "features.md"] = render_features(chapters, lang)
        out[d / "comparison.md"] = render_comparison(chapters, lang)
        out[d / "parts" / "features-short.md"] = render_short(chapters, lang)
        out[d / "parts" / "only-in-fedtail.md"] = render_only(chapters, lang)
        out[d / "parts" / "whats-new.md"] = render_new(chapters, lang)
        out[d / "parts" / "roadmap.md"] = render_roadmap(chapters, lang)
        out[d / "parts" / "parity.md"] = render_parity(lang)
        out[d / "parts" / "android.md"] = render_android(chapters, lang)
        out[d / "lanes.md"] = render_lanes(lang)
        example = config_doc.example_path(lang)
        out[d / "config.md"] = config_doc.build(example.read_text("utf-8"), lang)
    # parts first (they include nothing), then the generated pages, then the rest — so
    # whatever a file includes is already up to date when it is read
    everything = set(doc_files()) | set(out)
    order = sorted(everything, key=lambda p: ("parts" not in p.parts, p not in out, str(p)))
    for path in order:
        text = out.get(path)
        if text is None:
            text = path.read_text("utf-8")
        new = expand(text, path, out)
        if path in out or new != text:
            out[path] = new
    # the deep dive of the in-app help: the same pages, shipped inside the package
    for lang in LANGS:
        for name in REF_PAGES:
            out[ROOT / "fedtail" / "data" / "help" / lang / "ref" / name] = \
                out[ROOT / "docs" / lang / name]
    return out


def main(argv):
    try:
        files = build()
    except DocsError as e:
        print(e, file=sys.stderr)
        return 2
    stale = [p for p, text in files.items()
             if not p.exists() or p.read_text("utf-8") != text]
    if "--check" in argv:
        if stale:
            print("out of date — run python3 tools/docs_build.py:\n  "
                  + "\n  ".join(str(p.relative_to(ROOT)) for p in sorted(stale)))
            return 1
        return 0
    for p in sorted(stale):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(files[p], "utf-8")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
