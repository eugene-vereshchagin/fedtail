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
from urllib.parse import parse_qs, urlsplit

from ... import __version__, i18n, version
from ...core import config
from ...core.view import View
from ...i18n import _
from ...model import Account, Share, real
from ...model.text import reply_mentions, snippet
from ..common.commands import Commands
from ..richtext import clean

log = logging.getLogger(__name__)

COOKIE = "fedtail_web"
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8")}
CSP = ("default-src 'self'; img-src https: data:; media-src https: 'self'; style-src 'self'; "
       "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
       "form-action 'self'")
WAIT_SECONDS = 25
LINK_SECONDS = 15 * 60  # a one-time login link is good this long
MAX_CLIENTS = 32        # connections at once (a phone and a laptop need a handful)
SOCKET_SECONDS = WAIT_SECONDS + 35  # a client that sends nothing this long is dropped
# the browser hung up: nothing to answer, nothing to report
GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)
_ID = re.compile(r"[A-Za-z0-9_.-]{1,100}")


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


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def static_text(name):
    return resources.files("fedtail").joinpath(f"data/web/{name}").read_text("utf-8")


# ---- what the page gets -------------------------------------------------------------
def _https(url):
    return url if isinstance(url, str) and url.startswith("https://") else ""


def _iso(t):
    return t.isoformat().replace("+00:00", "Z") if t else ""


def account_json(acc):
    if acc is None:
        return {"id": None, "handle": "", "name": "", "avatar": "", "url": "", "bot": False}
    return {"id": acc.id, "handle": acc.handle, "name": acc.name or acc.username,
            "avatar": _https(acc.avatar_static), "url": _https(acc.url), "bot": acc.bot}


def web_clean(html):
    """Server HTML, cleaned (richtext.clean) — minus the inline styles meant for Qt,
    which the page's CSP refuses anyway."""
    return clean(html).replace(' style="text-decoration:none;"', "")


_SHORTCODE = re.compile(r":([A-Za-z0-9_]{1,64}):")


def with_emojis(html, emojis):
    """:shortcode: in cleaned HTML → the emoji's picture (https only; the code and the
    address are escaped, so nothing of the post becomes markup)."""
    if not emojis or ":" not in html:
        return html
    pics = {e.shortcode: _https(e.static_url or e.url) for e in emojis}

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
    return {"kind": m.kind, "preview": _https(m.preview), "url": _https(m.url or m.remote_url),
            "alt": m.alt, "w": m.width, "h": m.height}


def poll_json(poll):
    if poll is None:
        return None
    total = poll.votes or sum(o.votes or 0 for o in poll.options)
    return {"id": poll.id if hasattr(poll, "id") else poll.ref.id,
            "options": [{"title": o.title, "votes": o.votes,
                         "share": round(100 * (o.votes or 0) / total) if total else 0}
                        for o in poll.options],
            "multiple": poll.multiple, "expired": poll.expired, "voted": poll.voted,
            "mine": list(poll.my_votes),
            "summary": " · ".join(x for x in (
                _("poll_votes", n=poll.votes),
                _("poll_closed") if poll.expired else
                (_("poll_until", when=poll.expires.astimezone().strftime("%d.%m %H:%M"))
                 if poll.expires else ""),
                _("poll_multiple") if poll.multiple and not poll.expired else "") if x)}


def card_json(card):
    if card is None or not _https(card.url):
        return None
    return {"url": card.url, "title": card.title, "description": card.description,
            "image": _https(card.image), "provider": card.provider}


def quote_json(view, quote):
    if quote is None:
        return None
    if quote.post is None or quote.state != "accepted":
        key = "quote_" + quote.state if quote.state in QUOTE_STATES else "quote_unavailable"
        return {"id": quote.id, "note": _(key)}
    q = quote.post
    return {"id": q.id, "account": account_json(q.author), "text": snippet(q, 300),
            "created": _iso(q.created), "media": len(q.media)}


QUOTE_STATES = {"pending", "rejected", "revoked", "deleted", "unauthorized",
                "blocked_account", "blocked_domain", "muted_account"}


def post_json(view, entry, alias=None, unread=False, parent=None, number=None, depth=None,
              item_id=None):
    """A lane entry (Post or Share) as the page draws it."""
    p = real(entry)
    html = view.in_app(p) if view.cfg["ui"]["links_in_app"] else p.text
    me = view.me
    out = {
        "id": entry.id, "item": item_id or entry.id, "sid": p.id, "alias": alias,
        "account": account_json(p.author), "created": _iso(p.created),
        "edited": p.edited is not None, "visibility": p.visibility,
        "warning": p.warning, "sensitive": p.sensitive,
        "html": with_emojis(web_clean(html), p.emojis),
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
    if number is not None:
        out["number"], out["depth"] = number, depth or 0
    if p.reply_to and number is None:
        if parent == "missing":
            out["context"] = {"missing": True}
        elif parent is not None:
            out["context"] = {"handle": parent.author.handle, "text": snippet(parent, 140),
                              "id": parent.id}
    return out


# a profile's buttons the page has (common/profile.py): not yet the lists' submenu nor
# the tabs of whom they follow
WEB_PROFILE_ACTS = ("follow", "bell", "boosts", "langs", "mention", "mute", "block",
                    "remove_follower", "endorse", "note", "copy_handle", "open_browser")


class _WebHost:
    """The window common/links.py talks to, for the web: it waits for each future
    here (the request waits with it) and writes down what the page should do."""

    def __init__(self, view, confirmed):
        self.view, self.confirmed, self.out = view, confirmed, {}

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

    def open_thread(self, sid):
        self.out["open"] = {"thread": sid}

    def open_account(self, acc_id):
        self.out["open"] = {"account": acc_id}

    def copy_handle(self, handle):
        self.out["copy"] = "@" + handle.lstrip("@")

    def read_up_to(self, sid):
        self.out["read_up_to"] = sid

    def compose(self, reply_to=None, invite=False, edit=None, quote=None, text=None):
        c = {"text": text} if text else {}
        if edit is not None:
            text, cw = self.view.source(edit).result(timeout=30)
            c = {"edit": edit.id, "text": text, "cw": cw,
                 "visibility": real(edit).visibility}
        elif quote is not None:
            c = {"quote": real(quote).id, "quote_of": "@" + real(quote).author.handle}
        elif reply_to is not None:
            c = {"reply_to": reply_to.id, "invite": bool(invite)}
            if invite:
                c["text"] = "@"
        self.out["compose"] = c

    answer = None

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
        self.version = 0
        self.changed = threading.Condition()
        self.links = {}  # one-time login token -> good until (time.monotonic)
        self._links_lock = threading.Lock()
        for event in ("lanes_updated", "read_changed", "status_updated", "status_deleted",
                      "lists_changed"):
            self.core.on(event, lambda _n, _p: self.bump())
        # the theme's sounds: the page plays them (frontends/soundpack.py)
        self.sound_seq = 0
        self.sound_log = collections.deque(maxlen=8)  # (seq, event)
        self.core.on("sound", lambda _n, p: self.chime(p))

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

    def wait_answer(self, since, sound_since):
        v = self.wait(since)
        sounds, last = self.sounds_since(sound_since)
        return {"v": v, "s": last, "sounds": sounds}

    def bump(self):
        with self.changed:
            self.version += 1
            self.changed.notify_all()

    def wait(self, since, timeout=WAIT_SECONDS):
        with self.changed:
            self.changed.wait_for(lambda: self.version != since, timeout)
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
        me = self.core.me
        return {"me": account_json(me), "handle": me.handle if me else "",
                "version": __version__, "server": (self.core.auth or {}).get("server"),
                "mark_read": c["read"]["mark_read"], "order": c["feed"]["order"],
                "start_at": c["feed"]["start_at"], "expand_cw": config.expand_cw(c),
                "visibility": self.core.default_visibility(),
                "sensitive_media": config.sensitive_media(c),
                "quote_prefix": c["post"].get("quote_prefix", "> "),
                "homepage": version.HOMEPAGE, "help_url": self.help_url(),
                "lang": i18n.current_language(),
                "sound": {"volume": c["sound"]["volume"],
                          "when_focused": c["sound"]["when_focused"]},
                "words": {k: _(k) for k in WORDS}}

    @staticmethod
    def help_url():
        """The help as GitHub shows it, in the interface's language: the page has no
        Markdown of its own (the Qt window shows the same pages offline)."""
        from ..helpdocs import language
        return f"{version.HOMEPAGE}/blob/main/fedtail/data/help/{language()}/index.md"

    def lanes(self):
        from ..tui.model import lane_label, ordered_lanes, start_lane
        out = []
        for group, names in ordered_lanes(self.core):
            for i, name in enumerate(names):
                title, n = lane_label(self.core, name, 60)
                out.append({"name": name, "title": title, "unread": n,
                            "group": group if i == 0 else None})
        first = start_lane(self.core, [x["name"] for x in out])
        for x in out:
            x["start"] = x["name"] == first
        return out

    def _lane_name(self, name):
        from ...core.lanes import canonical
        name = canonical(str(name or ""))  # an old name ("comments") still finds its lane
        if name not in self.core.lane_by_name:
            raise KeyError(name)
        return name

    def lane(self, name):
        name = self._lane_name(name)
        core = self.core
        entries = core.entries(name)  # read only: activate() remembers what's open
        lane = core.lane_by_name[name]
        return {"name": name, "title": core.lane_title(name) or _("lane_" + name),
                "posts": self._posts([e for _i, e in entries],
                                     items=[i for i, _e in entries]),
                "older": bool(lane.source) and not lane.lazy}

    def older(self, name):
        """Older posts of a lane from the server (the "More" at its end)."""
        name = self._lane_name(name)
        return {"n": self.core.load_older(name).result() or 0}

    def activate(self, name):
        """The lane on screen (for notifications and the next start): a POST."""
        name = self._lane_name(name)
        self.core.set_active_lane(name)
        self.core.set_state("lane", name)
        return {"ok": True}

    def thread(self, sid):
        core = self.core
        sid = one_id(sid)
        items = core.thread(sid).result()
        posts = [n.post for n in items]
        short = core.short_ids(posts)
        unread = core.unread(posts)
        return {"focus": sid,
                "posts": [post_json(core, n.post, short.get(n.post.id), n.post.id in unread,
                                    number=n.number, depth=n.depth) for n in items]}

    def account(self, acc_id):
        core = self.core
        acc_id = one_id(acc_id)
        acc = core.account(acc_id).result()
        me = core.me
        try:
            rel = core.relationship(acc_id).result() if not me or acc_id != me.id else None
        except Exception:  # noqa: BLE001 — the profile shows without it
            rel = None
        page = core.account_posts(acc_id).result()
        info = account_json(acc)
        info.update(note=with_emojis(web_clean(acc.note), acc.emojis) if acc else "",
                    header=_https(acc.header_static) if acc else "",
                    counts=" · ".join((_("posts_n", n=acc.posts),
                                       _("followers_n", n=acc.followers),
                                       _("following_n", n=acc.following))) if acc else "",
                    fields=[{"name": f.name, "value": web_clean(f.value),
                             "verified": f.verified is not None}
                            for f in (acc.fields if acc else ())],
                    own=bool(me and acc and acc.id == me.id))
        from ..common import profile as prof
        own = bool(me and acc and acc.id == me.id)
        acts = [{"key": a.key, "label": a.label, "tip": a.tip, "primary": a.primary}
                for a in prof.actions(acc, rel, own, core.cfg, core.supports)
                if a.key in WEB_PROFILE_ACTS] if acc else []
        since = rel is not None and rel.following and core.followed_since(acc_id, rel)
        return {"account": info,
                "relation": {"following": bool(rel and rel.following),
                             "followed_by": bool(rel and rel.followed_by),
                             "requested": bool(rel and rel.requested)},
                "meta": prof.meta(acc, rel, self._date, since or None)[1:] if acc else [],
                "note_line": prof.note_line(rel, own),
                "actions": acts,
                "posts": self._posts(page)}

    @staticmethod
    def _date(when):
        return when.astimezone().strftime("%d.%m.%Y") if when else ""

    def profile_act(self, acc_id, key, answer=None, confirmed=False):
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
        prof.do(key, acc, rel, core, host, lambda _r: host.out.setdefault("refresh", True))
        if host.out.get("error"):
            raise ValueError(host.out["error"])
        return host.out

    def _post_by_id(self, sid):
        p = self.core.by_id(one_id(sid))
        if p is None:
            raise KeyError(sid)
        return p

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
        what is offered, when, in which order) — the page only lays them out. Items
        the page can't do yet (a list's submenu, as another account, the whole text,
        translation) are left out."""
        from ..common import actions
        core = self.core
        p = self._post_by_id(sid)
        me = core.me
        cfg = core.cfg
        ctx = actions.Ctx(cfg=cfg, me_id=me.id if me else None, supports=core.supports,
                          subscribed=core.subscribed, thread_quiet=core.thread_quiet,
                          quote_reply=bool(cfg["post"].get("quote_prefix", "> ")))
        short = core.short_ids([p]).get(real(p).id)
        unread = p.id in core.unread([p])
        items = []
        for it in actions.menu(p, ctx, short, unread):
            if it.kind in ("link", "open", "copy", "separator", "quote_reply"):
                items.append({"kind": it.kind, "label": it.label, "url": it.url,
                              "text": it.text})
        while items and items[0]["kind"] == "separator":
            items.pop(0)
        return {"subscribed": core.subscribed(p), "muted": core.thread_quiet(p),
                "own": bool(me and real(p).author.id == me.id), "items": items}

    def link(self, url, confirmed=False):
        """A fedtail: link from the ⋯ menu, done the way every window does it
        (common/links.py); what the page must do then comes back: a message, a
        question first ("sure?" — asked again with confirmed), a place to open, the
        editor to fill, text to copy."""
        from ..common.links import Links
        host = _WebHost(self.core, confirmed)
        Links(self.core, host).open(str(url or ""))
        if host.out.get("error"):
            raise ValueError(host.out["error"])
        return host.out

    def thread_act(self, action, sid):
        """Subscribe to, leave, mute or unmute the thread a post is in."""
        core = self.core
        p = self._post_by_id(sid)
        if action in ("sub", "unsub"):
            (core.subscribe if action == "sub" else core.unsubscribe)(p).result()
            return {"message": _("subbed" if action == "sub" else "unsubbed")}
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
            p = core.edit(self._post_by_id(body["edit"]), text, cw).result()
            return {"id": p.id if p else None, "url": p.url if p else "", "edited": True}
        parent = self._post_by_id(body["reply_to"]) if body.get("reply_to") else None
        vis = body.get("visibility") or core.reply_visibility(parent)
        if vis == "private":  # the API's word, from an older page
            vis = "followers"
        if vis not in ("public", "unlisted", "followers", "direct"):
            raise ValueError(vis)
        lang = (body.get("lang") or "").strip() or None
        p = core.post(text, vis, parent, cw, language=lang,
                      quote=str(body["quote"]) if body.get("quote") else None).result()
        return {"id": p.id if p else None, "url": p.url if p else ""}

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
         "web_reply_to", "web_cancel", "web_cmd", "web_visibility", "vis_public",
         "vis_unlisted", "vis_private", "vis_direct", "web_media", "web_sensitive",
         "web_parent_gone", "web_mark_read", "tui_profile", "open_browser", "refresh",
         "more", "no_older", "poll_vote", "poll_voted", "cw_placeholder", "cw_add",
         "web_new_post", "web_original", "web_close", "web_lanes", "web_edited",
         "web_requested", "lang_label",
         "reply_quote", "quote_in_reply", "sub_thread", "unsub_thread", "mute_thread",
         "unmute_thread", "copy_link", "delete", "delete_q", "help_title", "about",
         "edit", "quote",
         "my_profile", "web_more", "web_menu", "web_keys", "web_keys_text", "web_copied",
         "web_about")


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
        routes = {"/api/me": lambda: self.web.me(),
                  "/api/lanes": lambda: self.web.lanes(),
                  "/api/lane": lambda: self.web.lane(q.get("name", "")),
                  "/api/thread": lambda: self.web.thread(q.get("id", "")),
                  "/api/account": lambda: self.web.account(q.get("id", "")),
                  "/api/post_menu": lambda: self.web.post_menu(q.get("id", "")),
                  "/api/wait": lambda: self.web.wait_answer(
                      _int(q.get("v"), -1), _int(q.get("s"), -1))}
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
            "/api/read": lambda: (web.core.mark_read([str(i) for i in body.get("ids", [])
                                                      ][:500]), {"ok": True})[1],
            "/api/act": lambda: web.act(body.get("action"), str(body.get("id"))),
            "/api/vote": lambda: web.vote(str(body.get("id")), body.get("choices")),
            "/api/older": lambda: web.older(body.get("name")),
            "/api/follow": lambda: web.follow(str(body.get("id")), body.get("on")),
            "/api/post": lambda: web.post(body),
            "/api/command": lambda: web.command(str(body.get("line", "")),
                                                body.get("confirm") is True),
            "/api/active": lambda: web.activate(body.get("name")),
            "/api/resolve": lambda: web.resolve(str(body.get("url", ""))),
            "/api/thread_act": lambda: web.thread_act(body.get("action"), str(body.get("id"))),
            "/api/delete": lambda: web.delete(str(body.get("id"))),
            "/api/link": lambda: web.link(str(body.get("url", "")),
                                          bool(body.get("confirmed"))),
            "/api/profile_act": lambda: web.profile_act(
                str(body.get("id", "")), str(body.get("key", "")),
                body.get("answer") if isinstance(body.get("answer"), str) else None,
                bool(body.get("confirmed"))),
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
