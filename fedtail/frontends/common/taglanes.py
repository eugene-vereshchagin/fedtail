"""A hashtag into the sidebar's "Tags": a lane of its own, or one more tag of a lane of
tags kept there — the "＋ to lanes ▾" next to Follow wherever a tag is shown (a search,
its tab). Qt and GTK draw the menu; the choices are made here.

    for key, words, on in taglanes.choices(view, "tbilisi"): …
    taglanes.apply(view, key, "tbilisi") -> Future of the lane's name
"""

from __future__ import annotations

from ...core import taggroups
from ...i18n import _

OWN = "own"


def choices(view, tag):
    """[(key, words, enabled)]: its own lane (not when it's there already), then each
    lane of tags saved from fedtail (a lane from the config is changed in the config)."""
    tag = tag.lstrip("#").lower()
    own = taggroups.lane_name(taggroups.normal({"any": [tag]}))
    out = [(OWN, _("tags_own_lane"), own not in view.lane_by_name)]
    for g in getattr(view, "tag_groups", None) or []:
        if not g.get("saved"):
            continue
        name = taggroups.lane_name(g)
        if name == own:
            continue
        title = g.get("name") or taggroups.title(g)
        has = tag in (g.get("any") or []) + (g.get("all") or [])
        out.append((name, _("tags_into_lane", lane=title), not has))
    return out


def apply(view, key, tag):
    tag = tag.lstrip("#").lower()
    if key == OWN:
        return view.save_tag_group({"any": [tag]})
    return view.add_tag_to_group(key, tag)


__all__ = ["OWN", "apply", "choices"]
