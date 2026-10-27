"""Core: everything a frontend needs, no GUI.

Network calls return concurrent.futures.Future. Events are emitted from
worker threads (see events.py):

  ready            me (account dict)        connected and ready
  lanes_updated    {lane: [new item ids]}   something new arrived / older loaded
  parents          None                     reply contexts became available
  arrived          [(id, in_reply_to_id)]   new posts from a poll (open threads grow)
  thread_grew      root id                  replies fetched from other servers
  status_updated   status                   a status changed (fav, boost…)
  status_deleted   status id
  read_changed     [status ids]
  requests_updated [accounts]
  notify           [(lane, status)]         new unread comments / mentions
  error            str
  auth_failed      str                      token no longer accepted
"""

import logging
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import requests

from .. import diag, protocols
from ..protocols.base import RateLimited
from ..protocols.mastodon import api as api_module
from ..protocols.mastodon import counters
from ..protocols.mastodon.api import ApiError, Capabilities
from ..version import USER_AGENT
from . import atoms, auth, custom, lanes, presets, search, sources, subs, taggroups, threads
from .events import Events
from .model import id_after, interaction_policy, looks_sent, narrower, real, send_key
from .social import SocialMixin
from .sounds import Chime
from .store import Store, now_iso, sort_key


class MaybeSent(Exception):
    """The server didn't answer a send in time, and couldn't say whether the post was
    made: it may be out, or not. Retrying blindly may post it twice."""
    maybe_sent = True

    def __init__(self, cause):
        from ..i18n import _
        super().__init__(_("post_maybe_sent", err=cause.__class__.__name__))

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


def _due(last, every):
    """Time to do it again? (last: monotonic seconds, None = never done). Not
    "last = 0": monotonic time starts near zero at boot, so that would wait."""
    return last is None or time.monotonic() - last > every


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
PARENTS_FIRST = 20  # parents fetched before the rules sort a round's replies


def _when_of(st):
    """The time a lane's window looks at: the boost's, else the post's."""
    from .atoms import _when
    return _when(st.get("created_at")) or _when(real(st).get("created_at"))


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

class Core(SocialMixin):
    def __init__(self, cfg, paths, api_class=None):
        self.cfg = cfg
        self.paths = paths
        # what this account's server speaks (docs/en/dev/protocols.md): the client, its errors,
        # its live stream, its objects → fedtail.model
        self.proto = protocols.get()
        self.api_class = api_class or self.proto.client
        paths.ensure()
        self.store = Store(paths.db_file)
        self.events = Events()
        # user actions never wait behind background work
        self.pool = Pool(max_workers=4, thread_name_prefix="fedtail")
        self.bg = Pool(max_workers=2, thread_name_prefix="fedtail-bg")
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
        self.browse_empty = set()  # browse sources (local, federated) the server gave nothing
        self.sources = {}
        self.lists = []           # [{"id", "title", "exclusive"}] from the server
        self.list_members = {}    # list id -> {account ids}
        self._lists_version = 0
        self._lists_checked = None  # monotonic time of the last check; None: never
        self.customs = custom.load(cfg)[0]  # free lanes, [[lanes.custom]]
        self._following = None    # account ids I follow, for the free lanes' atoms
        self._world_version = 0   # bumped when what the rules know around posts changes
        self._following_at = 0.0
        self._important_waiting = False  # "Important people" on, but nothing in it yet
        self._waiting = set()            # lanes on but hidden while empty (SHOWN_WHEN_FULL)
        self._server_filters = []        # the server's filters (v2), for filter_context
        self._unsorted_on = False        # lanes.unsorted: Unsorted collects
        self.lanes = self._shown_lanes(lanes.enabled(cfg))
        self.tag_groups = []  # [{"any", "all", "none", "name", "saved"}], see taggroups
        self.lane_by_name = {lane.name: lane for lane in self.lanes}
        self.follow_requests = []
        self._limits = {}
        self.chime = Chime(cfg, chosen=self.lane_chosen)
        self._lane_cache = {}
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
        self._active_lane = None  # the lane on screen: browse lanes are fetched only then
        self._active_lanes = set()  # all of them on screen, side by side (ui.layout)
        self._last_poll_s = None
        self._poll_failures = 0     # for the federation status
        self._last_poll_ok = None   # time.time()
        self._last_poll_error = ""
        api_module.SLOW_SECONDS = float(cfg["debug"]["slow_request_seconds"])
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
            last = seen.get(str(payload))
            if last is not None and now - last < self.ERROR_QUIET_S:
                log.debug("error again (not shown): %s", str(payload)[:200])
                return
            seen[str(payload)] = now
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
    def begin_login(self, server, redirect=None):
        """→ the server's page where the user allows fedtail. redirect: where the server
        sends the code — None: it shows it to be pasted (the desktop); an app's address
        (fedtail://oauth on a phone): it goes straight back to the app."""
        def job():
            if not api_module.cleartext_ok(server):
                # the token would cross the internet in the clear: only a server here,
                # at home (localhost, a private address, .local/.lan) may be http://
                from ..i18n import _
                raise ValueError(_("login_insecure"))
            api = self.api_class(server)
            where = {"redirect": redirect} if redirect else {}
            app = api.register_app(**where)
            self._pending_login = (api, app, where)
            return api.authorize_url(app["client_id"], **where)
        return self.submit(job)

    def finish_login(self, code, expect=None):
        """expect: (server, acct) this profile already is — logging in anew must not
        put another account into its data (read marks, drafts, lists are that one's)."""
        def job():
            api, app, where = self._pending_login
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
        from ..protocols.mastodon import probe
        last = self.store.kv_get(probe.KV)
        if isinstance(last, dict) and new.same_server(last.get("software"),
                                                       last.get("version")):
            for feature, there in probe.features(last).items():
                if feature not in new.missing and feature not in new.present:
                    new.learn(feature, there)

    def connect(self):
        def job():
            if not api_module.cleartext_ok(self.auth["server"]):
                log.warning("server is plain http on the internet: the token goes in the "
                            "clear (log in anew with https://)")
            api = self.api_class(self.auth["server"], self.auth["token"])
            me = api.me()
            try:
                v2 = api.instance_v2() if hasattr(api, "instance_v2") else None
                caps = self.proto.capabilities(api.instance(), v2)
            except Exception:  # instance info is a nicety, not a must
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

    def start_polling(self):
        if self._poller:
            return
        self._start_stream()
        self._poller = threading.Thread(target=self._poll_loop, name="fedtail-poll", daemon=True)
        self._poller.start()
        if self.sync:
            self.sync.start()

    def poll_now(self):
        self._urgent = True  # asked for (Refresh, a post sent): no waiting
        self._wake.set()

    def _poll_soon(self):
        """The live stream says something came: a poll, but not more often than
        poll.stream_gap_seconds — a busy server sends events many times a minute, and
        every poll asks each lane (a dozen requests and some CPU each time). In slow
        mode the stream wakes nothing: the news waits for its round."""
        if self.slow_minutes():
            return
        self._wake.set()

    # ---- slow mode: the news comes once every N minutes, not as it arrives ------------
    def slow_minutes(self):
        """poll.slow_minutes: 0 — news as it comes; N — a round every N minutes only
        (Refresh still asks at once), so nothing stirs between them."""
        try:
            return max(0, int(self.cfg["poll"].get("slow_minutes", 0) or 0))
        except (TypeError, ValueError):
            return 0

    def set_slow(self, minutes):
        """Slow mode for this run, at once (the place saves it in the file too)."""
        self.cfg["poll"]["slow_minutes"] = max(0, int(minutes or 0))
        self._wake.set()  # the poller works out its next round anew

    def next_round(self):
        """Slow mode: when the next round comes (time.time()), or None."""
        return self._next_round if self.slow_minutes() else None

    def slow_due(self):
        """A round now keeps to slow mode: off, or its minutes have passed since the last
        (a phone's round from the system or a push asks this first)."""
        slow = self.slow_minutes()
        last = getattr(self, "_last_poll_ok", None)
        return not slow or last is None or time.time() - last >= slow * 60 - 5

    # ---- "notify at most every N minutes", a lane's own -------------------------------
    def calm(self, name):
        """Minutes a lane's notifications and sound wait after its last (0: as they come)."""
        try:
            return max(0, int(self.get_state(f"calm.{name}", 0) or 0))
        except (TypeError, ValueError):
            return 0

    def set_calm(self, name, minutes):
        self.set_state(f"calm.{name}", max(0, int(minutes or 0)) or None)
        if not minutes:
            self._calm_last.pop(name, None)

    # ---- "of them new": what the last update brought, still unread ---------------------
    def fresh_count(self, name):
        """How many of a lane's unread came with the last update that brought anything."""
        got = self._fresh.get(name)
        if not got:
            return 0
        if name == "activity":
            return min(len(got), int(self.activity_unread() or 0))
        if name == "requests":
            return len(got & {a["id"] for a in self.follow_requests or ()})
        entries = [e for e in self.lane_entries(name) if e[0] in got]
        return len(self.unread_ids(entries)) if entries else 0

    def _start_stream(self):
        """poll.stream: the server's live stream wakes the poller when something
        arrives. The stream itself fetches nothing: the poll does, as always."""
        if self.cfg["poll"].get("stream", "auto") == "off" or not self.auth or \
                not getattr(self.api, "has_stream", False):  # a test's fake API has none
            return
        stream = self.proto.stream
        base = self._stream_url()
        if not base:
            return

        def on_event(name):
            if name in stream.WAKE_ON:
                log.debug("stream: %s", name)
                self._poll_soon()
        self._stream = stream.Stream(base, self.auth["token"], on_event,
                                     user_agent=USER_AGENT)
        self._stream.start()

    def _stream_url(self):
        """Where the stream is, with the token: my server's own (or the host it names
        for it, on the same site), over TLS only. None: no stream, polling does it."""
        stream = self.proto.stream
        server = self.auth["server"]
        if not server.startswith("https://"):  # the token in the clear: polling only
            log.warning("stream: off, the server is not https")
            return None
        base = self.caps.streaming or server
        if not stream.same_site(base, server):  # the token goes to my server only
            log.warning("stream: the server names another site for it; using its own")
            base = server
        base = base.replace("https://", "wss://", 1)
        if not base.startswith("wss://"):  # http://, ws://, no scheme: never in the clear
            base = "wss://" + base.split("://")[-1]
        return base

    def pause_polling(self, on=True):
        """Out of sight (a phone's app in the background): no rounds until resumed; a
        resume polls at once. The desktop never pauses."""
        self._paused = on
        if not on:
            self.poll_now()

    def _poll_loop(self):
        while not self._stop.is_set():
            if getattr(self, "_paused", False):
                self._wake.wait(60)
                self._wake.clear()
                continue
            try:
                self.poll_once()  # counts the rounds failing in a row itself
            except RateLimited as e:  # the server says wait: _pace() waits, said once
                log.info("poll: the server's limit is spent (%s) — the round cut short", e)
            except Exception as e:  # never let the poller die silently
                if self._stop.is_set():
                    return
                log.exception("poll failed")
                self._poll_failures += 1
                self._last_poll_error = f"{time.strftime('%H:%M')} {e.__class__.__name__}"
                self.emit("error", str(e))
            quiet = self._pace()
            if quiet > 0:
                # the server's budget is nearly spent: nothing until its window starts
                # anew — a Refresh doesn't cut it short (it would only earn a 429)
                self._stop.wait(quiet)
                continue
            done = time.monotonic()
            back = self.backoff()
            if back:  # failing round after round: wait longer each time (Refresh still asks)
                self._wake.wait(back)
                self._wake.clear()
                self._urgent = False
                continue
            if self.slow_minutes():
                self._slow_wait(done)
                continue
            self._next_round = None
            if self._nap(float(self.cfg["poll"]["interval_seconds"])):
                self._urgent = True  # back from sleep: what came meanwhile, at once
            self._wake.clear()
            gap = float(self.cfg["poll"].get("stream_gap_seconds", 10))
            left = gap - (time.monotonic() - done)
            if not getattr(self, "_urgent", False) and left > 0 and not self._stop.is_set():
                # woken by the stream right after a poll: gather what else comes meanwhile
                self._wake.wait(left)  # Refresh still cuts it short
                self._wake.clear()
            self._urgent = False

    def _slow_wait(self, done):
        """Slow mode: sleep till the round is due — the stream doesn't wake it, Refresh
        does; slow mode changed meanwhile: the wait worked out anew."""
        while not self._stop.is_set():
            slow = self.slow_minutes()
            if not slow:
                break
            end = done + slow * 60
            self._next_round = time.time() + max(0.0, end - time.monotonic())
            left = end - time.monotonic()
            if left <= 0:
                break
            self._wake.wait(left)
            self._wake.clear()
            if getattr(self, "_urgent", False):
                break
        self._urgent = False

    NAP_STEP = 30  # s: how often a wait looks whether the computer slept meanwhile

    def _nap(self, seconds, clock=time.time, mono=time.monotonic):
        """Wait for the next round (a wake — Refresh, the stream — ends it early). True:
        the computer slept meanwhile (the wall clock went on far more than the monotonic
        one, which stands still in a suspend) — the wait ends then too: the news of the
        night comes on waking, not a round later."""
        end = mono() + seconds
        while True:
            left = end - mono()
            if left <= 0:
                return False
            w0, m0 = clock(), mono()
            if self._wake.wait(min(left, self.NAP_STEP)):
                return False
            if (clock() - w0) - (mono() - m0) > self.NAP_STEP:
                log.info("poll: the computer slept — a round now")
                return True

    BACKOFF_MAX = 15 * 60  # s: the longest wait between failing rounds

    def backoff(self):
        """Seconds to wait before the next round after rounds failed in a row (the server
        down, no network): the interval doubled each time — 90 s, 3, 6, 12 min — up to
        BACKOFF_MAX; 0 when the last round went through."""
        n = getattr(self, "_fails_in_row", 0)
        if n < 2:
            return 0
        base = float(self.cfg["poll"]["interval_seconds"])
        return min(self.BACKOFF_MAX, base * 2 ** min(n - 1, 10))

    RESERVE = 20  # requests kept for what I do by hand (a like, a reply), besides a round
    RESET_MARGIN = 5  # seconds after the server's window ends before asking again

    def _pace(self):
        """Seconds to keep quiet before the next round: the server's rate limit (its
        X-RateLimit headers) nearly spent — fewer left than two rounds and RESERVE — or
        spent. 0: go on as usual. Says so once a window (event rate_limited)."""
        budget = getattr(self.api, "budget", None)
        if budget is None:
            return 0
        # the dearest of the last rounds: a round cut short by a 429 cost 1 and let a
        # whole one start with 9 left (the night of 22.10: 429 again three minutes on)
        per_round = max(getattr(self, "_round_costs", None) or [0])
        if not (budget.spent() or budget.low(2 * per_round + self.RESERVE)):
            return 0
        # the server's window ends a little after its X-RateLimit-Reset says: it still
        # answered 429 right at it
        wait = max(0.0, budget.reset - time.time() + self.RESET_MARGIN)
        if wait and getattr(self, "_quiet_said", None) != budget.reset:
            self._quiet_said = budget.reset
            log.info("rate limit: %d of %d left, a round takes %d — quiet for %.0f s",
                     budget.remaining, budget.limit, per_round, wait)
            self.emit("rate_limited", {"until": budget.reset, "left": budget.remaining,
                                       "limit": budget.limit})
        return min(wait, 15 * 60)  # a clock gone wrong never stops polling for good

    def poll_once(self):
        """One round: catch every source up, check subscriptions, lists, activity,
        follow requests; then tell the frontend. Logged with its timing."""
        if not self.api:
            return
        before = getattr(self.api, "requests", 0)
        t = time.monotonic()
        self._steps = {}
        self._step_at = t
        self._polling = True
        self.emit("poll_state", True)  # "updating the lanes…" where the window shows it
        try:
            got = self._poll_once()
            self._last_poll_ok = time.time()
            self._fails_in_row = 0
            return got
        except RateLimited:  # the server asks to wait: not a failure of the network
            raise
        except Exception:
            self._fails_in_row = getattr(self, "_fails_in_row", 0) + 1
            raise
        finally:
            self._polling = False
            self.emit("poll_state", False)
            took = time.monotonic() - t
            self._round_requests = getattr(self.api, "requests", 0) - before
            costs = getattr(self, "_round_costs", None)
            if costs is None:
                costs = self._round_costs = []
            costs.append(self._round_requests)
            del costs[:-6]  # the last six rounds
            self._poll_count += 1
            self._last_poll_s = round(took, 2)
            self._poll_max_s = max(getattr(self, "_poll_max_s", 0.0), took)
            slow = float(self.cfg.get("debug", {}).get("slow_request_seconds", 5) or 5)
            # a slow poll says where the time went: which source, the store, markers…
            steps = ", ".join(f"{k} {v:.2f}" for k, v in
                              sorted(self._steps.items(), key=lambda kv: -kv[1])[:6]
                              if v >= 0.05)
            level = logging.WARNING if took > 60 else logging.INFO if took > slow \
                else logging.DEBUG
            log.log(level, "poll #%d took %.2f s%s", self._poll_count, took,
                    f" ({steps})" if steps and took > slow else "")
            if self._poll_count == 1:  # the window said "getting the lanes…": done now
                self.emit("first_poll_done", None)

    def poll_state(self):
        """Is a round going on, when did the last one come through, how many failed in
        a row since: what the window says of the lanes' freshness (common/sidebar.py
        poll_words) — so an empty lane reads as "nothing new", not "is it broken?"."""
        ok = getattr(self, "_last_poll_ok", None)
        return {"busy": bool(getattr(self, "_polling", False)), "ok_at": ok,
                "failing": int(getattr(self, "_fails_in_row", 0) or 0)}

    def _step(self, name):
        """Poll timing: the time since the last step goes to name (summed)."""
        now = time.monotonic()
        steps = getattr(self, "_steps", None)
        if steps is not None:
            steps[name] = steps.get(name, 0.0) + now - getattr(self, "_step_at", now)
        self._step_at = now

    def _poll_once(self):
        with self._poll_lock:
            first_run = not self.store.kv_get("initialized", False)
            fc = self.cfg["feed"]
            new_by_source = {}
            browse_changed = set()  # browse sources that turned empty or stopped being so
            every = self.cfg["lists"]["refresh_minutes"] * 60
            self._step("start")
            if _due(self._silence_checked, every):
                try:
                    self._refresh_silence()
                except Exception as e:  # an old server without mutes/blocks: never mind
                    self._silence_checked = time.monotonic()
                    log.warning("silence: %s", e)
            if self.cfg["lists"]["enabled"] and _due(self._lists_checked, every):
                try:
                    self._refresh_lists()
                except Exception as e:  # try again next round, not every poll
                    self._lists_checked = time.monotonic()
                    self.emit("error", f"lists: {e}")
            # not in the first rounds (a start asks enough); the time kept in the store,
            # so short sessions still get to it
            if self.cfg["feed"].get("forget_unfollowed", True) and self._poll_count >= 2 \
                    and time.time() - float(self.store.kv_get("home_followed_at", 0) or 0) \
                    > self.UNFOLLOW_CHECK_S:
                self.store.kv_set("home_followed_at", time.time())
                try:
                    self._forget_unfollowed_elsewhere()
                except Exception as e:  # noqa: BLE001 — next time; never the round
                    log.info("unfollowed elsewhere: %s", e)
            self._step("silence+lists")
            if "direct" in self.lane_by_name:
                self.sync_conversations()  # read here = read on the server (social.py)
                self._step("conversations")
            # followed threads: for their lane, and for Home's "threads with news"
            if "subs" in self.lane_by_name or self._needs_threads():
                try:
                    sc = self.cfg["subs"]
                    new_by_source["subs"] = subs.check(
                        self.store, self.api, self.me["id"], sc["interval_minutes"],
                        sc["active_days"], sc["max_threads"])
                except Exception as e:
                    self.emit("error", f"subs: {e}")
                self._step("subs")
            lazy = {lane.source for lane in self.lanes if lane.lazy}
            # a lane read through needs its sources caught up, even Local's
            lazy -= {lane.source for lane in self.lanes if not lane.lazy} | \
                {f for lane in self.lanes if lane.feeds and not lane.lazy for f in lane.feeds}
            open_names = [n for n in {self._active_lane, *self._active_lanes}
                          if n in self.lane_by_name]
            open_sources = {self.lane_by_name[n].source for n in open_names} | \
                {f for n in open_names for f in self.lane_by_name[n].feeds}
            needed = lanes.sources_needed(self.lanes) + \
                (["watched"] if self._important_waiting else [])
            for name in needed:
                if name not in self.sources and self.api is not None:
                    # a stream named by a lane's rule (account:, link:, quotes:, remote:)
                    src = sources.prefixed_source(self.api, name, remote=self.wider.remote_lane)
                    if src is not None:
                        self.sources[name] = src
                if name not in self.sources:
                    continue
                if name in lazy:  # browse lanes: only while open, newest page only
                    if name not in open_sources:
                        continue
                    try:
                        keep = int(self.cfg["lanes"].get("browse_keep", 200))
                        new_by_source[name] = sources.refresh_top(
                            self.store, self.sources[name], fc["page_size"], keep)
                        # the newest `keep`, and what "Older" brought into an open lane
                        shown = max((self._limits.get(x.name, 0) for x in self.lanes
                                     if x.source == name), default=0)
                        self.store.prune(name, max(keep, shown - fc["render_limit"] + keep))
                        # the server answered, and with nothing: its live feeds are off
                        # (mastodon.social and others do that) — the lane says so
                        empty = getattr(self.sources[name], "last_count", 1) == 0
                        if empty != (name in self.browse_empty):
                            (self.browse_empty.add if empty else self.browse_empty.discard)(name)
                            browse_changed.add(name)  # its lane says so (see below)
                    except Exception as e:
                        self.emit("error", f"{name}: {e}")
                    continue
                try:
                    new_by_source[name] = sources.catch_up(
                        self.store, self.sources[name], fc["page_size"], fc["catch_up_limit"])
                    self._step(name)
                    self.store.prune(name, self.keep_per_lane())
                    self._step("prune")
                except ApiError as e:
                    if e.status in (401, 403):
                        self.emit("auth_failed", str(e))
                        return
                    self.emit("error", f"{name}: {e}")
                except Exception as e:  # network down etc.
                    self.emit("error", f"{name}: {e}")

            self._step("sources")
            # other servers' public lanes and tags (lanes.federated_extra, tags_extra)
            fed_open = "federated" in open_sources
            if self.wider.due(fed_open):
                self.bg.submit(self.wider.run, fed_open)
            if "direct" in self.lane_by_name and self._carry_my_direct():
                self.emit("lanes_updated", {"direct": []})  # read already: no news, no sound
            self._step("my direct")
            new_requests = []
            if "requests" in self.lane_by_name or self._requests_in_activity():
                try:
                    self.follow_requests = self.api.follow_requests() or []
                    ids = {a["id"] for a in self.follow_requests}
                    if self._known_requests is not None:
                        new_requests = [a for a in self.follow_requests
                                        if a["id"] not in self._known_requests]
                    changed = ids != self._known_requests
                    self._known_requests = ids
                    if changed:  # not every poll: the tab would be rebuilt for nothing
                        self._warm_lanes()  # the window counts every lane on this too
                        self.emit("requests_updated", self.follow_requests)
                        if self._requests_in_activity():
                            self.emit("activity_updated", len(new_requests))
                except Exception as e:
                    self.emit("error", f"requests: {e}")

            new_activity = []
            if "activity" in self.lane_by_name or self._event_lanes():
                try:
                    new_activity = self._poll_activity()
                    if new_activity:
                        self._warm_lanes()  # the window counts every lane on this event
                        self.emit("activity_updated", len(new_activity))
                        events_in = {c.name: [] for c in self._event_lanes()}
                        if events_in:  # lanes showing likes, follows…: they look again
                            self.emit("lanes_updated", events_in)
                except Exception as e:
                    self.emit("error", f"activity: {e}")

            if self.derived.due():  # a snapshot of my followers, in the background
                self.bg.submit(self.derived.run)
            self._step("requests+activity")
            self._warm_lanes()  # before the window hears: it finds them made
            new_statuses = self._new_statuses(new_by_source)
            self._ask_prefetch(new_statuses)
            mine = [st["id"] for st in new_statuses if st["account"]["id"] == self.me["id"]]
            if first_run and fc["first_run_mark_read"]:
                # what another client (fedtail on another machine, the server's web) has
                # left unread stays unread: everything read was this machine's first start
                # telling the server "all read" with its next marker (22.10: a new Windows
                # install moved the Linux one's place by fifty posts)
                keep = self._unread_by_marker(new_statuses)
                self.store.mark_read([st["id"] for st in new_statuses if st["id"] not in keep])
            elif mine:
                self.store.mark_read(mine)
            # a post I replied to (from any client) counts as read
            answered = [st["in_reply_to_id"] for st in new_statuses
                        if st["account"]["id"] == self.me["id"] and st.get("in_reply_to_id")]
            if answered and not first_run:
                self.mark_read(answered)
            if first_run:
                self.store.kv_set("initialized", True)
            else:
                self._auto_subscribe([st for st in new_statuses
                                      if st["account"]["id"] == self.me["id"]])

            self._step("read marks")
            # rules that ask about the parent (a reply to my post or to a comment, whose
            # reply it is) sort a reply only once its parent is known: fetched first
            # (feeds.md §8, "atoms known late"), a few at most — the rest come after
            if any(c.routed and {"parent", "me"} & set(c.needs) for c in self.customs):
                self._fetch_parents([st for st in new_statuses
                                     if real(st).get("in_reply_to_id")][:PARENTS_FIRST])
            new_by_source.update(self._route_custom(new_by_source))
            self._show_important()  # after routing: Unsorted may have got its first
            per_lane = self._split_by_lane(new_by_source)
            if not first_run:
                self._note_fresh(per_lane, new_requests, new_activity)
            if any(per_lane.values()):
                self.emit("lanes_updated", per_lane)
            if browse_changed:  # an empty answer brings no news, but the lane must say why
                self.emit("lanes_updated", {lane.name: [] for lane in self.lanes
                                            if lane.source in browse_changed})
            if new_statuses and not first_run:
                self.emit("arrived", [(real(st)["id"], real(st).get("in_reply_to_id"))
                                      for st in new_statuses])
            self._step("lanes")
            if not first_run:
                self._notify(per_lane, new_requests, new_activity)
                self._step("notify")
                self._sync_markers()
                self._step("markers")
            self._fetch_parents(new_statuses)
            self._step("parents")
            if _due(self._gc_done, max(1, self.cfg["storage"]["gc_hours"]) * 3600):
                self.collect_garbage()
                self._step("gc")
            got = {k: len(v) for k, v in new_by_source.items() if v}
            if got or new_activity or new_requests:
                log.info("new: %s%s%s", got or "-",
                         f" activity+{len(new_activity)}" if new_activity else "",
                         f" requests+{len(new_requests)}" if new_requests else "")

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
    MARKERS = {"home": "home", "notifications": "mentions"}  # marker timeline -> our source

    def _unread_by_marker(self, statuses):
        """First start: the ids newer than where the server's home marker says reading
        stopped (read.sync_markers) — they stay unread; the marker is taken as known,
        so the next round doesn't push "all read" over it. No marker, no server answer:
        nothing kept (all read, as feed.first_run_mark_read says)."""
        if not self.cfg["read"].get("sync_markers", True):
            return set()
        try:
            remote = self.api.markers(("home",))
        except Exception as e:  # noqa: BLE001 — an old server without markers
            log.info("markers at first start: %s", e)
            return set()
        last = ((remote or {}).get("home") or {}).get("last_read_id")
        if not last:
            return set()
        self.store.kv_set("marker.home", last)
        keep = {st["id"] for st in statuses if id_after(st["id"], last)}
        log.info("first start: read up to %s elsewhere, %d newer stay unread", last,
                 len(keep))
        return keep

    def _sync_markers(self):
        """Pull: what another client marked as read up to its marker is read here too.
        Push: how far everything is read here, from the oldest on, goes to the server.
        (read.sync_markers)"""
        if not self.cfg["read"].get("sync_markers", True):
            return
        try:
            remote = self.api.markers(tuple(self.MARKERS))
        except Exception as e:  # noqa: BLE001 — an old server without markers: just skip
            log.info("markers: %s", e)
            return
        push = {}
        for timeline, source in self.MARKERS.items():
            # oldest -> newest; the server's own items only (not mine put in "Direct")
            items = [x for x in self.store.items(source, 400)
                     if not str(x[0]).startswith("mine:")]
            if not items:
                continue
            last = ((remote or {}).get(timeline) or {}).get("last_read_id")
            seen_key = f"marker.{timeline}"
            if last and last != self.store.kv_get(seen_key):
                older = [st["id"] for item, st in items if not id_after(item, last)]
                fresh = [i for i in older if i not in self.store.read_set(older)]
                if fresh:
                    log.info("markers: %s read up to %s elsewhere: %d here", timeline, last,
                             len(fresh))
                    self.mark_read(fresh)
                self.store.kv_set(seen_key, last)
            read = self.store.read_set(st["id"] for _i, st in items)
            mine = None
            for item, st in items:
                if st["id"] not in read:
                    break
                mine = item
            if mine and (not last or id_after(mine, last)):
                push[timeline] = mine
        if push:
            try:
                self.api.set_markers(push)
                for timeline, mine in push.items():
                    self.store.kv_set(f"marker.{timeline}", mine)
                log.debug("markers: read up to %s", push)
            except Exception as e:  # noqa: BLE001
                log.info("markers: can't set: %s", e)

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
        if new_activity:
            got["activity"] = {str(n.get("id")) for n in new_activity if isinstance(n, dict)} \
                or {str(i) for i in range(len(new_activity))}
        if new_requests:
            got["requests"] = {a["id"] for a in new_requests}
        if got:
            self._fresh = got

    # lanes shown only while something is in them: their stream decides (still filled while
    # hidden — once there is, they show, lists_changed redraws the sidebar)
    SHOWN_WHEN_FULL = {"important": "watched", lanes.UNSORTED: lanes.UNSORTED}

    def _shown_lanes(self, built):
        """The lanes as built, without "Important people" and "Unsorted" while nothing
        is in them."""
        self._waiting = {x.name for x in built if x.name in self.SHOWN_WHEN_FULL
                         and self.store.count_items(self.SHOWN_WHEN_FULL[x.name]) == 0}
        self._important_waiting = "important" in self._waiting
        self._unsorted_on = any(x.name == lanes.UNSORTED for x in built)
        return [x for x in built if x.name not in self._waiting]

    def _show_important(self):
        """A lane waiting to have something has it now: the lanes anew. (One emptied
        stays till the next start: a lane must not vanish under the reader.)"""
        if any(self.store.count_items(self.SHOWN_WHEN_FULL[n]) for n in self._waiting):
            self._apply_lists(list(self.lists), self.list_members)

    # ---- free lanes (core/custom.py) ---------------------------------------------------
    FOLLOWING_EVERY_S = 6 * 3600
    FOLLOWING_PAGES = 25

    def _refresh_following(self):
        """Whom I follow and which tags, for atoms like author = "followed" (every 6 hours;
        kept in the store between runs)."""
        if self._following is None:
            kept = self.store.kv_get("custom_following") or {}
            self._following = set(kept.get("ids") or ())
            self._following_at = float(kept.get("at") or 0)
            if kept.get("tags") is not None and \
                    getattr(self, "_followed_tag_names", None) is None:
                self._followed_tag_names = set(kept["tags"])
        if time.time() - self._following_at < self.FOLLOWING_EVERY_S:
            return
        self._following_at = time.time()
        ids, max_id, accounts = set(), None, {}
        try:
            for _ in range(self.FOLLOWING_PAGES):
                page, max_id = self.api.following(self.me["id"], max_id)
                ids |= {a["id"] for a in page or ()}
                accounts.update({a["id"]: a for a in page or ()})
                if not max_id or not page:
                    break
            tags = {t["name"] for t in self.api.followed_tags() or () if t.get("name")}
        except Exception as e:  # noqa: BLE001 — the old sets stay; next time
            log.info("free lanes: whom I follow: %s", e)
            return
        if (ids, tags) != (self._following, getattr(self, "_followed_tag_names", None)):
            self._world_version += 1  # the lanes' rules see another world: drawn anew
        if self._following and ids - self._following:  # followed since (here or elsewhere)
            self._my_follows([accounts[i] for i in sorted(ids - self._following)][:50])
        self._following, self._followed_tag_names = ids, tags
        self.store.kv_set("custom_following", {"ids": sorted(ids), "tags": sorted(tags),
                                               "at": self._following_at})

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

        lc = self.cfg["lanes"]
        host = urllib.parse.urlsplit(getattr(self.api, "base", "") or "").hostname or ""
        return atoms.World(me_id=self.me["id"] if self.me else "", my_host=host,
                           following=self._following or set(),
                           followed_tags=getattr(self, "_followed_tag_names", None) or set(),
                           extra_bots=tuple(lc["extra_bots"]), read=_Read(),
                           parents=_Parents(), new_replies=_News(),
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
        if new_requests:
            fresh.append("requests")
            if self._notify_wanted("requests", wanted, never):
                out += [("requests", acc) for acc in new_requests]
        if new_activity:
            fresh.append("activity")
            if self._notify_wanted("activity", wanted, never):
                out += [("activity", n) for n in new_activity]
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

    def lane_rank(self, name):
        """How personal a lane is, for one notification a post (feeds.md §5): 0 private,
        1 replies to me, 2 mentions, 3 followed threads, 4 the rest."""
        if name == "direct":
            return 0
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
            if name in ("requests", "activity") or not isinstance(x, dict):
                continue
            sid = real(x).get("id")
            rank = self.lane_rank(name)
            if sid not in best or rank < best[sid][0]:
                best[sid] = (rank, i)
        keep = {i for _r, i in best.values()}
        return [(n, x) for i, (n, x) in enumerate(out)
                if n in ("requests", "activity") or not isinstance(x, dict) or i in keep]

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
    def _poll_activity(self):
        """New notifications of the chosen kinds. The very first fetch is history,
        not news: it is stored as already seen."""
        types = list(self.cfg["activity"]["types"])
        if self.cfg["activity"].get("approvals", True):  # GoToSocial: waiting for my yes
            types += ["pending.reply", "pending.favourite", "pending.reblog"]
        if self.cfg["activity"].get("server_notices", True):  # Mastodon 4.3+
            types += ["severed_relationships", "moderation_warning"]
        fc = self.cfg["feed"]
        newest, _sort = self.store.activity_newest(server=True)
        if newest is None:
            self.store.activity_put(self._notifications(types, limit=fc["page_size"]))
            self.store.kv_set("activity_seen", self.store.activity_newest()[1])
            return []
        new, cursor = [], newest
        while True:
            page = self._notifications(types, limit=fc["page_size"], min_id=cursor)
            if not page:
                break
            new += self.store.activity_put(page)
            nxt = max(page, key=lambda n: sort_key(n.get("created_at"), n["id"]))["id"]
            if nxt == cursor or len(page) < fc["page_size"] or len(new) >= fc["catch_up_limit"]:
                break
            cursor = nxt
        return new

    def _notifications(self, types, **page):
        """A page of notifications: the server's own groups where it has them
        (activity.server_groups, Mastodon 4.3+), else one by one (GoToSocial, older
        Mastodon, Akkoma) — the first "no such thing" answer settles it for the run."""
        if self.cfg["activity"].get("server_groups", True) and self.supports("grouped") \
                and hasattr(self.api, "notification_groups"):
            from .social import NotSupported
            try:
                return self._api("grouped", self.api.notification_groups, types, **page)
            except NotSupported:
                log.info("no grouped notifications on this server: one by one")
        return self.api.notifications(types, **page)

    def activity_entries(self, limit=300):
        """Activity newest first; with activity.requests the follow requests on top, as
        entries waiting for a yes (social.FOLLOW_REQUEST ids, answered by the buttons)."""
        got = self.store.activity_recent(limit)
        if self._requests_in_activity():
            from .social import FOLLOW_REQUEST
            got = [{"id": FOLLOW_REQUEST + a["id"], "type": "follow_request", "account": a,
                    "created_at": a.get("created_at") or "", "sort": "~" + a["id"]}
                   for a in self.follow_requests or ()] + list(got)
        return got

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

    def _event_lanes(self):
        """The lanes shown that take events too (a condition with `event`)."""
        return [c for c in self.customs if c.event_conds and c.name in self.lane_by_name]

    def lane_events(self, name, limit=200):
        """[notification] newest first: the events (likes, boosts, follows…) a lane of
        rules shows among its posts (feeds.md §2.3) — from what Activity has stored."""
        c = next((c for c in self.customs if c.event_conds and c.name == name), None)
        if c is None or name not in self.lane_by_name:
            return []
        which = self.lane_filter(name)
        key = (self.store.activity_newest(), self.store.activity_count_after(""),
               self._world_version, self._lists_version, limit, which)
        cache = self.__dict__.setdefault("_events_cache", {})
        hit = cache.get(name)
        if hit and hit[0] == key:
            return hit[1]
        world, quiet = self._world(), self.muted | self.blocked
        got = [n for n in self.store.activity_recent(max(limit * 3, 300))
               if (n.get("account") or {}).get("id") not in quiet
               and c.takes_event(n, world, which)][:limit]
        cache[name] = (key, got)
        return got

    def activity_filters(self):
        """Activity's quick filters that can show something here: "requests" — when follow
        requests stand in Activity (no lane of their own) or approvals wait there
        (activity.approvals); "mine" — with activity.my_follows."""
        from .view import ACTIVITY_FILTERS
        a = self.cfg["activity"]
        out = []
        for k in ACTIVITY_FILTERS:
            if k == "requests" and not (self._requests_in_activity() or a.get("approvals")):
                continue
            if k == "mine" and not a.get("my_follows", True):
                continue
            out.append(k)
        return out

    def _requests_in_activity(self):
        """Follow requests stand in Activity — when it's on and there's no lane of their
        own (then they'd be there twice, and counted twice)."""
        return bool(self.cfg["activity"].get("requests", True)) and \
            "activity" in self.lane_by_name and "requests" not in self.lane_by_name

    def activity_seen_mark(self):
        return self.store.kv_get("activity_seen", "")

    def activity_unread(self):
        waiting = len(self.follow_requests or ()) if self._requests_in_activity() else 0
        return self.store.activity_count_after(self.activity_seen_mark()) + waiting

    def mark_activity_seen(self, upto=None):
        """Seen up to this entry's sort (what came on screen), or everything (None: the
        "all read" button). The mark only goes forward."""
        newest = self.store.activity_newest()[1]
        if upto is not None:
            newest = min(newest, upto) if newest else ""
        if newest and newest > self.activity_seen_mark():
            self.store.kv_set("activity_seen", newest)
            self.emit("activity_seen", newest)

    # ---- lists ---------------------------------------------------------------------
    # ---- silence: muted and blocked people, server filters ----------------------------
    def _refresh_silence(self):
        try:  # the server's filters, by their words (a lane's filter_context)
            got = [f for f in self.api.filters() or () if isinstance(f, dict)]
        except Exception as e:  # noqa: BLE001 — what we had stays
            log.debug("filters: %s", e)
            got = self._server_filters
        if got != self._server_filters:
            self._server_filters = got
            self._silence_version += 1
        muted = {a["id"] for a in self.api.mutes()}
        blocked = {a["id"] for a in self.api.blocks()}
        domains = self._domain_blocks()
        self._silence_checked = time.monotonic()
        if (muted, blocked, domains) != (self.muted, self.blocked, self.blocked_domains):
            self.muted, self.blocked, self.blocked_domains = muted, blocked, domains
            self._silence_version += 1
            self.emit("lanes_updated", {lane.name: [] for lane in self.lanes})

    def _domain_blocks(self):
        """My blocked servers; a server without the endpoint (GoToSocial for users) is
        asked once a run, not on every silence refresh."""
        if not self.supports("domain_blocks"):
            return self.blocked_domains
        try:
            return {d.lower() for d in self._api("domain_blocks", self.api.domain_blocks)}
        except Exception as e:  # noqa: BLE001 — not there, or down: what we had
            log.debug("domain blocks: %s", e)
            return self.blocked_domains

    def silenced(self, status):
        """Is this post hidden: its author or booster muted/blocked, or a server
        filter says "hide"?"""
        quiet = self.muted | self.blocked
        s = real(status)
        if self.hidden_posts and (s.get("id") in self.hidden_posts
                                  or status.get("id") in self.hidden_posts):
            return True
        if s["account"]["id"] in quiet or status["account"]["id"] in quiet:
            return True
        if self.blocked_domains and any(
                (a.get("acct") or "").partition("@")[2].lower() in self.blocked_domains
                for a in (s["account"], status["account"])):
            return True
        if self.cfg["ui"]["arts_mode"]:
            return False  # server filters don't hide anything in arts mode
        return any((f.get("filter") or {}).get("filter_action") == "hide"
                   for f in s.get("filtered") or [])

    def mute(self, acc_id, on=True, duration=0, notifications=True):
        """duration: seconds until the mute ends by itself (0 — for good); notifications:
        theirs muted too, or still coming (a mute of their posts only)."""
        if not on or (not duration and notifications):
            return self._silence(self.api.mute, self.muted, acc_id, on)
        return self._silence(lambda a, o: self.api.mute(a, o, duration=duration,
                                                         notifications=notifications),
                             self.muted, acc_id, on)

    def block(self, acc_id, on=True):
        if on:
            self.derived.mark_mine(acc_id)  # a block ends their follow: my doing
        return self._silence(self.api.block, self.blocked, acc_id, on)

    def _silence(self, call, bucket, acc_id, on):
        def job():
            rel = call(acc_id, on)
            (bucket.add if on else bucket.discard)(acc_id)
            self._silence_version += 1
            self.emit("lanes_updated", {lane.name: [] for lane in self.lanes})
            return rel
        return self.submit(job)

    def block_domain(self, domain, on=True):
        """Hide a whole server: nobody from there in any lane, no follows across."""
        domain = domain.lower()

        def job():
            self.api.block_domain(domain, on)
            (self.blocked_domains.add if on else self.blocked_domains.discard)(domain)
            self._silence_version += 1
            self.emit("lanes_updated", {lane.name: [] for lane in self.lanes})
            return domain
        return self.submit(job)

    FILTER_POLICY = ("for_not_following", "for_not_followers", "for_new_accounts",
                     "for_private_mentions", "for_limited_accounts")

    def filtered(self):
        """Notifications my server holds back (Mastodon 4.3+). Future:
        {"policy": {key: "accept"|"filter"|"drop"} or None, "requests": [...]};
        None when the server has no such thing (GoToSocial, older Mastodon)."""
        def job():
            if not self.supports("notification_policy"):
                return None
            try:
                policy = self._api("notification_policy", self.api.notification_policy) or {}
                requests = self.api.notification_requests()
            except ApiError as e:
                log.debug("filtered notifications: %s", e)
                return None
            return {"policy": {k: policy[k] for k in self.FILTER_POLICY if k in policy},
                    "pending": (policy.get("summary") or {}).get("pending_requests_count",
                                                                 len(requests)),
                    "requests": requests}
        return self.submit(job)

    def answer_filtered(self, rid, accept):
        """Let one held-back sender through (their notifications arrive) or drop them."""
        def job():
            self.api.answer_notification_request(rid, accept)
            if accept:
                self.poll_now()
        return self.submit(job)

    def set_filter_policy(self, **changes):
        bad = {k: v for k, v in changes.items()
               if k not in self.FILTER_POLICY or v not in ("accept", "filter", "drop")}
        if bad:
            raise ValueError(f"filter policy: {bad}")
        return self.call_api("set_notification_policy", **changes)

    def announcements(self):
        """The server's announcements not dismissed yet, oldest first; [] when
        ui.announcements is "off" or the server has none (GoToSocial: no such API)."""
        def job():
            if self.cfg["ui"]["announcements"] == "off" or not self.api:
                return []
            try:
                got = self.api.announcements()
            except ApiError as e:
                log.debug("announcements: %s", e)
                return []
            fresh = [a for a in got if not a.get("read")]
            return sorted(fresh, key=lambda a: a.get("published_at") or "")
        return self.submit(job)

    def dismiss_announcement(self, aid):
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

    def filters(self):
        return self.call_api("filters")

    def silenced_people(self):
        """{"muted": [accounts], "blocked": [accounts]} for the Silence dialog."""
        def job():
            muted, blocked = self.api.mutes(), self.api.blocks()
            self.muted = {a["id"] for a in muted}
            self.blocked = {a["id"] for a in blocked}
            self.blocked_domains = self._domain_blocks()
            return {"muted": muted, "blocked": blocked,
                    "domains": sorted(self.blocked_domains)}
        return self.submit(job)

    def add_filter(self, title, keywords, action="warn", contexts=None, expires_in=None):
        """expires_in: seconds until the filter ends by itself (None — never)."""
        args = (title, keywords, action) + ((tuple(contexts),) if contexts else ())
        if expires_in:
            return self.call_api("create_filter", *args, expires_in=int(expires_in))
        return self.call_api("create_filter", *args)

    def delete_filter(self, filter_id):
        return self.call_api("delete_filter", filter_id)

    def edit_filter(self, filter_id, title=None, words=None, action=None, contexts=None,
                    expires_in=None):
        """Change a filter of mine: words — the whole list it should have now (those gone
        are dropped, the new added); expires_in: seconds from now, 0 — for good, None —
        as it was."""
        def job():
            remove, add = (), ()
            if words is not None:
                have = next((f for f in self.api.filters() or []
                             if str(f.get("id")) == str(filter_id)), None)
                if have is None:
                    raise LookupError(filter_id)
                old = {k.get("keyword"): k.get("id") for k in have.get("keywords") or ()}
                want = [w for w in dict.fromkeys(x.strip() for x in words) if w]
                remove = tuple(kid for kw, kid in old.items() if kw not in want)
                add = tuple(w for w in want if w not in old)
            return self.api.update_filter(filter_id, title=title, action=action,
                                          contexts=tuple(contexts) if contexts else None,
                                          expires_in=expires_in, add=add, remove=remove)
        return self.submit(job)

    def _hidden_authors(self):
        """Who the lanes in lists.hide_in leave out: everyone in a list
        (lists.hide_members = "all"), only in exclusive ones, or nobody."""
        which = self.cfg["lists"]["hide_members"]
        if which == "off":
            return frozenset()
        return frozenset(a for x in self.lists if which == "all" or x.get("exclusive")
                         for a in self.list_members.get(x["id"], ()))

    def _refresh_lists(self):
        """Lists and who is in them, from the server; lanes follow."""
        self._retry_list_pending()
        got = [{"id": x["id"], "title": x.get("title", ""), "exclusive": bool(x.get("exclusive")),
                "replies_policy": x.get("replies_policy") or ""}
               for x in self.api.lists()]
        members = {x["id"]: {a["id"] for a in self.api.list_accounts(x["id"])} for x in got}
        for list_id, acc_id, _since in self._list_pending():  # still waiting: in, here
            members.setdefault(list_id, set()).add(acc_id)
        self._lists_checked = time.monotonic()
        if got == self.lists and members == self.list_members:
            return
        self._apply_lists(got, members)

    def _apply_lists(self, got, members):
        got = self._ordered_lists(got)
        self.lists, self.list_members = got, members
        for x in got:
            name = f"list:{x['id']}"
            if name not in self.sources:
                self.sources[name] = sources.list_source(self.api, x["id"])
        self.tag_groups = self._tag_groups()
        for g in self.tag_groups:
            name = taggroups.lane_name(g)
            if name not in self.sources:
                self.sources[name] = sources.tag_group_source(self.api, g)
        self.customs = custom.load(self.cfg)[0]  # the rules anew (the config may have changed)
        new_lanes = self._shown_lanes(lanes.enabled(self.cfg, got, self.tag_groups))
        self.lane_by_name = {lane.name: lane for lane in new_lanes}
        self.lanes = new_lanes
        self._lists_version += 1
        if threading.current_thread() is not threading.main_thread():
            self._warm_lanes()  # every lane anew (lists change what Home shows)
        self.emit("lists_changed", list(got))
        self.poll_now()

    def _ordered_lists(self, got):
        """Lists in my order (moved up and down in the sidebar, kept here: servers have
        no order of lists); the ones not placed yet keep the server's order, at the end."""
        order = self.store.kv_get("list_order", []) or []
        rank = {lid: i for i, lid in enumerate(order)}
        return sorted(got, key=lambda x: rank.get(x["id"], len(order) + got.index(x)))

    def move_list(self, list_id, step):
        """A list one place up (step -1) or down (+1) in the sidebar."""
        ids = [x["id"] for x in self.lists]
        if list_id not in ids:
            return
        i = ids.index(list_id)
        j = max(0, min(len(ids) - 1, i + step))
        if i == j:
            return
        ids.insert(j, ids.pop(i))
        self.store.kv_set("list_order", ids)
        if self.sync:
            self.sync.record_setting("list_order")
        self._apply_lists(list(self.lists), self.list_members)

    def list_people(self, list_id):
        """Who is in a list (and who waits to go in), for a tab of people: a future of
        ({accounts, relations}, None)."""
        def job():
            accounts = self.api.list_accounts(list_id)
            waiting = [p[1] for p in self._list_pending() if p[0] == list_id]
            log.info("list %s: %d on the server, %d waiting to go in", list_id,
                     len(accounts), len(waiting))
            have = {a["id"] for a in accounts}
            for acc_id in waiting:
                if acc_id not in have:
                    try:
                        accounts.append(self.api.account(acc_id))
                    except ApiError:
                        pass
            return self._with_relations(accounts), None
        return self.submit(job)

    def _tag_groups(self):
        """Lanes of several tags: the config's ([[lanes.tag_groups]]) and the ones saved
        from a search (kept here). Each {"any", "all", "none", "name", "saved"}."""
        out = []
        for g in self.cfg["lanes"].get("tag_groups") or []:
            out.append(dict(taggroups.normal(g), name=g.get("name") or "", saved=False,
                            not_in_home=bool(g.get("not_in_home"))))
        for g in self.store.kv_get("tag_groups", []) or []:
            out.append(dict(taggroups.normal(g), name=g.get("name") or "", saved=True,
                            not_in_home=bool(g.get("not_in_home"))))
        return out

    def set_tag_group_in_home(self, lane_name, in_home):
        """A saved lane of tags: its posts in Home too (True), or only in it (False)."""
        def job():
            saved = self.store.kv_get("tag_groups", []) or []
            for g in saved:
                if taggroups.lane_name(g) == lane_name:
                    g["not_in_home"] = not in_home
            self.store.kv_set("tag_groups", saved)
            if self.sync:
                self.sync.record_setting("tag_groups")
            self._apply_lists(list(self.lists), self.list_members)
        return self.submit(job)

    def tag_group_timeline(self, spec, max_id=None):
        """A page of several tags at once, for a search tab."""
        def job():
            page = taggroups.fetch(self.api.tag_timeline, spec,
                                   limit=self.cfg["feed"]["page_size"], max_id=max_id)
            self.store.put_statuses(page)
            return page
        return self.submit(job)

    def save_tag_group(self, spec, name="", in_home=True):
        """A search of several tags kept as a lane in the sidebar (group "Теги"); in_home
        False: its posts leave Home (like a list's "hide members")."""
        def job():
            saved = [g for g in self.store.kv_get("tag_groups", []) or []
                     if taggroups.key(g) != taggroups.key(spec)]
            saved.append(dict(taggroups.normal(spec), name=name, not_in_home=not in_home))
            self.store.kv_set("tag_groups", saved)
            if self.sync:
                self.sync.record_setting("tag_groups")
            self._apply_lists(list(self.lists), self.list_members)
            return taggroups.lane_name(spec)
        return self.submit(job)

    def add_tag_to_group(self, lane_name, tag):
        """A tag into a saved lane of tags (one more of its "any"). Its lane is called
        by what it holds, so it gets a new name: returned."""
        tag = tag.lstrip("#").lower()

        def job():
            saved = self.store.kv_get("tag_groups", []) or []
            out, new = [], lane_name
            for g in saved:
                if taggroups.lane_name(g) == lane_name:
                    g = dict(taggroups.normal(g), name=g.get("name") or "")
                    if tag not in g["any"] + g["all"]:
                        g["any"] = sorted(set(g["any"]) | {tag})
                    new = taggroups.lane_name(g)
                out.append(g)
            self.store.kv_set("tag_groups", out)
            if self.sync:
                self.sync.record_setting("tag_groups")
            self._apply_lists(list(self.lists), self.list_members)
            return new
        return self.submit(job)

    def drop_tag_group(self, lane_name):
        def job():
            saved = [g for g in self.store.kv_get("tag_groups", []) or []
                     if taggroups.lane_name(g) != lane_name]
            self.store.kv_set("tag_groups", saved)
            if self.sync:
                self.sync.record_setting("tag_groups")
            self._apply_lists(list(self.lists), self.list_members)
        return self.submit(job)

    def lane_title(self, name):
        """A list's title; None for the built-in lanes (their names are translated)."""
        c = next((c for c in self.customs if c.name == name), None)
        if c is not None:
            return c.title  # its own, or None: the built-in word
        if taggroups.is_tags(name):
            g = next((g for g in self.tag_groups if taggroups.lane_name(g) == name), None)
            return (g or {}).get("name") or taggroups.title(taggroups.spec_of(name) or {})
        if lanes.is_list(name):
            lid = name[len(lanes.LIST_PREFIX):]
            return next((x["title"] for x in self.lists if x["id"] == lid), "?")
        return None

    def lane_icon(self, name):
        """The picture of a lane: a lane of rules' `icon`; else the one its name has
        (frontends/iconpack.py LANE); a lane of one's own without one — a list's."""
        c = next((c for c in self.customs if c.name == name), None)
        if c is not None and c.rule.icon:
            return c.rule.icon
        if c is not None and name not in presets.known_names():
            return "list"
        return None

    def lists_of(self, acc_id):
        return {lid for lid, m in self.list_members.items() if acc_id in m}

    HIDDEN_POSTS = "fedtail: hidden posts"  # the filter "Hide this post" keeps them in

    def _hidden_filter(self, make=False):
        mine = next((f for f in self.api.filters() or []
                     if f.get("title") == self.HIDDEN_POSTS), None)
        if mine is None and make:
            mine = self.api.create_filter(self.HIDDEN_POSTS, [], "hide",
                                          ("home", "public", "thread", "account",
                                           "notifications"))
        return mine

    def _hidden_changed(self, sid, on):
        (self.hidden_posts.add if on else self.hidden_posts.discard)(sid)
        self._silence_version += 1
        self.emit("lanes_updated", {lane.name: [] for lane in self.lanes})

    def hide_post(self, status):
        """This very post out of sight everywhere (and in every client): put into a
        filter of the server's, made the first time, that hides posts one by one."""
        sid = status["id"] if isinstance(status, dict) else status

        def job():
            got = self._api("filter_status", self.api.filter_status,
                            self._hidden_filter(make=True)["id"], sid)
            self._hidden_changed(sid, True)
            return got
        return self.submit(job)

    def unhide_post(self, status):
        """The post back: out of the hidden posts' filter. True when it was there."""
        sid = status["id"] if isinstance(status, dict) else status

        def job():
            self._hidden_changed(sid, False)
            mine = self._hidden_filter()
            if mine is None:
                return False
            for fs in self.api.filter_statuses(mine["id"]) or []:
                if str(fs.get("status_id")) == str(sid):
                    self.api.unfilter_status(fs["id"])
                    return True
            return False
        return self.submit(job)

    def create_list(self, title, exclusive=False, add=None, replies_policy=None):
        """replies_policy: whose replies the list shows — "followed", "list", "none"."""
        def job():
            x = self.api.create_list(title, exclusive, replies_policy=replies_policy) \
                if replies_policy else self.api.create_list(title, exclusive)
            try:
                if add:  # refused (not followed yet): waits, as with an existing list
                    self._list_add_or_wait(x["id"], add)
            finally:
                self._refresh_lists()  # the new list shows whatever happened to the add
            return x
        return self.submit(job)

    def update_list(self, list_id, title, exclusive, replies_policy=None):
        def job():
            if replies_policy:
                self.api.update_list(list_id, title, exclusive, replies_policy=replies_policy)
            else:
                self.api.update_list(list_id, title, exclusive)
            self._refresh_lists()
        return self.submit(job)

    def delete_list(self, list_id):
        def job():
            self.api.delete_list(list_id)
            self._refresh_lists()
        return self.submit(job)

    LIST_PENDING_DAYS = 30

    def set_in_list(self, list_id, acc_id, on):
        """Into a list or out. A server takes only people I follow into lists; someone
        just followed (a locked account that hasn't approved yet, or a server slow to
        record it) is refused — then fedtail remembers it and puts them in by itself
        once it can. Returns "pending" in that case."""
        def job():
            if on:
                result = self._list_add_or_wait(list_id, acc_id)
            else:
                self.store.kv_set("list_pending", [p for p in self._list_pending()
                                                   if (p[0], p[1]) != (list_id, acc_id)])
                try:
                    self.api.list_remove(list_id, acc_id)
                except ApiError as e:  # it was only waiting here, never on the server
                    if e.status != 404:
                        raise
                result = "done"
            if result == "pending":  # in the list here at once: lanes treat them so
                members = {k: set(v) for k, v in self.list_members.items()}
                members.setdefault(list_id, set()).add(acc_id)
                self._apply_lists(list(self.lists), members)
            else:
                self._refresh_lists()
            # who is hidden where changed: every lane may look different now
            self.emit("lanes_updated", {lane.name: [] for lane in self.lanes})
            return result
        return self.submit(job)

    def _ask_prefetch(self, statuses):
        """The pictures of posts just come, for the frontend to fetch ahead
        (feed.prefetch): "previews" — previews and avatars; "all" — the originals, the
        videos and gifs too; "off" — nothing ahead, as before."""
        mode = self.cfg["feed"].get("prefetch", "previews")
        if mode == "off" or not statuses:
            return
        urls = []
        for st in statuses:
            for s in (st, real(st)):
                acc = s.get("account") or {}
                urls.append(acc.get("avatar_static") or acc.get("avatar"))
            for m in real(st).get("media_attachments") or []:
                urls.append(m.get("preview_url"))
                if mode == "all" and m.get("type") == "image":
                    urls.append(m.get("url"))
            card = real(st).get("card") or {}
            urls.append(card.get("image"))
        urls = [u for u in dict.fromkeys(urls) if u]
        if urls:
            self.emit("prefetch", urls)
        if mode == "all":  # videos, gifs, sounds: to their own cache (ui.video_disk_mb)
            videos = [m.get("url") for st in statuses
                      for m in real(st).get("media_attachments") or []
                      if m.get("type") in ("video", "gifv", "audio") and m.get("url")]
            if videos:
                self.emit("prefetch_video", list(dict.fromkeys(videos)))

    def _list_add_or_wait(self, list_id, acc_id):
        """Into the list on the server, or — refused for someone not followed (yet) —
        remembered and tried again on each lists refresh. "done" or "pending"."""
        pending = [p for p in self._list_pending() if (p[0], p[1]) != (list_id, acc_id)]
        try:
            self.api.list_add(list_id, acc_id)
            result = "done"
        except ApiError as e:
            if e.status not in (403, 404, 422):
                raise
            pending.append([list_id, acc_id, time.time()])
            log.info("list %s: %s not followed yet (%s), will add later", list_id, acc_id,
                     e.status)
            result = "pending"
        self.store.kv_set("list_pending", pending)
        return result

    def _list_pending(self):
        return [p for p in self.store.kv_get("list_pending", []) or []
                if time.time() - p[2] < self.LIST_PENDING_DAYS * 86400]

    def _retry_list_pending(self):
        """People waiting to go into lists: try again (on every lists refresh)."""
        pending = self._list_pending()
        if not pending:
            return
        # who is followed now: only they can go in; a request still waiting stays
        # waiting without asking the server; one refused or withdrawn is let go (it was
        # tried, and refused with a 404, every ten minutes for a month)
        try:
            rel = {r["id"]: r for r in self.api.relationships(
                list(dict.fromkeys(p[1] for p in pending)))}
        except Exception as e:  # noqa: BLE001 — can't tell now: try them all
            log.debug("list pending: relationships: %s", e)
            rel = None
        left = []
        for list_id, acc_id, since in pending:
            r = rel.get(acc_id) if rel is not None else None
            if r is not None and not r.get("following"):
                if r.get("requested"):
                    left.append([list_id, acc_id, since])
                else:
                    log.info("list %s: %s is not followed (the request refused or "
                             "withdrawn): not waiting to add them any more", list_id, acc_id)
                continue
            try:
                self.api.list_add(list_id, acc_id)
                log.info("list %s: %s added after all", list_id, acc_id)
            except Exception as e:  # noqa: BLE001 — not yet, or slow, or down: next time
                log.debug("list %s pending %s: %s", list_id, acc_id, e)
                left.append([list_id, acc_id, since])
        self.store.kv_set("list_pending", left)

    # ---- thread subscriptions ------------------------------------------------------
    def subscribed(self, status):
        """Is the thread this post is in followed? (Knows only threads it has seen.)"""
        return self._sub_root(status) is not None

    def subscribe(self, status):
        def job():
            root = subs.subscribe(self.store, self.api, status)
            if self.sync:
                self.sync.record_thread(root, "sub")
            self.emit("subs_changed", root)
            return root
        return self.submit(job)

    def _sub_root(self, status):
        st = real(status)
        parent = st.get("in_reply_to_id")
        return self.store.sub_root_of(st["id"]) or \
            (parent and self.store.sub_root_of(parent)) or None

    def unsubscribe(self, status):
        """Leave the thread: no more "Subscriptions" from it — and, with
        subs.leave_mutes, no more mentions either (replies there tag everyone)."""
        def job():
            quiet = self.cfg["subs"]["leave_mutes"]
            root = subs.leave(self.store, self.api, status, quiet=quiet)
            if self.sync:
                self.sync.record_thread(root, "muted" if quiet else "left")
            self._silence_seen = {}  # what was let through before may be muted now
            self.emit("subs_changed", root)
            self.emit("lanes_updated", {"subs": [], **({"mentions": []} if quiet else {})})
            return root
        return self.submit(job)

    # ---- sync with the account's other devices (`fedtail sync …`, core/sync) ---------
    def sync_key(self):
        from .sync import engine
        return engine.shown_key(self)

    def sync_join(self, text):
        from .sync import engine
        return engine.join(self, text)

    def sync_login_begin(self):
        from .sync import engine
        return engine.login_start(self.api_class, self.auth["server"])

    def sync_login_end(self, pending, code):
        from .sync import engine
        engine.login_finish(self.api_class, self.paths, pending, code)

    def sync_now(self):
        """One round at once: (sent, got), or None (sync.last says why)."""
        return self.sync.step() if self.sync else None

    def sync_status(self):
        return self.sync.status() if self.sync else None

    # the lanes' settings that travel with sync.lane_rules (core/sync)
    LANE_RULES = ("preset", "enabled", "custom", "posts_only")

    def _lane_rules(self):
        return {k: self.cfg["lanes"].get(k) for k in self.LANE_RULES}

    def _note_lane_rules(self):
        """The lanes as config.toml has them now, kept (kv "lane_rules"); changed since
        last time (edited by hand, in the lane editor) — they go to the other devices."""
        now = self._lane_rules()
        before = self.store.kv_get("lane_rules")
        if before == now:
            return
        self.store.kv_set("lane_rules", now)
        # the first time (a new device, a store started anew) is where it starts, not a
        # change: sent, it would win over the lanes the other devices have
        if self.sync and before is not None:
            self.sync.record_setting("lane_rules")

    def lanes_saved(self, cfg):
        """The lanes were written into config.toml here (the lane editor): this run takes
        them at once, and they travel (sync.lane_rules)."""
        for k in self.LANE_RULES:
            self.cfg["lanes"][k] = cfg["lanes"][k]
        self._note_lane_rules()
        self._apply_lists(list(self.lists), self.list_members)

    def _take_lane_rules(self):
        """Another device's lanes (sync.lane_rules): into this config.toml, then shown."""
        from . import config_edit
        got = self.store.kv_get("lane_rules")
        if not isinstance(got, dict):
            return
        changes = {("lanes", k): got[k] if got.get(k) is not None else config_edit.UNSET
                   for k in self.LANE_RULES if k in got}
        cfg, _w = config_edit.save(self.paths.config_file, changes)
        for k in self.LANE_RULES:
            self.cfg["lanes"][k] = cfg["lanes"][k]
        self.store.kv_set("lane_rules", self._lane_rules())  # as this file reads them

    def apply_lanes_state(self, keys):
        """Another device rearranged my lanes (core/sync: the order of lists, saved tag
        lanes; with sync.lane_rules the lanes themselves) — the new values are in the
        store already: the sidebar follows."""
        log.info("sync: %s from another device", ", ".join(keys))
        if "lane_rules" in keys:
            self._take_lane_rules()
        self._apply_lists(list(self.lists), self.list_members)

    def apply_thread_state(self, root, state):
        """Another device set this thread's state (core/sync): do the same here, without
        recording it again. Blocking (asks the server for the thread)."""
        post = {"id": root}
        if state == "sub":
            subs.subscribe(self.store, self.api, post)
        else:
            subs.leave(self.store, self.api, post, quiet=state == "muted")
            if state == "left":
                self.store.quiet_set(root, False)
            self._silence_seen = {}
        log.info("sync: thread %s → %s (another device)", root, state)
        self.emit("subs_changed", root)
        self.emit("lanes_updated", {"subs": [], "mentions": []})

    def thread_quiet(self, status):
        """Is this post's thread muted here? (Knows only the posts it has seen there.)"""
        return subs.quiet_root(self.store, status) is not None

    def _mention_entry(self, n):
        """The mentions source's entry: drops mentions from threads muted here."""
        e = sources.notification_entry(n)
        if e is None:
            return None
        sid = e[1].get("id")
        if sid in self._silence_seen:
            return None if self._silence_seen[sid] else e
        try:
            root = subs.silenced(self.store, self.api, e[1], False)
        except Exception as ex:  # noqa: BLE001 — a mention must never be lost to this
            log.warning("muted thread check %s: %s", sid, ex)
            root = None
        if len(self._silence_seen) > 2000:
            self._silence_seen.clear()
        self._silence_seen[sid] = root
        if root:
            log.info("mention %s dropped: thread %s is muted here", sid, root)
            return None
        return e

    def _auto_subscribe(self, my_statuses):
        """My new posts and comments: follow their threads (flags subs.auto)."""
        if "subs" not in self.lane_by_name:
            return
        want = set(self.cfg["subs"]["auto"])
        for st in my_statuses:
            st = real(st)
            kind = "comments" if st.get("in_reply_to_id") else "posts"
            if kind not in want or self.subscribed(st):
                continue
            try:
                if subs.subscribe(self.store, self.api, st, auto=True):
                    self.emit("subs_changed", None)
            except Exception as e:
                log.warning("auto-subscribe %s: %s", st.get("id"), e)

    # ---- reading ---------------------------------------------------------------
    def set_active_lane(self, name):
        """The frontend tells which lane is on screen; a browse lane (local,
        federated) is fetched right away and then on every poll while it stays."""
        self._active_lane = name
        lane = self.lane_by_name.get(name)
        if lane is not None and lane.lazy:
            self.poll_now()

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
        """My direct messages into the mentions stream, where "Direct" reads: the
        dialogue whole — theirs and mine, by the posts' own time. Mine are read (the store
        marks every post of mine read), so no count grows. statuses: the ones just sent;
        None — every one stored that isn't there yet. How many went in."""
        source = self.lane_by_name["direct"].source if "direct" in self.lane_by_name \
            else "mentions"
        if statuses is None:
            got = self.store.my_direct_outside(source)
        else:
            got = [s for s in statuses if s and s.get("visibility") == "direct"
                   and self.me and s.get("account", {}).get("id") == self.me["id"]]
        if not got:
            return 0
        # an item of its own ("mine:" + id): never one of the server's notification ids
        return len(self.store.put_items(source, [("mine:" + s["id"], s, s.get("created_at", ""))
                                                 for s in got]))

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
        key = (self.store.items_version.get(lane.source, 0), self.store.status_version, limit,
               self.me["id"] if self.me else None, only_posts, self._lists_version,
               self._silence_version, repeats, self._world_version,
               self.store.read_version if state else 0, self.lane_filter(name),
               # a window moves with the clock (and density with the posts' age): anew
               # each minute
               int(time.time() // 60) if getattr(lane, "window", 0)
               or getattr(lane, "sort", "") == "density" else 0)
        hit = self._lane_cache.get(name)
        if hit and hit[0] == key:
            return hit[1]
        ctx = self._ctx()
        kept = []
        rows = self.store.iter_items(lane.source, max_rows=max(FILTER_WINDOW, limit))
        if not repeats:
            rows = self._without_repeats(lane.source, rows)
        for item_id, st in rows:
            if only_posts and real(st).get("in_reply_to_id"):
                continue
            if self.silenced(st):
                continue
            if lanes.keeps(lane, st, ctx):
                kept.append((item_id, st))
                if len(kept) >= limit:
                    break
        kept.reverse()
        if lane.by_status_time:
            kept.sort(key=lambda e: (real(e[1]).get("created_at", ""), real(e[1])["id"]))
        if lane.chips:  # a free lane's quick filter
            shows = self._chip_shows(name)
            kept = [e for e in kept if shows(e[1])]
        if getattr(lane, "window", 0):  # only the last so many hours (mode = "catch_up")
            kept = _within(kept, lane.window)
        if getattr(lane, "filter_context", ""):
            kept = self._by_filter_context(kept, lane.filter_context)
        if getattr(lane, "sort", "arrival") in COUNT_SORTS:
            kept = _by_counts(kept, lane.sort, self.cfg["feed"]["order"] == "oldest_first")
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
        ids = [st["id"] for _, st in entries]
        read = self.store.read_set(ids)
        return {i for i in ids if i not in read}

    def unread_count(self, name):
        """Unread in a lane — cached while neither the lane nor any read mark changed:
        the sidebar asks for every lane after every event."""
        entries = self.lane_entries(name)
        hit = self._lane_cache.get(name)
        key = (hit[0] if hit else None, id(entries), self.store.read_version)
        cache = self.__dict__.setdefault("_unread_cache", {})
        got = cache.get(name)
        if got and got[0] == key:
            return got[1]
        n = len(self.unread_ids(entries))
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
        status_ids = list(status_ids)
        if status_ids:
            self.store.mark_read(status_ids)
            self.emit("read_changed", status_ids)
            if self.sync:
                self.sync.record_read(status_ids)
            self._read_conversations(status_ids)

    def load_older(self, name):
        lane = self.lane_by_name[name]
        if lane.feeds:
            return self.submit(lambda: self._older_custom(name))
        if lane.source not in self.sources:  # nothing older on a server for this one
            return self.submit(lambda: 0)

        def job():
            got = sources.fetch_older(self.store, self.sources[lane.source],
                                      self.cfg["feed"]["page_size"])
            limit = self._limits.get(name, self.cfg["feed"]["render_limit"])
            self._limits[name] = limit + len(got)
            # history is not news: older posts count as read
            self.store.mark_read([st["id"] for st in got])
            self.emit("lanes_updated", {name: []})
            self._fetch_parents(got)
            return len(got)
        return self.submit(job)

    def _older_custom(self, name):
        """A free lane's "Older": a page older from each of its feeds, through its rule."""
        c = next((c for c in self.customs if c.name == name), None)
        if c is None:
            return 0
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
        limit = self._limits.get(name, self.cfg["feed"]["render_limit"])
        self._limits[name] = limit + len(got)
        self.emit("lanes_updated", {name: []})
        self._fetch_parents(got)
        return len(got)

    def parent_of(self, status):
        """Parent status, 'missing', or None when it isn't known (yet)."""
        pid = real(status).get("in_reply_to_id")
        if not pid:
            return None
        p = self.store.get_status(pid)
        if p:
            return p
        if self.store.is_missing(pid):
            return "missing"
        return None

    def parents_for(self, statuses):
        """{status id: parent status | 'missing' | None} in two queries."""
        pids = {st["id"]: real(st).get("in_reply_to_id") for st in statuses}
        wanted = {p for p in pids.values() if p}
        found = self.store.get_statuses(wanted)
        missing = self.store.missing_set(wanted - set(found))
        out = {}
        for sid, pid in pids.items():
            if not pid:
                out[sid] = None
            elif pid in found:
                out[sid] = found[pid]
            elif pid in missing:
                out[sid] = "missing"
            else:
                out[sid] = None
        return out

    def short_ids(self, statuses):
        """{status id: '#a3f'-style alias} for the posts on screen (boosts: the original)."""
        return self.store.aliases(real(st)["id"] for st in statuses)

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

    def ensure_parents(self, statuses):
        self.bg.submit(self._fetch_parents, list(statuses))

    def _fetch_parents(self, statuses):
        want = []
        for st in statuses:
            pid = real(st).get("in_reply_to_id")
            if pid and pid not in self._parent_inflight and not self.store.get_status(pid) \
                    and not self.store.is_missing(pid):
                self._parent_inflight.add(pid)
                want.append(pid)
        got = False
        for pid in want:
            try:
                self.store.put_statuses([self.api.status(pid)])
                got = True
            except ApiError as e:
                if e.status in (403, 404, 410):
                    self.store.mark_missing(pid)
                    got = True
            except Exception:
                pass  # network hiccup: try again next time
            finally:
                self._parent_inflight.discard(pid)
        if got:
            self.emit("parents")

    def thread(self, sid):
        return self.submit(self._thread_nodes, sid)

    def _thread_nodes(self, sid):
        """The whole conversation, the same from whichever post it is opened: a
        server's context of a post holds its ancestors and *its* descendants only —
        not the sibling branches — so the tree is read from the top post."""
        focus = real(self.api.status(sid))
        ctx = self.api.context(focus["id"])
        ancestors = ctx.get("ancestors", [])
        root = ancestors[0] if ancestors else focus
        below = list(ctx.get("descendants", []))
        refresh = self._async_refresh_hint()
        if ancestors:
            below = self.api.context(root["id"]).get("descendants", []) + below + \
                ancestors[1:] + [focus]
            refresh = self._async_refresh_hint() or refresh
        seen, rest = {root["id"]}, []
        for st in below:
            if st["id"] not in seen:
                seen.add(st["id"])
                rest.append(st)
        everything = [root] + rest
        self.store.put_statuses(everything)
        if self.cfg["feed"]["honest_counters"]:
            self.bg.submit(self._honest_counts, everything)
        if self.cfg["feed"]["complete_threads"]:
            self.bg.submit(self._complete_thread, root, {s.get("uri") for s in everything})
            if refresh:
                self.bg.submit(self._await_refresh, root["id"], *refresh)
        return threads.build(root, {"ancestors": [], "descendants": rest})

    def _async_refresh_hint(self):
        hint = getattr(self.api, "last_async_refresh", None)
        return hint() if hint else None

    def _await_refresh(self, root_id, refresh_id, retry, budget=60):
        """Mastodon 4.5+ said it is fetching the rest of this thread from other
        servers: ask how it goes, and when done, the open thread grows."""
        waited = 0
        while waited < budget and not self._stop.is_set():
            pause = max(1, min(retry, 10))
            self._stop.wait(pause)
            waited += pause
            try:
                status = self.api.async_refresh(refresh_id)
            except Exception as e:  # noqa: BLE001 — experimental endpoint: give up quietly
                log.debug("async refresh %s: %s", refresh_id, e)
                return
            if status == "finished":
                log.info("thread %s: the server finished fetching replies (%d s)",
                         root_id, waited)
                self.emit("thread_grew", root_id)
                return

    def _complete_thread(self, root, known):
        """Replies the post's own server lists and mine hasn't got: mine fetches them
        by address. Then the open thread grows (event thread_grew)."""
        if root.get("visibility") not in ("public", "unlisted") or not root.get("uri"):
            return
        now = time.monotonic()
        if now - self._completed.get(root["id"], -1e9) < 300:
            return
        self._completed[root["id"]] = now
        from . import replies
        t = time.monotonic()
        # the whole conversation in one list where the server keeps one; else walk
        # the replies of replies
        uris = replies.context_uris(self._origin_json, root["uri"])
        how = "context"
        if not uris:
            uris, how = replies.reply_uris(self._origin_json, root["uri"]), "replies"
        missing = [u for u in uris if u not in known]

        def resolve(uri):
            try:
                found = self.api.search(uri, kind="statuses", resolve=True, limit=1)
            except Exception as e:  # not reachable, not public, gone: skip it
                log.debug("resolve %s: %s", uri, e)
                return []
            return (found or {}).get("statuses") or []
        # my server fetches each from its home: a few at once, not one after another
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="fedtail-resolve") as ex:
            got = [st for page in ex.map(resolve, missing[:30]) for st in page]
        log.info("thread %s: origin lists %d posts (%s), %d missing here, %d fetched "
                 "(%.1f s)", root["id"], len(uris), how, len(missing), len(got),
                 time.monotonic() - t)
        if got:
            self.store.put_statuses(got)
            self.emit("thread_grew", root["id"])

    def _own_hosts(self):
        """My servers' hostnames: exempt from remote's public-address rule (a server
        at home on a private address still shows its own pictures)."""
        from urllib.parse import urlparse
        server = (self.auth or {}).get("server") or ""
        return {(urlparse(server).hostname or "").lower()} - {""}

    def _origin_json(self, url):
        """An ActivityPub object from someone else's server: no token, short timeout,
        public https addresses only, the size capped (see remote)."""
        from ..protocols.mastodon.api import USER_AGENT
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
            nodes = self._thread_nodes(real(st)["id"])
            return next((n.status for n in nodes if n.number == number), None)
        return self.submit(job)

    def find_user(self, handle):
        """@user or user@server → the account (fetched through my server), or None."""
        def job():
            got = self.api.search("@" + handle.lstrip("@"), kind="accounts", resolve=True,
                                  limit=1)
            return (got.get("accounts") or [None])[0]
        return self.submit(job)

    def _origin_get(self, url):
        """GET from someone else's server: no token, short timeout (see remote)."""
        from ..protocols.mastodon.api import USER_AGENT
        from . import remote
        return remote.get_json(url, headers={"User-Agent": USER_AGENT},
                               own_hosts=self._own_hosts())

    def _honest_counts(self, statuses):
        now = time.monotonic()
        fresh = []
        for st in statuses[:40]:
            sid = real(st)["id"]
            if now - self._honest_checked.get(sid, -1e9) < 600:
                continue
            url = counters.origin_api_url(st, self.auth["server"])
            if not url:
                continue
            self._honest_checked[sid] = now
            try:
                origin = self._origin_get(url)
            except Exception as e:  # their server, their problems
                log.debug("honest counters %s: %s", url, e)
                origin = None
            if origin is None and self.cfg["feed"].get("counters_via_accounts", True):
                # their server won't tell a stranger: ask as one of my other accounts
                origin = self._counts_via_accounts(st, url)
            better = counters.merge(st, origin)
            if better:
                fresh.append(better)
        if fresh:
            self.store.put_statuses(fresh)
            for st in fresh:  # each its own: the window redoes only the cards of each
                self.emit("status_updated", st)

    def _other_accounts(self):
        """[(server, token)] of my other logged-in profiles (not this one), looked up
        once in ten minutes."""
        now = time.monotonic()
        cached = getattr(self, "_others_cache", None)
        if cached and now - cached[0] < 600:
            return cached[1]
        from . import paths as paths_module
        from . import profiles
        out = []
        try:
            for prof in profiles.listing():
                if prof["name"] == self.paths.profile or not prof["logged_in"]:
                    continue
                a = auth.load(paths_module.resolve(prof["name"]).auth_file)
                if a and a.get("server") and a.get("token"):
                    out.append((a["server"].rstrip("/"), a["token"]))
        except Exception as e:  # noqa: BLE001 — a nicety
            log.debug("other accounts: %s", e)
        self._others_cache = (now, out)
        return out

    def _counts_via_accounts(self, status, origin_url):
        """The post as my other accounts' servers see it — the post's own server when
        one of my accounts lives there (it knows every like), or another server that
        already has the post. Each token goes only to its own server."""
        from urllib.parse import urlparse

        import requests
        st = real(status)
        host = urlparse(origin_url).hostname
        best = None
        for server, token in self._other_accounts():
            head = {"User-Agent": USER_AGENT, "Authorization": f"Bearer {token}"}
            try:
                if urlparse(server).hostname == host:  # my account on the post's server
                    r = requests.get(origin_url, headers=head, timeout=8,
                                     allow_redirects=False)  # the token goes nowhere else
                    got = r.json() if r.status_code == 200 else None
                else:  # another server: only if it has the post already (no fetching)
                    r = requests.get(api_module.search_url(server), headers=head, timeout=8,
                                     params={"q": st.get("uri"), "type": "statuses",
                                             "resolve": "false", "limit": 1},
                                     allow_redirects=False)
                    found = (r.json() or {}).get("statuses") if r.status_code == 200 else []
                    got = found[0] if found else None
            except (requests.RequestException, ValueError) as e:
                log.debug("counters via %s: %s", urlparse(server).hostname, e)
                continue
            if not isinstance(got, dict) or got.get("uri") != st.get("uri"):
                continue
            if best is None or sum(got.get(k) or 0 for k in ("favourites_count",
                                                             "reblogs_count")) > \
                    sum(best.get(k) or 0 for k in ("favourites_count", "reblogs_count")):
                best = got
        return best

    PROFILE_SHOWS = {"all": {}, "posts": {"exclude_replies": True},
                     "media": {"only_media": True}}

    def account_statuses(self, acc_id, max_id=None, show="all"):
        """Someone's posts, a page; show: "all" (posts and replies), "posts" (without
        their replies to others — the server filters), "media" (only with pictures)."""
        def job():
            page = self.api.account_statuses(acc_id, limit=self.cfg["feed"]["page_size"],
                                             max_id=max_id,
                                             **self.PROFILE_SHOWS.get(show, {}))
            self.store.put_statuses(page)
            return page
        return self.submit(job)

    def account(self, acc_id):
        return self.call_api("account", acc_id)

    def posts_from_origin(self, acc, have_uris=()):
        """Someone from another server my server knows little about: their newest public
        posts, read from their own server's outbox (ActivityPub, without my token),
        fetched into my server by address so they are ordinary posts here — answerable,
        likeable. A future of those statuses (feed.remote_profiles)."""
        def job():
            fc = self.cfg["feed"]
            if not fc.get("remote_profiles", True) or "@" not in (acc.get("acct") or ""):
                return []
            from . import replies
            t = time.monotonic()
            outbox = self._outbox_of(acc)
            limit = min(40, int(fc.get("remote_posts", 20)))
            uris = []
            try:
                if outbox:
                    uris = replies.outbox_post_uris(self._origin_json, outbox, limit)
            except Exception as e:  # noqa: BLE001 — their server, anything goes
                log.info("profile %s: outbox: %s", acc.get("id"), e)
            have = set(have_uris)
            if not uris:  # no outbox for strangers: their public API, maybe
                uris = self._older_via_api(acc, None, have, limit, pages=1)[0]
            got = self._resolve_statuses([u for u in uris if u not in have])
            log.info("profile %s: outbox lists %d posts, %d new here, fetched in %.1f s",
                     acc.get("id"), len(uris), len(got), time.monotonic() - t)
            return got
        return self.bg.submit(job)

    def older_from_origin(self, acc, cursor=None, have_uris=(), resolve=True):
        """Further back in someone's posts than my server has (it knows only what reached
        it, mostly since someone here followed them): page by page from their own
        server's outbox, fetched into mine by address. A future of (statuses, cursor
        for the next call or None) — cursor None to start from their newest."""
        def job():
            if not self.cfg["feed"].get("remote_profiles", True) or \
                    "@" not in (acc.get("acct") or ""):
                return [], None
            from . import replies
            t = time.monotonic()
            limit = min(40, int(self.cfg["feed"].get("remote_posts", 20)))
            uris, nxt, how = [], None, "outbox"
            if not (cursor or "").startswith("api:"):
                where = cursor or self._outbox_of(acc)
                try:
                    if where:
                        uris, nxt = replies.outbox_page(self._origin_json, where, limit,
                                                        pages=5, skip=have_uris)
                except Exception as e:  # noqa: BLE001 — their server, anything goes
                    log.info("profile %s: outbox page: %s", acc.get("id"), e)
            if not uris and not nxt and (cursor is None or cursor.startswith("api:")):
                # no outbox for strangers (GoToSocial, Mastodon with authorized fetch):
                # their server's public API, if it answers without a token
                how = "api"
                uris, nxt = self._older_via_api(acc, cursor, set(have_uris), limit)
            log.info("profile %s: older from origin via %s: %d listed", acc.get("id"), how,
                     len(uris))
            if not resolve:  # the frontend fetches them a few at a time (resolve_statuses)
                return uris, nxt
            got = self._resolve_statuses(uris)
            log.info("profile %s: older from origin: %d listed, %d fetched in %.1f s, %s",
                     acc.get("id"), len(uris), len(got), time.monotonic() - t,
                     "more there" if nxt else "that's all")
            return got, nxt
        return self.bg.submit(job)

    def _older_via_api(self, acc, cursor, have, limit, pages=5):
        """Someone's public posts from their server's Mastodon API, without my token:
        (addresses, cursor "api:<their id>:<max id>" or None)."""
        from urllib.parse import urlparse
        host = next((urlparse(u).netloc for u in (acc.get("url"), acc.get("uri")) if u), "")
        if not host:
            return [], None
        try:
            if cursor:
                _api, their_id, max_id = cursor.split(":", 2)
            else:
                found = self._origin_get(api_module.lookup_url(host, acc.get("username")))
                their_id, max_id = (found or {}).get("id"), ""
                if not their_id:
                    log.info("profile %s: %s won't look them up", acc.get("id"), host)
                    return [], None
            uris = []
            for _ in range(pages):
                page = self._origin_get(api_module.statuses_url(host, their_id, max_id))
                if not isinstance(page, list) or not page:
                    log.info("profile %s: %s gave %s", acc.get("id"), host,
                             "nothing more" if page == [] else "no posts to a stranger")
                    return uris, None
                max_id = str(page[-1].get("id") or "")
                uris += [s["uri"] for s in page if s.get("uri") and s["uri"] not in have
                         and s.get("visibility") in ("public", "unlisted")]
                if len(uris) >= limit or not max_id:
                    break
            return uris, (f"api:{their_id}:{max_id}" if max_id else None)
        except Exception as e:  # noqa: BLE001 — their server, anything goes
            log.info("profile %s: %s api: %s", acc.get("id"), host, e)
            return [], None

    @staticmethod
    def server_host(text):
        from .remote import server_host
        return server_host(text)

    def remote_public(self, host, cursor=None):
        """Another server's public lane (its own people), read without an account and
        fetched into mine page by page, so each post can be liked, answered, opened as
        any other. A future of (statuses, cursor of the next page or None); LookupError
        when that server keeps its lane closed to strangers (many do; GoToSocial
        always) or isn't a server that has one."""
        def job():
            h = self.server_host(host)
            if not h:
                raise ValueError(host)
            mine = {x.lower() for x in self._own_hosts()}
            if h in mine:  # my own server: its Local, with my token
                page = self.api.local(limit=20, max_id=cursor) or []
                self.store.put_statuses(page)
                return page, (page[-1]["id"] if len(page) >= 20 else None)
            page = self._origin_get(api_module.public_url(h, cursor or ""))
            if not isinstance(page, list):
                raise LookupError(h)
            uris = [s["uri"] for s in page if isinstance(s, dict) and s.get("uri")
                    and s.get("visibility") in ("public", None)]
            nxt = str(page[-1].get("id") or "") if len(page) >= 20 else ""
            got = self._resolve_statuses(uris)
            log.info("server %s: public lane: %d listed, %d fetched", h, len(uris),
                     len(got))
            return got, (nxt or None)
        return self.bg.submit(job)

    def _outbox_of(self, acc):
        for url in (acc.get("uri"), acc.get("url")):
            if not url:
                continue
            try:
                actor = self._origin_json(url)
            except Exception as e:  # noqa: BLE001
                log.debug("actor %s: %s", url, e)
                continue
            if isinstance(actor, dict) and actor.get("outbox"):
                return actor["outbox"]
        log.info("profile %s: no outbox to read", acc.get("id"))
        return None

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

    def relationship(self, acc_id):
        """following, followed_by, requested, … between me and an account (and kept a
        few minutes for relation_known)."""
        def job():
            rel = self.api.relationship(acc_id)
            self._relations[acc_id] = (time.monotonic(), rel)
            return rel
        return self.submit(job)

    RELATION_KEEP_S = 300

    def relation_known(self, acc_id):
        """The relationship asked for lately, or None — for menus that open at once."""
        got = getattr(self, "_relations", {}).get(acc_id)
        if got and time.monotonic() - got[0] < self.RELATION_KEEP_S:
            return got[1]
        return None

    def follow(self, acc_id, on=True):
        """Follow or not. The server doesn't say since when I follow someone, so the
        moment it happens through fedtail is written down here (followed_since)."""
        def job():
            rel = self.api.follow(acc_id, on)
            self._relations[acc_id] = (time.monotonic(), rel)
            since = dict(self.store.kv_get("followed_at", {}) or {})
            if on:
                since.setdefault(acc_id, now_iso())
            else:
                since.pop(acc_id, None)
            self.store.kv_set("followed_at", since)
            if not on and self.cfg["feed"].get("forget_unfollowed", True):
                self._forget_in_home(acc_id)
            if self.cfg["feed"].get("follow_date_note", True):
                rel = self._note_follow(acc_id, rel, since.get(acc_id) if on else None)
            if on:
                try:
                    self._my_follows([self.api.account(acc_id)])
                except Exception as e:  # noqa: BLE001 — the follow itself is done
                    log.debug("my follow event: %s", e)
            return rel
        return self.submit(job)

    MY_FOLLOW = "fedtail.followed"  # Activity's type for "I followed someone"

    def _my_follows(self, accounts):
        """I followed these (here, or elsewhere — seen in whom I follow): a row each in
        Activity, mine (activity.my_follows) — not news, no number. One a day for each."""
        if not self.cfg["activity"].get("my_follows", True):
            return []
        from .store import MINE_EVENT
        day = now_iso()[:10]
        rows = [{"id": f"{MINE_EVENT}followed:{a['id']}:{day}", "type": self.MY_FOLLOW,
                 "account": a, "created_at": now_iso()}
                for a in accounts if isinstance(a, dict) and a.get("id")]
        new = self.store.activity_put(rows) if rows else []
        if new:
            self.emit("activity_updated", 0)
            lanes_in = {c.name: [] for c in self._event_lanes()}
            if lanes_in:
                self.emit("lanes_updated", lanes_in)
        return new

    def _forget_in_home(self, acc_id):
        """Unfollowed: their posts and boosts leave Home as they leave the server's.
        Kept, they stayed there — and showed up anew when the unfollow also took them
        out of a list that had kept them out of Home (lists.hide_members, 27.10)."""
        n = self.store.drop_items_by("home", acc_id)
        if n:
            log.info("unfollowed: %d of their posts out of Home", n)
            self.emit("lanes_updated", {lane.name: [] for lane in self.lanes
                                        if lane.source == "home"})

    UNFOLLOW_CHECK_S = 6 * 3600

    def _forget_unfollowed_elsewhere(self):
        """Unfollowed in another client or on the server's page: fedtail hears of it
        only by asking. Every few hours the people whose posts Home holds are asked
        about; who was followed last time and isn't now leaves Home. Who was never
        followed (a followed tag's posts) is never taken out: only a follow that ended."""
        me = (self.me or {}).get("id")
        authors = [a for a in self.store.authors_in("home", 400) if a != me]
        if not authors:
            return 0
        now = set()
        for i in range(0, len(authors), 40):
            chunk = authors[i:i + 40]
            rel = self.api.relationships(chunk) or []
            now |= {r["id"] for r in rel if r.get("following") or r.get("requested")}
        before = set(self.store.kv_get("home_followed", []) or [])
        gone = [a for a in authors if a in before and a not in now]
        for a in gone:
            self._forget_in_home(a)
        self.store.kv_set("home_followed", sorted(now))
        if gone:
            log.info("unfollowed elsewhere: %d account(s) out of Home", len(gone))
        return len(gone)

    def _note_follow(self, acc_id, rel, when):
        """The follow date into (or out of) my private note on them, on the server — so
        every device and client of mine sees it. A server without notes: just here."""
        from .model import note_followed, note_with_followed
        rel = rel or {}
        old = rel.get("note")
        if old is None:
            try:
                old = self.api.relationship(acc_id).get("note") or ""
            except ApiError:
                return rel
        day = when[:10] if when else None
        if when and note_followed(old):
            return rel  # followed before, unfollowed elsewhere: the first date stays
        new = note_with_followed(old, day)
        if new == (old or "").rstrip():
            return rel
        try:
            self.api.set_note(acc_id, new)
            log.info("follow date %s in the note on %s", day or "taken out", acc_id)
            return dict(rel, note=new)
        except ApiError as e:
            log.info("note on %s: %s", acc_id, e)
            return rel

    def followed_since(self, acc_id, rel=None):
        """Since when I follow them — from my note on them (any client of mine wrote it
        there through fedtail) or from what this profile saw. ISO date or None."""
        from .model import note_followed
        return note_followed((rel or {}).get("note")) or \
            (self.store.kv_get("followed_at", {}) or {}).get(acc_id)

    def follow_options(self, acc_id, reblogs=None, languages=None):
        """Their boosts shown or not, the languages read (feed.per_person_follow)."""
        def job():
            rel = self.api.follow_options(acc_id, reblogs, languages)
            self._relations[acc_id] = (time.monotonic(), rel)
            log.info("follow %s: boosts %s, languages %s", acc_id,
                     (rel or {}).get("showing_reblogs"), (rel or {}).get("languages"))
            return rel
        return self.submit(job)

    def notify_posts(self, acc_id, on=True):
        """The bell on someone I follow: their every new post comes as a notification
        (in Likes & boosts, with activity.types including "status")."""
        return self.call_api("notify_posts", acc_id, on)

    def followed_among(self, accounts):
        """Which of these accounts I follow — why a thread I'm not subscribed to still
        reaches my Home: the server puts there replies between people I follow.
        Future: [account] in the given order, me left out."""
        mine = (self.me or {}).get("id")
        uniq = list({a["id"]: a for a in accounts if a["id"] != mine}.values())

        def job():
            if not uniq:
                return []
            rel = {r["id"]: r for r in self.api.relationships([a["id"] for a in uniq[:40]])}
            return [a for a in uniq if rel.get(a["id"], {}).get("following")]
        return self.submit(job)

    def search(self, q):
        """People, tags and posts for a query; addresses (@user@server, a profile
        or post URL) are fetched from their home server by mine."""
        def job():
            got = self.api.search(q.strip(), resolve=True, limit=20)
            self.store.put_statuses(got.get("statuses") or [])
            accounts = got.get("accounts") or []
            rel = {r["id"]: r for r in self.api.relationships([a["id"] for a in accounts])} \
                if accounts else {}
            return {"accounts": accounts, "relations": rel,
                    "hashtags": got.get("hashtags") or [], "statuses": got.get("statuses") or []}
        return self.submit(job)

    def people(self, acc_id, which, max_id=None):
        """One page of whom an account follows (which="following") or who follows
        it ("followers"), with my relationship to each: ({accounts, relations}, next)."""
        def job():
            fetch = self.api.following if which == "following" else self.api.followers
            accounts, nxt = fetch(acc_id, max_id)
            rel = {r["id"]: r for r in self.api.relationships([a["id"] for a in accounts])} \
                if accounts else {}
            return {"accounts": accounts, "relations": rel}, nxt
        return self.submit(job)

    def people_from_origin(self, acc, which, have_ids=(), limit=40):
        """Whom someone from another server follows / who follows them, as their own
        server lists it (ActivityPub, without my token), each found through my server:
        ({accounts, relations, total}, None). Lists hidden by their owner give nothing."""
        def job():
            from . import replies
            actor = None
            for url in (acc.get("uri"), acc.get("url")):
                if url:
                    try:
                        actor = self._origin_json(url)
                    except Exception as e:  # noqa: BLE001
                        log.debug("actor %s: %s", url, e)
                    if isinstance(actor, dict) and actor.get(which):
                        break
            coll_url = actor.get(which) if isinstance(actor, dict) else None
            if not coll_url:
                return {"accounts": [], "relations": {}, "total": None}, None
            coll = self._origin_json(coll_url) if isinstance(coll_url, str) else coll_url
            total = coll.get("totalItems") if isinstance(coll, dict) else None
            try:
                uris = replies.collection_items(self._origin_json, coll or {}, pages=3)
            except Exception as e:  # noqa: BLE001
                log.info("%s of %s: %s", which, acc.get("id"), e)
                uris = []
            have, found = set(have_ids), []
            for uri in uris[:limit]:
                try:
                    got = self.api.search(uri, kind="accounts", resolve=True, limit=1)
                except Exception as e:  # noqa: BLE001
                    log.debug("resolve %s: %s", uri, e)
                    continue
                for a in (got or {}).get("accounts") or []:
                    if a["id"] not in have:
                        have.add(a["id"])
                        found.append(a)
            rel = {r["id"]: r for r in self.api.relationships([a["id"] for a in found])} \
                if found else {}
            log.info("%s of %s from their server: %s listed, %d found here", which,
                     acc.get("id"), total, len(found))
            return {"accounts": found, "relations": rel, "total": total}, None
        return self.bg.submit(job)

    def tag_info(self, name):
        return self.call_api("tag", name)

    def follow_tag(self, name, on=True):
        return self.call_api("follow_tag", name, on)

    def followed_tags(self):
        return self.call_api("followed_tags")

    # ---- completing hashtags while writing -------------------------------------------
    def prepare_tags(self):
        """Warm up what tag_suggestions() needs, in the background: the tags of the
        stored posts and the tags you follow."""
        self.bg.submit(self.store.tag_counts)
        if getattr(self, "_followed_tag_names", None) is None:
            self._followed_tag_names = set()

            def followed():
                try:
                    self._followed_tag_names = {t["name"] for t in self.api.followed_tags()
                                                if t.get("name")}
                except Exception as e:  # noqa: BLE001 — only suggestions are missing then
                    log.info("followed tags: %s", e)
            self.bg.submit(followed)

    def prepare_people(self):
        self.bg.submit(self.store.people_counts)

    def prepare_emoji(self):
        """The server's own emoji, once a run, for emoji_suggestions()."""
        if getattr(self, "_emoji", None) is not None or not self.api:
            return
        self._emoji = []

        def job():
            try:
                self._emoji = [e for e in self.api.custom_emojis()
                               if e.get("shortcode") and e.get("visible_in_picker", True)]
            except Exception as e:  # noqa: BLE001 — only suggestions are missing then
                log.info("custom emoji: %s", e)
        self.bg.submit(job)

    def emoji_suggestions(self, prefix, limit=8):
        """The server's emoji whose shortcode has prefix (no ":"): starting with it
        first, then containing it. [(shortcode, emoji dict)]."""
        p = prefix.casefold()
        if not p:
            return []
        every = getattr(self, "_emoji", None) or []
        starts = [e for e in every if e["shortcode"].casefold().startswith(p)]
        within = [e for e in every if p in e["shortcode"].casefold() and e not in starts]
        best = sorted(starts, key=lambda e: e["shortcode"].casefold()) + \
            sorted(within, key=lambda e: e["shortcode"].casefold())
        return [(e["shortcode"], e) for e in best[:limit]]

    def mention_suggestions(self, prefix, limit=8):
        """People whose address or name starts with prefix (no "@"), the most seen
        first: [(acct, display name)]. Never yourself."""
        p = prefix.casefold()
        if not p:
            return []
        me = (self.me or {}).get("acct", "").casefold()
        found = []
        for key, (acct, name, n) in (self.store.people_counts(compute=False) or {}).items():
            if key == me:
                continue
            words = [key, key.split("@")[0]] + [w.casefold() for w in (name or "").split()]
            if any(w.startswith(p) for w in words):
                found.append((-n, acct.casefold(), acct, name))
        found.sort()
        return [(acct, name) for _n, _k, acct, name in found[:limit]]

    def search_people(self, q, limit=8):
        """Ask the server for accounts matching q (no fetching from other servers):
        a future of [(acct, display name)]."""
        def job():
            got = self.api.search(q, "accounts", resolve=False, limit=limit)
            return [(a["acct"], a.get("display_name") or "") for a in got.get("accounts") or []]
        return self.submit(job)

    def tag_suggestions(self, prefix, limit=8):
        """Tags starting with prefix (no "#"): the ones you follow first, then the
        most used in the posts fedtail has seen."""
        p = prefix.casefold()
        if not p:
            return []
        followed = getattr(self, "_followed_tag_names", None) or set()
        counts = self.store.tag_counts(compute=False) or {}
        score = {}
        for key, (name, n) in counts.items():
            if key.startswith(p):
                score[key] = [name, n]
        for name in followed:
            if name.casefold().startswith(p):
                score.setdefault(name.casefold(), [name, 0])[1] += 1_000_000
        best = sorted(score.values(), key=lambda x: (-x[1], x[0].casefold()))
        return [name for name, _n in best[:limit]]

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
    def my_profile(self):
        """My account as the editor needs it (bio and fields as typed)."""
        return self.call_api("verify_credentials")

    def update_profile(self, **changes):
        def job():
            me = self.api.update_credentials(**changes)
            self.me = me
            self.emit("me_updated", me)
            return me
        return self.submit(job)

    # ---- writing ---------------------------------------------------------------
    def default_visibility(self):
        """post.default_visibility; "server" — what's set on the server's web side."""
        v = self.cfg["post"]["default_visibility"]
        if v == "server":
            v = self.server_prefs.get("posting:default:visibility") or "public"
            if v not in ("public", "unlisted", "private", "direct"):
                v = "public"
        return v

    def reply_visibility(self, parent):
        default = self.default_visibility()
        if parent is None:
            return default
        pv = real(parent).get("visibility", "public")
        if self.cfg["post"]["reply_never_wider"]:
            return narrower(pv, default)
        return default

    def post_accounts(self, reply_to=None):
        """The editor's "From": one account here — nothing to choose (core/merged.py has
        the window with all of them)."""
        return [], ""

    def post(self, text, visibility, reply_to=None, spoiler="", media=(), draft_key=None,
             language=None, sensitive=False, poll=None, quote=None, scheduled_at=None,
             account=None):
        """media: [(path, description)], [(path, description, (x, y) focus point)] or
        [(path, description, focus or None, cover picture's path)].
        language: ISO 639 code, None — post.language,
        "" — none (the server's default). The draft is dropped once the post is out,
        even if the window that sent it is gone by then."""
        lang = self.cfg["post"]["language"] if language is None else language
        from .model import chain_parts
        parts = chain_parts(text) if self.cfg["post"].get("chain", True) and \
            not scheduled_at else [text]
        if len(parts) > 1:
            text, rest = parts[0], parts[1:]
        else:
            rest = []

        def job():
            ids = [(self.api.upload_media(m[0], m[1], m[2] if len(m) > 2 else None,
                                          thumbnail=m[3]) if len(m) > 3 and m[3] else
                    self.api.upload_media(m[0], m[1], m[2] if len(m) > 2 else None))["id"]
                   for m in media]
            extra = {"language": lang} if lang else {}
            if sensitive and ids:
                extra["sensitive"] = True
            if poll and not ids:  # a server takes either pictures or a poll
                extra["poll"] = poll
            if quote:
                extra["quoted_status_id"] = quote
            if self.cfg["post"].get("quote_policy"):
                extra["quote_policy"] = self.cfg["post"]["quote_policy"]
            policy = interaction_policy(self.cfg["post"])
            if policy and self.caps.software == "gotosocial":
                extra["interaction_policy"] = policy
            if scheduled_at:
                extra["scheduled_at"] = scheduled_at
                st = self.api.post_status(text, visibility, reply_to, spoiler, ids,
                                          self.markdown, **extra)
                if draft_key:
                    self.delete_draft(draft_key)
                log.info("scheduled for %s", scheduled_at)
                return dict(st or {}, scheduled=True)
            started = time.time()
            wait = max(10, int(self.cfg["post"].get("send_timeout", 90)))
            try:
                st = self.api.post_status(
                    text, visibility, reply_to, spoiler, ids, self.markdown,
                    idempotency_key=send_key(self.me and self.me["id"], text, reply_to,
                                             visibility, spoiler),
                    timeout=(10, wait), **extra)
            except (requests.Timeout, requests.ConnectionError) as e:
                # the request may well have got there and the post been made, only the
                # answer was lost: look before saying "not sent" (a retry = a double)
                st = self._find_sent(text, reply_to, started)
                if st is None:
                    raise MaybeSent(e) from e
                log.info("send: no answer (%s), but the post is there: %s",
                         e.__class__.__name__, st.get("id"))
            log.debug("posted %s", st.get("id"))
            chain, prev = [st], st
            for i, part in enumerate(rest):  # the rest of a chain: each answering the last
                try:
                    prev = self.api.post_status(part, visibility, prev["id"], spoiler, [],
                                                self.markdown,
                                                **({"language": lang} if lang else {}))
                    chain.append(prev)
                except ApiError as e:
                    log.warning("chain: part %d of %d failed: %s", i + 2, len(rest) + 1, e)
                    self.emit("error", f"{len(chain)} / {len(rest) + 1}: {e}")
                    break
            if rest:
                log.info("chain: %d posts", len(chain))
            # the post is out; nothing below may turn that into a reported failure
            try:
                self.sound_moment("sent")
                if draft_key:
                    self.delete_draft(draft_key)
                self.store.put_statuses(chain)
                self.mark_read([x["id"] for x in chain] + ([reply_to] if reply_to else []))
                if "direct" in self.lane_by_name and self._carry_my_direct(chain):
                    self.emit("lanes_updated", {"direct": []})  # the dialogue: mine at once
                self._auto_subscribe([st])
                if reply_to:
                    # "you replied" under the post answered: the lanes it is in look again
                    # now (it changed no lane's list of posts, so nothing else tells them)
                    self.emit("parents")
            except Exception:
                log.exception("bookkeeping after post failed")
            self.poll_now()
            return dict(st, chain=len(chain)) if rest else st
        return self.submit(job)

    def _find_sent(self, text, reply_to, since):
        """My post with this text (and this parent) made since then — or None, also when
        the server can't say right now either."""
        if not self.me:
            return None
        try:
            mine = self.api.account_statuses(self.me["id"], limit=10) or []
        except (requests.RequestException, ApiError) as e:
            log.warning("send: can't check whether the post got there: %s",
                        e.__class__.__name__)
            return None
        return next((st for st in mine if looks_sent(st, text, reply_to, since)), None)

    def edit(self, status, text, spoiler="", draft_key=None, media=None):
        """Change my post's text and warning; its pictures stay. media: {media id:
        (description, (x, y) focus or None)} — their words and focus point anew."""
        s = real(status)

        def job():
            ids = [m["id"] for m in s.get("media_attachments") or []]
            attrs = [dict({"id": mid, "description": desc or ""},
                          **({"focus": f"{float(focus[0]):.2f},{float(focus[1]):.2f}"}
                             if focus else {}))
                     for mid, (desc, focus) in (media or {}).items() if mid in ids]
            st = self.api.edit_status(s["id"], text, spoiler, ids, self.markdown,
                                      media_attributes=attrs) if attrs else \
                self.api.edit_status(s["id"], text, spoiler, ids, self.markdown)
            self.store.put_statuses([st])
            if draft_key:
                self.delete_draft(draft_key)
            self.emit("status_updated", st)
            return st
        return self.submit(job)

    def source(self, status):
        """What I typed for this post; the shown text if the server can't say."""
        s = real(status)

        def job():
            try:
                return self.api.status_source(s["id"])
            except ApiError:
                from .model import html_to_text
                return {"text": html_to_text(s.get("content", "")),
                        "spoiler_text": s.get("spoiler_text", "")}
        return self.submit(job)

    def history(self, status):
        return self.call_api("status_history", real(status)["id"])

    def _update(self, st):
        self.store.put_statuses([st])
        self.emit("status_updated", st)
        return st

    def favourite(self, status):
        s = real(status)
        return self.submit(lambda: self._update(self.api.favourite(s["id"],
                                                                   not s.get("favourited"))))

    def vote(self, status, choices):
        """Vote in the post's poll (choices: option indexes); the post comes back
        with the counts and my votes in it."""
        s = real(status)
        pid = (s.get("poll") or {}).get("id")
        if not pid or not choices:
            raise ValueError("no poll or no choice")
        return self.submit(lambda: self._update(dict(s, poll=self.api.vote(pid, choices))))

    def refresh_poll(self, status):
        """Fresh counts for the post's poll."""
        s = real(status)
        pid = (s.get("poll") or {}).get("id")
        return self.submit(lambda: self._update(dict(s, poll=self.api.poll(pid))))

    def translate(self, status):
        """The post in the interface's language, by my server (a future)."""
        from ..i18n import current_language
        return self.call_api("translate", real(status)["id"], current_language())

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
    def vapid_key(self):
        """The server's public key a browser's push subscription is made with ("" —
        the server has no Web Push)."""
        def job():
            v2 = self.api.instance_v2() or {}
            key = ((v2.get("configuration") or {}).get("vapid") or {}).get("public_key")
            return str(key or "")
        return self.submit(job)

    # what a push subscription is told about: everything the activity shows
    PUSH_ALERTS = {"mention": True, "status": True, "reblog": True, "follow": True,
                   "follow_request": True, "favourite": True, "poll": True, "update": True}

    def push_subscribe(self, endpoint, p256dh, auth, alerts=None, policy="all"):
        return self.call_api("push_subscribe", endpoint, p256dh, auth,
                             alerts or self.PUSH_ALERTS, policy)

    def push_subscription(self):
        def job():
            try:
                return self.api.push_subscription()
            except ApiError as e:
                if e.status == 404:  # none yet
                    return None
                raise
        return self.submit(job)

    def push_unsubscribe(self):
        return self.call_api("push_unsubscribe")

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

    def _pinned_from_origin(self, acc_id, limit=10):
        from . import replies
        try:
            acc = self.api.account(acc_id) or {}
        except ApiError:
            return []
        if "@" not in (acc.get("acct") or "") or not acc.get("uri"):
            return []  # one of my server's own: it knows their pins
        try:
            actor = self._origin_json(acc["uri"])
            featured = actor.get("featured") if isinstance(actor, dict) else None
            uris = replies.collection_items(self._origin_json, featured, pages=1) \
                if featured else []
        except Exception as e:  # noqa: BLE001 — someone else's server
            log.debug("pins of %s at their server: %s", acc_id, e)
            return []
        got = []
        for uri in uris[:limit]:
            try:
                found = self.api.search(uri, kind="statuses", resolve=True, limit=1)
            except ApiError as e:
                log.debug("resolve pin %s: %s", uri, e)
                continue
            got += [dict(st, pinned=True) for st in (found or {}).get("statuses") or []]
        log.info("pins of %s: %d at their server, %d found here", acc_id, len(uris), len(got))
        return got

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

        def job():
            st = self.api.bookmark(s["id"], on) or dict(s, bookmarked=on)
            self.store.put_statuses([st])
            if on:
                self.store.put_items("bookmarks", [(st["id"], st, now_iso())])
            self.emit("status_updated", st)
            self.emit("lanes_updated", {"bookmarks": []})
            return st
        return self.submit(job)

    def boost(self, status):
        s = real(status)

        def job():
            res = self.api.reblog(s["id"], not s.get("reblogged"))
            return self._update((res or {}).get("reblog") or self.api.status(s["id"]))
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

    def redraft(self, status):
        """Delete my post and give back what it was made of, for a new draft: its text as
        I typed it (the source, not the server's HTML), CW, who sees it, language, what it
        answers. Pictures don't come back (servers drop them with the post)."""
        s = real(status)

        def job():
            src = {}
            try:
                src = self.api.status_source(s["id"]) or {}
            except ApiError as e:
                log.info("redraft %s: no source (%s), the text from the card", s["id"], e)
            self.api.delete_status(s["id"])
            self.store.delete_status(s["id"])
            self.emit("status_deleted", s["id"])
            from .model import html_to_text
            return {"text": src.get("text") or html_to_text(s.get("content") or ""),
                    "cw": src.get("spoiler_text", s.get("spoiler_text") or ""),
                    "visibility": s.get("visibility") or "private",
                    "language": s.get("language") or "",
                    "in_reply_to_id": s.get("in_reply_to_id"),
                    "media": len(s.get("media_attachments") or [])}
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
    @staticmethod
    def draft_key(reply_to_id=None, quote_id=None):
        if quote_id:
            return f"quote:{quote_id}"
        return f"reply:{reply_to_id}" if reply_to_id else "new"

    def get_draft(self, key):
        return self.store.get_draft(key)

    def save_draft(self, key, data):
        if self.cfg["post"]["drafts_autosave"]:
            self.store.save_draft(key, data)
            if self.sync:
                self.sync.record_draft(key)

    def delete_draft(self, key):
        """A draft sent or emptied: gone here, and on my other devices (sync.drafts)."""
        self.store.delete_draft(key)
        if self.sync:
            self.sync.record_draft(key)

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
        self.store.kv_set(f"ui.{key}", value)

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

    def shutdown(self):
        self._stop.set()
        self._wake.set()
        if self.sync:
            self.sync.stop()  # its last round sends what was marked just now
        if getattr(self, "_stream", None) is not None:
            self._stream.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.bg.shutdown(wait=False, cancel_futures=True)
        if self._poller:
            self._poller.join(timeout=3)
        # what is running already finishes (a little while) before the database closes
        # under it: no "closed database" from a badge count or a reminder at exit
        deadline = time.monotonic() + 3
        for pool in (self.pool, self.bg):
            pool.join(deadline)
        # a poll stuck in a slow request must not hold the exit: what's written is
        # committed already, an unclosed database is fine
        if self._poll_lock.acquire(timeout=3):
            try:
                self.store.close()
            finally:
                self._poll_lock.release()
        else:
            # not a problem (said as one, it looked like one in the night's log): SQLite
            # has every commit on disk, the process ending closes the file
            log.info("exit: a poll still waits for the server — not waited for; all "
                     "it stored is on disk")
