"""Editing my own profile: name, bio, pictures, profile fields, a few switches.

This is server data, not a client setting, so it gets a dialog (the client's
own behaviour stays in the config file)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ...i18n import _
from .card import _round

FIELDS_SHOWN = 4  # Mastodon allows 4; more are kept if the server already has them
IMAGE_FILTER = "*.png *.jpg *.jpeg *.gif *.webp"


class ProfileDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win, self.core = win, win.core
        self.setWindowTitle(_("profile_title"))
        self.setMinimumWidth(560)
        self.loaded = None
        self.avatar_path = self.header_path = None
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        self.header_img = QLabel()
        self.header_img.setFixedHeight(120)
        self.header_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_img.setObjectName("ctx")
        lay.addWidget(self.header_img)

        row = QHBoxLayout()
        self.avatar_img = QLabel()
        self.avatar_img.setFixedSize(72, 72)
        row.addWidget(self.avatar_img)
        pics = QVBoxLayout()
        for text, slot in ((_("change_avatar"), self._pick_avatar),
                           (_("change_header"), self._pick_header)):
            b = QPushButton(text)
            b.setObjectName("tool")
            b.clicked.connect(slot)
            pics.addWidget(b)
        row.addLayout(pics)
        row.addStretch(1)
        lay.addLayout(row)

        lay.addWidget(QLabel(_("profile_name")))
        self.name = QLineEdit()
        lay.addWidget(self.name)
        lay.addWidget(QLabel(_("profile_bio")))
        self.bio = QPlainTextEdit()
        self.bio.setFixedHeight(110)
        lay.addWidget(self.bio)

        lay.addWidget(QLabel(_("profile_fields")))
        self.grid = QGridLayout()
        lay.addLayout(self.grid)
        self.field_edits = []

        self.locked = QCheckBox(_("profile_locked"))
        self.bot = QCheckBox(_("profile_bot"))
        self.discoverable = QCheckBox(_("profile_discoverable"))
        for c in (self.locked, self.bot, self.discoverable):
            lay.addWidget(c)

        self.hint = QLabel(_("loading"))
        self.hint.setObjectName("counter")
        buttons = QHBoxLayout()
        buttons.addWidget(self.hint, 1)
        cancel = QPushButton(_("cancel"))
        cancel.setObjectName("tool")
        cancel.clicked.connect(self.reject)
        self.save_btn = QPushButton(_("save"))
        self.save_btn.setObjectName("primary")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save)
        buttons.addWidget(cancel)
        buttons.addWidget(self.save_btn)
        lay.addLayout(buttons)

        win.bridge.call(self.core.my_profile(), ok=self._loaded,
                        fail=lambda e: self.hint.setText(_("load_failed", err=e)))

    # ---- loading -------------------------------------------------------------------
    def _loaded(self, me):
        self.loaded = me
        src = me.get("source") or {}
        self.name.setText(me.get("display_name") or "")
        self.bio.setPlainText(src.get("note", ""))
        fields = [(f.get("name", ""), f.get("value", "")) for f in src.get("fields", [])]
        for i in range(max(FIELDS_SHOWN, len(fields))):
            n, v = fields[i] if i < len(fields) else ("", "")
            name, value = QLineEdit(n), QLineEdit(v)
            name.setPlaceholderText(_("field_name"))
            value.setPlaceholderText(_("field_value"))
            self.grid.addWidget(name, i, 0)
            self.grid.addWidget(value, i, 1, 1, 2)
            self.field_edits.append((name, value))
        self.locked.setChecked(bool(me.get("locked")))
        self.bot.setChecked(bool(me.get("bot")))
        self.discoverable.setChecked(bool(me.get("discoverable")))
        images = self.win.images
        images.get(me.get("avatar_static") or me.get("avatar"),
                   lambda pm: self.avatar_img.setPixmap(_round(pm, 72)))
        images.get(me.get("header_static") or me.get("header"), self._show_header)
        self.hint.setText("")
        self.save_btn.setEnabled(True)

    def _show_header(self, pm):
        w = max(self.header_img.width(), 520)
        self.header_img.setPixmap(pm.scaled(w, 120, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                            Qt.TransformationMode.SmoothTransformation))

    def _pick(self, title):
        last = self.core.get_state("last_media_dir", "")
        path, _f = QFileDialog.getOpenFileName(self, title, last,
                                               f"{_('media_files')} ({IMAGE_FILTER})")
        return path or None

    def _pick_avatar(self):
        from PySide6.QtGui import QPixmap
        path = self._pick(_("change_avatar"))
        if path:
            self.avatar_path = path
            self.avatar_img.setPixmap(_round(QPixmap(path), 72))

    def _pick_header(self):
        from PySide6.QtGui import QPixmap
        path = self._pick(_("change_header"))
        if path:
            self.header_path = path
            self._show_header(QPixmap(path))

    # ---- saving --------------------------------------------------------------------
    def changes(self):
        """Only what differs from the server, so nothing is overwritten by accident."""
        me = self.loaded
        src = me.get("source") or {}
        out = {}
        if self.name.text() != (me.get("display_name") or ""):
            out["display_name"] = self.name.text()
        if self.bio.toPlainText() != src.get("note", ""):
            out["note"] = self.bio.toPlainText()
        fields = [(n.text().strip(), v.text().strip()) for n, v in self.field_edits]
        fields = [f for f in fields if f[0] or f[1]]
        old = [(f.get("name", ""), f.get("value", "")) for f in src.get("fields", [])]
        if fields != old:
            out["fields"] = fields
        for key, box in (("locked", self.locked), ("bot", self.bot),
                         ("discoverable", self.discoverable)):
            if box.isChecked() != bool(me.get(key)):
                out[key] = box.isChecked()
        if self.avatar_path:
            out["avatar"] = self.avatar_path
        if self.header_path:
            out["header"] = self.header_path
        return out

    def save(self):
        if self.loaded is None:
            return
        changes = self.changes()
        if not changes:
            self.accept()
            return
        self.save_btn.setEnabled(False)
        self.hint.setText(_("saving"))
        self.win.bridge.call(self.core.update_profile(**changes), ok=lambda _me: self.accept(),
                             fail=self._failed)

    def _failed(self, e):
        self.hint.setText(_("error", err=e))
        self.save_btn.setEnabled(True)
