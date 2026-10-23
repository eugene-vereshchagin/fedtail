"""Playing the theme's sounds: one way for every window (Qt, GTK, the terminal). No toolkit.

The core emits ``sound`` with an event (core/sounds.py); the frontend asks
:class:`Sounds` to play it. Sounds looks the event up in the theme's scheme
(frontends/soundpack.py) and plays the file with a program of the system, in a thread
of its own, never two at once:

* Linux: ``pw-play`` (PipeWire), ``paplay`` (PulseAudio), ``aplay`` (ALSA) — the first
  found; a desktop sound (the "desktop" source) with ``canberra-gtk-play``, or
  fedtail's own quiet set when there is none;
* macOS: ``afplay``; Windows: ``winsound`` (WAV only — fedtail's sets are WAV);
* ``sound.player`` = a command of your own, ``{file}`` the path.

A "bell" sound (the terminal and bnw themes) is the frontend's own beep: Sounds calls
the ``bell`` it was given. Nothing to play with — silence, said once in the log.
"""

from __future__ import annotations

import logging
import shlex
import shutil
import subprocess
import sys
import threading

from ... import sysenv
from .. import soundpack

log = logging.getLogger(__name__)

# (program, how it takes the volume 0..100: None — it can't)
LINUX_PLAYERS = (
    # a notification, not music: the desktop's own volume for event sounds governs it,
    # and the sound server treats it as an event (not as a player that wants the card)
    ("pw-play", lambda v: ["--media-role=Notification", f"--volume={v / 100:.2f}"]),
    ("paplay", lambda v: ["--property=media.role=event", f"--volume={int(65536 * v / 100)}"]),
    ("aplay", None),
)
MAC_PLAYER = ("afplay", lambda v: ["-v", f"{v / 100:.2f}"])
CANBERRA = "canberra-gtk-play"
# FEDTAIL_SOUND=off: nothing reaches the speakers, whatever sound.enabled says — the
# tests and the dev tools set it (a self-check played hundreds of chimes and beeps
# through the desktop's sound server; on 23.10 the microphone went with them)
SILENT_ENV = "FEDTAIL_SOUND"


def silenced():
    import os
    return os.environ.get(SILENT_ENV, "").strip().lower() in ("off", "0", "no", "silent")
TIMEOUT = 15  # seconds a player may take before it's left behind


class Player:
    """Turns a soundpack.Sound into a command and runs it, one at a time.

    Args:
        cfg: the config dict (``sound.player``, ``sound.volume``).
        which: shutil.which (tests pass their own).
        platform: sys.platform.
        run: runs an argv and waits (tests pass their own).
    """

    def __init__(self, cfg, which=shutil.which, platform=sys.platform, run=None):
        self.cfg = cfg
        self.which = which
        self.platform = platform
        self._run = run or self._subprocess
        self._busy = threading.Lock()
        self._said = set()

    @property
    def volume(self):
        return max(0, min(100, int((self.cfg.get("sound") or {}).get("volume", 80))))

    def _say_once(self, what):
        if what not in self._said:
            self._said.add(what)
            log.info("sound: %s", what)

    def command(self, snd):
        """The argv that plays it, "winsound:<path>" on Windows, or None (can't)."""
        if snd is None or snd.kind == "bell":
            return None
        own = ((self.cfg.get("sound") or {}).get("player") or "auto").strip()
        if snd.kind == "desktop":
            exe = self.which(CANBERRA) if own == "auto" and \
                self.platform.startswith("linux") else None
            if exe:
                return [exe, "-i", snd.value, "-d", "fedtail"]
            path = snd.file  # no desktop sound theme player: our own quiet set
        else:
            path = snd.value
        if not path:
            return None
        if own != "auto":
            argv = shlex.split(own)
            if not argv:
                return None
            return [a.replace("{file}", path) for a in argv] if any(
                "{file}" in a for a in argv) else argv + [path]
        if self.platform.startswith("win"):
            return ["winsound:" + path] if path.lower().endswith(".wav") else None
        players = (MAC_PLAYER,) if self.platform == "darwin" else LINUX_PLAYERS
        for name, vol in players:
            exe = self.which(name)
            if exe:
                return [exe] + (vol(self.volume) if vol else []) + [path]
        self._say_once("no player found (pw-play, paplay, aplay): silent; "
                       "sound.player names one")
        return None

    def play(self, snd):
        """Play in the background. False: nothing to play it with, or busy already."""
        argv = self.command(snd)
        if not argv:
            return False
        if not self._busy.acquire(blocking=False):
            return False  # one at a time: a second chime would only muddle the first

        def go():
            try:
                self._run(argv)
            except Exception as e:  # a sound is never worth an error on screen
                self._say_once(f"{argv[0]}: {e}")
            finally:
                self._busy.release()
        threading.Thread(target=go, name="fedtail-sound", daemon=True).start()
        return True

    @staticmethod
    def _subprocess(argv):
        if silenced():
            return
        if argv[0].startswith("winsound:"):
            import winsound  # noqa: PLC0415 — Windows only
            winsound.PlaySound(argv[0][len("winsound:"):], winsound.SND_FILENAME)
            return
        subprocess.run(argv, env=sysenv.child_env(), stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=TIMEOUT, check=False)


class Sounds:
    """What a window keeps: the scheme of its theme and the player.

    Args:
        cfg: the config dict.
        theme_id: the theme whose sounds play (sound.scheme may name another).
        bell: the frontend's beep, for "bell" sounds (None: silent there).
        player: a Player (tests pass their own).
        only_bell: whatever the theme says, beep (the terminal's tui.sound = "bell": a
            terminal over ssh has no speakers of its own but the bell).
    """

    def __init__(self, cfg, theme_id, bell=None, player=None, only_bell=False):
        self.cfg = cfg
        self.bell = bell
        self.only_bell = only_bell
        self.player = player or Player(cfg)
        self.scheme = self._scheme(theme_id)
        self.played = []  # the last events played: tests and the debug log read it

    def _scheme(self, theme_id):
        sch = soundpack.scheme(theme_id, self.cfg)
        if self.only_bell and sch.source != "none":
            return soundpack.Scheme(sch.theme, "bell")
        return sch

    def set_theme(self, theme_id):
        """The theme changed (or was tried for a while): its sounds from now on."""
        soundpack.forget()
        self.scheme = self._scheme(theme_id)

    def wanted(self, focused):
        from ...core.sounds import enabled
        s = self.cfg.get("sound") or {}
        return enabled(self.cfg) and (not focused or s.get("when_focused", True))

    def play(self, event, focused=False):
        """Play the sound of a core event. Returns what was done: "file", "desktop",
        "bell", or "" (nothing)."""
        if not self.wanted(focused):
            return ""
        snd = self.scheme.find(event)
        if snd is None:
            return ""
        if snd.kind == "bell":
            if self.bell is None:
                return ""
            try:
                if not silenced():
                    self.bell()
            except Exception as e:  # noqa: BLE001 — a beep is never worth more
                log.debug("sound: bell: %s", e)
                return ""
            self._note(event)
            return "bell"
        if self.player.play(snd):
            self._note(event)
            return snd.kind
        return ""

    def test(self, event="reply"):
        """≡ → Debug → Test the sound: the words for the status line."""
        from ...i18n import _
        how = self.play(event, focused=False)
        if how:
            return _("debug_sound_played", event=event, theme=self.scheme.theme, how=how)
        return _("debug_sound_silent", event=event, theme=self.scheme.theme)

    def _note(self, event):
        self.played = (self.played + [event])[-20:]
        log.debug("sound: played %s (%s)", event, self.scheme.theme)
