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
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from .. import diag, protocols
from ..protocols.base import RateLimited
from ..protocols.mastodon import api as api_module
from ..protocols.mastodon import counters
from ..protocols.mastodon.api import ApiError, Capabilities
from ..version import USER_AGENT
from . import auth, lanes, search, sources, subs, taggroups, threads
from .events import Events
from .model import id_after, interaction_policy, looks_sent, narrower, real, send_key
from .social import SocialMixin
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


class Core(SocialMixin):
    def __init__(self, cfg, paths, api_class=None):
        self.cfg = cfg
        self.paths = paths
        # what this account's server speaks (docs/PROTOCOLS.md): the client, its errors,
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
        # read marks and thread states shared with the account's other devices (sync.*):
        # recorded whenever it is on, sent by the thread polling starts
        self.sync = None
        if cfg.get("sync", {}).get("enabled"):
            from .sync import Sync
            self.sync = Sync(self)
        self._relations = {}  # acc_id -> (when, relationship), see relation_known
        self.caps = Capabilities()
        self._silence_seen = {}  # status id -> muted thread's root or None (_mention_entry)
        self._conv_of = {}        # last status id -> (conversation id, unread on the server)
        self.server_prefs = {}    # what I set on the server's web side (its preferences)
        self.browse_empty = set()  # browse sources (local, federated) the server gave nothing
        self.sources = {}
        self.lists = []           # [{"id", "title", "exclusive"}] from the server
        self.list_members = {}    # list id -> {account ids}
        self._lists_version = 0
        self._lists_checked = None  # monotonic time of the last check; None: never
        self.lanes = lanes.enabled(cfg)
        self.tag_groups = []  # [{"any", "all", "none", "name", "saved"}], see taggroups
        self.lane_by_name = {lane.name: lane for lane in self.lanes}
        self.follow_requests = []
        self._limits = {}
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
        self._honest_checked = {}  # status id -> when its origin was asked
        self._completed = {}  # thread root id -> when its missing replies were looked for
        self._choices = {}  # this run's choices over lanes (see choice())
        self.muted, self.blocked = set(), set()
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
        self.events.emit(name, payload)

    @property
    def logged_in(self):
        return self.auth is not None

    @property
    def markdown(self):
        mode = self.cfg["account"]["markdown"]
        return self.caps.markdown if mode == "auto" else mode == "on"

    # ---- login -----------------------------------------------------------------
    def begin_login(self, server):
        def job():
            if not api_module.cleartext_ok(server):
                # the token would cross the internet in the clear: only a server here,
                # at home (localhost, a private address, .local/.lan) may be http://
                from ..i18n import _
                raise ValueError(_("login_insecure"))
            api = self.api_class(server)
            app = api.register_app()
            self._pending_login = (api, app)
            return api.authorize_url(app["client_id"])
        return self.submit(job)

    def finish_login(self, code, expect=None):
        """expect: (server, acct) this profile already is — logging in anew must not
        put another account into its data (read marks, drafts, lists are that one's)."""
        def job():
            api, app = self._pending_login
            token = api.get_token(app["client_id"], app["client_secret"], code)
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
            from . import profiles
            profiles.remember(self.paths, me, self.auth["server"])  # for the switcher
            self.sources = sources.make_sources(api, me["id"])
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
        every poll asks each lane (a dozen requests and some CPU each time)."""
        self._wake.set()

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

    def _poll_loop(self):
        while not self._stop.is_set():
            try:
                self.poll_once()
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
            self._wake.wait(self.cfg["poll"]["interval_seconds"])
            self._wake.clear()
            gap = float(self.cfg["poll"].get("stream_gap_seconds", 10))
            left = gap - (time.monotonic() - done)
            if not getattr(self, "_urgent", False) and left > 0 and not self._stop.is_set():
                # woken by the stream right after a poll: gather what else comes meanwhile
                self._wake.wait(left)  # Refresh still cuts it short
                self._wake.clear()
            self._urgent = False

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
        try:
            got = self._poll_once()
            self._last_poll_ok = time.time()
            return got
        finally:
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
            self._step("silence+lists")
            if "direct" in self.lane_by_name:
                self.sync_conversations()  # read here = read on the server (social.py)
                self._step("conversations")
            if "subs" in self.lane_by_name:
                try:
                    sc = self.cfg["subs"]
                    new_by_source["subs"] = subs.check(
                        self.store, self.api, self.me["id"], sc["interval_minutes"],
                        sc["active_days"], sc["max_threads"])
                except Exception as e:
                    self.emit("error", f"subs: {e}")
                self._step("subs")
            lazy = {lane.source for lane in self.lanes if lane.lazy}
            open_sources = {self.lane_by_name[n].source
                            for n in {self._active_lane, *self._active_lanes}
                            if n in self.lane_by_name}
            for name in lanes.sources_needed(self.lanes):
                if name not in self.sources:
                    continue
                if name in lazy:  # browse lanes: only while open, newest page only
                    if name not in open_sources:
                        continue
                    try:
                        new_by_source[name] = sources.refresh_top(
                            self.store, self.sources[name], fc["page_size"])
                        self.store.prune(name, self.keep_per_lane() // 3)
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
            new_requests = []
            if "requests" in self.lane_by_name:
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
                except Exception as e:
                    self.emit("error", f"requests: {e}")

            new_activity = []
            if "activity" in self.lane_by_name:
                try:
                    new_activity = self._poll_activity()
                    if new_activity:
                        self._warm_lanes()  # the window counts every lane on this event
                        self.emit("activity_updated", len(new_activity))
                except Exception as e:
                    self.emit("error", f"activity: {e}")

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
            per_lane = self._split_by_lane(new_by_source)
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
            items = self.store.items(source, 400)  # oldest -> newest
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
        """Emit 'notify' with [(lane, status-or-account)] for lanes the user wants."""
        wanted = set(self.cfg["notify"]["lanes"])
        never = set(self.cfg["notify"].get("except") or ())
        out, quiet = [], []
        for name, ids in per_lane.items():
            lane = self.lane_by_name[name]
            if not ids:
                continue
            if not self._notify_wanted(name, wanted, never):
                quiet.append(f"{name}+{len(ids)}")
                continue
            id_set = set(ids)
            rows = self.store.items(lane.source, len(ids) + 50)
            if not self.cfg["feed"].get("repeat_boosts", False):  # not shown: no news
                rows = self._without_repeats(lane.source, rows)
            sts = [st for item_id, st in rows if item_id in id_set]
            unread = self.store.read_set(st["id"] for st in sts)
            out += [(name, st) for st in sts if st["id"] not in unread and not self.silenced(st)]
        if new_requests and self._notify_wanted("requests", wanted, never):
            out += [("requests", acc) for acc in new_requests]
        if new_activity and self._notify_wanted("activity", wanted, never):
            out += [("activity", n) for n in new_activity]
        if quiet:  # "why no notification?" — answered by the log
            log.info("notify: not asked for (notify.lanes / notify.except): %s",
                     ", ".join(quiet))
        if out:
            self.emit("notify", out)

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
                                 self.cfg["lanes"]["mentions_all"],
                                 self.cfg["subs"]["replies_to_me"],
                                 self._hidden_authors(),
                                 frozenset(self.cfg["lists"]["hide_in"]),
                                 self.cfg["lanes"].get("direct_apart", True)
                                 and "direct" in self.lane_by_name)

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
        newest, _sort = self.store.activity_newest()
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
        return self.store.activity_recent(limit)

    def activity_seen_mark(self):
        return self.store.kv_get("activity_seen", "")

    def activity_unread(self):
        return self.store.activity_count_after(self.activity_seen_mark())

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

    def mute(self, acc_id, on=True):
        return self._silence(self.api.mute, self.muted, acc_id, on)

    def block(self, acc_id, on=True):
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
        return self.submit(self.api.set_notification_policy, **changes)

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
        return self.submit(self.api.dismiss_announcement, aid)

    def scheduled(self):
        return self.submit(self.api.scheduled)

    def cancel_scheduled(self, sid):
        return self.submit(self.api.cancel_scheduled, sid)

    def set_note(self, acc_id, text, old=""):
        """My private note on them; fedtail's follow-date line (in `old`) stays on."""
        from .model import note_followed, note_with_followed
        return self.submit(self.api.set_note, acc_id,
                           note_with_followed(text, note_followed(old)))

    def filters(self):
        return self.submit(self.api.filters)

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

    def add_filter(self, title, keywords, action="warn", contexts=None):
        args = (title, keywords, action) + ((tuple(contexts),) if contexts else ())
        return self.submit(self.api.create_filter, *args)

    def delete_filter(self, filter_id):
        return self.submit(self.api.delete_filter, filter_id)

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
        got = [{"id": x["id"], "title": x.get("title", ""), "exclusive": bool(x.get("exclusive"))}
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
        new_lanes = lanes.enabled(self.cfg, got, self.tag_groups)
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
            out.append(dict(taggroups.normal(g), name=g.get("name") or "", saved=False))
        for g in self.store.kv_get("tag_groups", []) or []:
            out.append(dict(taggroups.normal(g), name=g.get("name") or "", saved=True))
        return out

    def tag_group_timeline(self, spec, max_id=None):
        """A page of several tags at once, for a search tab."""
        def job():
            page = taggroups.fetch(self.api.tag_timeline, spec,
                                   limit=self.cfg["feed"]["page_size"], max_id=max_id)
            self.store.put_statuses(page)
            return page
        return self.submit(job)

    def save_tag_group(self, spec, name=""):
        """A search of several tags kept as a lane in the sidebar (group "Теги")."""
        def job():
            saved = [g for g in self.store.kv_get("tag_groups", []) or []
                     if taggroups.key(g) != taggroups.key(spec)]
            saved.append(dict(taggroups.normal(spec), name=name))
            self.store.kv_set("tag_groups", saved)
            self._apply_lists(list(self.lists), self.list_members)
            return taggroups.lane_name(spec)
        return self.submit(job)

    def drop_tag_group(self, lane_name):
        def job():
            saved = [g for g in self.store.kv_get("tag_groups", []) or []
                     if taggroups.lane_name(g) != lane_name]
            self.store.kv_set("tag_groups", saved)
            self._apply_lists(list(self.lists), self.list_members)
        return self.submit(job)

    def lane_title(self, name):
        """A list's title; None for the built-in lanes (their names are translated)."""
        if taggroups.is_tags(name):
            g = next((g for g in self.tag_groups if taggroups.lane_name(g) == name), None)
            return (g or {}).get("name") or taggroups.title(taggroups.spec_of(name) or {})
        if lanes.is_list(name):
            lid = name[len(lanes.LIST_PREFIX):]
            return next((x["title"] for x in self.lists if x["id"] == lid), "?")
        return None

    def lists_of(self, acc_id):
        return {lid for lid, m in self.list_members.items() if acc_id in m}

    def create_list(self, title, exclusive=False, add=None):
        def job():
            x = self.api.create_list(title, exclusive)
            try:
                if add:  # refused (not followed yet): waits, as with an existing list
                    self._list_add_or_wait(x["id"], add)
            finally:
                self._refresh_lists()  # the new list shows whatever happened to the add
            return x
        return self.submit(job)

    def update_list(self, list_id, title, exclusive):
        def job():
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
        key = (self.store.items_version.get(lane.source, 0), self.store.status_version, limit,
               self.me["id"] if self.me else None, only_posts, self._lists_version,
               self._silence_version, repeats)
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
        self._lane_cache[name] = (key, kept)
        return kept

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

    def account_statuses(self, acc_id, max_id=None):
        def job():
            page = self.api.account_statuses(acc_id, limit=self.cfg["feed"]["page_size"],
                                             max_id=max_id)
            self.store.put_statuses(page)
            return page
        return self.submit(job)

    def account(self, acc_id):
        return self.submit(self.api.account, acc_id)

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
            if self.cfg["feed"].get("follow_date_note", True):
                rel = self._note_follow(acc_id, rel, since.get(acc_id) if on else None)
            return rel
        return self.submit(job)

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
        return self.submit(self.api.notify_posts, acc_id, on)

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
        return self.submit(self.api.tag, name)

    def follow_tag(self, name, on=True):
        return self.submit(self.api.follow_tag, name, on)

    def followed_tags(self):
        return self.submit(self.api.followed_tags)

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
        return self.submit(self.api.verify_credentials)

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

    def post(self, text, visibility, reply_to=None, spoiler="", media=(), draft_key=None,
             language=None, sensitive=False, poll=None, quote=None, scheduled_at=None):
        """media: [(path, description)] or [(path, description, (x, y) focus point)].
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
            ids = [self.api.upload_media(m[0], m[1], m[2] if len(m) > 2 else None)["id"]
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
                    self.store.delete_draft(draft_key)
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
                if draft_key:
                    self.store.delete_draft(draft_key)
                self.store.put_statuses(chain)
                self.mark_read([x["id"] for x in chain] + ([reply_to] if reply_to else []))
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

    def edit(self, status, text, spoiler="", draft_key=None):
        """Change my post's text and warning; its pictures stay as they are."""
        s = real(status)

        def job():
            ids = [m["id"] for m in s.get("media_attachments") or []]
            st = self.api.edit_status(s["id"], text, spoiler, ids, self.markdown)
            self.store.put_statuses([st])
            if draft_key:
                self.store.delete_draft(draft_key)
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
        return self.submit(self.api.status_history, real(status)["id"])

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
        return self.submit(self.api.translate, real(status)["id"], current_language())

    def report(self, status, comment="", forward=False, category="other"):
        """Tell my server's moderators about a post (and its author); forward: also the
        moderators of the author's server, without saying who reported."""
        s = real(status)
        return self.submit(self.api.report, s["account"]["id"], [s["id"]], comment,
                           forward, category)

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
            self.api.delete_status(s["id"])
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

    def delete_draft(self, key):
        self.store.delete_draft(key)

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
