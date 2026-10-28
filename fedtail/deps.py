"""What fedtail needs from the system, checked before anything heavy is imported.

`fedtail --check` lists every piece — the must-haves, each interface's, the optional
ones — with what it gives, and ends with one command that installs what is missing
(apt on Debian and Ubuntu, pip elsewhere). At every start the must-haves and the
chosen interface's own pieces are checked: something missing is said in plain words
with that command, instead of a traceback (and the optional ones in one short line).

Only the standard library here: this runs when `requests` itself may be missing.
packaging/deb.py takes its Depends / Recommends / Suggests from the same table
(tests/test_deps.py holds the two together).
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

from .i18n import _


@dataclass(frozen=True)
class Need:
    key: str            # what it is called in the listing
    group: str          # "core", "qt", "gtk", "tui", "web", "extra"
    what: str           # an i18n key: what it gives
    check: object       # () -> bool
    deb: str = ""       # Debian / Ubuntu package(s), space separated
    pip: str = ""       # pip requirement(s), space separated
    level: str = "need"  # "need" (the group won't run without), "want" (a part won't)


def _module(name):
    """Is the module there? (found, not imported: cheap, and nothing runs)"""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _qt(part):
    def check():
        if not _module("PySide6"):
            return False
        return _module(f"PySide6.{part}")
    return check


def _python():
    return sys.version_info >= (3, 11)


def _sqlite_json():
    """The lanes' statistics and some rules ask SQLite for json_extract (JSON1)."""
    try:
        import sqlite3
        db = sqlite3.connect(":memory:")
        try:
            return db.execute("SELECT json_extract('{\"a\": 1}', '$.a')").fetchone() == (1,)
        finally:
            db.close()
    except Exception:  # noqa: BLE001 — no sqlite3 at all, or no JSON1 in it
        return False


def _gi_lib(namespace, version):
    """A GObject library (GTK 4, libadwaita) — asked in a child process: loading GTK
    here would sit badly with Qt in the same process."""
    def check():
        if not _module("gi"):
            return False
        code = (f"import gi; gi.require_version({namespace!r}, {version!r}); "
                f"from gi.repository import {namespace}")
        try:
            return subprocess.run([sys.executable, "-c", code], capture_output=True,
                                  timeout=20).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
    return check


def _qt_webp():
    """Qt's WebP / AVIF readers (Mastodon's pictures are often WebP): the plugin in the
    system's Qt or beside PySide6's own."""
    import glob
    places = ["/usr/lib/*/qt6/plugins/imageformats/libqwebp.so",
              "/usr/lib/qt6/plugins/imageformats/libqwebp.so"]
    spec = importlib.util.find_spec("PySide6") if _module("PySide6") else None
    if spec is not None and spec.submodule_search_locations:
        base = list(spec.submodule_search_locations)[0]
        places += [os.path.join(base, "Qt", "plugins", "imageformats", "*webp*"),
                   os.path.join(base, "plugins", "imageformats", "*webp*")]
    return any(glob.glob(p) for p in places)


def _enchant():
    if _module("enchant"):
        return True
    import ctypes.util
    return any(ctypes.util.find_library(n) for n in ("enchant-2", "enchant"))


def _emoji_font():
    """A colour emoji font: without one emoji and flags are squares."""
    import glob
    if any(glob.glob(p) for p in ("/usr/share/fonts/**/*[Cc]olor*[Ee]moji*",
                                  "/usr/share/fonts/**/*[Ee]moji*",
                                  os.path.expanduser("~/.local/share/fonts/**/*[Ee]moji*"))):
        return True
    if os.name == "nt" or sys.platform == "darwin":
        return True  # the system's own (Segoe UI Emoji, Apple Color Emoji)
    try:
        out = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "emoji" in out.lower()


def _tool(*names):
    return lambda: any(shutil.which(n) for n in names)


NEEDS = (
    # what nothing runs without
    Need("python ≥ 3.11", "core", "deps_python", _python, "python3"),
    Need("requests", "core", "deps_requests", lambda: _module("requests"),
         "python3-requests", "requests>=2.28"),
    Need("sqlite3 + JSON1", "core", "deps_sqlite", _sqlite_json, "libsqlite3-0"),
    # the window (Qt)
    Need("PySide6 (QtWidgets)", "qt", "deps_qt", _qt("QtWidgets"),
         "python3-pyside6.qtwidgets", "PySide6-Essentials>=6.5"),
    Need("PySide6 QtSvg", "qt", "deps_qt_svg", _qt("QtSvg"), "python3-pyside6.qtsvg",
         "PySide6-Essentials>=6.5", "want"),
    Need("PySide6 QtMultimedia", "qt", "deps_qt_media", _qt("QtMultimedia"),
         "python3-pyside6.qtmultimedia python3-pyside6.qtmultimediawidgets",
         "PySide6-Addons>=6.5", "want"),
    Need("PySide6 QtDBus", "qt", "deps_qt_dbus", _qt("QtDBus"), "python3-pyside6.qtdbus",
         "PySide6-Essentials>=6.5", "want"),
    Need("Qt WebP", "qt", "deps_qt_webp", _qt_webp, "qt6-image-formats-plugins", "", "want"),
    # the GTK window
    Need("PyGObject", "gtk", "deps_gi", lambda: _module("gi"), "python3-gi"),
    Need("GTK 4", "gtk", "deps_gtk", _gi_lib("Gtk", "4.0"), "gir1.2-gtk-4.0"),
    Need("libadwaita", "gtk", "deps_adw", _gi_lib("Adw", "1"), "gir1.2-adw-1", "", "want"),
    # the terminal
    Need("textual", "tui", "deps_textual", lambda: _module("textual"), "python3-textual",
         "textual>=0.86"),
    Need("Pillow", "tui", "deps_pil", lambda: _module("PIL"), "python3-pil", "Pillow>=9.1",
         "want"),
    Need("mpv", "tui", "deps_mpv", _tool("mpv"), "mpv", "", "want"),
    # whatever the interface
    Need("cryptography", "extra", "deps_crypto", lambda: _module("cryptography"),
         "python3-cryptography", "cryptography>=3.4", "want"),
    Need("langdetect", "extra", "deps_langdetect", lambda: _module("langdetect"),
         "python3-langdetect", "langdetect>=1.0.9", "want"),
    Need("Enchant", "extra", "deps_enchant", _enchant, "libenchant-2-2 hunspell-ru hunspell-en-us",
         "pyenchant", "want"),
    Need("PySocks", "extra", "deps_socks", lambda: _module("socks"), "python3-socks",
         "PySocks", "want"),
    Need("Noto Color Emoji", "extra", "deps_emoji", _emoji_font, "fonts-noto-color-emoji", "",
         "want"),
    Need("notify-send", "extra", "deps_notify", _tool("notify-send"), "libnotify-bin", "",
         "want"),
    Need("xdg-open", "extra", "deps_xdg", _tool("xdg-open"), "xdg-utils", "", "want"),
    Need("git", "extra", "deps_git", _tool("git"), "git", "", "want"),
)

GROUPS = ("core", "qt", "gtk", "tui", "extra")
GROUP_WORDS = {"core": "deps_g_core", "qt": "deps_g_qt", "gtk": "deps_g_gtk",
               "tui": "deps_g_tui", "extra": "deps_g_extra"}


def debian_like():
    """apt is the way here (Debian, Ubuntu, Mint…)."""
    return os.path.exists("/etc/debian_version") and bool(shutil.which("apt"))


def install_line(missing):
    """One command that installs these: apt where there is apt, else pip (for what pip
    has); "" — nothing to install that way."""
    if debian_like():
        pkgs = list(dict.fromkeys(p for n in missing for p in n.deb.split() if p))
        return "sudo apt install " + " ".join(pkgs) if pkgs else ""
    reqs = list(dict.fromkeys(_pinned(r) for n in missing for r in n.pip.split() if r))
    # double quotes: PowerShell and cmd take them, a POSIX shell too (cmd doesn't take '…')
    return (sys.executable.rsplit(os.sep, 1)[-1] + " -m pip install --user "
            + " ".join(f'"{r}"' for r in reqs)) if reqs else ""


def _pinned(req):
    """PySide6's parts must be one version: Addons (video, audio) is asked for at the
    version of the Essentials already installed — a newer one pulls a mismatched pair."""
    if req.startswith("PySide6-Addons"):
        try:
            from importlib.metadata import version
            return f"PySide6-Addons=={version('PySide6-Essentials')}"
        except Exception:  # noqa: BLE001 — Essentials not from pip (Debian): as it was
            return req
    return req


def missing(groups, levels=("need", "want")):
    """The pieces of these groups that aren't there."""
    return [n for n in NEEDS if n.group in groups and n.level in levels and not n.check()]


def report(out=None):
    """`fedtail --check`: every piece, ✓ or ✗ and what it gives; the command for what is
    missing. → 0 when fedtail can run (its must-haves and at least one interface)."""
    out = out or sys.stdout
    lost = []
    can = {}
    for g in GROUPS:
        print(f"\n{_(GROUP_WORDS[g])}", file=out)
        ok_needs = True
        for n in (x for x in NEEDS if x.group == g):
            there = n.check()
            if not there:
                lost.append(n)
                ok_needs = ok_needs and n.level != "need"
            mark = "✓" if there else ("✗" if n.level == "need" else "–")
            print(f"  {mark} {n.key:<24} {_(n.what)}", file=out)
        can[g] = ok_needs
    print(file=out)
    if lost:
        line = install_line(lost)
        print(_("deps_install"), file=out)
        print(f"  {line}" if line else "  " + _("deps_by_hand"), file=out)
        only_need = install_line([n for n in lost if n.level == "need"])
        if only_need and only_need != line:
            print(_("deps_install_needs"), file=out)
            print(f"  {only_need}", file=out)
    else:
        print(_("deps_all"), file=out)
    runs = [g for g in ("qt", "gtk", "tui") if can[g]] + ["web"]
    print(_("deps_runs", what=", ".join(runs)) if can["core"] else _("deps_core_missing"),
          file=out)
    return 0 if can["core"] else 3


def at_start(frontend, err=None, quiet=False):
    """At every start, before the heavy imports: the must-haves and `frontend`'s own
    pieces. Something it can't run without → said with the command, and False (the
    caller exits 3). Only the nice-to-haves missing → one short line, True."""
    err = err or sys.stderr
    if os.environ.get("FEDTAIL_NO_DEPCHECK") or getattr(sys, "frozen", False):
        return True  # the one-file build carries its own pieces
    groups = ("core", frontend) if frontend in GROUPS else ("core",)
    lost = [n for n in NEEDS if n.group in groups and n.level == "need" and not n.check()]
    if lost and quiet:
        return False
    if quiet:
        return True
    if lost:
        print("fedtail: " + _("deps_cant_start", what=", ".join(n.key for n in lost)),
              file=err)
        line = install_line(lost)
        if line:
            print("  " + line, file=err)
        print("  " + _("deps_see_check"), file=err)
        return False
    # the nice-to-haves of the chosen interface only: GTK's are checked in a child
    # process, too slow for every start — `fedtail --check` tells them
    soft = [n for n in NEEDS if n.group == frontend and n.level == "want" and
            n.group != "gtk" and not n.check()]
    if soft and _say_soft_once(soft):
        print("fedtail: " + _("deps_soft", what=", ".join(n.key for n in soft)) + " — "
              + (install_line(soft) or _("deps_see_check")), file=err)
    return True


def _say_soft_once(soft):
    """The nice-to-haves are said once for the same set of missing ones (not at every
    start): the set is kept in the user's cache folder."""
    from .core.paths import cache_base
    path = os.path.join(str(cache_base()), "deps-said")
    key = " ".join(sorted(n.key for n in soft))
    try:
        with open(path, encoding="utf-8") as f:
            if f.read().strip() == key:
                return False
    except OSError:
        pass
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(key)
    except OSError:
        pass
    return True


def deb_fields():
    """packaging/deb.py: (Depends, Recommends, Suggests) from the table — Qt's own
    must-haves are the package's Depends (the window is what it opens)."""
    def pkgs(pick):
        return list(dict.fromkeys(p for n in NEEDS if pick(n) for p in n.deb.split()
                                  if p and p not in ("python3", "libsqlite3-0")))
    depends = ["python3 (>= 3.11)"] + pkgs(lambda n: n.group in ("core", "qt") and
                                           n.level == "need")
    recommends = pkgs(lambda n: (n.group == "qt" and n.level == "want") or
                      n.group == "gtk" or n.key in ("cryptography", "langdetect"))
    suggests = [p for p in pkgs(lambda n: True) if p not in depends + recommends]
    return ", ".join(depends), ", ".join(recommends), ", ".join(suggests)
