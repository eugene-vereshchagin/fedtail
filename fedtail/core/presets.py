"""The sets of lanes (lanes.preset) and the words of their lanes: data of the config, never
of the code. They are written out in config.toml — `[[lanes.sets.<set>]]` a lane each,
`[lanes.words.<lane>]` (title, tip, icon, marks), `[lanes.sections.<section>]`,
`[lanes.renamed]` — and the reference config (fedtail/data/config.example.en.toml) is where
they come from for a config written before, or one that left them out: a set the file
writes takes the reference's of that name, whole; one it adds is a set of its own.

The sets at work are a config's (`use`, as a core starts): what a function here answers
without a config given is that config's, or the reference's when none was."""

import copy
import functools
import tomllib
from importlib import resources

DEFAULT = "fedtail"
EXTRA = "extra"  # lanes no set shows, any config may turn on
OLD_NAMES = {"own": DEFAULT}  # before every lane was a rule: "own" was your [lanes] as it was
# the tables of [lanes] that are the sets and their words (not options)
TABLES = ("sets", "words", "sections", "renamed", "about", "switches")
_active = None  # the tables of the config at work (use)


@functools.cache
def reference():
    """{"sets": {set: [lanes]}, "words": …, "sections": …, "renamed": …} as the
    reference config has them."""
    text = resources.files("fedtail").joinpath("data", "config.example.en.toml") \
        .read_text("utf-8")
    lanes = tomllib.loads(text).get("lanes") or {}
    return {k: lanes.get(k) or {} for k in TABLES}


def merged(own):
    """The reference's tables with a config's own over them (own: {"sets": …, …} as its
    file wrote them, any missing): a set of the file whole in the place of the
    reference's of that name, or beside them; a lane's words key by key; the sections —
    the file's, when it has any (their order is theirs); old names added."""
    ref = copy.deepcopy(reference())
    own = own or {}
    out = {"sets": {**ref["sets"], **(own.get("sets") or {})},
           "words": {n: dict(w) for n, w in ref["words"].items()},
           "sections": own.get("sections") or ref["sections"],
           "renamed": {**ref["renamed"], **(own.get("renamed") or {})},
           "about": {**ref["about"], **(own.get("about") or {})},
           "switches": {**ref["switches"], **(own.get("switches") or {})}}
    for name, words in (own.get("words") or {}).items():
        if isinstance(words, dict):
            out["words"][name] = {**out["words"].get(name, {}), **words}
    return out


def problems(own):
    """What is wrong with the tables a config wrote ([] — nothing): each a line to say."""
    out = []
    sets = (own or {}).get("sets")
    if sets is not None and not isinstance(sets, dict):
        return ["lanes.sets: tables [[lanes.sets.<name>]], a lane each"]
    for name, tables in (sets or {}).items():
        if not isinstance(tables, list) or not all(isinstance(t, dict) for t in tables):
            out.append(f"lanes.sets.{name}: tables [[lanes.sets.{name}]], a lane each")
        elif name in TABLES:
            out.append(f"lanes.sets.{name}: a set can't be called {name}")
    for key in ("words", "sections", "renamed", "about", "switches"):
        got = (own or {}).get(key)
        if got is not None and not isinstance(got, dict):
            out.append(f"lanes.{key}: tables [lanes.{key}.<name>]")
    return out


def use(cfg=None):
    """The sets at work from here on: this config's (None — the reference's)."""
    global _active
    _active = _of(cfg) if cfg is not None else None


def _of(cfg):
    lanes = cfg.get("lanes") if isinstance(cfg, dict) else None
    if isinstance(lanes, dict) and isinstance(lanes.get("sets"), dict):
        return {k: lanes.get(k) or {} for k in TABLES}
    return None


def _all(cfg=None):
    """The tables to answer from: this config's, else those at work, else the reference's."""
    return (_of(cfg) if cfg is not None else None) or _active or reference()


def _sets(cfg=None):
    return _all(cfg)["sets"]


def names(cfg=None):
    """The sets one can choose (not "extra")."""
    return [n for n in _sets(cfg) if n != EXTRA]


def lanes_of(name, cfg=None):
    """The lanes (tables) of a set, in its order — a copy, safe to change."""
    name = OLD_NAMES.get(name, name)
    sets = _sets(cfg)
    return copy.deepcopy(sets.get(name) or sets.get(DEFAULT) or [])


def extra(cfg=None):
    return copy.deepcopy(_sets(cfg).get(EXTRA) or [])


def known_names(cfg=None):
    """Every lane name some set (or "extra") has."""
    return frozenset(t["name"] for tables in _sets(cfg).values() for t in tables
                     if isinstance(t, dict) and t.get("name"))


def words(name, cfg=None):
    """What the config says of a lane by its name — {"title": …, "tip": …, "icon": …,
    "marks": …}, any of them missing ([lanes.words.<name>]) — for the lanes of every set,
    and one's own lane of that name that says none of its own."""
    got = _all(cfg)["words"].get(name)
    return dict(got) if isinstance(got, dict) else {}


def about(name, cfg=None, lang=None):
    """What a set is, in a line ([lanes.about]); "" — nothing said (a set of one's own)."""
    return in_language(_all(cfg)["about"].get(name), lang)


def switch_words(name, lang=None):
    """(title, tip) of a quick filter named by its key (a condition's switch = "@<key>"):
    the config's words for it ([lanes.switches.<key>]); no such table — the key itself."""
    got = _all()["switches"].get(name)
    got = got if isinstance(got, dict) else {}
    return in_language(got.get("title"), lang) or name, in_language(got.get("tip"), lang)


def shipped():
    """The sets fedtail comes with (the reference config's), "extra" too."""
    return list(reference()["sets"])


def renamed(cfg=None):
    """{old name: the name now} — the lanes once named otherwise ([lanes.renamed])."""
    return dict(_all(cfg)["renamed"])


def sections(cfg=None):
    """The sidebar's sections the config has, top to bottom."""
    return [n for n, t in _all(cfg)["sections"].items() if isinstance(t, dict)]


def section_title(name, lang=None):
    """What the config calls a section ("" — it has no such section)."""
    return in_language((_all()["sections"].get(name) or {}).get("title"), lang)


def own_section():
    """The section of a lane that names none: the one with `own = true`, else the first."""
    got = _all()["sections"]
    return next((n for n, t in got.items() if isinstance(t, dict) and t.get("own")),
                next(iter(got), ""))


def icons():
    """Every picture the sets' lanes wear: their words' and their tables' own `icon`."""
    got = {w.get("icon") for w in _all()["words"].values() if isinstance(w, dict)}
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
