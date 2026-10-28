"""The config reference, docs/<lang>/config.md, from fedtail/data/config.example.<lang>.toml:
every option in tables by chapter, with its default and what it does. The example files
are the source — edit the explanations there; `tools/docs_build.py` builds this along
with the other documents (and `--check`s it):

    python3 tools/docs_build.py            # write docs/ru/config.md, docs/en/config.md…
    python3 tools/config_doc.py            # the same (kept for habit)

The Russian and English examples hold the very same options, values and order — only the
comments differ; a test compares them line by line.
"""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "fedtail" / "data"


def example_path(lang):
    return DATA / f"config.example.{lang}.toml"


BANNER = re.compile(r"^#\s*═{5,}\s*$")
CHAPTER = re.compile(r"^#\s+(\d+)\.\s+(.+?)\s*$")
SUB = re.compile(r"^#\s*──\s*(.+?)\s*─+\s*$")
SECTION = re.compile(r"^\[([A-Za-z0-9_]+)\]\s*$")
OPTION = re.compile(r"^([A-Za-z0-9_]+)\s*=")
FLAG = re.compile(r"^#\s{2,}(\S.*?)\s{2,}(\S.*)$")  # "#   -p, --profile ИМЯ    профиль…"

L = {
    "ru": {
        "head": """# Настройки fedtail

[English](/docs/en/config.md)

Справочник по всем ключам конфига, таблицами по главам. **Файл собирается сам** из
`fedtail/data/config.example.ru.toml` командой `python3 tools/docs_build.py` — правь
пояснения там, а не здесь (тест проверяет, что этот файл не отстал).

Что за возможность стоит за ключом и как это у других клиентов —
[список возможностей](/docs/ru/features.md).
""",
        "file_title": "конфиг профиля", "flags": "Ключи запуска", "chapters": "Главы",
        "how": "Как устроен конфиг", "key": "Ключ", "does": "Что делает",
        "default": "По умолчанию",
    },
    "en": {
        "head": """# fedtail settings

[По-русски](/docs/ru/config.md)

Every key of the config, in tables by chapter. **This file is built** from
`fedtail/data/config.example.en.toml` by `python3 tools/docs_build.py` — edit the
explanations there, not here (a test checks this file keeps up).

Which feature stands behind a key and how other clients do it —
[the feature list](/docs/en/features.md).
""",
        "file_title": "profile config", "flags": "Launch keys", "chapters": "Chapters",
        "how": "How the config works", "key": "Key", "does": "What it does",
        "default": "Default",
    },
}


def _toml(value):
    from fedtail.core.config_update import _toml as dump
    return dump(value)


def _text(lines):
    """Comment lines (without "#") as one cell. A line indented by two to four spaces is
    an item of its own (a choice in a list): a new line in the cell. A plain line, or one
    indented further (aligned under the line above), goes on the same line."""
    out = []
    for raw in lines:
        t = re.sub(r"\s{2,}", " ", raw.strip())
        if not t:
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if out and 2 <= indent - 1 <= 4:  # raw keeps the space after "#"
            out.append("<br>" + t)
        elif out:
            out[-1] += " " + t
        else:
            out.append(t)
    return "".join(out).replace("|", "\\|")


def _next_is_sub(body, line):
    i = body.index(line)
    for nxt in body[i + 1:]:
        if nxt.strip():
            return bool(SUB.match(nxt))
    return False


def _anchor(title):
    a = title.lower()
    a = re.sub(r"[^\w\- ]", "", a)
    return a.replace(" ", "-")


def build(example_text, lang="ru"):
    lab = L[lang]
    defaults = tomllib.loads(example_text)
    lines = example_text.splitlines()
    first = next(i for i, x in enumerate(lines) if BANNER.match(x))
    head, body = lines[:first], lines[first:]

    # the file's own header: paragraphs, "where it lives", the start-up keys
    paras, flags, para = [], [], []
    in_flags = False
    for raw in head[2:] if head and lab["file_title"] in head[0] else head:
        t = raw[1:].strip() if raw.startswith("#") else raw.strip()
        if t.startswith(lab["flags"]):
            in_flags = True
            if para:
                paras.append(" ".join(para))
                para = []
            continue
        if in_flags:
            if t.startswith(lab["chapters"]):
                break  # the chapters are listed from the file itself
            m = FLAG.match(raw)
            if m:
                flags.append([m.group(1), m.group(2)])
            elif t and flags:
                flags[-1][1] += " " + t
            continue
        if not t:
            if para:
                paras.append(" ".join(para))
                para = []
        else:
            para.append(t)
    if para:
        paras.append(" ".join(para))

    # chapters → sections → options
    chapters = []  # [title, intro, [blocks]]; block: [heading, intro, [(key, default, doc)]]
    comments, section, pending_title = [], None, False
    for raw in body:
        if BANNER.match(raw):
            pending_title = not pending_title if pending_title else True
            continue
        m = CHAPTER.match(raw)
        if m and pending_title:
            chapters.append([f"{m.group(1)}. {m.group(2)}", [], []])
            comments = []
            continue
        pending_title = False
        m = SUB.match(raw)
        if m:
            chapters[-1][2].append([m.group(1), [], []])
            comments = []
            continue
        m = SECTION.match(raw)
        if m:
            section = m.group(1)
            ch = chapters[-1]
            if ch[2] and not ch[2][-1][2] or _next_is_sub(body, raw):
                pass  # sub-headings (── … ──) name the blocks of this section
            else:
                intro = comments if ch[2] or ch[1] else []
                if not ch[2] and not ch[1]:
                    ch[1] = comments  # words under the chapter title, before [section]
                ch[2].append([f"`[{section}]`", intro, []])
            comments = []
            continue
        if raw.startswith("#"):
            # a comment is always a comment: an option is a live `key = value` line. Prose
            # may well start with "key = …" (`# open_at = "…" in its table`), and taking it
            # for a commented-out option made rows in one language only
            comments.append(raw[1:])
            continue
        m = OPTION.match(raw)
        if m and section:
            key = m.group(1)
            value = defaults.get(section, {}).get(key)
            chapters[-1][2][-1][2].append((f"{section}.{key}", value, _text(comments)))
            comments = []
            continue
        if not raw.strip():
            continue
        comments = []

    out = [lab["head"], f"## {lab['how']}", ""]
    for p in paras:
        out += [p, ""]
    if flags:
        out += [f"## {lab['flags']}", "", f"| {lab['key']} | {lab['does']} |", "|---|---|"]
        out += [f"| `{k.replace('|', chr(92) + '|')}` | {v} |" for k, v in flags]
        out.append("")
    out += [f"## {lab['chapters']}", ""]
    for title, _intro, blocks in chapters:
        secs = [b[0] for b in blocks if b[0].startswith("`[")]
        names = ", ".join(secs) or "`[ui]`"
        out.append(f"- [{title}](#{_anchor(title)}) — {names}")
    out.append("")
    for title, intro, blocks in chapters:
        out += [f"## {title}", ""]
        if intro and _text(intro):
            out += [_text(intro).replace("<br>", " "), ""]
        for heading, bintro, opts in blocks:
            out += [f"### {heading}", ""]
            if bintro and _text(bintro):
                out += [_text(bintro).replace("<br>", " "), ""]
            if opts:
                out += [f"| {lab['key']} | {lab['default']} | {lab['does']} |",
                        "|---|---|---|"]
                for key, value, doc in opts:
                    shown = _toml(value) if value is not None else "—"
                    out.append(f"| `{key}` | `{shown}` | {doc} |")
                out.append("")
    return "\n".join(out).rstrip() + "\n"


def main(argv):
    import docs_build
    return docs_build.main(argv)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tools"))
    sys.exit(main(sys.argv[1:]))
