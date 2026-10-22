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
    lo_w, nat_w = w.measure(horizontal, -1)[:2]
    lo_w = max(1, lo_w)
    top = max(lo_w, nat_w, w.get_width(), 760) + 160
    widths = sorted(set(range(lo_w, top, 8)) | {w.get_width(), 744})
    box418 = None
    if isinstance(w, Gtk.Box) and w.get_orientation() == horizontal:
        # GTK 4.18's own rule (gtkboxlayout.c): a horizontal box's least height is its
        # children's least at their least width (measured at -1), whatever width it
        # gets — 4.14 here never shows it, so it is worked out the same way
        kids, c = [], w.get_first_child()
        while c is not None:
            if c.get_visible():
                kids.append(c.measure(vertical, -1)[0])
            c = c.get_next_sibling()
        box418 = max(kids, default=0)
    for width in widths:
        if width < lo_w:
            continue
        least, natural = w.measure(vertical, width)[:2]
        if box418 is not None:
            least = max(least, box418)
        if least > natural:
            return width, least, natural
    return None


def bad_heights(root, stop=None):
    """[(path, least, natural, width)] under root: path from the culprit up to (not
    including) a widget of class stop, or to root. Only where root itself goes wrong
    are its children looked into (widths tried are dear: hundreds of measures each)."""
    out = []

    def check(w):
        if not w.get_visible():  # (not placed yet is fine: that's when GTK asks)
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


def watch(cards, most=3, out=print):
    """GTK's own warning ("Card … reported min height … in measure() with for_size=…")
    caught as it happens — the card is in the state GTK found it in (built, not placed,
    its pictures not come), which a check afterwards never sees. The first `most` are
    taken apart: which widget inside goes wrong. cards() → the cards there are now.
    Everything else logged goes on to the terminal as before."""
    import ctypes
    import re
    import sys

    from .gi_setup import GLib
    pattern = re.compile(r"(\w+) (0x[0-9a-f]+) \(\w+\) reported min height (\d+) and natural "
                         r"height (\d+) in measure\(\) with for_size=(\d+)")
    get_pointer = ctypes.pythonapi.PyCapsule_GetPointer
    get_pointer.restype = ctypes.c_void_p
    get_pointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
    state = {"seen": 0, "busy": False, "said": 0}

    def text_of(fields):
        for f in fields:
            if f.key == "MESSAGE" and f.value:
                raw = ctypes.string_at(f.value) if f.length < 0 else \
                    ctypes.string_at(f.value, f.length)
                return raw.decode("utf-8", "replace")
        return ""

    def writer(level, fields, *_a):
        msg = text_of(fields)
        m = pattern.search(msg)
        if m and not state["busy"]:
            state["seen"] += 1
            if state["said"] < most:
                state["busy"] = True
                try:
                    addr = int(m.group(2), 16)
                    card = next((c for c in cards()
                                 if get_pointer(c.__gpointer__, None) == addr), None)
                    state["said"] += 1
                    out(f"  GTK: {m.group(1)} min {m.group(3)} > natural {m.group(4)} at "
                        f"{m.group(5)} — " + ("the card isn't among the lane's" if card is None
                                              else "inside it:"))
                    if card is not None:
                        lines = bad_heights(card) or [("(nothing inside, measured now: it "
                                                        "goes wrong only mid-build)", 0, 0, 0)]
                        for path, lo, nat, width in lines[:6]:
                            out(f"     {path}: least {lo} > natural {nat} at width {width}")
                        out(f"     mapped {card.get_mapped()}, width {card.get_width()}, "
                            f"post {getattr(getattr(card, 'post', None), 'id', '?')}")
                finally:
                    state["busy"] = False
            return GLib.LogWriterOutput.HANDLED
        if m:
            return GLib.LogWriterOutput.HANDLED
        if level & (GLib.LogLevelFlags.LEVEL_DEBUG | GLib.LogLevelFlags.LEVEL_INFO):
            return GLib.LogWriterOutput.HANDLED
        print(msg, file=sys.stderr, flush=True)
        return GLib.LogWriterOutput.HANDLED

    GLib.log_set_writer_func(writer, None)
    return state


def boxes_418(root):
    """Every horizontal box under root that GTK 4.18 would warn of: its children's
    least height at their least width above its natural height at the width it has.
    [(path, least, natural, width)] — the whole window walked, cheap (a measure or two a
    box)."""
    out = []
    hor, ver = Gtk.Orientation.HORIZONTAL, Gtk.Orientation.VERTICAL

    def walk(w):
        if not w.get_visible():
            return
        if isinstance(w, Gtk.Box) and w.get_orientation() == hor and w.get_width() > 0:
            kids, c = [], w.get_first_child()
            while c is not None:
                if c.get_visible():
                    kids.append(c.measure(ver, -1)[0])
                c = c.get_next_sibling()
            least = max(kids, default=0)
            natural = w.measure(ver, w.get_width())[1]
            if least > natural:
                chain, p = [], w
                for _i in range(5):
                    if p is None:
                        break
                    chain.append(type(p).__name__ + "".join(
                        "." + x for x in p.get_css_classes()[:2]))
                    p = p.get_parent()
                out.append((" < ".join(chain), least, natural, w.get_width()))
        c = w.get_first_child()
        while c is not None:
            walk(c)
            c = c.get_next_sibling()
    walk(root)
    return out
