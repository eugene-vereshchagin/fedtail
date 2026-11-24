"""The rules of writing a post, whatever draws the editor: which draft it is, what it
starts with (a draft, the mentions of a reply, the warning it inherits), what the
counter says, which #tag, @name or :emoji: is being typed, what a poll is, when a
draft is kept and when it goes. qt/compose.py and qt/dock.py, and the GTK editor, ask
here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ...core.hashtags import flat_tags
from ...model import VISIBILITIES
from ...model.text import chain_parts, reply_mentions

OLD_VIS = {"private": "followers"}  # drafts saved before the model's words
POLL_TIMES = [(300, "poll_5m"), (1800, "poll_30m"), (3600, "poll_1h"), (21600, "poll_6h"),
              (86400, "poll_1d"), (259200, "poll_3d"), (604800, "poll_7d")]
DEFAULT_VIS = VISIBILITIES[2]  # followers: private by default


def autosave_ms(cfg):
    """post.autosave_ms: how long after the last key the editor keeps its draft (the
    windows had 700 and 1500 ms)."""
    return max(100, int((cfg.get("post") or {}).get("autosave_ms", 700)))


def draft_key(view, reply_to=None, quote=None, edit=None, invite=False):
    """The draft's name: my post being corrected, a call into a thread (its own, not the
    reply's), or the core's key for a reply / a quote / a new post."""
    if edit is not None:
        return f"edit:{edit.id}"
    if invite and reply_to is not None:
        return f"invite:{reply_to.id}"
    return view.draft_key(reply_to.id if reply_to else None, quote.id if quote else None)


@dataclass
class Start:
    """What a new editor holds at first. visibility is one of VISIBILITIES; language
    None means "leave the editor's choice"; hint is an i18n key or ""."""
    text: str = ""
    cw: str = ""
    visibility: str = DEFAULT_VIS
    language: str | None = None
    media: list = field(default_factory=list)   # [(path, description, focus?)]
    sensitive: bool = False
    poll: dict | None = None
    hint: str = ""
    restored: bool = False


def start(view, key, reply_to=None, start_text="", invite=False):
    """A draft if there is one; else the mentions of the post replied to (or "@" for a
    call into the thread) and its content warning, and who sees it."""
    d = view.get_draft(key)
    vis = view.reply_visibility(reply_to)
    s = Start()
    if d:
        s.text = d.get("text", "")
        s.cw = d.get("cw", "")
        vis = OLD_VIS.get(d.get("visibility"), d.get("visibility") or vis)
        if "language" in d:
            s.language = d["language"]
        s.media = [tuple(m) for m in d.get("media", [])]
        s.sensitive = bool(d.get("sensitive"))
        s.poll = d.get("poll") or None
        s.hint, s.restored = "draft_restored", True
    else:
        if start_text:
            s.text = start_text
        # the post's warning carried on (post.reply_warning = "copy", as Mastodon's
        # page) or not ("none": a talk stayed under its first post's topic, 29.10)
        keep_cw = view.cfg["post"].get("reply_warning", "copy") == "copy"
        if invite and reply_to is not None:  # only the one called: nobody else bothered
            s.text, s.hint = "@", "invite_hint"
            s.cw = (reply_to.warning or "") if keep_cw else ""
        elif reply_to is not None:
            me = view.me
            s.text = reply_mentions(reply_to, me.handle if me else "")
            s.cw = (reply_to.warning or "") if keep_cw else ""
    s.visibility = vis if vis in VISIBILITIES else DEFAULT_VIS
    return s


def snapshot(text, cw, visibility, media, language, sensitive, poll):
    """A draft as it is kept."""
    return {"text": text, "cw": cw, "visibility": visibility, "media": media,
            "language": language, "sensitive": sensitive, "poll": poll}


def keep(snap, initial, has_draft):
    """What to do with the draft now: "skip" (nothing new), "delete" (emptied), "save"."""
    if snap == initial and not has_draft:
        return "skip"
    if not snap["text"].strip() and not snap["media"] and not snap["cw"]:
        return "delete"
    return "save"


def when_utc(local):
    """"When to send" as typed (an ISO date and time of this computer, "2026-10-23 09:30"
    or a browser's datetime-local) → what the server wants (UTC, ISO 8601); None — now.
    ValueError for words that aren't a time."""
    if not local or not str(local).strip():
        return None
    from datetime import UTC, datetime
    try:
        t = datetime.fromisoformat(str(local).strip())
    except ValueError:
        raise ValueError(str(local)) from None
    if t.tzinfo is None:
        t = t.astimezone()  # this computer's zone (the browser's, on localhost)
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def poll_data(enabled, options, expires_in, multiple):
    """The poll to send, or None: off, or fewer than two options filled in."""
    if not enabled:
        return None
    options = [o.strip() for o in options if o.strip()]
    if len(options) < 2:
        return None
    return {"options": options, "expires_in": expires_in, "multiple": bool(multiple)}


@dataclass(frozen=True)
class Count:
    n: int           # characters that count against the limit
    limit: int
    parts: int       # >1: a chain, each part counted on its own
    over: bool
    flat_tags: tuple  # #lowercasetags worth CamelCase (post.camelcase_hint)
    newcomers: tuple = ()  # @handles a private answer brings into the talk (newcomers())


def count(text, cw, limit, cfg, reply_to=None, visibility="", me=None):
    """The counter's words. With reply_to (the Post answered), visibility and me (my
    Account): whom a private answer adds to the talk, as the window
    shows it before it is sent."""
    parts = chain_parts(text) if cfg["post"].get("chain", True) else []
    if len(parts) > 1:
        n = max(len(x) for x in parts) + len(cw)
    else:
        n = len(text) + len(cw)
    flat = tuple(flat_tags(text)) if cfg["post"]["camelcase_hint"] else ()
    new = tuple(newcomers(text, reply_to, visibility, me))
    return Count(n, limit, max(1, len(parts)), n > limit, flat, new)


TYPED_MENTION = re.compile(r"(?<![\w/@])@(\w[\w.-]*(?:@[\w-]+(?:\.[\w-]+)+)?)")


def _me_parts(me):
    """(my username, my server's host) of my Account."""
    if me is None:
        return "", ""
    username = (me.username or me.handle or "").split("@")[0]
    return username.casefold(), (urlsplit(me.url or "").hostname or "").casefold()


def pasted_files(text):
    """Files pasted as their paths — what a terminal gets when a file is dropped on it,
    or a file manager's "copy" pasted: every line a path (quoted or not, "file://…" too)
    of a file that is there → [paths]; anything else (words, a link, a path that isn't
    a file) → [] — it is text. For an editor without a clipboard of pictures."""
    from pathlib import Path
    from urllib.parse import urlsplit
    from urllib.request import url2pathname
    lines = [x.strip() for x in str(text or "").splitlines() if x.strip()]
    if not lines or len(lines) > 20:
        return []
    out = []
    for line in lines:
        line = line.strip("'\"")
        if line.startswith("file://"):
            # file:///C:/x%20y.png on Windows, file:///home/x%20y.png elsewhere
            line = url2pathname(urlsplit(line).path)
        else:
            line = line.replace("\\ ", " ")  # a shell's escaped spaces
        try:
            p = Path(line).expanduser()
            if not (p.is_absolute() and p.is_file()):
                return []
        except (OSError, ValueError):
            return []
        out.append(str(p))
    return out


def newcomers(text, reply_to, visibility, me=None):
    """Who a private answer being written brings into the talk: the @people in the text
    that the private post answered neither came from nor named (cardtext.newcomers for
    one received). [@handle as typed], in order; [] when it isn't private, answers nothing
    or answers a post that isn't private."""
    if visibility != "direct" or reply_to is None or \
            getattr(reply_to, "visibility", "") != "direct":
        return []
    mine, host = _me_parts(me)

    def norm(handle):
        h = handle.lstrip("@").casefold()
        user, _sep, at = h.partition("@")
        return user if at == host else h

    known = {norm(reply_to.author.handle)} | {norm(m.handle) for m in reply_to.mentions}
    known.add(mine)
    out = []
    for typed in TYPED_MENTION.findall(text):
        key = norm(typed.rstrip("."))
        if key not in known and "@" + typed.rstrip(".") not in out:
            out.append("@" + typed.rstrip("."))
    return out


TOKEN_AT_END = re.compile(r"(?:^|[\s(«\"'])([#@:])(\w[\w.@-]*)$")


def token_at_end(before):
    """("#", "@" or ":", the word typed right before the cursor) — or (None, None).
    before: the line up to the cursor."""
    m = TOKEN_AT_END.search(before)
    if not m or (m.group(1) in "#:" and not re.fullmatch(r"\w+", m.group(2))):
        return None, None
    if m.group(1) == ":" and len(m.group(2)) < 2:
        return None, None
    return m.group(1), m.group(2)


def suggestions(view, sigil, word):
    """[(what goes in, what the list shows)] for the token being typed, from what's
    known here (post.complete_tags / complete_mentions / complete_emoji)."""
    post = view.cfg["post"]
    if sigil == "#" and post.get("complete_tags", True):
        return [("#" + n, "#" + n) for n in view.tag_suggestions(word)]
    if sigil == "@" and post.get("complete_mentions", True):
        return people_items(view.mention_suggestions(word))
    if sigil == ":" and post.get("complete_emoji", True):
        mine = [(f":{code}:", f":{code}:") for code, _e in view.emoji_suggestions(word)]
        return mine + view.emoji_standard_suggestions(word, max(0, 8 - len(mine)))
    return []


EMOJI_GROUPS = ("faces", "people", "nature", "food", "travel", "things", "symbols")


def emoji_standard(view, words=""):
    """The picker's "Standard" tab as every interface draws it: [(group title, [{"char",
    "code", "name"}])] in the groups' order; with `words`, one untitled group of what they
    find, the best first. [] with post.emoji_standard off."""
    from ...i18n import _
    got = view.emoji_standard(words)
    if words.strip():
        return [("", got)] if got else []
    by = {}
    for e in got:
        by.setdefault(e["group"], []).append(e)
    return [(_("emoji_g_" + g), by[g]) for g in EMOJI_GROUPS if by.get(g)]


def emoji_server(items, words=""):
    """The picker's "Server's" tab: the server's emoji (View.emoji_all's) [(category, [emoji
    dict])], or those whose short name holds `words` (one untitled group)."""
    w = words.strip().strip(":").casefold()
    if w:
        got = [e for e in items if w in e["shortcode"].casefold()]
        return [("", got)] if got else []
    by = {}
    for e in items:
        by.setdefault(str(e.get("category") or ""), []).append(e)
    return list(by.items())


def people_items(people):
    return [("@" + acct, f"@{acct}" + (f" — {name}" if name else "")) for acct, name in people]


def more_people(local, found, n=10):
    """The people known here, then the server's answer without them again."""
    seen = {a.casefold() for a, _n in local}
    more = [(a, nm) for a, nm in found if a.casefold() not in seen]
    return people_items(local + more)[:n]


def worth_offering(items, word):
    """A list with only the word already typed in it isn't worth popping up."""
    return bool(items) and not (len(items) == 1 and
                                items[0][0][1:].casefold() == (word or "").casefold())


def put_alias(text, alias):
    """A post's #abc into a command line: at its start, instead of the #number already
    there, if any."""
    rest = re.sub(r"^\s*#[0-9a-z]+(/\d+)?\s*", "", text) if text.lstrip().startswith("#") \
        else text
    return f"#{alias} " + rest.lstrip()


MEDIA_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".heic",
             ".mp4", ".webm", ".mov", ".mp3", ".ogg", ".m4a", ".flac")


# the kinds of picture made lighter before the upload, each by its own settings
# (post.<kind>_format, _quality, _max_side): a photo, and a PNG — screenshots, drawings.
# A GIF or a WebP (it may move: an animation is never flattened), a video, a sound go
# as they are.
PICTURE_KINDS = {"photo": (".jpg", ".jpeg", ".jfif", ".heic", ".heif", ".avif", ".tif",
                           ".tiff"),
                 "png": (".png", ".bmp")}
FORMAT_EXT = {"webp": ".webp", "jpeg": ".jpg", "png": ".png"}
PICTURE_KEYS = {"photo": ("photo_format", "photo_quality", "photo_max_side"),
                "png": ("png_format", "png_quality", "png_max_side")}  # [post]'s


def picture_kind(path):
    """"photo", "png" — the kind of picture by its name; None — not one made lighter."""
    low = str(path).lower()
    return next((k for k, exts in PICTURE_KINDS.items() if low.endswith(exts)), None)


def takes_webp(caps):
    """Does the server say it takes WebP? Not said — no: a JPEG goes, any server's."""
    types = [str(x).lower() for x in (getattr(caps, "media_types", None) or [])]
    return "image/webp" in types or "image/*" in types


def fit_for_server(path, caps, folder, images, fmt="", quality=90, max_side=0,
                   limits=True):
    """A picture as the server will take it, and as light as it was asked to be — a
    copy in `folder` (your file isn't touched), or the path itself when nothing is to
    be done.

    limits (post.resize_images): bigger than the server takes (caps.image_bytes,
    caps.image_pixels) — under its pixel limit, then its byte limit (the quality
    lowered, a PNG made smaller). fmt (post.<kind>_format): "webp", "jpeg", "png" — made
    anew in it at `quality`, its metadata gone (EXIF: where it was taken, the camera),
    standing as it was taken; WebP only where the server takes it and the toolkit can
    write it, else JPEG; a picture with transparency never as JPEG (PNG). "" — not made
    anew for that. max_side: the longest side at most that (0 — any). A GIF and a WebP
    go as they are: they may move, and an animation is never flattened.

    images: the toolkit's pictures — size(path) -> (w, h) or None, load(path) -> img or
    None (turned as the camera said), scaled(img, w, h), dims(img) -> (w, h),
    alpha(img), save(img, out, kind, quality) -> bool, can(kind) -> bool (WebP: may it
    be written) — qt/compose.py _QtImages, gtk/compose.py _PixbufImages, PilImages."""
    import hashlib
    import logging
    import os
    from pathlib import Path
    max_b, max_px = (int(caps.image_bytes or 0), int(caps.image_pixels or 0)) if limits \
        else (0, 0)
    if str(path).lower().endswith((".gif", ".webp")):
        return path  # it may move: never flatten an animation
    if fmt not in FORMAT_EXT:
        fmt = ""
    size = images.size(path)
    if size is None:
        return path
    big_px = max_px and size[0] * size[1] > max_px
    big_b = max_b and os.path.getsize(path) > max_b
    long = max_side and max(size) > max_side
    if not (big_px or big_b or long or fmt):
        return path
    if fmt == "webp":
        can = getattr(images, "can", None)
        if not takes_webp(caps) or can is None or not can("webp"):
            fmt = "jpeg"  # the server or the toolkit without WebP: the next lightest
    img = images.load(path)
    if img is None:
        return path
    w, h = images.dims(img)
    k = 1.0
    if max_side and max(w, h) > max_side:
        k = max_side / float(max(w, h))
    if max_px and w * h * k * k > max_px:
        k = (max_px / float(w * h)) ** 0.5 * 0.98
    if k < 1:
        img = images.scaled(img, int(w * k), int(h * k))
    alpha = images.alpha(img)
    kind = fmt or ("png" if alpha else "jpeg")
    if kind == "jpeg" and alpha:
        kind = "png"  # JPEG has no transparency: what's see-through would go black
    quality = max(1, min(100, int(quality))) if fmt else 90
    # one copy per file: two IMG_0001.jpg from two folders in one post are two
    tag = hashlib.sha1(os.path.abspath(str(path)).encode("utf-8")).hexdigest()[:6]
    out = Path(folder) / f"upload-{Path(path).stem}-{tag}{FORMAT_EXT[kind]}"
    while True:
        if not images.save(img, str(out), kind, quality):
            return path
        if not max_b or out.stat().st_size <= max_b or quality <= 40:
            break
        if kind == "png":  # a PNG can't get lighter by quality: smaller instead
            w, h = images.dims(img)
            img = images.scaled(img, int(w * 0.8), int(h * 0.8))
        else:
            quality -= 15
    logging.getLogger(__name__).info("%s → %s: %d KB → %d KB", Path(path).name, out.name,
                                     os.path.getsize(path) // 1024,
                                     out.stat().st_size // 1024)
    return str(out)


class PilImages:
    """What fit_for_server needs, with Pillow — for the interfaces without a toolkit's
    pictures of their own: the web page (and the phone through it), the terminal. Only
    the windows made a big photo fit; the others had it refused after the upload
    (21.11)."""

    @staticmethod
    def size(path):
        from PIL import Image
        try:
            with Image.open(path) as im:
                return im.size
        except Exception:  # noqa: BLE001 — not a picture Pillow reads: as it is
            return None

    @staticmethod
    def load(path):
        from PIL import Image, ImageOps
        try:
            with Image.open(path) as im:
                img = ImageOps.exif_transpose(im)  # a phone's photo stands as taken
                img.load()
        except Exception:  # noqa: BLE001
            return None
        img.info = PilImages._kept(img.info)  # its colours, not its EXIF
        return img

    @staticmethod
    def _kept(info):
        """Of a picture's info what is the picture's own: its colours (the ICC profile)
        and its see-through colour — not the EXIF, the comments, the dates."""
        return {k: v for k, v in info.items() if k in ("icc_profile", "transparency")}

    @staticmethod
    def dims(img):
        return img.size

    @staticmethod
    def scaled(img, w, h):
        from PIL import Image
        info = PilImages._kept(img.info)
        if img.mode == "P":  # a palette can't be smoothed: its colours first
            img = img.convert("RGBA" if "transparency" in info else "RGB")
            info.pop("transparency", None)
        img = img.resize((max(1, w), max(1, h)), Image.LANCZOS)
        img.info = info
        return img

    @staticmethod
    def alpha(img):
        return img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info

    @staticmethod
    def can(kind):
        if kind != "webp":
            return True
        from PIL import features
        return bool(features.check("webp"))

    @staticmethod
    def save(img, out, kind, quality):
        # nothing of the original's metadata but its colours (the ICC profile): the
        # EXIF — where, when, which camera — stays home
        icc = {"icc_profile": img.info["icc_profile"]} if img.info.get("icc_profile") \
            else {}
        try:
            if kind == "jpeg":
                img.convert("RGB").save(out, "JPEG", quality=quality, optimize=True, **icc)
            elif kind == "webp":
                rgba = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info
                img.convert("RGBA" if rgba else "RGB").save(
                    out, "WEBP", quality=quality, method=6, **icc)  # the smallest it makes
            else:
                img.save(out, "PNG", optimize=True, **icc)
            return True
        except Exception:  # noqa: BLE001
            return False


def pil_images():
    """PilImages when Pillow is there, else None (a picture then goes as it is)."""
    try:
        import PIL.Image  # noqa: F401
    except ImportError:
        return None
    return PilImages


def picture_rule(cfg, path):
    """What post.* says for this file: (format, quality, longest side) — its kind's
    (post.photo_*, post.png_*); ("", 90, 0) for any other."""
    keys = PICTURE_KEYS.get(picture_kind(path))
    post = (cfg or {}).get("post") or {}
    if keys is None:
        return "", 90, 0
    fmt, quality, side = keys
    return (str(post.get(fmt, "") or ""), int(post.get(quality, 80) or 80),
            int(post.get(side, 0) or 0))


def fit_media(media, cfg, caps, folder, images=None):
    """The editor's media tuples (path, …) with each picture made to fit the server
    (post.resize_images) and as light as its kind asks (post.photo_*, post.png_*) —
    fit_for_server; images: the toolkit's, else Pillow's when it is there. One rule
    for every editor: the windows', their input lines, the terminal's, the page's and
    the phone's."""
    media = [tuple(m) for m in media]
    limits = bool(((cfg or {}).get("post") or {}).get("resize_images", True))
    rules = [picture_rule(cfg, m[0]) for m in media]
    if not limits and not any(r[0] or r[2] for r in rules):
        return media
    images = images or pil_images()
    if images is None:
        return media
    return [(fit_for_server(m[0], caps, folder, images, fmt=r[0], quality=r[1],
                            max_side=r[2], limits=limits),) + m[1:]
            for m, r in zip(media, rules, strict=True)]


# ---- the post's language --------------------------------------------------------------
OTHER_LANG = "\x00other"
LANG_NAMES = {"tok": "toki pona", "jbo": "la .lojban.", "eo": "Esperanto",
              "ia": "Interlingua", "vo": "Volapük", "ie": "Interlingue"}
# each by its own name, for a toolkit with no locale database of its own (GTK)
NATIVE = {"ru": "русский", "en": "American English", "ka": "ქართული", "uk": "українська",
          "be": "беларуская", "kk": "қазақ тілі", "hy": "հայերեն", "az": "azərbaycan",
          "de": "Deutsch", "fr": "français", "es": "español", "it": "italiano",
          "pt": "português", "pl": "polski", "cs": "čeština", "sk": "slovenčina",
          "nl": "Nederlands", "sv": "svenska", "no": "norsk", "nb": "norsk bokmål",
          "da": "dansk", "fi": "suomi", "et": "eesti", "lv": "latviešu", "lt": "lietuvių",
          "ro": "română", "bg": "български", "sr": "српски", "hr": "hrvatski",
          "sl": "slovenščina", "el": "Ελληνικά", "hu": "magyar", "tr": "Türkçe",
          "ar": "العربية", "he": "עברית", "fa": "فارسی", "zh": "中文", "ja": "日本語",
          "ko": "한국어", "hi": "हिन्दी", "th": "ไทย", "vi": "Tiếng Việt", "id": "Indonesia",
          "ca": "català", "eu": "euskara", "gl": "galego", "ga": "Gaeilge", "cy": "Cymraeg",
          "is": "íslenska", "mk": "македонски", "tt": "татар", "cv": "чӑвашла",
          "ba": "башҡорт", "uz": "o‘zbek", "tg": "тоҷикӣ", "ky": "кыргызча",
          "mn": "монгол", "os": "ирон"}
LANG_CODE = re.compile(r"[a-z]{2,3}(-[a-z0-9]{2,8})?")


def language_label(code, native=None):
    """"Русский (ru)": a language by its own name and its code. native(code): the
    toolkit's own name for it, or None (then NATIVE, then the code)."""
    name = LANG_NAMES.get(code) or (native(code) if native else None) or NATIVE.get(code) \
        or code
    first = name[:1]
    # Georgian has no capitals in running text: str.upper() makes Mkhedruli Mtavruli
    if not "\u10d0" <= first <= "\u10ff":
        first = first.upper()
    return f"{first}{name[1:]} ({code})"


def languages(cfg, added=()):
    """The codes the editor offers: post.languages, then post.language if it's not
    among them, then those added by hand ("Another language…")."""
    post = cfg["post"]
    return list(dict.fromkeys(list(post.get("languages") or []) +
                              ([post["language"]] if post.get("language") else []) +
                              list(added or [])))


_NOT_WORDS = re.compile(r"(https?://\S+|[@#:][\w.@-]+:?|`[^`]*`)")


def lang_mismatch(cfg, text, language):
    """post.lang_check: the language the text reads as, when it isn't the one the post
    is marked with (the editor asks "send as is?"); None — they agree, or it's unsure,
    or the check is off. Links, @names, #tags and :emoji: aren't the text's words."""
    language = language or cfg["post"].get("language")  # "as in settings"
    if not cfg["post"].get("lang_check") or not language:
        return None
    from ...core import langs
    said = langs.guess(_NOT_WORDS.sub(" ", text or ""), min_words=8)
    if not said or said in ("cyrillic", "latin") or said == langs.base(language):
        return None
    return said


def lang_question(said, language):
    """The words of that question: (title, text, "mark it <said>", "send as is")."""
    from ...i18n import _
    return (_("lang_check_title"),
            _("lang_check_text", said=language_label(said), chosen=language_label(language)),
            _("lang_check_switch", said=language_label(said)), _("lang_check_anyway"))
