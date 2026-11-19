"""The source archive the distributions' packages are built from (Arch, RPM):

    python3 packaging/source.py [OUT_DIR]   # → dist/fedtail-<version>.tar.gz

`git archive` of HEAD, everything under fedtail-<version>/ — the release carries it, and
the PKGBUILD and the spec name it with its sha256. Needs git and a checkout.
"""

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fedtail import __version__  # noqa: E402


def name(version=__version__):
    return f"fedtail-{version}.tar.gz"


def make(out_dir=ROOT / "dist", version=__version__):
    """The archive; → its path."""
    out_dir = Path(out_dir).resolve()  # git -C reads a relative path from the root
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / name(version)
    subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar.gz",
                    f"--prefix=fedtail-{version}/", "-o", str(out), "HEAD"], check=True)
    return out


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


if __name__ == "__main__":
    print(make(*(Path(a) for a in sys.argv[1:2])))
