"""The menu entry and the icon in ~/.local/share, so the desktop shows fedtail with its
own icon in the launcher, the task bar and in notifications: made by `--install-desktop`
and checked at every start of a window (`ensure`, ui.desktop_entry), which also takes
away entries of the old name (fedtail.desktop, before the app had an id)."""

import logging
import os
import re
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

from .core.paths import main_profile
from .version import APP_ID

log = logging.getLogger(__name__)


def _data_home():
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def entry_text(profile=None, source_dir=None, icon="fedtail"):
    """The .desktop file. From a git checkout it runs `python3 -m fedtail` there.

    icon is best a full path: KWin and the task manager take the icon of a window
    from its .desktop entry, and a bare name has to be found in the icon theme —
    which Plasma caches, so a freshly installed one often shows as a blank page."""
    profile = profile or main_profile()
    args = "" if profile == main_profile() else f" --profile {profile}"
    if getattr(sys, "frozen", False):  # the one-file build: the file itself
        exec_line = f'"{sys.executable}"{args}'
        path_line = ""
    elif source_dir:
        exec_line = f"{sys.executable} -m fedtail{args}"
        path_line = f"Path={source_dir}\n"
    else:
        exec_line = f"fedtail{args}"
        path_line = ""
    name = "fedtail" if profile == main_profile() else f"fedtail ({profile})"
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name}\n"
        "GenericName=Fediverse client\n"
        "GenericName[ru]=Клиент федиверса\n"
        "Comment=Read and write to GoToSocial, Mastodon and the rest of the fediverse\n"
        "Comment[ru]=Читать и писать в GoToSocial, Mastodon и весь федиверс\n"
        f"Exec={exec_line}\n"
        f"{path_line}"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=Network;Chat;InstantMessaging;Qt;\n"
        "Keywords=mastodon;gotosocial;fediverse;point;juick;bnw;\n"
        "StartupWMClass=fedtail\n"
        "StartupNotify=true\n"
    )


def handler_text(entry):
    """The desktop entry for web+ap:// links: the same fedtail, `open %u`, not in the
    menu."""
    out = []
    for line in entry.splitlines():
        if line.startswith("Exec="):
            line += " open %u"
        elif line.startswith("Name="):
            line += " (links)"
        out.append(line)
    out += ["NoDisplay=true", "MimeType=x-scheme-handler/web+ap;"]
    return "\n".join(out) + "\n"


def desktop_id(profile=None):
    """The .desktop file's name without .desktop — the app's id (version.APP_ID), and
    for a profile other than the main one that id plus the profile, so each profile's
    window finds its own entry, icon and unread count on the task bar. Always a valid
    GApplication id: dot-separated parts of letters, digits, _ and -, none starting with
    a digit."""
    profile = profile or main_profile()
    if profile == main_profile():
        return APP_ID
    part = re.sub(r"[^A-Za-z0-9_-]", "_", profile)
    if not part or part[0].isdigit() or part[0] == "-":
        part = "p" + part
    return f"{APP_ID}.{part}"


def old_ids(profile=None):
    """What the entry was called before the app had an id."""
    profile = profile or main_profile()
    stem = "fedtail" if profile == main_profile() else f"fedtail-{profile}"
    return [stem, f"{stem}-open"]


def source_dir():
    """The checkout this code runs from, or None when installed as a package."""
    root = Path(__file__).resolve().parent.parent
    return root if (root / "pyproject.toml").exists() else None


def _windows_install(profile):
    """A Start menu shortcut (a .lnk, made by PowerShell's WScript.Shell). Its name is
    the one people see in the menu: "fedtail", "fedtail-<profile>" — not the app id."""
    stem = old_ids(profile)[0]
    menu = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming") / \
        "Microsoft/Windows/Start Menu/Programs"
    menu.mkdir(parents=True, exist_ok=True)
    link = menu / f"{stem}.lnk"
    args = "" if profile == main_profile() else f"--profile {profile}"
    if getattr(sys, "frozen", False):  # fedtail.exe from the zip
        target, workdir, icon = sys.executable, str(Path(sys.executable).parent), sys.executable
    else:  # from the source: pythonw — no console window
        pyw = Path(sys.executable).with_name("pythonw.exe")
        target = str(pyw if pyw.exists() else sys.executable)
        args = ("-m fedtail " + args).strip()
        workdir = str(source_dir() or Path.cwd())
        icon = target
    q = lambda s: "'" + str(s).replace("'", "''") + "'"  # noqa: E731 — PowerShell quoting
    script = (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({q(link)}); "
              f"$s.TargetPath = {q(target)}; $s.Arguments = {q(args)}; "
              f"$s.WorkingDirectory = {q(workdir)}; $s.IconLocation = {q(icon)}; "
              f"$s.Description = 'fediverse client'; $s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                   check=True, capture_output=True)
    return link, Path(icon)


def _files(profile):
    """{path: bytes} of what the menu entry is made of here."""
    data = _data_home()
    apps = data / "applications"
    icon = data / "icons" / "hicolor" / "512x512" / "apps" / "fedtail.png"
    stem = desktop_id(profile)
    text = entry_text(profile, source_dir(), icon=str(icon))
    icon_src = resources.files("fedtail").joinpath("data/icons/fedtail.png")
    return {apps / f"{stem}.desktop": text.encode(),
            apps / f"{stem}-open.desktop": handler_text(text).encode(),
            icon: icon_src.read_bytes()}


def _ours(path):
    """An entry fedtail made (not one of the same name someone wrote by hand)."""
    try:
        text = path.read_text("utf-8", errors="replace")
    except OSError:
        return False
    return "Keywords=mastodon;gotosocial;fediverse" in text and "fedtail" in text


def _remove_old(profile):
    apps = _data_home() / "applications"
    gone = []
    for stem in old_ids(profile):
        p = apps / f"{stem}.desktop"
        if p.is_file() and _ours(p):
            p.unlink()
            gone.append(p)
    return gone


def install(profile=None):
    profile = profile or main_profile()
    if os.name == "nt":
        return _windows_install(profile)
    files = _files(profile)
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    data = _data_home()
    # the opossum holding its own tail (the bubble of before goes: one icon by that name)
    (data / "icons" / "hicolor" / "scalable" / "apps" / "fedtail.svg").unlink(missing_ok=True)
    _remove_old(profile)
    entry, opener, icon = list(files)
    # web+ap:// links (a "open in your app" button on a server's page) and
    # `xdg-open web+ap://…` go to `fedtail open URL`: into the running window
    from . import sysenv
    if shutil.which("xdg-mime"):
        subprocess.run(["xdg-mime", "default", opener.name, "x-scheme-handler/web+ap"],
                       capture_output=True, env=sysenv.child_env())
    # let the desktop notice right away (best effort)
    apps = entry.parent
    for cmd in (["update-desktop-database", str(apps)],
                ["gtk-update-icon-cache", "-q", "-t", str(data / "icons" / "hicolor")],
                ["kbuildsycoca6"], ["kbuildsycoca5"]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, capture_output=True, env=sysenv.child_env())
    return entry, icon


def system_entry():
    """The entry a package put in /usr/share/applications (the deb), or None."""
    for base in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"):
        p = Path(base or "/usr/share") / "applications" / f"{APP_ID}.desktop"
        if p.is_file():
            return p
    return None


def ensure(profile=None):
    """At the start of a window (ui.desktop_entry): the menu entry and the icon are there
    and say what this fedtail is (moved checkout, new one-file build, a renamed id);
    entries of the old name go. Writes only when something differs, so an ordinary start
    costs a few small reads. Linux and the like only; never raises. What it did, or
    None when nothing was needed."""
    if os.name == "nt" or sys.platform == "darwin":
        return None
    profile = profile or main_profile()
    try:
        installed = not getattr(sys, "frozen", False) and source_dir() is None
        if installed and system_entry() is not None and profile == main_profile():
            # the package's own entry serves; one of ours beside it would be a duplicate
            gone = _remove_old(profile) + _remove_own(profile)
            return f"package entry kept, removed {len(gone)}" if gone else None
        files = _files(profile)
        stale = [p for p, c in files.items() if not p.is_file() or p.read_bytes() != c]
        old = [p for stem in old_ids(profile)
               if (p := _data_home() / "applications" / f"{stem}.desktop").is_file()
               and _ours(p)]
        if not stale and not old:
            return None
        entry, _icon = install(profile)
        return f"menu entry {entry} (was: {', '.join(p.name for p in stale + old)})"
    except Exception as e:  # noqa: BLE001 — a menu entry must never stop the start
        log.warning("menu entry: %s", e)
        return None


def _remove_own(profile):
    """Our user-level menu entry, when a package's is there for the same id (the
    web+ap:// link handler stays: the package has none)."""
    p = _data_home() / "applications" / f"{desktop_id(profile)}.desktop"
    if p.is_file() and _ours(p):
        p.unlink()
        return [p]
    return []
