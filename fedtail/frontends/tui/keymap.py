"""The terminal's keys as a keymap: every binding of every screen has a name (its
action), and a key of another's choosing goes by it — the config's ``[keys]`` for what
the posts do (next_post, reply, like… — core/keys.py, the same table as the windows'),
and ``tui.keys`` for anything else the terminal has (``"quit = Ctrl+Q"``). The letters were
written into each screen (23.11).

Textual does the work (``App.set_keymap``: a binding's id → its keys); here the ids are
given and the config is turned into Textual's words."""

import logging
from dataclasses import replace

from textual.binding import Binding

from ...core import keys

log = logging.getLogger(__name__)

# a binding's id (its action) → the action of the config's [keys] whose keys it takes
FROM_KEYS = {"cursor_down": "next_post", "cursor_up": "previous_post", "reply": "reply",
             "fav": "like", "boost": "boost", "bookmark": "bookmark",
             "top_comment(1)": "next_comment", "top_comment(-1)": "previous_comment",
             "fold_branch": "fold_branch"}


def named(bindings):
    """A screen's BINDINGS with an id on each — its action — so a keymap finds it:
    ``BINDINGS = named([...])`` (in the class's body: Textual reads BINDINGS when the
    class is made). One action bound twice in a screen keeps one id: both move."""
    out = []
    for b in bindings:
        if not isinstance(b, Binding):
            b = Binding(*b)
        out.append(b if b.id else replace(b, id=b.action))
    return out


def ids(*classes):
    """Every binding id of these screens: what tui.keys may name."""
    return sorted({b.id for cls in classes for b in cls.__dict__.get("BINDINGS", ())
                   if isinstance(b, Binding) and b.id})


def defaults(*classes):
    """[(binding id, its keys as written in the code)] of these screens, by name."""
    got = {}
    for cls in classes:
        for b in cls.__dict__.get("BINDINGS", ()):
            if isinstance(b, Binding) and b.id:
                had = got.setdefault(b.id, [])
                had += [k for k in b.key.split(",") if k not in had]
    return sorted((bid, " ".join(ks)) for bid, ks in got.items())


def keymap(cfg, known=()):
    """Textual's keymap for a config: {binding id: "key,key"}. The posts' keys from
    [keys]; then tui.keys — lines "binding id = keys as [keys] writes them" — over it. A key
    that isn't one, F1, an id no screen has: left out, said in the log."""
    out = {}
    for bid, action in FROM_KEYS.items():
        got = keys.of(cfg, action)
        if got:
            out[bid] = ",".join(k.textual() for k in got)
    for line in ((cfg or {}).get("tui") or {}).get("keys") or ():
        bid, sep, value = str(line).partition("=")
        bid = bid.strip()
        if not sep or not bid:
            log.warning('tui.keys: "%s" — written as "name = keys"', line)
            continue
        got, wrong = keys.read(value)
        for w in wrong:
            log.warning("tui.keys.%s: %s", bid, w)
        if known and bid not in known:
            log.warning("tui.keys: no key is called %s; there are: %s", bid,
                        ", ".join(known))
            continue
        if got:
            out[str(bid)] = ",".join(k.textual() for k in got)
    return out


def apply(app, cfg, known=()):
    """Set the app's keymap from the config (a Textual without keymaps: its own keys)."""
    setter = getattr(app, "set_keymap", None)
    if setter is None:  # Textual before keymaps
        log.info("this Textual has no keymaps: the keys stay as written")
        return {}
    got = keymap(cfg, known)
    setter(got)
    return got
