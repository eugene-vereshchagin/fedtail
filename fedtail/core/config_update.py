"""Keeping the user's config aware of every option.

The app never edits config.toml on its own. Instead:

* on every start it writes config.example.toml next to it — the complete reference
  for this version, in chapters, every option set to its default with an explanation
  (that file is ours, not the user's);
* it tells which options the user's file doesn't mention yet;
* `python3 -m fedtail --update-config` inserts those options, commented out with their
  explanations, into the right sections of the user's file (a .bak is kept); it also
  brings the explanations of the options already there up to date (new themes, new
  choices) and drops commented-out options this version no longer has. The user's
  values and their own notes stay as they are;
* `python3 -m fedtail --rebuild-config` writes the file anew from the reference, in
  its chapters, with the user's values put in (their own notes don't survive that;
  a .bak is kept).
"""

import difflib
import json
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
        if m and not line.lstrip().startswith("# "):  # "key = …" or "#key = …"
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


def _is_comment(line):
    t = line.strip()
    return t.startswith("#") and not _OPTION.match(line) and not _HEADER.match(line)


def _ours(block, fresh):
    """Is this comment block an older version of our explanation (and not the
    user's own note)? Then it may be replaced by the fresh one."""
    if not block or not fresh:
        return False
    a, b = "\n".join(block), "\n".join(fresh)
    return block[0][:24] == fresh[0][:24] or \
        difflib.SequenceMatcher(None, a, b).ratio() >= 0.6


def refresh(user_text, example_text, report=None):
    """Explanations above options brought up to date; commented-out options this
    version doesn't know dropped (with their explanation). Values untouched."""
    example = parse_example(example_text)
    docs = {sec: {key: block[:-1] for key, block in opts} for sec, opts in example.items()}
    head_end = next((i for i, x in enumerate(example_text.splitlines()) if _HEADER.match(x)),
                    0)
    fresh_head = example_text.splitlines()[:head_end]
    lines = user_text.splitlines()
    out, section, refreshed, dropped = [], None, [], []
    first = next((i for i, x in enumerate(lines) if _HEADER.match(x)), len(lines))
    if lines[:first] != fresh_head and _ours([x for x in lines[:first] if x.strip()],
                                             [x for x in fresh_head if x.strip()]):
        out, start = list(fresh_head), first
    else:
        start = 0
    for line in lines[start:]:
        m = _HEADER.match(line)
        if m and not line.lstrip().startswith("#"):
            section = m.group(1)
            out.append(line)
            continue
        m = _OPTION.match(line)
        if section and m and not line.lstrip().startswith("# "):
            key = m.group(1)
            block_start = len(out)
            while block_start > 0 and _is_comment(out[block_start - 1]):
                block_start -= 1
            block = out[block_start:]
            known = docs.get(section, {})
            if key in known:
                fresh = known[key]
                if block != fresh and _ours(block, fresh):
                    out[block_start:] = fresh
                    refreshed.append(f"{section}.{key}")
            elif section in docs and line.lstrip().startswith("#"):
                # an option of an older version, never switched on: away with it
                del out[block_start:]  # with the explanation we wrote for it
                dropped.append(f"{section}.{key}")
                continue
        out.append(line)
    if report is not None:
        report["refreshed"], report["dropped"] = refreshed, dropped
    return "\n".join(out) + "\n"


def update(user_text, example_text, report=None):
    """User text with every missing option added (commented) to its section, the
    explanations refreshed and options of older versions dropped (see refresh)."""
    rep = {} if report is None else report
    rep["added"] = missing(user_text, example_text)
    user_text = refresh(user_text, example_text, rep)
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
    # walk back over trailing blank lines and the comments under the last option — the
    # banner of the next chapter, say: those belong to what follows, additions go above
    for sec, end in ends.items():
        while end > 0 and (not lines[end - 1].strip() or _is_comment(lines[end - 1])):
            end -= 1
        ends[sec] = end

    inserts, appended = {}, []
    for sec, opts in example.items():
        add = [block for key, block in opts if key not in have.get(sec, set())]
        if not add:
            continue
        # a blank line between options, as in the reference: one block, one option
        chunk = [line for block in add for line in [""] + block]
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
    return "\n".join(_spaced(out)) + "\n"


def _spaced(lines):
    """A blank line between an option and whatever comes next (the explanation of the
    next option, a chapter banner, a section header), as in the reference — files of
    older versions had none."""
    out = []
    for line in lines:
        if out and line.strip() and (_is_comment(line) or _HEADER.match(line)):
            prev = out[-1]
            if prev.strip() and _OPTION.match(prev) and not prev.lstrip().startswith("# "):
                out.append("")
        out.append(line)
    return out


def _toml(value):
    """One value written back as TOML (what tomllib gave us: bool, number, text,
    list, table)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_toml(x) for x in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_toml(v)}" for k, v in value.items()) + " }"
    return json.dumps(str(value), ensure_ascii=False)


def rebuild(user_text, example_text, report=None):
    """The reference file, chapter by chapter, with every value the user set put in
    its place. Options this version doesn't know are kept at the end of their
    section with a note. The user's own comments are not carried over."""
    import tomllib
    user = tomllib.loads(user_text)
    out, section, ends, kept = [], None, {}, []
    for line in example_text.splitlines():
        m = _HEADER.match(line)
        if m and not line.lstrip().startswith("#"):
            section = m.group(1)
            out.append(line)
            ends[section] = len(out)
            continue
        m = _OPTION.match(line)
        if section and m and not line.lstrip().startswith("#"):
            key = m.group(1)
            mine = user.get(section, {})
            if isinstance(mine, dict) and key in mine:
                line = f"{key} = {_toml(mine[key])}"
                kept.append(f"{section}.{key}")
            out.append(line)
            ends[section] = len(out)
            continue
        out.append(line)
    known = parse_example(example_text)
    extra, inserts = [], {}
    for sec, values in user.items():
        if not isinstance(values, dict):
            continue
        names = {k for k, _ in known.get(sec, [])}
        rest = [(k, v) for k, v in values.items() if k not in names]
        if not rest:
            continue
        lines = ["# не из этой версии — оставлено как было:"] + \
            [f"{k} = {_toml(v)}" for k, v in rest]
        extra += [f"{sec}.{k}" for k, _ in rest]
        if sec in ends:
            inserts[ends[sec]] = lines
        else:
            out += ["", f"[{sec}]"] + lines
    for at in sorted(inserts, reverse=True):
        out[at:at] = inserts[at]
    if report is not None:
        report["kept"], report["extra"] = kept, extra
    return "\n".join(out) + "\n"
