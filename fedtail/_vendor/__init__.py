"""Packages fedtail carries inside itself, for what Debian doesn't have (VENDORED.toml,
tools/vendor.py): textual-image, the terminal's real pictures. Each stays an importable
package of its own name; use() puts this folder last on the path, so a copy installed in
the system or by pip — maybe newer — is the one imported."""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def use():
    """This folder on the import path, after everything else (once)."""
    here = str(HERE)
    if here not in sys.path:
        sys.path.append(here)
