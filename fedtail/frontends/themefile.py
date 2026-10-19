"""Theme files: find, inherit, validate. Plain Python (no Qt), so it is testable.

Built-in themes live in fedtail/data/themes/. Your own go to
~/.config/fedtail/themes/<name>.toml (shared by all profiles) and win over a
built-in of the same name. A copy of every built-in is kept up to date in
~/.config/fedtail/themes/builtin/ to start from.
"""

import copy
import os
import re
import tomllib
from pathlib import Path

BUILTIN_DIR = Path(__file__).resolve().parent.parent / "data" / "themes"
REFERENCE = "system"  # this theme lists every key
_COLOR = re.compile(r"^(auto|#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?|rgba?\(\s*[\d.,\s%]+\))$")
CHOICES = {
    ("shape", "card_style"): {"card", "rule"},
    ("shape", "card_header"): {"rich", "compact", "stacked"},
    ("shape", "avatar_shape"): {"circle", "square", "rounded"},
    ("shape", "short_id"): {"header", "footer"},
    ("shape", "actions_align"): {"left", "right"},
    ("shape", "unread_mark"): {"dot", "star"},
    ("shape", "posts_only"): {"segmented", "check"},
    ("icon", "style"): {"bubble", "terminal"},
}

README = """fedtail themes
==============

Put your own theme here as <name>.toml and set in your profile's config.toml:

    [ui]
    theme = "<name>"

Start from a copy of a file in builtin/ (they are rewritten by every new
version, so don't edit them in place). The easiest theme changes a few lines:

    name = "My green"
    inherit = "terminal"

    [colors]
    text = "#a8ff60"

system.toml in builtin/ lists every key with a comment on what it does.
"""


class ThemeError(Exception):
    pass


def user_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "fedtail" / "themes"


def available():
    names = {p.stem for p in BUILTIN_DIR.glob("*.toml")}
    if user_dir().is_dir():
        names |= {p.stem for p in user_dir().glob("*.toml")}
    return sorted(names)


def _find(name):
    for d in (user_dir(), BUILTIN_DIR):
        p = d / f"{name}.toml"
        if p.is_file():
            return p
    raise ThemeError(f"theme '{name}' not found (have: {', '.join(available())})")


def _read(path):
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ThemeError(f"{path}: {e}") from None


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def reference():
    return _read(BUILTIN_DIR / f"{REFERENCE}.toml")


def load(name):
    """Fully resolved theme dict for `name`, plus warnings. Raises ThemeError."""
    chain, seen, current = [], set(), name
    while current:
        if current in seen or len(chain) > 8:
            raise ThemeError(f"theme '{name}': inherit loop through '{current}'")
        seen.add(current)
        data = _read(_find(current))
        chain.append(data)
        current = data.get("inherit") or ""
    ref = reference()
    merged = copy.deepcopy(ref)
    for data in reversed(chain):
        merged = _merge(merged, data)
    merged["id"] = name
    return merged, validate(merged, ref)


def validate(theme, ref):
    """Raise on wrong values; return warnings for unknown keys."""
    warnings, errors = [], []
    for section, values in theme.items():
        if section in ("name", "inherit", "id"):
            continue
        if section not in ref or not isinstance(ref[section], dict):
            warnings.append(f"unknown section [{section}]")
            continue
        for key, val in values.items():
            if key not in ref[section]:
                warnings.append(f"unknown key {section}.{key}")
                continue
            want = ref[section][key]
            if section == "colors" or (section == "icon" and key != "style"):
                if not isinstance(val, str) or not _COLOR.match(val.strip()):
                    errors.append(f"colors.{key} = {val!r}: use \"#rrggbb\" or \"auto\"")
            elif isinstance(want, bool) or isinstance(val, bool):
                if type(val) is not type(want):
                    errors.append(f"{section}.{key} must be true/false")
            elif isinstance(want, (int, float)):
                if not isinstance(val, (int, float)) or val < 0:
                    errors.append(f"{section}.{key} must be a number ≥ 0")
            elif not isinstance(val, str):
                errors.append(f"{section}.{key} must be text")
            choices = CHOICES.get((section, key))
            if choices and val not in choices:
                errors.append(f"{section}.{key} = {val!r}; allowed: {', '.join(sorted(choices))}")
    if errors:
        raise ThemeError("\n".join(errors))
    return warnings


def install_copies():
    """Keep ~/.config/fedtail/themes/builtin/ and the README current. Best effort."""
    try:
        target = user_dir() / "builtin"
        target.mkdir(parents=True, exist_ok=True)
        for p in BUILTIN_DIR.glob("*.toml"):
            dst = target / p.name
            text = p.read_text("utf-8")
            if not dst.exists() or dst.read_text("utf-8") != text:
                dst.write_text(text, "utf-8")
        readme = user_dir() / "README.txt"
        if not readme.exists() or readme.read_text("utf-8") != README:
            readme.write_text(README, "utf-8")
    except OSError:
        pass
