#!/usr/bin/env python3
"""The packages fedtail carries inside itself (fedtail/_vendor/): those Debian doesn't have
— textual-image, the terminal's real pictures (sixel, kitty). Each is the wheel from PyPI
as it is, its checksum checked, a few files it doesn't need left out; what, which version
and why is fedtail/_vendor/VENDORED.toml. A copy installed in the system or by pip wins
over ours (fedtail/_vendor/__init__.py puts ours last on the path).

    python3 tools/vendor.py --check     # a newer version on PyPI? exit 1 (CI's vendored job)
    python3 tools/vendor.py --update    # every package to PyPI's newest, the toml with it
    python3 tools/vendor.py --update textual-image==0.14.2   # one, at a version
"""

import argparse
import fnmatch
import hashlib
import io
import json
import re
import shutil
import sys
import tomllib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "fedtail" / "_vendor"
LIST = VENDOR / "VENDORED.toml"
PYPI = "https://pypi.org/pypi/{name}/json"


def load():
    return tomllib.loads(LIST.read_text("utf-8"))


def version_key(v):
    """"0.14.2" → comparable; "1.0" > "1.0rc1" > "0.14.10" > "0.14.2"."""
    m = re.match(r"(\d+(?:\.\d+)*)(.*)", v.strip().lower())
    if m is None:
        return ((0,) * 6, 0, v)
    nums = tuple(int(x) for x in m.group(1).split("."))
    nums += (0,) * (6 - len(nums))
    rest = m.group(2).lstrip(".-")
    return (nums, 1, "") if not rest or rest.startswith("post") else (nums, 0, rest)


def pypi(name, version=None):
    url = PYPI.format(name=name) if version is None else \
        f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def newest(name):
    return pypi(name)["info"]["version"]


def check(items):
    """→ the packages with a newer version on PyPI: [(name, ours, theirs)]."""
    out = []
    for name, it in items.items():
        theirs = newest(name)
        print(f"{name}: carried {it['version']}, PyPI {theirs}")
        if version_key(theirs) > version_key(it["version"]):
            out.append((name, it["version"], theirs))
    return out


def fetch_wheel(name, version):
    """The pure-Python wheel of name==version from PyPI, its sha256 checked. → (bytes,
    sha256)."""
    info = pypi(name, version)
    wheel = next((u for u in info["urls"] if u["filename"].endswith("-py3-none-any.whl")),
                 None)
    if wheel is None:
        sys.exit(f"{name} {version}: no pure-Python wheel on PyPI")
    with urllib.request.urlopen(wheel["url"], timeout=60) as r:
        data = r.read()
    got = hashlib.sha256(data).hexdigest()
    if got != wheel["digests"]["sha256"]:
        sys.exit(f"{name} {version}: checksum {got} is not PyPI's")
    return data, got


def unpack(item, data):
    """The package out of the wheel into fedtail/_vendor/<package>/, the files it doesn't
    need left out, its licence beside it."""
    pkg = item["package"]
    dest = VENDOR / pkg
    if dest.exists():
        shutil.rmtree(dest)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            if n.endswith("/"):  # a folder's own entry: its files make it
                continue
            if n.startswith(pkg + "/"):
                rel = n[len(pkg) + 1:]
                if not rel or any(fnmatch.fnmatch(rel, d) or rel.startswith(d.rstrip("/") + "/")
                                  for d in item.get("dropped", [])):
                    continue
                out = dest / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(z.read(n))
            elif re.search(r"\.dist-info/(licenses/)?LICEN[CS]E", n):
                (dest / "LICENSE.txt").parent.mkdir(parents=True, exist_ok=True)
                (dest / "LICENSE.txt").write_bytes(z.read(n))


def write(items):
    lines = ["# What fedtail carries inside itself (tools/vendor.py): a package Debian lacks,",
             "# the PyPI wheel as it is (sha256 checked), the files listed in `dropped` left",
             "# out. A copy in the system or from pip wins over ours (_vendor/__init__.py).",
             ""]
    for name, it in items.items():
        lines.append(f'["{name}"]')
        for k in ("version", "package", "license", "sha256", "why"):
            lines.append(f"{k} = {json.dumps(it[k], ensure_ascii=False)}")
        lines.append("dropped = [" + ", ".join(json.dumps(d) for d in it.get("dropped", [])) +
                     "]")
        lines.append("")
    LIST.write_text("\n".join(lines), "utf-8")


def update(items, which=()):
    want = dict(w.partition("==")[::2] for w in which) if which else {n: "" for n in items}
    for name, pinned in want.items():
        if name not in items:
            sys.exit(f"{name}: not in {LIST.relative_to(ROOT)}")
        version = pinned or newest(name)
        data, sha = fetch_wheel(name, version)
        unpack(items[name], data)
        items[name].update(version=version, sha256=sha)
        print(f"{name} {version}: into fedtail/_vendor/{items[name]['package']}/")
    write(items)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="a newer version on PyPI? exit 1")
    ap.add_argument("--update", nargs="*", metavar="NAME[==VERSION]",
                    help="to PyPI's newest (or the version given)")
    a = ap.parse_args(argv)
    items = load()
    if a.update is not None:
        update(items, a.update)
        return 0
    newer = check(items)
    for name, ours, theirs in newer:
        print(f"::warning::{name} {theirs} is out (fedtail carries {ours}): "
              f"python3 tools/vendor.py --update {name}")
    return 1 if newer and a.check else 0


if __name__ == "__main__":
    sys.exit(main())
