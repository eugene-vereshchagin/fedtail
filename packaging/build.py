"""One file with everything inside — fedtail for people without Python.

    python3 packaging/build.py            # → dist/fedtail (Linux) or dist/fedtail.exe

PyInstaller packs Python, Qt (PySide6) and fedtail into a single executable that
unpacks itself on start. The version, commit and date of the build are written
into fedtail/_build.py first (there is no git inside the file), and removed after.
Running from the source with Python stays as it was: `python3 -m fedtail`.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = sys.platform == "win32"


def main():
    sys.path.insert(0, str(ROOT))
    from fedtail import version
    info = version.info()
    build = ROOT / "fedtail" / "_build.py"
    build.write_text(f"BUILD = {info['version']!r}\nCOMMIT = {info['commit']!r}\n"
                     f"DATE = {info['date']!r}\n", "utf-8")
    print("building fedtail", info["version"])
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--name", "fedtail",
            "--add-data", f"{ROOT / 'fedtail' / 'data'}{';' if WINDOWS else ':'}fedtail/data",
            "--collect-submodules", "fedtail",
            "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"),
            "--specpath", str(ROOT / "build")]
    if WINDOWS:
        icon = ROOT / "build" / "fedtail.ico"
        icon.parent.mkdir(exist_ok=True)
        subprocess.run([sys.executable, str(ROOT / "packaging" / "make_icon.py"),
                        str(ROOT / "fedtail" / "data" / "icons" / "fedtail.svg"), str(icon)],
                       check=True)
        args += ["--windowed", "--icon", str(icon)]
    try:
        subprocess.run(args + [str(ROOT / "packaging" / "fedtail_main.py")], check=True,
                       cwd=ROOT)
    finally:
        build.unlink(missing_ok=True)
    out = ROOT / "dist" / ("fedtail.exe" if WINDOWS else "fedtail")
    print("built", out, out.stat().st_size // (1024 * 1024), "MB")


if __name__ == "__main__":
    main()
