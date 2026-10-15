"""Keeping the user's config aware of every option.

The app never edits config.toml on its own. Instead:

* on every start it writes config.example.toml next to it — the complete,
  commented reference for this version (that file is ours, not the user's);
* it tells which options the user's file doesn't mention yet;
* `fedtail --update-config` inserts those options, commented out with their
  explanations, into the right sections of the user's file (a .bak is kept).
"""

import re

_HEADER = re.compile(r"^\s*#?\s*\[([A-Za-z0-9_]+)\]\s*$")
_OPTION = re.compile(r"^\s*#?\s*([A-Za-z0-9_]+)\s*=")


def parse_example(text):
    """{section: [(key, [lines: comments + the option line])]} in file order."""
    out, section, pending = {}, None, []
    for line in text.splitlines():
        m = _HEADER.match(line)
        if m:
            section, pending = m.group(1), []
            out.setdefault(section, [])
            continue
        if section is None:
            continue
        m = _OPTION.match(line)
        if m and line.lstrip().startswith("#") and not line.lstrip().startswith("# "):
            out[section].append((m.group(1), pending + [line]))
            pending = []
        elif line.lstrip().startswith("#"):
            pending.append(line)
        else:
            pending = []
    return out


def mentioned(text):
    """{section: {keys}} the user's file mentions, commented out or not."""
    out, section = {}, None
    for line in text.splitlines():
        m = _HEADER.match(line)
        if m:
            section = m.group(1)
            out.setdefault(section, set())
            continue
        m = _OPTION.match(line)
        if m and section:
            out[section].add(m.group(1))
    return out


def missing(user_text, example_text):
    have = mentioned(user_text)
    return [f"{sec}.{key}" for sec, opts in parse_example(example_text).items()
            for key, _ in opts if key not in have.get(sec, set())]


def update(user_text, example_text):
    """User text with every missing option added (commented) to its section."""
    have = mentioned(user_text)
    example = parse_example(example_text)
    lines = user_text.splitlines()

    # where each section of the user's file ends (insert point)
    ends, current = {}, None
    for i, line in enumerate(lines):
        m = _HEADER.match(line)
        if m:
            current = m.group(1)
        if current:
            ends[current] = i + 1
    # walk back over trailing blank lines, so additions sit with the section
    for sec, end in ends.items():
        while end > 0 and not lines[end - 1].strip():
            end -= 1
        ends[sec] = end

    inserts, appended = {}, []
    for sec, opts in example.items():
        add = [block for key, block in opts if key not in have.get(sec, set())]
        if not add:
            continue
        chunk = [line for block in add for line in block]
        if sec in ends:
            inserts.setdefault(ends[sec], []).extend(chunk)
        else:
            appended += ["", f"[{sec}]"] + chunk
    out = []
    for i, line in enumerate(lines):
        if i in inserts:
            out += inserts[i]
        out.append(line)
    if len(lines) in inserts:
        out += inserts[len(lines)]
    out += appended
    return "\n".join(out) + "\n"
