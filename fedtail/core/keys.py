"""The keys of every interface, from the config's ``[keys]`` table: which key does what is
the reader's to say, the defaults are the author's (docs/en/dev/principles.md: every
behaviour is a config key — the shortcuts were nailed into each window, 23.11).

One table (core/config.py ``DEFAULTS["keys"]``): an action's name → its keys, written the
way people write them — ``"Ctrl+N"``, ``"Shift+F3"``, ``"j"``, ``"]"``; several keys for
one action are separated by spaces (``"o Enter"``); ``""`` — no key at all. This module
reads a key once and says it in each toolkit's own words (``qt``, ``gtk``, ``textual``,
``web``), so no interface parses anything, and matches the events the toolkits give
(``from_gdk``, ``from_qt``).

Never ``F1`` or ``Shift+F1``, whatever the file says: they sit next to Esc (the
principles' last line) — such a key is dropped, and the config's check says so.
"""

from __future__ import annotations

from dataclasses import dataclass

# what the window itself does, and what the posts of a lane or a thread do (the second
# group goes off with window.post_keys = false)
WINDOW = ("new_post", "send", "search", "find", "find_next", "find_previous",
          "command_line", "refresh", "close_tab", "quit")
POSTS = ("next_post", "previous_post", "reply", "like", "boost", "bookmark",
         "open_thread", "next_comment", "previous_comment", "fold_branch")
ACTIONS = WINDOW + POSTS

# a key's names as people write them → the one name kept here
_NAMES = {
    "enter": "enter", "return": "enter", "esc": "escape", "escape": "escape",
    "space": "space", "tab": "tab", "backspace": "backspace",
    "del": "delete", "delete": "delete", "ins": "insert", "insert": "insert",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "home": "home", "end": "end",
    "pgup": "pageup", "pageup": "pageup", "pgdn": "pagedown", "pgdown": "pagedown",
    "pagedown": "pagedown", "plus": "+",
}
_NAMES.update({f"f{n}": f"f{n}" for n in range(1, 13)})

_MODS = {"ctrl": "ctrl", "control": "ctrl", "alt": "alt", "shift": "shift",
         "meta": "ctrl", "cmd": "ctrl"}

# the same key in each toolkit's words, where it isn't the name itself
_QT = {"enter": "Return", "escape": "Esc", "space": "Space", "tab": "Tab",
       "backspace": "Backspace", "delete": "Del", "insert": "Ins", "up": "Up",
       "down": "Down", "left": "Left", "right": "Right", "home": "Home", "end": "End",
       "pageup": "PgUp", "pagedown": "PgDown"}
_GDK = {"enter": "Return", "escape": "Escape", "space": "space", "tab": "Tab",
        "backspace": "BackSpace", "delete": "Delete", "insert": "Insert", "up": "Up",
        "down": "Down", "left": "Left", "right": "Right", "home": "Home", "end": "End",
        "pageup": "Page_Up", "pagedown": "Page_Down",
        "]": "bracketright", "[": "bracketleft", "-": "minus", "+": "plus", "=": "equal",
        "/": "slash", "\\": "backslash", ".": "period", ",": "comma", ";": "semicolon",
        ":": "colon", "'": "apostrophe", "`": "grave", "?": "question", "!": "exclam",
        "*": "asterisk", "#": "numbersign", "@": "at"}
_TEXTUAL = {"pageup": "pageup", "pagedown": "pagedown",
            "]": "right_square_bracket", "[": "left_square_bracket", "-": "minus",
            "+": "plus", "=": "equals_sign", "/": "slash", "\\": "backslash",
            ".": "full_stop", ",": "comma", ";": "semicolon", ":": "colon",
            "'": "apostrophe", "`": "grave_accent", "?": "question_mark",
            "!": "exclamation_mark", "*": "asterisk", "#": "number_sign", "@": "at"}
_WEB = {"enter": "Enter", "escape": "Escape", "space": " ", "tab": "Tab",
        "backspace": "Backspace", "delete": "Delete", "insert": "Insert",
        "up": "ArrowUp", "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight",
        "home": "Home", "end": "End", "pageup": "PageUp", "pagedown": "PageDown"}
_FROM_GDK = {v.lower(): k for k, v in _GDK.items()}
_FROM_GDK.update({"kp_enter": "enter", "iso_enter": "enter", "kp_subtract": "-",
                  "kp_add": "+"})
_FROM_QT = {v.lower(): k for k, v in _QT.items()}
_FROM_QT.update({"enter": "enter", "escape": "escape", "pgdown": "pagedown",
                 "pgup": "pageup"})


@dataclass(frozen=True)
class Key:
    """One key with its modifiers. name: a character in lower case ("n", "]", "5") or a
    key's name as _NAMES keeps it ("enter", "f5", "up")."""
    name: str
    ctrl: bool = False
    alt: bool = False
    shift: bool = False

    @property
    def plain(self):
        """No modifier: a letter of the posts (j, k, r…), typed with nothing held."""
        return not (self.ctrl or self.alt or self.shift)

    def words(self):
        """As the help and a tooltip say it: Ctrl+N, Shift+F3, j, Enter."""
        name = self.name
        if len(name) > 1:
            name = {"pageup": "PgUp", "pagedown": "PgDn", "escape": "Esc"}.get(
                name, name.capitalize() if not name.startswith("f") else name.upper())
        elif self.ctrl or self.alt or self.shift:
            name = name.upper()
        return "+".join([m for m, on in (("Ctrl", self.ctrl), ("Alt", self.alt),
                                         ("Shift", self.shift)) if on] + [name])

    def qt(self):
        """For QKeySequence: "Ctrl+Shift+N", "Return", "F5", "]"."""
        name = _QT.get(self.name) or (self.name.upper() if len(self.name) > 1 else
                                      self.name.upper())
        return "+".join([m for m, on in (("Ctrl", self.ctrl), ("Alt", self.alt),
                                         ("Shift", self.shift)) if on] + [name])

    def gtk(self):
        """For Gtk.ShortcutTrigger.parse_string: "<Control><Shift>n", "F5", "Return"."""
        name = _GDK.get(self.name) or (self.name.upper() if self.name.startswith("f")
                                       and len(self.name) > 1 else self.name)
        return "".join(m for m, on in (("<Control>", self.ctrl), ("<Alt>", self.alt),
                                       ("<Shift>", self.shift)) if on) + name

    def textual(self):
        """For a Textual Binding: "ctrl+n", "shift+f3", "j", "enter"."""
        name = _TEXTUAL.get(self.name, self.name)
        return "+".join([m for m, on in (("ctrl", self.ctrl), ("alt", self.alt),
                                         ("shift", self.shift)) if on] + [name])

    def web(self):
        """For the page: what a KeyboardEvent of it says — {"key", "ctrl", "alt",
        "shift"} (a letter in lower case: the page lowers the event's own)."""
        return {"key": _WEB.get(self.name) or (self.name.upper() if self.name.startswith("f")
                                              and len(self.name) > 1 else self.name),
                "ctrl": self.ctrl, "alt": self.alt, "shift": self.shift}


def parse(spec):
    """One key as written ("Ctrl+N", "shift+f3", "j", "]", "Ctrl++") → Key; ValueError
    with the reason when it isn't one."""
    text = str(spec or "").strip()
    if not text:
        raise ValueError("an empty key")
    if text.endswith("++") or text == "+":  # the plus key itself
        parts = [p for p in text[:-1].split("+") if p] + ["+"]
    else:
        parts = text.split("+")
    *mods, name = [p.strip() for p in parts]
    if not name:
        raise ValueError(f"{text}: no key after the modifiers")
    got = {}
    for m in mods:
        mod = _MODS.get(m.lower())
        if mod is None:
            raise ValueError(f"{text}: {m} is no modifier (Ctrl, Alt, Shift)")
        got[mod] = True
    low = name.lower()
    if len(name) == 1:
        key = low
    elif low in _NAMES:
        key = _NAMES[low]
    else:
        raise ValueError(f"{text}: {name} is no key fedtail knows")
    return Key(key, **got)


def forbidden(key):
    """F1 and Shift+F1 are never shortcuts: they sit next to Esc."""
    return key.name == "f1" and not key.ctrl and not key.alt


def read(value):
    """A [keys] value ("o Enter", a list of such, "") → ([Key], [what was wrong])."""
    if isinstance(value, (list, tuple)):
        specs = [str(v) for v in value]
    else:
        specs = str(value or "").split()
    keys, wrong = [], []
    for spec in specs:
        try:
            key = parse(spec)
        except ValueError as e:
            wrong.append(str(e))
            continue
        if forbidden(key):
            wrong.append(f"{spec}: F1 and Shift+F1 are never shortcuts (next to Esc)")
        elif key not in keys:
            keys.append(key)
    return keys, wrong


def problems(table, defaults):
    """What is wrong in the config's [keys], as words for its warnings: a key that isn't
    one, F1, one key given to two actions of the same kind."""
    out, taken = [], {}
    for action in ACTIONS:
        keys, wrong = read(table.get(action, defaults.get(action, "")))
        out += [f"keys.{action}: {w}" for w in wrong]
        for key in keys:
            other = taken.get(key)
            if other is not None:
                out.append(f"keys.{action}: {key.words()} is keys.{other}'s already")
            else:
                taken[key] = action
    return out


def of(cfg, action):
    """The keys of an action, as the config says ([Key], maybe none)."""
    return read(((cfg or {}).get("keys") or {}).get(action, ""))[0]


def words(cfg, action):
    """An action's keys for the help and a tooltip: "Ctrl+N", "o, Enter", ""."""
    return ", ".join(k.words() for k in of(cfg, action))


def table(cfg, actions=ACTIONS):
    """{Key: action} for the actions asked for — what a key pressed means."""
    out = {}
    for action in actions:
        for key in of(cfg, action):
            out.setdefault(key, action)
    return out


def from_gdk(name, ctrl=False, alt=False, shift=False):
    """A GTK key event (Gdk.keyval_name of its keyval, its modifiers) → Key. A letter
    typed with Shift comes as its capital: the same key, shift told apart."""
    low = str(name or "").lower()
    key = _FROM_GDK.get(low, low)
    if len(key) == 1 and not (ctrl or alt):
        shift = False  # "?" or "J" is its own character, not Shift+something
    return Key(key, ctrl, alt, shift)


def from_qt(name, ctrl=False, alt=False, shift=False):
    """A Qt key event (QKeySequence(key).toString(), its modifiers) → Key."""
    low = str(name or "").lower()
    key = _FROM_QT.get(low, low)
    if len(key) == 1 and not (ctrl or alt):
        shift = False
    return Key(key, ctrl, alt, shift)


def web_table(cfg, actions=ACTIONS):
    """For the page: [{"action", "key", "ctrl", "alt", "shift"}] — it compares a
    KeyboardEvent with each (a letter by its lower case)."""
    return [dict(key.web(), action=action) for key, action in table(cfg, actions).items()]


def hint(cfg, action):
    """An action's keys for the end of a tooltip: " (Ctrl+N)", or "" without a key."""
    said = words(cfg, action)
    return f" ({said})" if said else ""
