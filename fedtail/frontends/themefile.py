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
    ("shape", "card_header"): {"rich", "compact", "stacked", "chat"},
    ("shape", "avatar_shape"): {"circle", "square", "rounded"},
    ("shape", "short_id"): {"header", "footer"},
    ("shape", "actions_align"): {"left", "right"},
    ("shape", "rule"): {"dashed", "solid"},
    ("shape", "unread_mark"): {"dot", "star"},
    ("shape", "posts_only"): {"segmented", "check"},
    ("icon", "style"): {"bubble", "terminal"},
    ("shape", "faces"): {"qip", "agent", "none"},
    ("shape", "roster_rows"): {"lines", "faces"},
    ("shape", "tab_rows"): {"wrap", "one"},
    ("shape", "icons"): {"desktop", "own", "words"},
    ("pictures", "style"): {"gloss", "agent", "flat", "qip", "none"},
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

A theme can bring its own fonts: put the files next to it and name them in
[font] files = ["fonts/MyFont.ttf"], then family = "My Font". Fonts for every
theme go to ~/.config/fedtail/fonts/; ui.font in config.toml picks one over
the theme's.

The pictures on the buttons are the theme's: [shape] icons = "own" takes them from a
folder named as the theme, with icons/ in it, next to its file — themes/mine.toml →
themes/mine/icons/reply.svg (or .png), a file a picture; "desktop" takes the desktop's
icons, "words" has none. What your folder lacks comes from the theme you inherit (a
copy of each built-in theme's set is in builtin/<theme>/icons/ to start from), then
from [pictures] from = "<theme>", then from fedtail's fallback set — and the log says
which. An SVG may leave its colours blank: {c} the colour, {l} its light top, {d} the
outline; [pictures] style and colors fill them. The names of the pictures, and what
each is for: builtin/PICTURES.txt.

fedtail reads your themes right here, nothing is copied anywhere; builtin/ is only
a sample, rewritten at every start. To keep your themes in git, make this folder a
working copy of your repository and put builtin/ into its .gitignore.
"""


PICTURES = """The pictures a theme's set has (themes/<theme>/icons/<name>.svg or .png)
=====================================================================

Standard — always there when the theme has pictures at all ([shape] icons = "own"):
{standard}

Extended — the messengers': in the split layout, and anywhere with ui.icons = "additional":
{extended}

A picture the set lacks comes from the theme it inherits, then from [pictures] from,
then from fedtail's fallback set (the log says which). An SVG may leave its colours
blank: {{c}} the colour, {{l}} its light top, {{d}} the outline.
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


# a theme of an earlier version: [shape] icons = true / false (the desktop's or words),
# lane_icons (gone: a theme's pictures are all or none), icon_set (the pack's look: now
# [pictures] style)
_OLD_SET = {"gloss": "gloss", "qip": "qip", "agent": "agent", "flat": "flat", "psi": "flat"}


def _legacy(data):
    shape = data.get("shape")
    if not isinstance(shape, dict):
        return data
    if isinstance(shape.get("icons"), bool):
        shape["icons"] = "desktop" if shape["icons"] else "words"
    shape.pop("lane_icons", None)
    old = shape.pop("icon_set", None)
    if old in _OLD_SET:
        pics = data.setdefault("pictures", {})
        if isinstance(pics, dict):
            pics.setdefault("style", _OLD_SET[old])
    return data


def icon_dirs(chain):
    """Where a theme's own button pictures lie: a folder named as the theme, with
    icons/ in it, next to its file (themes/mine.toml → themes/mine/icons/reply.svg or
    .png) — the theme's own first, then those of the themes it inherits. A picture not
    there comes from [pictures] from, then from the fallback set (frontends/iconpack.py)."""
    out = []
    for path, _data in chain:
        d = path.parent / path.stem / "icons"
        if d.is_dir():
            out.append(str(d))
    return out


def load(name, _depth=0):
    """Fully resolved theme dict for `name`, plus warnings. Raises ThemeError."""
    chain, seen, current = [], set(), name
    while current:
        if current in seen or len(chain) > 8:
            raise ThemeError(f"theme '{name}': inherit loop through '{current}'")
        seen.add(current)
        path = _find(current)
        data = _legacy(_read(path))
        chain.append((path, data))
        current = data.get("inherit") or ""
    ref = reference()
    merged = copy.deepcopy(ref)
    files = []
    for path, data in reversed(chain):
        merged = _merge(merged, data)
        got = (data.get("font") or {}).get("files")
        if isinstance(got, list):  # each theme's fonts lie next to its own file
            for f in got:
                if not isinstance(f, str):
                    continue
                own = path.parent / f
                # a copy of a built-in theme moved into themes/: its fonts stay built in
                files.append(str(own if own.exists() or not (BUILTIN_DIR / f).exists()
                                 else BUILTIN_DIR / f))
    warnings = validate(merged, ref)
    merged["id"] = name
    merged["font"]["files"] = files
    merged["icon_dirs"] = icon_dirs(chain)
    # [pictures] from: a theme whose set this one borrows (and what that one borrows)
    borrowed = (merged.get("pictures") or {}).get("from") or ""
    if borrowed and _depth < 4:
        try:
            other, _w = load(borrowed, _depth + 1)
            merged["icon_dirs"] += [d for d in other["icon_dirs"]
                                    if d not in merged["icon_dirs"]]
        except ThemeError as e:
            warnings.append(f"pictures.from = {borrowed!r}: {e}")
    return merged, warnings


def fonts_dir():
    """Fonts of my own, used without installing them: ~/.config/fedtail/fonts/."""
    return user_dir().parent / "fonts"


FONT_EXT = {".ttf", ".otf", ".ttc"}


def builtin_fonts():
    """Every font that comes with fedtail (the built-in themes'), by file."""
    d = BUILTIN_DIR / "fonts"
    return sorted(str(p) for p in d.glob("*") if p.suffix.lower() in FONT_EXT) \
        if d.is_dir() else []


def font_files(theme_files=()):
    """The font files to load: the theme's own (those that exist), then the fonts folder."""
    out = [f for f in theme_files if Path(f).is_file()]
    d = fonts_dir()
    if d.is_dir():
        out += sorted(str(p) for p in d.rglob("*") if p.suffix.lower() in FONT_EXT)
    return out


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
            if section == "pictures" and key == "colors":
                if not isinstance(val, dict):
                    errors.append("pictures.colors must be a table: name = \"#rrggbb\"")
                    continue
                for k, v in val.items():
                    if not isinstance(v, str) or not _COLOR.match(v.strip()):
                        errors.append(f"pictures.colors.{k} = {v!r}: use \"#rrggbb\"")
                continue
            if section == "colors" or (section == "icon" and key != "style"):
                if not isinstance(val, str) or not _COLOR.match(val.strip()):
                    errors.append(f"colors.{key} = {val!r}: use \"#rrggbb\" or \"auto\"")
            elif isinstance(want, list):
                if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
                    errors.append(f"{section}.{key} must be a list of text")
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


_INSTALLED = []


def _copy_if_changed(src, dst):
    """dst made a copy of src unless it is one already (by size and time: reading every
    picture of every theme at each start and each theme tried took a tenth of a second)."""
    s = src.stat()
    try:
        d = dst.stat()
        if d.st_size == s.st_size and d.st_mtime >= s.st_mtime:
            return
    except OSError:
        pass
    dst.write_bytes(src.read_bytes())


def install_copies():
    """Keep ~/.config/fedtail/themes/builtin/ and the README current — once a run. Best
    effort."""
    where = str(user_dir())
    if where in _INSTALLED:
        return
    _INSTALLED.append(where)
    try:
        target = user_dir() / "builtin"
        target.mkdir(parents=True, exist_ok=True)
        for p in BUILTIN_DIR.glob("*.toml"):
            dst = target / p.name
            text = p.read_text("utf-8")
            if not dst.exists() or dst.read_text("utf-8") != text:
                dst.write_text(text, "utf-8")
            icons = BUILTIN_DIR / p.stem / "icons"  # its pictures, to start from too
            if icons.is_dir():
                (target / p.stem / "icons").mkdir(parents=True, exist_ok=True)
                for f in icons.iterdir():
                    if f.is_file():
                        _copy_if_changed(f, target / p.stem / "icons" / f.name)
        from . import iconpack
        names = PICTURES.format(
            standard="\n".join(f"    {k:<10} {v}" for k, v in iconpack.STANDARD.items()),
            extended="\n".join(f"    {k:<10} {v}" for k, v in iconpack.EXTENDED.items()))
        listing = target / "PICTURES.txt"
        if not listing.exists() or listing.read_text("utf-8") != names:
            listing.write_text(names, "utf-8")
        readme = user_dir() / "README.txt"
        if not readme.exists() or readme.read_text("utf-8") != README:
            readme.write_text(README, "utf-8")
    except OSError:
        pass
