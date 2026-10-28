"""The pictures on fedtail's buttons, from the theme. Plain Python (no Qt, no GTK):
which picture a button gets, from which file, in which colours — the frontends only draw
what this gives them.

Where they come from is the theme's choice ([shape] icons), which ui.icons may override:

    "desktop"     the desktop's icon theme (Breeze, Adwaita…), by freedesktop names —
                  the "system" and "debug" themes;
    "own"         the theme's own set: themes/<theme>/icons/, a file a picture —
                  every other theme;
    "additional"  (ui.icons only) the own set, and the messengers' pictures (EXTENDED)
                  also outside the split layout, on the buttons that have them;
    "words"       no pictures: words and glyphs (≡ ↔ ❯) — terminal, bnw.

Pictures are of two kinds. STANDARD ones are always there when there are pictures at
all: the menu, the width, the columns, the lanes, the buttons under a post, who sees it.
EXTENDED ones are the messengers' (the input line, the roster, the author's bar, a
person's flower): shown in the split layout, and anywhere with "additional".

A theme's set is a folder next to its file: themes/mine.toml → themes/mine/icons/,
reply.svg or reply.png (reply@2x.png beside it for a sharp screen). What the folder
lacks comes from the themes it inherits (their folders), then from [pictures] from = a
theme whose set it borrows, and last from the fallback set (data/icons/fallback/) —
an emergency only: no built-in theme needs it (tests/test_iconpack.py), and a theme of
yours that does is told in the log. An SVG may leave its colours blank — {c} the colour,
{l} its light top, {d} the outline, {o} lines outside the shape (the outline's colour;
silhouette, which cuts {d} lines out of a filled shape, draws them in its colour) —
filled as [pictures] style says, from the theme's accent or [pictures.colors].
"""

from __future__ import annotations

import functools
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .palette import Color, readable_on

log = logging.getLogger(__name__)

FALLBACK_DIR = Path(__file__).resolve().parent.parent / "data" / "icons" / "fallback"
# the lanes' library (tools/lane_pictures.py): what one's own lane may wear, coloured by
# each theme's [pictures] as its own; a theme's file of the same name wins
LANES_DIR = Path(__file__).resolve().parent.parent / "data" / "icons" / "lanes"
STYLES = ("gloss", "agent", "flat", "silhouette", "qip", "none")
SOURCES = ("desktop", "own", "words")             # a theme's [shape] icons
CHOICES = ("theme", "desktop", "own", "additional", "words")  # ui.icons
EXTS = (".svg", ".png")

# always there when there are pictures at all
STANDARD = {
    "menu": "the ≡ menu",
    "wide": "posts across the whole width (↔)",
    "columns": "lanes side by side (❯)",
    "close": "close a tab, a panel",
    "more": "a post's ⋯ menu",
    "refresh": "refresh a lane",
    "mark_read": "mark all read",
    "filter": "what a lane shows",
    "edit": "edit (my profile)",
    "accept": "approve (a follow request)",
    "reject": "reject (a follow request)",
    "clear": "clear (Activity)",
    "reply": "Reply under a post",
    "star": "Favourite under a post",
    "star_full": "Favourite, done; my favourites",
    "boost": "Boost under a post",
    "thread": "Thread under a post",
    "bookmark": "Bookmark under a post; my bookmarks",
    "public": "who sees a post: everyone; the federated lane",
    "unlisted": "who sees a post: quietly public",
    "private": "who sees a post: followers",
    "direct": "who sees a post: the mentioned only; private messages",
    "home": "the home lane",
    "local": "my server's lane",
    "mentions": "mentions",
    "replies": "replies to me",
    "subs": "followed threads",
    "bots": "bots",
    "my_posts": "my posts",
    "requests": "follow requests",
    "list": "a list; add to a list",
    "activity": "Activity (likes, boosts, follows)",
    "tags": "followed tags",
}
# the messengers': the split layout's, anywhere with ui.icons = "additional"
EXTENDED = {
    "warning": "the content warning (CW)",
    "attach": "add pictures or a file",
    "poll": "add a poll",
    "emoji": "emoji",
    "send": "Send",
    "follow": "Follow",
    "unfollow": "Unfollow",
    "talk": "a private talk; write privately",
    "profile": "open the profile",
    "accounts": "the accounts button",
    "settings": "how the roster looks (⚙)",
    "expand": "make bigger",
    "status": "a person (QIP's flower, the Agent's @, Psi's star)",
    "nobody": "a face for nobody: no one under the pointer, no picture yet",
}
NAMES = {**STANDARD, **EXTENDED}
# a picture a set may leave out: another stands in (a file of its own name wins)
ALIASES = {"federated": "public", "bookmarks": "bookmark", "my_likes": "star_full",
           "readone": "mark_read", "notifications": "activity", "tag": "tags"}
# "desktop": the desktop icon theme's names for each, the first found wins
FREEDESKTOP = {
    "menu": ("application-menu", "open-menu-symbolic"),
    # the desktop's own "fit to width" (Breeze has it): its look, not arrows drawn here
    "wide": ("zoom-fit-width", "zoom-fit-best", "view-fullscreen"),
    "columns": ("view-split-left-right",),
    "close": ("window-close", "window-close-symbolic"),
    "more": ("overflow-menu", "application-menu", "view-more-symbolic"),
    "refresh": ("view-refresh",),
    "mark_read": ("mail-mark-read", "object-select-symbolic"),
    "filter": ("view-filter",),
    "edit": ("document-edit",),
    "accept": ("dialog-ok",),
    "reject": ("dialog-cancel",),
    "clear": ("edit-clear-all",),
    "reply": ("mail-reply-sender",),
    "star": ("rating-unrated", "non-starred-symbolic"),
    "star_full": ("rating", "starred-symbolic"),
    "boost": ("media-playlist-repeat", "retweet"),
    "thread": ("view-list-tree", "format-indent-more"),
    "bookmark": ("bookmark-new", "bookmarks"),
    "public": ("globe", "applications-internet"),
    "unlisted": ("object-unlocked", "unlock"),
    "private": ("object-locked", "lock"),
    "direct": ("mail-message", "mail-unread"),
    "home": ("system-users",),
    "local": ("go-home",),
    "federated": ("applications-internet",),
    "mentions": ("mail-mark-important",),
    "replies": ("mail-replied",),
    "subs": ("mail-thread-watch",),
    "bots": ("applications-system",),
    "my_posts": ("document-edit",),
    "requests": ("list-add-user",),
    "list": ("view-list-details",),
    "activity": ("rating",),
    "bookmarks": ("bookmarks",),
    "my_likes": ("starred-symbolic",),
    "tags": ("tag",),
    "readone": ("mail-mark-read", "object-select-symbolic"),
    "warning": ("dialog-warning",),
    "attach": ("mail-attachment",),
    "poll": ("office-chart-bar", "view-statistics"),
    "emoji": ("face-smile",),
    "send": ("document-send", "mail-send"),
    "follow": ("list-add-user",),
    "unfollow": ("list-remove-user",),
    "talk": ("mail-message-new",),
    "profile": ("user-identity", "im-user"),
    "accounts": ("system-users",),
    "settings": ("configure", "preferences-system"),
    "expand": ("view-fullscreen",),
    "status": ("user-online",),
    "nobody": (),
    # the lanes' library: the desktop's where it has one alike, else fedtail's drawing
    "important": ("notifications", "preferences-desktop-notification-bell"),
    "commented": ("dialog-messages", "mail-thread-watch"),
    "person": ("user-identity",), "people": ("system-users",), "heart": ("emblem-favorite",),
    "news": ("news-subscribe", "application-rss+xml"), "rss": ("application-rss+xml",),
    "search": ("edit-find", "system-search"), "link": ("insert-link",),
    "image": ("image-x-generic",), "camera": ("camera-photo",), "film": ("video-x-generic",),
    "music": ("audio-x-generic",), "book": ("accessories-dictionary",),
    "code": ("text-x-script", "applications-development"), "game": ("input-gaming",),
    "globe": ("globe", "applications-internet"), "clock": ("chronometer", "clock"),
    "calendar": ("view-calendar", "x-office-calendar"), "chart": ("office-chart-bar",),
    "flag": ("flag",), "pin": ("mark-location",), "inbox": ("mail-folder-inbox",),
    "shield": ("security-high",), "wrench": ("tools", "applications-utilities"),
}
# a lane (sidebar, roster, a tab) by its name → its picture
LANE = {"home": "home", "local": "local", "federated": "federated", "mentions": "mentions",
        "replies": "replies", "subs": "subs", "bots": "bots", "my_posts": "my_posts",
        "requests": "requests", "list": "list", "activity": "activity",
        "bookmarks": "bookmarks", "direct": "direct", "my_likes": "my_likes", "tags": "tags",
        "to_me": "replies", "important": "important", "commented": "commented",
        "unsorted": "list", "custom": "list"}


def lane_picture(name, icon=None):
    """The picture of a lane ("list:12" → "list"), or None. icon: the one the lane asks
    for itself (a lane of rules' `icon`, core.lane_icon) — over its name's."""
    from ..core.atoms import LANE_ICONS
    if isinstance(icon, str) and icon in LANE_ICONS:
        return icon
    return LANE.get((name or "").split(":")[0])


def mode(cfg, shape):
    """Where the pictures come from: ui.icons, or the theme's [shape] icons."""
    chosen = (cfg.get("ui") or {}).get("icons", "theme") if cfg else "theme"
    if chosen in CHOICES and chosen != "theme":
        return chosen
    own = (shape or {}).get("icons", "desktop")
    return own if own in SOURCES else "desktop"


def shown(how, name, split=False):
    """Does this picture go on its button: none with "words"; a messenger's only in
    the split layout or with "additional"; the rest always."""
    if how == "words":
        return False
    if name in EXTENDED:
        return how == "additional" or bool(split)
    return True


def uses_set(how):
    return how in ("own", "additional")


# ---- a theme's set ----------------------------------------------------------------
@dataclass(frozen=True)
class Set:
    """Where a theme's pictures lie (the nearest first, the fallback last), how they
    are coloured, their own colours."""
    dirs: tuple
    style: str = "gloss"
    colors: tuple = ()  # ((name, "#rrggbb"), …)
    color: str = ""     # every picture's colour ("": the theme's accent)

    def find(self, name, exts=EXTS, fallback=True):
        """The file of a picture (or what stands in for it), or None."""
        dirs = self.dirs if fallback else self.dirs[:-1]
        for n in (name, ALIASES.get(name)):
            if not n:
                continue
            for d in dirs:
                for ext in exts:
                    p = Path(d) / f"{n}{ext}"
                    if p.is_file():
                        return p
        return None

    def color_of(self, name):
        return dict(self.colors).get(name)


def for_theme(theme):
    """The set of a theme (Qt's or GTK's: .icon_dirs, .pictures)."""
    pics = getattr(theme, "pictures", None) or {}
    colors = pics.get("colors") or {}
    return Set(dirs=tuple(str(d) for d in getattr(theme, "icon_dirs", ()) or ())
               + (str(LANES_DIR), str(FALLBACK_DIR)),
               style=pics.get("style") if pics.get("style") in STYLES else "gloss",
               colors=tuple(sorted((str(k), str(v)) for k, v in colors.items())),
               color=str(pics.get("color") or ""))


_told = set()


def missing(theme_id, pset):
    """The pictures a theme's own set (and what it inherits) lacks — the fallback stands
    in for them. Said once in the log."""
    gone = sorted(n for n in NAMES if pset.find(n, fallback=False) is None)
    if gone and (theme_id, pset.dirs) not in _told:
        _told.add((theme_id, pset.dirs))
        log.warning("theme '%s': no picture of its own for %s — from the fallback set",
                    theme_id, ", ".join(gone))
    return gone


# ---- colouring an SVG -------------------------------------------------------------------
_SHINE = re.compile(r'<ellipse[^>]*opacity="\.35"/>')
_WIDTH = re.compile(r'stroke-width="([\d.]+)"')
_FIRST = re.compile(r"<(?:path|rect|circle|ellipse|polygon|polyline|line)\b[^>]*>")


def styled(text, style, base, bg=None):
    """An SVG's blanks filled: {c} base, {l} its light top, {d} the outline — the way
    `style` draws (gloss: a gradient and a shine; agent: a brighter shine, a softer
    outline; flat: plain colour, no shine; silhouette: plain colour, no rim, the inner
    lines cut out (point.im); qip: a strong shine, a thick dark outline;
    none: the blanks filled, nothing else touched). bg: what the pictures stand on —
    an outline as dark as a dark theme's background is drawn light instead (the
    outline-only pictures, a star, an @, vanished on nord)."""
    base = base if isinstance(base, Color) else Color.parse(str(base))
    light = base.lighter(165)
    if style == "qip":
        text = text.replace('opacity=".35"', 'opacity=".55"')
        text = _WIDTH.sub(lambda m: f'stroke-width="{float(m.group(1)) * 1.35:.2f}"', text)
        light, dark = base.lighter(150), base.darker(300)
    elif style == "silhouette":
        # point.im's way: one plain colour, no shine, no rim — a filled shape's lines
        # (the ≡ of a menu, a list's bullets) cut out of it in the background's colour;
        # a picture drawn only in lines keeps them in its own colour. A darker rim made
        # every picture a little raised button (23.10)
        # cut out only when the picture starts with a filled shape the lines lie on
        # (a menu's box, an envelope); lines drawn first are the picture itself (a
        # thread's branch, refresh's arc) and keep its colour
        first = _FIRST.search(text.split("</defs>")[-1])
        filled = bool(first) and ('fill="url(#g)"' in first.group(0)
                                  or 'fill="{c}"' in first.group(0))
        text = _SHINE.sub("", text).replace('fill="url(#g)"', 'fill="{c}"')
        light = base
        if filled and bg:
            back = bg if isinstance(bg, Color) else Color.parse(str(bg))
            return text.replace("{c}", base.name()).replace("{l}", light.name()) \
                .replace("{d}", back.name()).replace("{o}", base.name())
        dark = base
    elif style == "flat":
        text = _SHINE.sub("", text).replace('fill="url(#g)"', 'fill="{c}"')
        dark = base.darker(140)
    elif style == "agent":
        text = text.replace('opacity=".35"', 'opacity=".6"')
        dark = base.darker(135)
    else:  # gloss, none
        dark = base.darker(170)
    if bg:
        back = bg if isinstance(bg, Color) else Color.parse(str(bg))
        if abs(dark.lightness() - back.lightness()) < OUTLINE_CONTRAST:
            dark = base.lighter(170) if back.lightness() < 128 else base.darker(260)
            if abs(dark.lightness() - back.lightness()) < OUTLINE_CONTRAST:
                dark = readable_on(back)
    return text.replace("{c}", base.name()).replace("{l}", light.name()) \
        .replace("{d}", dark.name()).replace("{o}", dark.name())


@dataclass(frozen=True)
class Picture:
    kind: str           # "svg" (text: ready to draw) or "png" (path, path2x)
    text: str = ""
    path: str = ""
    path2x: str = ""


PLAIN = frozenset({"menu", "wide", "columns"})
MISSING_RED = "#ff1744"


@functools.lru_cache(maxsize=1)
def mark_missing():
    """Pictures from the fallback set in red: in a development version (FEDTAIL_MARK_MISSING
    = 0 / 1 decides otherwise) — a theme's gaps seen at a glance."""
    import os
    env = os.environ.get("FEDTAIL_MARK_MISSING", "").strip().lower()
    if env in ("0", "off", "no", "false"):
        return False
    if env in ("1", "on", "yes", "true"):
        return True
    from .. import __version__
    return ".dev" in __version__
OUTLINE_CONTRAST = 70  # of HSL lightness, 0–255: less, and the outline is lost


@functools.lru_cache(maxsize=1024)
def picture(pset, name, accent, svg_ok=True, bg=None):
    """What to draw: Picture("svg", text) coloured for this set and accent
    ("#rrggbb"), or Picture("png", path); None when neither the set nor the fallback
    has it. svg_ok=False: a frontend that can't draw SVG — PNGs only."""
    p = pset.find(name, EXTS if svg_ok else (".png",))
    if p is None:
        return None
    if p.suffix == ".png":
        two = p.with_name(p.stem + "@2x.png")
        return Picture("png", path=str(p), path2x=str(two) if two.is_file() else "")
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        log.debug("picture %s: %s", p, e)
        return None
    own = pset.color_of(name) or pset.color_of(p.stem) or pset.color
    if mark_missing() and p.parent.resolve() == FALLBACK_DIR:
        # a development version: what the theme lacks, in red (system.toml [pictures])
        return Picture("svg", text=styled(text, "silhouette", MISSING_RED, bg))
    # the sidebar's top buttons (≡ ↔ ❯) are buttons already: their pictures plain, not
    # a glossy button drawn on a button (qip's looked raised twice, 23.10)
    style = "silhouette" if name in PLAIN and pset.style != "none" \
        else pset.style
    try:
        return Picture("svg", text=styled(text, style, own or accent, bg))
    except ValueError:  # a colour that isn't one (themefile warned): the accent
        return Picture("svg", text=styled(text, style, accent, bg))


def has_png(pset):
    """Some of the set's pictures are PNGs (drawable without an SVG renderer)."""
    return any(any(Path(d).glob("*.png")) for d in pset.dirs)
