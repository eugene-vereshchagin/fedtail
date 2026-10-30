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
from ..common import server
from .card import _round

IMAGE_FILTER = "*.png *.jpg *.jpeg *.gif *.webp"


class ProfileDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win, self.core = win, win.ctx.view
        self.setWindowTitle(_("profile_title"))
        self.setMinimumWidth(560)
        self.loaded = None
        self.avatar_path = self.header_path = None
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        self.header_img = QLabel()
        self.header_img.setFixedHeight(120)
        self.header_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_img.setObjectName("profileHeader")
        self.header_img.setText(_("no_header"))
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
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 2)
        lay.addLayout(self.grid)
        self.field_edits = []

        self.locked = QCheckBox(_("profile_locked"))
        self.bot = QCheckBox(_("profile_bot"))
        self.discoverable = QCheckBox(_("profile_discoverable"))
        self.hide_collections = QCheckBox(_("profile_hide_collections"))
        self.indexable = QCheckBox(_("profile_indexable"))
        for c in (self.locked, self.bot, self.discoverable, self.hide_collections,
                  self.indexable):
            lay.addWidget(c)
        lay.addWidget(QLabel(_("profile_attribution")))
        self.attribution = QLineEdit()
        self.attribution.setPlaceholderText("blog.example, news.example")
        self.attribution.setToolTip(_("profile_attribution_tip"))
        lay.addWidget(self.attribution)
        # the tags I write about most, not yet on my profile: one click puts one there
        self.suggest_row = QHBoxLayout()
        self.suggest_label = QLabel(_("featured_suggest"))
        self.suggest_label.setVisible(False)
        self.suggest_row.addWidget(self.suggest_label)
        self.suggest_row.addStretch(1)
        lay.addLayout(self.suggest_row)
        self.suggest_buttons = []

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
    def _loaded(self, prof):
        """prof: a MyProfile."""
        self.loaded = prof
        me = prof.account
        self.name.setText(me.name)
        self.bio.setPlainText(prof.bio)
        fields = list(prof.fields)
        from ..common.places import profile_fields
        for i in range(max(profile_fields(self.core), len(fields))):
            n, v = fields[i] if i < len(fields) else ("", "")
            name, value = QLineEdit(n), QLineEdit(v)
            name.setPlaceholderText(_("field_name"))
            value.setPlaceholderText(_("field_value"))
            self.grid.addWidget(name, i, 0)
            self.grid.addWidget(value, i, 1)
            self.field_edits.append((name, value))
        self.locked.setChecked(me.locked)
        self.bot.setChecked(me.bot)
        self.discoverable.setChecked(bool(me.discoverable))
        self.hide_collections.setChecked(bool(prof.hide_collections))
        self.indexable.setChecked(bool(prof.indexable))
        self.attribution.setText(", ".join(prof.attribution_domains))
        if self.core.supports("featured_tags"):
            self.win.bridge.call(self.core.featured_tag_suggestions(), ok=self._suggest,
                                 fail=lambda _e: None)
        self.hint.setText("")
        self.save_btn.setEnabled(True)
        # pictures come later, from the image cache
        images = self.win.images
        images.face(me.avatar_static or me.avatar, 72,
                    lambda pm: self.avatar_img.setPixmap(_round(pm, 72)))
        if me.header_static or me.header:
            images.get(me.header_static or me.header, self._show_header)

    def _suggest(self, tags):
        """featured_tag_suggestions: a button per tag; a click features it."""
        for t in tags or ():
            name = getattr(t, "name", "")
            if not name:
                continue
            b = QPushButton("#" + name)
            b.setObjectName("tool")
            b.clicked.connect(lambda _c=False, n=name, b=b: self._feature(n, b))
            self.suggest_row.insertWidget(self.suggest_row.count() - 1, b)
            self.suggest_buttons.append(b)
        self.suggest_label.setVisible(bool(self.suggest_buttons))

    def _feature(self, name, button):
        button.setEnabled(False)
        self.win.bridge.call(self.core.feature_tag(name, True),
                             ok=lambda _r: button.setText("✓ #" + name),
                             fail=lambda e: (button.setEnabled(True), self.win.error(e)))

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
        out = server.profile_changes(
            self.loaded, self.name.text(), self.bio.toPlainText(),
            [(n.text(), v.text()) for n, v in self.field_edits],
            {"locked": self.locked.isChecked(), "bot": self.bot.isChecked(),
             "discoverable": self.discoverable.isChecked()},
            self.avatar_path, self.header_path)
        out.update(server.flag_changes(self.loaded, self.hide_collections.isChecked(),
                                self.indexable.isChecked(), self.attribution.text()))
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
