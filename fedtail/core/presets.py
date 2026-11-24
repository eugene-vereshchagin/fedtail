"""The sets of lanes fedtail comes with (lanes.preset): fedtail/data/presets.toml, one file,
every lane in it a rule (core/custom.py builds lanes of them). Nothing here but reading it."""

import copy
import functools
import tomllib
from importlib import resources

DEFAULT = "fedtail"
EXTRA = "extra"  # lanes no set shows, any config may turn on
OLD_NAMES = {"own": DEFAULT}  # before every lane was a rule: "own" was your [lanes] as it was


@functools.cache
def _all():
    text = resources.files("fedtail").joinpath("data", "presets.toml").read_text("utf-8")
    return tomllib.loads(text)


WORDS = "words"  # not a set: the lanes' words by name (title, tip, icon)


def _sets():
    """{set: [its lanes' tables]} — every table of the file that is a list of lanes."""
    return {k: v for k, v in _all().items() if isinstance(v, list)}


def names():
    """The sets one can choose (not "extra")."""
    return [n for n in _sets() if n != EXTRA]


def lanes_of(name):
    """The lanes (tables) of a set, in its order — a copy, safe to change."""
    name = OLD_NAMES.get(name, name)
    return copy.deepcopy(_sets().get(name) or _sets()[DEFAULT])


def extra():
    return copy.deepcopy(_sets().get(EXTRA) or [])


@functools.cache
def known_names():
    """Every lane name some set (or "extra") has."""
    return frozenset(t["name"] for tables in _sets().values() for t in tables if t.get("name"))


def words(name):
    """What the file says of a lane by its name — {"title": …, "tip": …, "icon": …}, any
    of them missing ([words.<name>]) — for the lanes of every set, and one's own lane of
    that name that says none of its own."""
    got = (_all().get(WORDS) or {}).get(name)
    return dict(got) if isinstance(got, dict) else {}


SECTIONS = "sections"  # not a set: the sidebar's sections, in order


def sections():
    """The sidebar's sections the file has, top to bottom."""
    return [n for n, t in (_all().get(SECTIONS) or {}).items() if isinstance(t, dict)]


def section_title(name, lang=None):
    """What the file calls a section ("" — it has no such section)."""
    return in_language(((_all().get(SECTIONS) or {}).get(name) or {}).get("title"), lang)


def own_section():
    """The section of a lane that names none: the file's `own = true`, else its first."""
    got = _all().get(SECTIONS) or {}
    return next((n for n, t in got.items() if isinstance(t, dict) and t.get("own")),
                next(iter(got), ""))


@functools.cache
def icons():
    """Every picture the sets' lanes wear: their words' and their tables' own `icon`."""
    got = {w.get("icon") for w in (_all().get(WORDS) or {}).values() if isinstance(w, dict)}
    got |= {t.get("icon") for tables in _sets().values() for t in tables}
    return frozenset(i for i in got if isinstance(i, str) and i)


def in_language(said, lang=None):
    """A word written per language ({ ru = …, en = … }) in the interface's (lang), else
    English, else the first; a plain string as it is; nothing — ""."""
    if isinstance(said, dict):
        if lang is None:
            from ..i18n import current_language
            lang = current_language()
        said = said.get(lang) or said.get("en") or next(iter(said.values()), "")
    return said if isinstance(said, str) else ""


def title(name, lang=None):
    """A lane's title by its name alone: the file's word for it, else the name itself —
    for where no core is at hand (a settings list, a note); a lane's own title is the
    core's to say (Core.lane_title)."""
    return in_language(words(name).get("title"), lang) or name


def tip(name, lang=None):
    """What a lane of this name is, in a line ("" — the file says nothing)."""
    return in_language(words(name).get("tip"), lang)
