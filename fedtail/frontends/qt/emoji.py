"""The emoji picker of the editor: a small window with the standard emoji and the
server's own, and a search box. What is shown (groups, search) is common/compose.py's;
this only draws it and hands the chosen text to `put`."""

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFontMetrics, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...i18n import _
from ..common import compose as cc

COLUMNS = 10
# a cell: the button's own padding off (the theme's 12 px a side left 8 px of a 34 px
# button for the emoji: all of them cut to a sliver, 19.11), its size from the font
CELL_STYLE = "QPushButton {{ padding: 0px; font-size: {pt:.1f}pt; }}"


class EmojiPicker(QDialog):
    """Standard / Server's tabs over a search field; a click puts the emoji in the text."""

    def __init__(self, parent, win, put):
        """put(text): inserts into the editor; win: the main window (bridge, images)."""
        super().__init__(parent)
        self.win, self.core, self.put = win, win.ctx.view, put
        self.setWindowTitle(_("emoji_title"))
        self._glyph = self.font()
        if self._glyph.pointSizeF() > 0:
            self._glyph.setPointSizeF(self._glyph.pointSizeF() * 1.5)
        self._side = max(38, QFontMetrics(self._glyph).height() + 12)
        self.resize(COLUMNS * (self._side + 2) + 60, 420)
        self._server = None  # the server's emoji once they came; None: not yet
        self._failed = False
        lay = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(_("emoji_search"))
        self.search.setClearButtonEnabled(True)
        lay.addWidget(self.search)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self.standard = self._scroll()
        self.server = self._scroll()
        self.has_standard = bool(self.core.cfg["post"].get("emoji_standard", True))
        if self.has_standard:
            self.tabs.addTab(self.standard[0], _("emoji_tab_standard"))
        self.tabs.addTab(self.server[0], _("emoji_tab_server"))
        # the emoji's options, at hand where emoji are picked (none found them, 19.11)
        self.settings_btn = QPushButton(_("emoji_settings"))
        self.settings_btn.setObjectName("tool")
        self.settings_btn.setToolTip(_("emoji_settings_tip"))
        self.settings_btn.clicked.connect(self.open_settings)
        lay.addWidget(self.settings_btn, 0, Qt.AlignmentFlag.AlignLeft)
        # typing in the box waits a moment: the core searches on every change
        self._timer = QTimer(self, singleShot=True, interval=150)
        self._timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda _t: self._timer.start())
        self.refresh()
        win.bridge.call(self.core.emoji_all(), ok=self._got, fail=self._lost)
        self.search.setFocus()

    def open_settings(self):
        """The settings window, its search at the emoji options."""
        self.close()
        self.win.open_settings("emoji")

    @staticmethod
    def _scroll():
        area = QScrollArea()
        area.setWidgetResizable(True)
        body = QWidget()
        box = QVBoxLayout(body)
        box.setAlignment(Qt.AlignmentFlag.AlignTop)
        area.setWidget(body)
        return area, box

    def _got(self, items):
        self._server = list(items or [])
        self.refresh()

    def _lost(self, _err):
        self._server, self._failed = [], True
        self.refresh()

    @staticmethod
    def _clear(box):
        while box.count():
            w = box.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def refresh(self):
        """Redraw both tabs for what is in the search box."""
        words = self.search.text()
        if self.has_standard:
            self._fill(self.standard[1], cc.emoji_standard(self.core, words),
                       lambda e: (e["char"], ":" + e["code"] + ":", e["char"], None))
        if self._server is None:
            groups = []
        else:
            groups = cc.emoji_server(self._server, words)
        self._fill(self.server[1], groups,
                   lambda e: (":" + e["shortcode"] + ":", ":" + e["shortcode"] + ":",
                              ":" + e["shortcode"] + ": ", e.get("static_url") or e.get("url")),
                   _("emoji_server_none") if self._server == [] and not words.strip() else "")

    def _fill(self, box, groups, describe, empty_text=""):
        self._clear(box)
        if not any(items for _t, items in groups):
            box.addWidget(QLabel(empty_text or _("emoji_none")))
            return
        for title, items in groups:
            if title:
                head = QLabel(f"<b>{title}</b>")
                box.addWidget(head)
            grid_w = QWidget()
            grid = QGridLayout(grid_w)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(2)
            grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            for n, e in enumerate(items):
                label, tip, inserted, url = describe(e)
                b = QPushButton("" if url else label)
                b.setObjectName("tool")
                b.setFlat(True)
                b.setToolTip(tip)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setStyleSheet(CELL_STYLE.format(pt=self._glyph.pointSizeF()))
                b.setFixedSize(self._side, self._side)
                b.clicked.connect(lambda _c=False, s=inserted: self.put(s))
                if url:
                    self._picture(b, url)
                grid.addWidget(b, n // COLUMNS, n % COLUMNS)
            box.addWidget(grid_w)

    def _picture(self, button, url):
        """The emoji's picture on its button (the label shows till it comes)."""
        images = getattr(self.win, "images", None)
        button.setText(button.toolTip()[1:3])
        if images is None:
            return

        def show(pm):
            try:
                if pm is not None and not pm.isNull():
                    button.setText("")
                    button.setIcon(QIcon(pm))
                    side = self._side - 10
                    button.setIconSize(QSize(side, side))
            except RuntimeError:  # the list was redrawn meanwhile
                pass
        images.get(url, show, 128, owner=button)
