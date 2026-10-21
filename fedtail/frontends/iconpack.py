"""Picture packs: fedtail's own button pictures (ui.additional_icons), a set a folder.
Plain Python (no Qt, no GTK): which file a picture comes from and, for an SVG, its
colours filled in — the frontends only draw what this gives them.

A pack is a folder with pack.toml and a file a picture, named as the button it is for
(NAMES): reply.svg or reply.png. pack.toml says

    name = "My pack"          # shown in the docs and the warnings
    about = "…"
    inherit = "gloss"         # whose pictures stand in for those this one has not
    style = "gloss"           # how an SVG's blank colours are filled (STYLES); the
                              # first pack in the chain that says one decides
    [colors]                  # a picture of its own colour whatever the theme
    send = "#3aa63a"          # (the rest take the theme's accent); the nearer pack wins

An SVG may leave its colours blank: {c} the colour, {l} its light top (for a gloss),
{d} the outline. A PNG is shown as it is (reply@2x.png beside it for a sharp screen).

Built-in packs: data/icons/packs/ (gloss — the base; qip, agent, flat — gloss's pictures
drawn their way; psi — Psi+'s own PNGs). Your own: ~/.config/fedtail/icons/<name>/,
winning over a built-in one of the same name; a copy of the built-in ones is kept in
~/.config/fedtail/icons/builtin/ to start from. A theme picks its pack with
shape.icon_set; a theme's own folder, themes/<theme>/icons/, is a pack over it (a
pack.toml there is optional — without one it inherits the theme's icon_set).
"""

from __future__ import annotations

import functools
import logging
import re
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .palette import Color

log = logging.getLogger(__name__)

BUILTIN_DIR = Path(__file__).resolve().parent.parent / "data" / "icons" / "packs"
BASE = "gloss"  # every chain ends here: no button without a picture
STYLES = ("gloss", "agent", "flat", "qip", "none")
EXTS = (".svg", ".png")

# every picture fedtail asks a pack for, and what it is on
NAMES = {
    "reply": "Reply under a post",
    "star": "Favourite under a post",
    "star_full": "Favourite, done",
    "boost": "Boost under a post",
    "thread": "Thread under a post; a followed thread in the roster",
    "bookmark": "Bookmark under a post",
    "public": "who sees a post: everyone",
    "unlisted": "who sees a post: quietly public",
    "private": "who sees a post: followers",
    "direct": "who sees a post: the mentioned only",
    "warning": "the content warning button (CW)",
    "attach": "add pictures or a file",
    "poll": "add a poll",
    "emoji": "emoji",
    "send": "Send",
    "follow": "Follow",
    "unfollow": "Unfollow",
    "list": "add to a list",
    "talk": "a private talk; write privately",
    "profile": "open the profile",
    "accounts": "the accounts button",
    "menu": "the ≡ menu",
    "settings": "how the roster looks (⚙)",
    "expand": "make bigger",
    "status": "a person in the roster (QIP's flower, the Agent's @, Psi's star)",
    "nobody": "a face for nobody: no one under the pointer, no picture yet",
}

README = """fedtail picture packs
=====================

The pictures on fedtail's buttons (ui.additional_icons: in the split layout, or
everywhere) come from a pack: a folder with pack.toml and a file a picture.
A theme picks its pack with

    [shape]
    icon_set = "<pack>"

Make your own: copy a folder from builtin/ next to it under a new name, change
pack.toml's name, draw over the pictures you want different and delete the rest —
those come from the pack it inherits. builtin/ is rewritten by every new version,
so don't edit it in place.

A picture is <name>.svg or <name>.png (and <name>@2x.png for a sharp screen):
{names}

An SVG may leave its colours blank: {{c}} the colour, {{l}} its light top, {{d}} the
outline — the pack's style fills them from the theme's accent, or from [colors]
in pack.toml. A PNG is shown as it is.

A single theme can carry its own pictures too: themes/<theme>/icons/<name>.svg,
over the pack its icon_set names.
"""


class PackError(Exception):
    pass


def user_dir():
    from .themefile import user_dir as themes_dir
    return themes_dir().parent / "icons"


def _pack_dir(name):
    """The folder of a pack by name: yours first, then the built-in one."""
    if not name or "/" in name or name.startswith(".") or name == "builtin":
        return None
    for root in (user_dir(), BUILTIN_DIR):
        d = root / name
        if (d / "pack.toml").is_file():
            return d
    return None


def available():
    """The packs' names, yours and the built-in ones."""
    names = set()
    for root in (BUILTIN_DIR, user_dir()):
        if root.is_dir():
            names |= {d.name for d in root.iterdir()
                      if d.name != "builtin" and (d / "pack.toml").is_file()}
    return sorted(names)


def exists(name):
    return _pack_dir(name) is not None


def _read(d):
    p = d / "pack.toml"
    if not p.is_file():
        return {}
    try:
        with open(p, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise PackError(f"{p}: {e}") from None
    return data if isinstance(data, dict) else {}


@dataclass
class Pack:
    """A pack and all it inherits: where to look (the nearest first), its style, the
    pictures' own colours."""
    name: str
    title: str = ""
    about: str = ""
    dirs: list = field(default_factory=list)
    style: str = "gloss"
    colors: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    def find(self, picture, exts=EXTS):
        """The file of a picture (the nearest pack that has it), or None."""
        for d in self.dirs:
            for ext in exts:
                p = d / f"{picture}{ext}"
                if p.is_file():
                    return p
        return None

    @property
    def key(self):
        return (self.name, tuple(str(d) for d in self.dirs), self.style)


@functools.lru_cache(maxsize=32)
def load(name, own=()):
    """The pack `name` (a theme's shape.icon_set) with `own` — a theme's own folders of
    pictures — over it. An unknown or broken pack: gloss, and a warning saying so."""
    warnings = []
    chain = []  # (folder, its pack.toml) the nearest first
    for d in own:
        d = Path(d)
        try:
            data = _read(d)
        except PackError as e:
            warnings.append(str(e))
            data = {}
        chain.append((d, data))
        if data.get("inherit"):
            name = data["inherit"]
    if not exists(name):
        if name:
            warnings.append(f"picture pack '{name}' not found (have: "
                            f"{', '.join(available())}) — using '{BASE}'")
        name = BASE
    seen, current = set(), name
    while current:
        if current in seen or len(chain) > 12:
            warnings.append(f"picture pack '{name}': inherit loop through '{current}'")
            break
        seen.add(current)
        d = _pack_dir(current)
        if d is None:
            warnings.append(f"picture pack '{current}' (inherited) not found")
            break
        try:
            data = _read(d)
        except PackError as e:
            warnings.append(str(e))
            data = {}
        chain.append((d, data))
        current = data.get("inherit") or ("" if current == BASE else BASE)
    if all(d != _pack_dir(BASE) for d, _data in chain) and _pack_dir(BASE):
        chain.append((_pack_dir(BASE), _read(_pack_dir(BASE))))  # never without pictures
    style, colors = None, {}
    for _d, data in reversed(chain):  # the base first: the nearer ones win
        got = data.get("colors")
        if isinstance(got, dict):
            for k, v in got.items():
                try:
                    Color.parse(str(v))
                    colors[str(k)] = str(v)
                except ValueError:
                    warnings.append(f"picture pack '{name}': colors.{k} = {v!r}: not a colour")
    for _d, data in chain:
        s = data.get("style")
        if s:
            if s in STYLES:
                style = s
                break
            warnings.append(f"picture pack '{name}': style = {s!r}; allowed: "
                            f"{', '.join(STYLES)}")
    top = next((data for d, data in chain if data.get("name")), {})
    for w in warnings:
        log.warning("%s", w)
    return Pack(name=name, title=str(top.get("name") or name), about=str(top.get("about", "")),
                dirs=[d for d, _data in chain], style=style or "gloss", colors=colors,
                warnings=warnings)


def for_theme(theme):
    """The pack a theme (Qt's or GTK's: .shape, .icon_dirs) draws with."""
    return load(str(theme.shape.get("icon_set") or BASE),
                tuple(str(d) for d in getattr(theme, "icon_dirs", ()) or ()))


# ---- colouring an SVG -------------------------------------------------------------------
_SHINE = re.compile(r'<ellipse[^>]*opacity="\.35"/>')
_WIDTH = re.compile(r'stroke-width="([\d.]+)"')


def styled(text, style, base):
    """An SVG's blanks filled: {c} base, {l} its light top, {d} the outline — the way
    `style` draws (gloss: a gradient and a shine; agent: a brighter shine, a softer
    outline; flat: plain colour, no shine; qip: a strong shine, a thick dark outline;
    none: the blanks filled, nothing else touched)."""
    base = base if isinstance(base, Color) else Color.parse(str(base))
    light = base.lighter(165)
    if style == "qip":
        text = text.replace('opacity=".35"', 'opacity=".55"')
        text = _WIDTH.sub(lambda m: f'stroke-width="{float(m.group(1)) * 1.35:.2f}"', text)
        light, dark = base.lighter(150), base.darker(300)
    elif style == "flat":
        text = _SHINE.sub("", text).replace('fill="url(#g)"', 'fill="{c}"')
        dark = base.darker(140)
    elif style == "agent":
        text = text.replace('opacity=".35"', 'opacity=".6"')
        dark = base.darker(135)
    else:  # gloss, none
        dark = base.darker(170)
    return text.replace("{c}", base.name()).replace("{l}", light.name()) \
        .replace("{d}", dark.name())


@dataclass(frozen=True)
class Picture:
    kind: str           # "svg" (text: ready to draw) or "png" (path, path2x)
    text: str = ""
    path: str = ""
    path2x: str = ""


@functools.lru_cache(maxsize=512)
def _picture(pack_key, name, accent, svg_ok):
    pack = _by_key[pack_key]
    exts = EXTS if svg_ok else (".png",)
    p = pack.find(name, exts)
    if p is None:
        return None
    if p.suffix == ".png":
        two = p.with_name(p.stem + "@2x.png")
        return Picture("png", path=str(p), path2x=str(two) if two.is_file() else "")
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        log.debug("picture %s: %s", p, e)
        return None
    return Picture("svg", text=styled(text, pack.style, pack.colors.get(name) or accent))


_by_key = {}


def picture(pack, name, accent, svg_ok=True):
    """What to draw for a picture: Picture("svg", text) coloured for this pack and
    accent ("#rrggbb"), Picture("png", path); None when the pack (and all it inherits)
    has none. svg_ok=False: a frontend that can't draw SVG — PNGs only."""
    _by_key[pack.key] = pack
    return _picture(pack.key, name, str(accent), bool(svg_ok))


def has_png(pack):
    """Some of the pack's pictures are PNGs (drawable without an SVG renderer)."""
    return any(any(d.glob("*.png")) for d in pack.dirs)


# ---- the copies to start from -------------------------------------------------------------
def install_copies():
    """Keep ~/.config/fedtail/icons/builtin/ and its README current. Best effort."""
    try:
        root = user_dir()
        target = root / "builtin"
        for src in BUILTIN_DIR.iterdir():
            if not src.is_dir():
                continue
            dst = target / src.name
            dst.mkdir(parents=True, exist_ok=True)
            for f in src.iterdir():
                d = dst / f.name
                if f.is_file() and (not d.exists() or d.read_bytes() != f.read_bytes()):
                    shutil.copyfile(f, d)
        names = "\n".join(f"    {k:<10} {v}" for k, v in NAMES.items())
        text = README.format(names=names)
        readme = root / "README.txt"
        if not readme.exists() or readme.read_text("utf-8") != text:
            readme.write_text(text, "utf-8")
    except OSError:
        pass
