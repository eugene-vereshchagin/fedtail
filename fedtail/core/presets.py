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


def names():
    """The sets one can choose (not "extra")."""
    return [n for n in _all() if n != EXTRA]


def lanes_of(name):
    """The lanes (tables) of a set, in its order — a copy, safe to change."""
    name = OLD_NAMES.get(name, name)
    return copy.deepcopy(_all().get(name) or _all()[DEFAULT])


def extra():
    return copy.deepcopy(_all().get(EXTRA) or [])


@functools.cache
def known_names():
    """Every lane name some set (or "extra") has."""
    return frozenset(t["name"] for tables in _all().values() for t in tables if t.get("name"))
