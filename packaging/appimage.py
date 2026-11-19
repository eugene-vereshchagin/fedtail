"""The AppImage: one file that runs on most Linux systems, with a menu entry of its own
(AppImageLauncher, Gear Lever) and updates by delta (zsync):

    python3 packaging/build.py --onedir      # first: dist/onedir/fedtail/
    python3 packaging/appimage.py [APPIMAGETOOL]
        → dist/fedtail-<version>-x86_64.AppImage and its .zsync

Inside: the PyInstaller folder (Python, Qt, Textual — the same as the one-file build,
but mounted, not unpacked at each start), the menu entry, the icon and the AppStream
file (packaging/desktop_files.py). The update information points at the latest GitHub
release's AppImage, so AppImageUpdate finds the next one. appimagetool: its path, or
`appimagetool` on the PATH; it fetches the AppImage runtime itself.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packaging"))

import desktop_files  # noqa: E402

from fedtail import __version__  # noqa: E402
from fedtail.version import APP_ID  # noqa: E402

UPDATE = "gh-releases-zsync|eugene-vereshchagin|fedtail|latest|fedtail-*-x86_64.AppImage.zsync"

APPRUN = """#!/bin/sh
# the AppImage's entry: the program inside, with what it was given
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/fedtail/fedtail" "$@"
"""


def appdir(work=ROOT / "build" / "AppDir", onedir=ROOT / "dist" / "onedir" / "fedtail"):
    """The AppDir made anew from the PyInstaller folder; → its path."""
    if not (onedir / "fedtail").exists():
        raise SystemExit(f"no {onedir}/fedtail: run packaging/build.py --onedir first")
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(onedir, work / "usr/lib/fedtail", symlinks=True)
    run = work / "AppRun"
    run.write_text(APPRUN, "utf-8")
    run.chmod(0o755)
    desk, png, _xml = desktop_files.install(work / "usr")
    # appimagetool takes the entry and the icon from the top of the AppDir
    shutil.copy(desk, work / f"{APP_ID}.desktop")
    shutil.copy(png, work / "fedtail.png")
    os.symlink("fedtail.png", work / ".DirIcon")
    return work


def build(tool=None, out_dir=ROOT / "dist"):
    work = appdir()
    tool = tool or shutil.which("appimagetool") or "appimagetool"
    out = Path(out_dir) / f"fedtail-{__version__}-x86_64.AppImage"
    env = dict(os.environ, ARCH="x86_64",
               # no FUSE in a container: the tool runs from its unpacked self
               APPIMAGE_EXTRACT_AND_RUN="1")
    subprocess.run([str(tool), "--no-appstream", "-u", UPDATE, str(work), str(out)],
                   check=True, env=env, cwd=out_dir)
    return out


if __name__ == "__main__":
    print(build(*sys.argv[1:2]))
