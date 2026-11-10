"""A theme as one file: a zip to take a theme off a device and to bring one onto it.

The phone keeps its themes where no file manager reaches (the app's own folder), so a
theme travels as an archive: ``pack()`` puts a theme into one — its ``.toml``, its folder
(``icons/``, ``sounds/``), the fonts it names, and the themes of the user's own it needs
(``inherit``, ``[pictures] from``, ``[sound] from``; the built-in ones are everywhere) —
with the manual (README.ru.md, README.en.md: how to change it, rename it, bring it back).
``unpack()`` takes one into the themes folder, carefully: names only inside the folder,
only the kinds of files a theme has, a size limit, and a theme of the same name kept
unless the caller says to replace it.

The archive is laid out as the themes folder is (``mine.toml``, ``mine/icons/…``,
``fonts/…``), so unpacked by hand into ``~/.config/fedtail/themes/`` it works as well.
No toolkit here: every interface (the windows, the phone, the command line) calls these.
"""

import re
import shutil
import tempfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

from . import themefile

# what a theme's archive may hold, by kind: the theme, its pictures, sounds and fonts, a
# manual; anything else is left out (said in the answer), never written
KINDS = {".toml", ".svg", ".png", ".wav", ".ogg", ".oga", ".opus", ".mp3", ".flac",
         ".ttf", ".otf", ".ttc"}
MANUALS = {"README.ru.md", "README.en.md", "README.md", "README.txt"}
MAX_FILES = 2000
MAX_BYTES = 64 * 1024 * 1024  # unpacked, all of it (a theme with fonts: a few MB)
NAME = re.compile(r"^[\w][\w.+-]{0,63}$")  # a theme's name: its file's name, no path
INCLUDE = re.compile(r"<!-- include: parts/theme-files[^>]*-->\n(.*?)<!-- /include -->", re.S)
HELP_DIR = Path(__file__).resolve().parent.parent / "data" / "help"


class PackError(Exception):
    """A theme that can't be packed, an archive that can't be taken: the words say why."""


def manual(lang):
    """The manual that goes into an archive: the in-app help's "A theme as a file"
    (docs/<lang>/parts/theme-files.md, put into look.md by tools/docs_build.py)."""
    try:
        text = (HELP_DIR / lang / "look.md").read_text("utf-8")
    except OSError:
        return ""
    m = INCLUDE.search(text)
    return m.group(1).strip() + "\n" if m else ""


def _builtin(path):
    return Path(path).resolve().parent == themefile.BUILTIN_DIR.resolve()


def _needs(name, seen):
    """The theme `name` and the user's own themes it needs, as [(name, path, data)]."""
    if name in seen or len(seen) > 16:
        return []
    seen.add(name)
    try:
        path = themefile._find(name)
    except themefile.ThemeError as e:
        raise PackError(str(e)) from None
    data = themefile._read(path)
    out = [(name, path, data)]
    for other in (data.get("inherit"), (data.get("pictures") or {}).get("from"),
                  (data.get("sound") or {}).get("from")):
        if isinstance(other, str) and other:
            try:
                p = themefile._find(other)
            except themefile.ThemeError:
                continue  # said by the theme's own warnings when it is loaded
            if not _builtin(p):  # a built-in one is on every device
                out += _needs(other, seen)
    return out


def _font_files(path, data):
    """(name in the archive, file) of each font the theme names, found as load() does."""
    out = []
    for f in (data.get("font") or {}).get("files") or ():
        if not isinstance(f, str):
            continue
        rel = PurePosixPath(f.replace("\\", "/"))
        if rel.is_absolute() or ".." in rel.parts:
            continue  # a font outside the themes folder: not the theme's to carry
        own = path.parent / rel
        src = own if own.is_file() else themefile.BUILTIN_DIR / rel
        if src.is_file():
            out.append((str(rel), src))
    return out


def contents(name):
    """{name in the archive: file on disk} for theme `name` — what pack() writes."""
    files = {}
    for _n, path, data in _needs(name, set()):
        files[path.name] = path
        folder = path.parent / path.stem
        for part in ("icons", "sounds"):
            d = folder / part
            if d.is_dir():
                for f in sorted(d.iterdir()):
                    if f.is_file() and f.suffix.lower() in KINDS:
                        files[f"{path.stem}/{part}/{f.name}"] = f
        for arc, src in _font_files(path, data):
            files[arc] = src
    return files


def pack(name, dest):
    """Theme `name` (the user's or a built-in one) into the zip `dest`, the manual in
    it. Returns the archive's names."""
    files = contents(name)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for lang in ("ru", "en"):
            text = manual(lang)
            if text:
                z.writestr(f"README.{lang}.md", text)
        for arc, src in sorted(files.items()):
            z.write(src, arc)
    return sorted(files)


def _members(z):
    """The archive's files as (zip info, safe relative path); the folder an archive
    zipped "with its folder" holds everything in is taken off."""
    infos = [i for i in z.infolist() if not i.is_dir()]
    if len(infos) > MAX_FILES:
        raise PackError(f"{len(infos)} files: more than a theme has ({MAX_FILES} at most)")
    if sum(i.file_size for i in infos) > MAX_BYTES:
        raise PackError(f"more than {MAX_BYTES // (1024 * 1024)} MB unpacked")
    paths = []
    for i in infos:
        p = PurePosixPath(i.filename.replace("\\", "/"))
        if p.is_absolute() or ".." in p.parts or not p.parts or \
                (i.external_attr >> 16) & 0o170000 == 0o120000:  # a symlink
            raise PackError(f"{i.filename}: a path out of the themes folder")
        paths.append((i, p))
    tops = {p.parts[0] for _i, p in paths}
    if not any(len(p.parts) == 1 and p.suffix == ".toml" for _i, p in paths) and \
            len(tops) == 1 and all(len(p.parts) > 1 for _i, p in paths):
        paths = [(i, PurePosixPath(*p.parts[1:])) for i, p in paths]
    return paths


def themes_in(path):
    """The names of the themes a zip brings (its top .toml files), without taking it."""
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise PackError(f"not a zip: {e}") from None
    with z:
        return sorted(p.stem for _i, p in _members(z)
                      if len(p.parts) == 1 and p.suffix == ".toml")


def unpack(path, replace=False, target=None):
    """The zip at `path` into the themes folder (`target`, the user's by default).

    Returns {"themes": [names], "skipped": [archive names left out], "warnings": [...]}.
    Raises PackError: not a zip, no theme in it, an unsafe name, too big, a theme not a
    theme (its TOML broken), or one of the same name there and `replace` false (the
    words name it: the interface asks, then calls again with replace=True)."""
    target = Path(target) if target is not None else themefile.user_dir()
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise PackError(f"not a zip: {e}") from None
    with z:
        members = _members(z)
        names = sorted(p.stem for _i, p in members if len(p.parts) == 1 and p.suffix == ".toml")
        if not names:
            raise PackError("no theme in it: a theme is a .toml file at the archive's top")
        bad = [n for n in names if not NAME.match(n)]
        if bad:
            raise PackError(f"not a theme's name: {', '.join(bad)}")
        if not replace:
            have = [n for n in names if (target / f"{n}.toml").exists()]
            if have:
                raise PackError("already there: " + ", ".join(have))
        skipped, warnings = [], []
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for info, p in members:
                if p.name in MANUALS and len(p.parts) == 1:
                    continue  # the manual: read in the archive, not a theme's file
                if p.suffix.lower() not in KINDS:
                    skipped.append(str(p))
                    continue
                out = tmp.joinpath(*p.parts)
                out.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            for n in names:  # a theme, each of them: TOML that reads
                try:
                    with open(tmp / f"{n}.toml", "rb") as f:
                        tomllib.load(f)
                except tomllib.TOMLDecodeError as e:
                    raise PackError(f"{n}.toml: {e}") from None
            target.mkdir(parents=True, exist_ok=True)
            for n in names:  # replaced: the old one's pictures and sounds go with it
                old = target / n
                if replace and old.is_dir() and not old.is_symlink():
                    shutil.rmtree(old)
            for src in sorted(tmp.rglob("*")):
                if src.is_file():
                    dst = target / src.relative_to(tmp)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dst)
    mine = target.resolve() == themefile.user_dir().resolve()
    for n in names if mine else ():  # what it says once there: inherit missing, keys unknown
        try:
            _theme, said = themefile.load(n)
            warnings += [f"{n}: {w}" for w in said]
        except themefile.ThemeError as e:
            warnings.append(f"{n}: {e}")
    return {"themes": names, "skipped": skipped, "warnings": warnings}
