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

from .. import diag
from . import api as api_module
from . import auth, counters, lanes, search, sources, subs, threads
from .api import USER_AGENT, Api, ApiError, Capabilities, capabilities_from_instance
from .events import Events
from .model import id_after, interaction_policy, narrower, real
from .social import SocialMixin
from .store import Store, now_iso, sort_key

log = logging.getLogger(__name__)

KEEP_PER_SOURCE = 3000
FILTER_WINDOW = 2000


def _due(last, every):
    """Time to do it again? (last: monotonic seconds, None = never done). Not
    "last = 0": monotonic time starts near zero at boot, so that would wait."""
    return last is None or time.monotonic() - last > every


class Core(SocialMixin):
    def __init__(self, cfg, paths, api_class=Api):
        self.cfg = cfg
        self.paths = paths
        self.api_class = api_class
        paths.ensure()
        self.store = Store(paths.db_file)
        self.events = Events()
        # user actions never wait behind background work
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="fedtail")
        self.bg = ThreadPoolExecutor(max_workers=2, thread_name_prefix="fedtail-bg")
        self.auth = auth.load(paths.auth_file)
        self.api = None
        self.me = None
        self.caps = Capabilities()
        self.unsupported = set()  # features the server said it hasn't got (social.py)
        self._conv_of = {}        # last status id -> (conversation id, unread on the server)
        self.server_prefs = {}    # what I set on the server's web side (/api/v1/preferences)
        self.sources = {}
        self.lists = []           # [{"id", "title", "exclusive"}] from the server
        self.list_members = {}    # list id -> {account ids}
        self._lists_version = 0
        self._lists_checked = None  # monotonic time of the last check; None: never
        self.lanes = lanes.enabled(cfg)
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
        self._poll_count = 0
        self._active_lane = None  # the lane on screen: browse lanes are fetched only then
        self._last_poll_s = None
        api_module.SLOW_SECONDS = float(cfg["debug"]["slow_request_seconds"])
        diag.add_stats("core", self.diag_stats)

    # ---- plumbing ------------------------------------------------------------
    def submit(self, fn, *a, **kw):
        return self.pool.submit(fn, *a, **kw)

    def emit(self, name, payload=None):
        if name == "error":
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
            api = self.api_class(server)
            app = api.register_app()
            self._pending_login = (api, app)
            return api.authorize_url(app["client_id"])
        return self.submit(job)

    def finish_login(self, code):
        def job():
            api, app = self._pending_login
            token = api.get_token(app["client_id"], app["client_secret"], code)
            me = self.api_class(api.base, token).me()
            data = {"server": api.base, "client_id": app["client_id"],
                    "client_secret": app["client_secret"], "token": token, "acct": me["acct"]}
            auth.save(self.paths.auth_file, data)
            self.auth = data
            return me
        return self.submit(job)

    def logout(self):
        auth.forget(self.paths.auth_file)
        self.auth = None
        self.api = None

    # ---- connect & poll ----------------------------------------------------------
    def connect(self):
        def job():
            api = self.api_class(self.auth["server"], self.auth["token"])
            me = api.me()
            try:
                caps = capabilities_from_instance(api.instance())
            except Exception:  # instance info is a nicety, not a must
                caps = Capabilities()
            self.api, self.me, self.caps = api, me, caps
            self.load_preferences()
            from . import profiles
            profiles.remember(self.paths, me, self.auth["server"])  # for the switcher
            self.sources = sources.make_sources(api, me["id"])
            if self.cfg["lists"]["enabled"]:
                try:
                    self._refresh_lists()
                except Exception as e:  # lists are a nicety; the rest must start
                    log.warning("lists: %s", e)
            self.emit("ready", me)
            return me
        return self.submit(job)

    def start_polling(self):
        if self._poller:
            return
        self._start_stream()
        self._poller = threading.Thread(target=self._poll_loop, name="fedtail-poll", daemon=True)
        self._poller.start()

    def poll_now(self):
        self._wake.set()

    def _start_stream(self):
        """poll.stream: the server's live stream wakes the poller when something
        arrives. The stream itself fetches nothing: the poll does, as always."""
        if self.cfg["poll"].get("stream", "auto") == "off" or not self.auth or \
                not getattr(self.api, "has_stream", False):  # a test's fake API has none
            return
        from . import stream
        base = self.caps.streaming or self.auth["server"]
        base = base.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        if not base.startswith(("wss://", "ws://")):
            base = "wss://" + base.split("://")[-1]

        def on_event(name):
            if name in stream.WAKE_ON:
                log.debug("stream: %s", name)
                self.poll_now()
        self._stream = stream.Stream(base, self.auth["token"], on_event,
                                     user_agent=USER_AGENT)
        self._stream.start()

    def _poll_loop(self):
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception as e:  # never let the poller die silently
                if self._stop.is_set():
                    return
                log.exception("poll failed")
                self.emit("error", str(e))
            self._wake.wait(self.cfg["poll"]["interval_seconds"])
            self._wake.clear()

    def poll_once(self):
        """One round: catch every source up, check subscriptions, lists, activity,
        follow requests; then tell the frontend. Logged with its timing."""
        if not self.api:
            return
        t = time.monotonic()
        try:
            return self._poll_once()
        finally:
            took = time.monotonic() - t
            self._poll_count += 1
            self._last_poll_s = round(took, 2)
            log.log(logging.WARNING if took > 60 else logging.DEBUG,
                    "poll #%d took %.2f s", self._poll_count, took)

    def _poll_once(self):
        with self._poll_lock:
            first_run = not self.store.kv_get("initialized", False)
            fc = self.cfg["feed"]
            new_by_source = {}
            every = self.cfg["lists"]["refresh_minutes"] * 60
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
            if "direct" in self.lane_by_name:
                self.sync_conversations()  # read here = read on the server (social.py)
            if "subs" in self.lane_by_name:
                try:
                    sc = self.cfg["subs"]
                    new_by_source["subs"] = subs.check(
                        self.store, self.api, self.me["id"], sc["interval_minutes"],
                        sc["active_days"], sc["max_threads"])
                except Exception as e:
                    self.emit("error", f"subs: {e}")
            lazy = {lane.source for lane in self.lanes if lane.lazy}
            active = self.lane_by_name.get(self._active_lane)
            for name in lanes.sources_needed(self.lanes):
                if name not in self.sources:
                    continue
                if name in lazy:  # browse lanes: only while open, newest page only
                    if active is None or active.source != name:
                        continue
                    try:
                        new_by_source[name] = sources.refresh_top(
                            self.store, self.sources[name], fc["page_size"])
                        self.store.prune(name, KEEP_PER_SOURCE // 3)
                    except Exception as e:
                        self.emit("error", f"{name}: {e}")
                    continue
                try:
                    new_by_source[name] = sources.catch_up(
                        self.store, self.sources[name], fc["page_size"], fc["catch_up_limit"])
                    self.store.prune(name, KEEP_PER_SOURCE)
                except ApiError as e:
                    if e.status in (401, 403):
                        self.emit("auth_failed", str(e))
                        return
                    self.emit("error", f"{name}: {e}")
                except Exception as e:  # network down etc.
                    self.emit("error", f"{name}: {e}")

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
                        self.emit("requests_updated", self.follow_requests)
                except Exception as e:
                    self.emit("error", f"requests: {e}")

            new_activity = []
            if "activity" in self.lane_by_name:
                try:
                    new_activity = self._poll_activity()
                    if new_activity:
                        self.emit("activity_updated", len(new_activity))
                except Exception as e:
                    self.emit("error", f"activity: {e}")

            new_statuses = self._new_statuses(new_by_source)
            mine = [st["id"] for st in new_statuses if st["account"]["id"] == self.me["id"]]
            if first_run and fc["first_run_mark_read"]:
                self.store.mark_read([st["id"] for st in new_statuses])
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

            per_lane = self._split_by_lane(new_by_source)
            if any(per_lane.values()):
                self.emit("lanes_updated", per_lane)
            if new_statuses and not first_run:
                self.emit("arrived", [(real(st)["id"], real(st).get("in_reply_to_id"))
                                      for st in new_statuses])
            if not first_run:
                self._notify(per_lane, new_requests, new_activity)
                self._sync_markers()
            self._fetch_parents(new_statuses)
            got = {k: len(v) for k, v in new_by_source.items() if v}
            if got or new_activity or new_requests:
                log.info("new: %s%s%s", got or "-",
                         f" activity+{len(new_activity)}" if new_activity else "",
                         f" requests+{len(new_requests)}" if new_requests else "")

    # ---- read position shared with other clients (markers) -------------------------
    MARKERS = {"home": "home", "notifications": "mentions"}  # marker timeline -> our source

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
        # one list by its title: "list:Друзья" (the id works too)
        titled = {x[5:].casefold() for x in wanted if lanes.is_list(x)}
        out, quiet = [], []
        for name, ids in per_lane.items():
            lane = self.lane_by_name[name]
            if not ids:
                continue
            if name not in wanted and not (lanes.is_list(name) and (
                    "lists" in wanted or self.lane_title(name).casefold() in titled
                    or name[len(lanes.LIST_PREFIX):].casefold() in titled)):
                quiet.append(f"{name}+{len(ids)}")
                continue
            id_set = set(ids)
            sts = [st for item_id, st in self.store.items(lane.source, len(ids) + 50)
                   if item_id in id_set]
            unread = self.store.read_set(st["id"] for st in sts)
            out += [(name, st) for st in sts if st["id"] not in unread and not self.silenced(st)]
        if "requests" in wanted:
            out += [("requests", acc) for acc in new_requests]
        if "activity" in wanted:
            out += [("activity", n) for n in new_activity]
        if quiet:  # "why no notification?" — answered by the log
            log.debug("notify: not asked for (notify.lanes): %s", ", ".join(quiet))
        if out:
            self.emit("notify", out)

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
        types = self.cfg["activity"]["types"]
        fc = self.cfg["feed"]
        newest, _sort = self.store.activity_newest()
        if newest is None:
            self.store.activity_put(self.api.notifications(types, limit=fc["page_size"]))
            self.store.kv_set("activity_seen", self.store.activity_newest()[1])
            return []
        new, cursor = [], newest
        while True:
            page = self.api.notifications(types, limit=fc["page_size"], min_id=cursor)
            if not page:
                break
            new += self.store.activity_put(page)
            nxt = max(page, key=lambda n: sort_key(n.get("created_at"), n["id"]))["id"]
            if nxt == cursor or len(page) < fc["page_size"] or len(new) >= fc["catch_up_limit"]:
                break
            cursor = nxt
        return new

    def activity_entries(self, limit=300):
        return self.store.activity_recent(limit)

    def activity_seen_mark(self):
        return self.store.kv_get("activity_seen", "")

    def activity_unread(self):
        return self.store.activity_count_after(self.activity_seen_mark())

    def mark_activity_seen(self):
        newest = self.store.activity_newest()[1]
        if newest and newest != self.activity_seen_mark():
            self.store.kv_set("activity_seen", newest)
            self.emit("activity_seen", newest)

    # ---- lists ---------------------------------------------------------------------
    # ---- silence: muted and blocked people, server filters ----------------------------
    def _refresh_silence(self):
        muted = {a["id"] for a in self.api.mutes()}
        blocked = {a["id"] for a in self.api.blocks()}
        try:
            domains = {d.lower() for d in self.api.domain_blocks()}
        except Exception as e:  # noqa: BLE001 — a server without it
            log.debug("domain blocks: %s", e)
            domains = self.blocked_domains
        self._silence_checked = time.monotonic()
        if (muted, blocked, domains) != (self.muted, self.blocked, self.blocked_domains):
            self.muted, self.blocked, self.blocked_domains = muted, blocked, domains
            self._silence_version += 1
            self.emit("lanes_updated", {lane.name: [] for lane in self.lanes})

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
            try:
                policy = self.api.notification_policy() or {}
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

    def set_note(self, acc_id, text):
        return self.submit(self.api.set_note, acc_id, text)

    def filters(self):
        return self.submit(self.api.filters)

    def silenced_people(self):
        """{"muted": [accounts], "blocked": [accounts]} for the Silence dialog."""
        def job():
            muted, blocked = self.api.mutes(), self.api.blocks()
            self.muted = {a["id"] for a in muted}
            self.blocked = {a["id"] for a in blocked}
            try:
                self.blocked_domains = {d.lower() for d in self.api.domain_blocks()}
            except Exception as e:  # noqa: BLE001
                log.debug("domain blocks: %s", e)
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
        got = [{"id": x["id"], "title": x.get("title", ""), "exclusive": bool(x.get("exclusive"))}
               for x in self.api.lists()]
        members = {x["id"]: {a["id"] for a in self.api.list_accounts(x["id"])} for x in got}
        self._lists_checked = time.monotonic()
        if got == self.lists and members == self.list_members:
            return
        self._apply_lists(got, members)

    def _apply_lists(self, got, members):
        self.lists, self.list_members = got, members
        for x in got:
            name = f"list:{x['id']}"
            if name not in self.sources:
                self.sources[name] = sources.list_source(self.api, x["id"])
        new_lanes = lanes.enabled(self.cfg, got)
        self.lane_by_name = {lane.name: lane for lane in new_lanes}
        self.lanes = new_lanes
        self._lists_version += 1
        self.emit("lists_changed", list(got))
        self.poll_now()

    def lane_title(self, name):
        """A list's title; None for the built-in lanes (their names are translated)."""
        if lanes.is_list(name):
            lid = name[len(lanes.LIST_PREFIX):]
            return next((x["title"] for x in self.lists if x["id"] == lid), "?")
        return None

    def lists_of(self, acc_id):
        return {lid for lid, m in self.list_members.items() if acc_id in m}

    def create_list(self, title, exclusive=False, add=None):
        def job():
            x = self.api.create_list(title, exclusive)
            if add:
                self.api.list_add(x["id"], add)
            self._refresh_lists()
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

    def set_in_list(self, list_id, acc_id, on):
        def job():
            (self.api.list_add if on else self.api.list_remove)(list_id, acc_id)
            self._refresh_lists()
            # who is hidden where changed: every lane may look different now
            self.emit("lanes_updated", {lane.name: [] for lane in self.lanes})
        return self.submit(job)

    # ---- thread subscriptions ------------------------------------------------------
    def subscribed(self, status):
        """Is the thread this post is in followed? (Knows only threads it has seen.)"""
        return self._sub_root(status) is not None

    def subscribe(self, status):
        def job():
            root = subs.subscribe(self.store, self.api, status)
            self.emit("subs_changed", root)
            return root
        return self.submit(job)

    def _sub_root(self, status):
        st = real(status)
        parent = st.get("in_reply_to_id")
        return self.store.sub_root_of(st["id"]) or \
            (parent and self.store.sub_root_of(parent)) or None

    def unsubscribe(self, status):
        def job():
            root = self._sub_root(status) or real(status)["id"]
            subs.unsubscribe(self.store, root)
            self.emit("subs_changed", root)
            self.emit("lanes_updated", {"subs": []})
            return root
        return self.submit(job)

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
        key = (self.store.items_version.get(lane.source, 0), self.store.status_version, limit,
               self.me["id"] if self.me else None, only_posts, self._lists_version,
               self._silence_version)
        hit = self._lane_cache.get(name)
        if hit and hit[0] == key:
            return hit[1]
        ctx = self._ctx()
        kept = []
        for item_id, st in self.store.iter_items(lane.source,
                                                 max_rows=max(FILTER_WINDOW, limit)):
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

    def unread_ids(self, entries):
        ids = [st["id"] for _, st in entries]
        read = self.store.read_set(ids)
        return {i for i in ids if i not in read}

    def unread_count(self, name):
        return len(self.unread_ids(self.lane_entries(name)))

    def mark_read(self, status_ids):
        status_ids = list(status_ids)
        if status_ids:
            self.store.mark_read(status_ids)
            self.emit("read_changed", status_ids)
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
        'mine' lane fetched). Only for posts that have replies at all, and each
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

    def _origin_json(self, url):
        """An ActivityPub object from someone else's server: no token, short timeout."""
        import requests

        from .api import USER_AGENT
        from .replies import AP_ACCEPT
        r = requests.get(url, timeout=8, headers={"User-Agent": USER_AGENT,
                                                  "Accept": AP_ACCEPT})
        return r.json() if r.status_code == 200 else None

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
        """GET from someone else's server: no token, short timeout."""
        import requests

        from .api import USER_AGENT
        r = requests.get(url, timeout=8, headers={"User-Agent": USER_AGENT})
        return r.json() if r.status_code == 200 else None

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
                    r = requests.get(origin_url, headers=head, timeout=8)
                    got = r.json() if r.status_code == 200 else None
                else:  # another server: only if it has the post already (no fetching)
                    r = requests.get(server + "/api/v2/search", headers=head, timeout=8,
                                     params={"q": st.get("uri"), "type": "statuses",
                                             "resolve": "false", "limit": 1})
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
        return self.submit(self.api.get, f"/api/v1/accounts/{acc_id}")

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
            actor = None
            for url in (acc.get("uri"), acc.get("url")):
                if url:
                    try:
                        actor = self._origin_json(url)
                    except Exception as e:  # noqa: BLE001 — their server, anything goes
                        log.debug("actor %s: %s", url, e)
                    if isinstance(actor, dict) and actor.get("outbox"):
                        break
            if not isinstance(actor, dict) or not actor.get("outbox"):
                log.info("profile %s: no outbox to read", acc.get("id"))
                return []
            limit = min(40, int(fc.get("remote_posts", 20)))
            try:
                uris = replies.outbox_post_uris(self._origin_json, actor["outbox"], limit)
            except Exception as e:  # noqa: BLE001
                log.info("profile %s: outbox: %s", acc.get("id"), e)
                return []
            have = set(have_uris)
            got = []
            for uri in [u for u in uris if u not in have]:
                try:
                    found = self.api.search(uri, kind="statuses", resolve=True, limit=1)
                except Exception as e:  # noqa: BLE001 — gone, not public: skip it
                    log.debug("resolve %s: %s", uri, e)
                    continue
                got += (found or {}).get("statuses") or []
            if got:
                self.store.put_statuses(got)
            log.info("profile %s: outbox lists %d posts, %d new here, fetched in %.1f s",
                     acc.get("id"), len(uris), len(got), time.monotonic() - t)
            return got
        return self.bg.submit(job)

    def relationship(self, acc_id):
        """following, followed_by, requested, … between me and an account."""
        return self.submit(self.api.relationship, acc_id)

    def follow(self, acc_id, on=True):
        return self.submit(self.api.follow, acc_id, on)

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
            st = self.api.post_status(text, visibility, reply_to, spoiler, ids, self.markdown,
                                      **extra)
            log.debug("posted %s", st.get("id"))
            # the post is out; nothing below may turn that into a reported failure
            try:
                if draft_key:
                    self.store.delete_draft(draft_key)
                self.store.put_statuses([st])
                self.mark_read([st["id"]] + ([reply_to] if reply_to else []))
                self._auto_subscribe([st])
            except Exception:
                log.exception("bookkeeping after post failed")
            self.poll_now()
            return st
        return self.submit(job)

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
            acc = self.api.get(f"/api/v1/accounts/{acc_id}") or {}
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
    def diag_stats(self):
        """For the periodic stats line: what could grow or get stuck."""
        out = {"polls": self._poll_count, "last_poll_s": self._last_poll_s,
               "pool_queue": self.pool._work_queue.qsize(),
               "bg_queue": self.bg._work_queue.qsize(),
               "lane_cache": len(self._lane_cache),
               "parents_inflight": len(self._parent_inflight),
               "replies_inflight": len(self._replies_inflight),
               "honest_checked": len(self._honest_checked),
               "lists": len(self.lists)}
        out.update(self.store.diag_counts())
        return out

    def shutdown(self):
        self._stop.set()
        self._wake.set()
        if getattr(self, "_stream", None) is not None:
            self._stream.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.bg.shutdown(wait=False, cancel_futures=True)
        if self._poller:
            self._poller.join(timeout=3)
        # a poll stuck in a slow request must not hold the exit: what's written is
        # committed already, an unclosed database is fine
        if self._poll_lock.acquire(timeout=3):
            try:
                self.store.close()
            finally:
                self._poll_lock.release()
        else:
            log.warning("exit: a poll is still running, database left open")
