"""Core: everything a frontend needs, no GUI.

Network calls return concurrent.futures.Future. Events are emitted from
worker threads (see events.py):

  ready            me (account dict)        connected and ready
  lanes_updated    {lane: [new item ids]}   something new arrived / older loaded
  parents          None                     reply contexts became available
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

from . import auth, lanes, sources, subs, threads
from .api import Api, ApiError, Capabilities, capabilities_from_instance
from .events import Events
from .model import narrower, real
from .store import Store, sort_key

log = logging.getLogger(__name__)

KEEP_PER_SOURCE = 3000
FILTER_WINDOW = 2000


class Core:
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
        self.sources = {}
        self.lists = []           # [{"id", "title", "exclusive"}] from the server
        self.list_members = {}    # list id -> {account ids}
        self._lists_version = 0
        self._lists_checked = 0.0
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

    # ---- plumbing ------------------------------------------------------------
    def submit(self, fn, *a, **kw):
        return self.pool.submit(fn, *a, **kw)

    def emit(self, name, payload=None):
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
        self._poller = threading.Thread(target=self._poll_loop, name="fedtail-poll", daemon=True)
        self._poller.start()

    def poll_now(self):
        self._wake.set()

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
        if not self.api:
            return
        with self._poll_lock:
            first_run = not self.store.kv_get("initialized", False)
            fc = self.cfg["feed"]
            new_by_source = {}
            if self.cfg["lists"]["enabled"] and time.monotonic() - self._lists_checked > \
                    self.cfg["lists"]["refresh_minutes"] * 60:
                try:
                    self._refresh_lists()
                except Exception as e:
                    self.emit("error", f"lists: {e}")
            if "subs" in self.lane_by_name:
                try:
                    sc = self.cfg["subs"]
                    new_by_source["subs"] = subs.check(
                        self.store, self.api, self.me["id"], sc["interval_minutes"],
                        sc["active_days"], sc["max_threads"])
                except Exception as e:
                    self.emit("error", f"subs: {e}")
            for name in lanes.sources_needed(self.lanes):
                if name not in self.sources:
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
                    self._known_requests = ids
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
            if not first_run:
                self._notify(per_lane, new_requests, new_activity)
            self._fetch_parents(new_statuses)

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
                                   if item_id in ids and lane.keep(st, ctx)]
        return per_lane

    def _notify(self, per_lane, new_requests=(), new_activity=()):
        """Emit 'notify' with [(lane, status-or-account)] for lanes the user wants."""
        wanted = set(self.cfg["notify"]["lanes"])
        out = []
        for name, ids in per_lane.items():
            lane = self.lane_by_name[name]
            if not ids or (name not in wanted and
                           not (lanes.is_list(name) and "lists" in wanted)):
                continue
            id_set = set(ids)
            sts = [st for item_id, st in self.store.items(lane.source, len(ids) + 50)
                   if item_id in id_set]
            unread = self.store.read_set(st["id"] for st in sts)
            out += [(name, st) for st in sts if st["id"] not in unread]
        if "requests" in wanted:
            out += [("requests", acc) for acc in new_requests]
        if "activity" in wanted:
            out += [("activity", n) for n in new_activity]
        if out:
            self.emit("notify", out)

    def _ctx(self):
        return lanes.LaneContext(self.me["id"] if self.me else "",
                                 tuple(self.cfg["lanes"]["extra_bots"]),
                                 self.cfg["lanes"]["mentions_all"],
                                 self.cfg["subs"]["replies_to_me"],
                                 self._hidden_authors())

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
    def _hidden_authors(self):
        if not self.cfg["lists"]["exclusive_hides"]:
            return frozenset()
        return frozenset(a for x in self.lists if x.get("exclusive")
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
    def posts_only(self, name):
        saved = self.get_state(f"posts_only.{name}")
        return saved if saved is not None else name in self.cfg["lanes"]["posts_only"]

    def set_posts_only(self, name, on):
        self.set_state(f"posts_only.{name}", bool(on))

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
               self.me["id"] if self.me else None, only_posts, self._lists_version)
        hit = self._lane_cache.get(name)
        if hit and hit[0] == key:
            return hit[1]
        ctx = self._ctx()
        kept = []
        for item_id, st in self.store.iter_items(lane.source,
                                                 max_rows=max(FILTER_WINDOW, limit)):
            if only_posts and real(st).get("in_reply_to_id"):
                continue
            if lane.keep(st, ctx):
                kept.append((item_id, st))
                if len(kept) >= limit:
                    break
        kept.reverse()
        if lane.by_status_time:
            kept.sort(key=lambda e: (real(e[1]).get("created_at", ""), real(e[1])["id"]))
        self._lane_cache[name] = (key, kept)
        return kept

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
        def job():
            focus = self.api.status(sid)
            focus = real(focus)
            ctx = self.api.context(focus["id"])
            self.store.put_statuses([focus] + ctx.get("ancestors", []) +
                                    ctx.get("descendants", []))
            return threads.build(focus, ctx)
        return self.submit(job)

    def account_statuses(self, acc_id, max_id=None):
        def job():
            page = self.api.account_statuses(acc_id, limit=self.cfg["feed"]["page_size"],
                                             max_id=max_id)
            self.store.put_statuses(page)
            return page
        return self.submit(job)

    def account(self, acc_id):
        return self.submit(self.api.get, f"/api/v1/accounts/{acc_id}")

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
    def reply_visibility(self, parent):
        default = self.cfg["post"]["default_visibility"]
        if parent is None:
            return default
        pv = real(parent).get("visibility", "public")
        if self.cfg["post"]["reply_never_wider"]:
            return narrower(pv, default)
        return default

    def post(self, text, visibility, reply_to=None, spoiler="", media=(), draft_key=None):
        """media: [(path, description)]. The draft is dropped once the post is out,
        even if the window that sent it is gone by then."""
        def job():
            ids = [self.api.upload_media(p, d)["id"] for p, d in media]
            st = self.api.post_status(text, visibility, reply_to, spoiler, ids, self.markdown)
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

    def _update(self, st):
        self.store.put_statuses([st])
        self.emit("status_updated", st)
        return st

    def favourite(self, status):
        s = real(status)
        return self.submit(lambda: self._update(self.api.favourite(s["id"],
                                                                   not s.get("favourited"))))

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
    def draft_key(reply_to_id=None):
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
    def shutdown(self):
        self._stop.set()
        self._wake.set()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.bg.shutdown(wait=False, cancel_futures=True)
        if self._poller:
            self._poller.join(timeout=5)
        with self._poll_lock:
            self.store.close()
