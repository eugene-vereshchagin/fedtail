"""The debugging mode's corner of the status bar: how the window is drawn, the same
fields in the same order in Qt and GTK, so two screenshots can be put side by side —
theme · toolkit and its version · style · font · display · scale · build."""

from __future__ import annotations

import sys

from ...i18n import _

# what each toolkit calls the display's kind → one word for both
DISPLAYS = {"xcb": "x11", "x11": "x11", "wayland": "wayland", "windows": "windows",
            "win32": "windows", "cocoa": "macos", "macos": "macos", "offscreen": "offscreen",
            "broadway": "broadway"}


def display_word(name):
    name = (name or "").lower()
    return DISPLAYS.get(name, name or "?")


def text(theme, toolkit, style, font, display, scale):
    """theme: the theme's id; toolkit: "Qt 6.8.2" / "GTK 4.18.6"; style: the Qt style or
    "libadwaita" / "GTK"; font: "Open Sans 10pt"; display: the toolkit's own word for it;
    scale: the screen's pixel ratio (1.25 → "125%"). Empty fields are left out."""
    bits = [_("debug_theme", theme=theme), toolkit, style, font, display_word(display),
            f"{scale * 100:g}%" if scale else "",
            "onefile" if getattr(sys, "frozen", False) else "source"]
    return " · ".join(b for b in bits if b)
