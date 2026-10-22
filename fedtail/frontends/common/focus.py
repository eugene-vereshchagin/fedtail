"""A picture's focus point (Mastodon: x, y in -1…1, y up) — which part every app that
crops a preview keeps — from a click on the picture and back, for every toolkit."""


def to_focus(x, y, w, h):
    """A click at (x, y) on a w×h picture → the focus point."""
    fx = max(-1.0, min(1.0, x / w * 2 - 1))
    fy = max(-1.0, min(1.0, 1 - y / h * 2))
    return round(fx, 2), round(fy, 2)


def from_focus(focus, w, h):
    """The focus point → where on a w×h picture."""
    fx, fy = focus
    return (fx + 1) / 2 * w, (1 - fy) / 2 * h
