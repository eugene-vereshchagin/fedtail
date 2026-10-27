"""The settings window, without a toolkit: what it shows and what saving does. Qt and
GTK draw it as a window (chapters on the left, options on the right), the web page and
the terminal as a place (common/places.py, "settings").

The config file stays the one place the settings live. Everything here is read from it
and from the reference next to it (config.example.<lang>.toml: the chapters, the
explanations, what each choice means); saving writes the changed lines back into it
(core/config_edit.py) and nowhere else. Most options are read once, at start: the
window says so and offers to restart.

    chapters = settings.model(view)            # [Chapter(title, [Option…])]
    o = chapters[0].options[0]                 # o.section, o.key, o.kind, o.value…
    settings.save(view, {("ui", "theme"): "paper"})
    settings.save(view, {("ui", "theme"): settings.UNSET})   # the default again
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field

from ...core import config
from ...core.config_edit import UNSET, SaveError, is_set
from ...i18n import _

# list options whose items come from a known set: shown as ticks, not a line to type
_LANE_LISTS = set(config.LANE_LISTS)
_ITEMS = {("activity", "types"): config.ACTIVITY_TYPES, ("subs", "auto"): config.SUBS_AUTO}
_LANE_CHOICE = {("ui", "start_lane")}
# arrays of tables ([[lanes.custom]], [[lanes.tag_groups]]): no line to type them in — a
# list's field would show them as text and write them back broken; the file is their place
TABLES = {("lanes", "custom"), ("lanes", "tag_groups")}


@dataclass
class Option:
    """One option. kind: "bool", "int", "text", "choice" (choices: [(value, words)]),
    "checks" (a list of choices: value is a list), "list" (a list typed as a line)."""
    section: str
    key: str
    kind: str
    value: object
    default: object
    title: str = ""
    about: str = ""                  # the explanation, without the lines about choices
    choices: list = field(default_factory=list)
    minimum: int | None = None
    in_file: bool = False            # set in the file (not left to the default)
    group: str = ""                  # the sub-heading of the reference it is under

    @property
    def changed(self):
        """Set in the file to something other than the default."""
        return self.in_file and self.value != self.default

    @property
    def name(self):
        return f"{self.section}.{self.key}"

    def words_of(self, value):
        return next((w for v, w in self.choices if v == value), str(value))

    def matches(self, query):
        q = query.strip().lower()
        return not q or any(q in s.lower() for s in (self.name, self.title, self.about))

    def parse(self, text):
        """What a typed line means for this option: a value, or ValueError."""
        if self.kind == "int":
            try:
                v = int(str(text).strip())
            except ValueError:
                raise ValueError(_("settings_need_number")) from None
            if self.minimum is not None and v < self.minimum:
                raise ValueError(_("settings_at_least", n=self.minimum))
            return v
        if self.kind in ("list", "checks"):
            if isinstance(text, (list, tuple)):
                return list(text)
            return [x.strip().strip('"') for x in str(text).split(",") if x.strip()]
        if self.kind == "bool":
            if isinstance(text, bool):
                return text
            return str(text).strip().lower() in ("1", "true", "on", "yes", "да")
        return str(text)

    def shown(self, value=None):
        """The value as a line: what a field to type in starts with."""
        value = self.value if value is None else value
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, list):
            return ", ".join(str(x) for x in value) or "—"
        return str(value) if value != "" else '""'

    def line(self):
        """The value as a field to type in holds it (a list: items with commas)."""
        if isinstance(self.value, list):
            return ", ".join(str(x) for x in self.value)
        return str(self.value)

    def default_shown(self):
        return self.shown(self.default)


@dataclass
class Chapter:
    number: int
    title: str
    sections: list = field(default_factory=list)
    options: list = field(default_factory=list)

    @property
    def key(self):
        return self.sections[0] if self.sections else str(self.number)


_BANNER = re.compile(r"^#\s+(\d+)\.\s+(.+?)\s*$")
_RULE = re.compile(r"^#\s*══")
_SUB = re.compile(r"^#\s*──\s*(.+?)\s*─+\s*$")
_HEAD = re.compile(r"^\[([A-Za-z0-9_]+)\]\s*$")
_OPT = re.compile(r"^#?\s*([A-Za-z0-9_]+)\s*=")
_CHOICE = re.compile(r'^\s{0,6}((?:"[^"]*",?\s*)+)—\s*(.*)$')


def _doc(lines):
    """The comment lines as text: "# " off, ordinary lines run together into
    paragraphs, indented ones (lists, examples) kept as they are."""
    out = []
    for raw in lines:
        t = raw.lstrip()
        t = t[1:] if t.startswith("#") else t
        t = t[1:] if t.startswith(" ") else t
        if out and t and not t[0].isspace() and out[-1] and \
                not out[-1].endswith((":", ".")) and not t.startswith(("-", "*", '"')):
            out[-1] += " " + t
        else:
            out.append(t)
    return "\n".join(out).strip()


def _choices_in(lines):
    """[(value, words)] the explanation gives for the choices (`"value" — words`, or
    several values sharing the words), and the explanation without those lines."""
    found, rest, words = [], [], None
    for raw in lines:
        t = raw.lstrip()[1:] if raw.lstrip().startswith("#") else raw
        m = _CHOICE.match(t)
        if m:
            words = [m.group(2).strip()]
            found += [(v, words) for v in re.findall(r'"([^"]*)"', m.group(1))]
            continue
        if words is not None and t.startswith("     ") and t.strip():
            words[0] += " " + t.strip()  # the choice's words go on
            continue
        words = None
        rest.append(raw)
    return [(v, w[0].rstrip(";.").strip()) for v, w in found], rest


_IF = re.compile(r'^(При|With|If|When)\s+[\w.]+\s*=\s*"[^"]*"\s*(—|:|,)\s*', re.I)


def _title(about, key):
    """A short name for the option: the first words of its explanation."""
    first = _IF.sub("", about.split("\n", 1)[0]).strip()
    cuts = [i for i in (first.find(s) for s in (" — ", ": ", ". ", " (", "; ")) if i > 0]
    if first.endswith((":", ".")):
        cuts.append(len(first) - 1)
    if cuts:
        first = first[:min(cuts)]
    if len(first) > 48 and ", " in first[12:]:
        first = first[:12 + first[12:].index(", ")]
    if len(first) > 64:
        first = first[:60].rsplit(" ", 1)[0] + "…"
    first = first.strip().rstrip(".:,")
    if not first:
        return key.replace("_", " ")
    return first[0].upper() + first[1:]


def reference(lang):
    """[(chapter number, title, section, group, key, comment lines)] in file order."""
    out, chapter, title, section, group, pending = [], 0, "", None, "", []
    lines = config.example_text(lang).splitlines()
    for i, line in enumerate(lines):
        m = _BANNER.match(line)
        if m and i > 0 and _RULE.match(lines[i - 1]):
            chapter, title, pending = int(m.group(1)), m.group(2), []
            continue
        if _RULE.match(line):
            pending = []
            continue
        m = _HEAD.match(line)
        if m:
            section, group, pending = m.group(1), "", []
            continue
        if section is None:
            continue
        m = _SUB.match(line)
        if m:
            group, pending = m.group(1), []
            continue
        m = _OPT.match(line)
        if m and not line.startswith("# "):
            out.append((chapter, title, section, group, m.group(1), pending))
            pending = []
        elif line.startswith("#"):
            pending.append(line)
        else:
            pending = []
    return out


def _lane_words(view):
    """A lane's name in words: the interface's own for the standard ones, the view's
    for the rest (a list, a lane of tags), else the name itself."""
    title = getattr(view, "lane_title", None)

    def words(name):
        own = _("lane_" + name)
        if own != "lane_" + name:
            return own
        try:
            got = title(name) if title else None
        except Exception:  # noqa: BLE001 — a name the core doesn't know: as it is
            got = None
        return got or name
    return words


def _theme_names():
    from .. import themefile
    try:
        return list(themefile.available())
    except Exception:  # noqa: BLE001
        return []


def config_file(view):
    """The file the settings live in: the profile's config.toml (-c's file, if given);
    with every account in one window, the main profile's."""
    core = getattr(view, "_core", view)
    core = getattr(core, "primary", core)
    paths = getattr(core, "paths", None) or view.paths
    return paths.config_file


def user_text(view):
    path = config_file(view)
    try:
        return path.read_text("utf-8")
    except FileNotFoundError:
        return ""


def model(view, lang=None, text=None):
    """[Chapter] of every option the reference has, with the values of the file."""
    from ...i18n import current_language as current
    text = user_text(view) if text is None else text
    lang = lang or (current() if current() in config.EXAMPLE_LANGS else "en")
    try:
        cfg, _w = config.validate(tomllib.loads(text))
    except (tomllib.TOMLDecodeError, config.ConfigError):
        cfg = config.DEFAULTS  # a broken file: the window still shows the defaults
    lane = _lane_words(view)
    chapters = {}
    for number, title, section, group, key, lines in reference(lang):
        if section not in config.DEFAULTS or key not in config.DEFAULTS[section] or \
                (section, key) in TABLES:
            continue
        default = config.DEFAULTS[section][key]
        value = cfg.get(section, {}).get(key, default)
        listed, rest = _choices_in(lines)
        about = _doc(rest)
        o = Option(section, key, "text", value, default, title=_title(about, key),
                   about=about, in_file=is_set(text, section, key), group=group,
                   minimum=config.MINIMUM.get((section, key)))
        known = config.CHOICES.get((section, key))
        if isinstance(default, bool):
            o.kind = "bool"
        elif isinstance(default, int):
            o.kind = "int"
        elif isinstance(default, list):
            items = None
            if (section, key) in _LANE_LISTS:
                items = sorted(config.LANE_NAMES)
            elif (section, key) in _ITEMS:
                items = sorted(_ITEMS[(section, key)])
            if items is not None:
                o.kind = "checks"
                words = dict(listed)
                o.choices = [(v, words.get(v) or (lane(v) if (section, key) in _LANE_LISTS
                                                  else v)) for v in items]
                o.choices += [(v, v) for v in value if v not in items]  # lists, tags…
            else:
                o.kind = "list"
        elif known or (section, key) in _LANE_CHOICE or (section, key) == ("ui", "theme"):
            o.kind = "choice"
            words = dict(listed)
            if (section, key) == ("ui", "theme"):
                values = _theme_names()
            elif (section, key) in _LANE_CHOICE:
                values = sorted(config.LANE_NAMES)
            else:
                # in the reference's order where it gives one, then the rest
                values = [v for v, _w in listed if v in known] + \
                    sorted(v for v in known if v not in words)
            for v in [*values, value, default]:
                if v not in [c for c, _w in o.choices]:
                    o.choices.append((v, words.get(v) or (lane(v) if (section, key)
                                                          in _LANE_CHOICE else v)))
        ch = chapters.get(number)
        if ch is None:
            ch = chapters[number] = Chapter(number, title)
        if section not in ch.sections:
            ch.sections.append(section)
            if len(ch.sections) > 1 and not group:
                o.group = f"[{section}]"
        ch.options.append(o)
    return [chapters[n] for n in sorted(chapters)]


def find(chapters, query):
    """[(chapter, [options matching])] with at least one match."""
    out = []
    for ch in chapters:
        hits = [o for o in ch.options if o.matches(query)]
        if hits:
            out.append((ch, hits))
    return out


def option(chapters, name):
    return next((o for ch in chapters for o in ch.options if o.name == name), None)


def save(view, changes):
    """Write the changes {(section, key): value or UNSET} into the file. Returns the
    words to show ("Saved in …: restart for it to take effect"); SaveError (its words
    are for the person) if the file would come out wrong — it stays as it was then."""
    from ...core import config_edit
    if not changes:
        return ""
    path = config_file(view)
    _cfg, warnings = config_edit.save(path, changes)
    names = ", ".join(f"{s}.{k}" for s, k in changes)
    words = _("settings_saved", names=names, file=path.name) + " · " + _("settings_after_restart")
    if warnings:
        words += " · " + "; ".join(warnings[:2])
    return words


def changes_of(chapters, values):
    """{(section, key): value} of the options whose typed/ticked value differs from
    the file's: values is {"section.key": what the form holds}. ValueError (with the
    option's name) for what doesn't read."""
    out = {}
    for name, raw in values.items():
        o = option(chapters, name)
        if o is None:
            continue
        try:
            v = o.parse(raw)
        except ValueError as e:
            raise ValueError(f"{o.title} ({o.name}): {e}") from None
        if v != o.value:
            out[(o.section, o.key)] = v
    return out


__all__ = ["UNSET", "Chapter", "Option", "SaveError", "changes_of", "config_file", "find",
           "model",
           "option", "reference", "save", "user_text"]
