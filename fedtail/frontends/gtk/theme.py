"""A theme file (frontends/themefile.py) as GTK CSS, its colours from palette.py.

GTK 4 has no desktop palette to ask (Qt has QPalette): what it can say is light or dark
and, with libadwaita ≥ 1.6, the accent. So "auto" colours are worked out from Adwaita's
own reference colours, light or dark, with the desktop's accent when known — the
"system" theme on GTK means "as Adwaita" (docs/en/dev/gtk.md).
"""

from __future__ import annotations

import logging

from .. import palette, themefile
from ..palette import Color, Desktop
from . import gi_setup
from .gi_setup import Gdk, Gtk

log = logging.getLogger(__name__)

# Adwaita's reference colours (libadwaita 1.5+: view, window, text, blue, link)
ADWAITA_LIGHT = dict(base="#ffffff", window="#fafafb", text="#202024", highlight="#3584e4",
                     link="#1c71d8")
ADWAITA_DARK = dict(base="#1d1d20", window="#222226", text="#ffffff", highlight="#3584e4",
                    link="#78aeed")


def is_dark():
    Adw = gi_setup.Adw
    if Adw is not None:
        try:
            return bool(Adw.StyleManager.get_default().get_dark())
        except Exception:  # noqa: BLE001 — not initialised yet: ask GTK
            pass
    settings = Gtk.Settings.get_default()
    if settings is None:
        return False
    if settings.get_property("gtk-application-prefer-dark-theme"):
        return True
    name = (settings.get_property("gtk-theme-name") or "").lower()
    return name.endswith("-dark") or ":dark" in name


def accent():
    """The desktop's accent colour (libadwaita ≥ 1.6), or None."""
    Adw = gi_setup.Adw
    try:
        rgba = Adw.StyleManager.get_default().get_accent_color_rgba() if Adw else None
    except AttributeError:
        return None
    if rgba is None:
        return None
    return Color(round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255))


def desktop():
    ref = ADWAITA_DARK if is_dark() else ADWAITA_LIGHT
    d = {k: Color.parse(v) for k, v in ref.items()}
    acc = accent()
    if acc is not None:
        d["highlight"] = acc
    return Desktop(**d)


class Theme:
    """What the widgets need: resolved colours (`c`), shape, words, fonts."""

    def __init__(self, data, desk, warnings=()):
        self.id = data["id"]
        self.name = data.get("name") or self.id
        self.font = data["font"]
        self.shape = data["shape"]
        self.icon_dirs = list(data.get("icon_dirs") or ())  # the theme's own pictures
        self.pictures = data.get("pictures") or {}  # how they're coloured, from where
        self.icon_mode = "desktop"  # where the pictures come from: set by apply()
        self.split_layout = False
        self.words = data["words"]
        self.c = palette.resolve(data["colors"], desk)
        self.warnings = list(warnings)
        self.dark = desk.base.lightness() < 128
        self.font_family = ""  # set by apply(): the family the CSS gives, "" — the desktop's

    def word(self, key, text, **kw):
        return palette.word(self.words, key, text, **kw)

    def date(self, when, fmt=None):
        return palette.date(self.words, when, fmt)

    def css(self, font_family="", post_scale=1.0):
        c = {k: v.css() for k, v in self.c.items()}
        r = int(self.shape.get("radius", 12))
        br = int(self.shape.get("button_radius", 8))
        rule = self.shape.get("card_style", "card") == "rule"
        card = (f"background: {c['view']}; border: none; border-bottom: 1px "
                f"{self.shape.get('rule', 'solid')} {c['card_border']}; border-radius: 0;"
                if rule else
                f"background: {c['card']}; border: 1px solid {c['card_border']}; "
                f"border-radius: {r}px;")
        fam = f"font-family: {css_families(font_family)};" if font_family else ""
        return f"""
window.fedtail, .fedtail-main {{ background: {c['window']}; color: {c['text']}; {fam} }}
.ft-sidebar {{ background: {c['sidebar']}; border-right: 1px solid {c['sidebar_border']}; }}
.ft-sidebar row {{ color: {c['sidebar_text']}; padding: 5px 8px; border-radius: {br}px;
  background: transparent; box-shadow: none; border: none; min-height: 0;
  margin: 1px 0; }}
.ft-sidebar row:hover {{ background: alpha({c['sidebar_text']}, 0.08); }}
.ft-sidebar row:selected, .ft-sidebar row:selected:hover {{ background: {c['selected']};
  color: {c['selected_text']}; }}
.ft-sidebar .ft-account {{ color: {c['sidebar_muted']}; }}
.ft-sidebar button, .ft-sidebar .ft-name {{ color: {c['sidebar_text']}; }}
.ft-sidebar .ft-muted {{ color: {c['sidebar_muted']}; }}
.ft-badge {{ background: {c['accent']}; color: {c['on_accent']}; border-radius: 9px;
            padding: 0 6px; font-size: smaller; }}
.ft-badge.hot {{ background: {c['hot']}; color: {c['on_hot']}; }}
.ft-badge.quiet {{ background: {c['quiet']}; color: {c['on_quiet']}; }}
.ft-view, .ft-view > viewport, .ft-feed {{ background: {c['view']}; }}
.ft-lane-header {{ background: {c['header']}; border-bottom: 1px solid {c['header_border']};
                   padding: 4px 10px; }}
.ft-lane-title {{ font-weight: bold; color: {c['text']}; font-size: 1.55em; }}
.ft-lane-header togglebutton:checked, .ft-lane-header button:checked {{
    background: {c['accent']}; color: {c['on_accent']}; }}
.ft-active {{ color: {c['accent']}; }}
.ft-new-pill {{ background: {c['new_pill']}; color: {c['on_new_pill']};
               border-radius: 11px; padding: 2px 10px; font-weight: 600; }}
.ft-feed > row {{ background: transparent; padding: 3px 0; }}
.ft-feed > row:hover, .ft-feed > row:focus {{ background: transparent; outline: none; }}
.ft-card {{ {card} padding: 8px 12px; color: {c['text']}; }}
.ft-card.ft-unread {{ border-color: {c['card_border_unread']}; }}
.ft-card.ft-focus {{ background: {c['focus']}; border-color: {c['focus_border']}; }}
.ft-card.ft-found {{ border: 2px solid {c['accent']}; }}
.ft-findbar {{ background: {c['header']}; }}
.ft-announce {{ background: {c['ctx']}; border: 1px solid {c['card_border']};
               border-radius: {br}px; padding: 4px 8px; }}
.ft-over {{ color: {c['hot']}; }}
.ft-name {{ color: {c['name']}; font-weight: bold; }}
.ft-muted, .ft-card .ft-muted {{ color: {c['muted']}; }}
.ft-dot {{ color: {c['dot']}; }}
.ft-mono {{ font-family: monospace; color: {c['muted']}; }}
.ft-ctx {{ background: {c['ctx']}; border-left: 3px solid {c['ctx_bar']}; padding: 3px 8px;
          color: {c['muted']}; border-radius: 0 {br}px {br}px 0; }}
.ft-myreply {{ background: {c['myreply']}; color: {c['on_myreply']}; padding: 2px 8px;
              border-radius: {br}px; }}
.ft-body {{ font-size: {post_scale:.2f}em; }}
.ft-card label link, .ft-ctx label link {{ color: {c['link']}; }}
.ft-cw {{ font-weight: bold; }}
.ft-newcomer {{ color: {c['hot']}; font-weight: bold; }}
.ft-event {{ color: {c['muted']}; border-left: 3px solid {c['ctx_bar']}; padding: 4px 10px; }}
.ft-event link {{ color: {c['muted']}; }}
.ft-separator {{ color: {c['separator']}; border-bottom: 1px dashed {c['separator']};
                padding: 2px 0; font-size: smaller; }}
.ft-action {{ background: transparent; border: 1px solid transparent; box-shadow: none;
             border-radius: {br}px; color: {c['muted']}; padding: 0 6px; min-height: 22px; }}
menubutton.ft-action > button {{ background: transparent; border-color: transparent;
    box-shadow: none; min-height: 22px; padding: 0 6px; }}
.ft-action:hover {{ background: {c['button']}; border-color: {c['button_border']}; }}
.ft-card label link, .ft-ctx label link, .ft-myreply label link {{
    text-decoration-line: none; }}
.ft-card .ft-muted link, .ft-card .ft-mono link {{ color: {c['muted']}; }}
.ft-card .ft-ctx link {{ color: {c['muted']}; }}
.ft-action.ft-active {{ background: {c['active']}; color: {c['on_active']}; }}
.ft-primary {{ background: {c['primary']}; color: {c['on_primary']}; border-radius: {br}px; }}
.ft-sidebar button.ft-primary {{ color: {c['on_primary']}; }}
.ft-status {{ color: {c['muted']}; padding: 2px 8px; font-size: smaller; }}
.ft-rail {{ border-left: 2px solid {c['rail']}; }}
.ft-avatar-circle {{ border-radius: 9999px; }}
.ft-avatar-rounded {{ border-radius: 6px; }}
.ft-avatar-square {{ border-radius: 0; }}
.ft-thumb {{ border-radius: {br}px; background: {c['ctx']}; }}
.ft-cmdline {{ background: {c['panel']}; padding: 4px 0; }}
.ft-cmdline entry {{ font-family: monospace; }}
.ft-card levelbar block.filled {{ background: {c['accent']}; }}
.ft-write {{ font-weight: bold; min-height: 34px; }}
.ft-statusbar {{ background: {c['panel']}; border-top: 1px solid {c['sidebar_border']};
                padding: 1px 0; font-size: smaller; }}
.ft-compose-panel {{ background: {c['window']}; border: 1px solid {c['focus_border']};
                    border-radius: {r}px; box-shadow: 0 6px 24px rgba(0,0,0,0.35); }}
.ft-compose-head {{ background: {c['header']}; border-radius: {br}px; padding: 2px 6px; }}
.ft-compose-frame {{ border: 1px solid {c['card_border']}; border-radius: {br}px;
                    background: {c['card']}; }}
.ft-compose-text, .ft-compose-text text {{ background: transparent; color: {c['text']}; }}
.ft-column {{ border-right: 1px solid {c['sidebar_border']}; }}
.ft-agent-face {{ background: {c['panel']}; border-left: 1px solid {c['sidebar_border']}; }}
.ft-tabrows {{ background: {c['header']}; border-bottom: 1px solid {c['header_border']};
               padding: 3px 4px 0 4px; }}
.ft-tabrows > flowboxchild {{ padding: 0; }}
.ft-compose-bar > flowboxchild {{ padding: 0; background: none; }}
.ft-tabchip {{ border: 1px solid {c['card_border']}; border-bottom: none;
              border-radius: {br}px {br}px 0 0; padding: 0 2px 0 8px; color: {c['muted']}; }}
.ft-tabrows > flowboxchild.ft-current .ft-tabchip {{ background: {c['view']};
    color: {c['text']}; border-color: {c['accent']}; }}
.ft-tabchip label {{ color: {c['muted']}; }}
.ft-tabrows > flowboxchild.ft-current .ft-tabchip label {{ color: {c['text']}; }}
.ft-tabchip-x {{ min-height: 18px; min-width: 18px; padding: 0; }}
.ft-viewer {{ background: rgba(0, 0, 0, 0.85); }}
.ft-viewer-text {{ color: #dddddd; }}
.ft-viewer-keys {{ color: #888888; font-size: smaller; }}
.ft-viewer-button {{ background: rgba(0, 0, 0, 0.47); color: rgba(255, 255, 255, 0.82);
    border: 1px solid rgba(255, 255, 255, 0.24); border-radius: 8px; padding: 4px 12px;
    box-shadow: none; }}
.ft-viewer-button:hover {{ background: rgba(255, 255, 255, 0.18); color: white; }}
.ft-play {{ background: rgba(0, 0, 0, 0.55); color: white; border-radius: 9999px;
           padding: 6px 12px; font-size: 1.4em; }}
.ft-help-toc row {{ padding: 3px 8px; }}
.ft-help-toc .ft-help-deep {{ font-weight: bold; padding-top: 8px; }}
scrollbar slider {{ margin: 0; min-width: 6px; min-height: 6px; }}
.ft-face-frame {{ border: 1px solid {c['card_border']}; border-radius: 4px;
                  background: {c['card']}; }}
"""


_provider = None


def apply(cfg, name=None):
    """Load ui.theme (or name, for this run), fall back to the reference, and style the
    whole app. Called again, it restyles it."""
    global _provider
    name = name or cfg["ui"]["theme"]
    themefile.install_copies()
    try:
        data, warnings = themefile.load(name)
    except themefile.ThemeError as e:
        data, _w = themefile.load(themefile.REFERENCE)
        warnings = [f"theme '{name}': {e} — using '{themefile.REFERENCE}'"]
    theme = Theme(data, desktop(), warnings)
    # the pictures: the theme's [shape] icons, or ui.icons (frontends/iconpack.py)
    from .. import iconpack
    theme.icon_mode = iconpack.mode(cfg, data["shape"])
    theme.split_layout = cfg["ui"].get("layout") in ("split", "qip")
    if iconpack.uses_set(theme.icon_mode):
        iconpack.missing(theme.id, iconpack.for_theme(theme))
    for w in warnings:
        log.warning("%s", w)
    mode = cfg["ui"].get("fonts", "theme")
    if mode == "custom":
        load_fonts(themefile.font_files(themefile.builtin_fonts()))
    elif mode == "theme":
        load_fonts(themefile.font_files(theme.font.get("files") or ()))
    family = {"custom": cfg["ui"].get("font") or "",
              "theme": theme.font.get("family") or ""}.get(mode, "")
    # the whole list goes to the CSS (Pango takes the first it has, as Qt does); the
    # first of them this computer has is what the status line names. Only the first
    # went before: "Tahoma" on a Linux without it became whatever fontconfig chose,
    # while Qt drew PT Sans that comes with fedtail (the night of 23.10)
    theme.font_family = first_available(family)
    css = theme.css(family, float(theme.font.get("post_scale") or 1.0))
    display = Gdk.Display.get_default()
    if display is None:
        return theme
    if _provider is not None:
        Gtk.StyleContext.remove_provider_for_display(display, _provider)
    _provider = Gtk.CssProvider()
    _load_css(_provider, css)
    Gtk.StyleContext.add_provider_for_display(
        display, _provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    return theme


GENERIC = {"serif", "sans-serif", "sans", "monospace", "cursive", "fantasy", "system-ui"}
_loaded_fonts = set()


def families(spec):
    return [f.strip().strip('"') for f in (spec or "").split(",") if f.strip()]


def css_families(spec):
    """'Tahoma, PT Sans, sans-serif' as CSS: names quoted, the generic ones bare."""
    return ", ".join(f if f in GENERIC else f'"{f}"' for f in families(spec))


def first_available(spec):
    """The first family of the list this computer has (the theme's own files loaded),
    or the first named when none is known."""
    names = families(spec)
    try:
        have = {f.get_name().lower() for f in _font_map().list_families()}
    except Exception:  # noqa: BLE001 — no font map (tests without a display)
        have = set()
    for n in names:
        if n.lower() in have:
            return n
    return names[0] if names else ""


def _font_map():
    """The font map GTK draws with (no PangoCairo typelib needed)."""
    return Gtk.Label().get_pango_context().get_font_map()


def load_fonts(paths):
    """Fonts that come with the theme (or ~/.config/fedtail/fonts/) for this run, as Qt
    loads them: Pango's own way where it has one (1.56+), fontconfig's otherwise."""
    for path in paths:
        if path in _loaded_fonts:
            continue
        _loaded_fonts.add(path)
        ok = False
        fm = None
        try:
            fm = _font_map()
            if hasattr(fm, "add_font_file"):
                ok = bool(fm.add_font_file(path))
        except Exception:  # noqa: BLE001
            ok = False
        if not ok:
            ok = _fontconfig_add(path)
            if ok and fm is not None:  # Pango learns of fontconfig's new fonts
                for again in ("config_changed", "changed"):
                    if hasattr(fm, again):
                        try:
                            getattr(fm, again)()
                        except Exception:  # noqa: BLE001
                            pass
                        break
        log.info("font %s: %s", path.rsplit("/", 1)[-1], "loaded" if ok else "not loaded")


def _fontconfig_add(path):
    import ctypes
    import ctypes.util
    name = ctypes.util.find_library("fontconfig")
    if not name:
        return False
    try:
        fc = ctypes.CDLL(name)
        fc.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        return bool(fc.FcConfigAppFontAddFile(None, path.encode()))
    except (OSError, AttributeError):
        return False


def _load_css(provider, css):
    """load_from_string is 4.12+; older GTK takes bytes."""
    if hasattr(provider, "load_from_string"):
        provider.load_from_string(css)
    else:
        provider.load_from_data(css, -1)
