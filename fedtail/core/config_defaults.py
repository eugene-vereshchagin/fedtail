"""Defaults that changed, brought into the configs written before.

A profile's config.toml is written whole from the reference at the first start: every
option is set there, at the default of that day. So when a later version changes a
default (Drafts on, sync of the lanes on), a config written before keeps the old value,
and nothing tells it from one the person chose: the author's own config kept Drafts off
after 0.23.3 turned them on, and the drafts set aside were nowhere to be found (18.11).

CHANGED lists every such change: (section, key, the old defaults, the version). At a
start, an option still at an old default is set to the new one — that one line, the way
the settings window writes it (config_edit.save: the old file kept as config.toml.bak).
Each change is looked at once per profile (defaults_seen.json beside the config): an
option the person sets back afterwards stays as they set it.

A change of a default in config.DEFAULTS gets its line here, in the same commit.
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger(__name__)

# (section, key, [old defaults], since): the defaults changed since 0.22.4
CHANGED = (
    ("feed", "tag_click", ["author"], "0.22.4"),
    ("sync", "lane_rules", [False], "0.23.1"),
    ("sync", "people", [False], "0.23.1"),
    ("ui", "command_line", [True], "0.23.1"),
    ("post", "drafts_place", [False], "0.23.3"),
    # no default names a lane: "marked" — the lanes whose rules mark themselves (`marks`;
    # the sets' words mark the very lanes these lists named)
    ("ui", "icon_count", [["to_me", "replies", "mentions", "subs", "commented", "important",
                           "requests"]], "0.23.10"),
    ("notify", "lanes", [["direct", "to_me", "replies", "mentions", "subs", "commented",
                          "important", "activity", "requests"]], "0.23.10"),
    ("sound", "lanes", [["direct", "to_me", "replies", "mentions", "subs", "commented",
                         "important", "requests"]], "0.23.10"),
    ("lanes", "languages_in", [["federated", "local", "tags"]], "0.23.10"),
    ("lists", "hide_in", [["home", "bots", "federated", "local"]], "0.23.10"),
)

SEEN = "defaults_seen.json"


def _id(section, key, since):
    return f"{section}.{key}@{since}"


def _seen_path(config_path):
    return os.path.join(os.path.dirname(os.path.realpath(os.fspath(config_path))), SEEN)


def _read_seen(path):
    try:
        with open(path, encoding="utf-8") as f:
            got = json.load(f)
        return set(got) if isinstance(got, list) else set()
    except (OSError, ValueError):
        return set()


def due(user, seen):
    """user: the file's values in the program's sections (config.from_file) →
    [(section, key, new default, id)]: the changes not looked at yet whose option the
    file sets to an old default; and the ids of every change not looked at yet."""
    from .config import DEFAULTS
    out, fresh = [], []
    for section, key, old, since in CHANGED:
        cid = _id(section, key, since)
        if cid in seen:
            continue
        fresh.append(cid)
        have = (user.get(section) or {}) if isinstance(user.get(section), dict) else {}
        if key in have and have[key] in old and DEFAULTS[section][key] not in old:
            out.append((section, key, DEFAULTS[section][key], cid))
    return out, fresh


def bring(config_path, user):
    """At a start: the options still at an old default set to the new one in the file;
    → [(section.key, new value)] brought (logged). The file is left as it is when there
    is nothing to bring; a file that can't be written is left too (logged)."""
    from .config import from_file
    seen_path = _seen_path(config_path)
    seen = _read_seen(seen_path)
    todo, fresh = due(from_file(user)[0], seen)  # the program's sections, not the file's
    if not fresh:
        return []
    brought = []
    if todo:
        from . import config_edit
        try:
            config_edit.save(config_path, {(s, k): v for s, k, v, _c in todo})
            brought = [(f"{s}.{k}", v) for s, k, v, _c in todo]
            log.info("defaults brought to this version: %s",
                     ", ".join(f"{n} = {v!r}" for n, v in brought))
        except Exception as e:  # noqa: BLE001 — a config we can't write: as it is
            log.warning("defaults not brought (%s): %s", ", ".join(
                f"{s}.{k}" for s, k, _v, _c in todo), e)
            return []
    try:
        with open(seen_path, "w", encoding="utf-8") as f:
            json.dump(sorted(seen | set(fresh)), f, indent=0)
    except OSError as e:
        log.warning("%s: %s", seen_path, e)
    return brought
