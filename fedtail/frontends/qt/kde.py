"""Looking like KDE when Qt can't ask KDE itself.

Qt from the distribution loads KDE's own integration (the Breeze style, the colour
scheme, the fonts, the icon theme). The Qt inside the one-file build is a different
Qt, and KDE's plugins don't fit it: without help it comes up in plain Fusion grey
with the wrong font. So in a KDE session without that integration we read the same
settings KDE writes for everyone, ~/.config/kdeglobals, and apply them ourselves.
"""

import configparser
import logging
import os
import sys
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QIcon, QPalette

log = logging.getLogger(__name__)

# Breeze Light, for a kdeglobals that never had a colour scheme written into it
BREEZE = {
    "Colors:Window": {"BackgroundNormal": "239,240,241", "ForegroundNormal": "35,38,39",
                      "ForegroundInactive": "112,125,138"},
    "Colors:View": {"BackgroundNormal": "255,255,255", "BackgroundAlternate": "247,247,247",
                    "ForegroundNormal": "35,38,39", "ForegroundInactive": "112,125,138",
                    "ForegroundLink": "41,128,185", "ForegroundVisited": "155,89,182"},
    "Colors:Button": {"BackgroundNormal": "252,252,252", "ForegroundNormal": "35,38,39"},
    "Colors:Selection": {"BackgroundNormal": "61,174,233", "ForegroundNormal": "255,255,255"},
    "Colors:Tooltip": {"BackgroundNormal": "247,247,247", "ForegroundNormal": "35,38,39"},
}


DEFAULT_FONT = "Noto Sans,10,-1,5,400,0,0,0,0,0,0,0,0,0,0,1"


def in_kde():
    return sys.platform.startswith("linux") and \
        "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper()


def kdeglobals():
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    try:
        cp.read(Path(base) / "kdeglobals", encoding="utf-8")
    except (OSError, configparser.Error) as e:
        log.warning("kdeglobals: %s", e)
    return cp


def _color(cp, section, key):
    raw = cp.get(section, key, fallback=None) or BREEZE.get(section, {}).get(key)
    if not raw:
        return None
    try:
        parts = [int(x) for x in raw.split(",")[:4]]
        return QColor(*parts)
    except (ValueError, TypeError):
        return None


def palette(cp):
    pal = QPalette()
    R, G = QPalette.ColorRole, QPalette.ColorGroup
    roles = [(R.Window, "Colors:Window", "BackgroundNormal"),
             (R.WindowText, "Colors:Window", "ForegroundNormal"),
             (R.Base, "Colors:View", "BackgroundNormal"),
             (R.AlternateBase, "Colors:View", "BackgroundAlternate"),
             (R.Text, "Colors:View", "ForegroundNormal"),
             (R.PlaceholderText, "Colors:View", "ForegroundInactive"),
             (R.Button, "Colors:Button", "BackgroundNormal"),
             (R.ButtonText, "Colors:Button", "ForegroundNormal"),
             (R.Highlight, "Colors:Selection", "BackgroundNormal"),
             (R.HighlightedText, "Colors:Selection", "ForegroundNormal"),
             (R.ToolTipBase, "Colors:Tooltip", "BackgroundNormal"),
             (R.ToolTipText, "Colors:Tooltip", "ForegroundNormal"),
             (R.Link, "Colors:View", "ForegroundLink"),
             (R.LinkVisited, "Colors:View", "ForegroundVisited")]
    for role, section, key in roles:
        c = _color(cp, section, key)
        if c is not None:
            pal.setColor(role, c)
    button = pal.color(R.Button)
    pal.setColor(R.Light, button.lighter(150))
    pal.setColor(R.Midlight, button.lighter(115))
    pal.setColor(R.Mid, button.darker(130))
    pal.setColor(R.Dark, button.darker(160))
    pal.setColor(R.Shadow, QColor(0, 0, 0, 120))
    dim = _color(cp, "Colors:Window", "ForegroundInactive")
    if dim is not None:
        for role in (R.WindowText, R.Text, R.ButtonText):
            pal.setColor(G.Disabled, role, dim)
    return pal


def adopt(app):
    """In a KDE session where Qt didn't load KDE's integration (the one-file build),
    take KDE's colours, fonts and icon theme from kdeglobals. Returns what was done,
    for the log; "" when nothing was needed."""
    style = app.style().name().lower()
    if not in_kde() or style == "breeze" or os.environ.get("FEDTAIL_NO_KDEGLOBALS"):
        return ""
    cp = kdeglobals()
    app.setStyle("Fusion")
    app.setPalette(palette(cp))
    done = [f"style {style} → Fusion", "KDE colours"]
    # KDE writes the font into kdeglobals only once it has been changed; until then
    # it is Plasma's own default — not the bare "Sans Serif 9" Qt would pick
    font = cp.get("General", "font", fallback="") or DEFAULT_FONT
    if font:
        f = QFont()
        if f.fromString(font):
            app.setFont(f)
            done.append(f"font {f.family()} {f.pointSizeF():g}pt")
    icons = cp.get("Icons", "Theme", fallback="breeze")
    if QIcon.themeName() in ("", "hicolor"):
        QIcon.setThemeName(icons)
        done.append(f"icons {icons}")
    return ", ".join(done)
