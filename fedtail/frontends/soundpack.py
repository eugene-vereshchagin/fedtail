"""The sounds of a theme: which file (or desktop sound, or beep) each event makes. Plain
Python (no Qt, no GTK) — the frontends only play what this gives them.

The core names the event (core/sounds.py: "direct", "reply", "mention", "thread",
"request", "activity", "message", "online", "sent"); the theme's [sound] section says
where its sounds come from:

    "desktop"  the desktop's sound theme, by freedesktop names (message-new-instant…),
               played with canberra-gtk-play; without it, fedtail's quiet fallback set —
               the "system" and "debug" themes;
    "own"      the theme's own set: themes/<theme>/sounds/<event>.wav, a file an event —
               the messengers (qip-retro, mra, psi);
    "bell"     the terminal's (or the toolkit's) beep — terminal, bnw;
    "none"     silence.

What an own set lacks comes from the themes it inherits (their folders), then from
[sound] from = a theme whose set it borrows, then from a lighter event of the same set
(STANDS_IN: a reply sounds like a mention, a mention like a message); "online" and "sent"
stand in for nothing — a set without them is silent there. fedtail's own sets are made
by tools/make_sounds.py (synthesised, GPL like the rest).

sound.scheme in the config may take another theme's sounds whatever the look.
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass
from pathlib import Path

from . import themefile

log = logging.getLogger(__name__)

FALLBACK_DIR = Path(__file__).resolve().parent.parent / "data" / "sounds" / "fallback"
SOURCES = ("desktop", "own", "bell", "none")
# Windows plays only .wav by itself: a set's .wav wins over the others
EXTS = (".wav", ".ogg", ".oga", ".flac", ".mp3")
EVENTS = {
    "direct": "a private message (lane direct)",
    "reply": "a reply to me (lane replies)",
    "mention": "a mention (lane mentions)",
    "thread": "news in a followed thread (lane subs)",
    "request": "a follow request",
    "activity": "a like, a boost, a follow (lane activity)",
    "message": "news in any other lane (home, lists, bots…)",
    "online": "connected to the server",
    "sent": "a post has gone out",
}
# a lighter event of the same set stands in for one the set lacks
STANDS_IN = {"direct": "mention", "reply": "mention", "mention": "message",
             "thread": "message", "request": "activity", "activity": "message"}
# "desktop": the freedesktop sound naming spec's names (None: the desktop is silent there)
FREEDESKTOP = {
    "direct": "message-new-instant", "reply": "message-new-instant",
    "mention": "message-new-instant", "thread": "message-new-instant",
    "message": "message-new-instant", "request": "dialog-information",
    "activity": "dialog-information", "online": None, "sent": None,
}


@dataclass(frozen=True)
class Sound:
    """One sound to play.

    Attributes:
        kind: "file" (value: a path), "desktop" (value: a freedesktop name, file: the
            fallback file to play when the desktop can't) or "bell".
        value: the path or the name.
        event: what it sounds for.
        file: for "desktop", a file of fedtail's own to play instead.
    """
    kind: str
    value: str
    event: str
    file: str = ""


def _find_in(dirs, event):
    for d in dirs:
        for ext in EXTS:
            p = Path(d) / f"{event}{ext}"
            if p.is_file():
                return str(p)
    return ""


@dataclass(frozen=True)
class Scheme:
    """A theme's sounds: where from, and the folders of its own set (own first)."""
    theme: str
    source: str
    dirs: tuple = ()

    def find(self, event):
        """The Sound for an event, or None (silence)."""
        if event not in EVENTS or self.source == "none":
            return None
        if self.source == "bell":
            return Sound("bell", "", event)
        if self.source == "desktop":
            name = FREEDESKTOP.get(event)
            if not name:
                return None
            return Sound("desktop", name, event, file=self.file_for(event, (str(FALLBACK_DIR),)))
        path = self.file_for(event, self.dirs)
        return Sound("file", path, event) if path else None

    @staticmethod
    def file_for(event, dirs):
        seen = set()
        while event and event not in seen:
            seen.add(event)
            path = _find_in(dirs, event)
            if path:
                return path
            event = STANDS_IN.get(event)
        return ""

    def missing(self):
        """Events an own set has no file for, even through STANDS_IN (for the log)."""
        if self.source != "own":
            return []
        return [e for e in EVENTS if not self.file_for(e, self.dirs)]


def sound_dirs(theme):
    """The folders of a theme's own sounds, from a loaded theme dict."""
    return tuple(theme.get("sound_dirs") or ())


@functools.lru_cache(maxsize=16)
def _scheme_of(name):
    try:
        theme, _w = themefile.load(name)
    except themefile.ThemeError as e:
        log.warning("sounds: theme %r: %s", name, e)
        return Scheme(name, "none")
    src = (theme.get("sound") or {}).get("source") or "desktop"
    scheme = Scheme(name, src if src in SOURCES else "desktop", sound_dirs(theme))
    lacking = scheme.missing()
    if lacking:
        log.info("sounds: theme %s has no %s (silent there)", name, ", ".join(lacking))
    return scheme


def scheme(theme_id, cfg=None):
    """The Scheme to sound with: sound.scheme's ("theme" — this theme's; a theme's name
    — that one's; "none" — silence), and none at all with sound.enabled = false."""
    s = (cfg or {}).get("sound") or {}
    if s and not s.get("enabled", True):
        return Scheme(theme_id or "", "none")
    want = s.get("scheme", "theme") if s else "theme"
    if want == "none":
        return Scheme(theme_id or "", "none")
    return _scheme_of(theme_id if want in ("", "theme") else want)


def forget():
    """Read the theme files again (a theme changed, or another one applied)."""
    _scheme_of.cache_clear()
