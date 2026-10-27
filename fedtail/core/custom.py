"""Free lanes: the lanes of `[[lanes.custom]]` (docs/en/dev/feeds.md), first version.

Every free lane is a stream of its own in the store, `custom:<name>`, filled by the core,
not fetched: after each poll the new items of the real sources (home, mentions, local…) go
through the lanes' rules (core/atoms.py) and those a rule takes are put into its stream. So
a free lane is, to the rest of fedtail, a lane like any other: unread marks, counts, never
jumping, notifications, sounds, columns — all as they are.

A new lane — or one whose rule changed — is filled from what is stored already (`backfill`),
nothing is fetched for it. What this version doesn't do yet: events (likes, follows) in a
lane, the quick-filter chips (`switch`), "Unsorted", fetching older pages for a free lane.
"""

import hashlib
import json
import logging

from . import atoms, lanes

log = logging.getLogger(__name__)

PREFIX = "custom:"
# the streams a free lane can be fed from in this version
FEEDS = {"home", "local", "federated", "mentions", "mine", "bookmarks", "favourites", "subs"}
FEED_PREFIXES = ("list:", "tags:")
DEFAULT_FEED = "home"
BACKFILL_ROWS = 3000  # per feed, the newest: what a new lane starts with


# the quick filters of built-in lanes, as rules: (lanes.HOME_CHIPS, TO_ME_CHIPS) — the
# chip's words are i18n keys, the rule only parts what the lane already holds
BUILTIN_CHIPS = {
    "home": [{"via": "tag", "switch": "@chip_tags"}, {"kind": "boost", "switch": "@chip_boosts"},
             {"state": "new_replies", "switch": "@chip_threads_new"}],
    "to_me": [{"me": "reply", "switch": "@chip_replies"},
              {"me": ["mention", "direct"], "switch": "@chip_mentions"}],
}


def builtin_chips(name):
    """A Custom whose rule gives a built-in lane its quick filters, or None."""
    conds = BUILTIN_CHIPS.get(name)
    if not conds:
        return None
    return Custom(atoms.Rule.parse({"name": name, "source": "home", "any": conds}))


def is_custom(name):
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
    return out or {DEFAULT_FEED}


class Custom:
    """One free lane: its rule, its stream, the sources that feed it."""

    def __init__(self, rule, warnings=()):
        self.rule = rule
        self.name = PREFIX + rule.name
        self._title = rule.title or rule.name
        self.warnings = list(warnings)
        feeds = set()
        for cond in rule.any:
            feeds |= rule.source or infer_sources(cond)
        bad = sorted(f for f in feeds if not _feedable(f))
        if bad:
            self.warnings.append(f"sources not in this version: {', '.join(bad)}")
        self.feeds = {f for f in feeds if _feedable(f)}
        self.digest = hashlib.sha1(json.dumps(rule_key(rule), sort_keys=True, default=str)
                                   .encode()).hexdigest()[:12]

    @property
    def title(self):
        """The lane's title; written per language ({ ru = …, en = … }) — the interface's,
        else English, else the first one."""
        t = self._title
        if not isinstance(t, dict):
            return t
        from ..i18n import current_language
        return t.get(current_language()) or t.get("en") or next(iter(t.values()))

    def lane(self):
        return lanes.Lane(self.name, self.name, lanes._all,
                          by_status_time=self.rule.sort == "post_time",
                          lazy=self.rule.read == "browse", feeds=tuple(sorted(self.feeds)),
                          chips=self.chips(),
                          group="standard" if self.rule.group == "standard" else "personal")

    def takes(self, status, world, source):
        return self.rule.takes(atoms.post_facts(status, world, source), world.now)

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
        facts = atoms.post_facts(status, world)
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


def load(cfg):
    """[Custom] from cfg["lanes"]["custom"], and the warnings ("lanes.custom[2]: …")."""
    out, warnings, seen = [], [], set()
    for i, table in enumerate(cfg["lanes"].get("custom") or []):
        rule = atoms.Rule.parse(table)
        where = f"lanes.custom[{i}] {rule.name or '?'}"
        if not rule.name:
            warnings += [f"{where}: {w}" for w in rule.warnings]
            continue
        if rule.name in seen:
            warnings.append(f"{where}: the name is taken by another lane")
            continue
        seen.add(rule.name)
        c = Custom(rule, rule.warnings)
        warnings += [f"{where}: {w}" for w in c.warnings]
        out.append(c)
    return out, warnings


def _entry(status):
    return status["id"], status, status.get("created_at", "")


def route(store, customs, new_by_source, world):
    """Put the new items of the real sources into the free lanes that take them.
    new_by_source: {source: [item ids]} as the poll got them. Returns {lane: [new ids]}."""
    out = {}
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
                out.setdefault(c.name, []).extend(store.put_items(c.name, taken))
    return {k: v for k, v in out.items() if v}


def take(store, custom, statuses, world, source):
    """Put into a lane what of `statuses` (come from `source`) its rule takes. Returns
    the statuses taken."""
    taken = [st for st in statuses if custom.takes(st, world, source)]
    store.put_items(custom.name, [_entry(st) for st in taken])
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
        held = store.held_by(PREFIX, [st["id"] for st in rows])  # taken before, from elsewhere
        for st in rows:
            if st["id"] in taken or st["id"] in held:
                continue
            if any(lanes.keeps(x, st, ctx) for x in own):
                continue
            put.append(_entry(st))
    return store.put_items(lanes.UNSORTED, put)


def backfill(store, custom, world, rows=BACKFILL_ROWS):
    """Fill a lane anew from what is stored for its feeds. Returns how many it took."""
    store.prune(custom.name, 0)
    taken = []
    for source in sorted(custom.feeds):
        for _item_id, st in store.iter_items(source, max_rows=rows):
            if custom.takes(st, world, source):
                taken.append(_entry(st))
    store.put_items(custom.name, taken)
    store.kv_set(f"custom_rule:{custom.name}", custom.digest)
    log.info("free lane %s: %d posts from %s", custom.name, len(taken),
             ", ".join(sorted(custom.feeds)))
    return len(taken)


def stale(store, custom):
    """Is the lane's stream not what its rule would make (new lane, changed rule)?"""
    return store.kv_get(f"custom_rule:{custom.name}") != custom.digest
