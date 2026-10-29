"""Writing a post or a reply. Drafts are saved as you type."""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import (
    QGuiApplication,
    QIcon,
    QImage,
    QKeySequence,
    QShortcut,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...i18n import _
from ...model import VISIBILITIES, Post, Scheduled, Share, real
from ...model.text import chain_parts, join_quote, quote_lines, snippet
from ..common import compose as rules
from .card import VIS_KEY
from .text import display_name, esc


class _Hint(QLabel):
    """A line of what happened (draft restored, saved…): there only when it says
    something."""

    def setText(self, text):
        super().setText(text)
        self.setVisible(bool(text))


class _Bar(QWidget):
    """The editor's bottom: what the post is on the left, what to do with it on the
    right — one row when both fit, else the two halves in two rows, each keeping to
    its side."""

    def __init__(self, left, right):
        super().__init__()
        from PySide6.QtWidgets import QBoxLayout
        self.left, self.right = left, right
        self.box = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(8)
        self.box.addWidget(left, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.box.addWidget(right, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setMinimumWidth(240)  # narrower: two rows (the layout alone would hold it wide)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        from PySide6.QtWidgets import QBoxLayout
        need = self.left.sizeHint().width() + self.right.sizeHint().width() + 24
        want = QBoxLayout.Direction.LeftToRight if self.width() >= need else \
            QBoxLayout.Direction.TopToBottom
        if self.box.direction() != want:
            self.box.setDirection(want)


MEDIA_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".heic",
             ".mp4", ".webm", ".mov", ".mp3", ".ogg", ".m4a", ".flac")
MEDIA_FILTER = " ".join("*" + e for e in MEDIA_EXT)
# what a cover picture goes with: a video or a sound (the server shows the cover until
# it's played)
COVERED_EXT = (".mp4", ".webm", ".mov", ".mp3", ".ogg", ".m4a", ".flac")
COVER_FILTER = " ".join("*" + e for e in (".jpg", ".jpeg", ".png", ".webp", ".gif"))
# the media list's item roles past path / description / focus
ROLE_REMOTE = Qt.ItemDataRole.UserRole + 3   # an attachment of the post being edited: its id
ROLE_COVER = Qt.ItemDataRole.UserRole + 4    # a cover picture's path
ROLE_WAS = Qt.ItemDataRole.UserRole + 5      # its description and focus as they were


def _was(desc, focus):
    """An attachment's words and focus as one comparable string."""
    return json.dumps([desc or "", [round(float(x), 2) for x in focus] if focus else None])

log = logging.getLogger(__name__)



class _QtImages:
    """What common/compose.fit_for_server needs, with Qt's pictures."""

    @staticmethod
    def size(path):
        from PySide6.QtGui import QImageReader
        reader = QImageReader(str(path))
        if not reader.canRead():
            return None
        size = reader.size()
        return (size.width(), size.height()) if size.isValid() else (0, 0)

    @staticmethod
    def load(path):
        from PySide6.QtGui import QImage
        img = QImage(str(path))
        return None if img.isNull() else img

    @staticmethod
    def scaled(img, w, h):
        return img.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)

    @staticmethod
    def dims(img):
        return img.width(), img.height()

    @staticmethod
    def alpha(img):
        return img.hasAlphaChannel()

    @staticmethod
    def save(img, out, kind, quality):
        return img.save(out, "PNG" if kind == "png" else "JPG",
                        -1 if kind == "png" else quality)


def fit_for_server(path, caps, folder):
    """common/compose.fit_for_server with Qt's pictures."""
    return rules.fit_for_server(path, caps, folder, _QtImages)


def media_paths(mime):
    """Local media files in a drag or the clipboard (Dolphin, browser, file dialog)."""
    out = []
    if mime.hasUrls():
        for url in mime.urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(MEDIA_EXT):
                out.append(str(Path(url.toLocalFile())))  # C:\\… on Windows, not C:/…
    return out


def save_image(core, image):
    """A picture without a file (a screenshot, an image from a web page): keep it
    as PNG next to the profile's data, so the draft can refer to it."""
    folder = core.paths.data_dir / "attachments"
    folder.mkdir(exist_ok=True)
    path = folder / f"pasted-{datetime.now():%Y%m%d-%H%M%S-%f}.png"
    return str(path) if image.save(str(path), "PNG") else None



from ..common.compose import (  # noqa: E402,F401  (Qt's names)
    LANG_NAMES,
    OTHER_LANG,
    lang_mismatch,
    lang_question,
)

BIG_PCT = 90  # the ⤢ button: this share of the main window
# languages Qt has no name of their own for
def _lang_label(code, qlocale):
    def native(c):
        loc = qlocale(c)
        if loc.language() == qlocale.Language.C and c != "c":
            return None
        return loc.nativeLanguageName() or None
    return rules.language_label(code, native)

# a draft kept before the composer spoke the model's words
_OLD_VIS = {"private": "followers"}


class Compose(QDialog):
    def __init__(self, win, reply_to=None, attach=(), text="", edit=None, quote=None,
                 invite=False):
        """invite: "Call into the thread" — a reply to reply_to that is only "@" at first,
        the people list open: the one named gets a notification and the thread with it."""
        super().__init__(win)
        self.win, self.core = win, win.ctx.view
        # Posts (the model); a stored status still comes in from older callers
        self.edit = self._as_post(edit)  # my post being corrected
        self.reply_to = self._as_post(reply_to)
        self.quote = self._as_post(quote)  # the post this one quotes
        self.invite = bool(invite and self.reply_to)
        self.key = rules.draft_key(self.core, self.reply_to, self.quote, self.edit,
                                   self.invite)
        self.start_text = text  # "@someone " from a profile's Mention button
        # the window finds an open reply here to put a quote into (quote_reply)
        alive = []
        for c in getattr(win, "open_composes", []):
            try:
                if c.isVisible():
                    alive.append(c)
            except RuntimeError:  # closed and gone
                pass
        win.open_composes = alive + [self]
        self.sent = False
        title = _("compose_edit") if edit else _("compose_invite") if self.invite else \
            _("compose_reply") if reply_to else _("compose_quote") if quote else _("compose_new")
        self.setWindowTitle(title)
        # ui.compose = "inline": a panel inside the main window, not a window of its own.
        # A new window can come up with another keyboard layout (KDE keeps one per
        # window): typing on in Russian you'd get Latin letters. Inside, it stays.
        self.inline = win.cfg["ui"]["compose"] == "inline"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)
        if self.inline:
            old = getattr(win, "inline_compose", None)
            try:
                if old is not None and old.isVisible():
                    old.reject()  # one panel at a time; its text stays a draft
            except RuntimeError:  # already gone
                pass
            win.inline_compose = self
            self.setWindowFlags(Qt.WindowType.Widget)
            self.setObjectName("composePanel")
            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            # the title strip (shape.header_stripes: point.im's hatched band)
            head_box = QWidget(self)
            head_box.setObjectName("composeHead")
            head_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            top = QHBoxLayout(head_box)
            top.setContentsMargins(10, 6, 6, 6)
            # bigger / smaller (⤡) at the top left, as ✕ is at the top right
            self.size_btn = QPushButton("⤡")
            self.size_btn.setObjectName("tool")
            self.size_btn.setToolTip(_("compose_bigger_tip"))
            self.size_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.size_btn.clicked.connect(self._toggle_big)
            top.addWidget(self.size_btn)
            head = QLabel(title)
            head.setObjectName("laneTitle")
            top.addWidget(head, 1)
            close = QPushButton("✕")
            close.setObjectName("tool")
            close.setToolTip(_("close_tip") + " (Esc)")
            close.setCursor(Qt.CursorShape.PointingHandCursor)
            close.clicked.connect(self.reject)
            top.addWidget(close)
            lay.addWidget(head_box)
            win.installEventFilter(self)

        if self.reply_to:
            q = QLabel(f"↑ <b>{display_name(self.reply_to.author)}</b>: "
                       f"{esc(snippet(self.reply_to, 400))}")
            q.setWordWrap(True)
            q.setObjectName("ctx")
            lay.addWidget(q)
        if self.quote:
            q = QLabel(f"❝ <b>{display_name(self.quote.author)}</b>: "
                       f"{esc(snippet(self.quote, 400))}")
            q.setWordWrap(True)
            q.setObjectName("ctx")
            lay.addWidget(q)

        self.cw = QLineEdit()
        self.cw.setPlaceholderText(_("cw_placeholder"))
        self.cw.setVisible(False)
        lay.addWidget(self.cw)

        self.text = QPlainTextEdit()
        # pictures dropped or pasted into the text become attachments
        self.text.installEventFilter(self)
        self.text.viewport().installEventFilter(self)
        self.setAcceptDrops(True)
        self.text.setPlaceholderText(_("text_placeholder_md") if self.core.markdown
                                     else _("text_placeholder"))
        from .markup import bar as format_bar
        from .markup import put
        # B I S code link quote list (post.format_bar): at the side, above or below
        self.format_bar = format_bar(self.text, win.cfg, self.core.markdown)
        put(lay, self.text, self.format_bar)
        # "#ge" offers the tags already in use: #georgia, #GeorgiaNews…
        from .complete import Completer
        self.completion = Completer(self, self.text, self.core, win.bridge)
        self._tag_model = self.completion.model          # (the names tests know)
        self.tag_completer = self.completion.completer
        self.camel = QLabel()
        self.camel.setObjectName("counter")
        self.camel.setWordWrap(True)
        self.camel.hide()
        lay.addWidget(self.camel)
        # a private answer that brings someone new into the talk: said before it goes
        self.newcomer = QLabel()
        self.newcomer.setObjectName("newcomer")
        self.newcomer.setWordWrap(True)
        self.newcomer.hide()
        lay.addWidget(self.newcomer)

        self.media = QListWidget()
        self.media.setObjectName("mediaList")
        self.media.setViewMode(QListWidget.ViewMode.IconMode)
        self.media.setIconSize(QSize(72, 72))
        self.media.setMovement(QListWidget.Movement.Static)
        self.media.setWrapping(False)
        self.media.setFixedHeight(112)
        self.media.setVisible(False)
        self.media.setToolTip(_("media_tip"))
        self.media.itemDoubleClicked.connect(self.edit_description)
        lay.addWidget(self.media)
        self._build_poll(lay)

        tools_w = QWidget()
        row = QHBoxLayout(tools_w)
        row.setContentsMargins(0, 0, 0, 0)
        self.vis = QComboBox()
        self.vis.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for v in VISIBILITIES:
            self.vis.addItem(_("vis_" + VIS_KEY.get(v, v)), v)
        row.addWidget(self.vis)
        # all accounts in one window: which one it goes from, its whole @name@server
        # (one name on two servers looked like one account — 23.10)
        self.from_box = None
        accounts, first = self.core.post_accounts(self.reply_to)
        if len(accounts) > 1 and not self.edit:
            self.from_box = QComboBox()
            self.from_box.setObjectName("postFrom")
            self.from_box.setToolTip(_("post_from_tip"))
            self.from_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            for key, handle in accounts:
                self.from_box.addItem(_("post_from", acct=handle), key)
            self.from_box.setCurrentIndex(max(0, self.from_box.findData(first)))
            self._from_first = first
            self.from_box.currentIndexChanged.connect(self._from_changed)
            row.insertWidget(0, self.from_box)
            self._from_changed()
        self.lang = QComboBox()
        self.lang.setToolTip(_("lang_tip"))
        self.lang.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._fill_languages()
        row.addWidget(self.lang)
        add = QPushButton(QIcon.fromTheme("mail-attachment"), _("attach"))
        self.attach_btn = add
        add.setObjectName("tool")
        add.clicked.connect(self.attach)
        row.addWidget(add)
        if self.edit:  # an edit changes words; pictures and who sees it stay as they were
            add.setEnabled(False)
            add.setToolTip(_("edit_media_kept"))
            self.setAcceptDrops(False)
        self.cover_btn = QPushButton(_("media_cover"))
        self.cover_btn.setObjectName("tool")
        self.cover_btn.setToolTip(_("media_cover_tip"))
        self.cover_btn.clicked.connect(lambda: self.pick_cover())
        self.cover_btn.setVisible(False)
        row.addWidget(self.cover_btn)
        self.cw_btn = QPushButton("⚠ " + _("cw_add"))
        self.cw_btn.setObjectName("tool")
        self.cw_btn.setCheckable(True)
        self.cw_btn.setToolTip(_("cw_add_tip"))
        self.cw_btn.toggled.connect(self._toggle_cw)
        row.addWidget(self.cw_btn)
        self.poll_btn = QPushButton("📊 " + _("poll_add"))
        self.poll_btn.setObjectName("tool")
        self.poll_btn.setCheckable(True)
        self.poll_btn.setToolTip(_("poll_add_tip"))
        self.poll_btn.toggled.connect(self._toggle_poll)
        self.poll_btn.setVisible(not self.edit)
        row.addWidget(self.poll_btn)
        self.sensitive_btn = QPushButton("🔞 " + _("sensitive_mark"))
        self.sensitive_btn.setObjectName("tool")
        self.sensitive_btn.setCheckable(True)
        self.sensitive_btn.setToolTip(_("sensitive_mark_tip"))
        self.sensitive_btn.setVisible(False)
        self.sensitive_btn.toggled.connect(lambda _on: self._changed())
        row.addWidget(self.sensitive_btn)
        rm = QPushButton(_("detach"))
        rm.setObjectName("tool")
        self.detach_btn = rm
        rm.clicked.connect(self.detach)
        row.addWidget(rm)
        # the count in the text field's own corner, bottom right (no row of its own)
        self.counter = QLabel(self.text)
        self.counter.setObjectName("counter")
        self.counter.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hint = _Hint()
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        self.hint.setVisible(False)
        lay.addWidget(self.hint)
        # what the post is (left) and what to do with it (right): one row when there's
        # room, two in a narrow window — the halves keep to their sides
        acts_w = QWidget()
        row = QHBoxLayout(acts_w)
        row.setContentsMargins(0, 0, 0, 0)
        close_btn = QPushButton(_("close"))
        close_btn.setObjectName("tool")
        close_btn.setToolTip(_("close_tip"))
        close_btn.clicked.connect(self.reject)
        row.addWidget(close_btn)
        self.discard_btn = QPushButton(_("discard"))
        self.discard_btn.setObjectName("tool")
        self.discard_btn.clicked.connect(self.discard)
        row.addWidget(self.discard_btn)
        self.later_btn = QPushButton("⏰ " + _("schedule"))
        self.later_btn.setObjectName("tool")
        self.later_btn.setToolTip(_("schedule_tip"))
        self.later_btn.clicked.connect(self.ask_schedule)
        self.later_btn.setVisible(not self.edit and self.core.cfg["post"].get("schedule", True))
        row.addWidget(self.later_btn)
        if self.core.cfg["post"].get("preview", True):
            pv = QPushButton("👁 " + _("preview"))
            pv.setObjectName("tool")
            pv.setToolTip(_("preview_tip"))
            pv.clicked.connect(self.preview)
            row.addWidget(pv)
        self.send_btn = QPushButton(_("send"))
        self.send_btn.setObjectName("primary")
        self.send_btn.setDefault(True)
        self.send_btn.clicked.connect(self.send)
        row.addWidget(self.send_btn)
        lay.addWidget(_Bar(tools_w, acts_w))

        for seq in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(QKeySequence(seq), self).activated.connect(self.send)

        self._autosave = QTimer(self, singleShot=True, interval=700)
        self._autosave.timeout.connect(self.save_draft)
        self._load()
        if self.cw.text() or self.core.cfg["post"]["cw_field"]:
            self.cw_btn.setChecked(True)
        if attach:
            self.add_paths(attach)
        self.text.textChanged.connect(self._changed)
        self.cw.textChanged.connect(self._changed)
        self.vis.currentIndexChanged.connect(self._changed)
        self._count()
        pct = self._size_pct()
        if pct and not self.inline:  # a window of its own: the same share of the main one
            self.resize(int(win.width() * pct / 100), int(win.height() * pct / 100))
        else:
            self.resize(720, 500)
        if self.inline:
            self._place()
        self.text.setFocus()
        cur = self.text.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        self.text.setTextCursor(cur)
        if self.invite and self.text.toPlainText() == "@":  # who to call: the list at once
            QTimer.singleShot(0, self._suggest_tags)

    def _fill_languages(self):
        """"As in settings" first, then post.languages, then post.language if it's
        not among them — each by its own name (Русский, ქართული…)."""
        from PySide6.QtCore import QLocale
        cfg = self.core.cfg["post"]
        added = list(self.core.get_state("languages_added", []) or [])
        codes = list(dict.fromkeys(cfg["languages"] + ([cfg["language"]] if cfg["language"]
                                                       else []) + added))
        self.lang.addItem(_("lang_default"), "")
        for code in codes:
            self.lang.addItem(_lang_label(code, QLocale), code)
        # one more at the bottom: any language by its code, kept for the next posts
        self.lang.addItem(_("lang_other"), OTHER_LANG)
        self.set_language(cfg["language"])
        self._lang_before = self.lang.currentIndex()
        self.lang.activated.connect(self._lang_picked)
        # spelling (core/spell.py): checked in the post's language, picked anew with it
        from .spellcheck import Spell
        self.spell = Spell(self, self.text)
        self.lang.currentIndexChanged.connect(self.spell.repick)

    def _language(self):
        code = self.lang.currentData()
        return "" if code == OTHER_LANG else code

    def _lang_picked(self, i):
        if self.lang.itemData(i) != OTHER_LANG:
            self._lang_before = i
            return
        from PySide6.QtCore import QLocale
        from PySide6.QtWidgets import QInputDialog
        code, ok = QInputDialog.getText(self, _("lang_other_title"), _("lang_other_ask"))
        code = (code or "").strip().lower()
        if not ok or not re.fullmatch(r"[a-z]{2,3}(-[a-z0-9]{2,8})?", code):
            self.lang.setCurrentIndex(self._lang_before)
            return
        if self.lang.findData(code) < 0:
            self.lang.insertItem(self.lang.count() - 1, _lang_label(code, QLocale), code)
            added = list(self.core.get_state("languages_added", []) or [])
            if code not in added:
                self.core.set_state("languages_added", added + [code])
                log.info("compose: language %s added to the list", code)
        self.set_language(code)
        self._lang_before = self.lang.currentIndex()

    def set_language(self, code):
        i = self.lang.findData(code or "")
        if i < 0 and code:
            self.lang.addItem(code, code)
            i = self.lang.count() - 1
        self.lang.setCurrentIndex(max(i, 0))

    # ---- quoting --------------------------------------------------------------------
    def insert_quote(self, text, whole=False, at_end=False):
        """Put `text` in as a quote (post.quote_prefix) where the cursor is (at_end: after
        what's there), the cursor after it, ready for the answer."""
        q = quote_lines(text, self.core.cfg["post"].get("quote_prefix", "> ") or "> ",
                        strip_mentions=whole)
        if not q:
            return
        cur = self.text.textCursor()
        if at_end:
            cur.movePosition(QTextCursor.MoveOperation.End)
        head = QTextCursor(cur)  # the text up to the cursor (positions aren't str indexes)
        head.clearSelection()
        head.movePosition(QTextCursor.MoveOperation.Start, QTextCursor.MoveMode.KeepAnchor)
        before = head.selectedText().replace("\u2029", "\n")
        cur.insertText(join_quote(before, q) + q)
        self.text.setTextCursor(cur)
        self.text.ensureCursorVisible()
        self.raise_()
        self.activateWindow()
        self.text.setFocus()

    def _as_post(self, x):
        if x is None:
            return None
        if isinstance(x, (Post, Share)):
            return real(x)
        return real(self.core.entry(x))  # a stored status

    # ---- drafts -------------------------------------------------------------------
    def _load(self):
        if self.edit:
            self._load_edit()
            return
        st = rules.start(self.core, self.key, self.reply_to, self.start_text, self.invite)
        self.text.setPlainText(st.text)
        self.cw.setText(st.cw)
        if st.language is not None:
            self.set_language(st.language)
        for path, desc, *rest in st.media:
            if Path(path).exists():
                cover = rest[1] if len(rest) > 1 and rest[1] and Path(rest[1]).exists() \
                    else None
                self._add_media(path, desc, rest[0] if rest else None, cover)
        self.sensitive_btn.setChecked(st.sensitive)
        if st.poll:
            self.poll_btn.setChecked(True)
            for e, text in zip(self.poll_options, st.poll.get("options", []), strict=False):
                e.setText(text)
            i = self.poll_time.findData(st.poll.get("expires_in"))
            if i >= 0:
                self.poll_time.setCurrentIndex(i)
            self.poll_multiple.setChecked(bool(st.poll.get("multiple")))
        if st.hint:
            self.hint.setText(_(st.hint))
        vis = st.visibility
        self.vis.setCurrentIndex(VISIBILITIES.index(vis) if vis in VISIBILITIES else 2)
        self.initial = self._snapshot()

    def _load_edit(self):
        for m in self.edit.media:  # their words and focus can change; they stay
            self._add_remote(m)
        v = self.edit.visibility
        self.vis.setCurrentIndex(VISIBILITIES.index(v) if v in VISIBILITIES else 2)
        self.set_language(self.edit.lang or "")
        self.lang.setEnabled(False)
        self.vis.setEnabled(False)
        self.vis.setToolTip(_("edit_media_kept"))
        d = self.core.get_draft(self.key)
        if d:
            self.text.setPlainText(d.get("text", ""))
            self.cw.setText(d.get("cw", ""))
            self.hint.setText(_("draft_restored"))
            self.initial = self._snapshot()
            return
        self.text.setEnabled(False)
        self.hint.setText(_("loading"))

        def got(src):
            text, warning = src
            self.text.setEnabled(True)
            self.text.setPlainText(text)
            self.cw.setText(warning)
            if self.cw.text():
                self.cw_btn.setChecked(True)
            self.hint.setText(_("edit_hint"))
            self.initial = self._snapshot()
            self.text.setFocus()
        self.initial = self._snapshot()
        self.win.bridge.call(self.core.source(self.edit), ok=got,
                             fail=lambda e: (self.text.setEnabled(True),
                                             self.hint.setText(_("load_failed", err=e))))

    def _snapshot(self):
        return rules.snapshot(self.text.toPlainText(), self.cw.text(), self.vis.currentData(),
                              self._media_list(), self._language(),
                              self.sensitive_btn.isChecked(), self.poll_data())

    # ---- a poll -------------------------------------------------------------------
    POLL_TIMES = rules.POLL_TIMES

    def _build_poll(self, lay):
        self.poll_box = QWidget()
        self.poll_box.setObjectName("pollEditor")
        v = QVBoxLayout(self.poll_box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        self.poll_options = []
        for i in range(max(2, self.core.caps.max_poll_options)):
            e = QLineEdit()
            e.setPlaceholderText(_("poll_option", n=i + 1))
            e.textChanged.connect(lambda _t: self._changed())
            v.addWidget(e)
            self.poll_options.append(e)
        h = QHBoxLayout()
        self.poll_time = QComboBox()
        for secs, key in self.POLL_TIMES:
            self.poll_time.addItem(_(key), secs)
        self.poll_time.setCurrentIndex(4)  # a day
        self.poll_time.currentIndexChanged.connect(lambda _i: self._changed())
        h.addWidget(self.poll_time)
        self.poll_multiple = QCheckBox(_("poll_several"))
        self.poll_multiple.toggled.connect(lambda _on: self._changed())
        h.addWidget(self.poll_multiple)
        h.addStretch(1)
        v.addLayout(h)
        self.poll_box.setVisible(False)
        lay.addWidget(self.poll_box)

    def _toggle_poll(self, on):
        self.poll_box.setVisible(on)
        if on:
            self.poll_options[0].setFocus()
        self._media_or_poll()
        self._changed()

    def _media_or_poll(self):
        """A server takes pictures or a poll, not both: one closes the other's door."""
        if not hasattr(self, "sensitive_btn"):
            return  # still being built
        has_media = bool(self._media_list())
        self.poll_btn.setEnabled(not has_media and not self.edit)
        self.sensitive_btn.setVisible(has_media)
        if getattr(self, "attach_btn", None) is not None:
            self.attach_btn.setEnabled(not self.poll_btn.isChecked() and not self.edit)

    def poll_data(self):
        if not getattr(self, "poll_btn", None):
            return None
        return rules.poll_data(self.poll_btn.isChecked(), [e.text() for e in self.poll_options],
                               self.poll_time.currentData(), self.poll_multiple.isChecked())

    def _changed(self):
        self._count()
        self._media_or_poll()
        self._autosave.start()

    # ---- completing #tags and @people -----------------------------------------------
    def _token_at_cursor(self):
        return self.completion.token()

    # (kept for the name the tests know it by)
    def _suggest_tags(self):
        self.completion.suggest()

    def _put_tag(self, label):
        self.completion.put(label)

    def save_draft(self):
        if self.sent:
            return
        snap = self._snapshot()
        what = rules.keep(snap, self.initial, bool(self.core.get_draft(self.key)))
        if what == "skip":
            return
        if what == "delete":
            self.core.delete_draft(self.key)
            return
        self.core.save_draft(self.key, snap)
        if self.core.cfg["post"]["drafts_autosave"]:
            self.hint.setText(_("draft_saved"))

    def discard(self):
        if QMessageBox.question(self, _("discard_q_title"), _("discard_q")) \
                == QMessageBox.StandardButton.Yes:
            self.core.delete_draft(self.key)
            self.sent = True  # nothing to keep
            self._leave()

    def _toggle_cw(self, on):
        self.cw.setVisible(on)
        if on:
            self.cw.setFocus()
        elif self.cw.text():
            self.cw.clear()  # hiding the field drops the warning
            self.text.setFocus()

    # ---- drag & drop, paste -----------------------------------------------------------
    def _accepts(self, mime):
        return bool(media_paths(mime)) or mime.hasImage()

    def _take(self, mime):
        paths = media_paths(mime)
        if not paths and mime.hasImage():
            img = QImage(mime.imageData())
            saved = save_image(self.core, img) if not img.isNull() else None
            paths = [saved] if saved else []
        if paths:
            self.add_paths(paths)
        return bool(paths)

    def _place_counter(self):
        c, t = getattr(self, "counter", None), self.text
        if c is None:
            return
        c.adjustSize()
        bar = t.verticalScrollBar()
        right = bar.width() if bar.isVisible() else 0
        c.move(max(0, t.width() - c.width() - right - 10), max(0, t.height() - c.height() - 6))
        c.raise_()

    def eventFilter(self, obj, e):
        t = e.type()
        if obj is self.text and t == QEvent.Type.Resize:
            self._place_counter()
        if self.inline and obj is self.win and t == QEvent.Type.Resize:
            self._place()  # the panel follows the window
            return False
        if t in (QEvent.Type.DragEnter, QEvent.Type.DragMove) and self._accepts(e.mimeData()):
            e.acceptProposedAction()
            return True
        if t == QEvent.Type.Drop and self._accepts(e.mimeData()):
            e.acceptProposedAction()
            self._take(e.mimeData())
            return True
        if t == QEvent.Type.KeyPress and e.matches(QKeySequence.StandardKey.Paste):
            mime = QGuiApplication.clipboard().mimeData()
            if (media_paths(mime) or (mime.hasImage() and not mime.hasText())) and \
                    self._take(mime):
                return True
        return super().eventFilter(obj, e)

    def dragEnterEvent(self, e):
        if self._accepts(e.mimeData()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        if self._take(e.mimeData()):
            e.acceptProposedAction()

    # ---- media --------------------------------------------------------------------
    def _media_list(self):
        """[path, description(, focus(, cover))] of the files to upload (not the
        attachments of a post being edited: those are the server's already)."""
        out = []
        for i in range(self.media.count()):
            it = self.media.item(i)
            if it.data(ROLE_REMOTE):
                continue
            entry = [it.data(Qt.ItemDataRole.UserRole), it.data(Qt.ItemDataRole.UserRole + 1)]
            focus = it.data(Qt.ItemDataRole.UserRole + 2)
            cover = it.data(ROLE_COVER)
            if focus or cover:
                entry.append(list(focus) if focus else None)
            if cover:
                entry.append(cover)
            out.append(entry)
        return out

    def media_changes(self):
        """Edit: {media id: (description, focus)} of the post's attachments whose words or
        focus point were changed here."""
        out = {}
        for i in range(self.media.count()):
            it = self.media.item(i)
            mid = it.data(ROLE_REMOTE)
            if not mid:
                continue
            desc = it.data(Qt.ItemDataRole.UserRole + 1) or ""
            focus = it.data(Qt.ItemDataRole.UserRole + 2)
            if _was(desc, focus) != it.data(ROLE_WAS):
                out[mid] = (desc, tuple(focus) if focus else None)
        return out

    def _is_covered(self, it):
        path = it.data(Qt.ItemDataRole.UserRole) or ""
        return not it.data(ROLE_REMOTE) and Path(path).suffix.lower() in COVERED_EXT

    def pick_cover(self, path=None):
        """A cover for the chosen video or sound (or the first one): path, or asked."""
        items = [self.media.item(i) for i in range(self.media.count())]
        chosen = [it for it in self.media.selectedItems() if self._is_covered(it)]
        it = (chosen or [x for x in items if self._is_covered(x)] or [None])[0]
        if it is None:
            return
        if path is None:
            last = self.core.get_state("last_media_dir", str(Path.home()))
            path, _f = QFileDialog.getOpenFileName(self, _("media_cover"), last,
                                                   f"{_('media_files')} ({COVER_FILTER})")
        if path:
            it.setData(ROLE_COVER, path)
            self._label_item(it)
            self._changed()

    def _add_remote(self, m):
        """An attachment of the post being edited: its description (and a picture's focus
        point, its preview being at hand) can be changed; it can't go or be replaced."""
        it = QListWidgetItem("")
        local = self.win.images.local(m.preview or m.url) if m.kind == "image" else None
        if local:
            it.setIcon(QIcon(local))
        it.setData(Qt.ItemDataRole.UserRole, local or "")
        it.setData(Qt.ItemDataRole.UserRole + 1, m.alt)
        it.setData(Qt.ItemDataRole.UserRole + 2, list(m.focus) if m.focus else None)
        it.setData(ROLE_REMOTE, m.ref.id)
        it.setData(ROLE_WAS, _was(m.alt, m.focus))
        self._label_item(it)
        self.media.addItem(it)

    def add_paths(self, paths):
        known = {m[0] for m in self._media_list()}
        paths = [p for p in paths if p not in known]
        left = self.core.caps.max_media - self.media.count()
        if len(paths) > left:
            self.hint.setText(_("media_limit", n=self.core.caps.max_media))
        for p in paths[:max(left, 0)]:
            self._add_media(p)
        if paths:
            self._changed()

    def _add_media(self, path, desc="", focus=None, cover=None):
        it = QListWidgetItem(QIcon(path), "")
        it.setData(Qt.ItemDataRole.UserRole, path)
        it.setData(Qt.ItemDataRole.UserRole + 1, desc)
        it.setData(Qt.ItemDataRole.UserRole + 2, list(focus) if focus else None)
        it.setData(ROLE_COVER, cover or None)
        self._label_item(it)
        self.media.addItem(it)
        self._media_or_poll()

    def _label_item(self, it):
        name = Path(it.data(Qt.ItemDataRole.UserRole) or "").name
        desc = it.data(Qt.ItemDataRole.UserRole + 1)
        cover = it.data(ROLE_COVER)
        it.setText((_("alt_set") if desc else _("no_alt"))
                   + ("\n" + _("media_cover_set", name=Path(cover).name) if cover else ""))
        it.setToolTip(f"{name}\n{desc}" if desc else f"{name}\n{_('media_tip')}")

    def attach(self):
        left = self.core.caps.max_media - self.media.count()
        if left <= 0:
            self.hint.setText(_("media_limit", n=self.core.caps.max_media))
            return
        last = self.core.get_state("last_media_dir", str(Path.home()))
        paths, _f = QFileDialog.getOpenFileNames(self, _("attach"), last,
                                                 f"{_('media_files')} ({MEDIA_FILTER});;* (*)")
        if paths:
            self.core.set_state("last_media_dir", str(Path(paths[0]).parent))
            self.add_paths(paths)

    def detach(self):
        for it in self.media.selectedItems():
            self.media.takeItem(self.media.row(it))
        self._changed()

    def edit_description(self, it):
        """The picture's description and (post.focus_point) its focus point: a click on
        the picture puts the cross where the main thing is."""
        from .focus import FocusDialog
        dlg = FocusDialog(self, it.data(Qt.ItemDataRole.UserRole),
                          it.data(Qt.ItemDataRole.UserRole + 1) or "",
                          it.data(Qt.ItemDataRole.UserRole + 2),
                          with_focus=self.core.cfg["post"].get("focus_point", True))

        def done():
            it.setData(Qt.ItemDataRole.UserRole + 1, dlg.description())
            it.setData(Qt.ItemDataRole.UserRole + 2, dlg.focus)
            self._label_item(it)
            self._changed()
        dlg.accepted.connect(done)
        self.focus_dialog = dlg
        dlg.open()
        return dlg

    # ---- preview ----------------------------------------------------------------------
    def preview(self):
        """How it will look: Markdown made into text the way a Markdown server does (when
        this one is), the CW, who sees it, each post of a chain, the pictures; Send or
        back to editing from here."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser

        text = self.text.toPlainText().strip()
        parts = chain_parts(text) if self.core.cfg["post"].get("chain", True) else [text]
        parts = parts or [text]
        dlg = QDialog(self)
        dlg.setWindowTitle(_("preview"))
        dlg.resize(min(720, self.win.width() - 80), min(600, self.win.height() - 80))
        lay = QVBoxLayout(dlg)
        head = " · ".join(x for x in (
            self.vis.currentText(), self.lang.currentText() if self._language() else "",
            _("chain_count", n=len(parts)) if len(parts) > 1 else "",
            _("preview_media", n=self.media.count()) if self.media.count() else "",
            _("preview_md") if self.core.markdown else _("preview_plain")) if x)
        info = QLabel(head)
        info.setObjectName("meta")
        info.setWordWrap(True)
        lay.addWidget(info)
        for i, part in enumerate(parts):
            if self.cw.text().strip():
                cw = QLabel("⚠ " + esc(self.cw.text().strip()))
                cw.setWordWrap(True)
                lay.addWidget(cw)
            view = QTextBrowser()
            view.setOpenExternalLinks(False)
            if self.core.markdown:
                view.setMarkdown(part)
            else:
                view.setPlainText(part)
            lay.addWidget(view, 1)
            if i < len(parts) - 1:
                lay.addWidget(QLabel("↳"))
        box = QDialogButtonBox()
        send = box.addButton(_("send"), QDialogButtonBox.ButtonRole.AcceptRole)
        box.addButton(_("preview_back"), QDialogButtonBox.ButtonRole.RejectRole)
        box.rejected.connect(dlg.reject)
        send.clicked.connect(lambda: (dlg.accept(), self.send()))
        lay.addWidget(box)
        dlg.open()
        return dlg

    # ---- sending --------------------------------------------------------------------
    def _count(self):
        c = rules.count(self.text.toPlainText(), self.cw.text(), self.core.caps.max_characters,
                        self.core.cfg, reply_to=self.reply_to,
                        visibility=self.vis.currentData() or "", me=self.core.me)
        self.newcomer.setVisible(bool(c.newcomers))
        if c.newcomers:
            self.newcomer.setText(_("dm_newcomer_typed", who=", ".join(c.newcomers)))
        if c.parts > 1:  # a chain: each part counts on its own
            self.counter.setText(_("chain_count", n=c.parts) + f" · {c.n} / {c.limit}")
        else:
            self.counter.setText(f"{c.n} / {c.limit}")
        over = "true" if c.over else "false"
        self._place_counter()
        if self.counter.property("over") != over:
            self.counter.setProperty("over", over)
            self.counter.style().unpolish(self.counter)
            self.counter.style().polish(self.counter)
        if self.core.cfg["post"]["camelcase_hint"]:
            flat = c.flat_tags
            self.camel.setVisible(bool(flat))
            if flat:
                self.camel.setText(_("camel_hint", tags=", ".join("#" + t for t in flat[:3])))
        has_media = self.media.count() > 0
        self.media.setVisible(has_media)
        self.detach_btn.setVisible(has_media and not self.edit)  # an edit keeps them all
        self.cover_btn.setVisible(any(self._is_covered(self.media.item(i))
                                      for i in range(self.media.count())))

    def ask_schedule(self):
        """When to send it: the server keeps the post and sends it then."""
        from PySide6.QtCore import QDateTime
        from PySide6.QtWidgets import QDateTimeEdit, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle(_("schedule"))
        v = QVBoxLayout(dlg)
        when = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        when.setCalendarPopup(True)
        when.setMinimumDateTime(QDateTime.currentDateTime().addSecs(300))
        when.setDisplayFormat("dd.MM.yyyy HH:mm")
        v.addWidget(QLabel(_("schedule_when")))
        v.addWidget(when)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        ok = buttons.addButton(_("schedule_ok"), QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setObjectName("primary")
        buttons.rejected.connect(dlg.reject)
        ok.clicked.connect(dlg.accept)
        v.addWidget(buttons)
        self.schedule_dialog = dlg
        dlg.accepted.connect(lambda: self.send(
            scheduled_at=when.dateTime().toUTC().toString("yyyy-MM-ddTHH:mm:ss.zzzZ")))
        dlg.open()
        return dlg

    def _from_changed(self, *_a):
        """The title says whom it goes from; a reply from another account says how."""
        if self.from_box is None:
            return
        handle = self.from_box.currentText()
        base = self.windowTitle().split(" · ")[0]
        self.setWindowTitle(f"{base} · {handle}")
        key = self.from_box.currentData()
        if self.reply_to is not None and key != self._from_first:
            acct = handle.split(" ", 1)[-1]
            self.from_box.setToolTip(_("post_from_other", acct=acct))
        else:
            self.from_box.setToolTip(_("post_from_tip"))

    def send(self, scheduled_at=None, alt_checked=False, lang_checked=False):
        text = self.text.toPlainText().strip()
        media = [tuple(m) for m in self._media_list()]
        if self.core.cfg["post"].get("resize_images", True):
            media = [(fit_for_server(m[0], self.core.caps, self.core.paths.cache_dir),) +
                     tuple(m[1:]) for m in media]
        if not text and not media and not (self.edit and self.media_changes()):
            return
        bare = [i for i in range(self.media.count())
                if not self.media.item(i).data(Qt.ItemDataRole.UserRole + 1)
                and not self.media.item(i).data(ROLE_REMOTE)]
        if bare and not alt_checked and not self.edit and \
                self.core.cfg["post"].get("alt_reminder", True):
            self._ask_alt(bare, scheduled_at)
            return
        said = None if lang_checked or self.edit else \
            lang_mismatch(self.core.cfg, text, self._language())
        if said:  # post.lang_check: the text reads as another language
            self._ask_lang(said, scheduled_at)
            return
        self.save_draft()  # whatever happens next, the text is safe
        log.info("send: %s, reply to %s, %s, language %s, %d chars, %d pictures",
                 "edit" if self.edit else "post", self.reply_to.id if self.reply_to else "-",
                 self.vis.currentData(), self._language() or "-", len(text), len(media))
        self.send_btn.setEnabled(False)
        self.send_btn.setText(_("sending"))
        if self.edit:
            changed = self.media_changes()
            fut = self.core.edit(self.edit, text, self.cw.text().strip(), draft_key=self.key,
                                 **({"media": changed} if changed else {}))
            self.win.bridge.call(fut, ok=self._edited, fail=self._failed)
            return
        fut = self.core.post(text, self.vis.currentData(), self.reply_to,
                             self.cw.text().strip(), media=media, draft_key=self.key,
                             language=self._language(),
                             sensitive=self.sensitive_btn.isChecked(), poll=self.poll_data(),
                             quote=self.quote, scheduled_at=scheduled_at,
                             **({"account": self.from_box.currentData()}
                                if self.from_box is not None else {}))
        self.win.bridge.call(fut, ok=self._sent, fail=self._failed)
        if self.core.cfg["post"].get("send_in_background"):  # out of the way at once
            self.hide()
            self.win.statusBar().showMessage(_("sent_background"), 4000)

    def _ask_alt(self, bare, scheduled_at):
        """post.alt_reminder: a picture without a description — describe it, or send as is."""
        box = QMessageBox(QMessageBox.Icon.Question, _("alt_missing_title"),
                          _("alt_missing", n=len(bare)), parent=self)
        describe = box.addButton(_("alt_describe"), QMessageBox.ButtonRole.AcceptRole)
        anyway = box.addButton(_("alt_send_anyway"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(describe)

        def done(button):
            if button is describe:
                self.edit_description(self.media.item(bare[0]))
            elif button is anyway:
                self.send(scheduled_at, alt_checked=True)
        box.buttonClicked.connect(done)
        self.alt_box = box
        box.open()
        return box

    def _ask_lang(self, said, scheduled_at):
        """post.lang_check: the text reads as `said`, the post says otherwise — mark it
        so and send, send as is, or go back to the text."""
        title, text, switch_w, anyway_w = lang_question(
            said, self._language() or self.core.cfg["post"].get("language"))
        box = QMessageBox(QMessageBox.Icon.Question, title, text, parent=self)
        switch = box.addButton(switch_w, QMessageBox.ButtonRole.AcceptRole)
        anyway = box.addButton(anyway_w, QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(switch)

        def done(button):
            if button is switch:
                self.set_language(said)
            if button in (switch, anyway):
                self.send(scheduled_at, alt_checked=True, lang_checked=True)
        box.buttonClicked.connect(done)
        self.lang_box = box
        box.open()
        return box

    def _sent(self, st):
        self.sent = True
        try:
            self.core.delete_draft(self.key)
            if isinstance(st, Scheduled):
                self.win.statusBar().showMessage(
                    _("scheduled_msg", when=self.win.theme.date(st.at) if st.at else ""), 8000)
                return
            self.win.after_post(st, self.reply_to)
        finally:
            self._leave()

    def _edited(self, st):
        self.sent = True
        self.core.delete_draft(self.key)
        self.win.statusBar().showMessage(_("edited_msg"), 4000)
        self._leave()

    def _failed(self, err):
        self.send_btn.setEnabled(True)
        self.send_btn.setText(_("send"))
        away = self.isHidden()
        if away:  # sent in the background (post.send_in_background): back
            self.show()
        maybe = getattr(err, "maybe_sent", False)  # no answer: the post may be out
        QMessageBox.warning(self, _("send_maybe" if maybe else "send_failed"),
                            _("sent_background_failed" if away else "send_failed_text",
                              err=err))

    # Every way out (Esc, the window's X, Close, after sending) goes through
    # reject(): QDialog.closeEvent itself calls reject(), so reject() must
    # never call close() again — that loop is what kept the window stuck.
    def reject(self):
        if not self.sent and self.send_btn.isEnabled():
            if self.core.cfg["post"]["drafts_autosave"]:
                self.save_draft()
            elif self._snapshot() != self.initial and self.text.toPlainText().strip():
                if QMessageBox.question(self, _("discard_q_title"), _("discard_q")) \
                        != QMessageBox.StandardButton.Yes:
                    return
        # still sending? fine: the core drops the draft once the post is out
        self._leave()

    # ---- the inline panel: over the lanes, in the middle, following the window ------
    def _size_pct(self):
        """How big, in % of the main window: the ⤢ choice if made, else ui.compose_size
        (0: as before — at most 820 × 540)."""
        big = self.core.get_state("compose_big")
        if big:
            return BIG_PCT
        if big is False:
            return 0
        return min(100, int(self.win.cfg["ui"].get("compose_size", 0) or 0))

    def _toggle_big(self):
        self.core.set_state("compose_big", not self._size_pct())
        self._place()

    def _place(self):
        win = self.win
        pct = self._size_pct()
        if pct:
            w = max(420, int(win.width() * pct / 100) - 20)
            h = max(320, int(win.height() * pct / 100) - 20)
        else:
            w = min(820, max(420, win.width() - 80))
            h = min(540, max(320, win.height() - 120))
        x = max(10, (win.width() - w) // 2)
        y = max(10, (win.height() - h) // 2)
        self.setGeometry(x, y, w, h)
        self.raise_()

    def showEvent(self, e):
        super().showEvent(e)
        if self.inline:
            self._place()
            self.text.setFocus()

    def _leave(self):
        self._autosave.stop()
        if self.inline:
            self.win.removeEventFilter(self)
        super().reject()  # hides the dialog
        self.deleteLater()
