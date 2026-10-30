"""The Debian packages for Debian 13 and the like, one per interface — each toolkit comes
only with the package that wants it:

    python3 packaging/deb.py     → dist/fedtail-common_<v>_all.deb   the program: the core,
                                   the web page, the menu entry and the icon (requests only)
                                   dist/fedtail-qt_<v>_all.deb       the Qt window's toolkit
                                   dist/fedtail-gtk_<v>_all.deb      GTK 4 and libadwaita
                                   dist/fedtail-tui_<v>_all.deb      Textual (the terminal)
                                   dist/fedtail_<v>_all.deb          the usual install:
                                   common and a window — Qt, or GTK if that one is there

Pure Python, Architecture: all; every dependency comes from apt (fedtail/deps.py's table,
the same `fedtail --check` reads). The interfaces' packages hold no code of their own —
fedtail-common has all of it, and `fedtail` opens the window that is installed
(ui.frontend = "auto"). An old single fedtail package is replaced cleanly (Breaks /
Replaces). Needs dpkg-deb.

    sudo apt install ./fedtail-common_….deb ./fedtail-gtk_….deb    # GNOME, no Qt
    sudo apt install ./fedtail_….deb ./fedtail-common_….deb ./fedtail-qt_….deb
"""

import gzip
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fedtail import __version__, deps  # noqa: E402
from fedtail.desktop import entry_text  # noqa: E402
from fedtail.version import APP_ID  # noqa: E402

MAINTAINER = "Eugene Vereshchagin <eugene-vereshchagin@users.noreply.github.com>"
HOMEPAGE = "https://github.com/eugene-vereshchagin/fedtail"


def deb_version(v):
    """0.10.0.dev3 → 0.10.0~dev3 (a tilde sorts before the release, as it should)."""
    return re.sub(r"\.?(dev|a|b|rc)(\d*)", r"~\1\2", v)


DESCRIPTION = {
    "fedtail": ("fediverse client for people who miss Point.im and Juick",
                " A desktop client for GoToSocial, Mastodon, Akkoma and anything else that\n"
                " speaks the Mastodon API: whole threads as trees, every reply shows what it\n"
                " answers, lanes that never jump, everything is a config option.\n"
                " .\n"
                " This package installs the program with a window: Qt, or GTK 4 when\n"
                " fedtail-gtk is chosen instead. fedtail-tui adds the terminal interface."),
    "fedtail-common": ("fediverse client for people who miss Point.im and Juick (program)",
                       " The program itself: the core, the web interface and the menu entry.\n"
                       " Install fedtail-qt, fedtail-gtk or fedtail-tui for an interface\n"
                       " of its own; `fedtail` opens the one that is installed."),
    "fedtail-qt": ("fediverse client fedtail — the Qt window",
                   " The Qt 6 toolkit for fedtail's window (KDE and the rest)."),
    "fedtail-gtk": ("fediverse client fedtail — the GTK 4 window",
                    " GTK 4 and libadwaita for fedtail's window on GNOME."),
    "fedtail-tui": ("fediverse client fedtail — in a terminal",
                    " Textual for fedtail in a terminal (fedtail --ui tui), with pictures."),
}


def _control(work, name, ver, depends, recommends="", suggests="", extra=""):
    size = sum(p.stat().st_size for p in work.rglob("*") if p.is_file()) // 1024
    short, long = DESCRIPTION[name]
    fields = [f"Package: {name}", f"Version: {ver}", "Architecture: all",
              f"Maintainer: {MAINTAINER}", f"Installed-Size: {size}",
              f"Depends: {depends}"]
    fields += [f"Recommends: {recommends}"] * bool(recommends)
    fields += [f"Suggests: {suggests}"] * bool(suggests)
    fields += [extra] * bool(extra)
    fields += ["Section: net", "Priority: optional", f"Homepage: {HOMEPAGE}",
               f"Description: {short}", long]
    control = work / "DEBIAN"
    control.mkdir()
    (control / "control").write_text("\n".join(fields) + "\n", "utf-8")


def _doc(work, name, copyright_text):
    """A package's /usr/share/doc/<name>: its copyright and the changelog."""
    doc = work / "usr/share/doc" / name
    doc.mkdir(parents=True)
    (doc / "copyright").write_text(copyright_text, "utf-8")
    (doc / "changelog.gz").write_bytes(gzip.compress((ROOT / "CHANGELOG.md").read_bytes(),
                                                     mtime=0))


def _pack(work, out_dir, name, ver):
    out_dir.mkdir(parents=True, exist_ok=True)
    deb = out_dir / f"{name}_{ver}_all.deb"
    subprocess.run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", str(work), str(deb)],
                   check=True)
    return deb


def build(out_dir=ROOT / "dist", work=ROOT / "build" / "deb"):
    """Every package; → their paths, fedtail-common's first."""
    ver = deb_version(__version__)
    if work.exists():
        shutil.rmtree(work)
    same = f"(= {ver})"
    debs = [_common(out_dir, work / "common", ver)]
    plain = (f"Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/\n"
             f"Upstream-Name: fedtail\nSource: {HOMEPAGE}\n\n"
             "Files: *\nCopyright: Eugene Vereshchagin\nLicense: GPL-3+\n"
             " On Debian systems the full text is in /usr/share/common-licenses/GPL-3.\n")
    for group in ("qt", "gtk", "tui"):
        name = deps.DEB_PACKAGES[group]
        w = work / group
        _doc(w, name, plain)
        depends, recommends, _s = deps.deb_fields(group)
        _control(w, name, ver, f"fedtail-common {same}, {depends}", recommends)
        debs.append(_pack(w, out_dir, name, ver))
    w = work / "meta"
    _doc(w, "fedtail", plain)
    _control(w, "fedtail", ver, f"fedtail-common {same}, fedtail-qt {same} | fedtail-gtk {same}",
             suggests="fedtail-tui")
    debs.append(_pack(w, out_dir, "fedtail", ver))
    return debs


def _common(out_dir, work, ver):
    pkg = work / "usr/lib/python3/dist-packages/fedtail"
    shutil.copytree(ROOT / "fedtail", pkg,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    bin_dir = work / "usr/bin"
    bin_dir.mkdir(parents=True)
    launcher = bin_dir / "fedtail"
    launcher.write_text("#!/usr/bin/python3\nimport sys\n\nfrom fedtail.__main__ import main\n\n"
                        "sys.exit(main())\n", "utf-8")
    launcher.chmod(0o755)
    apps = work / "usr/share/applications"
    apps.mkdir(parents=True)
    (apps / f"{APP_ID}.desktop").write_text(entry_text(icon="fedtail"), "utf-8")
    icons = work / "usr/share/icons/hicolor/512x512/apps"
    icons.mkdir(parents=True)
    shutil.copy(ROOT / "fedtail/data/icons/fedtail.png", icons / "fedtail.png")
    _doc(work, "fedtail-common", (
        "Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/\n"
        f"Upstream-Name: fedtail\nSource: {HOMEPAGE}\n\n"
        "Files: *\nCopyright: Eugene Vereshchagin\nLicense: GPL-3+\n"
        " On Debian systems the full text is in /usr/share/common-licenses/GPL-3.\n\n"
        "Files: */fedtail/data/themes/fonts/*\nCopyright: ParaType, IBM, Adobe, Google, "
        "Mozilla and the font projects' authors\n"
        "License: OFL-1.1\n The full text for each family lies next to it (OFL-*.txt).\n\n"
        "Files: */fedtail/data/icons/fedtail.png */fedtail/data/icons/fedtail-swing.*\n"
        "Copyright: Boggart Owl (https://www.instagram.com/boggartowl/)\n"
        "License: other\n A sticker from the official Telegram sticker pack fluffyloafer\n"
        " (https://t.me/addstickers/fluffyloafer),\n"
        " used as Telegram's stickers are shared everywhere; not under the GPL.\n\n"
        "Files: */fedtail/_vendor/textual_image/*\n"
        "Copyright: Simon Hayessen and the textual-image authors\n"
        "License: LGPL-3+\n Carried as PyPI has it (tools/vendor.py, _vendor/VENDORED.toml);\n"
        " the full text is LICENSE.txt there and /usr/share/common-licenses/LGPL-3.\n\n"
        "Files: */fedtail/data/themes/psi/icons/*.png\n"
        "Copyright: the Psi and Psi+ authors (Jason Kim, "
        "Everaldo Coelho)\nLicense: GPL-2+\n From Psi+'s iconsets: see LICENSE.txt there.\n"
    ))
    depends, recommends, suggests = deps.deb_fields("common")
    # the program was the one package fedtail before 0.22: its files are ours now
    _control(work, "fedtail-common", ver, depends, recommends,
             ", ".join(filter(None, [suggests, "fedtail-tui"])),
             "Breaks: fedtail (<< 0.22.0~)\nReplaces: fedtail (<< 0.22.0~)")
    return _pack(out_dir=out_dir, work=work, name="fedtail-common", ver=ver)


if __name__ == "__main__":
    print("\n".join(str(d) for d in build()))
