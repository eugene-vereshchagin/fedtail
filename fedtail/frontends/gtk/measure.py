"""Widgets that measure themselves wrong: a least height above the natural one at the
width they have. GTK 4.18 warns of the Card so ("reported min height 260 and natural
height 241 in measure()"), thousands of lines a bench, and lays it out by a guess. This
names the culprit: the deepest widget that does it, whose own children are all right.
Used by the GTK tests and tools/gtk_bench.py; nothing in the window calls it."""

from __future__ import annotations

from .gi_setup import Gtk


def _bad_at(w):
    """A width at which w says least height > natural one, or None. Tried across widths
    (from its least one to past the one it has): GTK asks at widths it never gives
    (4.18: the Card at 744 while it had another), and that's where it goes wrong."""
    horizontal, vertical = Gtk.Orientation.HORIZONTAL, Gtk.Orientation.VERTICAL
    lo_w = max(1, w.measure(horizontal, -1)[0])
    top = max(lo_w, w.get_width()) + 160
    widths = sorted(set(range(lo_w, top, 8)) | {w.get_width(), 744})
    for width in widths:
        if width < lo_w:
            continue
        least, natural = w.measure(vertical, width)[:2]
        if least > natural:
            return width, least, natural
    return None


def bad_heights(root, stop=None):
    """[(path, least, natural, width)] under root: path from the culprit up to (not
    including) a widget of class stop, or to root. Only where root itself goes wrong
    are its children looked into (widths tried are dear: hundreds of measures each)."""
    out = []

    def check(w):
        if not w.get_visible() or w.get_width() <= 0:
            return False
        hit = _bad_at(w)
        if hit is None:
            return False
        kids_bad = False
        c = w.get_first_child()
        while c is not None:
            kids_bad |= check(c)
            c = c.get_next_sibling()
        if not kids_bad:
            width, least, natural = hit
            chain, p = [], w
            while p is not None:
                chain.append(type(p).__name__ + "".join(
                    "." + x for x in p.get_css_classes()[:2]))
                if p is root or (stop and isinstance(p, stop)):
                    break
                p = p.get_parent()
            out.append((" < ".join(chain), least, natural, width))
        return True
    check(root)
    return out


def report(roots, stop=None, most=12, limit=60):
    """Lines saying who measures wrong under each of roots (a set of kinds, counted);
    the first `limit` roots."""
    seen = {}
    for r in list(roots)[:limit]:
        for path, least, natural, width in bad_heights(r, stop):
            hit = seen.setdefault(path, [0, least, natural, width])
            hit[0] += 1
    return [f"{n}×  {path}: least {lo} > natural {nat} at width {w}"
            for path, (n, lo, nat, w) in sorted(seen.items(), key=lambda kv: -kv[1][0])
            ][:most]
