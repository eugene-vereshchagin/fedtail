"""The lane editor, without a toolkit: the lanes as config.toml and the chosen set make
them (lanes.preset, lanes.enabled, [[lanes.custom]]), and the changes to them — the order,
shown or not, a lane's title, picture, sources and conditions — written back into the
file at once (core/config_edit.py) and taken by the running program (Core.lanes_saved).
common/lanesplace.py draws it as a place, so every interface has it.

    ed = Editor.load(view)                  # the lanes as the file has them now
    ed.move("bots", -1); ed.toggle("local")
    ed.put("pics", {"name": "pics", "any": [{"has": "image"}]})
    ed.save(view)                           # → the words to show ("Saved: …")

A condition is typed as one line, the keys with their words:

    author: me, followed; kind: post            (a comma: any of them)
    text: grúzia + tbilisi, georgia             (a "+": all of them in one group)

A set's lane changed here becomes one's own ([[lanes.custom]] of its name, in its
place); "Back to the set's" takes that away again.
"""

from __future__ import annotations

import copy
import tomllib

from ...core import atoms, config, config_edit, custom, presets
from ...i18n import _, current_language
from . import settings

# the kinds of lanes that aren't rules: the editor moves them, nothing more
NOT_RULES = custom.KINDS | {"lists", "tags"}
SOURCES = tuple(sorted(custom.FEEDS))
GROUPS = ("personal", "standard")
READS = ("through", "browse")
SORTS = ("arrival", "post_time", "replies", "likes", "boosts", "density")
FILTER_CONTEXTS = ("home", "public", "notifications", "thread", "account")
# the keys a condition's line may have, with the words each takes (None: anything)
KEYS = {k: (sorted(v) if v else None) for k, v in atoms._SET_KEYS.items()} | \
    {k: None for k in atoms._COUNT_KEYS} | \
    {"age": None, "age_of": ["post", "original"], "text": None,
     "text_in": sorted(atoms.TEXT_IN), "text_case": ["true", "false"],
     "text_regex": ["true", "false"], "apart": None, "until": None}
_BOOLS = {"text_case", "text_regex"}
_INTS = {"priority"}
_OWN_FIELDS = ("switch", "shown")  # a condition's fields of their own, not in its line
EVERYTHING = "*"  # the line of a condition that asks nothing (`{}`): every post


def cond_line(cond):
    """A condition (a table) as one line to type — without switch / shown (fields of
    their own)."""
    parts = []
    for k, v in cond.items():
        if k in _OWN_FIELDS:
            continue
        if k == "any" and isinstance(v, (list, tuple)):
            words = " ".join(f"[{cond_line(t)}]" for t in v if isinstance(t, dict))
        elif k == "text":
            groups = [[v]] if isinstance(v, str) else [[g] if isinstance(g, str) else g
                                                        for g in v]
            words = ", ".join(" + ".join(map(str, g)) for g in groups)
        elif isinstance(v, bool):
            words = "true" if v else "false"
        elif isinstance(v, (list, tuple)):
            words = ", ".join(map(str, v))
        else:
            words = str(v)
        parts.append(f"{k}: {words}")
    return "; ".join(parts) or EVERYTHING


def parse_line(line):
    """A typed line → a condition (a table). ValueError with what is wrong."""
    out = {}
    if str(line or "").strip() == EVERYTHING:
        return out
    for part in [p.strip() for p in _split(str(line or ""), ";") if p.strip()]:
        key, sep, words = part.partition(":")
        key = key.strip()
        if not sep or not key:
            raise ValueError(_("le_bad_part", part=part))
        if key == "any":  # an inner OR: [a: x; b: y] [c: z]
            groups = _groups(words)
            if not groups:
                raise ValueError(_("le_bad_part", part=part))
            out[key] = [parse_line(g) for g in groups]
            continue
        if key not in KEYS and key not in _INTS:
            raise ValueError(_("le_bad_key", word=key, keys=", ".join(sorted(KEYS))))
        words = words.strip()
        if key == "text":
            groups = [[w.strip() for w in g.split("+") if w.strip()]
                      for g in words.split(",") if g.strip()]
            out[key] = groups
        elif key in _BOOLS:
            out[key] = words.lower() in ("true", "yes", "1", "да")
        elif key in _INTS:
            try:
                out[key] = int(words)
            except ValueError:
                raise ValueError(_("le_bad_part", part=part)) from None
        else:
            items = [w.strip() for w in words.split(",") if w.strip()]
            if not items:
                raise ValueError(_("le_bad_part", part=part))
            out[key] = items[0] if len(items) == 1 else items
    return out


def _split(line, sep):
    """`line` split at `sep` outside […]."""
    out, depth, cur = [], 0, []
    for ch in line:
        depth += (ch == "[") - (ch == "]")
        if ch == sep and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def _groups(words):
    """"[a: x; b: y] [c: z]" → ["a: x; b: y", "c: z"]; None when the brackets don't pair."""
    out, depth, cur = [], 0, []
    for ch in words.strip():
        if ch == "[":
            depth += 1
            if depth == 1:
                cur = []
                continue
        elif ch == "]":
            depth -= 1
            if depth < 0:
                return None
            if depth == 0:
                out.append("".join(cur).strip())
                continue
        elif depth == 0:
            if ch.strip():
                return None
            continue
        cur.append(ch)
    return out if depth == 0 else None


def problems(table):
    """What the rule's parser says against a lane (a table): [] — it reads. A lane that
    isn't a rule (Activity, requests, lists, tags: `kind`) has nothing to parse."""
    kind = table.get("kind") if isinstance(table, dict) else None
    if kind is not None or custom._name(table) in ("lists", "tags"):
        return [] if kind in custom.KINDS or kind is None else \
            [f"kind: {kind!r} — one of {', '.join(sorted(custom.KINDS))}"]
    return list(atoms.Rule.parse(table).warnings)


class Editor:
    """The lanes of one config.toml (text): their order, which are shown, each one's
    table, and which of them the file has as its own."""

    def __init__(self, text):
        self.text = text
        try:
            user = tomllib.loads(text) if text.strip() else {}
            cfg, _w = config.validate(user)
        except (tomllib.TOMLDecodeError, config.ConfigError):
            cfg = copy.deepcopy(config.DEFAULTS)
        self.cfg = cfg
        self.preset = cfg["lanes"]["preset"]
        defs = custom.definitions(cfg)
        self.base = {custom._name(t): t for t in presets.lanes_of(self.preset)}
        self.base.update({custom._name(t): t for t in presets.extra()
                          if custom._name(t) not in self.base})
        self.tables = {n: copy.deepcopy(t) for n, t, _own in defs}
        self.own = [n for n, _t, own in defs if own]  # the file's, in its order
        shown = custom.shown_names(cfg)
        self.shown = set(shown)
        self.order = shown + [n for n in self.tables if n not in self.shown]
        self.enabled_set = bool(cfg["lanes"].get("enabled"))

    @classmethod
    def load(cls, view):
        return cls(settings.user_text(view))

    # ---- what a lane is ------------------------------------------------------------------
    def kind(self, name):
        """"rule", or what else it is: "lists", "tags", "activity", "requests"."""
        if name in ("lists", "tags"):
            return name
        t = self.tables.get(name) or {}
        return t.get("kind") or "rule"

    def is_own(self, name):
        return name in self.own

    def from_set(self, name):
        return name in self.base

    def changed(self, name):
        """A set's lane the file has a lane of its own for — other than the set's."""
        return self.from_set(name) and self.is_own(name) and not self._as_set(name)

    def _as_set(self, name):
        """Its table is the set's own, word for word (a copy written into the file)."""
        base = self.base.get(name)
        t = self.tables.get(name)
        return base is not None and t is not None and dict(t, name=name) == dict(base,
                                                                                 name=name)

    def title(self, name):
        t = (self.tables.get(name) or {}).get("title")
        if isinstance(t, dict):
            return t.get(current_language()) or t.get("en") or next(iter(t.values()), "")
        if t:
            return str(t)
        if name in ("lists", "tags"):
            return _("lists_header") if name == "lists" else _("grp_tags")
        key = "lane_" + name
        return _(key) if _(key) != key else name

    # ---- changes -------------------------------------------------------------------------
    def move(self, name, step):
        """One place up (-1) or down (+1) among the lanes shown."""
        shown = [n for n in self.order if n in self.shown]
        if name not in shown:
            return False
        i = shown.index(name)
        j = max(0, min(len(shown) - 1, i + step))
        if i == j:
            return False
        shown[i], shown[j] = shown[j], shown[i]
        self.order = shown + [n for n in self.order if n not in self.shown]
        self.enabled_set = True
        return True

    def toggle(self, name, on=None):
        on = (name not in self.shown) if on is None else bool(on)
        if on:
            self.shown.add(name)
            shown = [n for n in self.order if n in self.shown and n != name] + [name]
            self.order = shown + [n for n in self.order if n not in self.shown]
        else:
            self.shown.discard(name)
            self.order = [n for n in self.order if n in self.shown] + \
                [n for n in self.order if n not in self.shown]
        self.enabled_set = True
        return on

    def put(self, name, table):
        """A lane's new table: one's own from now on (a set's lane: its own of that name)."""
        table = dict(table, name=name)
        self.tables[name] = table
        if name not in self.own:
            self.own.append(name)
        if name not in self.order:
            self.order.append(name)
            self.shown.add(name)
            self.order = [n for n in self.order if n in self.shown] + \
                [n for n in self.order if n not in self.shown]

    def new(self, name):
        """A new lane of one's own: a word not taken; ValueError otherwise."""
        name = str(name or "").strip()
        if not name or not all(c.isalnum() or c in "_-" for c in name):
            raise ValueError(_("le_bad_name"))
        if name in self.tables or name in ("lists", "tags", "unsorted"):
            raise ValueError(_("le_name_taken", name=name))
        self.put(name, {"name": name, "any": [{"author": "me"}]})
        self.enabled_set = True
        return name

    def reset(self, name):
        """A set's lane back to the set's: one's own of its name goes."""
        if name in self.own:
            self.own.remove(name)
        if name in self.base:
            self.tables[name] = copy.deepcopy(self.base[name])

    def delete(self, name):
        """One's own lane gone (a set's lane is only hidden: the set has it)."""
        if self.from_set(name):
            self.reset(name)
            self.toggle(name, False)
            return
        if name in self.own:
            self.own.remove(name)
        self.tables.pop(name, None)
        self.shown.discard(name)
        self.order = [n for n in self.order if n != name]

    # ---- writing -------------------------------------------------------------------------
    def changes(self):
        """{(section, key): value} for config_edit.save."""
        # a set's lane copied into the file as it is isn't one's own: left to the set
        own = [self.tables[n] for n in self.own if n in self.tables and not self._as_set(n)]
        shown = [n for n in self.order if n in self.shown]
        out = {("lanes", "custom"): own}
        probe = copy.deepcopy(self.cfg)
        probe["lanes"]["enabled"] = []
        probe["lanes"]["custom"] = own
        default = custom.shown_names(probe)
        # the set's own order, untouched: lanes.enabled stays unset (the set may grow)
        out[("lanes", "enabled")] = config_edit.UNSET if shown == default and \
            not self.cfg["lanes"].get("enabled") else shown
        return out

    def save(self, view):
        """Into the file, and into the running program. → the words to say."""
        for n in self.own:
            bad = problems(self.tables[n])
            if bad:
                raise settings.SaveError(f"{n}: " + "; ".join(bad))
        cfg, warnings = config_edit.save(settings.config_file(view), self.changes())
        saved = getattr(view, "lanes_saved", None)
        if saved is not None:
            saved(cfg)
        return _("le_saved") + (" · " + "; ".join(warnings) if warnings else "")


__all__ = ["Editor", "KEYS", "cond_line", "parse_line", "problems"]
