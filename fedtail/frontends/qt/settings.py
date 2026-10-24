"""The settings window: the chapters of config.toml on the left, the options of one on
the right — each a card with its name, its control, the explanation the reference gives
and "Default" when it is set to something else. What it shows and what saving does is
common/settings.py's: a change is written into the file at once (that line only), and
the window offers to restart, as most options are read at start. The file stays the
one place the settings live: edited outside while the window is open, it is read again.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...i18n import _
from ..common import settings as model_of

log = logging.getLogger(__name__)

FOUND = "\x00found"  # the list's row for what the search found


def _short(words, n=70):
    return words if len(words) <= n else words[:n - 3].rsplit(" ", 1)[0] + "…"


class SettingsDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.view = win.ctx.view
        self.setWindowTitle(_("settings_title"))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.path = model_of.config_file(self.view)
        self.stamp = self._stamp()
        self.chapters = model_of.model(self.view)
        k = win.theme.css
        self.setStyleSheet(f"""
QFrame#setCard {{ background: {k('card')}; border: 1px solid {k('card_border')};
                  border-radius: 8px; }}
QFrame#setCard QLabel {{ background: transparent; border: 0; }}
QFrame#setCard[changed="true"] {{ border-left: 3px solid {k('accent')}; }}
QLabel#setTitle {{ font-weight: 600; }}
QLabel#setAbout {{ color: {k('muted')}; }}
QLabel#setName {{ color: {k('muted')}; font-family: monospace; font-size: 8.5pt; }}
QLabel#setGroup {{ color: {k('accent')}; font-size: 11pt; padding-top: 6px; }}
QLabel#setMuted {{ color: {k('muted')}; }}
""")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 10)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(_("settings_search"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self._timer.start())
        top.addWidget(self.search, 1)
        lay.addLayout(top)
        self._timer = QTimer(self, singleShot=True, interval=250)
        self._timer.timeout.connect(self._searched)

        split = QSplitter()
        self.list = QListWidget()
        self.list.setMinimumWidth(190)
        for ch in self.chapters:
            item = QListWidgetItem(f"{ch.number}. {ch.title}")
            item.setData(Qt.ItemDataRole.UserRole, ch.key)
            self.list.addItem(item)
        self.list.currentItemChanged.connect(lambda cur, _p: cur and self.show_chapter(
            cur.data(Qt.ItemDataRole.UserRole)))
        split.addWidget(self.list)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        split.addWidget(self.scroll)
        split.setStretchFactor(1, 1)
        split.setSizes([210, 640])
        lay.addWidget(split, 1)

        hint = QLabel(_("settings_hint", file=str(self.path)))
        hint.setObjectName("setMuted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        bottom = QHBoxLayout()
        self.status = QLabel("")
        self.status.setWordWrap(True)
        bottom.addWidget(self.status, 1)
        open_file = QPushButton(_("settings_open_file"))
        open_file.setObjectName("tool")
        open_file.clicked.connect(self._open_file)
        bottom.addWidget(open_file)
        self.restart = QPushButton(_("settings_restart"))
        self.restart.setObjectName("primary")
        self.restart.setToolTip(_("settings_restart_tip"))
        self.restart.setVisible(False)
        self.restart.clicked.connect(self._restart)
        bottom.addWidget(self.restart)
        close = QPushButton(_("close"))
        close.setObjectName("tool")
        close.clicked.connect(self.close)
        bottom.addWidget(close)
        lay.addLayout(bottom)
        self.resize(900, 680)
        self.current = self.chapters[0].key if self.chapters else ""
        self.list.setCurrentRow(0)

    # ---- the file ----------------------------------------------------------------------
    def _stamp(self):
        try:
            st = self.path.stat()
            return st.st_mtime_ns, st.st_size
        except OSError:
            return None

    def _fresh(self):
        """Read the file again if someone changed it outside since: True if so."""
        if self._stamp() == self.stamp:
            return False
        self.stamp = self._stamp()
        self.chapters = model_of.model(self.view)
        self.status.setText(_("settings_changed_outside"))
        return True

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == e.Type.ActivationChange and self.isActiveWindow() and self._fresh():
            self._redraw()

    def _open_file(self):
        from .opener import open_path
        open_path(self.path)

    def _restart(self):
        self.close()
        self.win.restart()

    def save(self, option, value):
        self._fresh()
        now = model_of.option(self.chapters, option.name)
        if now is None or (value is not model_of.UNSET and value == now.value
                           and now.in_file):
            return  # a control drawn before the last save, saying it again
        try:
            words = model_of.save(self.view, {(option.section, option.key): value})
        except model_of.SaveError as e:
            self.status.setText("⚠ " + str(e))
            self._redraw()
            return
        log.info("settings: %s changed", option.name)  # the value may be private: not it
        self.stamp = self._stamp()
        self.chapters = model_of.model(self.view)
        self.status.setText(words)
        self.restart.setVisible(True)
        QTimer.singleShot(0, self._redraw)  # after the control that called has finished

    # ---- drawing -----------------------------------------------------------------------
    def _searched(self):
        q = self.search.text().strip()
        self.list.setEnabled(not q)
        self._redraw()

    def show_chapter(self, key):
        self.current = key
        self._redraw()

    def _redraw(self):
        self.controls = {}  # option's name → its control, as drawn now
        bar = self.scroll.verticalScrollBar()
        keep = bar.value() if getattr(self, "_drawn", None) == self._what() else 0
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 0, 10, 10)
        v.setSpacing(8)
        q = self.search.text().strip()
        if q:
            found = model_of.find(self.chapters, q)
            if not found:
                none = QLabel(_("settings_none"))
                none.setObjectName("setMuted")
                v.addWidget(none)
            for ch, hits in found:
                self._group(v, f"{ch.number}. {ch.title}")
                for o in hits:
                    v.addWidget(self._card(o))
        else:
            ch = next((c for c in self.chapters if c.key == self.current), None)
            group = None
            for o in ch.options if ch else ():
                if o.group and o.group != group:
                    group = o.group
                    self._group(v, group)
                v.addWidget(self._card(o))
        v.addStretch(1)
        self.scroll.setWidget(page)
        self._drawn = self._what()
        QTimer.singleShot(0, lambda: bar.setValue(keep))

    def _what(self):
        return self.search.text().strip() or self.current

    @staticmethod
    def _group(v, words):
        g = QLabel(words)
        g.setObjectName("setGroup")
        v.addWidget(g)

    def _card(self, o):
        card = QFrame()
        card.setObjectName("setCard")
        card.setProperty("changed", "true" if o.changed else "false")
        g = QGridLayout(card)
        g.setContentsMargins(12, 8, 12, 8)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(4)
        title = QLabel(o.title)
        title.setObjectName("setTitle")
        title.setWordWrap(True)
        g.addWidget(title, 0, 0)
        control = self.controls[o.name] = self._control(o)
        row = 1
        if o.kind == "checks":  # a block of ticks: under the name, the whole width
            g.addWidget(control, row, 0, 1, 2)
            row += 1
        else:
            g.addWidget(control, 0, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        about = o.about
        if about and about.split("\n", 1)[0].rstrip(".:") == o.title.rstrip("."):
            about = about.split("\n", 1)[1] if "\n" in about else ""
        if about:
            text = QLabel(about)
            text.setObjectName("setAbout")
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            g.addWidget(text, row, 0, 1, 2)
            row += 1
        foot = QHBoxLayout()
        name = QLabel(o.name + ("" if o.changed else "  ·  " + _("settings_default",
                                                                  value=o.default_shown())))
        name.setObjectName("setName")
        foot.addWidget(name, 1)
        if o.changed:
            reset = QPushButton(_("settings_reset"))
            reset.setObjectName("tool")
            reset.setToolTip(_("settings_reset_tip", value=o.default_shown()))
            reset.clicked.connect(lambda _c=False, o=o: self.save(o, model_of.UNSET))
            foot.addWidget(reset)
        g.addLayout(foot, row, 0, 1, 2)
        g.setColumnStretch(0, 1)
        return card

    def _control(self, o):
        if o.kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(o.value))
            w.toggled.connect(lambda on, o=o: self.save(o, bool(on)))
            return w
        if o.kind == "int":
            w = QSpinBox()
            low = o.minimum if o.minimum is not None else (0 if o.default >= 0 else -10**6)
            w.setRange(low, 10**9)
            w.setValue(int(o.value))
            w.setKeyboardTracking(False)  # one save when typing is done, not per digit
            w.setMinimumWidth(110)
            w.valueChanged.connect(lambda n, o=o: n != o.value and self.save(o, int(n)))
            return w
        if o.kind == "choice":
            w = QComboBox()
            for v, words in o.choices:
                w.addItem(str(v) if words == str(v) else f"{v} — {_short(words, 48)}", v)
                w.setItemData(w.count() - 1, words, Qt.ItemDataRole.ToolTipRole)
            w.setCurrentIndex(max(0, w.findData(o.value)))
            w.setMinimumWidth(220)
            w.setMaximumWidth(420)
            w.currentIndexChanged.connect(
                lambda i, w=w, o=o: w.itemData(i) != o.value and self.save(o, w.itemData(i)))
            return w
        if o.kind == "checks":
            box = QWidget()
            grid = QGridLayout(box)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(14)
            ticks = []
            for i, (v, words) in enumerate(o.choices):
                c = QCheckBox(_short(words, 32))
                c.setToolTip(f"{v}: {words}" if words != v else v)
                c.setChecked(v in (o.value or ()))
                ticks.append((v, c))
                grid.addWidget(c, i // 4, i % 4)

            def ticked(_on, o=o, ticks=ticks):
                now = [v for v, c in ticks if c.isChecked()]
                # the order of the file stays: kept ones as they were, new ones after
                kept = [v for v in o.value if v in now] + [v for v in now if v not in o.value]
                self.save(o, kept)
            for _v, c in ticks:
                c.toggled.connect(ticked)
            return box
        w = QLineEdit(o.line())
        w.setMinimumWidth(260)
        if o.kind == "list":
            w.setPlaceholderText("a, b, c")

        def typed(w=w, o=o):
            try:
                value = o.parse(w.text())
            except ValueError as e:
                self.status.setText(f"⚠ {o.title}: {e}")
                return
            if value != o.value:
                self.save(o, value)
        w.editingFinished.connect(typed)
        return w


__all__ = ["SettingsDialog"]
