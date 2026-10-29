"""A Debian package: fedtail_<version>_all.deb for Debian 13 and the like.

    python3 packaging/deb.py            → dist/fedtail_<version>_all.deb

Pure Python, Architecture: all; Qt, requests, GTK 4 (and, if wanted, Textual) come
from apt. The GTK window is an action of the menu entry ("fedtail (GTK)"). Needs
dpkg-deb. The menu entry and the icon go where the desktop looks for them, so after
`sudo apt install ./fedtail_….deb` fedtail is in the menu.
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

# from the table fedtail --check reads (fedtail/deps.py): one list for both
DEPENDS, RECOMMENDS, SUGGESTS = deps.deb_fields()
MAINTAINER = "Eugene Vereshchagin <eugene-vereshchagin@users.noreply.github.com>"
HOMEPAGE = "https://github.com/eugene-vereshchagin/fedtail"


def deb_version(v):
    """0.10.0.dev3 → 0.10.0~dev3 (a tilde sorts before the release, as it should)."""
    return re.sub(r"\.?(dev|a|b|rc)(\d*)", r"~\1\2", v)


def build(out_dir=ROOT / "dist", work=ROOT / "build" / "deb"):
    ver = deb_version(__version__)
    if work.exists():
        shutil.rmtree(work)
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
    doc = work / "usr/share/doc/fedtail"
    doc.mkdir(parents=True)
    (doc / "copyright").write_text(
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
        "Everaldo Coelho)\nLicense: GPL-2+\n From Psi+'s iconsets: see LICENSE.txt there.\n",
        "utf-8")
    (doc / "changelog.gz").write_bytes(gzip.compress((ROOT / "CHANGELOG.md").read_bytes(),
                                                     mtime=0))
    size = sum(p.stat().st_size for p in work.rglob("*") if p.is_file()) // 1024
    control = work / "DEBIAN"
    control.mkdir()
    (control / "control").write_text(
        f"Package: fedtail\nVersion: {ver}\nArchitecture: all\nMaintainer: {MAINTAINER}\n"
        f"Installed-Size: {size}\nDepends: {DEPENDS}\nRecommends: {RECOMMENDS}\n"
        f"Suggests: {SUGGESTS}\nSection: net\nPriority: optional\nHomepage: {HOMEPAGE}\n"
        "Description: fediverse client for people who miss Point.im and Juick\n"
        " A desktop client for GoToSocial, Mastodon, Akkoma and anything else that\n"
        " speaks the Mastodon API: whole threads as trees, every reply shows what it\n"
        " answers, lanes that never jump, everything is a config option. Also runs\n"
        " in a terminal (with python3-textual), as a GTK 4 window (fedtail --ui gtk)\n"
        " and as a page in a browser.\n", "utf-8")
    out_dir.mkdir(parents=True, exist_ok=True)
    deb = out_dir / f"fedtail_{ver}_all.deb"
    subprocess.run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", str(work), str(deb)],
                   check=True)
    return deb


if __name__ == "__main__":
    print(build())
