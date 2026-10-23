"""Lanes made of several hashtags: "#georgia #грузия -#politics" — any of these, all of
"+" ones, none of "-" ones. Typed into the search, saved from there into the sidebar
(kept by fedtail), or written in the config ([[lanes.tag_groups]]).

Mastodon could answer that in one request (timelines/tag/:t?any[]=…), GoToSocial reads
only one tag; so the posts of each tag are fetched and put together here, the same on
every server: newest first, each once, the "+" and "-" ones checked on the posts."""

import re

PREFIX = "tags:"
_TAG = re.compile(r"^([+-]?)#([\w·‌]+)$")


def parse(text, one_ok=False):
    """{"any": [...], "all": [...], "none": [...]} from "#a #b +#c -#d", or None when it
    isn't only tags or is a single plain one (that's the ordinary tag lane)."""
    words = (text or "").split()
    if not words:
        return None
    spec = {"any": [], "all": [], "none": []}
    for w in words:
        m = _TAG.match(w)
        if not m:
            return None
        kind = {"": "any", "+": "all", "-": "none"}[m.group(1)]
        tag = m.group(2).lower()
        if tag not in spec[kind]:
            spec[kind].append(tag)
    if not spec["any"] and not spec["all"]:
        return None
    if len(spec["any"]) + len(spec["all"]) < 2 and not spec["none"] and not one_ok:
        return None  # one tag typed in the search: its own tab, as always
    return spec


def normal(spec):
    """The same spec whatever the order or case it was written in."""
    return {k: sorted({str(t).lower().lstrip("#") for t in spec.get(k) or []})
            for k in ("any", "all", "none")}


def key(spec):
    s = normal(spec)
    return " ".join(["#" + t for t in s["any"]] + ["+#" + t for t in s["all"]] +
                    ["-#" + t for t in s["none"]])


def lane_name(spec):
    return PREFIX + key(spec)


def is_tags(name):
    return str(name).startswith(PREFIX)


def spec_of(name):
    # a saved lane may be one tag (its tab's "＋ to lanes")
    return parse(name[len(PREFIX):], one_ok=True) if is_tags(name) else None


def title(spec):
    """How the lane is called when it has no name of its own."""
    return key(spec)


def matches(st, spec):
    """Does a post fit: one of "any" (when there are any), every "all", no "none"."""
    from .model import real
    tags = {(t.get("name") or "").lower() for t in real(st).get("tags") or []}
    s = normal(spec)
    if s["any"] and not tags & set(s["any"]):
        return False
    if any(t not in tags for t in s["all"]):
        return False
    return not tags & set(s["none"])


def fetch(tag_timeline, spec, limit=40, max_id=None, min_id=None):
    """One page of the lane: each "any" tag's timeline (or the first "all" one, when
    there are no "any"), put together newest first, each post once, then checked."""
    s = normal(spec)
    asked = s["any"] or s["all"][:1]
    seen, out = set(), []
    for tag in asked:
        for st in tag_timeline(tag, limit=limit, max_id=max_id, min_id=min_id) or []:
            if st["id"] not in seen:
                seen.add(st["id"])
                out.append(st)
    out = [st for st in out if matches(st, s)]
    out.sort(key=lambda st: (st.get("created_at") or "", st["id"]), reverse=True)
    return out
