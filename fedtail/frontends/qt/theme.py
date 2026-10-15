"""A theme file (see frontends/themefile.py) turned into Qt colours and a stylesheet."""

from datetime import UTC, datetime

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

from ...i18n import months
from .. import themefile

EMOJI_FONTS = ("Noto Color Emoji", "Twemoji", "JoyPixels")


def _mix(a, b, t):
    a, b = QColor(a), QColor(b)
    return QColor(round(a.red() * (1 - t) + b.red() * t),
                  round(a.green() * (1 - t) + b.green() * t),
                  round(a.blue() * (1 - t) + b.blue() * t))


def _auto_colors(pal):
    """Every 'auto' colour, derived from the desktop palette (works light and dark)."""
    R = QPalette.ColorRole
    base, win, text = pal.color(R.Base), pal.color(R.Window), pal.color(R.Text)
    hl, link = pal.color(R.Highlight), pal.color(R.Link)
    dark = base.lightness() < 128
    green = QColor("#3c9a3c")
    accent = hl.darker(135) if dark else hl.darker(145)
    return {
        "window": win,
        "sidebar": win.lighter(112) if dark else win.darker(104),
        "sidebar_border": _mix(win, text, 0.15),
        "selected": base.lighter(130) if dark else base,
        "selected_text": text,
        "view": base,
        "header_border": _mix(base, text, 0.12),
        "card": base.lighter(115) if dark else base,
        "card_border": _mix(base, text, 0.13),
        "card_border_unread": _mix(base, hl, 0.45),
        "text": text,
        "muted": _mix(text, base, 0.36),
        "link": link,
        "accent": accent,
        "on_accent": _readable_on(accent),
        "quiet": _mix(base, text, 0.18),
        "on_quiet": text,
        "new_pill": _mix(base, hl, 0.16),
        "on_new_pill": hl.lighter(150) if dark else hl.darker(170),
        "ctx": _mix(base, text, 0.05),
        "ctx_bar": _mix(base, text, 0.35),
        "focus": _mix(base, hl, 0.12),
        "focus_border": _mix(base, hl, 0.5),
        "myreply": _mix(base, green, 0.12),
        "on_myreply": _mix(text, green, 0.55) if not dark else green.lighter(150),
        "separator": accent,
        "rail": _mix(base, text, 0.22),
        "button": base,
        "button_border": _mix(base, text, 0.22),
        "dot": hl,
    }


class Theme:
    def __init__(self, data, palette, warnings=()):
        self.id = data["id"]
        self.name = data.get("name") or self.id
        self.font = data["font"]
        self.shape = data["shape"]
        self.words = data["words"]
        self.warnings = list(warnings)
        auto = _auto_colors(palette)
        self.c = {}
        for key, val in data["colors"].items():
            val = val.strip()
            if val == "auto":
                col = auto.get(key, QColor("#888888"))
            elif val.startswith("rgb"):
                nums = [float(x.strip().rstrip("%")) for x in val[val.index("(") + 1:-1].split(",")]
                col = QColor(int(nums[0]), int(nums[1]), int(nums[2]))
                if len(nums) > 3:
                    col.setAlphaF(nums[3] if nums[3] <= 1 else nums[3] / 255)
            else:
                col = QColor(val)
                if len(val) == 9:  # #rrggbbaa (Qt reads #aarrggbb)
                    col = QColor(val[:7])
                    col.setAlpha(int(val[7:], 16))
            self.c[key] = col
        # the old flat attributes some widgets still use
        self.muted = self.c["muted"].name()
        self.bg = self.c["view"].name()
        self.fg = self.c["text"].name()

    # ---- words --------------------------------------------------------------------
    def word(self, key, text, **kw):
        if self.words.get("lowercase"):
            text = text.lower()
        return self.words[key].format(text=text, **kw)

    def date(self, iso):
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
        except (ValueError, AttributeError):
            return ""
        now = datetime.now(UTC).astimezone()
        time = f"{dt:%H:%M}" if dt.year == now.year else str(dt.year)
        return self.words["date"].format(day=dt.day, mon=months()[dt.month - 1],
                                         dd=f"{dt.day:02d}", mm=f"{dt.month:02d}",
                                         time=time)

    # ---- stylesheet -------------------------------------------------------------------
    def css(self, key):
        c = self.c[key]
        if c.alpha() < 255:
            return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"
        return c.name()

    def stylesheet(self, base_pt, mono_family):
        k = self.css
        s = self.shape
        r, br = s["radius"], s["button_radius"]
        post_pt = round(base_pt * float(self.font["post_scale"]), 1)
        title_pt = round(base_pt * 1.55, 1)
        if s["card_style"] == "rule":
            card = (f"background: transparent; border: 0; border-radius: 0; "
                    f"border-bottom: 1px dashed {k('card_border')};")
            card_unread = "border-bottom: 1px dashed " + k("card_border")
            card_focus = (f"background: {k('focus')}; border: 1px solid {k('focus_border')}; "
                          f"border-radius: {r}px;")
            card_found = f"border: 2px solid {k('accent')}; border-radius: {r}px;"
        else:
            card = (f"background: {k('card')}; border: 1px solid {k('card_border')}; "
                    f"border-radius: {r}px;")
            card_unread = f"border-color: {k('card_border_unread')}"
            card_focus = f"background: {k('focus')}; border-color: {k('focus_border')};"
            card_found = f"border: 2px solid {k('accent')};"
        return f"""
QMainWindow, QWidget#central {{ background: {k('window')}; }}
QWidget {{ color: {k('text')}; }}
QToolTip {{ color: {k('text')}; background: {k('card')}; border: 1px solid {k('card_border')}; }}

/* ---- sidebar ---- */
QWidget#sidebar {{ background: {k('sidebar')}; border-right: 1px solid {k('sidebar_border')}; }}
QLabel#accountName {{ font-weight: 700; font-size: {round(base_pt * 1.1, 1)}pt; }}
QLabel#accountSub {{ color: {k('muted')}; }}
QLabel#sideFooter {{ color: {k('muted')}; font-size: {round(base_pt * 0.8, 1)}pt; }}
QToolButton#menu {{ border: 0; border-radius: {br}px; padding: 6px; }}
QToolButton#menu:hover {{ background: {k('selected')}; }}
QToolButton#menu::menu-indicator {{ image: none; width: 0; }}
QPushButton#compose {{ background: {k('accent')}; color: {k('on_accent')}; border: 0;
    border-radius: {br}px; padding: 11px; font-weight: 600; font-size: {round(base_pt * 1.05, 1)}pt; }}
QPushButton#compose:hover {{ background: {self.c['accent'].lighter(110).name()}; }}
QListWidget#lanes {{ background: transparent; border: 0; outline: 0; }}
QListWidget#lanes::item {{ border-radius: {br}px; margin: 1px 0; }}
QListWidget#lanes::item:selected {{ background: {k('selected')}; }}
QListWidget#lanes::item:hover:!selected {{ background: {_alpha(self.c['selected'], 110)}; }}
QLabel#laneName {{ background: transparent; }}
QLabel#laneName[current="true"] {{ font-weight: 600; color: {k('selected_text')}; }}
QLabel#badge {{ border-radius: 10px; padding: 0 7px; min-height: 20px; max-height: 20px;
    font-size: {round(base_pt * 0.85, 1)}pt;
    font-weight: 700; background: {k('accent')}; color: {k('on_accent')}; }}
QLabel#badge[kind="hot"] {{ background: {k('hot')}; color: {k('on_hot')}; }}
QLabel#badge[kind="quiet"] {{ background: {k('quiet')}; color: {k('on_quiet')}; font-weight: 600;
    border: 1px solid {k('button_border')}; }}

/* ---- tabs & lane header ---- */
QTabWidget::pane {{ border: 0; }}
QTabBar::tab {{ background: transparent; color: {k('muted')}; padding: 7px 14px; border: 0;
    border-top-left-radius: {br}px; border-top-right-radius: {br}px; }}
QTabBar::tab:selected {{ background: {k('view')}; color: {k('text')}; font-weight: 600; }}
QWidget#laneHeader {{ background: {k('view')}; border-bottom: 1px solid {k('header_border')}; }}
QLabel#laneTitle {{ font-size: {title_pt}pt; font-weight: 700; }}
QLabel#laneInfo {{ color: {k('muted')}; }}
QLabel#newPill {{ background: {k('new_pill')}; color: {k('on_new_pill')}; border-radius: 11px;
    padding: 2px 10px; font-weight: 600; }}
QPushButton#tool, QToolButton#tool {{ background: {k('button')}; color: {k('text')};
    border: 1px solid {k('button_border')}; border-radius: {br}px; padding: 6px 12px; }}
QPushButton#tool:hover, QToolButton#tool:hover {{ border-color: {k('accent')}; }}
QPushButton#seg {{ background: {k('button')}; color: {k('text')}; border: 1px solid {k('button_border')};
    padding: 6px 14px; }}
QPushButton#seg[pos="first"] {{ border-top-left-radius: {br}px; border-bottom-left-radius: {br}px;
    border-right: 0; }}
QPushButton#seg[pos="last"] {{ border-top-right-radius: {br}px; border-bottom-right-radius: {br}px; }}
QPushButton#seg:checked {{ background: {k('accent')}; color: {k('on_accent')}; font-weight: 600;
    border-color: {k('accent')}; }}
QCheckBox#check {{ color: {k('text')}; spacing: 8px; }}
QCheckBox#check::indicator {{ width: 12px; height: 12px; border: 1px solid {k('muted')};
    background: {k('view')}; border-radius: 2px; }}
QCheckBox#check::indicator:checked {{ background: {k('accent')}; }}

/* ---- inputs & dialogs ---- */
QDialog {{ background: {k('window')}; }}
QLineEdit, QPlainTextEdit, QComboBox, QListWidget#mediaList {{ background: {k('card')};
    color: {k('text')}; border: 1px solid {k('card_border')}; border-radius: {br}px; padding: 6px 8px; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {k('accent')}; }}
QPushButton#primary {{ background: {k('accent')}; color: {k('on_accent')}; border: 0;
    border-radius: {br}px; padding: 8px 18px; font-weight: 600; }}
QPushButton#primary:disabled {{ background: {k('quiet')}; color: {k('muted')}; }}
QLabel#counter {{ color: {k('muted')}; }}
QLabel#counter[over="true"] {{ color: {k('hot')}; font-weight: 700; }}

/* ---- feed ---- */
QScrollArea#feed, QWidget#feedBody {{ background: {k('view')}; border: 0; }}
QFrame#card {{ {card} }}
QFrame#card[unread="true"] {{ {card_unread} }}
QFrame#card[focus="true"] {{ {card_focus} }}
QFrame#card[found="true"] {{ {card_found} }}
QLabel#profileHeader {{ background: {k('quiet')}; color: {k('muted')}; border-radius: {r}px; }}
QWidget#findBar {{ background: {k('window')}; border-top: 1px solid {k('header_border')}; }}
QLabel#name {{ font-weight: 700; }}
QLabel#meta, QLabel#boost, QLabel#muted {{ color: {k('muted')}; }}
QLabel#shortId {{ color: {k('muted')}; font-family: "{mono_family}"; }}
QLabel#num {{ color: {k('link')}; font-family: "{mono_family}"; font-weight: 700; }}
QLabel#cameFrom {{ color: {k('link')}; font-weight: 600; }}
QLabel#dot {{ background: {k('dot')}; border-radius: 4px; }}
QLabel#star {{ color: {k('dot')}; font-weight: 700; }}
QLabel#postText {{ font-size: {post_pt}pt; }}
QLabel#ctx {{ background: {k('ctx')}; color: {k('muted')}; border-left: 3px solid {k('ctx_bar')};
    border-radius: 6px; padding: 6px 10px; }}
QLabel#myreply {{ background: {k('myreply')}; color: {k('on_myreply')}; border-radius: 6px;
    padding: 5px 10px; }}
QLabel#cw {{ color: {k('muted')}; font-style: italic; }}
QWidget#actions QToolButton {{ color: {k('muted')}; border: 0; border-radius: 6px; padding: 5px 9px; }}
QWidget#actions QToolButton:hover {{ background: {k('ctx')}; color: {k('text')}; }}
QWidget#actions QToolButton[active="true"] {{ background: {k('active')}; color: {k('on_active')};
    font-weight: 600; }}
QWidget#actions QToolButton::menu-indicator {{ image: none; width: 0; }}
QFrame#rail {{ background: {k('rail')}; }}
QLabel#sepText {{ color: {k('separator')}; font-weight: 600; }}
QFrame#sepLine {{ background: {k('separator')}; max-height: 1px; min-height: 1px; }}
QPushButton#older {{ background: transparent; color: {k('muted')}; border: 1px dashed {k('button_border')};
    border-radius: {br}px; padding: 8px; }}

QStatusBar {{ background: {k('window')}; color: {k('muted')}; }}
QStatusBar::item {{ border: 0; }}
"""


def _readable_on(bg):
    """Black or white, whichever reads better on bg."""
    r, g, b = (c / 255 for c in (bg.red(), bg.green(), bg.blue()))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return QColor("#111111") if lum > 0.45 else QColor("#ffffff")


def _alpha(col, a):
    return f"rgba({col.red()},{col.green()},{col.blue()},{a})"


def _families(spec):
    return [f.strip().strip('"') for f in (spec or "").split(",") if f.strip()]


def apply(app, cfg):
    """Load the configured theme (falling back to 'system'), style the app."""
    name = cfg["ui"]["theme"]
    themefile.install_copies()
    try:
        data, warnings = themefile.load(name)
    except themefile.ThemeError as e:
        data, _w = themefile.load(themefile.REFERENCE)
        warnings = [f"theme '{name}': {e} — using '{themefile.REFERENCE}'"]
    theme = Theme(data, app.palette(), warnings)

    if theme.c["window"] != app.palette().color(QPalette.ColorRole.Window) or \
            data["colors"].get("window", "auto") != "auto":
        # a theme with its own colours: give Qt's own widgets (menus, inputs,
        # scrollbars, dialogs) the same palette
        pal = QPalette(app.palette())
        R = QPalette.ColorRole
        for role, key in [(R.Window, "window"), (R.Base, "card"), (R.AlternateBase, "ctx"),
                          (R.Text, "text"), (R.WindowText, "text"), (R.Button, "button"),
                          (R.ButtonText, "text"), (R.Link, "link"), (R.Highlight, "accent"),
                          (R.HighlightedText, "on_accent"), (R.PlaceholderText, "muted"),
                          (R.ToolTipBase, "card"), (R.ToolTipText, "text"), (R.Mid, "rail")]:
            pal.setColor(role, theme.c[key])
        app.setPalette(pal)

    f = QFont(app.font())
    fam = _families(theme.font["family"])
    if fam:
        f.setFamilies(fam)
    size = cfg["ui"]["font_size"]
    if size:
        f.setPointSize(size)
    families = f.families() or [f.family()]
    # emoji and flags come from a colour emoji font when the main one lacks them
    f.setFamilies([x for x in families if x not in EMOJI_FONTS] + list(EMOJI_FONTS))
    app.setFont(f)
    mono = _families(theme.font["mono"]) or \
        [QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()]
    pt = f.pointSizeF() if f.pointSizeF() > 0 else 10.0
    app.setStyleSheet(theme.stylesheet(pt, mono[0]))
    return theme
