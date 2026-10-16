"""`--install-desktop`: a menu entry and the icon in ~/.local/share, so KDE shows
fedtail with its own icon in the launcher, the task bar and in notifications."""

import os
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

from .core.paths import DEFAULT_PROFILE


def _data_home():
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def entry_text(profile=DEFAULT_PROFILE, source_dir=None, icon="fedtail"):
    """The .desktop file. From a git checkout it runs `python3 -m fedtail` there.

    icon is best a full path: KWin and the task manager take the icon of a window
    from its .desktop entry, and a bare name has to be found in the icon theme —
    which Plasma caches, so a freshly installed one often shows as a blank page."""
    args = "" if profile == DEFAULT_PROFILE else f" --profile {profile}"
    if getattr(sys, "frozen", False):  # the one-file build: the file itself
        exec_line = f'"{sys.executable}"{args}'
        path_line = ""
    elif source_dir:
        exec_line = f"{sys.executable} -m fedtail{args}"
        path_line = f"Path={source_dir}\n"
    else:
        exec_line = f"fedtail{args}"
        path_line = ""
    name = "fedtail" if profile == DEFAULT_PROFILE else f"fedtail ({profile})"
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
        "Keywords=mastodon;gotosocial;fediverse;point;juick;\n"
        "StartupWMClass=fedtail\n"
        "StartupNotify=true\n"
    )


def desktop_id(profile=DEFAULT_PROFILE):
    """The .desktop file's name without .desktop: what the window says it is, so
    the task bar finds its icon and the unread count lands on the right button."""
    return "fedtail" if profile == DEFAULT_PROFILE else f"fedtail-{profile}"


def source_dir():
    """The checkout this code runs from, or None when installed as a package."""
    root = Path(__file__).resolve().parent.parent
    return root if (root / "pyproject.toml").exists() else None


def _windows_install(profile):
    """A Start menu shortcut (a .lnk, made by PowerShell's WScript.Shell)."""
    stem = desktop_id(profile)
    menu = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming") / \
        "Microsoft/Windows/Start Menu/Programs"
    menu.mkdir(parents=True, exist_ok=True)
    link = menu / f"{stem}.lnk"
    args = "" if profile == DEFAULT_PROFILE else f"--profile {profile}"
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


def install(profile=DEFAULT_PROFILE):
    if os.name == "nt":
        return _windows_install(profile)
    data = _data_home()
    apps = data / "applications"
    icons = data / "icons" / "hicolor" / "scalable" / "apps"
    apps.mkdir(parents=True, exist_ok=True)
    icons.mkdir(parents=True, exist_ok=True)
    icon_src = resources.files("fedtail").joinpath("data/icons/fedtail.svg")
    (icons / "fedtail.svg").write_bytes(icon_src.read_bytes())
    stem = desktop_id(profile)
    entry = apps / f"{stem}.desktop"
    entry.write_text(entry_text(profile, source_dir(), icon=str(icons / "fedtail.svg")),
                     "utf-8")
    # let the desktop notice right away (best effort)
    for cmd in (["update-desktop-database", str(apps)],
                ["gtk-update-icon-cache", "-q", "-t", str(data / "icons" / "hicolor")],
                ["kbuildsycoca6"], ["kbuildsycoca5"]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, capture_output=True)
    return entry, icons / "fedtail.svg"
