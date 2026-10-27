"""Lanes are rules (docs/en/dev/feeds.md): the sets fedtail comes with (core/presets.py,
lanes.preset) and the lanes of `[[lanes.custom]]` in config.toml, which take a set's lane of
the same name or add new ones — one kind of lane either way.

A lane of one source is a view of that source's stream: its rule filters what the stream
holds (Home, Bots, To me…), and the rest of fedtail treats it as it always did. A lane of
several sources has a stream of its own, `custom:<name>`, filled by the core after each poll:
the new items of its sources go through its rule (`route`); a new lane, or one whose rule
changed, is filled from what is stored already (`backfill`). Activity, follow requests, the
server's lists and the saved tag lanes are kinds of their own (kind = …).
"""

import hashlib
import json
import logging

from . import atoms, lanes, presets
from .model import real

log = logging.getLogger(__name__)

PREFIX = "custom:"  # the stream of a lane of several sources
# the streams a lane can be fed from in this version
FEEDS = {"home", "local", "federated", "mentions", "mine", "bookmarks", "favourites", "subs",
         "watched", "trends", "direct", "bubble"}
FEED_PREFIXES = ("list:", "tags:", "account:", "link:", "quotes:", "remote:")
DEFAULT_FEED = "home"
BACKFILL_ROWS = 3000  # per feed, the newest: what a new lane starts with
KINDS = {"activity", "requests", "lists", "tags"}  # lanes that aren't a rule


def is_custom(name):
    """Is this the stream of a lane of several sources?"""
    return isinstance(name, str) and name.startswith(PREFIX)


def _feedable(source):
    return source in FEEDS or source.startswith(FEED_PREFIXES)


def infer_sources(cond):
    """Where a condition's posts can come from, when it doesn't say (`source`)."""
    s = cond.sets
    if "source" in s:
        return set(s["source"])
    out = set()
    if s.get("me"):
        out.add("subs" if s["me"] == {"in_my_thread"} else "mentions")
    who = s.get("author", set())
    if "me" in who:
        out.add("mine")
    if "local" in who:
        out.add("local")
    if s.get("state", set()) & {"bookmarked"}:
        out.add("bookmarks")
    if s.get("state", set()) & {"liked"}:
        out.add("favourites")
    if not out and cond.inner:  # an inner `any`: where any of its tables come from
        for i in cond.inner:
            out |= infer_sources(i)
    return out or {DEFAULT_FEED}


class Custom:
    """One lane of rules: its rule, the sources that feed it, the stream it is read from."""

    def __init__(self, rule, warnings=(), title=None):
        self.rule = rule
        self.name = rule.name
        self._title = title  # None: the interface's word for the name (a set's lanes)
        self.warnings = list(warnings)
        # conditions of events (likes, follows… — `event = …`): the lane shows those rows
        # of Activity too; they ask no stream of posts
        self.event_conds = [c for c in rule.any if "event" in c.sets]
        feeds = set()
        for cond in rule.any:
            if cond not in self.event_conds:
                feeds |= rule.source or infer_sources(cond)
        bad = sorted(f for f in feeds if not _feedable(f))
        if bad:
            self.warnings.append(f"sources not in this version: {', '.join(bad)}")
        self.feeds = {f for f in feeds if _feedable(f)} or {DEFAULT_FEED}
        # one source: the lane is a view of its stream; several: a stream of its own
        self.routed = len(self.feeds) > 1
        self.stream = PREFIX + self.name if self.routed else next(iter(self.feeds))
        self.needs = rule.needs  # every axis, chips' too (for the quick filters)
        # what deciding "in the lane or not" needs: a condition of `any` that asks nothing
        # (`{}`) takes every post, so then only `none` matters — Home's chips cost nothing
        # until one is chosen
        takes_all = any(not c.sets and not c.counts and not c.text and c.age is None
                        and not c.switch and not c.inner for c in rule.any)
        self.take_needs = set().union(*(c.needs for c in rule.none)) if takes_all \
            else rule.needs
        self.digest = hashlib.sha1(json.dumps(rule_key(rule), sort_keys=True, default=str)
                                   .encode()).hexdigest()[:12]

    @property
    def title(self):
        """The lane's own title (written per language: { ru = …, en = … } — the
        interface's, else English, else the first one); None — the built-in word."""
        t = self._title
        if not isinstance(t, dict):
            return t
        from ..i18n import current_language
        return t.get(current_language()) or t.get("en") or next(iter(t.values()))

    def lane(self):
        if self.routed:
            keep = lanes._all  # its stream holds what the rule took
        else:
            def keep(st, ctx, c=self):
                return c.takes(st, ctx.world, c.stream)
        return lanes.Lane(self.name, self.stream, keep,
                          by_status_time=self.rule.sort == "post_time",
                          lazy=self.rule.read == "browse",
                          feeds=tuple(sorted(self.feeds)) if self.routed else (),
                          chips=self.chips(),
                          group="standard" if self.rule.group == "standard" else "personal",
                          sort=self.rule.sort,
                          window=self.rule.window.total_seconds() if self.rule.window else 0.0,
                          filter_context=self.rule.filter_context)

    def takes(self, status, world, source):
        world = world or atoms.World()
        return self.rule.takes(atoms.post_facts(status, world, source, self.take_needs),
                               world.now)

    def takes_event(self, notification, world=None, which="all"):
        """Does this lane show this event (a row of Activity: a like, a follow…)? One of
        its conditions of events matches it and none of `none` does; with a quick filter
        (`which`: "main", "chip:<n>") — as it shows posts. A mention is a post, not an
        event: the lane takes it as a post or not at all."""
        if not self.event_conds:
            return False
        world = world or atoms.World()
        facts = atoms.event_facts(notification, world)
        if not facts.event or any(c.matches(facts, world.now) for c in self.rule.none):
            return False
        hits = [i for i, c in enumerate(self.rule.any)
                if c in self.event_conds and c.matches(facts, world.now)]
        if not hits:
            return False
        if which == "main":
            return any(self.rule.any[i].shown for i in hits)
        if which.startswith("chip:"):
            return which[5:].isdigit() and int(which[5:]) in hits
        return True

    # ---- quick filters: a condition with `switch` is one, `shown = false` hides it --------
    def chips(self):
        """((key, words)…) of the lane's quick filters: "main" first when a condition is
        hidden by default, then one per condition with a `switch`; () — no switches."""
        out = [(f"chip:{i}", c.switch) for i, c in enumerate(self.rule.any) if c.switch]
        if any(not c.shown for c in self.rule.any):
            out.insert(0, ("main", ""))
        return tuple(out)

    def default_filter(self):
        return "main" if any(not c.shown for c in self.rule.any) else "all"

    def shows(self, status, world, which):
        """Does the quick filter `which` ("all", "main", "chip:<n>") show this post of the
        lane? The post's own source isn't kept, so a condition's `source` is left out here:
        the post is in the lane already."""
        if which == "all" or not which:
            return True
        facts = atoms.post_facts(status, world, None, self.needs)
        now = world.now
        hits = [i for i, c in enumerate(self.rule.any) if _unsourced(c).matches(facts, now)]
        if which == "main":
            return not hits or any(self.rule.any[i].shown for i in hits)
        if which.startswith("chip:"):
            try:
                return int(which[5:]) in hits
            except ValueError:
                return True
        return True


def explain(custom, status, world, sources):
    """Why a post is in a lane of rules or not ("Why is it here?", --explain-lane):
    {"taken": bool, "by": index of `any` that took it or None, "out": index of `none`
    that kept it out or None, "conds": [(part, index, line, reason)]} — reason "" where
    the condition matched, else the first key that didn't."""
    world = world or atoms.World()
    feeds = set(sources) & (custom.feeds | {custom.stream}) or set(sources) or {None}
    facts = atoms.post_facts(status, world, feeds - {None} or None, None)
    now = world.now
    verdicts = custom.rule.explain(facts, now)
    out = {"taken": False, "by": None, "out": None, "conds": [], "source_ok": True}
    for where, i, reason in verdicts:
        if where == "source":
            out["source_ok"] = False
            continue
        cond = (custom.rule.none if where == "none" else custom.rule.any)[i]
        out["conds"].append((where, i, cond.raw, reason))
        if where == "none" and not reason and out["out"] is None:
            out["out"] = i
    if out["source_ok"] and out["out"] is None:
        took = custom.rule.taken_by(facts, now)
        if took is not None:
            out["taken"] = True
            out["by"] = custom.rule.any.index(took)
    return out


def _unsourced(cond):
    if "source" not in cond.sets:
        return cond
    c = atoms.Condition(**{**cond.__dict__, "sets": {k: v for k, v in cond.sets.items()
                                                     if k != "source"}})
    return c


def rule_key(rule):
    """What decides a lane's contents: when it changes, the lane is filled anew."""
    return {"any": [c.raw for c in rule.any], "none": [c.raw for c in rule.none],
            "source": sorted(rule.source)}


# ---- the lanes of a config: the set's, with config.toml's own over them ----------------
def _name(table):
    n = table.get("name") if isinstance(table, dict) else None
    return lanes.canonical(n) if isinstance(n, str) else n


def definitions(cfg):
    """[(name, table, own)] every lane a config can show, in the set's order — its own
    [[lanes.custom]] in the place of a set's lane of that name, new ones after; then the
    lanes of "extra" (shown only when lanes.enabled names them). own: from config.toml."""
    out = [(_name(t), t, False) for t in presets.lanes_of(cfg["lanes"].get("preset"))]
    names = [n for n, _t, _o in out]
    own = set()
    for t in cfg["lanes"].get("custom") or []:
        n = _name(t)
        if not isinstance(t, dict) or not n or n in own:  # the first of a name wins
            continue
        own.add(n)
        t = dict(t, name=n)
        if n in names:
            out[names.index(n)] = (n, t, True)
        else:
            out.append((n, t, True))
            names.append(n)
    for t in presets.extra():
        if _name(t) not in names:
            out.append((_name(t), t, False))
    return out


def shown_names(cfg):
    """The names lanes.enabled shows (or the set's own order), lists and tags among them."""
    defs = definitions(cfg)
    order = [lanes.canonical(n) for n in cfg["lanes"].get("enabled") or []]
    if not order:  # the set's own lanes and one's own; "extra" only when named
        theirs = {_name(t) for t in presets.lanes_of(cfg["lanes"].get("preset"))}
        order = [n for n, _t, own in defs if own or n in theirs]
    else:
        order += [n for n, _t, own in defs if own and n not in order]
    if cfg["lists"]["enabled"] and "lists" not in order:
        order.append("lists")
    if "tags" not in order:
        order.append("tags")
    return list(dict.fromkeys(order))


def load(cfg):
    """[Custom] of every lane of rules a config has (the set's and its own), and the
    warnings about its own ("lanes.custom[2] feed: …"). A `none` condition "apart" from a
    lane that isn't shown is left out: without Direct, the private ones stay where they are."""
    shown = set(shown_names(cfg))
    out, warnings, seen = [], [], set()
    own_index = {}
    for i, t in enumerate(cfg["lanes"].get("custom") or []):
        n = _name(t)
        if n in own_index:
            warnings.append(f"lanes.custom[{i}] {n}: the name is taken by another lane")
        elif n:
            own_index[n] = i
        else:
            rule = atoms.Rule.parse(t)
            warnings += [f"lanes.custom[{i}] ?: {w}" for w in rule.warnings]
    for n, t, own in definitions(cfg):
        if n in seen or (t.get("kind") in KINDS):
            continue
        seen.add(n)
        rule = atoms.Rule.parse({k: v for k, v in t.items() if k not in ("kind",)})
        rule.none = [c for c in rule.none if not c.apart or c.apart in shown]
        title = t.get("title") if own else None
        if isinstance(title, dict):
            title = {k: v for k, v in title.items() if v} or None
        if own and not title and n not in presets.known_names():
            title = n  # one's own lane without a title: its name (a set's: its own word)
        c = Custom(rule, rule.warnings if own else (), title=title)
        if own:
            where = f"lanes.custom[{own_index.get(n, '?')}] {n}"
            warnings += [f"{where}: {w}" for w in c.warnings]
        out.append(c)
    return out, warnings


def build(cfg, lists=(), tag_groups=()):
    """The lanes to show, in order: lanes.enabled's (a name of the set's, "extra"'s or
    one's own; "lists" and "tags" — where those stand), or — empty — the set's own order;
    one's own lanes lanes.enabled doesn't name come after; the lists and the tag lanes
    where their kind stands (else at the end); Unsorted at the very end."""
    rules = {c.name: c for c in load(cfg)[0]}
    kinds = {n: t.get("kind") for n, t, _o in definitions(cfg) if t.get("kind") in KINDS}
    order = shown_names(cfg)
    out, seen = [], set()
    for n in order:
        if n in seen:
            continue
        seen.add(n)
        kind = kinds.get(n) or (n if n in ("lists", "tags") else None)
        if kind == "lists":
            if cfg["lists"]["enabled"]:
                out += [lanes.list_lane(x["id"]) for x in lists]
        elif kind == "tags":
            done = set()
            for g in tag_groups:
                lane = lanes.tag_lane(g)
                if lane.name not in done:
                    done.add(lane.name)
                    out.append(lane)
        elif kind in ("activity", "requests"):
            out.append(lanes.Lane(n, None, lanes._all, group="personal"))
        elif n in rules:
            out.append(rules[n].lane())
    if cfg["lanes"].get("unsorted", True):  # shown only while it holds something (Core)
        out.append(lanes.Lane(lanes.UNSORTED, lanes.UNSORTED, lanes._all, group="personal"))
    return out


def _entry(status):
    return status["id"], status, status.get("created_at", "")


def route(store, customs, new_by_source, world):
    """Put the new items of the real sources into the free lanes that take them.
    new_by_source: {source: [item ids]} as the poll got them. Returns {stream: [new ids]}."""
    out = {}
    customs = [c for c in customs if c.routed]
    wanted = {f for c in customs for f in c.feeds}
    for source, ids in new_by_source.items():
        if source not in wanted or not ids:
            continue
        idset = set(ids)
        rows = [st for item_id, st in store.items(source, len(idset) + 50) if item_id in idset]
        for c in customs:
            if source not in c.feeds:
                continue
            taken = [_entry(st) for st in rows if c.takes(st, world, source)]
            if taken:
                out.setdefault(c.stream, []).extend(store.put_items(c.stream, taken))
    return {k: v for k, v in out.items() if v}  # by stream, as new_by_source is


def take(store, custom, statuses, world, source):
    """Put into a lane what of `statuses` (come from `source`) its rule takes. Returns
    the statuses taken."""
    taken = [st for st in statuses if custom.takes(st, world, source)]
    store.put_items(custom.stream, [_entry(st) for st in taken])
    return taken


def unsorted(store, lanes_now, new_by_source, ctx, taken):
    """What came from the read-through sources and no lane took — into "Unsorted".
    taken: status ids the free lanes took this round. Browse sources (federated, local
    while lazy) don't go there: they'd drown it. Returns the new item ids."""
    browse = {lane.source for lane in lanes_now if lane.lazy} - \
        {f for lane in lanes_now if lane.feeds and not lane.lazy for f in lane.feeds}
    put = []
    for source, ids in new_by_source.items():
        if not ids or source in browse or is_custom(source) or source == lanes.UNSORTED:
            continue
        idset = set(ids)
        own = [x for x in lanes_now if x.source == source and not x.feeds]
        rows = [st for item_id, st in store.items(source, len(idset) + 50) if item_id in idset]
        # held by another lane already: a lane of several sources, a list, a tag lane…
        others = {x.source for x in lanes_now if x.source and x.source != source}
        held = store.held_by(PREFIX, [st["id"] for st in rows]) | \
            store.held_in(others, [st["id"] for st in rows])
        for st in rows:
            if st["id"] in taken or st["id"] in held:
                continue
            # someone put in a list: read in the list's lane (lists.hide_in took them out)
            if st["account"]["id"] in ctx.hidden or real(st)["account"]["id"] in ctx.hidden:
                continue
            if any(lanes.keeps(x, st, ctx) for x in own):
                continue
            put.append(_entry(st))
    return store.put_items(lanes.UNSORTED, put)


def backfill(store, custom, world, rows=BACKFILL_ROWS):
    """Fill a lane anew from what is stored for its feeds. Returns how many it took."""
    store.prune(custom.stream, 0)
    taken = []
    for source in sorted(custom.feeds):
        for _item_id, st in store.iter_items(source, max_rows=rows):
            if custom.takes(st, world, source):
                taken.append(_entry(st))
    store.put_items(custom.stream, taken)
    store.kv_set(f"custom_rule:{custom.stream}", custom.digest)
    log.info("lane %s: %d posts from %s", custom.name, len(taken),
             ", ".join(sorted(custom.feeds)))
    return len(taken)


def stale(store, custom):
    """Is the lane's stream not what its rule would make (new lane, changed rule)?"""
    return store.kv_get(f"custom_rule:{custom.stream}") != custom.digest
