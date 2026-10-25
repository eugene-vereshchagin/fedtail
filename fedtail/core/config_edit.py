"""Setting one option in the user's config.toml, the way a person would: that one line
changes and nothing else — the comments, the order, the user's own notes, the other
values stay as they are. The file stays the one place the settings live: the settings
window (frontends/common/settings.py) only reads it and writes it through here.

    text = set_value(text, "ui", "theme", "paper")   # `theme = "paper"`
    text = unset(text, "ui", "theme")                # `#theme = …`: the default again
    save(path, {("ui", "theme"): "paper", ("ui", "font_size"): UNSET})

Where the option is:
* set (`key = …`, maybe over several lines for a list) — its value is replaced;
* commented out (`#key = …`, as --update-config leaves new ones) — that line becomes
  `key = …`, the explanation above it stays;
* not mentioned — it goes at the end of its section, with the reference's explanation
  above it; a section the file doesn't have goes at the end of the file.

save() checks the new text reads back to the very values asked for and passes
config.validate, keeps the old file as config.toml.bak and replaces the file in one
step (a crash halfway leaves the old one).
"""

from __future__ import annotations

import json
import os
import re
import tomllib

_HEADER = re.compile(r"^\s*\[([A-Za-z0-9_]+)\]\s*(#.*)?$")


class _Unset:
    def __repr__(self):
        return "UNSET"


UNSET = _Unset()  # save(): back to the default (the line commented out)


def toml_value(v):
    """A value as TOML writes it: true, 12, "text", ["a", "b"]."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)  # TOML basic strings escape as JSON does
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    raise TypeError(f"can't write {type(v).__name__} to the config")


def _option(key):
    return re.compile(r"^(\s*)(#\s*)?" + re.escape(key) + r"\s*=")


def _value_end(lines, i):
    """The last line of the option starting at lines[i]: a list may go on for several
    lines, until its brackets close (strings and comments don't count)."""
    depth, j = 0, i
    while j < len(lines):
        line = lines[j]
        body = line.split("=", 1)[1] if j == i and "=" in line else line
        if j > i:
            body = body.lstrip("#") if lines[i].lstrip().startswith("#") else body
        in_str = None
        k = 0
        while k < len(body):
            c = body[k]
            if in_str:
                if c == "\\" and in_str == '"':
                    k += 2
                    continue
                if c == in_str:
                    in_str = None
            elif c in "\"'":
                in_str = c
            elif c == "#":
                break
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
            k += 1
        if depth <= 0:
            return j
        j += 1
    return i  # brackets never closed: the one line, as the file is broken anyway


def _sections(lines):
    """{section: (header line, end line exclusive)} of the real (not commented) headers."""
    out, cur, start = {}, None, 0
    for i, line in enumerate(lines):
        m = _HEADER.match(line)
        if m:
            if cur is not None:
                out.setdefault(cur, (start, i))
            cur, start = m.group(1), i
    if cur is not None:
        out.setdefault(cur, (start, len(lines)))
    return out


def _find(lines, section, key):
    """(first, last, commented) of the option inside its section, or None. A set line
    wins over a commented-out one."""
    span = _sections(lines).get(section)
    if span is None:
        return None
    pat = _option(key)
    commented = None
    i = span[0] + 1
    while i < span[1]:
        m = pat.match(lines[i])
        if m:
            end = _value_end(lines, i)
            if not m.group(2):
                return i, end, False
            if commented is None:
                commented = (i, end, True)
            i = end + 1
            continue
        i += 1
    return commented


def _doc_of(section, key, example_text):
    if not example_text:
        return []
    from .config_update import parse_example
    for k, block in parse_example(example_text).get(section, []):
        if k == key:
            return block[:-1]
    return []


def set_value(text, section, key, value, example_text=""):
    """The text with section.key set to value (see the module's docstring)."""
    lines = text.splitlines()
    line = f"{key} = {toml_value(value)}"
    found = _find(lines, section, key)
    if found is not None:
        first, last, _c = found
        indent = re.match(r"^(\s*)", lines[first]).group(1)
        lines[first:last + 1] = [indent + line]
    else:
        span = _sections(lines).get(section)
        block = _doc_of(section, key, example_text) + [line]
        if span is None:
            while lines and not lines[-1].strip():
                lines.pop()
            lines += ["", f"[{section}]"] + block
        else:
            from .config_update import _is_comment
            end = span[1]
            # above the blank lines and the next chapter's banner, under the last option
            while end > span[0] + 1 and (not lines[end - 1].strip()
                                         or _is_comment(lines[end - 1])):
                end -= 1
            lines[end:end] = [""] + block if lines[end - 1].strip() else block
    return "\n".join(lines) + "\n"


def unset(text, section, key, default=None):
    """The text with section.key commented out — the program's default from then on.
    `default` (when given) is written in the commented line, as the reference has it."""
    lines = text.splitlines()
    found = _find(lines, section, key)
    if found is None or found[2]:
        return text if text.endswith("\n") else text + "\n"
    first, last, _c = found
    indent = re.match(r"^(\s*)", lines[first]).group(1)
    shown = toml_value(default) if default is not None else \
        lines[first].split("=", 1)[1].strip()
    lines[first:last + 1] = [f"{indent}#{key} = {shown}"]
    return "\n".join(lines) + "\n"


def is_set(text, section, key):
    found = _find(text.splitlines(), section, key)
    return found is not None and not found[2]


def apply(text, changes, example_text=""):
    """Every change {(section, key): value or UNSET} put in the text."""
    from .config import DEFAULTS
    for (section, key), value in changes.items():
        if value is UNSET:
            text = unset(text, section, key, DEFAULTS.get(section, {}).get(key))
        else:
            text = set_value(text, section, key, value, example_text)
    return text


class SaveError(Exception):
    pass


def check(new_text, changes):
    """(config, warnings) of the new text; SaveError if it doesn't read, doesn't pass
    validate, or doesn't say what was asked."""
    from . import config
    try:
        user = tomllib.loads(new_text)
    except tomllib.TOMLDecodeError as e:
        raise SaveError(f"the file wouldn't read: {e}") from None
    for (section, key), value in changes.items():
        got = user.get(section, {}).get(key, UNSET)
        want = UNSET if value is UNSET else (list(value) if isinstance(value, tuple)
                                             else value)
        if got != want and not (value is UNSET and got is UNSET):
            raise SaveError(f"{section}.{key}: wrote {want!r}, reads back {got!r}")
    try:
        return config.validate(user)
    except config.ConfigError as e:
        raise SaveError(str(e)) from None


# the files backed up by this run: config.toml.bak keeps the file as it was before the
# run's first change — the settings window saves at every tick and every step of a
# number, and a .bak written each time held only the step before (25.10)
_backed_up = set()


def save(path, changes, example_text=None):
    """Put the changes into the file at path. Returns (config, warnings) of the new
    file; SaveError and the file untouched if the result isn't right. The file as it
    was before this run's first change stays in <file>.bak; a symlinked config (one
    kept with the dotfiles) is written through the link, the link stays."""
    from . import config
    path = os.path.realpath(os.fspath(path))
    try:
        with open(path, encoding="utf-8") as f:
            old = f.read()
    except FileNotFoundError:
        old = config.example_text(config.default_language())
    if example_text is None:
        example_text = config.example_text(config.language_of(old))
    new = apply(old, changes, example_text)
    result = check(new, changes)
    if new == old:
        return result
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if os.path.exists(path) and path not in _backed_up:
        with open(path + ".bak", "w", encoding="utf-8") as f:
            f.write(old)
        _backed_up.add(path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(new)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return result


__all__ = ["UNSET", "SaveError", "apply", "check", "is_set", "save", "set_value",
           "toml_value", "unset"]
