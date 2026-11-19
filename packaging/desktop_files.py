"""The files around the program that a package installs into <prefix>/share: the menu
entry, the icon, the AppStream file — the same for every package that has a /usr
(RPM, Arch, Flatpak, AppImage; the .deb writes its own, packaging/deb.py):

    python3 packaging/desktop_files.py PREFIX [--icon NAME] [--exec COMMAND]

    PREFIX/share/applications/online.dmesg.fedtail.desktop
    PREFIX/share/icons/hicolor/512x512/apps/<icon>.png   (icon: "fedtail"; Flatpak's
                                                           must be the app id)
    PREFIX/share/metainfo/online.dmesg.fedtail.metainfo.xml
"""

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packaging"))

import metainfo  # noqa: E402

from fedtail.core.paths import main_profile  # noqa: E402
from fedtail.desktop import entry_text  # noqa: E402
from fedtail.version import APP_ID  # noqa: E402


def entry(icon="fedtail", exec_line="fedtail"):
    """The menu entry of an installed fedtail: `fedtail` on the PATH (whatever profile
    the machine that builds it calls its main one)."""
    text = entry_text(profile=main_profile(), icon=icon)
    lines = []
    for line in text.splitlines():
        if line.startswith("Exec="):
            rest = line.split(" --ui ", 1)
            line = f"Exec={exec_line}" + (f" --ui {rest[1]}" if len(rest) > 1 else "")
        elif line.startswith("Path="):
            continue
        lines.append(line)
    return "\n".join(lines) + "\n"


def install(prefix, icon="fedtail", exec_line="fedtail"):
    """Write the three under prefix/share; → their paths."""
    share = Path(prefix) / "share"
    apps = share / "applications"
    icons = share / "icons/hicolor/512x512/apps"
    meta = share / "metainfo"
    for d in (apps, icons, meta):
        d.mkdir(parents=True, exist_ok=True)
    desk = apps / f"{APP_ID}.desktop"
    desk.write_text(entry(icon, exec_line), "utf-8")
    png = icons / f"{icon}.png"
    shutil.copy(ROOT / "fedtail/data/icons/fedtail.png", png)
    xml = metainfo.write(meta / f"{APP_ID}.metainfo.xml")
    return [desk, png, xml]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("prefix")
    ap.add_argument("--icon", default="fedtail")
    ap.add_argument("--exec", dest="exec_line", default="fedtail")
    a = ap.parse_args()
    print("\n".join(str(p) for p in install(a.prefix, a.icon, a.exec_line)))
