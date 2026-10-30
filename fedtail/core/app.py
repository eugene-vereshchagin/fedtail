"""Core: everything a frontend needs, no GUI.

Network calls return concurrent.futures.Future. Events are emitted from
worker threads (see events.py):

  ready            me (account dict)        connected and ready
  lanes_updated    {lane: [new item ids]}   something new arrived / older loaded
  parents          None                     reply contexts became available
  arrived          [(id, in_reply_to_id)]   new posts from a poll
  announcements_updated n                   the server's announcements changed
  thread_grew      root id                  an opened thread got replies (other servers,
                                            a round, mine sent): its tab reloads
  status_updated   status                   a status changed (fav, boost…)
  status_deleted   status id
  read_changed     [status ids]
  requests_updated [accounts]
  notify           [(lane, status)]         new unread comments / mentions
  error            str
  auth_failed      str                      token no longer accepted
"""

import json
import logging
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import requests

from .. import diag
from ..version import USER_AGENT
from . import (
    atoms,
    auth,
    custom,
    lanes,
    langs,
    proto,
    remote,
    search,
    sources,
)
from .activity import ActivityMixin
from .counts import CountsMixin
from .events import Events
from .lists import ListsMixin
from .markers import MarkersMixin
from .model import real
from .origin import OriginMixin
from .people import PeopleMixin
from .poll import PollMixin
from .proto import Capabilities
from .proto import Error as ApiError  # the protocol's error answer (core/proto.py)
from .push import PushMixin
from .silence import SilenceMixin
from .social import SocialMixin
from .sounds import Chime
from .store import Store, now_iso
from .syncing import SyncMixin
from .thread_ops import ThreadsMixin
from .translate import TranslateMixin
from .writing import WritingMixin

log = logging.getLogger(__name__)

FILTER_WINDOW = 2000
KEEP_FLOOR = 300  # under size pressure a lane is never cut below this many entries


def next_keep(size_mb, max_mb, keep, wanted):
    """How many entries a lane keeps next, after a gc left the store at size_mb: over
    the budget — 30 % fewer (not below KEEP_FLOOR); well under it (60 %) — back up
    towards what the config wants; else as it is."""
    if size_mb > max_mb:
        return max(min(KEEP_FLOOR, wanted), int(keep * 0.7))
    if size_mb < max_mb * 0.6 and keep < wanted:
        return min(wanted, max(keep + 1, int(keep * 1.3)))
    return min(keep, wanted)




class Pool(ThreadPoolExecutor):
    """A pool that, once shut down, takes no more work quietly: a late job (a window
    timer, a badge count at exit) gets a cancelled future instead of RuntimeError."""

    def submit(self, fn, /, *args, **kwargs):
        try:
            return super().submit(fn, *args, **kwargs)
        except RuntimeError:
            if not self._shutdown:
                raise
            from concurrent.futures import Future
            fut = Future()
            fut.cancel()
            return fut

    def join(self, deadline):
        """Wait for running jobs until deadline (time.monotonic)."""
        for t in list(getattr(self, "_threads", ())):
            t.join(max(0.0, deadline - time.monotonic()))


class OtherAccount(ValueError):
    """Logging in anew brought another account than this profile's: nothing saved.
    The message is PREFIX + "@acct" (results reach the window as text)."""
    PREFIX = "other account: "



COUNT_SORTS = ("replies", "likes", "boosts", "density")  # a lane's sort by counts


def _when_of(st):
    """The time a lane's window looks at: the boost's, else the post's."""
    from .atoms import _when
    return _when(st.get("created_at")) or _when(real(st).get("created_at"))


def _author_of(st):
    return ((real(st).get("account") or {}).get("id")) or ""


def _per_author(entries, n):
    """At most n entries of one author — the newest n (entries in the lane's order,
    oldest first)."""
    seen, out = {}, []
    for e in reversed(entries):
        a = _author_of(e[1])
        seen[a] = seen.get(a, 0) + 1
        if seen[a] <= n:
            out.append(e)
    out.reverse()
    return out


def _bundled(entries, oldest_first):
    """Each author's posts together (in their own order), the authors by how many they
    have — the busiest where reading starts (the top: oldest_first lists top-down,
    newest_first is turned round by the window)."""
    groups = {}
    for e in entries:
        groups.setdefault(_author_of(e[1]), []).append(e)
    newest = {a: max(str(x[1].get("created_at") or "") for x in g) for a, g in groups.items()}
    order = sorted(groups, key=lambda a: (len(groups[a]), newest[a]), reverse=True)
    if not oldest_first:
        order.reverse()
    return [e for a in order for e in groups[a]]


def _within(entries, seconds):
    from datetime import UTC, datetime, timedelta
    cutoff = datetime.now(UTC) - timedelta(seconds=seconds)
    return [e for e in entries if (_when_of(e[1]) or cutoff) >= cutoff]


def _by_counts(entries, how, oldest_first):
    """By replies / likes / boosts, or "density" — all three per hour of its age; the
    best where reading starts (the top: oldest_first lists top-down, newest_first is
    turned round by the window)."""
    from datetime import UTC, datetime

    def score(e):
        p = real(e[1])
        n = {"replies": p.get("replies_count"), "likes": p.get("favourites_count"),
             "boosts": p.get("reblogs_count")}
        if how != "density":
            return int(n[how] or 0)
        total = sum(int(v or 0) for v in n.values())
        when = _when_of(e[1])
        hours = max(1.0, (datetime.now(UTC) - when).total_seconds() / 3600) if when else 1.0
        return total / hours
    return sorted(entries, key=score, reverse=oldest_first)


def _filter_hits(st, filters):
    """The server's filters whose words this post has (its text and content warning)."""
    import re
    from html import unescape
    text = unescape(re.sub(r"<[^>]+>", " ", st.get("content") or "")) + " " + \
        (st.get("spoiler_text") or "")
    low = text.lower()
    out = []
    for f in filters:
        for k in f.get("keywords") or ():
            word = str(k.get("keyword") or "").lower()
            if not word:
                continue
            if k.get("whole_word") and re.search(rf"(?<!\w){re.escape(word)}(?!\w)", low) or \
                    not k.get("whole_word") and word in low:
                out.append(f)
                break
    return out

class Core(WritingMixin, ThreadsMixin, PeopleMixin, PollMixin, MarkersMixin, PushMixin,
           CountsMixin,
           OriginMixin, SyncMixin, ActivityMixin, ListsMixin, SilenceMixin, TranslateMixin,
           SocialMixin):
    """The core the frontends talk to: one account, its store, its rounds. Its parts
    live in modules of their own, mixed in here — poll.py (the rounds, the stream),
    people.py, thread_ops.py, writing.py, silence.py, lists.py, activity.py, syncing.py,
    origin.py, translate.py, push.py, markers.py, social.py — and this file keeps the
    connection, the lanes (their rules, reading them, the notifications) and the rest."""


    def __init__(self, cfg, paths, api_class=None):
        self.cfg = cfg
        self.paths = paths
        langs.configure(cfg["lanes"].get("detect_among", "auto"))  # before any guess
        # what this account's server speaks (docs/en/dev/protocols.md): the client, its errors,
        # its live stream, its objects → fedtail.model
        self.proto = proto.PROTO  # the protocol this core speaks (core/proto.py)
        self.api_class = api_class or self.proto.client
        paths.ensure()
        self.store = Store(paths.db_file)
        self.events = Events()
        # user actions never wait behind background work
        self.pool = Pool(max_workers=4, thread_name_prefix="fedtail")
        self.bg = Pool(max_workers=2, thread_name_prefix="fedtail-bg")
        # after read marks: the lanes' counts made anew here, not in a window (mark_read)
        self.reads = Pool(max_workers=1, thread_name_prefix="fedtail-read")
        self.auth = auth.load(paths.auth_file)
        self.api = None
        self.me = None
        # read marks, thread states and my lanes' arrangement shared with the account's
        # other devices (sync.*): on when sync.url or sync.folder says where they meet;
        # recorded whenever it is on, sent by the thread polling starts
        self.sync = None
        from .sync.engine import wanted
        if wanted(cfg):
            from .sync import Sync
            self.sync = Sync(self)
        self._note_lane_rules()  # the lanes changed in the file since: they go out
        from .derived import Derived
        self.derived = Derived(self)  # who stopped following me (activity.unfollows)
        from .wider import Wider
        self.wider = Wider(self)  # other servers' lanes into mine (lanes.*_extra)
        self._relations = {}  # acc_id -> (when, relationship), see relation_known
        self.caps = Capabilities()
        self._silence_seen = {}  # status id -> muted thread's root or None (_mention_entry)
        self._conv_of = {}        # last status id -> (conversation id, unread on the server)
        self.server_prefs = {}    # what I set on the server's web side (its preferences)
        self.translation_languages = None  # {source: [targets]} its translator can do
        self._browse_extra = {}  # browse source → (posts kept beyond browse_keep, pages asked)
        self.browse_empty = set()  # browse sources (local, federated) the server gave nothing
        self.sources = {}
        self.lists = []           # [{"id", "title", "exclusive"}] from the server
        self.list_members = {}    # list id -> {account ids}
        self._lists_version = 0
        self._lists_checked = None  # monotonic time of the last check; None: never
        self._announced_at = None   # poll.announcements_minutes: asked last (monotonic)
        self._announced_sig = None
        self.customs = custom.load(cfg)[0]  # free lanes, [[lanes.custom]]
        self._following = None    # account ids I follow, for the free lanes' atoms
        self._world_version = 0   # bumped when what the rules know around posts changes
        self._following_at = 0.0
        self._waiting = {}  # lanes on but hidden while empty (_shown_lanes): name → Lane
        self._server_filters = []        # the server's filters (v2), for filter_context
        self._unsorted_on = False        # lanes.unsorted: Unsorted collects
        self.lanes = self._shown_lanes(lanes.enabled(cfg))
        self.tag_groups = []  # [{"any", "all", "none", "name", "saved"}], see taggroups
        self.lane_by_name = {lane.name: lane for lane in self.lanes}
        self.follow_requests = []
        self._limits = {}
        self._horizons = {}  # lane → how many stored items its window looks through
        self._lane_deep = {}  # lane → its store had more than was looked through
        self.chime = Chime(cfg, chosen=self.lane_chosen, event_of=self.lane_sound)
        self._lane_cache = {}
        self._opened_threads = {}  # root id -> when it was opened (thread recheck)
        self._rechecked = {}       # root id -> when it was asked again
        self._pending_login = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._poll_lock = threading.Lock()
        self._poller = None
        self._parent_inflight = set()
        self.new_options = []  # options the user's config doesn't mention yet
        self._replies_inflight = set()
        self._known_requests = None  # follow requests seen so far (None: not fetched yet)
        # what the last update that brought anything brought, per lane: {lane: {item id}}
        # (activity: notification ids, requests: account ids) — "of them new N" on a tile
        self._fresh = {}
        # a lane's news held back by its "notify at most every N minutes": {lane: [st]}
        self._held = {}
        self._calm_last = {}  # lane -> time.time() its news last came out
        self._next_round = None  # slow mode: time.time() of the next round
        self._honest_checked = {}  # status id -> when its origin was asked
        self._completed = {}  # thread root id -> when its missing replies were looked for
        self._choices = {}  # this run's choices over lanes (see choice())
        self.muted, self.blocked = set(), set()
        self.hidden_posts = set()  # "Hide this post": out of sight at once, not on the next fetch
        self.blocked_domains = set()
        self._silence_version = 0
        self._silence_checked = None
        self._gc_done = None  # monotonic time of the last store gc; None: not this run
        self._poll_count = 0
        # starting: from here until the first round ends (or connecting fails) the lanes
        # are being got — busy for poll_state, so the curtain's opossum swings from the
        # window's first frame, not only once polling begins
        self._starting = self.auth is not None  # (logged out: the login comes first)
        self._active_lane = None  # the lane on screen: browse lanes are fetched only then
        self._active_lanes = set()  # all of them on screen, side by side (ui.layout)
        self._last_poll_s = None
        self._poll_failures = 0     # for the federation status
        self._hand_waiting = []     # Refresh presses waiting for their round (poll.py)
        self._hand_lock = threading.Lock()
        self._last_poll_ok = None   # time.time()
        self._last_poll_error = ""
        proto.PROTO.tune(slow_seconds=cfg["debug"]["slow_request_seconds"])
        diag.add_stats("core", self.diag_stats)

    # ---- plumbing ------------------------------------------------------------
    def submit(self, fn, *a, **kw):
        return self.pool.submit(fn, *a, **kw)

    def call_api(self, name, *a, **kw):
        """The server's `name`(…) in the pool. Before the connection is made (a profile
        or a tag opened while still connecting) the future fails with "connecting…",
        instead of an AttributeError in the window's own thread."""
        def go():
            if self.api is None:
                from ..i18n import _
                raise ApiError(0, _("connecting"))
            return getattr(self.api, name)(*a, **kw)
        return self.pool.submit(go)

    ERROR_QUIET_S = 600

    def emit(self, name, payload=None):
        if name == "error":
            # the same error from every poll while a server is down: shown and logged
            # once, again only when it changes or after ERROR_QUIET_S of it
            now = time.monotonic()
            seen = getattr(self, "_errors_seen", None)
            if seen is None:
                seen = self._errors_seen = {}
            if "HTTP 429" in str(payload):
                # the server asks to wait: said once by rate_limited, not lane by lane
                log.info("rate limited: %s", str(payload)[:200])
                return
            # one failure each time: not told apart by an object's address in its words
            key = re.sub(r" at 0x[0-9a-f]+", "", str(payload))
            last = seen.get(key)
            if last is not None and now - last < self.ERROR_QUIET_S:
                log.debug("error again (not shown): %s", str(payload)[:200])
                return
            seen[key] = now
            if len(seen) > 200:
                seen.clear()
            log.warning("error shown to the user: %s", payload)
        else:
            log.debug("event %s", name)
            self._warm_if_changed()
        self.events.emit(name, payload)

    def _warm_if_changed(self):
        """An event from a background thread after the stored posts changed (a thread
        loaded, a post favourited, a boost's count): the lanes counted anew here, before
        the window hears — it recounts every lane on most events, and did it itself
        between two frames (the freezes of 300–600 ms on activity_seen and read_changed
        after a thread came in, 26.10)."""
        if threading.current_thread() is threading.main_thread():
            return  # the window's own act: counting here is counting there
        store = getattr(self, "store", None)
        if store is None or not getattr(self, "lanes", None) or getattr(self, "_warming", 0):
            return
        try:
            key = (store.status_version, tuple(sorted(store.items_version.items())))
        except Exception:  # noqa: BLE001 — a store without versions (a test's fake)
            return
        if key == getattr(self, "_warmed_at", None):
            return
        self._warming = 1
        try:
            self._warm_lanes()
        finally:
            self._warming = 0

    @property
    def logged_in(self):
        return self.auth is not None

    @property
    def markdown(self):
        mode = self.cfg["account"]["markdown"]
        return self.caps.markdown if mode == "auto" else mode == "on"

    # ---- login -----------------------------------------------------------------
    def set_proxy(self, proxy):
        """net.proxy, typed at login (net.proxy_at_login): written into config.toml and
        used at once — the login itself goes through it. "" — none."""
        from . import config, config_edit
        proxy = str(proxy or "").strip()
        if not config.proxy_ok(proxy):
            from ..i18n import _
            raise ValueError(_("proxy_bad", proxy=proxy))
        if proxy == str(self.cfg["net"].get("proxy") or ""):
            return
        config_edit.save(self.paths.config_file, {("net", "proxy"): proxy})
        self.cfg["net"]["proxy"] = proxy
        config.apply_proxy(self.cfg)
        log.info("proxy %s", "set" if proxy else "off")  # not the address: it may hold a password

    def begin_login(self, server, redirect=None, proxy=None):
        """→ the server's page where the user allows fedtail. redirect: where the server
        sends the code — None: it shows it to be pasted (the desktop); an app's address
        (fedtail://oauth on a phone): it goes straight back to the app. proxy: what the
        login window's proxy field holds (net.proxy_at_login), None — no such field."""
        def job():
            from ..i18n import _
            if proxy is not None:
                self.set_proxy(proxy)
            try:  # "social,example", " social.example ", @me@host, a link: the server's address
                where = proto.address(server)
            except ValueError:
                raise ValueError(_("login_bad_server", server=str(server).strip())) from None
            if not remote.cleartext_ok(where):
                # the token would cross the internet in the clear: only a server here,
                # at home (localhost, a private address, .local/.lan) may be http://
                raise ValueError(_("login_insecure"))
            api = self.api_class(where)
            back = {"redirect": redirect} if redirect else {}
            host = where.split("://", 1)[-1]
            try:
                app = api.register_app(**back)
            except requests.ConnectionError as e:  # no such name, no answer, refused
                log.info("login: %s unreachable: %s", host, e)
                raise ValueError(_("login_unreachable", host=host)) from None
            except requests.Timeout:
                raise ValueError(_("login_timeout", host=host)) from None
            except ApiError as e:
                # a site, but no fediverse server there: no such page, or not JSON (a
                # typo's parked domain); a refusal of the app (422: the redirect) stays
                if e.status < 400 or e.status in (404, 405, 410, 501):
                    log.info("login: %s is no server: %s", host, e)
                    raise ValueError(_("login_not_server", host=host)) from None
                raise
            self._pending_login = (api, app, back)
            auth.save(self.paths.login_file, {"server": api.base, "app": app, "back": back,
                                              "at": time.time()})
            return api.authorize_url(app["client_id"], **back)
        return self.submit(job)

    def _login_under_way(self):
        """(api, app, back) of the login begun — this run's, or one an earlier run began
        (a phone kills the app while the browser is out) within the hour; None."""
        if self._pending_login is not None:
            return self._pending_login
        try:
            data = json.loads(self.paths.login_file.read_text("utf-8"))
            if time.time() - float(data["at"]) < 3600:
                return (self.api_class(data["server"]), data["app"], data["back"])
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def finish_login(self, code, expect=None):
        """expect: (server, acct) this profile already is — logging in anew must not
        put another account into its data (read marks, drafts, lists are that one's)."""
        def job():
            begun = self._login_under_way()
            if begun is None:
                from ..i18n import _
                raise ValueError(_("login_not_begun"))
            api, app, where = begun
            token = api.get_token(app["client_id"], app["client_secret"], code, **where)
            me = self.api_class(api.base, token).me()
            if expect and (api.base.rstrip("/"), me["acct"]) != \
                    (expect[0].rstrip("/"), expect[1]):
                log.warning("login anew: another account, not saved")
                raise OtherAccount(f"{OtherAccount.PREFIX}@{me['acct']}")
            data = {"server": api.base, "client_id": app["client_id"],
                    "client_secret": app["client_secret"], "token": token, "acct": me["acct"]}
            old = self.auth
            auth.save(self.paths.auth_file, data)
            self.auth = data
            self._pending_login = None
            auth.forget(self.paths.login_file)  # done: its secret has no more use
            if old and old.get("token") != token and \
                    old.get("server", "").rstrip("/") == api.base.rstrip("/"):
                self._revoke(old, wait=True)  # logged in anew: the old token is let go
            return me
        return self.submit(job)

    def logout(self):
        """The token off this computer and, best effort, dead on the server too: a copy of
        auth.json left in a backup is worth nothing then."""
        old = self.auth
        auth.forget(self.paths.auth_file)
        self.auth = None
        self.api = None
        if old:
            self._revoke(old)

    def _revoke(self, data, wait=False):
        def job():
            try:
                self.api_class(data["server"]).revoke(data.get("client_id", ""),
                                                      data.get("client_secret", ""),
                                                      data["token"])
                log.info("token revoked on the server")
            except Exception as e:  # noqa: BLE001 — offline, or a server without it
                log.warning("token not revoked on the server: %s", e.__class__.__name__)
        if wait:
            job()
        else:  # not a daemon: a window closing right after still lets it finish
            threading.Thread(target=job, name="fedtail-revoke").start()

    # ---- connect & poll ----------------------------------------------------------
    def _own_software(self, caps):
        """The instance document only guessed what my server runs (a bare version
        number): its nodeinfo says for sure — GoToSocial can't dismiss one notification,
        mute a thread on the server…, and the core must know."""
        if caps.software_sure:
            return
        from urllib.parse import urlparse
        host = urlparse(self.auth["server"]).hostname or ""
        try:
            name = self.server_software(host).result(timeout=10)
        except Exception as e:  # noqa: BLE001 — a guess stays a guess
            log.debug("own nodeinfo: %s", e)
            return
        sw = name.split()[0].lower() if name else ""
        if sw:
            if sw != caps.software:
                log.info("server software: %s (the instance document said only %r)",
                         sw, caps.version)
            caps.software, caps.software_sure = sw, True

    def _carry_answers(self, old, new):
        """What the server answered about its features stays across a reconnect to the
        same server; the last probe (kept) speaks for the same software and version."""
        if old.same_server(new.software, new.version):
            new.missing |= old.missing
            new.present |= old.present
        probe = proto.probe
        last = self.store.kv_get(probe.KV)
        if isinstance(last, dict) and new.same_server(last.get("software"),
                                                       last.get("version")):
            for feature, there in probe.features(last).items():
                if feature not in new.missing and feature not in new.present:
                    new.learn(feature, there)

    def connect(self):
        def job():
            if not getattr(self, "_poll_count", 0):  # (connecting anew later: not starting)
                self._starting = True
                self.emit("poll_state", True)
            try:
                return connect()
            except BaseException:
                self._starting = False  # nothing is coming: the opossum stands still
                self.emit("poll_state", False)
                raise

        def connect():
            if not remote.cleartext_ok(self.auth["server"]):
                # a login of long ago to a plain http:// server on the internet: the token
                # isn't sent in the clear — log in anew with https:// (as a login refuses)
                from ..i18n import _
                log.warning("server is plain http on the internet: the token is not sent "
                            "(log in anew with https://)")
                raise ValueError(_("login_insecure"))
            api = self.api_class(self.auth["server"], self.auth["token"])
            me = api.me()
            try:  # the newer document apart: its trouble mustn't cost the older one's facts
                v2 = api.instance_v2() if hasattr(api, "instance_v2") else None
            except Exception as e:  # noqa: BLE001 — a timeout, a broken answer
                log.info("instance v2: %s: %s", type(e).__name__, e)
                v2 = None
            try:
                caps = self.proto.capabilities(api.instance(), v2)
            except Exception as e:  # instance info is a nicety, not a must
                log.warning("instance: %s: %s — the server's limits and features unknown",
                            type(e).__name__, e)
                caps = Capabilities()
            self._own_software(caps)
            self._carry_answers(self.caps, caps)
            self.api, self.me, self.caps = api, me, caps
            self.store.me_id = (me or {}).get("id")  # my posts are read, however they come
            n = self.store.mark_mine_read()
            if n:
                log.info("read: %d posts of mine were unread (written elsewhere)", n)
            self.load_preferences()
            self.load_translation_languages()
            from . import profiles
            profiles.remember(self.paths, me, self.auth["server"])  # for the switcher
            self.sources = sources.make_sources(api, me["id"])
            self.sources.update(sources.wider_sources(api, self.cfg["lanes"].get("bubble")))
            self._silence_seen = {}
            self.sources["mentions"].entry = self._mention_entry
            done = False
            if self.cfg["lists"]["enabled"]:
                try:
                    self._refresh_lists()
                    done = True
                except Exception as e:  # lists are a nicety; the rest must start
                    log.warning("lists: %s", e)
            if not done and (self.cfg["lanes"].get("tag_groups") or
                             self.store.kv_get("tag_groups")):
                self._apply_lists([], {})  # the tag lanes come all the same
            self.emit("ready", me)
            self.sound_moment("online")
            return me
        return self.submit(job)

    # ---- slow mode: the news comes once every N minutes, not as it arrives ------------
    # ---- "notify at most every N minutes", a lane's own -------------------------------
    # ---- "of them new": what the last update brought, still unread ---------------------
    def fresh_count(self, name):
        """How many of a lane's unread came with the last update that brought anything."""
        got = self._fresh.get(name)
        if not got:
            return 0
        if self._events_only(name):
            seen = self.activity_seen_mark()
            return sum(1 for n in self.lane_events(name, 1000)
                       if str(n.get("id")) in got and str(n.get("sort") or "") > seen)
        entries = [e for e in self.lane_entries(name) if e[0] in got]
        if not entries:
            return 0
        unread = self.unread_ids(entries)
        if self._by_thread(name):  # a card a thread: the threads the news came to
            return self._threads_of([e for e in entries if e[1]["id"] in unread])
        return len(unread)

    def _by_thread(self, name):
        """A lane that shows a card a thread (view = "threads": "Commented posts"): its
        number counts threads with news, as many as the cards — not every comment."""
        return getattr(self.lane_by_name.get(name), "view", "") == "threads"

    def _threads_of(self, entries):
        """How many threads these lane entries belong to (core/threads.py: by the
        highest post known of each), the way the lane draws them."""
        from .threads import conversations
        return len(conversations(entries, self.store.get_status, set()))

    # ---- keeping the store in bounds ([storage]) -----------------------------------
    def keep_per_lane(self):
        """Entries each lane keeps: storage.keep_per_lane, less while the store is
        over storage.max_mb (collect_garbage lowers it, and raises it back later)."""
        wanted = max(KEEP_FLOOR, self.cfg["storage"]["keep_per_lane"])
        keep = self.store.kv_get("storage.keep")
        return min(wanted, keep) if isinstance(keep, int) and keep > 0 else wanted

    def collect_garbage(self):
        """Forget posts nothing points at (Store.gc); over the size budget, cut every
        lane shorter and collect again, until it fits or lanes reach KEEP_FLOOR."""
        self._gc_done = time.monotonic()
        sc = self.cfg["storage"]
        wanted = max(KEEP_FLOOR, sc["keep_per_lane"])
        try:
            t = time.monotonic()
            total = self.store.gc(sc["keep_activity"], sc["grace_hours"])
            size, keep = self.store.size_mb(), self.keep_per_lane()
            while True:
                nxt = next_keep(size, sc["max_mb"], keep, wanted)
                if nxt == keep:
                    break
                keep = nxt
                self.store.kv_set("storage.keep", keep)
                if size <= sc["max_mb"]:
                    break  # only growing back: the lanes fill up again by themselves
                for source in self.store.item_sources():
                    self.store.prune(source, keep)
                more = self.store.gc(sc["keep_activity"], sc["grace_hours"], drop_read=True)
                total = {k: total.get(k, 0) + more.get(k, 0) for k in {*total, *more}}
                size = self.store.size_mb()
                if keep <= KEEP_FLOOR:
                    break
            log.info("storage gc: %s; %.1f MB of %d, %d per lane, %.2f s",
                     {k: v for k, v in sorted(total.items()) if v} or "nothing",
                     size, sc["max_mb"], keep, time.monotonic() - t)
            if size > sc["max_mb"]:
                log.warning("storage: still %.1f MB after gc (budget %d MB)", size,
                            sc["max_mb"])
        except Exception as e:  # noqa: BLE001 — a failed gc must never stop the poll
            log.warning("storage gc: %s", e, exc_info=True)

    # ---- read position shared with other clients (markers) -------------------------
    NO_SUCH = (404, 405, 410, 501)  # a server's "no such thing here"

    def _new_statuses(self, new_by_source):
        out = []
        for name, ids in new_by_source.items():
            if not ids:
                continue
            id_set = set(ids)
            out += [st for item_id, st in self.store.items(name, len(ids) + 50)
                    if item_id in id_set]
        return out

    def _note_fresh(self, per_lane, new_requests, new_activity):
        """The last update that brought anything: what it brought, lane by lane."""
        got = {name: set(ids) for name, ids in per_lane.items() if ids}
        for name, events in self._events_by_lane(new_requests, new_activity).items():
            got[name] = {str(n.get("id")) for n in events}
        if got:
            self._fresh = got

    # lanes shown only while something is in them — Unsorted, and any lane whose rule says
    # `hide_empty = true` ("Important people" in the fedtail set): their stream decides
    # (still filled while hidden — once there is, they show, lists_changed redraws)
    def _shown_lanes(self, built):
        """The lanes as built, without those that wait for something to show."""
        self._waiting = {x.name: x for x in built
                         if (x.name == lanes.UNSORTED or getattr(x, "hide_empty", False))
                         and x.source and self.store.count_items(x.source) == 0}
        self._unsorted_on = any(x.name == lanes.UNSORTED for x in built)
        return [x for x in built if x.name not in self._waiting]

    def _waiting_sources(self):
        """What the lanes waiting to have something are filled from: fetched as the
        shown ones' are, or they'd never fill."""
        return [s for x in self._waiting.values() for s in (x.source, *(x.feeds or ()))
                if s and s != lanes.UNSORTED]

    def _show_important(self):
        """A lane waiting to have something has it now: the lanes anew. (One emptied
        stays till the next start: a lane must not vanish under the reader.)"""
        if any(self.store.count_items(x.source) for x in self._waiting.values()):
            self._apply_lists(list(self.lists), self.list_members)

    # ---- free lanes (core/custom.py) ---------------------------------------------------
    def _world(self):
        """What the free lanes' atoms know around a post (core/atoms.World)."""
        store = self.store

        class _Read:
            def __contains__(self, sid):
                return bool(store.read_set([sid]))

        class _Parents:
            def get(self, pid, default=None):
                got = store.get_statuses({pid}).get(pid)
                if got is None and store.missing_set({pid}):
                    return "missing"
                return got if got is not None else default

        class _News:  # asked only when a rule needs it: one query, then kept
            got = None

            def __contains__(self, sid):
                if self.got is None:
                    self.got = store.threads_with_news()
                return sid in self.got

        core = self

        class _Subscribed:  # state = "subscribed": the post is in a followed thread
            def __contains__(self, sid):
                return core.followed_root(sid) is not None

        class _MyThreads:  # me = "in_my_thread": a thread I wrote in, followed or not
            def __contains__(self, sid):
                return core.in_my_thread(sid)

        lc = self.cfg["lanes"]
        host = urllib.parse.urlsplit(getattr(self.api, "base", "") or "").hostname or ""
        return atoms.World(me_id=self.me["id"] if self.me else "", my_host=host,
                           subscribed=_Subscribed(), my_threads=_MyThreads(),
                           following=self._following or set(),
                           followed_tags=getattr(self, "_followed_tag_names", None) or set(),
                           extra_bots=tuple(lc["extra_bots"]), read=_Read(),
                           parents=_Parents(), new_replies=_News(),
                           deleted=store.deleted_set(),
                           hidden_home=set(store.kv_get("people.hidden_home", []) or ()),
                           detect=lc["detect_language"],
                           min_words=lc["detect_min_words"])

    def _route_custom(self, new_by_source):
        """The new items of the real sources into the free lanes that take them; a new
        lane, or one whose rule changed, filled from what is stored. {lane: [new ids]}."""
        if not self.customs or not self.me:
            return {}
        self._refresh_following()  # rules ask whom I follow (Home's "Tags", author = …)
        world = self._world()
        refilled = {}
        for c in self.customs:
            if c.routed and custom.stale(self.store, c):
                custom.backfill(self.store, c, world)
                refilled[c.name] = []
        got = custom.route(self.store, self.customs, new_by_source, world)
        for name in got:
            self.store.prune(name, self.keep_per_lane())
        if self._unsorted_on:  # lanes.unsorted (shown or waiting to have something)
            # what a lane has taken since (a list's, a tag lane's): out of Unsorted
            if self.store.drop_held(lanes.UNSORTED,
                                    {x.source for x in self.lanes if x.source}) and \
                    lanes.UNSORTED in self.lane_by_name:
                # left it: the lane and its number on the sidebar must hear (27.10: "12",
                # and nothing in it)
                refilled[lanes.UNSORTED] = []
            taken = {sid for name in got for sid in got[name]}
            left = custom.unsorted(self.store, self.lanes, new_by_source, self._ctx(), taken)
            if left:
                got[lanes.UNSORTED] = left
                self.store.prune(lanes.UNSORTED, self.keep_per_lane())
        if refilled:
            self.emit("lanes_updated", refilled)  # filled anew: the lanes look again
        return got

    def _split_by_lane(self, new_by_source):
        ctx = self._ctx()
        per_lane = {}
        for lane in self.lanes:
            ids = set(new_by_source.get(lane.source) or ())
            if not ids:
                continue
            per_lane[lane.name] = [item_id for item_id, st
                                   in self.store.items(lane.source, len(ids) + 50)
                                   if item_id in ids and lanes.keeps(lane, st, ctx)]
        return per_lane

    def _notify(self, per_lane, new_requests=(), new_activity=()):
        """Emit 'notify' with [(lane, status-or-account)] for lanes the user wants, and
        'sound' with the event a batch's news makes (core/sounds.py)."""
        wanted = set(self.cfg["notify"]["lanes"])
        never = set(self.cfg["notify"].get("except") or ())
        out, quiet, fresh = [], [], []
        for name, ids in per_lane.items():
            lane = self.lane_by_name[name]
            if not ids:
                continue
            notify = self._notify_wanted(name, wanted, never)
            chime = self.chime.on and self.chime.lane_wanted(name)
            if not notify:
                quiet.append(f"{name}+{len(ids)}")
            if not notify and not chime:
                continue
            id_set = set(ids)
            rows = self.store.items(lane.source, len(ids) + 50)
            if not self.cfg["feed"].get("repeat_boosts", False):  # not shown: no news
                rows = self._without_repeats(lane.source, rows)
            sts = [st for item_id, st in rows if item_id in id_set]
            if lane.chips:  # what a free lane's quick filter hides makes no news either
                shows = self._chip_shows(name)
                sts = [st for st in sts if shows(st)]
            unread = self.store.read_set(st["id"] for st in sts)
            news = [(name, st) for st in sts
                    if st["id"] not in unread and not self.silenced(st)]
            if news and self.calm(name):  # the lane's own pace: out with the next batch
                self._held.setdefault(name, []).extend(st for _n, st in news)
                continue
            if news:
                fresh.append(name)
            if notify:
                out += news
        for name, news in self._calm_out(wanted, never):
            fresh.append(name)
            if self._notify_wanted(name, wanted, never):
                out += news
        for name, events in self._events_by_lane(new_requests, new_activity).items():
            fresh.append(name)
            if self._notify_wanted(name, wanted, never):
                out += [(name, n) for n in events]
        if quiet:  # "why no notification?" — answered by the log
            log.info("notify: not asked for (notify.lanes / notify.except): %s",
                     ", ".join(quiet))
        out = self._once_per_post(out)
        if out:
            self.emit("notify", out)
        self.sound_news(fresh)

    def explain_post(self, status_id):
        """Why this post is in each lane of rules shown, or not (feeds.md §8: "Why is it
        here?"): [{"lane", "title", "in_lane", "taken", "by", "out", "conds",
        "quiet"}] — in_lane: the lane shows it now; quiet: what took it out before any
        rule (muted, a list's person, a language, a tag lane "not in Home")."""
        st = self.store.get_status(status_id)
        if st is None:
            return []
        sources = self.store.sources_of(status_id)
        world, ctx = self._world(), self._ctx()
        out = []
        for lane in self.lanes:
            c = next((c for c in self.customs if c.name == lane.name), None)
            if c is None:
                continue
            got = custom.explain(c, st, world, sources)
            quiet = ""
            if self.silenced(st):
                quiet = "silenced"
            elif got["taken"] and not lanes.keeps(lane, st, ctx) and \
                    (c.routed or c.takes(st, world, c.stream)):
                quiet = "before_rules"
            in_lane = lane.source in sources and lanes.keeps(lane, st, ctx) \
                and not self.silenced(st)
            out.append(dict(got, lane=lane.name, title=self.lane_title(lane.name) or "",
                            in_lane=bool(in_lane), quiet=quiet))
        return out

    def explain_lane(self, name, n=30):
        """--explain-lane: a lane of rules — its rule's warnings, where it reads from, and
        for the newest n stored posts of its sources whether it takes each and why."""
        c = next((c for c in self.customs if c.name == name), None)
        if c is None:
            return None
        world = self._world()
        rows, seen = [], set()
        for source in sorted(c.feeds):
            for _item, st in self.store.items(source, n):
                sid = real(st)["id"]
                if sid in seen:
                    continue
                seen.add(sid)
                got = custom.explain(c, st, world, self.store.sources_of(st["id"]))
                rows.append(dict(got, id=st["id"], source=source,
                                 who=real(st)["account"].get("acct", ""),
                                 created=st.get("created_at", ""),
                                 text=re.sub(r"<[^>]+>", " ", real(st).get("content") or "")))
        rows.sort(key=lambda r: r["created"], reverse=True)
        return {"name": name, "warnings": list(c.warnings), "feeds": sorted(c.feeds),
                "routed": c.routed, "rows": rows[:n]}

    def lanes_fed_by(self, *sources):
        """The lanes a source (or several) fills: by their own source or the feeds of a
        free lane — never by a lane's name. What "look again" goes to after a change in
        a source: the lane set is the user's (Home or no Home, "mentions" or "to_me")."""
        want = set(sources)
        return [x.name for x in self.lanes
                if x.source in want or want & set(x.feeds or ())]

    def redraw(self, *sources):
        """lanes_updated with nothing new for the lanes those sources fill: they look
        again (a thread left, a bookmark taken back)."""
        names = self.lanes_fed_by(*sources)
        if names:
            self.emit("lanes_updated", {n: [] for n in names})

    def private_lanes(self):
        """The lanes of private messages — whatever their names: the rule says so (a
        condition of `visibility = "direct"` or `me = "direct"`, lane_rank 0)."""
        return [x.name for x in self.lanes if self.lane_rank(x.name) == 0]

    def lane_sound(self, name):
        """The sound a lane's news makes (core/sounds.py), by its rule: how personal it is,
        or the events it takes."""
        from .sounds import event_for_lane
        lane = self.lane_by_name.get(name)
        events = None
        if lane is not None and getattr(lane, "events", False) and not lane.source:
            c = next((c for c in self.customs if c.name == name), None)
            events = {w for cond in (c.event_conds if c else ()) for w in cond.sets["event"]}
        return event_for_lane(self.lane_rank(name), events)

    def thread_lanes(self):
        """The lanes of followed threads, whatever their names: their rule's (lane_rank 3
        — the subs source, or a condition of my threads)."""
        return [x.name for x in self.lanes if self.lane_rank(x.name) == 3]

    def lane_rank(self, name):
        """How personal a lane is, for one notification a post (feeds.md §5): 0 private,
        1 replies to me, 2 mentions, 3 followed threads, 4 the rest — by its rule."""
        c = next((c for c in self.customs if c.name == name), None)
        if c is None:
            return 4
        best = 4
        for cond in c.rule.any:
            me = cond.sets.get("me", set())
            if me == {"direct"} or cond.sets.get("visibility") == {"direct"}:
                best = min(best, 0)
            elif me & {"reply", "reply_to_post", "reply_to_comment"}:
                best = min(best, 1)
            elif "mention" in me:
                best = min(best, 2)
            elif "in_my_thread" in me or "subs" in cond.sets.get("source", ()) \
                    or "subs" in c.rule.source:
                best = min(best, 3)
        return best

    def _once_per_post(self, out):
        """A post in several lanes is said once — by the most personal of them (private >
        reply > mention > thread > the rest); requests and activity stay as they are."""
        best = {}
        for i, (name, x) in enumerate(out):
            if not isinstance(x, dict) or "type" in x:  # an event: as it is
                continue
            sid = real(x).get("id")
            rank = self.lane_rank(name)
            if sid not in best or rank < best[sid][0]:
                best[sid] = (rank, i)
        keep = {i for _r, i in best.values()}
        return [(n, x) for i, (n, x) in enumerate(out)
                if not isinstance(x, dict) or "type" in x or i in keep]

    def _calm_out(self, wanted, never):
        """The lanes with news held back whose minutes have passed: [(lane, news still
        unread)]; the rest stay held. A lane quiet for long says its first news at once."""
        now = time.time()
        out = []
        for name in list(self._held):
            minutes = self.calm(name)
            last = self._calm_last.get(name)
            if minutes and last is not None and now - last < minutes * 60:
                continue
            sts = self._held.pop(name)
            read = self.store.read_set(st["id"] for st in sts)
            seen, news = set(), []
            for st in sts:
                if st["id"] not in read and st["id"] not in seen:
                    seen.add(st["id"])
                    news.append((name, st))
            if news:
                self._calm_last[name] = now
                out.append((name, news))
        return out

    def sound_news(self, lanes_with_news):
        """Emit 'sound' for a batch of news in these lanes, if the config wants one."""
        event = self.chime.for_news(lanes_with_news)
        if event:
            log.debug("sound: %s (%s)", event, ", ".join(lanes_with_news))
            self.emit("sound", event)

    def sound_moment(self, event):
        """Emit 'sound' for "online" or "sent", if the config wants it."""
        event = self.chime.for_moment(event)
        if event:
            log.debug("sound: %s", event)
            self.emit("sound", event)

    def _notify_wanted(self, name, wanted, never):
        """notify.lanes names this lane and notify.except doesn't (see lanes.chosen)."""
        return self.lane_chosen(name, wanted, never)

    def lane_chosen(self, name, wanted, never=()):
        """lanes.chosen with this lane's title: "list:Друзья" finds the list by name."""
        return lanes.chosen(name, wanted, never,
                            self.lane_title(name) if lanes.is_list(name) else None)

    def _ctx(self):
        return lanes.LaneContext(self.me["id"] if self.me else "",
                                 tuple(self.cfg["lanes"]["extra_bots"]),
                                 self._hidden_authors(),
                                 frozenset(self.cfg["lists"]["hide_in"]),
                                 frozenset(self.cfg["lanes"]["languages"]),
                                 frozenset(self.cfg["lanes"]["languages_in"]),
                                 self.cfg["lanes"]["detect_language"],
                                 self.cfg["lanes"]["detect_min_words"],
                                 frozenset(t for g in self.tag_groups if g.get("not_in_home")
                                           for t in g["any"] + g["all"]),
                                 self._world())

    # ---- activity: favourites, boosts, follows --------------------------------------
    def open_at(self, lane=None):
        """Where a thread opened from a card of `lane` opens: "post" or "first_unread" —
        the lane's own `open_at` (a lane of rules), else threads.open_at. No lane (a
        profile, Activity, a thread's own cards): threads.open_at."""
        own = getattr(self.lane_by_name.get(lane), "open_at", "") if lane else ""
        return own or self.cfg["feed"].get("open_at") or "post"

    def thread_news(self):
        """{root post id: unread replies} — the followed threads with something new
        (feed.thread_news: the line under such a post's card). Cached till the store
        or a read mark changes."""
        if not self.cfg["feed"].get("thread_news", True):
            return {}
        key = (self.store.items_version.get("subs", 0), self.store.read_version)
        hit = getattr(self, "_thread_news", None)
        if hit and hit[0] == key:
            return hit[1]
        got = self.store.thread_news_counts()
        self._thread_news = (key, got)
        return got

    # ---- lists ---------------------------------------------------------------------
    # ---- silence: muted and blocked people, server filters ----------------------------
    # ---- a hashtag muted in one click (Fedilab's way): a server filter "#tag" ------------
    def announcements(self):
        """The server's announcements not dismissed yet, oldest first; [] when
        ui.announcements is "off" or the server has none (GoToSocial: no such API)."""
        return self.submit(self._fetch_announcements)

    def _fetch_announcements(self):
        if self.cfg["ui"]["announcements"] == "off" or not self.api:
            return []
        try:
            got = self.api.announcements()
        except ApiError as e:
            log.debug("announcements: %s", e)
            return []
        gone = self.__dict__.get("_dismissed_ann", set())
        return sorted((a for a in got if not a.get("read") and a.get("id") not in gone),
                      key=lambda a: a.get("published_at") or "")

    def _check_announcements(self):
        """poll.announcements_minutes: the server's announcements asked again by the core
        for every interface (the windows each kept a timer of their own, the terminal and
        the web page none); something new, gone or reacted to — announcements_updated."""
        fresh = self._fetch_announcements()
        sig = [(a.get("id"), a.get("updated_at"),
                tuple((r.get("name"), r.get("count"), r.get("me")) for r in
                      a.get("reactions") or ())) for a in fresh]
        if sig != self._announced_sig:
            self._announced_sig = sig
            self.emit("announcements_updated", len(fresh))

    def dismiss_announcement(self, aid):
        """Read: gone here at once — a round asking the server before the dismissal got
        there brought it back (the banner came again: CI on Windows, 30.10)."""
        self.__dict__.setdefault("_dismissed_ann", set()).add(aid)
        return self.call_api("dismiss_announcement", aid)

    def scheduled(self):
        return self.call_api("scheduled")

    def cancel_scheduled(self, sid):
        return self.call_api("cancel_scheduled", sid)

    def set_note(self, acc_id, text, old=""):
        """My private note on them; fedtail's follow-date line (in `old`) stays on."""
        from .model import note_followed, note_with_followed
        return self.call_api("set_note", acc_id,
                           note_with_followed(text, note_followed(old)))

    # ---- thread subscriptions ------------------------------------------------------
    # ---- sync with the account's other devices (`fedtail sync …`, core/sync) ---------
    # ---- reading ---------------------------------------------------------------
    def set_active_lane(self, name):
        """The frontend tells which lane is on screen; a browse lane (local,
        federated) is fetched right away and then on every poll while it stays."""
        self._active_lane = name
        lane = self.lane_by_name.get(name)
        if lane is not None and lane.lazy:
            self._browse_waiting.add(lane.source)  # "loading…" till the server answers
            self.poll_now()

    @property
    def _browse_waiting(self):
        return self.__dict__.setdefault("_browse_waiting_set", set())

    @property
    def _lang_out(self):
        return self.__dict__.setdefault("_lang_out_counts", {})

    def language_hidden(self, name):
        """How many of the lane's posts lanes.languages left out (the last time it was
        made), 0 when none or no filter there."""
        return self._lang_out.get(name, 0)

    def lane_waiting(self, name):
        """A browse lane (Federated, Local) just opened, its server not answered yet:
        the lane says "loading…" (with the opossum) instead of looking empty."""
        lane = self.lane_by_name.get(name)
        return bool(lane is not None and lane.lazy and lane.source in self._browse_waiting)

    def set_active_lanes(self, names):
        """Columns side by side: every lane on screen at once (the browse ones among
        them fetched while they stay)."""
        new = set(names or ())
        fresh = new - self._active_lanes
        self._active_lanes = new
        if any(getattr(self.lane_by_name.get(n), "lazy", False) for n in fresh):
            self.poll_now()

    # ---- choices over a lane (posts only, new only, conversations) -----------------
    # Kept for this run only, unless feed.remember_choices: every start begins at the
    # config's defaults (lanes.posts_only), not wherever a lane was left last week.
    def choice(self, key, default=None):
        if self.cfg["feed"]["remember_choices"]:
            return self.get_state(key, default)
        return self._choices.get(key, default)

    def set_choice(self, key, value):
        if self.cfg["feed"]["remember_choices"]:
            self.set_state(key, value)
        else:
            self._choices[key] = value
        self._lane_cache.clear()

    def posts_only(self, name):
        saved = self.choice(f"posts_only.{name}")
        return saved if saved is not None else name in self.cfg["lanes"]["posts_only"]

    def set_posts_only(self, name, on):
        self.set_choice(f"posts_only.{name}", bool(on))

    def _carry_my_direct(self, statuses=None):
        """My direct messages into the stream of every lane of private messages (whatever
        its name, private_lanes): the dialogue whole — theirs and mine, by the posts' own
        time. Mine are read (the store marks every post of mine read), so no count grows.
        statuses: the ones just sent; None — every one stored that isn't there yet. How
        many went in (none: no such lane)."""
        n = 0
        for source in dict.fromkeys(x.source for x in self.lanes
                                    if self.lane_rank(x.name) == 0):
            if not source:
                continue
            if statuses is None:
                got = self.store.my_direct_outside(source)
            else:
                got = [s for s in statuses if s and s.get("visibility") == "direct"
                       and self.me and s.get("account", {}).get("id") == self.me["id"]]
            # an item of its own ("mine:" + id): never one of the server's notification ids
            n += len(self.store.put_items(source, [("mine:" + s["id"], s,
                                                    s.get("created_at", "")) for s in got]))
        return n

    def lane_entries(self, name):
        """[(item_id, status)] oldest → newest, at most the lane's render limit.

        Cached until the store changes: the GUI asks for this on every
        scroll-triggered badge update, and parsing thousands of JSON blobs
        each time is what makes a client feel sticky.
        """
        lane = self.lane_by_name.get(name)
        if lane is None or not lane.source:  # a list deleted meanwhile
            return []
        limit = self._limits.get(name, self.cfg["feed"]["render_limit"])
        only_posts = self.posts_only(name)
        repeats = self.cfg["feed"].get("repeat_boosts", False)
        rule = next((c for c in self.customs if c.name == name), None)
        state = rule is not None and "state" in rule.needs  # unread, new_replies…
        horizon = self._horizons.get(name, max(FILTER_WINDOW, limit))
        funnel = self._funnel(name)
        key = (self.store.items_version.get(lane.source, 0), self.store.status_version, limit,
               self.me["id"] if self.me else None, only_posts, self._lists_version,
               self._silence_version, repeats, self._world_version,
               self.store.read_version if state else 0, self.lane_filter(name),
               horizon, str(self.choice(f"media.{name}")),
               # a window moves with the clock (and density with the posts' age): anew
               # each minute
               int(time.time() // 60) if getattr(lane, "window", 0)
               or getattr(lane, "sort", "") == "density" else 0)
        hit = self._lane_cache.get(name)
        if hit and hit[0] == key:
            return hit[1]
        ctx = self._ctx()
        kept = []
        # the quick filters (a free lane's switches, the funnel "only video…") count
        # before the window does: the window is the newest `limit` posts they let
        # through — not the newest `limit` posts, filtered after, a handful of videos
        # out of a lane full of them further down (28.10)
        shows = self._chip_shows(name) if lane.chips else None
        scanned, full = 0, False
        # lanes.languages: how many it took out, said in the lane's line (a lane showing
        # one post of forty, the rest gone without a word, 29.10)
        by_lang = bool(ctx.languages) and lanes.in_scope(lane.name, ctx.languages_in)
        lang_out = 0
        rows = self.store.iter_items(lane.source, max_rows=horizon)
        if not repeats:
            rows = self._without_repeats(lane.source, rows)
        for item_id, st in rows:
            if scanned >= horizon:
                break
            scanned += 1
            if only_posts and real(st).get("in_reply_to_id"):
                continue
            if self.silenced(st):
                continue
            if funnel is not None and not funnel(st):
                continue
            if shows is not None and not shows(st):
                continue
            if by_lang and not langs.wanted(real(st), ctx.languages, ctx.detect,
                                            ctx.min_words):
                lang_out += 1
                continue
            if lanes.keeps(lane, st, ctx):
                kept.append((item_id, st))
                if len(kept) >= limit:
                    full = True
                    break
        self._lang_out[name] = lang_out
        # what "Older" does next: the store has more to look through, or only the server
        self._lane_deep[name] = not full and scanned >= horizon
        kept.reverse()
        if lane.by_status_time:
            kept.sort(key=lambda e: (real(e[1]).get("created_at", ""), real(e[1])["id"]))
        if getattr(lane, "window", 0):  # only the last so many hours (mode = "catch_up")
            kept = _within(kept, lane.window)
        if getattr(lane, "filter_context", ""):
            kept = self._by_filter_context(kept, lane.filter_context)
        if getattr(lane, "sort", "arrival") in COUNT_SORTS:
            kept = _by_counts(kept, lane.sort, self.cfg["feed"]["order"] == "oldest_first")
        if getattr(lane, "per_author", 0):  # a noisy one: their newest so many
            kept = _per_author(kept, lane.per_author)
        if getattr(lane, "bundle", "") == "author":
            kept = _bundled(kept, self.cfg["feed"]["order"] == "oldest_first")
        self._lane_cache[name] = (key, kept)
        return kept

    def _by_filter_context(self, entries, context):
        """A lane's filter_context: the server's filters of that context, by their words,
        hide its posts ("hide") or fold them ("warn") — whatever context they came by."""
        filters = [f for f in self._server_filters if context in (f.get("context") or ())]
        if not filters:
            return entries
        out = []
        for item_id, st in entries:
            hit = _filter_hits(real(st), filters)
            if any(f.get("filter_action") == "hide" for f in hit):
                continue
            if hit:
                have = {(x.get("filter") or {}).get("id") for x in real(st).get("filtered") or ()}
                more = [{"filter": f} for f in hit if f.get("id") not in have]
                if more:
                    r = real(st)
                    r = dict(r, filtered=list(r.get("filtered") or ()) + more)
                    st = dict(st, reblog=r) if st.get("reblog") else r
            out.append((item_id, st))
        return out

    def _chipper(self, name):
        """The lane of rules whose quick filters part a lane; None — none such."""
        c = next((c for c in self.customs if c.name == name), None)
        return c if c is not None and c.chips() else None

    def _needs_threads(self):
        """Is a lane's quick filter on that asks for threads with news (state = new_replies)?
        Then the followed threads are checked even without their own lane."""
        for c in self.customs:
            which = self.lane_filter(c.name) if c.chips() else "all"
            if which.startswith("chip:"):
                i = int(which[5:])
                if i < len(c.rule.any) and "new_replies" in c.rule.any[i].sets.get("state", ()):
                    return True
        return False

    def lane_filter(self, name):
        """A lane's quick filter now: "all", "main", "chip:<n>"."""
        c = self._chipper(name)
        if c is None:
            return "all"
        got = self.choice(f"filter.{name}")
        return got if got in {"all"} | {k for k, _w in c.chips()} else c.default_filter()

    def _funnel(self, name):
        """The lane's funnel ("only posts with video…", boosts or not — LaneModel's
        MediaFilter, a choice "media.<name>"): a test of a status, or None (all)."""
        got = self.choice(f"media.{name}")
        if not isinstance(got, dict):
            return None
        wanted = set(got.get("wanted") or ()) & set(atoms.MEDIA_KINDS)
        boosts = bool(got.get("boosts", True))
        if (not wanted or wanted == set(atoms.MEDIA_KINDS)) and boosts:
            return None
        every = not wanted or wanted == set(atoms.MEDIA_KINDS)
        return lambda st: (boosts or not st.get("reblog")) and \
            (every or bool(atoms.media_kinds(st) & wanted))

    def set_lane_filter(self, name, which):
        self.set_choice(f"filter.{name}", which)

    def _chip_shows(self, name):
        c = self._chipper(name)
        which = self.lane_filter(name)
        if c is None or which == "all":
            return lambda st: True
        world = self._world()
        return lambda st: c.shows(st, world, which)

    def _without_repeats(self, source, rows, chunk=200):
        """feed.repeat_boosts = false: a boost shows only if it is how the post first came
        into this lane — not an old post boosted again (and again), not one read already.
        The post itself, come as itself, always shows."""
        batch = []

        def flush():
            firsts = self.store.first_seen(source, [st["reblog"]["id"] for _, st in batch
                                                    if st.get("reblog")])
            for item_id, st in batch:
                if not st.get("reblog") or firsts.get(st["reblog"]["id"], item_id) == item_id:
                    yield item_id, st
        for row in rows:
            batch.append(row)
            if len(batch) >= chunk:
                yield from flush()
                batch = []
        yield from flush()

    def deep_find(self, name, query):
        """Ctrl+F past what the lane shows: look through everything stored for it.
        If an older match exists, the lane is extended down to it. Returns
        {"total": matches in the store, "more": whether the lane grew}."""
        def job():
            lane = self.lane_by_name.get(name)
            if lane is None or not lane.source:
                return {"total": 0, "more": False}
            ctx, only_posts = self._ctx(), self.posts_only(name)
            limit = self._limits.get(name, self.cfg["feed"]["render_limit"])
            found, i = [], 0
            for _item, st in self.store.iter_items(lane.source):
                if only_posts and real(st).get("in_reply_to_id"):
                    continue
                if not lanes.keeps(lane, st, ctx):
                    continue
                i += 1
                if search.matches(query, search.haystack(st)):
                    found.append(i)
            older = [x for x in found if x > limit]
            if older:
                self._limits[name] = older[0] + 10  # down to the next match, a bit more
                self.emit("lanes_updated", {name: []})
            return {"total": len(found), "more": bool(older)}
        return self.submit(job)

    FIND_EVERYWHERE_MAX = 500

    def find_everywhere(self, query):
        """Ctrl+F with "in every lane": everything stored, lane by lane in the sidebar's
        order, each lane's posts newest first. A post found in one lane isn't repeated
        for the next. [{"lane", "item", "status_id", "index"}] — index: its place in the
        lane counting from the newest, for reveal_in_lane.

        Lanes sharing a source (home, bots, replies…) are gone through together: each
        stored post is parsed and matched once, not once per lane."""
        def job():
            ctx = self._ctx()
            repeats = self.cfg["feed"].get("repeat_boosts", False)
            by_source = {}
            for lane in self.lanes:
                if lane.source:
                    by_source.setdefault(lane.source, []).append(lane)
            found = {}  # lane name -> its hits, newest first
            for source, group in by_source.items():
                only = {lane.name: self.posts_only(lane.name) for lane in group}
                count = dict.fromkeys(only, 0)
                rows = self.store.iter_items(source)
                if not repeats:
                    rows = self._without_repeats(source, rows)
                for item_id, st in rows:
                    if self.silenced(st):
                        continue
                    reply = bool(real(st).get("in_reply_to_id"))
                    hit = None  # matched lazily: only if some lane keeps the post
                    for lane in group:
                        if (only[lane.name] and reply) or not lanes.keeps(lane, st, ctx):
                            continue
                        count[lane.name] += 1
                        if hit is None:
                            hit = search.matches(query, search.haystack(st))
                        if hit:
                            found.setdefault(lane.name, []).append(
                                {"lane": lane.name, "item": item_id, "status_id": st["id"],
                                 "index": count[lane.name], "_rid": real(st)["id"]})
            seen, out = set(), []
            for lane in self.lanes:  # the sidebar's order; each post once
                for h in found.get(lane.name, ()):
                    rid = h.pop("_rid")
                    if rid not in seen and len(out) < self.FIND_EVERYWHERE_MAX:
                        seen.add(rid)
                        out.append(h)
            return out
        return self.submit(job)

    def reveal_in_lane(self, name, index):
        """The lane loaded down to its index-th post from the newest (a match found by
        find_everywhere further back than the lane shows). True if it grew: the caller
        redraws the lane (no event — it is about to anyway)."""
        limit = self._limits.get(name, self.cfg["feed"]["render_limit"])
        if index <= limit:
            return False
        self._limits[name] = index + 10
        return True

    def unread_ids(self, entries):
        """The unread among (item, status) entries. A post read once is read everywhere:
        a boost counts read when its post is (read as itself, in another lane, or as
        someone else's boost) — each was read by its own id, and the same post stood
        unread in the next lane or interface (29.10)."""
        pairs = [(st["id"], (st.get("reblog") or {}).get("id")) for _, st in entries]
        read = self.store.read_set({i for pair in pairs for i in pair if i})
        return {i for i, post in pairs if i not in read and (not post or post not in read)}

    def unread_count(self, name):
        """Unread in a lane — cached while neither the lane nor any read mark changed:
        the sidebar asks for every lane after every event. A lane of events only counts
        its events not seen yet."""
        if self._events_only(name):
            return self.events_unread(name)
        entries = self.lane_entries(name)
        hit = self._lane_cache.get(name)
        key = (hit[0] if hit else None, id(entries), self.store.read_version)
        cache = self.__dict__.setdefault("_unread_cache", {})
        got = cache.get(name)
        if got and got[0] == key:
            return got[1]
        unread = self.unread_ids(entries)
        n = self._threads_of([e for e in entries if e[1]["id"] in unread]) \
            if self._by_thread(name) else len(unread)
        cache[name] = (key, n)
        return n

    def _warm_lanes(self):
        """The lanes and their unread counts worked out here, in the poll thread, before
        the window hears of news: it then finds them made, instead of reading thousands
        of stored posts itself between two frames (the freezes of 250 ms to a second
        after each poll)."""
        t = time.monotonic()
        for lane in list(self.lanes):
            if lane.lazy or self._stop.is_set():
                continue
            try:
                self.unread_count(lane.name)
            except Exception as e:  # noqa: BLE001 — the window will try again itself
                log.debug("warm %s: %s", lane.name, e)
        self._step("warm lanes")
        try:
            self._warmed_at = (self.store.status_version,
                               tuple(sorted(self.store.items_version.items())))
        except Exception:  # noqa: BLE001 — a store without versions (a test's fake)
            pass
        log.debug("lanes warmed in %.2f s", time.monotonic() - t)

    def mark_read(self, status_ids):
        """These read — and, for a boost among them, its post too: read once, read
        everywhere (unread_ids)."""
        status_ids = list(status_ids)
        if status_ids:
            try:
                have = self.store.get_statuses(set(status_ids))
            except Exception:  # noqa: BLE001 — a store without statuses (a test's fake)
                have = {}
            posts = {(st.get("reblog") or {}).get("id") for st in have.values()
                     if isinstance(st, dict) and isinstance(st.get("reblog"), dict)}
            status_ids += sorted(i for i in posts - set(status_ids) if i)
            self.store.mark_read(status_ids, shared=True)
            self.emit("read_changed", status_ids)  # the cards: at once
            self._reading_moment(len(status_ids))

            def counted():  # every lane's count anew here, then "counts_ready": the
                self._warm_lanes()  # window made them itself after each mark (330 ms)
                self.emit("counts_ready", None)
            try:
                self.reads.submit(counted)
            except RuntimeError:  # shut down: nobody to tell
                pass
            if self.sync:
                self.sync.record_read(status_ids)
            self._read_conversations(status_ids)

    READ_QUIET_S = 3600  # read marks after this much quiet: "reading began" (the night's)
    READ_DONE_S = 600    # …and none for this long since: "reading ended"

    def _reading_moment(self, n=0):
        """The memory before and after reading, for the night's summary (diag.moment):
        the first marks after an hour's quiet — the night left behind — and, once marks
        have stopped for ten minutes (a round looks: n = 0), the end of it."""
        now = time.monotonic()
        run = self.__dict__.get("_reading_run")
        last = self.__dict__.get("_last_mark")
        if n:
            if last is None or now - last > self.READ_QUIET_S:
                quiet = round((now - last) / 3600, 1) if last is not None else None
                diag.moment("reading began", quiet_hours=quiet)
                run = self._reading_run = [now, 0]
            if run is not None:
                run[1] += n
            self._last_mark = now
        elif run is not None and last is not None and now - last > self.READ_DONE_S:
            diag.moment("reading ended", minutes=round((last - run[0]) / 60, 1),
                        marked=run[1])
            self._reading_run = None

    def older_ahead(self, name):
        """The end of lane `name` came in sight (a frontend says so as one scrolls):
        a page older by itself — reading.older_ahead — unless one is on its way already
        or the server gave nothing older the last time. A future of how many came, or
        None (nothing asked). Every interface asks only this; the core decides."""
        if not self.cfg["feed"].get("older_ahead") or name not in self.lane_by_name:
            return None
        busy = self.__dict__.setdefault("_older_busy", set())
        if name in busy or name in self.__dict__.get("_older_none", set()):
            return None
        busy.add(name)
        fut = self.load_older(name)

        def done(f):
            busy.discard(name)
            # nothing came (the start of it, or a rule that took none of a page): asked
            # no more by itself — a lane drawn anew at its end would ask on and on; the
            # button still may
            if f.exception() is not None or not f.result():
                self.__dict__.setdefault("_older_none", set()).add(name)
        fut.add_done_callback(done)
        return fut

    def load_older(self, name):
        """A page older: from the store first, while it holds more than the lane's
        window looked through (a filtered lane, a funnel: the posts are there, further
        down), then from the server."""
        lane = self.lane_by_name[name]
        if self._lane_deep.get(name):
            def deeper():
                limit = self._limits.get(name, self.cfg["feed"]["render_limit"])
                before = len(self.lane_entries(name))
                self._horizons[name] = self._horizons.get(
                    name, max(FILTER_WINDOW, limit)) + FILTER_WINDOW
                self._limits[name] = limit + self.cfg["feed"]["page_size"]
                got = len(self.lane_entries(name)) - before
                self.emit("lanes_updated", {name: []})
                return max(got, 1) if self._lane_deep.get(name) else got
            return self.submit(deeper)
        if lane.feeds:
            return self.submit(lambda: self._older_custom(name))
        if lane.source not in self.sources:  # nothing older on a server for this one
            return self.submit(lambda: 0)

        def job():
            got = self._older_pages(name, lambda: sources.fetch_older(
                self.store, self.sources[lane.source], self.cfg["feed"]["page_size"]))
            limit = self._limits.get(name, self.cfg["feed"]["render_limit"])
            self._limits[name] = limit + len(got)
            # history is not news: older posts count as read
            self.store.mark_read([st["id"] for st in got])
            self.emit("lanes_updated", {name: []})
            self._fetch_parents(got)
            return len(got)
        return self.submit(job)

    FUNNEL_WANT = 10  # posts through the funnel an "Older" goes on for (funnel_fill_pages)

    def _older_pages(self, name, one):
        """one() → what a page older brought into the lane. The funnel on ("only video"):
        pages on, up to lanes.funnel_fill_pages, till FUNNEL_WANT of them pass it — a page
        of forty left one or two posts, and the lane grew by those (30.10)."""
        funnel = self._funnel(name)
        pages = max(1, int(self.cfg["lanes"].get("funnel_fill_pages", 5))) if funnel else 1
        got, passed = [], 0
        for _n in range(pages):
            more = one()
            got += more
            if not more or funnel is None:
                break
            passed += sum(1 for st in more if funnel(st))
            if passed >= self.FUNNEL_WANT:
                break
        return got

    def _older_custom(self, name):
        """A free lane's "Older": a page older from each of its feeds, through its rule
        (more pages while the funnel leaves few, _older_pages)."""
        c = next((c for c in self.customs if c.name == name), None)
        if c is None:
            return 0
        got = self._older_pages(name, lambda: self._older_custom_page(c))
        limit = self._limits.get(name, self.cfg["feed"]["render_limit"])
        self._limits[name] = limit + len(got)
        self.emit("lanes_updated", {name: []})
        self._fetch_parents(got)
        return len(got)

    def _older_custom_page(self, c):
        world, got = self._world(), []
        for source in sorted(c.feeds):
            if source not in self.sources:
                continue
            try:
                older = sources.fetch_older(self.store, self.sources[source],
                                            self.cfg["feed"]["page_size"])
            except Exception as e:  # noqa: BLE001 — the other feeds still give theirs
                self.emit("error", f"{source}: {e}")
                continue
            self.store.mark_read([st["id"] for st in older])  # history is not news
            got += custom.take(self.store, c, older, world, source)
        return got

    def short_ids(self, statuses):
        """{status id: '#a3f'-style alias} for the posts on screen (boosts: the original);
        a numbered comment — its post's and its number, "a3f/2", as on Point
        (threads.comment_ids = "post"): a comment was named as if it were a post of its own
        (30.10), its thread's numbers seen only inside the thread. The command line
        takes "#a3f/2" (target)."""
        ids = [real(st)["id"] for st in statuses]
        out = self.store.aliases(ids)
        if self.cfg["feed"].get("comment_ids", "post") != "post":
            return out
        nums = self.store.comment_numbers(ids)
        if nums:
            roots = self.store.aliases(root for root, _n in nums.values())
            for sid, (root, n) in nums.items():
                out[sid] = f"{roots[root]}/{n}"
        return out

    def resolve_alias(self, alias):
        return self.store.by_alias(alias)

    def my_replies(self, statuses):
        """{status id: [my replies to it]} for the given (possibly boosted) statuses."""
        if not self.me:
            return {}
        return self.store.replies_by({real(st)["id"] for st in statuses}, self.me["id"])

    def check_my_replies(self, statuses):
        """Find my replies the cache doesn't know about yet (older than what the
        'my_posts' lane fetched). Only for posts that have replies at all, and each
        post only once per reply count, so this stays cheap."""
        want = []
        for st in statuses:
            s = real(st)
            n = s.get("replies_count") or 0
            if n and s["id"] not in self._replies_inflight and \
                    self.store.kv_get(f"replies_checked:{s['id']}") != n:
                self._replies_inflight.add(s["id"])
                want.append((s["id"], n))
        if want:
            self.bg.submit(self._check_my_replies, want)

    def _check_my_replies(self, want):
        known = self.my_replies([{"id": sid} for sid, _ in want])
        found = []
        for sid, n in want:
            try:
                if sid not in known:
                    ctx = self.api.context(sid)
                    self.store.put_statuses(ctx.get("descendants", []))
                    mine = [d for d in ctx.get("descendants", [])
                            if d.get("in_reply_to_id") == sid
                            and d["account"]["id"] == self.me["id"]]
                    if mine:
                        found.append(sid)
                self.store.kv_set(f"replies_checked:{sid}", n)
            except Exception:
                pass  # try again next time
            finally:
                self._replies_inflight.discard(sid)
        if found:
            self.mark_read(found)  # I answered it, so I have read it
            self.emit("parents")

    def own_hosts(self):
        """My servers' hostnames: exempt from remote's public-address rule (a server
        at home on a private address still shows its own pictures)."""
        return self._own_hosts()

    def _own_hosts(self):
        """(own_hosts.)"""
        from urllib.parse import urlparse
        server = (self.auth or {}).get("server") or ""
        return {(urlparse(server).hostname or "").lower()} - {""}

    def _origin_json(self, url):
        """An ActivityPub object from someone else's server: no token, short timeout,
        public https addresses only, the size capped (see remote)."""
        from . import remote
        from .replies import AP_ACCEPT
        return remote.get_json(url, headers={"User-Agent": USER_AGENT, "Accept": AP_ACCEPT},
                               own_hosts=self._own_hosts())

    def long_form(self, st):
        """The whole post from the author's server (feed.long_form): an article, a page,
        an event with its time and place. No token goes there."""
        from .model import long_form_of, real
        uri = real(st).get("uri") or ""

        def job():
            if not uri.startswith("https://"):
                return None
            return long_form_of(self._origin_json(uri))
        return self.bg.submit(job)

    NODEINFO_KEEP_S = 7 * 86400

    def server_software(self, host):
        """What a server runs, from its nodeinfo (no token): "GoToSocial 0.17.3", or ""
        when it doesn't say. Kept a week per server (feed.server_info)."""
        def job():
            if not host or not self.cfg["feed"].get("server_info", True):
                return ""
            cache = self.store.kv_get("nodeinfo", {}) or {}
            got = cache.get(host)
            if got and time.time() - got[0] < self.NODEINFO_KEEP_S:
                return got[1]
            name = ""
            try:
                links = self._origin_get(f"https://{host}/.well-known/nodeinfo") or {}
                href = next((x.get("href") for x in reversed(links.get("links") or [])
                             if "nodeinfo" in (x.get("rel") or "")), None)
                # the document itself on that same server: never an address it names
                from urllib.parse import urlparse
                if not isinstance(href, str) or \
                        (urlparse(href).hostname or "").lower() != host.lower():
                    href = None
                info = self._origin_get(href) if href else None
                sw = (info or {}).get("software") or {}
                if sw.get("name"):
                    pretty = {"gotosocial": "GoToSocial", "mastodon": "Mastodon",
                              "akkoma": "Akkoma", "pleroma": "Pleroma", "misskey": "Misskey",
                              "sharkey": "Sharkey", "lemmy": "Lemmy", "pixelfed": "Pixelfed",
                              "peertube": "PeerTube", "friendica": "Friendica",
                              "writefreely": "WriteFreely", "mobilizon": "Mobilizon",
                              "iceshrimp": "Iceshrimp", "hometown": "Hometown"}
                    n = str(sw["name"]).lower()
                    name = f"{pretty.get(n, sw['name'])} {sw.get('version') or ''}".strip()
            except Exception as e:  # noqa: BLE001 — their server, anything goes
                log.debug("nodeinfo %s: %s", host, e)
            cache[host] = (time.time(), name)
            if len(cache) > 2000:
                cache = dict(sorted(cache.items(), key=lambda kv: kv[1][0])[-1000:])
            self.store.kv_set("nodeinfo", cache)
            return name
        return self.bg.submit(job)

    # ---- the command line (core/commands.py parses, the frontend runs) --------------
    def by_alias(self, alias):
        """The stored status behind a short id like a3f, or None."""
        sid = self.store.by_alias(alias)
        return self.store.get_status(sid) if sid else None

    def target(self, alias, number=0):
        """#a3f → that post; #a3f/2 → comment /2 of its thread. Future: status or None."""
        def job():
            st = self.by_alias(alias)
            if st is None or not number:
                return st
            nodes = self._thread_nodes(real(st)["id"])  # numbered as said: #a3f/N
            return next((n.status for n in nodes if n.number == number), None)
        return self.submit(job)

    PROFILE_SHOWS = {"all": {}, "posts": {"exclude_replies": True},
                     "media": {"only_media": True}}

    def profile_filter(self, show):
        """What the server filters someone's posts by: show of PROFILE_SHOWS, or
        "tag:<name>" — only those with the tag (a tag as one author writes it)."""
        if str(show).startswith("tag:"):
            return {"tagged": show[4:].lstrip("#")}
        return self.PROFILE_SHOWS.get(show, {})

    def account_statuses(self, acc_id, max_id=None, show="all"):
        """Someone's posts, a page; show: "all" (posts and replies), "posts" (without
        their replies to others — the server filters), "media" (only with pictures)."""
        def job():
            page = self.api.account_statuses(acc_id, limit=self.cfg["feed"]["page_size"],
                                             max_id=max_id, **self.profile_filter(show))
            self.store.put_statuses(page)
            return page
        return self.submit(job)

    def resolve_statuses(self, uris):
        """A future of the posts at these addresses, fetched into my server."""
        return self.bg.submit(self._resolve_statuses, list(uris))

    def _resolve_statuses(self, uris):
        """Posts by address, fetched into my server (a few at a time) and stored."""
        def one(uri):
            try:
                found = self.api.search(uri, kind="statuses", resolve=True, limit=1)
            except Exception as e:  # noqa: BLE001 — gone, not public: skip it
                log.debug("resolve %s: %s", uri, e)
                return []
            return (found or {}).get("statuses") or []
        got = []
        if uris:
            with ThreadPoolExecutor(4, thread_name_prefix="resolve") as pool:
                for sts in pool.map(one, uris):
                    got += sts
        if got:
            self.store.put_statuses(got)
        return got

    # ---- my own names for people (feed.aliases), travelling with sync.people -------------
    # ---- "Not in Home": someone still followed, their posts kept out of Home ------------
    def search(self, q):
        """People, tags and posts for a query; addresses (@user@server, a profile
        or post URL) are fetched from their home server by mine."""
        def job():
            got = self.api.search(q.strip(), resolve=True,
                                  limit=int(self.cfg["feed"].get("search_limit", 20)))
            self.store.put_statuses(got.get("statuses") or [])
            accounts = got.get("accounts") or []
            rel = {r["id"]: r for r in self.api.relationships([a["id"] for a in accounts])} \
                if accounts else {}
            return {"accounts": accounts, "relations": rel,
                    "hashtags": got.get("hashtags") or [], "statuses": got.get("statuses") or []}
        return self.submit(job)

    def tag_info(self, name):
        return self.call_api("tag", name)

    def follow_tag(self, name, on=True):
        return self.call_api("follow_tag", name, on)

    def followed_tags(self):
        return self.call_api("followed_tags")

    # ---- completing hashtags while writing -------------------------------------------
    def tag_timeline(self, tag, max_id=None):
        def job():
            page = self.api.tag_timeline(tag, limit=self.cfg["feed"]["page_size"],
                                         max_id=max_id)
            self.store.put_statuses(page)
            return page
        return self.submit(job)

    def resolve(self, url):
        """A web address of a fediverse profile or post → ("account", acc) /
        ("status", st) through my own server, or None if it doesn't know it."""
        def job():
            got = self.api.search(url, resolve=True, limit=1)
            if got.get("statuses"):
                st = got["statuses"][0]
                self.store.put_statuses([st])
                return ("status", st)
            if got.get("accounts"):
                return ("account", got["accounts"][0])
            return None
        return self.submit(job)

    # ---- my profile ------------------------------------------------------------
    # ---- writing ---------------------------------------------------------------
    def favourite(self, status):
        s = real(status)
        self._on_server(s)
        def job():
            got = self._update(self.api.favourite(s["id"], not s.get("favourited")))
            if not s.get("favourited"):  # liked now: threads.auto = "likes"
                self._follow_for("likes", s)
            return got
        return self.submit(job)

    def vote(self, status, choices):
        """Vote in the post's poll (choices: option indexes); the post comes back
        with the counts and my votes in it."""
        s = real(status)
        pid = (s.get("poll") or {}).get("id")
        if not pid or not choices:
            raise ValueError("no poll or no choice")
        def job():
            got = self._update(dict(s, poll=self.api.vote(pid, choices)))
            self._follow_for("votes", s)  # threads.auto = "votes"
            return got
        return self.submit(job)

    def refresh_poll(self, status):
        """Fresh counts for the post's poll."""
        s = real(status)
        pid = (s.get("poll") or {}).get("id")
        return self.submit(lambda: self._update(dict(s, poll=self.api.poll(pid))))

    # ---- feed.translate_auto: posts in languages I neither read nor write ---------------
    def report(self, status, comment="", forward=False, category="other", rule_ids=()):
        """Tell my server's moderators about a post (and its author); forward: also the
        moderators of the author's server, without saying who reported; rule_ids: the
        server's rules it breaks (the category is "violation" then)."""
        s = real(status)
        if rule_ids:
            return self.call_api("report", s["account"]["id"], [s["id"]], comment,
                                 forward, category, rule_ids=tuple(rule_ids))
        return self.call_api("report", s["account"]["id"], [s["id"]], comment,
                             forward, category)

    def stats(self, days=7):
        """feed.stats: the last days, each — how many posts came into Home, how many I
        wrote, how much activity; and who filled Home the most. Days are local ones,
        today last: [(date, home, mine, activity)], [(acct, n)]."""
        import datetime as dt
        today = dt.date.today()
        first = today - dt.timedelta(days=days - 1)
        start = dt.datetime.combine(first, dt.time()).astimezone(dt.UTC)
        got = self.store.stats_since(start.strftime("%Y-%m-%dT%H:%M:%S"),
                                     (self.me or {}).get("id"), source=self._home_source())

        def local_day(iso):
            try:
                t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
            except ValueError:
                return None
            if t.tzinfo is None:
                t = t.replace(tzinfo=dt.UTC)
            return t.astimezone().date()

        counts = {first + dt.timedelta(days=i): [0, 0, 0] for i in range(days)}
        for k, key in enumerate(("home", "mine", "activity")):
            for iso in got[key]:
                d = local_day(iso)
                if d in counts:
                    counts[d][k] += 1
        self._stats_links = got["links"]  # the week's most shared links (stats_links)
        return [(d, *c) for d, c in sorted(counts.items())], got["authors"]

    def stats_links(self):
        """[(url, title, how many posts)] — the links Home shared most this week (the
        last stats())."""
        return list(getattr(self, "_stats_links", []))

    def _home_source(self):
        """The source the Home lane is fed by (the server's home timeline)."""
        return "home"

    def raw_json(self, sid):
        """The post as the server gave it, JSON (debug.raw_json — for bug reports);
        "" when it isn't stored."""
        import json
        st = self.store.get_status(sid)
        return json.dumps(st, ensure_ascii=False, indent=2, sort_keys=True) if st else ""

    def came_by_tag(self, status):
        """Why a post is in Home when its author isn't followed: the followed tag it
        carries ("" — not that way). card.why_home says it on the card."""
        st = real(status)
        who = (st.get("account") or {}).get("id")
        if not who or who == (self.me or {}).get("id") or who in (self._following or ()):
            return ""
        followed = getattr(self, "_followed_tag_names", None) or set()
        return next(((t.get("name") or "") for t in st.get("tags") or ()
                     if (t.get("name") or "").lower() in followed), "")

    def around(self, sid):
        """"Around this post" (feed.around_post): what came just before and just after it
        in Home — or, when Home never had it, on its author's wall. Newest first."""
        def job():
            st = self.store.get_status(sid) or self._status_again(sid)
            n = max(5, self.cfg["feed"]["page_size"] // 2)
            older = self.api.home(limit=n, max_id=sid) or []
            newer = self.api.home(limit=n, min_id=sid) or []
            if not older and not newer:
                acc = real(st)["account"]["id"]
                older = self.api.account_statuses(acc, limit=n, max_id=sid) or []
                newer = self.api.account_statuses(acc, limit=n, min_id=sid) or []
            seen, out = set(), []
            for x in newer + [st] + older:
                if x["id"] not in seen:
                    seen.add(x["id"])
                    out.append(x)
            out.sort(key=lambda x: (x.get("created_at") or "", x["id"]), reverse=True)
            self.store.put_statuses(out)
            return out
        return self.submit(job)

    def link_timeline(self, url, max_id=None):
        """Posts sharing this link (a trending one: the server keeps only those)."""
        def job():
            page = self._api("link_timeline", self.api.link_timeline, url,
                             limit=self.cfg["feed"]["page_size"], max_id=max_id) or []
            self.store.put_statuses(page)
            return page
        return self.submit(job)

    def featured_tag_suggestions(self):
        return self.call_api("featured_tag_suggestions")

    # ---- Web Push: the browser of the web page subscribes at my server itself ----------
    def featured(self, acc_id):
        """What someone puts forward on their profile: {"tags": [featured tags],
        "people": [accounts they recommend]}. A server without one of these gives []."""
        def job():
            out = {}
            for key, fn in (("tags", self.api.featured_tags), ("people", self.api.endorsements)):
                try:
                    out[key] = fn(acc_id) or []
                except ApiError as e:
                    log.debug("featured %s: %s", key, e)
                    out[key] = []
            return out
        return self.submit(job)

    def pinned(self, acc_id):
        """The posts someone pinned to the top of their profile (a future of a list).
        Someone from another server my server knows little about: their pins as their
        own server lists them (the actor's "featured" collection, read without my
        token), each fetched through my server (feed.remote_profiles)."""
        def job():
            page = self.api.pinned(acc_id) or []
            if not page and self.cfg["feed"].get("remote_profiles", True):
                page = self._pinned_from_origin(acc_id)
            self.store.put_statuses(page)
            return page
        return self.submit(job)

    def pin(self, status, on=True):
        """Pin my post to my profile, or take it off."""
        s = real(status)

        def job():
            st = self.api.pin(s["id"], on) or dict(s, pinned=on)
            self.store.put_statuses([st])
            self.emit("status_updated", st)
            return st
        return self.submit(job)

    def bookmark(self, status, on=None):
        """Into the bookmarks or out (on=None: toggle). The Bookmarks lane follows
        at once, without waiting for the server's list."""
        s = real(status)
        on = (not s.get("bookmarked")) if on is None else on

        from . import rss

        def job():
            # an RSS item lives only here: its bookmark too
            st = dict(s, bookmarked=on) if rss.is_rss(s) else \
                self.api.bookmark(s["id"], on) or dict(s, bookmarked=on)
            self.store.put_statuses([st])
            if on:
                self.store.put_items("bookmarks", [(st["id"], st, now_iso())])
            self.emit("status_updated", st)
            self.redraw("bookmarks")
            if on and not rss.is_rss(s):
                self._follow_for("bookmarks", s)  # threads.auto = "bookmarks"
            return st
        return self.submit(job)

    def boost(self, status):
        s = real(status)
        self._on_server(s)

        def job():
            res = self.api.reblog(s["id"], not s.get("reblogged"))
            got = self._update((res or {}).get("reblog") or self.api.status(s["id"]))
            if not s.get("reblogged"):  # boosted now: threads.auto = "boosts"
                self._follow_for("boosts", s)
            return got
        return self.submit(job)

    def delete(self, status):
        s = real(status)

        def job():
            try:
                self.api.delete_status(s["id"])
            except ApiError as e:
                if e.status not in (404, 410):
                    raise
                # gone already (deleted from the server's web, another client): the
                # wish is done all the same — it goes here too, no error
                log.info("delete %s: already gone on the server (%s)", s["id"], e.status)
            self.store.delete_status(s["id"])
            self.emit("status_deleted", s["id"])
        return self.submit(job)

    def answer_follow(self, acc_id, approve):
        def job():
            if approve:
                self.api.authorize_follow(acc_id)
            else:
                self.api.reject_follow(acc_id)
            self.follow_requests = [a for a in self.follow_requests if a["id"] != acc_id]
            self.emit("requests_updated", self.follow_requests)
        return self.submit(job)

    # ---- drafts & ui state -----------------------------------------------------
    # the lanes a phone pins as tiles (its overview of lanes); kept here so that sync can
    # carry them (sync.tiles) — a desktop keeps them without showing them
    def pinned_tiles(self):
        return list(self.store.kv_get("pinned_tiles", []) or [])

    def set_pinned_tiles(self, names):
        self.store.kv_set("pinned_tiles", [str(n) for n in names])
        if self.sync:
            self.sync.record_setting("pinned_tiles")

    def get_state(self, key, default=None):
        return self.store.kv_get(f"ui.{key}", default)

    def set_state(self, key, value):
        # by the background: the interfaces set it from their own threads (the window
        # froze 21 s here, the disk busy, 29.10)
        self.store.kv_set_soon(f"ui.{key}", value)

    # ---- shutdown ----------------------------------------------------------------
    def _list_waiting(self):
        """Who waits to go into a list, by name, and why: the one thing the status
        window asks my server (who those ids are, the follow between us)."""
        pending = self._list_pending()
        if not pending:
            return []
        ids = list(dict.fromkeys(p[1] for p in pending))
        try:
            rel = {r["id"]: r for r in self.api.relationships(ids)}
        except Exception as e:  # noqa: BLE001 — offline: names only
            log.debug("list waiting: relationships: %s", e)
            rel = {}
        people = {}
        for acc_id in ids:
            known = getattr(self, "_waiting_accounts", None)
            if known is None:
                known = self._waiting_accounts = {}
            acc = self.store.account_of(acc_id) or known.get(acc_id)
            if acc is None:  # no post of theirs here: my server knows who it is (once)
                try:
                    acc = known[acc_id] = self.api.account(acc_id)
                except Exception as e:  # noqa: BLE001 — gone, or offline
                    log.debug("list waiting: account %s: %s", acc_id, e)
            people[acc_id] = acc if isinstance(acc, dict) else {}
        out = []
        for list_id, acc_id, since in pending:
            acc, r = people[acc_id], rel.get(acc_id)
            state = "unknown" if r is None else "following" if r.get("following") else \
                "requested" if r.get("requested") else "not_following"
            out.append({"id": acc_id, "account": acc.get("acct") or "",
                        "name": acc.get("display_name") or acc.get("username") or "",
                        "url": acc.get("url") or "", "state": state,
                        "list": next((x["title"] for x in self.lists if x["id"] == list_id),
                                     list_id), "since": since})
        return out

    def federation_status(self):
        """What the Debug → Federation status window shows (a future of plain data): my
        server (what it runs, how fast it answers, the stream, the polls), what keeps
        failing on it and on other servers (core.health), what it hasn't got, who waits
        to go into a list. Nothing here is asked of the network: it's what this run saw."""
        def job():
            from . import health
            snap = health.REC.snapshot()
            stream = getattr(self, "_stream", None)
            waiting = self._list_waiting()
            caps = getattr(self, "caps", None)
            return {
                "server": (self.auth or {}).get("server", ""),
                "software": getattr(caps, "software", "") if caps else "",
                "version": getattr(caps, "version", "") if caps else "",
                "me": (self.me or {}).get("acct", ""),
                "polls": {"count": self._poll_count, "last_s": self._last_poll_s,
                          "last_ok": self._last_poll_ok, "failures": self._poll_failures,
                          "last_error": self._last_poll_error,
                          "interval_s": self.cfg["poll"]["interval_seconds"]},
                "stream": None if stream is None else {
                    "open": stream.connected.is_set(), "since": stream.opened_at,
                    "last_event": stream.last_event_at, "drops": stream.drops,
                    "last_error": stream.last_error},
                "stream_mode": self.cfg["poll"].get("stream", "auto"),
                "unsupported": sorted(self.unsupported),
                "list_waiting": waiting,
                **snap,
            }
        return self.bg.submit(job)

    def store_counts(self):
        """The database's counts, for an "about this install" screen (the phone's first)."""
        return self.store.diag_counts()

    def diag_stats(self):
        """For the periodic stats line: what could grow or get stuck."""
        out = {"polls": self._poll_count, "last_poll_s": self._last_poll_s,
               "max_poll_s": round(getattr(self, "_poll_max_s", 0.0), 2),  # since last
               "pool_queue": self.pool._work_queue.qsize(),
               "bg_queue": self.bg._work_queue.qsize(),
               "lane_cache": len(self._lane_cache),
               "parents_inflight": len(self._parent_inflight),
               "replies_inflight": len(self._replies_inflight),
               "honest_checked": len(self._honest_checked),
               "lists": len(self.lists)}
        out.update(self.store.diag_counts())
        self._poll_max_s = 0.0
        return out

    EXIT_WAIT = 4.0  # seconds the exit waits, all in all, for what is still running

    def shutdown(self):
        # one deadline for everything: on a slow network each wait used to take its own
        # 3–5 s, and the exit dragged on for a quarter of a minute (28.10), holding the
        # profile's lock — "already running" when started again
        deadline = time.monotonic() + self.EXIT_WAIT
        self._stop.set()
        self._wake.set()
        if self.sync:
            self.sync.stop(wait=min(3.0, self.EXIT_WAIT))  # its last round: the marks
        if getattr(self, "_stream", None) is not None:
            self._stream.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.bg.shutdown(wait=False, cancel_futures=True)
        self.reads.shutdown(wait=False, cancel_futures=True)
        if self._poller:
            self._poller.join(timeout=max(0.1, deadline - time.monotonic()))
        # what is running already finishes (a little while) before the database closes
        # under it: no "closed database" from a badge count or a reminder at exit
        for pool in (self.pool, self.bg):
            pool.join(deadline)
        # a poll stuck in a slow request must not hold the exit: what's written is
        # committed already, an unclosed database is fine
        if self._poll_lock.acquire(timeout=max(0.1, deadline - time.monotonic())):
            try:
                self.store.close()
            finally:
                self._poll_lock.release()
        else:
            # not a problem (said as one, it looked like one in the night's log): SQLite
            # has every commit on disk, the process ending closes the file
            log.info("exit: a poll still waits for the server — not waited for; all "
                     "it stored is on disk")
