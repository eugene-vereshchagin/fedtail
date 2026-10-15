"""Colours and the application stylesheet."""

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

EMOJI_FONTS = ("Noto Color Emoji", "Twemoji", "JoyPixels")


@dataclass
class Theme:
    name: str
    bg: str
    card: str
    fg: str
    muted: str
    link: str
    unread: str     # left bar of unread posts
    focus: str      # background of the post you came to in a thread
    rail: str       # thread depth line
    ctx: str        # background of the "in reply to" strip
    font: str = ""

    def stylesheet(self):
        return f"""
QScrollArea#feed, QWidget#feedBody {{ background: {self.bg}; border: 0; }}
QFrame#card {{ background: {self.card}; border-left: 3px solid {self.card};
               border-radius: 4px; }}
QFrame#card[unread="true"] {{ border-left: 3px solid {self.unread}; }}
QFrame#card[focus="true"] {{ background: {self.focus}; }}
QFrame#rail {{ background: {self.rail}; }}
QLabel#ctx {{ background: {self.ctx}; color: {self.muted}; padding: 3px 6px;
              border-left: 2px solid {self.rail}; }}
QLabel#muted, QLabel#boost, QLabel#actions {{ color: {self.muted}; }}
QLabel#myreply {{ color: {self.muted}; padding: 2px 6px;
                 border-left: 2px solid {self.unread}; }}
QLabel#cw {{ color: {self.muted}; font-style: italic; }}
QLabel#strip {{ color: {self.muted}; }}
"""


def system_theme():
    p = QApplication.palette()
    c = lambda role: p.color(role).name()
    R = QPalette.ColorRole
    base = p.color(R.Base)
    window = p.color(R.Window)
    dark = base.lightness() < 128
    card = base
    bg = window if window != base else (base.darker(106) if not dark else base.lighter(120))
    focus = p.color(R.Highlight)
    focus.setAlpha(255)
    focus = QColor(focus).lighter(185) if not dark else QColor(focus).darker(250)
    return Theme(
        name="system", bg=bg.name(), card=card.name(), fg=c(R.Text),
        muted=c(R.PlaceholderText), link=c(R.Link), unread=c(R.Highlight),
        focus=focus.name(), rail=c(R.Mid),
        ctx=(base.darker(104) if not dark else base.lighter(115)).name(),
    )


def terminal_theme():
    return Theme(
        name="terminal", bg="#000000", card="#030a05", fg="#33ff66", muted="#1f9f45",
        link="#9dffb5", unread="#33ff66", focus="#0b2e16", rail="#1f6f35", ctx="#04140a",
        font="Monospace",
    )


def apply(app, cfg):
    theme = terminal_theme() if cfg["ui"]["theme"] == "terminal" else system_theme()
    if theme.name == "terminal":
        pal = QPalette()
        R = QPalette.ColorRole
        for role, col in [(R.Window, "#000000"), (R.Base, "#000000"),
                          (R.AlternateBase, "#04140a"), (R.Text, theme.fg),
                          (R.WindowText, theme.fg), (R.Button, "#04140a"),
                          (R.ButtonText, theme.fg), (R.Link, theme.link),
                          (R.Highlight, "#1f6f35"), (R.HighlightedText, "#000000"),
                          (R.PlaceholderText, theme.muted), (R.ToolTipBase, "#000000"),
                          (R.ToolTipText, theme.fg), (R.Mid, theme.rail)]:
            pal.setColor(role, QColor(col))
        app.setPalette(pal)
        f = QFont(theme.font)
        f.setStyleHint(QFont.StyleHint.Monospace)
        app.setFont(f)
    size = cfg["ui"]["font_size"]
    f = app.font()
    if size:
        f.setPointSize(size)
    # emoji and flags come from a colour emoji font when the main one lacks them
    families = f.families() or [f.family()]
    f.setFamilies([x for x in families if x not in EMOJI_FONTS] + list(EMOJI_FONTS))
    app.setFont(f)
    app.setStyleSheet(theme.stylesheet())
    return theme
