"""Widgets that measure themselves wrong: a least height above the natural one at the
width they have. GTK 4.18 warns of the Card so ("reported min height 260 and natural
height 241 in measure()"), thousands of lines a bench, and lays it out by a guess. This
names the culprit: the deepest widget that does it, whose own children are all right.
Used by the GTK tests and tools/gtk_bench.py; nothing in the window calls it."""

from __future__ import annotations

from .gi_setup import Gtk


def bad_heights(root, stop=None):
    """[(path, least, natural, width)] under root: path from the culprit up to (not
    including) a widget of class stop, or to root."""
    out = []
    vertical = Gtk.Orientation.VERTICAL

    def check(w):
        kids_bad = False
        c = w.get_first_child()
        while c is not None:
            kids_bad |= check(c)
            c = c.get_next_sibling()
        width = w.get_width()
        if width <= 0 or not w.get_visible():
            return kids_bad
        least, natural = w.measure(vertical, width)[:2]
        if least <= natural:
            return kids_bad
        if not kids_bad:
            chain, p = [], w
            while p is not None and p is not root and not (stop and isinstance(p, stop)):
                chain.append(type(p).__name__ + "".join(
                    "." + x for x in p.get_css_classes()[:2]))
                p = p.get_parent()
            out.append((" < ".join(chain), least, natural, width))
        return True
    check(root)
    return out


def report(roots, stop=None, most=12):
    """Lines saying who measures wrong under each of roots (a set of kinds, counted)."""
    seen = {}
    for r in roots:
        for path, least, natural, width in bad_heights(r, stop):
            hit = seen.setdefault(path, [0, least, natural, width])
            hit[0] += 1
    return [f"{n}×  {path}: least {lo} > natural {nat} at width {w}"
            for path, (n, lo, nat, w) in sorted(seen.items(), key=lambda kv: -kv[1][0])
            ][:most]
