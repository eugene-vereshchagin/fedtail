"""A theme file (see frontends/themefile.py) turned into Qt colours and a stylesheet."""

from datetime import UTC, datetime

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

from ...i18n import months
from .. import palette, themefile

EMOJI_FONTS = ("Noto Color Emoji", "Twemoji", "JoyPixels")


def stripe_tile(color, size=10, width=3):
    """A small square of diagonal stripes (45°, seamless when repeated) in a shade a
    little darker than color, as a PNG in the temp folder; its path, or "" if it can't
    be written."""
    import tempfile
    from pathlib import Path

    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QImage, QPainter, QPen
    path = Path(tempfile.gettempdir()) / f"fedtail-stripes-{color.name()[1:]}-{size}.png"
    if not path.exists():
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(color)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(color.darker(108), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        for off in (-size, 0, size):  # the line and its neighbours, so the edges meet
            p.drawLine(QPointF(off, size), QPointF(off + size, 0))
        p.end()
        if not img.save(str(path), "PNG"):
            return ""
    return path.as_posix()


def desktop_of(pal):
    """What palette.py needs of the desktop's QPalette."""
    R = QPalette.ColorRole

    def c(role):
        q = pal.color(role)
        return palette.Color(q.red(), q.green(), q.blue(), q.alpha())
    return palette.Desktop(base=c(R.Base), window=c(R.Window), text=c(R.Text),
                           highlight=c(R.Highlight), link=c(R.Link))


def _q(col):
    return QColor(col.r, col.g, col.b, col.a)


class Theme:
    def __init__(self, data, pal, warnings=()):
        self.id = data["id"]
        self.name = data.get("name") or self.id
        self.font = data["font"]
        self.shape = data["shape"]
        self.words = data["words"]
        self.icon = data.get("icon", {})
        self.icon_dirs = list(data.get("icon_dirs") or ())  # the theme's own pictures
        self.pictures = data.get("pictures") or {}  # how they're coloured, from where
        self.icon_mode = "desktop"  # where the pictures come from: set by apply()
        self.split_layout = False
        self.warnings = list(warnings)
        # every colour worked out by palette.py (the GTK window's too): "auto" from the
        # desktop's palette, the ones that follow or tint others
        self.c = {k: _q(v) for k, v in palette.resolve(data["colors"],
                                                       desktop_of(pal)).items()}
        # the old flat attributes some widgets still use
        self.muted = self.c["muted"].name()
        self.bg = self.c["view"].name()
        self.fg = self.c["text"].name()

    # ---- words --------------------------------------------------------------------
    def word(self, key, text, **kw):
        if self.words.get("lowercase"):
            text = text.lower()
        return self.words[key].format(text=text, **kw)

    def date(self, iso, fmt=None):
        """A time as the theme writes it (words.date, or fmt): an aware datetime (the
        model's) or ISO text. Placeholders: {day} {mon} {time} (the year, for another
        year) {dd} {mm} {yyyy} {clock} (HH:MM) {secs} (HH:MM:SS)."""
        if isinstance(iso, datetime):
            dt = iso.astimezone()
        else:
            try:
                dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
            except (ValueError, AttributeError):
                return ""
        now = datetime.now(UTC).astimezone()
        time = f"{dt:%H:%M}" if dt.year == now.year else str(dt.year)
        return (fmt or self.words["date"]).format(
            day=dt.day, mon=months()[dt.month - 1], dd=f"{dt.day:02d}", mm=f"{dt.month:02d}",
            yyyy=dt.year, yy=f"{dt:%y}", time=time, clock=f"{dt:%H:%M}",
            secs=f"{dt:%H:%M:%S}")

    # ---- stylesheet -------------------------------------------------------------------
    def css(self, key):
        c = self.c[key]
        if c.alpha() < 255:
            return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"
        return c.name()

    def _stripes_css(self):
        """shape.header_stripes: a hatched band behind titles (point.im's header), a
        tile drawn in the theme's header colour and kept in the temp folder."""
        if not self.shape.get("header_stripes"):
            return ""
        path = stripe_tile(self.c["header"])
        return f"background-image: url({path}); background-repeat: repeat-xy;" if path else ""

    def _bar_css(self):
        """shape.header_bar: a band of colors.header_bar above the title strip (the dark
        top bar of point.im over its hatched header), that many pixels high."""
        px = int(self.shape.get("header_bar") or 0)
        return f"border-top: {px}px solid {self.css('header_bar')};" if px > 0 else ""

    def _bg(self, key):
        """A background: the colour, or — with colors.<key>_end other than it — a
        vertical gradient down to that (the Agent's and QIP's glossy windows, bars and
        buttons)."""
        end = self.c.get(key + "_end")
        if end is None or end == self.c[key]:
            return self.css(key)
        return (f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {self.css(key)}, "
                f"stop:1 {end.name()})")

    def _view_gradient_css(self):
        """colors.view_end other than view: the posts and the input line on a pale
        diagonal gradient, as QIP Infium had them (white top right, tinted lower left)."""
        if self.c["view_end"] == self.c["view"]:
            return ""
        # white over most of it, the tint only towards the lower left (as Infium's)
        g = (f"qlineargradient(x1:1, y1:0, x2:0, y2:1, stop:0 {self.css('view')}, "
             f"stop:0.4 {self.css('view')}, stop:1 {self.css('view_end')})")
        # on the scroll area itself: Qt paints a QAbstractScrollArea's background into its
        # viewport, and the earlier flat rule for it won over one on the viewport
        return (f"QScrollArea#feed {{ background: {g}; }}\n"
                f"QWidget#feedBody {{ background: transparent; }}\n"
                f"QPlainTextEdit#dockText {{ background: {g}; }}")

    def stylesheet(self, base_pt, mono_family):
        k = self.css
        s = self.shape
        r, br = s["radius"], s["button_radius"]
        post_pt = round(base_pt * float(self.font["post_scale"]), 1)
        title_pt = round(base_pt * 1.55, 1)
        if s["card_style"] == "rule":
            line = "solid" if s.get("rule") == "solid" else "dashed"
            card = (f"background: transparent; border: 0; border-radius: 0; "
                    f"border-bottom: 1px {line} {k('card_border')};")
            card_unread = f"border-bottom: 1px {line} " + k("card_border")
            card_focus = (f"background: {k('focus')}; border: 1px solid {k('focus_border')}; "
                          f"border-radius: {r}px;")
            card_found = f"border: 2px solid {k('accent')}; border-radius: {r}px;"
        else:
            card = (f"background: {k('card')}; border: 1px solid {k('card_border')}; "
                    f"border-radius: {r}px;")
            card_unread = f"border-color: {k('card_border_unread')}"
            card_focus = f"background: {k('focus')}; border-color: {k('focus_border')};"
            card_found = f"border: 2px solid {k('accent')};"
        return self._stylesheet(k, s, r, br, post_pt, title_pt, base_pt, mono_family, card,
                                card_unread, card_focus, card_found) + \
            (self._ticks(k) if s.get("icons") != "desktop" else "") + \
            (DEBUG_CSS if s.get("debug") else "")

    @staticmethod
    def _ticks(k):
        """Check boxes and radio buttons in the theme's colours: the desktop's style
        took the theme's button colour for the box, so an empty box in bnw was as
        green as a ticked one. Empty — the card's colour, a frame; ticked — the accent.
        (The system and debug themes keep the desktop's own.)"""
        return f"""
QCheckBox::indicator {{ width: 13px; height: 13px; border: 1px solid {k('muted')};
    background: {k('card')}; border-radius: 3px; }}
QCheckBox::indicator:checked {{ background: {k('accent')}; border-color: {k('accent')}; }}
QCheckBox::indicator:indeterminate {{ background: {k('muted')}; }}
QCheckBox::indicator:disabled {{ border-color: {k('rail')}; }}
QRadioButton::indicator {{ width: 13px; height: 13px; border: 1px solid {k('muted')};
    background: {k('card')}; border-radius: 7px; }}
QRadioButton::indicator:checked {{ background: qradialgradient(cx: 0.5, cy: 0.5, radius: 0.5,
    fx: 0.5, fy: 0.5, stop: 0 {k('accent')}, stop: 0.55 {k('accent')}, stop: 0.6 {k('card')},
    stop: 1 {k('card')}); border-color: {k('accent')}; }}
"""

    def _stylesheet(self, k, s, r, br, post_pt, title_pt, base_pt, mono_family, card,
                    card_unread, card_focus, card_found):
        return f"""
QMainWindow, QWidget#central {{ background: {self._bg('window')}; }}
QWidget {{ color: {k('text')}; }}
QToolTip {{ color: {k('text')}; background: {k('card')}; border: 1px solid {k('card_border')}; }}
QFrame#hintPopup {{ background: {k('card')}; border: 1px solid {k('accent')}; border-radius: 4px; }}
QLabel#hintText {{ color: {k('text')}; background: transparent; }}

/* ---- sidebar ---- */
QWidget#sidebar {{ background: {k('sidebar')}; border-right: 1px solid {k('sidebar_border')}; }}
QLabel#accountName, QLabel#laneName, QToolButton#menu {{ color: {k('sidebar_text')}; }}
QLabel#accountSub, QLabel#sideFooter, QLabel#listsHeader {{ color: {k('sidebar_muted')}; }}
QLabel#accountName {{ font-weight: 700; font-size: {round(base_pt * 1.1, 1)}pt; }}
QLabel#sideFooter {{ font-size: {round(base_pt * 0.8, 1)}pt; }}
QToolButton#menu {{ border: 0; border-radius: {br}px; padding: 6px; }}
QToolButton#menu:hover {{ background: {k('selected')}; }}
QToolButton#menu:checked {{ background: {k('selected')}; color: {k('accent')}; }}
QToolButton#menu::menu-indicator {{ image: none; width: 0; }}
QSplitter#sideSplit::handle {{ background: transparent; }}
QSplitter#sideSplit::handle:hover {{ background: {k('selected')}; }}
QPushButton#compose {{ background: {k('primary')}; color: {k('on_primary')}; border: 0;
    border-radius: {br}px; padding: 11px; font-weight: 600; font-size: {round(base_pt * 1.05, 1)}pt; }}
QPushButton#compose:hover {{ background: {self.c['primary'].lighter(110).name()}; }}
QListWidget#lanes {{ background: transparent; border: 0; outline: 0; }}
QListWidget#lanes::item {{ border-radius: {br}px; margin: 1px 0; }}
QListWidget#lanes::item:selected {{ background: {k('selected')}; }}
QListWidget#lanes QScrollBar:vertical {{ background: {k('sidebar')}; width: 8px; margin: 0;
    border: 0; }}
QListWidget#lanes QScrollBar::handle:vertical {{ background: {k('rail')}; min-height: 24px;
    border-radius: 4px; margin: 1px; }}
QListWidget#lanes QScrollBar::add-line:vertical, QListWidget#lanes QScrollBar::sub-line:vertical
    {{ height: 0; border: 0; }}
QListWidget#lanes QScrollBar::add-page:vertical, QListWidget#lanes QScrollBar::sub-page:vertical
    {{ background: none; }}
QListWidget#lanes::item:hover:!selected {{ background: {_alpha(self.c['selected'], 110)}; }}
QLabel#laneName {{ background: transparent; }}
QLabel#listsHeader {{ font-weight: 600; background: transparent; }}
QLabel#laneName[current="true"] {{ font-weight: 600; color: {k('selected_text')}; }}
QListWidget#rosterList {{ outline: 0; }}
QListWidget#rosterList::item:selected {{ background: {k('selected')}; color: {k('selected_text')}; }}
QListWidget#rosterList::item:hover:!selected {{ background: {_alpha(self.c['selected'], 110)}; }}
QLabel#rosterName, QLabel#rosterLine, QLabel#rosterGroup {{ background: transparent; }}
QLabel#rosterName[unread="true"] {{ color: {k('hot')}; }}
QLabel#rosterLine {{ color: {k('muted')}; font-style: italic;
    font-size: {round(base_pt * 0.85, 1)}pt; }}
QLabel#rosterGroup {{ color: {k('sidebar_muted')}; font-weight: 700; }}
QLabel#rosterStatus {{ color: {k('muted')}; background: transparent;
    font-size: {round(base_pt * 0.9, 1)}pt; }}
QLabel#rosterNews {{ font-size: {round(base_pt * 0.85, 1)}pt; }}
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
QWidget#roster {{ background: {self._bg('window')}; }}
QWidget#messageTabs {{ background: {self._bg('window')}; }}
QFrame#msgTab {{ background: {self._bg('button')}; border: 1px solid {k('button_border')};
    border-bottom: 0; border-top-left-radius: {br}px; border-top-right-radius: {br}px; }}
QFrame#msgTab:hover {{ background: {k('selected')}; }}
QFrame#msgTab[current="true"] {{ background: {k('view')}; border-top: 2px solid {k('tab_mark')}; }}
QFrame#msgTab QLabel {{ background: transparent; }}
QFrame#msgTab[current="true"] QLabel#msgTabText {{ font-weight: 600; }}
QToolButton#msgTabClose {{ border: 0; background: transparent; color: {k('hot')};
    font-weight: 700; padding: 0 2px; }}
QToolButton#msgTabClose:hover {{ background: {k('hot')}; color: {k('on_hot')}; border-radius: 2px; }}
QWidget#authorBar {{ background: {self._bg('header')}; border-bottom: 1px solid {k('header_border')}; }}
QSplitter#readWrite::handle {{ background: {k('header_border')}; margin: 1px 0; }}
QSplitter#readWrite::handle:hover {{ background: {k('selected')}; }}
QWidget#inputDock {{ background: {self._bg('header')}; }}
QWidget#contactCard {{ background: {k('card')}; border: 1px solid {k('accent')};
    border-radius: {br}px; }}
QWidget#agentFace {{ background: {k('panel')}; border-left: 1px solid {k('card_border')}; }}
QLabel#faceFrame {{ border: 1px solid {k('card_border')}; background: {k('card')}; }}
QLabel#faceName {{ font-weight: 600; background: transparent; }}
QTabBar#messageTabs::tab {{ background: {k('button')}; color: {k('text')};
    border: 1px solid {k('button_border')}; border-bottom: 0; margin: 3px 1px 0 1px;
    padding: 4px 10px; border-top-left-radius: {br}px; border-top-right-radius: {br}px; }}
QTabBar#messageTabs::tab:selected {{ background: {k('view')}; margin-top: 0;
    padding-bottom: 7px; font-weight: 600; }}
QTabBar#messageTabs::tab:hover:!selected {{ background: {k('selected')}; }}
QWidget#composeHead {{ background: {self._bg('header')};
    {self._stripes_css()} {self._bar_css()} border-radius: {br}px; }}
QWidget#laneHeader {{ background: {self._bg('header')}; {self._stripes_css()} {self._bar_css()} border-bottom: 1px solid {k('header_border')}; }}
QLabel#laneTitle {{ font-size: {title_pt}pt; font-weight: 700; }}
QWidget#laneHeader[slim="true"] QLabel#laneTitle {{ font-size: {round(base_pt * 1.15, 1)}pt; }}
QLabel#laneInfo {{ color: {k('muted')}; }}
QLabel#loadingPlate {{ background: {k('view')}; color: {k('muted')};
    border: 1px solid {k('header_border')}; border-radius: 12px; padding: 8px 18px; }}
QLabel#newPill {{ background: {k('new_pill')}; color: {k('on_new_pill')}; border-radius: 11px;
    padding: 2px 10px; font-weight: 600; }}
QPushButton#tool, QToolButton#tool {{ background: {self._bg('button')}; color: {k('text')};
    border: 1px solid {k('button_border')}; border-radius: {br}px; padding: 6px 12px; }}
QPushButton#tool:hover, QToolButton#tool:hover {{ border-color: {k('accent')}; }}
QPushButton#seg {{ background: {self._bg('button')}; color: {k('text')}; border: 1px solid {k('button_border')};
    padding: 6px 14px; }}
QPushButton#seg[pos="first"] {{ border-top-left-radius: {br}px; border-bottom-left-radius: {br}px;
    border-right: 0; }}
QPushButton#seg[pos="last"] {{ border-top-right-radius: {br}px; border-bottom-right-radius: {br}px; }}
QPushButton#seg[pos="middle"] {{ border-right: 0; border-radius: 0; }}
QPushButton:disabled {{ color: {k('muted')}; }}
QPushButton#seg:checked {{ background: {k('accent')}; color: {k('on_accent')}; font-weight: 600;
    border-color: {k('accent')}; }}
QCheckBox#check {{ color: {k('text')}; spacing: 8px; }}
QCheckBox#check::indicator {{ width: 12px; height: 12px; border: 1px solid {k('muted')};
    background: {k('view')}; border-radius: 2px; }}
QCheckBox#check::indicator:checked {{ background: {k('accent')}; }}
QRadioButton#check {{ color: {k('text')}; spacing: 6px; }}

/* ---- inputs & dialogs ---- */
QDialog {{ background: {k('panel')}; }}
QLineEdit, QPlainTextEdit, QComboBox, QListWidget#mediaList {{ background: {k('card')};
    color: {k('text')}; border: 1px solid {k('card_border')}; border-radius: {br}px; padding: 6px 8px; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {k('accent')}; }}
QPushButton#primary {{ background: {k('primary')}; color: {k('on_primary')}; border: 0;
    border-radius: {br}px; padding: 8px 18px; font-weight: 600; }}
QPushButton#primary:disabled {{ background: {k('quiet')}; color: {k('muted')}; }}
QLabel#counter {{ color: {k('muted')}; }}
QLabel#counter[over="true"] {{ color: {k('hot')}; font-weight: 700; }}

/* ---- feed ---- */
QScrollArea#feed, QWidget#feedBody {{ background: {k('view')}; border: 0; }}
{self._view_gradient_css()}
QFrame#card {{ {card} }}
QFrame#card[unread="true"] {{ {card_unread} }}
QFrame#card[focus="true"] {{ {card_focus} }}
QFrame#card[found="true"] {{ {card_found} }}
QFrame#card[keyed="true"] {{ {card_found} }}
QLabel#media {{ background: {k('quiet')}; color: {k('muted')}; border-radius: {r}px; }}
QLabel#profileHeader {{ background: {k('quiet')}; color: {k('muted')}; border-radius: {r}px; }}
QFrame#profileCard {{ background: {_alpha(self.c['accent'], 22)};
    border: 1px solid {_alpha(self.c['accent'], 90)}; border-left: 4px solid {k('accent')};
    border-radius: {r}px; margin-bottom: 4px; }}
QFrame#profileCard[focus="true"] {{ border: 2px solid {k('accent')};
    border-left: 4px solid {k('accent')}; }}
QLabel#profileBanner {{ border-radius: {r}px; background: {k('quiet')}; }}
QLabel#profileName {{ font-size: {round(base_pt * 1.35, 1)}pt; font-weight: 700;
    background: transparent; }}
QLabel#sectionTitle {{ color: {k('muted')}; font-weight: 600; padding: 10px 4px 2px 4px;
    border-bottom: 1px solid {k('card_border')}; }}
QWidget#findBar {{ background: {k('panel')}; border-top: 1px solid {k('header_border')}; }}
QLabel#name {{ font-weight: 700; }}
QLabel#meta, QLabel#boost, QLabel#muted {{ color: {k('muted')}; }}
QLabel#shortId {{ color: {k('muted')}; font-family: "{mono_family}"; }}
QLabel#num {{ color: {k('link')}; font-family: "{mono_family}"; font-weight: 700; }}
QLabel#cameFrom {{ color: {k('link')}; font-weight: 600; }}
QDialog#composePanel {{ background: {k('panel')}; border: 1px solid {k('accent')};
    border-radius: {r}px; }}
QFrame#quoteBox {{ background: {k('ctx')}; border: 1px solid {k('card_border')};
    border-left: 3px solid {k('ctx_bar')}; border-radius: {r}px; }}
QFrame#quoteBox:hover {{ border-color: {k('accent')}; }}
QFrame#quoteBox QLabel {{ background: transparent; }}
QLabel#quoteHead, QLabel#quoteNote {{ color: {k('muted')}; }}
QLabel#altCaption {{ color: {k('muted')}; font-size: {round(base_pt * 0.9, 1)}pt; }}
QFrame#announceBar {{ background: {k('ctx')}; border-bottom: 1px solid {k('card_border')};
    border-left: 3px solid {k('accent')}; }}
QFrame#announceBar QLabel {{ background: transparent; }}
QLabel#announceHead {{ color: {k('muted')}; font-weight: 600; }}
QFrame#linkCard {{ background: {k('ctx')}; border: 1px solid {k('card_border')};
    border-radius: {r}px; }}
QFrame#linkCard:hover {{ border-color: {k('accent')}; }}
QFrame#linkCard QLabel {{ background: transparent; }}
QLabel#linkCardSite {{ color: {k('muted')}; font-size: {round(base_pt * 0.85, 1)}pt; }}
QLabel#linkCardText {{ color: {k('muted')}; }}
QLabel#linkCardImage {{ background: {k('quiet')}; border-top-left-radius: {r}px;
    border-bottom-left-radius: {r}px; }}
QLabel#via {{ color: {k('on_quiet')}; background: {k('quiet')}; border-radius: 8px;
    padding: 0 7px; font-size: {round(base_pt * 0.85, 1)}pt; }}
QProgressBar#pollBar {{ background: {k('quiet')}; border: 0; border-radius: 3px;
    min-height: 6px; max-height: 6px; }}
QProgressBar#pollBar::chunk {{ background: {_alpha(self.c['accent'], 150)}; border-radius: 3px; }}
QProgressBar#pollBar[mine="true"]::chunk {{ background: {k('accent')}; }}
QRadioButton#pollChoice, QCheckBox#pollChoice {{ color: {k('text')}; spacing: 8px; }}
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

QStatusBar {{ background: {self._bg('window')}; color: {k('muted')}; }}
QStatusBar::item {{ border: 0; }}
"""


def _alpha(col, a):
    return f"rgba({col.red()},{col.green()},{col.blue()},{a})"


GENERIC = {"sans-serif", "serif", "monospace"}


def _families(spec):
    """The theme's font list, only fonts that are actually installed. Handing Qt a
    missing name makes fontconfig substitute something — sometimes with absurd
    metrics; a generic name at the end ("serif") becomes the matching system face."""
    wanted = [f.strip().strip('"') for f in (spec or "").split(",") if f.strip()]
    if not wanted:
        return []
    have = {f.lower() for f in QFontDatabase.families()}
    out = [f for f in wanted if f.lower() in have]
    if not out:
        generic = next((f for f in wanted if f in GENERIC), None)
        hint = {"serif": QFont.StyleHint.Serif, "monospace": QFont.StyleHint.Monospace}.get(
            generic, QFont.StyleHint.SansSerif)
        probe = QFont()
        probe.setStyleHint(hint)
        out = [probe.defaultFamily()] if generic else []
    return out


_loaded_fonts = set()

# the classes a platform theme may give a font of their own (Qt's
# QApplicationPrivate::initializeWidgetFontHash): a theme's font is set on them too
CLASS_FONTS = ("QLabel", "QStatusBar", "QAbstractItemView", "QListView", "QHeaderView",
               "QPushButton", "QCheckBox", "QRadioButton", "QToolButton", "QMenu",
               "QMenuBar", "QMessageBox", "QTipLabel", "QDockWidgetTitle",
               "QComboMenuItem", "QComboLineEdit", "QMdiSubWindowTitleBar", "QListBox",
               "QMenuItem")


def _load_fonts(theme_files):
    """Fonts that come with the theme or lie in ~/.config/fedtail/fonts/: given to Qt for
    this run, nothing installed. Each file once."""
    import logging
    for path in themefile.font_files(theme_files):
        if path in _loaded_fonts:
            continue
        _loaded_fonts.add(path)
        fid = QFontDatabase.addApplicationFont(path)
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        import os
        logging.getLogger(__name__).info("font %s: %s", os.path.basename(path),
                                         ", ".join(fams) or "not readable")


# the desktop's own palette and font, as they were before any theme touched them: a
# theme tried from the menu (≡ → Try a theme) starts from these, not from the last one
_desktop = None


def apply(app, cfg, name=None):
    """Load the configured theme — or `name`, tried for this run only — falling back to
    'system', and style the app. Called again, it restyles the running app."""
    global _desktop
    name = name or cfg["ui"]["theme"]
    if _desktop is None:
        from . import kde
        adopted = kde.adopt(app)
        if adopted:
            import logging
            logging.getLogger(__name__).info("Qt has no KDE integration here (one-file "
                                             "build?): %s from kdeglobals", adopted)
        themefile.install_copies()
        _desktop = (QPalette(app.palette()), QFont(app.font()),
                    {c: QFont(app.font(c)) for c in CLASS_FONTS})
    else:
        app.setPalette(QPalette(_desktop[0]))
        app.setFont(QFont(_desktop[1]))
        for c, font in _desktop[2].items():
            app.setFont(QFont(font), c)
    try:
        data, warnings = themefile.load(name)
    except themefile.ThemeError as e:
        data, _w = themefile.load(themefile.REFERENCE)
        warnings = [f"theme '{name}': {e} — using '{themefile.REFERENCE}'"]
    theme = Theme(data, app.palette(), warnings)
    # the pictures: the theme's [shape] icons, or ui.icons (frontends/iconpack.py)
    from .. import iconpack
    theme.icon_mode = iconpack.mode(cfg, data["shape"])
    theme.split_layout = cfg["ui"].get("layout") in ("split", "qip")
    if iconpack.uses_set(theme.icon_mode):
        iconpack.missing(theme.id, iconpack.for_theme(theme))

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

    # ui.fonts: "theme" — the theme's (it may bring them along); "system" — the
    # desktop's, whatever the theme says; "custom" — ui.font / ui.mono_font, from the
    # system, ~/.config/fedtail/fonts/ or the fonts that come with fedtail
    mode = cfg["ui"].get("fonts", "theme")
    if mode == "custom":
        _load_fonts(themefile.builtin_fonts())
    elif mode == "theme":
        _load_fonts(theme.font.get("files") or ())
    f = QFont(app.font())
    if mode == "custom":
        fam = _families(cfg["ui"].get("font") or "")
    elif mode == "theme":
        fam = _families(theme.font["family"])
    else:
        fam = []
    if fam:
        f.setFamilies(fam)
    size = cfg["ui"]["font_size"]
    if size:
        f.setPointSize(size)
    families = f.families() or [f.family()]
    # emoji and flags come from a colour emoji font when the main one lacks them
    f.setFamilies([x for x in families if x not in EMOJI_FONTS] + list(EMOJI_FONTS))
    app.setFont(f)
    if fam or size:
        # the desktop's platform theme gives some classes fonts of their own (KDE: labels,
        # buttons, lists, the status bar), and those beat the application's: on KDE the
        # cards, the lanes and the status bar of a monospace theme came out in the
        # desktop's sans while its inputs were monospace (the night of 23.10, bnw)
        for c in CLASS_FONTS:
            app.setFont(f, c)
    mono = _families({"custom": cfg["ui"].get("mono_font") or "",
                      "theme": theme.font["mono"]}.get(mode, "")) or \
        [QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()]
    pt = f.pointSizeF() if f.pointSizeF() > 0 else 10.0
    app.setStyleSheet(theme.stylesheet(pt, mono[0]))
    import sys
    card = sys.modules.get(__package__ + ".card")
    if card is not None:  # the buttons' widths, measured under the old look: anew
        card._HINTS.clear()
    return theme


# shape.debug = true (the "debug" theme): every state a card can be in, loud and each
# its own, so a mark that doesn't come or doesn't go is seen at once. Last in the
# stylesheet: it wins over the theme's own rules.
DEBUG_CSS = """
QFrame#card[unread="true"] { border: 3px dashed #ff2bd6; }
QFrame#card[glimpsed="true"] { border: 3px dotted #ffb000; }
QFrame#card[keyed="true"] { border: 3px solid #39ff14; }
QFrame#card[found="true"] { border: 3px solid #00e5ff; }
QFrame#card[focus="true"] { background: #3a3200; border: 3px solid #ffe600; }
QFrame#card:hover { background: #2a2f3a; }
QWidget:focus { border: 2px solid #ff3b30; }
QPushButton:disabled, QToolButton:disabled { color: #ff3b30; text-decoration: line-through; }
QLabel#muted:hover, QLabel#meta:hover { background: #40263d; }
"""

