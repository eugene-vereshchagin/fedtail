"""The Arch Linux package (and the AUR's PKGBUILD):

    python3 packaging/arch.py OUT_DIR                 # PKGBUILD for the release's archive
    python3 packaging/arch.py OUT_DIR --local ARCHIVE # …built from this archive here
                                                        (CI: makepkg in an archlinux box)

One package, `fedtail`: the program with the Qt window. depends — what it can't run
without (fedtail/deps.py's `arch` names: Python, requests, PySide6); optdepends — the rest
with what each gives (pacman shows them, `pacman -S --asdeps` takes them): the Qt
window's SVG pictures, video and WebP, sync, languages, GTK, the terminal… The source is
the release's own archive (packaging/source.py), named with its sha256. Built as a
wheel and installed with python-installer, as Arch builds Python programs; the menu
entry, the icon and the AppStream file from packaging/desktop_files.py.
"""

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packaging"))

import source  # noqa: E402

from fedtail import __version__, deps, i18n  # noqa: E402

HOMEPAGE = "https://github.com/eugene-vereshchagin/fedtail"
DESCRIPTION = "Fediverse client for people who miss Point.im and Juick: threads as trees"
MAINTAINER = "Eugene Vereshchagin <eugene-vereshchagin at users dot noreply dot github dot com>"


def _quote(s):
    return "'" + s.replace("'", "'\\''") + "'"


def pkgbuild(sha256, local_name=None, version=__version__):
    """The PKGBUILD's text. local_name: the archive lies beside it (a test build);
    else the release's download."""
    i18n.setup("en")
    needs, recommends, suggests = deps.dist_fields("arch")
    # the icon's folders are the theme's (namcap asks for it)
    depends = " ".join(_quote(p) for p in [p for p, _n in needs] + ["hicolor-icon-theme"])
    opt = "\n".join(f"  {_quote(f'{p}: {i18n._(n.what)}')}"
                    for p, n in recommends + suggests)
    src = local_name or (f"{source.name('$pkgver')}::{HOMEPAGE}/releases/download/"
                         f"v$pkgver/{source.name('$pkgver')}")
    return f"""# Maintainer: {MAINTAINER}
# made by packaging/arch.py from fedtail/deps.py — change it there
pkgname=fedtail
pkgver={version}
pkgrel=1
pkgdesc={_quote(DESCRIPTION)}
arch=('any')
url={_quote(HOMEPAGE)}
license=('GPL-3.0-or-later')
depends=({depends})
optdepends=(
{opt}
)
makedepends=('python-build' 'python-installer' 'python-setuptools' 'python-wheel')
source=("{src}")
sha256sums=('{sha256}')

build() {{
  cd "fedtail-$pkgver"
  python -m build --wheel --no-isolation
}}

package() {{
  cd "fedtail-$pkgver"
  python -m installer --destdir="$pkgdir" dist/*.whl
  python packaging/desktop_files.py "$pkgdir/usr"
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}}
"""


def write(out_dir, local=None, archive=None):
    """PKGBUILD into out_dir; local: build from this archive (copied beside it);
    archive: the release's archive, for its sha256 (made from HEAD when not given)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if local:
        local = Path(local)
        if local.resolve() != (out_dir / local.name).resolve():
            shutil.copy(local, out_dir / local.name)
        text = pkgbuild(source.sha256(local), local.name)
    else:
        text = pkgbuild(source.sha256(archive or source.make(out_dir)))
    path = out_dir / "PKGBUILD"
    path.write_text(text, "utf-8")
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out_dir")
    ap.add_argument("--local", help="build from this archive (beside the PKGBUILD)")
    ap.add_argument("--archive", help="the release's archive (for its sha256)")
    a = ap.parse_args()
    print(write(a.out_dir, a.local, a.archive))
