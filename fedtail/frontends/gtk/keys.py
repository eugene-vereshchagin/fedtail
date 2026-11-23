"""The config's [keys] (core/keys.py) in GTK's words: a key event as a Key, and an
action's shortcuts added to a Gtk.ShortcutController."""

from ...core import keys
from .gi_setup import Gdk, Gtk


def key_of(keyval, state):
    """A key-pressed event's (keyval, state) → core.keys.Key: the key as its lower-case
    name, Ctrl / Alt / Shift told apart (the keypad's Enter is Enter)."""
    name = Gdk.keyval_name(Gdk.keyval_to_lower(keyval)) or ""
    return keys.from_gdk(name, bool(state & Gdk.ModifierType.CONTROL_MASK),
                         bool(state & Gdk.ModifierType.ALT_MASK),
                         bool(state & Gdk.ModifierType.SHIFT_MASK))


def bind(controller, cfg, action, fn):
    """A shortcut on the controller for every key the config gives the action."""
    for key in keys.of(cfg, action):
        triggers = [key.gtk()]
        if key.name == "enter":  # the keypad's too
            triggers.append(key.gtk().replace("Return", "KP_Enter"))
        for trigger in triggers:
            controller.add_shortcut(Gtk.Shortcut.new(
                Gtk.ShortcutTrigger.parse_string(trigger),
                Gtk.CallbackAction.new(lambda *_a, f=fn: (f(), True)[1])))
