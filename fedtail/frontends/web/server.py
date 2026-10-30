"""The web interface's server: the page, and a small JSON API over the Core.

Standard library only (http.server). Who may use it: whoever has the key — a
random secret kept in the profile's data folder and printed as a link at start;
the link puts it into a cookie (HttpOnly, SameSite=Strict). Every POST also needs
the X-Fedtail header, which a form on another site can't send. The page loads
scripts from here only (Content-Security-Policy); server HTML is cleaned here,
before it reaches the page. The key never goes into the log.
"""

import collections
import hmac
import json
import logging
import os
import re
import secrets
import sys
import threading
import time
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from ... import __version__, i18n, version
from ...core import config
from ...core.view import View
from ...i18n import _
from ...model import Account, Share, real
from ...model.text import reply_mentions, snippet
from ..common import timed
from ..common.cardtext import context_chars, indent_of
from ..common.commands import Commands
from ..richtext import clean
from ..richtext import link_chars as richtext_link_chars

log = logging.getLogger(__name__)

COOKIE = "fedtail_web"
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8"),
          # Web Push: shows what the user's server sends to this browser (data/web/sw.js)
          "/sw.js": ("sw.js", "text/javascript; charset=utf-8")}
POSSUM = {"/possum.png": ("fedtail.png", "image/png"),
          "/possum.gif": ("fedtail-swing.gif", "image/gif")}
CSP = ("default-src 'self'; img-src 'self' data:; media-src https: 'self'; "
       "style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
       "base-uri 'none'; form-action 'self'")
WAIT_SECONDS = 25
LINK_SECONDS = 15 * 60  # a one-time login link is good this long
MAX_CLIENTS = 32        # connections at once (a phone and a laptop need a handful)
SOCKET_SECONDS = WAIT_SECONDS + 35  # a client that sends nothing this long is dropped
# the browser hung up: nothing to answer, nothing to report
GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)
_UPLOAD = re.compile(r"[A-Za-z0-9_-]{16}(\.[a-z0-9]{1,6})?")
MAX_UPLOAD = 40 * 1024 * 1024  # bytes a file of a post may have (servers take less)
# "~": all accounts in one window — "work~123", a post or person of another account
# (core/merged.py); still one path segment, no "/" and no ".." into the API
_ID = re.compile(r"[A-Za-z0-9_.~-]{1,100}")


def one_id(value):
    """A post or account id from the page: one path segment, never a path into the
    API ("1/../../statuses/2/reblog")."""
    value = str(value or "")
    if not _ID.fullmatch(value) or value in (".", ".."):
        raise ValueError("bad id")
    return value


def load_key(data_dir):
    """The profile's web key: made once, kept readable by the owner only."""
    path = data_dir / "web.key"
    try:
        key = path.read_text("utf-8").strip()
        if len(key) >= 20:
            return key
    except OSError:
        pass
    key = secrets.token_urlsafe(24)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)  # O_CREAT would keep an old file's mode
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(key)
    return key


def _btn_json(b):
    return {"label": b.label, "act": list(b.act), "primary": b.primary, "tip": b.tip}


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _focus(value):
    """A picture's focus from the page: (x, y), each -1…1 (y up), or None."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        x, y = (float(v) for v in value)
    except (TypeError, ValueError):
        return None
    if x != x or y != y:  # NaN
        return None
    return (round(max(-1.0, min(1.0, x)), 2), round(max(-1.0, min(1.0, y)), 2))


def _light(colors):
    """Is the theme a light one (its text darker than its page)?"""
    def lum(c):
        c = c if isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}.*", c) else ""
        if not c:
            return None
        r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
        return 0.299 * r + 0.587 * g + 0.114 * b
    text = lum(colors.get("text"))
    page = lum(colors.get("view")) or lum(colors.get("window")) or lum(colors.get("card"))
    return text is None or page is None or page > text


def static_text(name):
    return resources.files("fedtail").joinpath(f"data/web/{name}").read_text("utf-8")


# ---- what the page gets -------------------------------------------------------------
def _https(url):
    return url if isinstance(url, str) and url.startswith("https://") else ""


# the page's pictures through /pic (the browser on a page of ours); the phone (which takes
# these same answers, android/…/bridge.py) loads the addresses itself: False there
PIC_THROUGH = True


def _pic(url):
    """A picture's address for the page: through this server (/pic, the windows' disk
    cache and their checked fetch) — the browser asked other servers itself, and some
    give their pictures to no other site (avatars stayed grey, 29.10); it no longer
    tells them who looks either."""
    url = _https(url)
    if not PIC_THROUGH:
        return url
    return "/pic?u=" + quote(url, safe="") if url else ""


def _picture_later():
    from ..common.images import Cache
    return Cache.LATER_TRIES


def _iso(t):
    return t.isoformat().replace("+00:00", "Z") if t else ""


def account_json(acc):
    if acc is None:
        return {"id": None, "handle": "", "name": "", "avatar": "", "url": "", "bot": False}
    out = {"id": acc.id, "handle": acc.handle, "name": acc.name or acc.username,
           "avatar": _pic(acc.avatar_static), "url": _https(acc.url), "bot": acc.bot}
    if acc.color:  # people.nick_colors: my colour for their name
        out["color"] = acc.color
    if acc.emojis and ":" in out["name"]:  # :blobcat: in a name — its picture, as in a post
        out["name_html"] = with_emojis(escape(out["name"]), acc.emojis)
    return out


def web_clean(html, link_chars=40):
    """Server HTML, cleaned (richtext.clean) — minus the inline styles meant for Qt,
    which the page's CSP refuses anyway."""
    return clean(html, link_chars=link_chars).replace(' style="text-decoration:none;"', "")


_SHORTCODE = re.compile(r":([A-Za-z0-9_]{1,64}):")


def with_emojis(html, emojis):
    """:shortcode: in cleaned HTML → the emoji's picture (https only; the code and the
    address are escaped, so nothing of the post becomes markup)."""
    if not emojis or ":" not in html:
        return html
    pics = {e.shortcode: _pic(e.static_url or e.url) for e in emojis}

    def one(m):
        url = pics.get(m.group(1))
        if not url:
            return m.group(0)
        code = escape(m.group(0))
        return f'<img class="emoji" src="{escape(url)}" alt="{code}" title="{code}">'
    # outside tags only: a shortcode inside an attribute stays text
    return re.sub(r"(<[^>]*>)|([^<]+)",
                  lambda m: m.group(1) or _SHORTCODE.sub(one, m.group(2)), html)


def _api_error(e):
    """What the page may show of a failure: the server's own answer ("HTTP 422: …"),
    or just what kind of failure it was — never a request's address."""
    from ...protocols.base import ServerError
    return str(e)[:300] if isinstance(e, ServerError) else e.__class__.__name__


def media_json(m):
    url = m.url or m.remote_url  # a picture through /pic too; a video plays from its own
    return {"kind": m.kind, "preview": _pic(m.preview),
            "url": _pic(url) if m.kind == "image" else _https(url),
            "alt": m.alt, "w": m.width, "h": m.height}


def poll_json(poll):
    if poll is None:
        return None
    total = poll.total
    return {"id": poll.id if hasattr(poll, "id") else poll.ref.id,
            "options": [{"title": o.title, "votes": o.votes,
                         "share": round(100 * (o.votes or 0) / total) if total else 0}
                        for o in poll.options],
            "multiple": poll.multiple, "expired": poll.expired, "voted": poll.voted,
            "mine": list(poll.my_votes),
            # how many people, where the server says (Qt's footer); else the votes
            "summary": " · ".join(x for x in (
                _("poll_people", n=poll.people) if poll.people is not None else
                _("poll_votes", n=poll.votes),
                _("poll_closed") if poll.expired else
                (_("poll_until", when=poll.expires.astimezone().strftime("%d.%m %H:%M"))
                 if poll.expires else ""),
                _("poll_multiple") if poll.multiple and not poll.expired else "") if x)}


def card_json(card):
    if card is None or not _https(card.url):
        return None
    return {"url": card.url, "title": card.title, "description": card.description,
            "image": _pic(card.image), "provider": card.provider}


def quote_json(view, quote):
    if quote is None:
        return None
    if quote.post is None or quote.state != "accepted":
        key = "quote_" + quote.state if quote.state in QUOTE_STATES else "quote_unavailable"
        return {"id": quote.id, "note": _(key)}
    q = quote.post
    # behind its warning, as the windows show it (cardtext.quote_bit): the warning, not the words
    return {"id": q.id, "account": account_json(q.author),
            "text": "⚠ " + q.warning if q.warning else snippet(q, 300),
            "warning": q.warning or "",
            "created": _iso(q.created), "media": len(q.media)}


QUOTE_STATES = {"pending", "rejected", "revoked", "deleted", "unauthorized",
                "blocked_account", "blocked_domain", "muted_account"}


def bit_json(b):
    return {"text": b.text, "link": b.link, "tip": b.tip, "kind": b.kind} \
        if b is not None else None


def event_json(spec, dismiss_one=True):
    """An event's row (common/activity.EventParts) as the page and the phone draw it:
    who (names with their fedtail:account/ links), what, when, the post it is about
    and its link, × (fedtail:eventhide/…), a request's yes / no links with their words.
    Every action is a fedtail: link: /api/link does it, as for a card's ⋯."""
    from ..common.activity import ANSWER_WORDS, event_parts
    parts = event_parts(spec.extra["row"], web_date, dismiss_one)
    # :blobcat: in a name — its picture, as on a card (account_json); beside the pairs,
    # which the phone reads as they are
    html = []
    for i, (name, _url) in enumerate(parts.people):
        emojis = parts.emojis[i] if i < len(parts.emojis) else ()
        html.append(with_emojis(escape(name), emojis) if emojis and ":" in name else "")
    return {"kind": parts.kind, "people": [list(x) for x in parts.people],
            "people_html": html, "more": parts.more,
            "what": parts.what, "when": parts.when, "notice": parts.notice,
            "post": parts.post, "post_link": parts.post_link, "hide": parts.hide,
            "hide_tip": parts.hide_tip, "answers": [list(x) for x in parts.answers],
            "answer_words": [[_(words), _(tip)] for words, tip in ANSWER_WORDS],
            "tip": parts.tip, "unread": bool(spec.unread)}


def words_json(view, spec, date):
    """The words around a card (common/cardtext.py): the windows' own."""
    from ..common.cardtext import card_words
    w = card_words(spec, view.cfg, date)
    return {"boosted": bit_json(w.boosted), "meta": [bit_json(b) for b in w.meta],
            "context": bit_json(w.context), "warning": w.warning, "folded": w.folded,
            "my_replies": [bit_json(b) for b in w.my_replies],
            "conversation": bit_json(w.conversation), "reactions": w.reactions,
            "quote": bit_json(w.quote), "quote_inner": bit_json(w.quote_inner),
            "newcomer": bit_json(w.newcomer),
            "thread_news": bit_json(w.thread_news)}


def web_date(when):
    """A time as the cards say it: today's hour, else the day too (the windows' way)."""
    if not when:
        return ""
    from datetime import datetime
    local = when.astimezone()
    if local.date() == datetime.now().astimezone().date():
        return local.strftime("%H:%M")
    return local.strftime("%d.%m.%Y %H:%M")


def post_json(view, entry, alias=None, unread=False, parent=None, number=None, depth=None,
              item_id=None, spec=None):
    """A lane entry (Post or Share) as the page draws it; spec (common/lane.py): the
    card's own words come with it."""
    p = real(entry)
    html = p.text
    if view.cfg["feed"].get("collapse_tags", True):  # a tail of #tags: "… +N" (the windows')
        from ...model.text import collapse_tag_stuffing
        html = collapse_tag_stuffing(html, full=number is not None or depth is not None)
    if view.cfg["ui"]["links_in_app"]:
        from dataclasses import replace as _with
        html = view.in_app(_with(p, text=html))
    me = view.me
    out = {
        "id": entry.id, "item": item_id or entry.id, "sid": p.id, "alias": alias,
        "account": account_json(p.author), "created": _iso(p.created),
        "edited": p.edited is not None, "visibility": p.visibility,
        "warning": p.warning, "sensitive": p.sensitive,
        "html": with_emojis(web_clean(html, richtext_link_chars(view.cfg)), p.emojis),
        "url": _https(p.url or p.uri), "media": [media_json(m) for m in p.media],
        "counts": {"replies": p.counts.replies, "shares": p.counts.shares,
                   "likes": p.counts.likes},
        "mine": {"liked": p.mine.liked, "shared": p.mine.shared,
                 "bookmarked": p.mine.bookmarked},
        "poll": poll_json(p.poll), "card": card_json(p.card), "quote": quote_json(view, p.quote),
        "unread": bool(unread), "own": bool(me and p.author.id == me.id),
        "reply_to": p.reply_to, "lang": p.lang,
        "reply_prefix": reply_mentions(p, me.handle if me else ""),
    }
    if isinstance(entry, Share):
        out["shared_by"] = account_json(entry.by)
    via = view.via(entry) if hasattr(view, "via") else ""
    if via:  # all accounts in one window: which of mine got it (and acts on it)
        out["via"] = {"text": "→ " + via, "tip": _("via_tip", acct=via)}
        if view.cfg["ui"].get("account_colors", True):  # a colour of its own, as the windows'
            from ..common.lane import account_color
            out["via"]["color"] = account_color(via)
    # where its thread opens (CardSpec.open_at: the lane's, else threads.open_at)
    out["open_at"] = spec.open_at if spec is not None else \
        (view.open_at() if hasattr(view, "open_at") else "post")
    if spec is not None:
        out["words"] = words_json(view, spec, web_date)
        out["item"] = spec.key
    if number is not None:
        out["number"], out["depth"] = number, depth or 0
        out["indent"] = indent_of(view.cfg, depth)  # how far in it is drawn, as the windows
    if p.reply_to and number is None:
        if parent == "missing":
            out["context"] = {"missing": True}
        elif parent is not None:
            out["context"] = {"handle": parent.author.handle,
                              "text": snippet(parent, context_chars(view.cfg)), "id": parent.id}
    return out


# a profile's buttons (common/profile.py): every one
WEB_PROFILE_ACTS = ("details", "edit_profile", "follow", "bell", "boosts", "langs",
                    "mention", "mute", "block", "remove_follower", "endorse", "lists",
                    "collections", "collect",
                    "following", "followers", "note", "copy_handle", "open_browser")


def _chosen(body):
    """The page's pick for a choose() question, or None."""
    got = body.get("chosen")
    return got if isinstance(got, dict) else None


class _WebHost:
    """The window common/links.py talks to, for the web: it waits for each future
    here (the request waits with it) and writes down what the page should do."""

    def __init__(self, view, confirmed, shown=()):
        self.view, self.confirmed, self.out = view, confirmed, {}
        self.shown = list(shown or ())  # the ids of the cards the page (or phone) shows

    def call(self, fut, ok=None, fail=None):
        try:
            got = fut.result(timeout=60)
        except Exception as e:  # noqa: BLE001 — said on the page
            (fail or self.error)(str(e))
            return
        if ok is not None:
            ok(got)
        self.out.setdefault("refresh", True)

    def status(self, text):
        self.out["message"] = str(text)

    def error(self, text):
        self.out["error"] = str(text)

    def confirm(self, title, text, then):
        if self.confirmed:
            then()
        else:
            self.out["confirm"] = str(text)

    def open_url(self, url):
        self.out["open"] = {"url": url}

    def open_thread(self, sid, at="post"):
        self.out["open"] = {"thread": sid, "at": at}

    def open_account(self, acc_id):
        self.out["open"] = {"account": acc_id}

    def _place(self, name, arg="", tab=""):
        self.out["open"] = {"page": name, "arg": arg, "tab": tab}

    # the places a link or a profile button opens: the page draws them (common/places.py)
    def open_tag(self, tag):
        self._place("tag", tag)

    def show_history(self, post):
        self._place("history", real(post).id)

    def report(self, post):
        self._place("report", post.id)

    def open_reactions(self, post, kind):
        self._place("reactions", post.id, kind)

    def open_quotes(self, post):
        self._place("quotes", post.id)

    def open_link_posts(self, url):
        """Who else shared this link: the "link" place (common/places.py)."""
        self._place("link", url)

    def open_people(self, acc, which):
        self._place("people", acc.id, which)

    def edit_profile(self):
        self._place("profile_edit")

    def open_lists(self, acc):
        self._place("list_of", acc.id)

    def put_alias(self, alias):
        self.out["alias"] = alias

    def resolve_link(self, url):
        """A fediverse address: what my server finds there, else the browser."""
        try:
            found = self.view.resolve(url).result(timeout=30)
        except Exception:  # noqa: BLE001 — the browser then
            found = None
        if isinstance(found, Account):
            self.open_account(found.id)
        elif found is not None:
            self.open_thread(found.id)
        elif url.startswith(("https://", "http://")):
            self.open_url(url)

    def copy_handle(self, handle):
        self.out["copy"] = "@" + handle.lstrip("@")

    def read_up_to(self, sid):
        """⋯ → "Read up to here": the one rule (common/lane.read_up_to — by time, a boost
        where it was boosted), over the cards the page shows; marked here, the ids said
        back so the page only paints them read (it had its own count by place)."""
        from ..common.lane import read_up_to
        entries = [self.view.stored(i) for i in dict.fromkeys(map(str, self.shown))]
        ids = read_up_to([e for e in entries if e is not None], str(sid))
        self.view.mark_read(ids)
        self.out["read"] = ids

    def compose(self, reply_to=None, invite=False, edit=None, quote=None, text=None):
        c = {"text": text} if text else {}
        if edit is not None:
            text, cw = self.view.source(edit).result(timeout=30)
            c = {"edit": edit.id, "text": text, "cw": cw,
                 "visibility": real(edit).visibility,
                 # its pictures stay; their descriptions and focus can change
                 "media": [{"id": m.ref.id, "alt": m.alt, "kind": m.kind,
                            "url": _pic(m.preview or m.url),
                            "focus": list(m.focus) if m.focus else None}
                           for m in real(edit).media]}
        elif quote is not None:
            c = {"quote": real(quote).id, "quote_of": "@" + real(quote).author.handle}
        elif reply_to is not None:
            c = {"reply_to": reply_to.id, "invite": bool(invite)}
            if invite:
                c["text"] = "@"
        self.out["compose"] = c

    answer = None
    chosen = None  # {"key", "ticked"}: the page's answer to choose(), asked again with it

    def choose(self, title, text, options, done, check=None):
        """One of a few answers, and maybe a box to tick (common/timed.py): the page
        asks, then sends the same thing again with what was picked."""
        if isinstance(self.chosen, dict):
            want = str(self.chosen.get("key"))
            for key, _label in options:
                if str(key) == want:
                    done(key, self.chosen.get("ticked") is True)
                    return
        self.out["choose"] = {"title": str(title), "text": str(text or ""),
                              "options": [{"key": k, "label": str(lb)} for k, lb in options],
                              "check": str(check) if check else ""}

    def ask_text(self, title, question, then, text="", allow_empty=False):
        if self.answer is not None and (self.answer.strip() or allow_empty):
            then(self.answer)
        else:
            self.out["ask"] = {"title": str(title), "question": str(question), "text": text}

    def redrafted(self, d):
        self.out["compose"] = {"text": d.text, "cw": d.warning, "visibility": d.visibility,
                               "lang": d.language, "reply_to": d.reply_to}
        if d.media:
            self.out["message"] = _("redraft_media", n=d.media)


class Web:
    """The state behind the handler: the core (as a View), the key, a version for long
    polls."""

    def __init__(self, core, key):
        self.core = core if isinstance(core, View) else View(core)
        self.key = key
        self.cmds = Commands(self.core)
        self.models = {}  # lane -> LaneModel (common/lane.py)
        self._saver = None  # common/images.Cache for "Save", made when first asked
        try:  # attachments of posts never sent last time: gone
            d = self.core.paths.data_dir / "web-uploads"
            for f in d.iterdir() if d.is_dir() else ():
                f.unlink(missing_ok=True)
        except (OSError, AttributeError):  # (a core without a profile folder: tests)
            pass
        self.version = 0
        self.changed = threading.Condition()
        self.links = {}  # one-time login token -> good until (time.monotonic)
        self._links_lock = threading.Lock()
        self.theme = ""  # one tried from the page's menu: until fedtail stops (ui.theme stays)
        # the theme's sounds: the page plays them (frontends/soundpack.py)
        self.sound_seq = 0
        self.sound_log = collections.deque(maxlen=8)  # (seq, event)
        # desktop notifications, shown by the browser (notifytext: the windows' words)
        self.note_seq = 0
        self.note_log = collections.deque(maxlen=20)  # (seq, {title, body, lane, thread})
        self.instance = None  # this profile's single-instance lock (web/__init__.run)
        self.auth_failed = None  # the server refused the token: what the page says
        self._listen(self.core)

    def _listen(self, view):
        """The core's news, to the page."""
        # thread_grew: replies from other servers came into a thread — an open one grows
        # events came, were seen or answered: every lane that takes them is drawn anew
        for event in ("lanes_updated", "read_changed", "status_updated", "status_deleted",
                      "lists_changed", "thread_grew", "activity_updated", "activity_seen",
                      "requests_updated"):
            view.on(event, lambda _n, _p: self.bump())
        view.on("thread_grew", lambda _n, _p: self._thread_news())
        view.on("status_updated", lambda _n, _p: self._thread_news())
        view.on("sound", lambda _n, p: self.chime(p))
        view.on("notify", lambda _n, p: self.notified(p))
        view.on("auth_failed", lambda _n, _p: self.auth_lost())
        view.on("poll_state", lambda _n, _p: self.poll_changed())

    def _thread_news(self):
        """A thread grew or a post changed: an open thread is drawn anew (thread_seq —
        the phone asks it, not to fetch the thread at every change of the lanes)."""
        self.thread_seq = getattr(self, "thread_seq", 0) + 1

    def poll_changed(self):
        """A round began or ended: the page's "⟳ updating the lanes…" / "updated at"
        changes — the long wait answers, without reloading anything."""
        with self.changed:
            self.poll_seq = getattr(self, "poll_seq", 0) + 1
            self.changed.notify_all()

    def auth_lost(self):
        """The server no longer takes the token: the page says so (the windows' words)
        and opens Accounts, where "log in again" is."""
        with self.changed:
            self.auth_failed = {"title": _("auth_failed_title"), "text": _("auth_failed")}
        self.bump()

    def switch_profile(self, name):
        """Another account's profile in this same page (Accounts → Open, or after a
        login): its core made, connected and polling, then put in place of this one,
        which is shut down. The page keeps its key and cookie — it only reloads. A
        profile open in its own window stays there (profile_busy): two processes on one
        profile's database would fight over it."""
        from ...core import config, paths
        from ...core.app import Core
        from ...core.instance import SingleInstance
        old_view = self.core
        old = getattr(old_view, "_core", old_view)
        old = getattr(old, "primary", old)
        if name == old.paths.profile:
            return
        where = paths.resolve(name)
        where.ensure()
        lock = SingleInstance(where.socket_file)
        if lock.poke_existing():
            raise ValueError(_("profile_busy", profile=name))
        cfg, _warn = config.load(where.config_file)
        new = Core(cfg, where, api_class=old.api_class)
        if not new.logged_in:
            new.shutdown()
            raise ValueError(_("cli_login_first"))
        try:
            new.connect().result(timeout=60)
        except Exception:
            new.shutdown()
            raise
        lock.listen(lambda _m: None)
        view = View(new)
        self._listen(view)
        self.core, self.cmds, self.models, self._saver = view, Commands(view), {}, None
        held, self.instance = self.instance, lock
        new.start_polling()
        log.info("web: profile %s -> %s", old.paths.profile, name)
        try:
            old_view.shutdown()
        finally:
            if held is not None:
                held.close()
        self.bump()

    def login_link(self, base):
        """A link that logs a browser in once, within LINK_SECONDS: what the history,
        a synced browser or a terminal's scrollback keep is dead by then. The key
        itself never goes into a link (it stays in the cookie)."""
        token = secrets.token_urlsafe(18)
        with self._links_lock:
            now = time.monotonic()
            self.links = {t: until for t, until in self.links.items() if until > now}
            self.links[token] = now + LINK_SECONDS
        return f"{base}/?t={token}"

    def use_link(self, token):
        with self._links_lock:
            until = self.links.pop(token, 0)
        return until > time.monotonic()

    def scheme(self):
        from .. import soundpack
        return soundpack.scheme(self.core.cfg["ui"].get("theme", "system"), self.core.cfg)

    def chime(self, event):
        with self.changed:
            self.sound_seq += 1
            self.sound_log.append((self.sound_seq, str(event)))
        self.bump()

    def notified(self, items):
        from .. import notifytext
        cfg = self.core.cfg["notify"]
        if not cfg.get("enabled", True):
            return
        try:
            notes = notifytext.build(self.core.model_of(list(items)), cfg["privacy"],
                                     self.core.lane_title, cfg.get("max_lines", 3))
        except Exception:  # noqa: BLE001 — a note is never worth a failed poll
            log.exception("web notify")
            return
        with self.changed:
            for n in notes:
                self.note_seq += 1
                self.note_log.append((self.note_seq, {"title": n.title, "body": n.body,
                                                      "lane": n.lane, "thread": n.thread}))
        self.bump()

    def notes_since(self, seq):
        """The notes newer than seq (none for a page that just opened), and the newest."""
        with self.changed:
            got = [n for k, n in self.note_log if k > seq] if seq >= 0 else []
            return got[-5:], self.note_seq

    def sounds_since(self, seq):
        """What the page should play: [{event, kind}] newer than seq ("file" — fetch
        /sound/<event>; "bell" — beep), and the newest seq. A page that opens hears
        nothing of what came before it."""
        with self.changed:
            last = self.sound_seq
            got = [e for n, e in self.sound_log if n > seq] if seq >= 0 else []
        out = []
        sch = self.scheme()
        for e in got[-1:]:  # a page that slept: one sound, the newest, not a medley
            snd = sch.find(e)
            if snd is None:
                continue
            kind = "bell" if snd.kind == "bell" else "file"
            if kind == "file" and not (snd.file if snd.kind == "desktop" else snd.value):
                continue
            out.append({"event": e, "kind": kind})
        return out, last

    def sound_file(self, event):
        """The bytes of an event's sound (a browser can't play the desktop's sound
        theme: fedtail's own quiet set stands in), or None."""
        snd = self.scheme().find(str(event))
        if snd is None or snd.kind == "bell":
            return None
        path = snd.file if snd.kind == "desktop" else snd.value
        try:
            return Path(path).read_bytes() if path else None
        except OSError:
            return None

    def wait_answer(self, since, sound_since, note_since=-1, poll_since=-1):
        v = self.wait(since, poll_since=poll_since)
        sounds, last = self.sounds_since(sound_since)
        notes, last_note = self.notes_since(note_since)
        from ..common import sidebar
        out = {"v": v, "s": last, "sounds": sounds, "n": last_note, "notes": notes,
               "p": getattr(self, "poll_seq", 0), "status": sidebar.status_words(self.core),
               "busy": sidebar.polling(self.core)}
        if self.auth_failed:
            out["auth_failed"] = self.auth_failed
        return out

    def bump(self):
        with self.changed:
            self.version += 1
            self.changed.notify_all()

    def wait(self, since, timeout=WAIT_SECONDS, poll_since=None):
        """Until the lanes changed (or a round began or ended, when poll_since is the
        page's last one), or the time is up → the version now."""
        with self.changed:
            self.changed.wait_for(
                lambda: self.version != since or poll_since is not None and
                poll_since >= 0 and getattr(self, "poll_seq", 0) != poll_since, timeout)
            return self.version

    def _posts(self, entries, parents=True, items=None):
        core = self.core
        es = [e for e in entries]
        unread = core.unread(es)
        short = core.short_ids(es)
        par = core.parents(es) if parents else {}
        return [post_json(core, e, short.get(real(e).id), e.id in unread, par.get(e.id),
                          item_id=items[i] if items else None)
                for i, e in enumerate(es)]

    # ---- API ---------------------------------------------------------------------
    def me(self):
        c = self.core.cfg
        if not self.core.logged_in or self.core.me is None and not self.core.auth:
            # not logged in yet: the page shows the login place and nothing else
            return {"login": self.core.paths.profile, "version": __version__,
                    "lang": i18n.current_language(), "homepage": version.HOMEPAGE,
                    "words": {k: _(k) for k in WORDS}}
        if self.core.me is None:  # just logged in from the page: connected, then polling
            self.core.connect().result(timeout=120)
        self.core.start_polling()
        me = self.core.me
        return {"me": account_json(me), "handle": me.handle if me else "",
                "version": __version__, "server": (self.core.auth or {}).get("server"),
                "mark_read": c["read"]["mark_read"], "order": c["feed"]["order"],
                "start_at": c["feed"]["start_at"], "expand_cw": config.expand_cw(c),
                "older_ahead": bool(c["feed"].get("older_ahead")),
                # the posts' column, as the windows': ui.max_width (0: the whole width),
                # and ↔ — the same remembered state as theirs
                "max_width": int(c["ui"].get("max_width") or 0),
                "full_width": bool(self.core.get_state("full_width")),
                "highlight": bool(c["ui"].get("additional_highlight", True)),
                "visibility": self.core.default_visibility(),
                # when a picture that didn't come is asked again: the windows' times
                "picture_later": list(_picture_later()),
                # the reading rule's numbers, as the windows read them (common/lane)
                "dwell_ms": int(c["read"].get("dwell_ms", 350)),
                "message_percent": int(c["ui"].get("message_percent", 100)),
                "unfocused_seconds": float(c["read"].get("unfocused_seconds", 5)),
                "sensitive_media": config.sensitive_media(c),
                "quote_prefix": c["post"].get("quote_prefix", "> "),
                "homepage": version.HOMEPAGE, "help_url": self.help_url(),
                "lang": i18n.current_language(),
                "sound": {"volume": c["sound"]["volume"],
                          "when_focused": c["sound"]["when_focused"]},
                "notify": {"when_focused": c["notify"]["when_focused"]},
                "editor": self.editor_facts(),
                "merged": self.merged(),
                "words": {k: _(k) for k in WORDS}}

    # ---- the theme: the windows' colours and font, as the page's own --------------------
    # CSS variable <- the theme's colour (the first one set, "auto" passed over)
    THEME_VARS = (("--bg", ("view", "window")), ("--card", ("card",)),
                  ("--text", ("text",)), ("--muted", ("muted",)),
                  ("--line", ("card_border", "header_border")),
                  ("--accent", ("accent", "link")), ("--accent-text", ("on_accent",)),
                  ("--unread", ("card_border_unread", "accent")), ("--ctx", ("ctx",)),
                  ("--danger", ("hot",)), ("--on-hot", ("on_hot",)),
                  ("--quiet", ("quiet",)), ("--on-quiet", ("on_quiet",)),
                  ("--button-border", ("button_border",)))

    def theme_name(self):
        return self.theme or self.core.cfg["ui"].get("theme") or "system"

    def theme_colors(self, name=None):
        """The theme's colours by the page's names (THEME_VARS without "--"), whether it
        is a light one, its font family: ({}, True, "") for system (the browser's or the
        phone's own light or dark) or a theme that won't load. The phone's app paints
        itself with these too."""
        from .. import themefile
        name = name or self.theme_name()
        try:
            theme, _warnings = themefile.load(name)
        except (themefile.ThemeError, OSError) as e:
            log.info("web theme %s: %s", name, e)
            return {}, True, ""
        colors = theme.get("colors") or {}
        out = {}
        for var, keys in self.THEME_VARS:
            got = next((colors[k] for k in keys
                        if isinstance(colors.get(k), str) and colors[k] != "auto"), "")
            if got and re.fullmatch(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?|rgba?\([\d.,\s%]+\)",
                                    got):
                out[var[2:]] = got
        if "bg" not in out or "text" not in out:
            out = {}  # the page and its text follow the system: the browser's own then
        family = (theme.get("font") or {}).get("family") or ""
        family = family if re.fullmatch(r"[\w\s,\"'-]*", family) else ""
        return out, _light(colors), family

    def theme_css(self):
        """The page's colours from the theme (themes/*.toml, the same files the windows
        read): "" for system (the browser's light or dark) or a theme that won't load."""
        colors, light, family = self.theme_colors()
        lines = [f"  --{k}: {v};" for k, v in colors.items()]
        if not lines and not family:
            return ""
        css = ":root, :root:root {\n" + "\n".join(lines) + "\n  --shadow: none;\n}\n" \
            if lines else ""
        if lines:  # the theme's own colours: light or dark is the theme's, not the browser's
            css += ":root { color-scheme: only light; }\n" if light else \
                ":root { color-scheme: only dark; }\n"
        if family:
            css += f"body {{ font-family: {family}; }}\n"
        return css

    def merged(self):
        """All accounts in one window: ui.merge, or switched on from a menu (state)."""
        primary = getattr(self.core, "primary", self.core)
        return bool(self.core.cfg["ui"].get("merge") or primary.get_state("merge"))

    def toggle_merge(self):
        """≡ → All accounts in one window: from the next start, as in the windows."""
        primary = getattr(self.core, "primary", self.core)
        primary.set_state("merge", [] if self.merged() else ["all"])
        on = self.merged()
        return {"merged": on, "message": ("☑ " if on else "☐ ") + _("accounts_merge") +
                " — " + _("settings_restart_tip")}

    # ---- Web Push: the browser subscribes at my server itself (through fedtail) --------
    def push_state(self):
        """What the page needs to subscribe: the server's key ("" — no Web Push there)
        and the subscription the server keeps for this token, if any."""
        key = self.core.vapid_key().result()
        sub = self.core.push_subscription().result() if key else None
        return {"key": key, "endpoint": (sub or {}).get("endpoint", ""),
                "words": {k: _(k) for k in ("web_push_on", "web_push_off", "web_push_none",
                                            "web_push_insecure", "web_push_turn_off",
                                            "web_push", "web_push_tip")}}

    def push_on(self, body):
        """The browser's subscription, to my server: it sends there from now on."""
        endpoint = str(body.get("endpoint") or "")
        keys = body.get("keys") if isinstance(body.get("keys"), dict) else {}
        if not endpoint.startswith("https://") or not keys.get("p256dh") or \
                not keys.get("auth"):
            raise ValueError("subscription")
        self.core.push_subscribe(endpoint, str(keys["p256dh"]), str(keys["auth"])).result()
        return {"message": _("web_push_on")}

    def push_off(self):
        self.core.push_unsubscribe().result()
        return {"message": _("web_push_off")}

    def themes(self):
        """≡ → Try a theme: the names, which one is on, which the config says."""
        from .. import themefile
        configured = self.core.cfg["ui"].get("theme") or "system"
        current = self.theme_name()
        names = themefile.for_layout(self.core.cfg, keep=(configured, current))
        return {"current": current, "configured": configured,
                "themes": [{"name": n, "label": n + ("  · " + _("theme_in_config")
                                                     if n == configured else ""),
                            "on": n == current} for n in names],
                "title": _("try_theme"), "tip": _("try_theme_tip")}

    def try_theme(self, name):
        """Another theme for the page, until fedtail stops; the config stays."""
        from .. import themefile
        name = str(name or "")
        if name not in themefile.available():
            raise ValueError(name)
        self.theme = name
        configured = self.core.cfg["ui"].get("theme") or "system"
        return {"message": _("theme_tried", name=name, configured=configured)}

    def editor_facts(self):
        """What the editor needs: the server's limits, the languages to pick from (the
        windows': common/compose.py), the poll's lengths."""
        from ..common import compose as cc
        caps = self.core.caps
        accounts, _first = self.core.post_accounts(None)
        added = self.core.get_state("languages_added", []) or []
        langs = [["", _("lang_default")]] + [[code, cc.language_label(code)]
                                             for code in cc.languages(self.core.cfg, added)]
        # "Another language…" last, as in the windows (the page asks for the code)
        langs.append([cc.OTHER_LANG, _("lang_other")])
        return {"limit": int(getattr(caps, "max_characters", 500) or 500),
                "max_media": int(getattr(caps, "max_media", 4) or 4),
                "max_options": int(getattr(caps, "max_poll_options", 4) or 4),
                "languages": langs, "language": self.core.cfg["post"].get("language", ""),
                # all accounts in one window: whom a post may go from, whole @name@server
                "accounts": [[k, _("post_from", acct=h)] for k, h in accounts]
                if len(accounts) > 1 else [],
                "poll_lengths": [[secs, _(key)] for secs, key in cc.POLL_TIMES],
                "preview": bool(self.core.cfg["post"].get("preview", True)),
                # spell checking: the browser's own (post.spellcheck), in the post's
                # language — the windows check with the system's dictionaries
                "spellcheck": bool(self.core.cfg["post"].get("spellcheck", True)),
                # the formatting buttons (post.format_bar): [] — none
                "format_bar": self.format_bar(),
                # where they stand: "left", "right", "top", "bottom" ("" — none)
                "format_place": self._format_place()}

    def _format_place(self):
        from ..common import markup
        return markup.place(self.core.cfg, self.core.markdown)

    def format_bar(self):
        """The editor's formatting buttons (common/markup.py) — [{name, face, tip, keys}],
        [] when post.format_bar hides them; the phone draws the same."""
        from ..common import markup
        if not markup.shown(self.core.cfg, self.core.markdown):
            return []
        return [{"name": f.name, "face": f.face, "tip": markup.tip(f, _(f.tip)),
                 "keys": f.keys} for f in markup.FORMATS]

    def format_text(self, body):
        """One button of the formatting row on the editor's text: {name, text, start, end}
        → {text, start, end}. Positions are the browser's and Kotlin's (UTF-16); the work
        is common/markup.py's, the windows' own."""
        from ..common import markup
        text = str(body.get("text") or "")
        s = markup.from_utf16(text, int(body.get("start") or 0))
        e = markup.from_utf16(text, int(body.get("end") or 0))
        got = markup.apply(str(body.get("name") or ""), text, s, e)
        return {"text": got.text, "start": markup.utf16(got.text, got.start),
                "end": markup.utf16(got.text, got.end)}

    # ---- attachments: the page sends the file, the post names it by its token ----------
    def uploads_dir(self):
        d = self.core.paths.data_dir / "web-uploads"
        d.mkdir(mode=0o700, parents=True, exist_ok=True)
        return d

    def upload(self, data, name):
        """A file for a post to come: kept in the profile's folder (0600) until the post
        goes or the next start; its token is all the page gets back."""
        if not data:
            raise ValueError("empty")
        ext = Path(name or "").suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,6}", ext or ""):
            ext = ""
        token = secrets.token_urlsafe(12)
        path = self.uploads_dir() / (token + ext)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return {"token": token + ext, "size": len(data)}

    def upload_path(self, token):
        if not isinstance(token, str) or not _UPLOAD.fullmatch(token):
            raise ValueError("bad attachment")
        path = self.uploads_dir() / token
        if not path.is_file():
            raise ValueError("attachment gone")
        return path

    @staticmethod
    def help_url():
        """The help as GitHub shows it, in the interface's language: the page has no
        Markdown of its own (the Qt window shows the same pages offline)."""
        from ..helpdocs import language
        return f"{version.HOMEPAGE}/blob/main/fedtail/data/help/{language()}/index.md"

    def lanes(self):
        """The sidebar as the windows have it (common/sidebar.py): its sections with
        their titles and folded or not (one state for every window), each lane's count
        and the tip the windows give it."""
        from ..common import sidebar
        core = self.core
        folded = sidebar.folded(core)
        out = []
        for group, names in sidebar.groups(core, core.cfg):
            title = None
            if group:
                title = sidebar.group_title(group)
            for i, name in enumerate(names):
                label, n = sidebar.lane_label(core, name, 60)
                tip = _("tip_" + name)
                fresh = sidebar.fresh(core, name) if n else 0
                out.append({"name": name, "title": label, "unread": n,
                            "badge": sidebar.badge_kind(core, name),
                            "fresh": min(fresh, n), "fresh_words": sidebar.fresh_words(
                                min(fresh, n)),
                            "tip": "" if tip == "tip_" + name else tip,
                            "group": title if i == 0 else None, "section": group,
                            "folded": bool(group) and group in folded})
        first = sidebar.start_lane(core, [x["name"] for x in out])  # None: the curtain
        for x in out:
            x["start"] = x["name"] == first
        return out

    def slow(self):
        """How fresh the lanes are and slow mode, for the bar: {"text": "updated at
        14:32 · slow · next at 14:45"}; "" before the first round."""
        from ..common import sidebar
        return {"text": sidebar.status_words(self.core)}

    def columns(self):
        """Lanes side by side, as the windows' ❯: which ones (as left last time, else
        ui.columns, else Home, Replies, Activity — common/columns.py), how wide, and
        whether the page starts in columns (ui.layout)."""
        from ..common import columns, sidebar
        known = [n for _g, names in sidebar.groups(self.core, self.core.cfg) for n in names]
        # the View's lists are the model's (title, id as attributes): Qt's own way
        titles = {x.title: "list:" + str(x.id) for x in self.core.lists or ()}
        ui = self.core.cfg["ui"]
        return {"names": columns.start_names(self.core.cfg, self.core.get_state("columns"),
                                             known, titles, view=self.core),
                "layout": ui.get("layout", "single"),
                "open_columns": bool(ui.get("open_columns")),
                "width": max(280, int(ui.get("column_width") or 460))}

    def set_columns(self, names, on):
        """The page's columns changed (added, moved, closed) or went (❯ off): kept for
        every window, and every column's lane is on screen for notifications."""
        if not on:
            self.core.set_active_lanes([])
            return {"ok": True}
        if not isinstance(names, list) or not names:
            raise ValueError("names")
        got = []
        for n in names[:40]:
            n = self._lane_name(n)
            if n not in got:
                got.append(n)
        self.core.set_state("columns", got)
        self.core.set_active_lanes(got)
        return {"names": got}

    def fold(self, group):
        """A section of the sidebar folded or unfolded (kept for every window)."""
        from ..common import sidebar
        if not isinstance(group, str) or not group:
            raise ValueError("group")
        return {"folded": sidebar.fold(self.core, group)}

    def _lane_name(self, name):
        from ...core.lanes import canonical
        name = canonical(str(name or ""))  # an old name ("comments") still finds its lane
        if name not in self.core.lane_by_name:
            raise KeyError(name)
        return name

    def model(self, name):
        """The lane's choices and cards (common/lane.py LaneModel, as the windows')."""
        from ..common.lane import LaneModel
        m = self.models.get(name)
        if m is None:
            m = self.models[name] = LaneModel(self.core, name)
        return m

    def lane(self, name, keep=False):
        """The cards of a lane: the windows' (LaneModel: "new below", All | Posts | New,
        conversations, the media funnel), with each card's words. keep: the page is
        standing in the lane already (the divider stays where it was)."""
        from ..common.lane import MEDIA_KINDS, SEPARATOR
        name = self._lane_name(name)
        core = self.core
        title = core.lane_title(name) or _("lane_" + name)
        m = self.model(name)
        built = m.build(bool(keep))
        specs = [sp for sp in built.specs]
        # where reading starts (LaneModel.start: feed.start_at, "new below", the order) —
        # the card's id, or None for the newest end: the page and the phone stand there,
        # they don't count it again
        at, where = m.start(specs)
        if at == SEPARATOR:  # "new below": the first card under it
            line = next(i for i, x in enumerate(specs) if x.key == SEPARATOR)
            at = next((sp.key for sp in specs[line + 1:] if sp.entry is not None), None)
        start = next((sp.entry.id for sp in specs if sp.key == at and sp.entry is not None),
                     None)
        if m.newest_first:  # the page turns newest-first lanes round itself
            specs.reverse()
        posts, divider, pending = [], None, None
        events, waiting = [], []  # likes, follows… among the posts: before which one
        dismiss_one = bool(core.can_dismiss_one()) if hasattr(core, "can_dismiss_one") \
            else True
        entries = [sp.entry for sp in specs if sp.entry is not None]
        short = core.short_ids(entries)
        unread = core.unread(entries)
        for sp in specs:
            if sp.key == SEPARATOR:  # "new below": before the card that follows it
                pending = sp.extra.get("separator", "")
                continue
            if sp.extra.get("event"):  # an event's row: its parts, every action a link
                if pending is not None:
                    divider, pending = {"before": sp.key, "text": pending}, None
                waiting.append({"key": sp.key, "event": event_json(sp, dismiss_one)})
                continue
            e = sp.entry
            events += [dict(x, before=e.id) for x in waiting]
            waiting = []
            if pending is not None:
                divider, pending = {"before": e.id, "text": pending}, None
            posts.append(post_json(core, e, short.get(real(e).id), e.id in unread,
                                   sp.parent if sp.parent is not None else None,
                                   item_id=sp.key, spec=sp))
        events += [dict(x, before=None) for x in waiting]  # after the last post
        lane = core.lane_by_name[name]
        return {"name": name, "title": title, "posts": posts, "info": built.info,
                "waiting": bool(core.lane_waiting(name)) and not posts,  # browse: asked
                "divider": divider, "events": events, "start": start,
                "start_where": where,
                "older": bool(lane.source) and not lane.lazy, "empty_browse": built.empty,
                "filters": [[f, *m.filter_words(f)] for f in m.filters]
                if len(m.filters) > 1 else [],
                "filter": m.current_filter(),
                # a lane of events only: "Clear" (every notification, on the server too)
                "clear": {"label": _("activity_clear"), "tip": _("activity_clear_tip")}
                if m.events_only() and getattr(core, "supports", lambda _f: True)("dismiss")
                else None,
                "conversations": {"offered": m.conversations_offered(), "on": m.conversations(),
                                  "words": [_("view_feed"), _("conv_mode")],
                                  "tips": [_("view_feed_tip"), _("conv_mode_tip")]},
                "media": {"active": m.media.active(), "label": _("media_filter"),
                          "tip": _("media_filter_tip"), "all": _("filter_all"),
                          "kinds": [[k, _("filter_" + k), k in m.media.wanted]
                                    for k in MEDIA_KINDS] +
                                   [["boosts", _("filter_boosts"), m.media.boosts]]}}

    def lane_set(self, body):
        """A lane's choice from its header: filter, conversations, the media funnel."""
        from ..common.lane import MEDIA_KINDS
        name = self._lane_name(body.get("name"))
        m = self.model(name)
        if body.get("filter") in m.filters:
            m.set_filter(body["filter"])
        if isinstance(body.get("conversations"), bool) and m.conversations_offered():
            m.set_conversations(body["conversations"])
        kind = body.get("media")
        if kind == "reset":
            m.media.reset()
        elif kind == "boosts":
            m.media.boosts = bool(body.get("on"))
        elif kind in MEDIA_KINDS:
            m.media.toggle(kind, bool(body.get("on")))
        return {"ok": True}

    def read(self, ids, lane=None):
        """Posts seen: marked read — a conversation card's whole conversation with it. An
        event's row seen ("event:<id>") goes to the lane model that drew it
        (LaneModel.read: the events seen up to it, one mark for every lane). lane: "mark
        all read" over that lane — its events seen too, every one of them."""
        events = [i for i in ids if str(i).startswith("event:")]
        ids = [i for i in ids if not str(i).startswith("event:")]
        members = {}
        for m in self.models.values():
            members.update(m.conv_members)
            mine = [k for k in events if k in m.event_sorts]
            if mine:
                m.read(mine)  # events only: what it says of posts is decided here
        out = [x for i in ids for x in members.get(i, [i])]
        if out or not events:
            self.core.mark_read(out[:2000])
        if lane:
            name = self._lane_name(lane)
            if getattr(self.core.lane_by_name.get(name), "events", False):
                self.core.mark_activity_seen()
        return {"ok": True}

    def lane_clear(self, name, confirmed=False):
        """"Clear" over a lane of events only: every notification gone, here and on the
        server (asked first: {confirm})."""
        name = self._lane_name(name)
        if not self.model(name).events_only():
            raise ValueError(name)
        if not confirmed:
            return {"confirm": _("activity_clear_q")}
        self.core.clear_activity().result(timeout=60)
        return {"refresh": True}

    def find(self, name, query):
        """Ctrl+F: the posts of a lane that have every word (common/find.py's rule:
        text, warning, alt texts, name and @handle, #id), in the lane's order."""
        from ...model.text import haystack, matches
        name = self._lane_name(name)
        if not query.strip():
            return {"ids": [], "text": ""}
        es = [e for _i, e in self.core.entries(name)]
        short = self.core.short_ids(es)
        ids = [e.id for e in es if matches(query, haystack(e, short.get(real(e).id)))]
        from ..common.find import count_text
        text, _none = count_text(query, 0 if ids else -1, len(ids))
        return {"ids": ids, "text": text}

    def find_deeper(self, name, query):
        """"Deeper": everything stored for the lane, not only what it shows; the lane
        grows down to an older match (core.deep_find, as the windows' find bar)."""
        name = self._lane_name(name)
        if not query.strip():
            return {"more": False, "total": 0, "text": ""}
        got = self.core.deep_find(name, query).result()
        text = "" if got["more"] else (_("find_archive_none") if not got["total"] else "")
        return {"more": bool(got["more"]), "total": int(got["total"]), "text": text}

    def find_everywhere(self, query):
        """"In every lane": what's stored, lane by lane in the sidebar's order — each
        match with its lane's title (core.find_everywhere)."""
        from ..common.find import count_text
        if not query.strip():
            return {"hits": [], "text": ""}
        core = self.core
        hits = [{"lane": h["lane"], "item": h["item"], "id": h["status_id"],
                 "index": h["index"], "title": core.lane_title(h["lane"])
                 or _("lane_" + h["lane"])}
                for h in core.find_everywhere(query).result()
                if h["lane"] in core.lane_by_name]
        text, _none = count_text(query, 0 if hits else -1, len(hits),
                                 hits[0]["title"] if hits else None, everywhere=True)
        return {"hits": hits, "text": text}

    def reveal(self, name, index):
        """The lane loaded down to a match found further back than it shows."""
        name = self._lane_name(name)
        return {"grew": bool(self.core.reveal_in_lane(name, _int(index, 0)))}

    def older(self, name, ahead=False):
        """Older posts of a lane from the server (the "More" at its end); ahead: its end
        came in sight — core.older_ahead decides (reading.older_ahead), "asked": False
        when it didn't ask."""
        name = self._lane_name(name)
        if ahead:
            fut = self.core.older_ahead(name)
            return {"n": fut.result() or 0, "asked": True} if fut is not None else \
                {"n": None, "asked": False}
        return {"n": self.core.load_older(name).result() or 0}

    def curtain(self):
        """The curtain's words (every lane closed) and the lane Enter opens there."""
        from ..common import sidebar
        names = [n for _g, ns in sidebar.groups(self.core, self.core.cfg) for n in ns]
        title, info, hint = sidebar.curtain(self.core, names)
        return {"title": title, "info": info, "hint": hint,
                "last": sidebar.start_lane(self.core, names, closable=False)}

    def on_screen(self, ids):
        """The posts on the page's screen: their numbers asked again in a while."""
        self.core.on_screen([str(i) for i in (ids or [])][:200])
        return {"ok": True}

    def stood(self, lane, key, end=False):
        """The last card seen whole on the page's screen, the scroll standing (LaneModel.stood):
        where the lane opens next time, in every interface; end — at the lane's end."""
        if lane and (key or end):
            self.model(self._lane_name(str(lane))).stood(str(key or ""), end)
        return {"ok": True}

    def full_width(self, on):
        """↔: the posts across the whole width or in a column — remembered as the
        windows remember it (the state "full_width"), for every interface."""
        self.core.set_state("full_width", bool(on))
        return {"ok": True, "full_width": bool(on)}

    def activate(self, name):
        """The lane on screen (for notifications and the next start): a POST."""
        name = self._lane_name(name)
        self.core.set_active_lane(name)
        self.core.set_state("lane", name)
        return {"ok": True}

    def thread(self, sid, at="post"):
        """The thread of `sid`; at: where it stands (common/links.py THREAD_AT) — the
        page scrolls to "focus"."""
        core = self.core
        sid = one_id(sid)
        items = core.thread(sid).result()
        posts = [n.post for n in items]
        short = core.short_ids(posts)
        unread = core.unread(posts)
        out = [post_json(core, n.post, short.get(n.post.id), n.post.id in unread,
                         number=n.number, depth=n.depth) for n in items]
        for p in out:  # the post the thread was opened from: "you came from here"
            if p["sid"] == sid or p["id"] == sid:
                p["came_from"] = _("came_from")
        from ..common.lane import thread_read_on_open
        return {"focus": core.thread_focus(sid, items, at if at in ("post", "first_unread")
                                           else "post"),
                "posts": out, "head": self.thread_head(posts, short),
                # read as it opens, unless by hand: decided once (common/lane.py)
                "read_on_open": thread_read_on_open(core.cfg, unread)}

    def thread_head(self, posts, short):
        """The head the windows put over a thread (qt/feed.py ThreadWidget,
        gtk/threadhead.py): its first words, how many answers, #id, Follow (and why it
        reaches me without), every warning opened or closed at once."""
        if not posts:
            return None
        core, root = self.core, posts[0]
        on = bool(core.subscribed(root))
        sid = short.get(root.id)
        info = _("thread_info", n=len(posts) - 1) + (f" · #{sid}" if sid else "")
        via = ""
        if not on:  # not followed, yet the comments come: the server's Home says why
            try:
                followed = core.followed_among([p.author for p in posts]).result()
            except Exception:  # noqa: BLE001 — a head without the reason, as the windows'
                followed = []
            if followed:
                names = ", ".join("@" + a.handle.split("@")[0] for a in followed[:3])
                if len(followed) > 3:
                    names += " " + _("and_more", n=len(followed) - 3)
                via = _("thread_via_home", names=names)
        return {"sid": root.id, "title": snippet(root, 60) or "@" + root.author.handle,
                "info": info, "via": via, "via_tip": _("thread_via_home_tip") if via else "",
                "subscribed": on, "sub": _("subscribed") if on else _("sub_thread"),
                "sub_tip": _("sub_tip"),
                "cw": any(p.warning for p in posts),
                "cw_show": _("cw_all_show"), "cw_hide": _("cw_all_hide"),
                "cw_tip": _("cw_all_tip"),
                "progress": bool(core.cfg["feed"].get("thread_progress"))}

    def account(self, acc_id, show=None):
        """A profile; show: which of their posts (common/timed.py: posts, all, media),
        feed.profile_show when not said."""
        core = self.core
        acc_id = one_id(acc_id)
        if show not in dict(timed.PROFILE_SHOWS):
            show = timed.profile_show(core.cfg)
        acc = core.account(acc_id).result()
        me = core.me
        try:
            rel = core.relationship(acc_id).result() if not me or acc_id != me.id else None
        except Exception:  # noqa: BLE001 — the profile shows without it
            rel = None
        page = core.account_posts(acc_id, show=show).result()
        own = bool(me and acc and acc.id == me.id)
        extra = self._profile_extras(acc, own, show) if acc else {}
        pinned = extra.pop("pinned", [])
        top = {e.id for e in pinned}
        info = account_json(acc)
        info.update(note=with_emojis(web_clean(acc.note), acc.emojis) if acc else "",
                    header=_pic(acc.header_static) if acc else "",
                    counts=" · ".join((_("posts_n", n=acc.posts),
                                       _("followers_n", n=acc.followers),
                                       _("following_n", n=acc.following))) if acc else "",
                    fields=[{"name": f.name, "value": web_clean(f.value),
                             "verified": f.verified is not None}
                            for f in (acc.fields if acc else ())],
                    own=bool(me and acc and acc.id == me.id))
        from ..common import profile as prof
        acts = [{"key": a.key, "label": a.label, "tip": a.tip, "primary": a.primary}
                for a in prof.actions(acc, rel, own, core.cfg, core.supports, lists=True,
                                      collections=True, details=True)
                if a.key in WEB_PROFILE_ACTS] if acc else []
        since = rel is not None and rel.following and core.followed_since(acc_id, rel)
        return {"account": info,
                "relation": {"following": bool(rel and rel.following),
                             "followed_by": bool(rel and rel.followed_by),
                             "requested": bool(rel and rel.requested)},
                "meta": prof.meta(acc, rel, self._date, since or None,
                                  extra.get("software") or "")[1:] if acc else [],
                "note_line": prof.note_line(rel, own),
                "actions": acts,
                "shows": [{"key": k, "label": label, "on": k == show}
                          for k, label in timed.profile_shows()],
                "show_tip": _("profile_show_tip"),
                "posts": [dict(p, pinned=True) for p in self._posts(pinned)] +
                self._posts([e for e in page if e.id not in top]),
                "featured": extra.get("featured") or [],
                "familiar": extra.get("familiar") or "",
                "moved": extra.get("moved"),
                # the next page: my server's, then (remote_profiles) theirs, further back
                "older": self._older_offer(acc, page),
                "max_id": page[-1].id if page else ""}

    def _profile_extras(self, acc, own, show):
        """What the windows add to a profile, asked at once: the pinned posts on top
        (feed.profile_pinned), what they put forward (feed.profile_featured), whom of
        mine they follow, their server's software (feed.server_info), a move."""
        from urllib.parse import urlparse
        core, cfg = self.core, self.core.cfg["feed"]
        futs = {}
        if cfg.get("profile_pinned", True) and show != "media":
            futs["pinned"] = core.pinned(acc.id)
        if cfg.get("profile_featured", True):
            futs["featured"] = core.featured(acc.id)
        host = urlparse(acc.url or acc.uri or "").hostname or ""
        if host and not own:
            futs["software"] = core.server_software(host)
        if not own and core.supports("familiar"):
            futs["familiar"] = core.familiar(acc.id)
        got = {}
        for key, fut in futs.items():
            try:
                got[key] = fut.result(timeout=20)
            except Exception as e:  # noqa: BLE001 — the profile shows without it
                log.debug("profile %s: %s", key, e)
        out = {"pinned": list(got.get("pinned") or []), "software": got.get("software") or ""}
        feat = got.get("featured") or {}
        lines = []
        tags = ["#" + t.name + (f" ({int(t.posts)})" if t.posts else "")
                for t in feat.get("tags") or [] if t.name]
        people = [a for a in feat.get("people") or [] if a.id]
        if tags:
            lines.append({"title": _("featured_tags"), "text": ", ".join(tags),
                          "tags": [t.name for t in feat["tags"] if t.name]})
        if people:
            lines.append({"title": _("featured_people"),
                          "people": [account_json(a) for a in people],
                          "text": ", ".join("@" + a.handle for a in people)})
        out["featured"] = lines
        known = [a for a in got.get("familiar") or [] if a.id]
        if known:
            more = len(known) - 5
            out["familiar"] = _("familiar", who=", ".join("@" + a.handle for a in known[:5]) +
                                (" " + _("act_more", n=more) if more > 0 else ""))
        if acc.moved and cfg.get("show_moved", True):
            from html import unescape
            words = unescape(re.sub(r"<[^>]+>", "", _("moved_to", acct="@" + acc.moved.handle)))
            out["moved"] = {"text": words,
                            "account": account_json(acc.moved), "open": _("moved_open")}
        return out

    def _remote_host(self, acc):
        handle = acc.handle if acc else ""
        if "@" not in handle or not self.core.cfg["feed"].get("remote_profiles", True):
            return ""
        return handle.split("@", 1)[1]

    def _older_offer(self, acc, page, cursor=""):
        """The "more" under a profile's posts: {label, cursor} — my server's next page
        (cursor ""), their own server's ("origin" to start, then its next page), or None
        when there is nothing further back."""
        if page and cursor == "":
            return {"label": _("more"), "cursor": ""}
        host = self._remote_host(acc)
        if not host or cursor == "end":
            return None
        return {"label": _("older_from_origin", host=host), "cursor": cursor or "origin",
                "tip": _("older_from_origin_tip", host=host)}

    def account_more(self, acc_id, show=None, max_id="", cursor=""):
        """The next page of a profile's posts: my server's after max_id, or (cursor —
        "origin" or where their outbox goes on) from their own server, each post
        fetched into mine. → {posts, max_id, older}."""
        core = self.core
        acc_id = one_id(acc_id)
        if show not in dict(timed.PROFILE_SHOWS):
            show = timed.profile_show(core.cfg)
        acc = core.account(acc_id).result()
        cursor = str(cursor or "")
        if not cursor:
            page = core.account_posts(acc_id, one_id(max_id) if max_id else None,
                                      show=show).result()
            if page:
                return {"posts": self._posts(page), "max_id": page[-1].id,
                        "older": self._older_offer(acc, page)}
            return {"posts": [], "max_id": max_id, "older": self._older_offer(acc, [])}
        if cursor == "end" or not self._remote_host(acc):
            return {"posts": [], "max_id": max_id, "older": None}
        got, nxt = core.older_from_origin(acc, None if cursor == "origin" else cursor,
                                          (), resolve=True).result(timeout=180)
        got = [e for e in got or () if timed.keeps(e, show, acc_id)]
        host = self._remote_host(acc)
        return {"posts": self._posts(got), "max_id": max_id,
                "older": self._older_offer(acc, [], nxt or "end"),
                # how many came from their server, as the windows' status line says it
                "said": _("origin_got", n=len(got), host=host) + " · " +
                _("older_from_origin_note") if got else ""}

    def origin_list(self, acc_id, cursor=""):
        """Their own server's posts, step one: the addresses of the next page (fast) →
        {uris, older, host, words} — the page then fetches them a few at a time
        (origin_fetch), counting "n of N" on its button, as the windows do."""
        core = self.core
        acc = core.account(one_id(acc_id)).result()
        host = self._remote_host(acc)
        cursor = str(cursor or "")
        if not host or cursor == "end":
            return {"uris": [], "older": None, "host": host, "words": {}}
        uris, nxt = core.older_from_origin(acc, None if cursor in ("", "origin") else cursor,
                                           (), resolve=False).result(timeout=180)
        n = len(uris or ())
        return {"uris": list(uris or ()), "older": self._older_offer(acc, [], nxt or "end"),
                "host": host,
                "words": {"fetching": _("origin_fetching", n="{n}", total=n, host=host),
                          "got": _("older_from_origin_note")}}

    def origin_fetch(self, acc_id, uris, show=None):
        """Step two: these addresses' posts fetched into my server → {posts}."""
        core = self.core
        acc_id = one_id(acc_id)
        if show not in dict(timed.PROFILE_SHOWS):
            show = timed.profile_show(core.cfg)
        uris = [str(u) for u in (uris or ()) if str(u).startswith("https://")][:8]
        got = core.resolve_statuses(uris).result(timeout=180) if uris else []
        got = [e for e in got or () if timed.keeps(e, show, acc_id)]
        return {"posts": self._posts(got)}

    @staticmethod
    def _date(when):
        return when.astimezone().strftime("%d.%m.%Y") if when else ""

    def profile_act(self, acc_id, key, answer=None, confirmed=False, chosen=None):
        """A profile's button (common/profile.py), done as the windows do it; what's
        left for the page comes back: a question, a line to type, the editor."""
        from ..common import profile as prof
        core = self.core
        acc_id = one_id(acc_id)
        if key not in WEB_PROFILE_ACTS:
            raise ValueError(key)
        acc = core.account(acc_id).result()
        rel = core.relationship(acc_id).result()
        host = _WebHost(core, confirmed)
        host.answer = answer
        host.chosen = chosen
        prof.do(key, acc, rel, core, host, lambda _r: host.out.setdefault("refresh", True))
        if host.out.get("error"):
            raise ValueError(host.out["error"])
        return host.out

    def _post_by_id(self, sid):
        p = self.core.by_id(one_id(sid))
        if p is None:
            raise KeyError(sid)
        return p

    _client_errors = 0

    def client_error(self, body):
        """The page's own error (window.onerror, an unhandled promise) into fedtail's log:
        a browser's console nobody looks at was the only place it went. Addresses lose
        their query (the page's key may ride in one); at most 200 a run, each cut short."""
        Web._client_errors += 1
        if Web._client_errors > 200:
            return {}

        def clean(value, most):
            return re.sub(r"\?[\w=&%.~+-]*", "", str(value or ""))[:most]
        log.warning("web page %s: %s%s", clean(body.get("kind"), 20),
                    clean(body.get("message"), 500),
                    ("\n" + clean(body.get("where"), 2000)) if body.get("where") else "")
        return {}

    def act(self, action, sid):
        core = self.core
        p = self._post_by_id(sid)
        fn = {"like": core.like, "share": core.share, "bookmark": core.bookmark}.get(action)
        if fn is None:
            raise ValueError(action)
        got = fn(p).result() or core.by_id(p.id) or p
        return post_json(core, got, core.short_ids([got]).get(got.id))

    def post_menu(self, sid):
        """A post's ⋯ menu: the very items the Qt and GTK windows show (common/actions:
        what is offered, when, in which order) — the page only lays them out; a list's
        submenu, the whole text and the translation open as places (common/places.py).
        Left out: "as another account" (one account a page)."""
        from ..common import actions
        core = self.core
        p = self._post_by_id(sid)
        me = core.me
        cfg = core.cfg
        ctx = actions.Ctx(cfg=cfg, me_id=me.id if me else None, supports=core.supports,
                          subscribed=core.subscribed, thread_quiet=core.thread_quiet,
                          lists=True, long_form=bool(cfg["feed"].get("long_form", True)),
                          translate=bool(getattr(core.caps, "translation", False)),
                          translates=getattr(core, "translation_languages", None),
                          quote_reply=bool(cfg["post"].get("quote_prefix", "> ")),
                          # all accounts in one: ★ ♻ ↩ from another of them (ui.act_as)
                          act_as=(lambda e: self.merged_core().act_accounts(core.raw(e)))
                          if self.merged_core() and cfg["ui"].get("act_as", True) else None)
        short = core.short_ids([p]).get(real(p).id)
        unread = p.id in core.unread([p])
        items = []
        for it in actions.menu(p, ctx, short, unread):
            if it.kind in ("link", "open", "copy", "separator", "quote_reply"):
                items.append({"kind": it.kind, "label": it.label, "url": it.url,
                              "text": it.text})
            elif it.kind == "lists":  # a place: the lists, ticked where they are
                items.append({"kind": "lists", "label": it.label, "url": "", "text": "",
                              "page": {"page": "list_of", "arg": it.data.id}})
            elif it.kind == "act_as":  # one item a choice: the page has no submenus
                items.append({"kind": "act_as", "label": it.label, "url": "", "text": "",
                              "choices": [{"label": label, "tag": tag or "", "action": action}
                                          for label, _e, tag, action in it.data]})
            elif it.kind in ("long_form", "translate"):
                items.append({"kind": it.kind, "label": it.label, "url": "", "text": "",
                              "page": {"page": it.kind, "arg": p.id}})
        while items and items[0]["kind"] == "separator":
            items.pop(0)
        return {"subscribed": core.subscribed(p), "muted": core.thread_quiet(p),
                "own": bool(me and real(p).author.id == me.id), "items": items}

    def link(self, url, confirmed=False, chosen=None, shown=()):
        """A fedtail: link from the ⋯ menu, done the way every window does it
        (common/links.py); what the page must do then comes back: a message, a
        question first ("sure?" — asked again with confirmed), a place to open, the
        editor to fill, text to copy."""
        from ..common.links import Links
        host = _WebHost(self.core, confirmed, shown)
        host.chosen = chosen
        Links(self.core, host).open(str(url or ""))
        if host.out.get("error"):
            raise ValueError(host.out["error"])
        return host.out

    def merged_core(self):
        """The merged core behind this page (all accounts in one), or None."""
        inner = getattr(self.core, "_core", self.core)
        return inner if hasattr(inner, "act_as") and getattr(inner, "others", None) else None

    def act_as(self, sid, tag, action):
        """★ / ♻ / ↩ from another account of the window (the ⋯ menu's "As…"): the post
        found on that account's server, the action done there; a reply opens the editor
        on the post as that account sees it (common/actions, Qt's window.act_as)."""
        if action not in ("fav", "boost", "reply") or self.merged_core() is None:
            raise ValueError(action)
        p = self._post_by_id(sid)
        tag = str(tag or "") or None
        got = self.core.act_as(p, tag, "find" if action == "reply" else action).result(120)
        if action == "reply":
            if got is None:
                raise ValueError(_("act_as_wait"))
            post = post_json(self.core, got, None)
            return {"compose": {"reply_to": got.id}, "post": post}
        via = self.core.via(got) if got is not None else ""
        me = self.core.me
        return {"message": _("act_as_done", acct=via or "@" + (me.handle if me else ""))}

    def thread_act(self, action, sid):
        """Subscribe to, leave, mute or unmute the thread a post is in."""
        core = self.core
        p = self._post_by_id(sid)
        if action in ("sub", "unsub"):
            (core.subscribe if action == "sub" else core.unsubscribe)(p).result()
            return {"message": _("subbed") if action == "sub" else _("unsubbed")}
        if action in ("mute", "unmute"):
            core.mute_thread(p, action == "mute").result()
            return {"message": _("thread_muted" if action == "mute" else "thread_unmuted")}
        raise ValueError(action)

    def delete(self, sid):
        """My own post, after the page asked "sure?"."""
        core = self.core
        p = self._post_by_id(sid)
        me = core.me
        if not (me and real(p).author.id == me.id):
            raise ValueError("not mine")
        core.delete(p).result()
        return {"message": _("deleted")}

    def vote(self, sid, choices):
        core = self.core
        p = self._post_by_id(sid)
        choices = [int(c) for c in choices or ()][:50]
        got = core.vote(p, choices).result() or p
        return post_json(core, got, core.short_ids([got]).get(got.id))

    def add_language(self, code):
        """"Another language…": a code the editor lists from then on (kept as the windows
        keep it: languages_added); its row for the page's list."""
        from ..common import compose as cc
        code = str(code or "").strip().lower()
        if not cc.LANG_CODE.fullmatch(code):
            raise ValueError(_("lang_other_ask"))
        added = list(self.core.get_state("languages_added", []) or [])
        if code not in added and code not in cc.languages(self.core.cfg):
            self.core.set_state("languages_added", added + [code])
        return {"code": code, "label": cc.language_label(code)}

    # ---- drafts: the core's, as the windows keep them (synced: sync.drafts) ------------
    def draft_start(self, reply_to="", quote="", edit="", invite=False):
        """What the editor starts with (common/compose.start): the draft kept for this
        post — a new one, a reply, a quote, my post corrected — or the reply's mentions
        and its warning. → {key, text, cw, visibility, language, sensitive, poll,
        restored, hint}. Pictures aren't kept in a phone's or a page's draft."""
        from ..common import compose as cc
        core = self.core
        parent = self._post_by_id(reply_to) if reply_to else None
        quoted = self._post_by_id(quote) if quote else None
        mine = self._post_by_id(edit) if edit else None
        key = cc.draft_key(core, parent, quoted, mine, bool(invite))
        st = cc.start(core, key, parent, invite=bool(invite))
        return {"key": key, "text": st.text, "cw": st.cw, "visibility": st.visibility,
                "language": st.language, "sensitive": st.sensitive, "poll": st.poll,
                "restored": st.restored, "hint": _(st.hint) if st.hint else ""}

    def draft_save(self, key, snap):
        """The editor as it is now, kept under key (or gone, emptied) — post.drafts_autosave
        as in the windows. → {saved: bool, hint}."""
        from ..common import compose as cc
        key = str(key or "")
        if not re.fullmatch(r"(new|reply:|quote:|edit:|invite:)[\w.~-]{0,100}", key):
            raise ValueError("key")
        snap = cc.snapshot(str(snap.get("text") or ""), str(snap.get("cw") or ""),
                           str(snap.get("visibility") or cc.DEFAULT_VIS), [],
                           snap.get("language"), bool(snap.get("sensitive")),
                           snap.get("poll") if isinstance(snap.get("poll"), dict) else None)
        what = cc.keep(snap, None, bool(self.core.get_draft(key)))
        if what == "delete":
            self.core.delete_draft(key)
            return {"saved": False, "hint": ""}
        if what == "save":
            self.core.save_draft(key, snap)
        return {"saved": bool(self.core.cfg["post"]["drafts_autosave"]),
                "hint": _("draft_saved") if self.core.cfg["post"]["drafts_autosave"] else ""}

    def draft_drop(self, key):
        """Sent, or discarded after the question: the draft goes (here and elsewhere)."""
        self.core.delete_draft(str(key or ""))
        return {"ok": True}

    def complete(self, before):
        """What the editor offers for the #tag, @name or :emoji: being typed (the
        windows' completion, common/compose): before is the line up to the cursor →
        {"word", "items": [{insert, label}]}; for a name with few known here, the
        server is asked too."""
        from ..common import compose as cc
        core = self.core
        if not getattr(self, "_completion_ready", False):
            self._completion_ready = True
            core.prepare_tags()
            core.prepare_people()
            if core.cfg["post"].get("complete_emoji", True):
                core.prepare_emoji()
        sigil, word = cc.token_at_end(str(before or "")[-200:])
        if not sigil:
            return {"word": "", "items": []}
        items = cc.suggestions(core, sigil, word)
        if sigil == "@" and core.cfg["post"].get("complete_mentions", True) and \
                len(word) >= 2 and len(items) < 8:
            try:
                found = core.search_people(word).result(timeout=8)
                items = cc.more_people(core.mention_suggestions(word), found)
            except Exception as e:  # noqa: BLE001 — what's known here still helps
                log.debug("complete: %s", e)
        if not cc.worth_offering(items, word):
            items = []
        return {"word": sigil + word, "items": [{"insert": i, "label": lb} for i, lb in items]}

    def compose_check(self, body):
        """What the editor shows beside the text as it is typed (common/compose.count, the
        windows'): characters of the limit, how many posts a chain makes, the #CamelCase
        hint for screen readers (post.camelcase_hint)."""
        from ..common import compose as cc
        caps = self.core.caps
        sid = str(body.get("reply_to") or "")
        reply_to = self.core.by_id(sid) if sid else None
        c = cc.count(str(body.get("text") or ""), str(body.get("cw") or ""),
                     int(getattr(caps, "max_characters", 500) or 500), self.core.cfg,
                     reply_to=reply_to, visibility=str(body.get("visibility") or ""),
                     me=self.core.me)
        return {"n": c.n, "limit": c.limit, "over": c.over, "parts": c.parts,
                "newcomers": _("dm_newcomer_typed", who=", ".join(c.newcomers))
                if c.newcomers else "",
                "chain": _("chain_count", n=c.parts) if c.parts > 1 else "",
                "camel": _("camel_hint", tags=", ".join("#" + t for t in c.flat_tags[:3]))
                if c.flat_tags else ""}

    def preview(self, body):
        """The post as it will read (Qt's preview): who sees it, the language, a chain's
        parts, the pictures, Markdown or plain — each part as safe HTML."""
        from html import escape as esc

        from ...model.text import chain_parts
        from ..mdhtml import markdown_html
        text = str(body.get("text") or "").strip()
        cw = str(body.get("cw") or "").strip()
        parts = (chain_parts(text) if self.core.cfg["post"].get("chain", True) else []) \
            or [text]
        md = bool(self.core.markdown)
        n = _int(body.get("media"), 0)
        head = " · ".join(x for x in (
            str(body.get("visibility_words") or ""), str(body.get("lang_words") or ""),
            _("chain_count", n=len(parts)) if len(parts) > 1 else "",
            _("preview_media", n=n) if n else "",
            _("preview_md") if md else _("preview_plain")) if x)
        html = [markdown_html(p, lambda u: u if u.startswith("https://") else None)
                if md else "<p>" + esc(p).replace("\n", "<br>") + "</p>" for p in parts]
        return {"title": _("preview"), "head": head, "cw": cw, "parts": html,
                "back": _("preview_back"), "send": _("send")}

    def save_media(self, url):
        """A picture's or a video's original into ui.save_dir on this machine, as the
        windows' "Save" (common/images.py: no token along, public addresses only)."""
        from ...core import saving
        from ..common.images import Cache
        url = str(url or "")
        if not _https(url):
            raise ValueError("url")
        if self._saver is None:
            self._saver = Cache(self.core, None)  # saving needs no toolkit
        path = self._saver.save(url, saving.save_dir(self.core.cfg)).result()
        return {"message": _("saved_to", path=str(path))}

    def thread_progress(self, sid):
        """threads.thread_progress: how fetching the open thread's replies goes →
        {"text", "bar", "stage"} ("" — nothing going on)."""
        from ..common.progress import bar, thread_words
        step = self.core.thread_progress(one_id(sid)) \
            if self.core.cfg["feed"].get("thread_progress") else None
        return {"text": thread_words(step), "bar": bar(step),
                "stage": (step or {}).get("stage", "")}

    def refresh(self):
        """The page's ⟳: a round now, and the lanes holding new posts let them in."""
        self.core.refresh_by_hand()
        return {"ok": True}

    def poll_refresh(self, sid):
        """Fresh counts for a post's poll (the "refresh" in its footer)."""
        core = self.core
        p = self._post_by_id(sid)
        got = core.refresh_poll(p).result() or core.by_id(p.id) or p
        return post_json(core, got, core.short_ids([got]).get(got.id))

    def follow(self, acc_id, on):
        rel = self.core.follow(one_id(acc_id), bool(on)).result()
        return {"following": bool(rel.following or rel.requested) if rel else bool(on),
                "requested": bool(rel and rel.requested)}

    def post(self, body):
        core = self.core
        text = (body.get("text") or "").strip()
        if not text:
            raise ValueError("empty")
        cw = (body.get("cw") or "").strip()
        if body.get("edit"):  # my post corrected (the ⋯ menu's Edit)
            mine = self._post_by_id(body["edit"])
            changed = self._media_changes(mine, body.get("media_edit"))
            p = (core.edit(mine, text, cw, media=changed) if changed else
                 core.edit(mine, text, cw)).result()
            return {"id": p.id if p else None, "url": p.url if p else "", "edited": True}
        parent = self._post_by_id(body["reply_to"]) if body.get("reply_to") else None
        vis = body.get("visibility") or core.reply_visibility(parent)
        if vis == "private":  # the API's word, from an older page
            vis = "followers"
        if vis not in ("public", "unlisted", "followers", "direct"):
            raise ValueError(vis)
        lang = (body.get("lang") or "").strip() or None
        media = []
        for m in (body.get("media") or [])[:20]:
            if isinstance(m, dict):
                item = (str(self.upload_path(m.get("token"))), str(m.get("alt") or "")[:1500])
                focus = _focus(m.get("focus"))
                # a video's or a sound's cover: a picture uploaded the same way
                cover = str(self.upload_path(m["cover"])) if m.get("cover") else None
                if cover:
                    media.append(item + (focus, cover))
                else:
                    media.append(item + (focus,) if focus else item)
        bare = sum(1 for m in media if not m[1].strip())
        if bare and not body.get("alt_ok") and core.cfg["post"].get("alt_reminder", True):
            # post.alt_reminder: a picture without a description — the page asks first,
            # as the windows do; nothing is sent until it answers
            return {"ask_alt": {"title": _("alt_missing_title"), "text": _("alt_missing", n=bare),
                                "describe": _("alt_describe"), "send": _("alt_send_anyway")}}
        from ..common import compose as cc
        said = None if body.get("lang_ok") else cc.lang_mismatch(core.cfg, text, lang)
        if said:  # post.lang_check: the text reads as another language — asked first
            title, words, switch, anyway = cc.lang_question(
                said, lang or core.cfg["post"].get("language"))
            return {"ask_lang": {"title": title, "text": words, "lang": said,
                                 "switch": switch, "send": anyway}}
        poll = None
        if isinstance(body.get("poll"), dict) and not media:
            from ..common import compose as cc
            pb = body["poll"]
            poll = cc.poll_data(True, [str(o) for o in pb.get("options") or []][:20],
                                int(pb.get("expires_in") or 86400), bool(pb.get("multiple")))
        from ..common.compose import when_utc
        when = when_utc(body.get("scheduled_at"))
        extra = {}
        if body.get("account") is not None:  # the editor's "From" (all accounts in one)
            keys = [k for k, _h in core.post_accounts(None)[0]]
            if str(body["account"]) not in keys:
                raise ValueError("account")
            extra["account"] = str(body["account"])
        quote = str(body["quote"]) if body.get("quote") else None
        away = core.cfg["post"].get("send_in_background") and not when
        key = core.draft_key(parent.id if parent else None, quote) if away else None
        if away:  # kept here till it's out: a failure loses nothing typed
            core.save_draft(key, {"text": text, "cw": cw, "visibility": vis,
                                  **({"language": lang} if lang else {})})
        fut = core.post(text, vis, parent, cw, language=lang, quote=quote,
                        media=media, sensitive=bool(body.get("sensitive")), poll=poll,
                        scheduled_at=when, draft_key=key, **extra)

        def tidy(f):  # sent or not: the copies go (a focus may ride along as the third)
            for m in media:
                Path(m[0]).unlink(missing_ok=True)
                if len(m) > 3 and m[3]:  # and the cover's
                    Path(m[3]).unlink(missing_ok=True)
            if away and f.exception() is not None:  # the page hears it as a notification
                log.warning("send in the background: %s", f.exception())
                with self.changed:
                    self.note_seq += 1
                    self.note_log.append((self.note_seq, {
                        "title": _("send_failed"),
                        "body": _("sent_background_failed", err=f.exception()),
                        "lane": "", "thread": parent.id if parent else ""}))
                self.bump()
        if away:  # post.send_in_background: the page's editor closes at once
            fut.add_done_callback(tidy)
            return {"id": None, "url": "", "background": True,
                    "message": _("sent_background")}
        p = fut.result()
        tidy(fut)
        if when:
            return {"id": None, "url": "", "scheduled": True,
                    "message": _("scheduled_msg", when=when.replace("T", " ")[:16])}
        return {"id": p.id if p else None, "url": p.url if p else ""}

    @staticmethod
    def _media_changes(post, wanted):
        """{media id: (description, focus)} for the pictures of my post whose words or
        focus the editor changed ({}: none)."""
        if not isinstance(wanted, list):
            return {}
        have = {m.ref.id: m for m in real(post).media}
        out = {}
        for w in wanted[:20]:
            if not isinstance(w, dict) or str(w.get("id")) not in have:
                continue
            m = have[str(w["id"])]
            alt = str(w.get("alt") or "")[:1500]
            focus = _focus(w.get("focus"))
            if alt != m.alt or (focus is not None and focus != m.focus):
                out[m.ref.id] = (alt, focus)
        return out

    def command(self, line, confirmed=False):
        """confirmed: D #id deletes only when asked twice — the page asks "sure?" in
        between; a typo or a stray request alone deletes nothing."""
        fut, message = self.cmds.run(line)
        if fut is None:
            return {"ok": False, "message": message}
        result = fut.result()
        if isinstance(result, tuple):
            kind, what = result
            if kind == "thread":
                return {"ok": True, "open": {"thread": what}}
            if kind == "profile":
                return {"ok": True, "open": {"account": what.id}}
            if kind == "delete":
                if not confirmed:
                    return {"ok": False, "confirm": _("delete_q", text=snippet(what, 200))}
                self.core.delete(what).result()
                return {"ok": True, "message": _("deleted")}
        return {"ok": True, "message": result if isinstance(result, str) else message}

    # ---- places (common/places.py) ------------------------------------------------
    def places(self):
        from ..common.places import Places
        return Places(self.core, self._date_time)

    @staticmethod
    def _date_time(when):
        return when.astimezone().strftime("%d.%m.%Y %H:%M") if when else ""

    def place_menu(self):
        return [{"name": n, "title": t} for n, t in self.places().menu()]

    def page(self, name, arg="", tab="", cursor=""):
        from ..common.places import PLACES
        if name not in PLACES:
            raise KeyError(name)
        pg = self.places().page(name, arg, tab, cursor)
        posts = [r.data for r in pg.rows if r.kind == "post"]
        made = iter(self._posts(posts, parents=True)) if posts else iter(())
        rows = []
        for r in pg.rows:
            row = {"kind": r.kind, "title": r.title, "line": r.line, "key": r.key,
                   "buttons": [_btn_json(b) for b in r.buttons]}
            if r.kind == "post":
                row["post"] = next(made)
            elif r.kind == "account" and r.data is not None:
                row["account"] = account_json(r.data)
            elif r.kind == "html":
                row["html"] = web_clean(r.title) if name not in ("help", "news") else r.title
                row["title"] = ""
            elif r.kind == "pre":
                row["html"] = "<pre>" + escape(r.title) + "</pre>"
                row["kind"], row["title"] = "html", ""
            elif r.kind == "qr":  # our own SVG (common/qr.py), and the rows for the phone
                from ..common.qr import svg
                row["qr"] = list(r.data or ())
                row["html"] = ('<div class="qr">' + svg(row["qr"]) + "<div>" + escape(r.line) +
                               "</div></div>")
                row["kind"] = "html"
                row["title"] = ""
                row["line"] = r.line
            rows.append(row)
        return {"name": pg.name, "title": pg.title, "arg": pg.arg, "hint": pg.hint,
                "tabs": [list(t) for t in pg.tabs], "tab": pg.tab, "rows": rows,
                "form": [{"name": f.name, "label": f.label, "value": f.value, "kind": f.kind,
                          "choices": [list(c) for c in f.choices], "tip": f.tip,
                          "scan": f.scan}
                         for f in pg.form],
                "submit": _btn_json(pg.submit) if pg.submit else None,
                "more": _btn_json(pg.more) if pg.more else None, "empty": pg.empty}

    def place_act(self, body):
        act = body.get("act")
        if not (isinstance(act, list) and len(act) == 3 and all(isinstance(x, str)
                                                               for x in act)):
            raise ValueError("act")
        values = body.get("values") if isinstance(body.get("values"), dict) else {}
        # a file field (a new avatar): the page uploaded it, the place gets its path
        values = {k: str(self.upload_path(v["upload"])) if isinstance(v, dict) and
                  "upload" in v else v for k, v in values.items()}
        answer = body.get("answer") if isinstance(body.get("answer"), str) else None
        out = self.places().act(*act, values=values, confirmed=body.get("confirmed") is True,
                                answer=answer)
        if out.open and out.open.get("profile") and not out.error:
            # another account: this page goes over to it (Accounts, a login done)
            self.switch_profile(str(out.open["profile"]))
            return {k: v for k, v in (("message", out.message), ("reload", True)) if v}
        got = {k: v for k, v in (("message", out.message), ("confirm", out.confirm),
                                 ("open", out.open), ("compose", out.compose),
                                 ("copy", out.copy)) if v}
        if out.ask:
            got["ask"] = {"title": out.ask[0], "question": out.ask[1], "text": out.ask[2]}
        if out.refresh:
            got["refresh"] = True
        if out.error:
            raise ValueError(out.error)
        return got

    def help_link(self, url, current):
        """A help page's link (fedtail:help/… or the web): where it goes."""
        from ..common.places import Places
        return Places(self.core).help_target(url, current).open

    def resolve(self, url):
        found = self.core.resolve(url).result()
        if found is None:
            return {"found": None}
        if isinstance(found, Account):
            return {"found": "account", "id": found.id}
        return {"found": "thread", "id": found.id}


# words the page shows, in the profile's language
WORDS = ("reply", "fav", "faved", "boost", "boosted", "bookmark", "unbookmark", "thread",
         "write", "send", "sent", "tui_back", "web_thread", "follow", "unfollow",
         "acc_follows_you", "web_cw", "web_show", "web_load_error", "web_empty",
         "web_reply_to", "post_from_tip", "post_from_other", "web_cancel", "web_cmd",
         "web_visibility", "vis_public",
         "vis_unlisted", "vis_private", "vis_direct", "web_media", "web_sensitive",
         "web_parent_gone", "web_mark_read", "tui_profile", "open_browser", "refresh",
         "more", "no_older", "older_up", "older_down", "poll_vote", "poll_voted",
         "cw_placeholder", "cw_add",
         "web_new_post", "web_original", "web_close", "web_lanes", "web_edited",
         "web_requested", "lang_label", "pinned", "act_as_wait",
         "reply_quote", "quote_in_reply", "sub_thread", "unsub_thread", "mute_thread",
         "unmute_thread", "copy_link", "delete", "delete_q", "help_title", "about",
         "edit", "quote",
         "my_profile", "web_more", "web_menu", "web_keys", "web_keys_text", "web_copied",
         "web_about", "help_news", "web_notify", "web_notify_on", "web_notify_off",
         "find_placeholder", "find_prev", "find_next", "find_close", "find_none",
         "find_count", "to_new", "to_new_tip", "browse_empty", "media_limit", "alt_prompt",
         "detach", "poll_option", "poll_several", "lang_tip", "attach", "poll_add_tip",
         "sensitive_mark_tip", "schedule_tip", "schedule_when",
         # what the windows have and the page now too (docs/src/parity.toml)
         "help_back", "help_forward", "debug_notify", "debug_notify_sent", "notify_failed",
         "notify_test_body", "accounts_merge", "accounts_merge_tip", "try_theme",
         "web_push", "web_push_tip",
         "try_theme_tip", "a11y_avatar",
         "group_fold_tip", "thread_loading", "loading", "find_deeper", "find_deeper_tip",
         "find_everywhere", "find_everywhere_tip", "find_searching", "find_archive_none",
         "poll_results", "poll_refresh", "poll_sending", "preview", "preview_tip",
         "discard", "discard_q", "discard_q_title", "lang_other_title", "lang_other_ask",
         "edit_media_kept", "focus_at", "focus_centre", "focus_none", "focus_tip",
         "media_cover", "media_cover_tip", "media_cover_set", "alt_title",
         "viewer_save", "viewer_save_tip", "viewer_keys", "viewer_unreachable", "saving",
         "image_failed", "image_loading", "short_id_tip", "reactions_tip", "cw_add_tip",
         "close_tip", "to_end_tip", "unread_tip",
         # columns: lanes side by side (ui.layout = "columns", ❯)
         "columns", "columns_tip", "full_width_tip", "column_left", "column_right", "column_close",
         # ≡ as a window: its groups, as the windows' submenus
         "web_menu_lanes", "web_menu_look", "tender_menu", "menu_people", "accounts",
         "debug_menu")


class Server(ThreadingHTTPServer):
    """At most MAX_CLIENTS connections at once: more are closed at the door, so a
    pile of half-open connections (from the network, with web.host open to it)
    can't take every thread."""
    daemon_threads = True

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.slots = threading.BoundedSemaphore(MAX_CLIENTS)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def handle_error(self, request, client_address):
        """A page that hung up mid-answer is everyday life, not a traceback on the
        terminal; anything else goes to the log (not stderr: no traceback over the
        terminal fedtail runs in)."""
        exc = sys.exc_info()[1]
        if isinstance(exc, GONE):
            log.debug("web: %s hung up", client_address[0])
            return
        log.warning("web: request failed", exc_info=True)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "fedtail"
    sys_version = ""
    web = None  # set by make_server
    timeout = SOCKET_SECONDS  # a client that goes quiet is dropped, its thread freed

    def log_message(self, fmt, *args):  # the path without its query: no key in the log
        log.debug("web %s %s -> %s", self.command, urlsplit(self.path).path,
                  args[1] if len(args) > 1 else "")

    # ---- plumbing ----------------------------------------------------------------
    def _authorized(self):
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            name, _sep, value = part.strip().partition("=")
            if name == COOKIE and hmac.compare_digest(value.encode(), self.web.key.encode()):
                return True
        return False

    def _send(self, status, body, ctype="application/json; charset=utf-8", extra=()):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, obj, status=HTTPStatus.OK):
        self._send(status, json.dumps(obj, ensure_ascii=False))

    def _forbidden(self):
        self._send(HTTPStatus.FORBIDDEN, _("web_forbidden"), "text/plain; charset=utf-8")

    # ---- GET ---------------------------------------------------------------------
    PIC_TYPES = {"jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif",
                 "webp": "image/webp", "avif": "image/avif", "bmp": "image/bmp",
                 "ico": "image/x-icon"}

    def _picture(self, url):
        """/pic?u=<https url>: the picture from the disk cache, fetched into it first
        when it isn't there (common/images.fetch_picture: no token, public addresses,
        redirects checked; only a whole picture is kept or given)."""
        from ...core import imagesniff, remote
        from ..common import images as pictures
        if not url.startswith("https://"):
            return self._send(HTTPStatus.BAD_REQUEST, b"", "text/plain")
        view = self.web.core
        own = view.own_hosts()
        p = pictures.fetch_picture(
            view.paths.cache_dir, url,
            lambda u, timeout: remote.open_url(None, u, timeout=timeout,
                                               schemes=("https",), own_hosts=own))
        if p is None:
            return self._send(HTTPStatus.NOT_FOUND, b"", "text/plain")
        data = p.read_bytes()
        fmt, _why = imagesniff.readable(data)
        ctype = self.PIC_TYPES.get(fmt or "")
        if ctype is None:  # a format the cache keeps but a browser can't show
            return self._send(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, b"", "text/plain")
        return self._send(HTTPStatus.OK, data, ctype,
                          extra=(("Cache-Control", "private, max-age=86400"),))

    def do_GET(self):  # noqa: N802 — http.server's name
        u = urlsplit(self.path)
        q = {k: v[-1] for k, v in parse_qs(u.query).items()}
        if u.path == "/" and ("k" in q or "t" in q):
            # t: a one-time link (what fedtail prints and opens); k: the key itself,
            # for links people kept from before — both end in the cookie and "/"
            if self.web.use_link(q["t"]) if "t" in q else \
                    hmac.compare_digest(q["k"].encode(), self.web.key.encode()):
                cookie = f"{COOKIE}={self.web.key}; HttpOnly; SameSite=Strict; Path=/; " \
                         f"Max-Age={400 * 24 * 3600}"
                self._send(HTTPStatus.SEE_OTHER, b"", "text/plain",
                           extra=(("Set-Cookie", cookie), ("Location", "/")))
            else:
                self._forbidden()
            return
        if not self._authorized():
            return self._forbidden()
        if u.path in STATIC:
            name, ctype = STATIC[u.path]
            return self._send(HTTPStatus.OK, static_text(name), ctype)
        if u.path in POSSUM:  # the curtain's opossum: still, or swinging while updating
            data = resources.files("fedtail").joinpath(
                "data/icons/" + POSSUM[u.path][0]).read_bytes()
            return self._send(HTTPStatus.OK, data, POSSUM[u.path][1])
        if u.path == "/pic":
            return self._picture(q.get("u", ""))
        if u.path == "/theme.css":
            return self._send(HTTPStatus.OK, self.web.theme_css(), "text/css; charset=utf-8")
        routes = {"/api/me": lambda: self.web.me(),
                  "/api/lanes": lambda: self.web.lanes(),
            "/api/curtain": lambda: self.web.curtain(),
                  "/api/slow": lambda: self.web.slow(),
                  "/api/columns": lambda: self.web.columns(),
                  "/api/lane": lambda: self.web.lane(q.get("name", ""), q.get("keep") == "1"),
                  "/api/thread_progress": lambda: self.web.thread_progress(q.get("id", "")),
                  "/api/thread": lambda: self.web.thread(q.get("id", ""),
                                                         q.get("at", "post")),
                  "/api/account": lambda: self.web.account(q.get("id", ""),
                                                           q.get("show") or None),
                  "/api/account_more": lambda: self.web.account_more(
                      q.get("id", ""), q.get("show") or None, q.get("max_id", ""),
                      q.get("cursor", "")),
                  "/api/post_menu": lambda: self.web.post_menu(q.get("id", "")),
                  "/api/places": lambda: self.web.place_menu(),
                  "/api/themes": lambda: self.web.themes(),
                  "/api/push": lambda: self.web.push_state(),
                  "/api/find": lambda: self.web.find(q.get("lane", ""), q.get("q", "")),
                  "/api/find_deeper": lambda: self.web.find_deeper(q.get("lane", ""),
                                                                   q.get("q", "")),
                  "/api/find_everywhere": lambda: self.web.find_everywhere(q.get("q", "")),
                  "/api/page": lambda: self.web.page(q.get("name", ""), q.get("arg", ""),
                                                     q.get("tab", ""), q.get("cursor", "")),
                  "/api/wait": lambda: self.web.wait_answer(
                      _int(q.get("v"), -1), _int(q.get("s"), -1), _int(q.get("n"), -1),
                      _int(q.get("p"), -1))}
        if u.path.startswith("/sound/"):
            data = self.web.sound_file(u.path[len("/sound/"):])
            if data is None:
                return self._send(HTTPStatus.NOT_FOUND, b"", "text/plain")
            return self._send(HTTPStatus.OK, data, "audio/wav")
        self._run(routes.get(u.path))

    # ---- POST --------------------------------------------------------------------
    def do_POST(self):  # noqa: N802
        if not self._authorized() or self.headers.get("X-Fedtail") != "1":
            return self._forbidden()
        if urlsplit(self.path).path == "/api/upload":  # a file, not JSON
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if n <= 0 or n > MAX_UPLOAD:
                return self._json({"error": "size"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            data = self.rfile.read(n)
            from urllib.parse import unquote
            name = unquote(self.headers.get("X-Name") or "")
            return self._run(lambda: self.web.upload(data, name))
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n < 0:  # read(-1) would read to the end: no limit at all
                raise ValueError(n)
            body = json.loads(self.rfile.read(min(n, 1_000_000)) or b"{}")
        except ValueError:
            return self._json({"error": "bad json"}, HTTPStatus.BAD_REQUEST)
        if not isinstance(body, dict):
            return self._json({"error": "bad json"}, HTTPStatus.BAD_REQUEST)
        path = urlsplit(self.path).path
        web = self.web
        routes = {
            "/api/read": lambda: web.read([str(i) for i in body.get("ids", [])][:500],
                                          body.get("lane") or None),
            "/api/lane_clear": lambda: web.lane_clear(body.get("name"),
                                                      body.get("confirmed") is True),
            "/api/lane_set": lambda: web.lane_set(body),
            "/api/act": lambda: web.act(body.get("action"), str(body.get("id"))),
            "/api/client_error": lambda: web.client_error(body),
            # what a reply starts with — who sees it, its warning (common/compose.start)
            "/api/draft_start": lambda: web.draft_start(str(body.get("reply_to") or "")),
            "/api/vote": lambda: web.vote(str(body.get("id")), body.get("choices")),
            "/api/poll_refresh": lambda: web.poll_refresh(str(body.get("id"))),
            "/api/refresh": web.refresh,
            "/api/fold": lambda: web.fold(body.get("group")),
            "/api/columns": lambda: web.set_columns(body.get("names"), body.get("on") is not False),
            "/api/reveal": lambda: web.reveal(body.get("lane"), body.get("index")),
            "/api/compose_check": lambda: web.compose_check(body),
            "/api/format": lambda: web.format_text(body),
            "/api/add_language": lambda: web.add_language(body.get("code")),
            "/api/preview": lambda: web.preview(body),
            "/api/save": lambda: web.save_media(body.get("url")),
            "/api/older": lambda: web.older(body.get("name"), bool(body.get("ahead"))),
            "/api/full_width": lambda: web.full_width(body.get("on")),
            "/api/on_screen": lambda: web.on_screen(body.get("ids")),
            "/api/stood": lambda: web.stood(body.get("lane"), body.get("key"),
                                            bool(body.get("end"))),
            "/api/follow": lambda: web.follow(str(body.get("id")), body.get("on")),
            "/api/post": lambda: web.post(body),
            "/api/command": lambda: web.command(str(body.get("line", "")),
                                                body.get("confirm") is True),
            "/api/active": lambda: web.activate(body.get("name")),
            "/api/resolve": lambda: web.resolve(str(body.get("url", ""))),
            "/api/thread_act": lambda: web.thread_act(body.get("action"), str(body.get("id"))),
            "/api/complete": lambda: web.complete(body.get("before")),
            "/api/origin_list": lambda: web.origin_list(str(body.get("id")),
                                                        str(body.get("cursor") or "")),
            "/api/origin_fetch": lambda: web.origin_fetch(str(body.get("id")),
                                                          body.get("uris") or [],
                                                          body.get("show") or None),
            "/api/act_as": lambda: web.act_as(str(body.get("id")), body.get("tag"),
                                              str(body.get("action") or "")),
            "/api/place": lambda: web.place_act(body),
            "/api/delete": lambda: web.delete(str(body.get("id"))),
            "/api/theme": lambda: web.try_theme(body.get("name")),
            "/api/merge": lambda: web.toggle_merge(),
            "/api/push_on": lambda: web.push_on(body),
            "/api/push_off": lambda: web.push_off(),
            "/api/link": lambda: web.link(str(body.get("url", "")),
                                          bool(body.get("confirmed")), _chosen(body),
                                          [str(x) for x in body.get("shown") or ()
                                           if isinstance(x, (str, int))][:2000]),
            "/api/profile_act": lambda: web.profile_act(
                str(body.get("id", "")), str(body.get("key", "")),
                body.get("answer") if isinstance(body.get("answer"), str) else None,
                bool(body.get("confirmed")), _chosen(body)),
        }
        self._run(routes.get(path))

    def _run(self, fn):
        """Answer with what fn returns. Its failures become the page's error; a page
        that left before the answer (a reload, a closed tab: the long /api/wait most of
        all) is no failure at all — the answer just has nowhere to go."""
        status = HTTPStatus.OK
        if fn is None:
            body, status = {"error": "not found"}, HTTPStatus.NOT_FOUND
        else:
            try:
                body = fn()
            except GONE:
                return self._gone()
            except (KeyError, ValueError) as e:
                body = {"error": f"{e.__class__.__name__}: {e}"}
                status = HTTPStatus.BAD_REQUEST
            except Exception as e:  # noqa: BLE001 — the page says what failed
                # the kind of failure only: a request's error text carries its whole
                # address (a search's words in the query), and the log goes into bug reports
                log.warning("web %s: %s", urlsplit(self.path).path, e.__class__.__name__)
                body, status = {"error": _api_error(e)}, HTTPStatus.BAD_GATEWAY
        try:
            return self._json(body, status)
        except GONE:
            return self._gone()

    def _gone(self):
        log.debug("web %s: the page left before the answer", urlsplit(self.path).path)
        self.close_connection = True


def make_server(core, host, port, key):
    web = Web(core, key)
    handler = type("FedtailHandler", (Handler,), {"web": web})
    srv = Server((host, port), handler)
    srv.web = web
    return srv
