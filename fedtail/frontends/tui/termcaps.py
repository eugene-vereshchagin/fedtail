"""What the terminal the TUI runs in can show, and which programs show it best — told
from the environment only (no escape codes asked: Textual owns the screen once it is
up). No Textual here: tested on its own, and used by tools/tui_check.py to say on the
user's machine what was found.

    caps = termcaps.detect()            # Caps(graphics="sixel", name="Konsole", …)
    termcaps.viewer(caps)               # Tool("chafa", argv-builder) or None
    termcaps.video(caps, "auto")        # ("window"|"terminal"|"browser", argv or None)

Graphics: "kitty" — the kitty graphics protocol (kitty, Ghostty); "sixel" — Konsole,
WezTerm, foot, iTerm2, VS Code, Windows Terminal, mlterm, contour; None — none known
(GNOME Terminal and the rest of VTE, a Linux console, tmux in between).
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass

SIXEL_TERMS = ("foot", "mlterm", "contour", "yaft", "wezterm")
SIXEL_PROGRAMS = ("WezTerm", "iTerm.app", "vscode", "mintty", "contour", "BlackBox")


@dataclass(frozen=True)
class Caps:
    name: str            # what the terminal is, in words ("Konsole", "kitty", "?")
    graphics: str | None  # "kitty", "sixel" or None
    display: bool        # a desktop to open a window on (mpv in its own window)
    tmux: bool = False   # inside tmux/screen: graphics pass through only if set up


def detect(env=None, platform=None):
    """The terminal from env (os.environ by default)."""
    env = os.environ if env is None else env
    platform = platform or sys.platform
    term = env.get("TERM", "")
    program = env.get("TERM_PROGRAM", "")
    tmux = bool(env.get("TMUX")) or term.startswith(("screen", "tmux"))
    if env.get("KITTY_WINDOW_ID") or term == "xterm-kitty":
        name, graphics = "kitty", "kitty"
    elif program.lower() == "ghostty" or term == "xterm-ghostty":
        name, graphics = "Ghostty", "kitty"
    elif env.get("KONSOLE_VERSION") or env.get("KONSOLE_DBUS_SESSION"):
        name, graphics = "Konsole", "sixel"
    elif env.get("WEZTERM_EXECUTABLE") or env.get("WEZTERM_PANE") or program == "WezTerm":
        name, graphics = "WezTerm", "sixel"
    elif program in SIXEL_PROGRAMS:
        name, graphics = program, "sixel"
    elif env.get("WT_SESSION"):
        name, graphics = "Windows Terminal", "sixel"
    elif term.startswith(SIXEL_TERMS):
        name, graphics = term.split("-")[0], "sixel"
    elif env.get("VTE_VERSION"):
        name, graphics = "VTE (GNOME Terminal…)", None
    elif term == "linux":
        name, graphics = "Linux console", None
    else:
        name, graphics = program or term or "?", None
    if tmux:
        graphics = None  # tmux passes them through only when told to: blocks are safe
    display = platform in ("win32", "darwin") or bool(
        env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))
    return Caps(name, graphics, display, tmux)


@dataclass(frozen=True)
class Tool:
    """A program that shows a picture in the terminal: name, its path, the graphics
    it will use."""
    name: str
    path: str
    graphics: str | None

    def argv(self, file, cols, rows):
        size = f"{max(1, cols)}x{max(1, rows)}"
        if self.name == "kitten":
            return [self.path, "icat", "--align", "left", file]
        if self.name == "chafa":
            fmt = {"kitty": "kitty", "sixel": "sixels"}.get(self.graphics or "", "symbols")
            return [self.path, "-f", fmt, "--size", size, "--animate", "off", file]
        if self.name == "timg":
            proto = {"kitty": "-pk", "sixel": "-ps"}.get(self.graphics or "", "-pq")
            return [self.path, proto, f"-g{size}", file]
        return [self.path, file]  # img2sixel


def viewer(caps, which=None):
    """The best program to show a picture whole in this terminal, or None (then the
    app's own view). kitty's own icat in kitty; chafa (it speaks sixel, kitty and
    symbols); timg; img2sixel only where sixel works."""
    which = which or shutil.which
    if caps.graphics == "kitty" and caps.name == "kitty" and which("kitten"):
        return Tool("kitten", which("kitten"), "kitty")
    for name in ("chafa", "timg"):
        path = which(name)
        if path:
            return Tool(name, path, caps.graphics)
    if caps.graphics == "sixel" and which("img2sixel"):
        return Tool("img2sixel", which("img2sixel"), "sixel")
    return None


VIDEO_MODES = ("auto", "window", "terminal", "browser")


def video(caps, mode="auto", which=None, loop=False):
    """How to play a video here: ("window", argv) — mpv in a window of its own (a
    desktop is there); ("terminal", argv) — mpv drawing into this terminal (sixel,
    kitty, or coloured text); ("browser", None) — no mpv, or asked for. The address
    goes at the end of argv."""
    which = which or shutil.which
    mpv = which("mpv")
    if mode == "browser" or not mpv:
        return "browser", None
    base = [mpv, "--really-quiet"] + (["--loop-file=inf"] if loop else [])
    if mode == "window" or (mode == "auto" and caps.display):
        return "window", base + ["--force-window=immediate"]
    vo = {"kitty": "kitty", "sixel": "sixel"}.get(caps.graphics or "", "tct")
    return "terminal", base + [f"--vo={vo}", "--terminal=yes"]


# the terminals' own notifications: an escape code the terminal turns into a desktop one
OSC_NOTIFY = {"kitty": "99", "Ghostty": "777", "WezTerm": "777", "foot": "777",
              "iTerm.app": "9"}


def notifier(caps, which=None):
    """How to tell of something new from here: ("notify-send", path) — a desktop is
    there; ("osc", "99" | "777" | "9") — the terminal shows it itself (kitty, Ghostty,
    WezTerm, foot, iTerm2; not through tmux); ("none", None)."""
    which = which or shutil.which
    if caps.display and which("notify-send"):
        return "notify-send", which("notify-send")
    code = OSC_NOTIFY.get(caps.name)
    if code and not caps.tmux:
        return "osc", code
    return "none", None


def osc(code, title, body):
    """The escape sequence that asks the terminal for a notification."""
    clean = lambda s: "".join(c for c in str(s) if c >= " " and c not in "\x7f;")  # noqa: E731
    title, body = clean(title)[:120], clean(body)[:400]
    if code == "99":  # kitty: the title, then the body, the same id
        return f"\x1b]99;i=1:d=0;{title}\x1b\\\x1b]99;i=1:p=body;{body}\x1b\\"
    if code == "777":
        return f"\x1b]777;notify;{title};{body}\x1b\\"
    return f"\x1b]9;{title}: {body}\x1b\\"


def summary(env=None, which=None, platform=None):
    """What was found, as lines (tools/tui_check.py puts them into its report)."""
    which = which or shutil.which
    caps = detect(env, platform)
    tool = viewer(caps, which)
    how, _argv = video(caps, "auto", which)
    try:
        import textual_image  # noqa: F401
        ti = "installed"
    except Exception:  # noqa: BLE001 — absent or broken: the same for us
        ti = "not installed"
    return [f"terminal: {caps.name}" + (" (inside tmux)" if caps.tmux else ""),
            f"graphics: {caps.graphics or 'none known (half blocks)'}",
            f"textual-image: {ti}",
            f"picture viewer: {tool.name if tool else 'none (the app’s own view)'}",
            f"mpv: {which('mpv') or 'not found'}; a video plays: {how}",
            f"desktop for a window: {'yes' if caps.display else 'no'}",
            f"notifications: {notifier(caps, which)[0]}"]
