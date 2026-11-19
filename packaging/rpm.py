"""The RPM for Fedora (the spec, and the package built from it):

    python3 packaging/rpm.py OUT_DIR                   # fedtail.spec for the release
    python3 packaging/rpm.py OUT_DIR --local ARCHIVE   # …built from this archive here
                                                         (CI: rpmbuild in a fedora box)

One package, `fedtail`, noarch: Requires — what it can't run without (fedtail/deps.py's
`rpm` names: Python, requests, PySide6); Recommends — the Qt window's WebP, sync,
languages (dnf installs them unless told not to); Suggests — GTK, the terminal, the
other extras. Built with Fedora's pyproject macros from the release's own archive
(packaging/source.py); the menu entry, the icon and the AppStream file from
packaging/desktop_files.py.

    rpmbuild -ba --define "_sourcedir $PWD" --define "_rpmdir $PWD" fedtail.spec
"""

import argparse
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packaging"))

import source  # noqa: E402

from fedtail import __version__, deps  # noqa: E402

HOMEPAGE = "https://github.com/eugene-vereshchagin/fedtail"
SUMMARY = "Fediverse client for people who miss Point.im and Juick"
# the interfaces whose toolkits are only recommended or suggested: not imported at build
UNCHECKED = " ".join(f"-e 'fedtail.frontends.{ui}*'" for ui in ("qt", "gtk", "tui"))
PACKAGER = "Eugene Vereshchagin <eugene-vereshchagin@users.noreply.github.com>"


def rpm_version(v):
    """0.23.6.dev0 → 0.23.6~dev0 (a tilde sorts before the release, as in the .deb)."""
    return re.sub(r"\.?(dev|a|b|rc)(\d*)", r"~\1\2", v)


def spec(local_name=None, version=__version__, when=None):
    """The spec's text. local_name: the archive lies in _sourcedir (a test build); else
    the release's download."""
    needs, recommends, suggests = deps.dist_fields("rpm")
    # Python's own sqlite3 pulls the library in (rpmlint: explicit-lib-dependency)
    needs = [(p, n) for p, n in needs if p != "sqlite-libs"]
    req = "\n".join(f"Requires:       {p}" for p, _n in needs)
    rec = "\n".join(f"Recommends:     {p}" for p, _n in recommends)
    sug = "\n".join(f"Suggests:       {p}" for p, _n in suggests)
    src = local_name or f"{HOMEPAGE}/releases/download/v{version}/{source.name(version)}"
    when = (when or datetime.now(UTC)).strftime("%a %b %d %Y")
    rv = rpm_version(version)
    return f"""# made by packaging/rpm.py from fedtail/deps.py — change it there
Name:           fedtail
Version:        {rv}
Release:        1%{{?dist}}
Summary:        {SUMMARY}
License:        GPL-3.0-or-later
URL:            {HOMEPAGE}
Source0:        {src}
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
{req}
{rec}
{sug}

%description
A desktop client for GoToSocial, Mastodon, Akkoma and anything else that speaks
the Mastodon API: whole threads as trees, every reply shows what it answers,
lanes that never jump, everything is a config option. The Qt window comes
with it; the GTK window and the terminal interface take their toolkits when
installed.

%prep
%autosetup -n fedtail-{version}

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files fedtail
%{{python3}} packaging/desktop_files.py %{{buildroot}}%{{_prefix}}

%check
# the windows' toolkits are Recommends/Suggests: not here at build time
%pyproject_check_import {UNCHECKED}

%files -f %{{pyproject_files}}
%license LICENSE
%doc README.md CHANGELOG.md
%{{_bindir}}/fedtail
%{{_datadir}}/applications/online.dmesg.fedtail.desktop
%{{_datadir}}/icons/hicolor/512x512/apps/fedtail.png
%{{_metainfodir}}/online.dmesg.fedtail.metainfo.xml

%changelog
* {when} {PACKAGER} - {rv}-1
- fedtail {version}: see CHANGELOG.md
"""


def write(out_dir, local=None):
    """fedtail.spec into out_dir; local: build from this archive (copied beside it)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = None
    if local:
        local = Path(local)
        name = local.name
        if local.resolve() != (out_dir / name).resolve():
            shutil.copy(local, out_dir / name)
    path = out_dir / "fedtail.spec"
    path.write_text(spec(name), "utf-8")
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out_dir")
    ap.add_argument("--local", help="build from this archive (beside the spec)")
    a = ap.parse_args()
    print(write(a.out_dir, a.local))
