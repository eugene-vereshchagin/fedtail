"""The rounds: the poll loop and one round of it (every source caught up, the lanes'
rules, notifications), its pace — slow mode, "notify at most every N minutes", the
server's request budget, backing off — and the live stream that wakes it."""

import logging
import threading
import time
from urllib.parse import urlsplit

import requests

from ..i18n import _
from ..version import USER_AGENT
from . import (
    lanes,
    neterr,
    sources,
    subs,
)
from .model import real
from .proto import Error as ApiError  # the protocol's error answer (core/proto.py)
from .proto import RateLimited

log = logging.getLogger("fedtail.core.app")  # the Core's log: one name for all its parts


PARENTS_FIRST = 20  # parents fetched before the rules sort a round's replies


class Offline(Exception):
    """The account's own server out of reach at all — no network, its name not resolved,
    the connection refused: the round stops at the first such answer instead of asking
    every source in turn (each failing alike, each said to the user), and counts as a
    failed one, so the next waits longer (backoff)."""


def _due(last, every):
    """Time to do it again? (last: monotonic seconds, None = never done). Not
    "last = 0": monotonic time starts near zero at boot, so that would wait."""
    return last is None or time.monotonic() - last > every


class PollMixin:
    """A part of Core (core/app.py): see the module's words."""

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

    hand_refreshes = 0  # "Refresh" pressed: the lanes holding new posts let them in

    def refresh_by_hand(self):
        """The interface's Refresh (⟳, F5): a round at once, and feed.on_new = "hold"
        lets the new posts it held into the lanes. → a future of how it went (and the
        event "refreshed", the same): {"new": n} | {"error": words} | {"wait_until": t}
        — a press that brought nothing looked like a button that does nothing (30.10);
        common/results.refresh_text says it."""
        from concurrent.futures import Future
        self.hand_refreshes += 1
        fut = Future()
        until = getattr(self, "_quiet_until", 0) or 0
        if until > time.time():  # the server's budget waited out: the round comes then
            self._refreshed([fut], {"wait_until": until})
        else:
            with self._hand_lock:
                self._hand_waiting.append(fut)
        self.poll_now()
        return fut

    def _refreshed(self, futs, result):
        for f in futs:
            if not f.done():
                f.set_result(result)
        if futs:
            self.emit("refreshed", result)

    def _poll_soon(self):
        """The live stream says something came: a poll, but not more often than
        poll.stream_gap_seconds — a busy server sends events many times a minute, and
        every poll asks each lane (a dozen requests and some CPU each time). In slow
        mode the stream wakes nothing: the news waits for its round."""
        if self.slow_minutes():
            return
        self._wake.set()

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

    def stream_allowed(self, on):
        """The phone's phone.stream ("wifi": on Wi-Fi only): the live stream stopped
        on a metered network, started again on Wi-Fi. Polling goes on either way."""
        running = getattr(self, "_stream", None)
        if not on and running is not None:
            running.stop()
            self._stream = None
            log.info("stream: off (phone.stream)")
        elif on and running is None and self.auth:
            self._start_stream()

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
                self._loop_round()
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
            self._quiet_until = time.time() + quiet if quiet > 0 else 0
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

    def _loop_round(self):
        """A round of the loop: the server out of reach is said once an outage; the
        Refresh presses made before it began are told how it went."""
        with self._hand_lock:
            asked, self._hand_waiting = self._hand_waiting, []
        self._round_new = 0
        try:
            self.poll_once()  # counts the rounds failing in a row itself
        except Offline as e:
            self._went_offline(e.__cause__ or e)
            self._refreshed(asked, {"error": neterr.words(e.__cause__ or e,
                                                          getattr(self.api, "host", "?"))})
            return
        except RateLimited:
            budget = getattr(self.api, "budget", None)
            self._refreshed(asked, {"wait_until": getattr(budget, "reset", 0) or time.time()})
            raise
        except Exception as e:
            self._refreshed(asked, {"error": str(e)[:200]})
            raise
        self._back_online()
        self._refreshed(asked, {"new": int(getattr(self, "_round_new", 0) or 0)})

    def _cut_off(self, e):
        """Is e the own server out of reach (not one source's other server: an RSS
        site, another server's lane)?"""
        if not isinstance(e, requests.ConnectionError):
            return False
        url = getattr(getattr(e, "request", None), "url", None) or ""
        host = (urlsplit(url).hostname or "").lower()
        return not host or host == getattr(self.api, "host", host)

    def _round_error(self, where, e):
        """A source's failure in a round: the server out of reach stops the round
        (Offline); anything else is said and the round goes on."""
        if self._cut_off(e):
            raise Offline(str(e)) from e
        self.emit("error", f"{where}: {e}")

    def _went_offline(self, e):
        """Said once an outage: the first round that couldn't reach the server; the
        status line says "no answer since…" meanwhile (common/sidebar.poll_words)."""
        self._poll_failures += 1
        self._last_poll_error = f"{time.strftime('%H:%M')} {e.__class__.__name__}"
        if getattr(self, "_offline_since", None):
            log.info("poll: still out of reach (%s), next in %.0f s",
                     neterr.kind(e) or "down", self.backoff())
            return
        self._offline_since = time.time()
        host = getattr(self.api, "host", "") or "?"
        log.warning("poll: %s out of reach (%s) — the rounds wait, longer each time",
                    host, neterr.kind(e) or "down")
        self.emit("error", _("poll_offline", why=neterr.words(e, host)))

    def _back_online(self):
        since = getattr(self, "_offline_since", None)
        if since:
            self._offline_since = None
            log.info("poll: the server answers again (out of reach %.0f s)", time.time() - since)

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
            self._starting = False  # the first round is over, however it went
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
        busy = getattr(self, "_polling", False) or getattr(self, "_starting", False)
        return {"busy": bool(busy), "ok_at": ok,
                "failing": int(getattr(self, "_fails_in_row", 0) or 0)}

    def _step(self, name):
        """Poll timing: the time since the last step goes to name (summed)."""
        now = time.monotonic()
        steps = getattr(self, "_steps", None)
        if steps is not None:
            steps[name] = steps.get(name, 0.0) + now - getattr(self, "_step_at", now)
        self._step_at = now

    def _fill_browse(self, name):
        """lanes.browse_fill_pages: an open browse lane (Federated, Local) the languages
        filter left short of a page — a relay pours in, nearly all of it in other
        languages, and the lane showed one post of two hundred (30.10) — asks pages
        older till it has one, at most so many pages while it stays open; what they
        brought is kept beyond browse_keep. → the posts kept so, for the prune."""
        pages = int(self.cfg["lanes"].get("browse_fill_pages", 5))
        extra, asked = self._browse_extra.get(name, (0, 0))
        page = self.cfg["feed"]["page_size"]
        here = [x.name for x in self.lanes if x.source == name]
        while asked < pages:
            # the languages filter or the funnel ("only video") left it short
            short = [n for n in here if len(self.lane_entries(n)) < page
                     and (self.language_hidden(n) or self._funnel(n))]
            if not short:
                break
            got = sources.fetch_older(self.store, self.sources[name], page)
            asked += 1
            extra += len(got)
            if not got:  # the server has nothing older: no more asking
                asked = pages
        self._browse_extra[name] = (extra, asked)
        return extra

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
                    if self._cut_off(e):
                        raise Offline(str(e)) from e
                    self._silence_checked = time.monotonic()
                    log.warning("silence: %s", e)
            ann = int(self.cfg["poll"].get("announcements_minutes", 30)) * 60
            if ann and self.cfg["ui"]["announcements"] != "off" and \
                    _due(self._announced_at, ann):
                self._announced_at = time.monotonic()
                try:
                    self._check_announcements()
                except Exception as e:  # noqa: BLE001 — a banner is never worth a round
                    log.debug("announcements: %s", e)
            if self.cfg["lists"]["enabled"] and _due(self._lists_checked, every):
                try:
                    self._refresh_lists()
                except Exception as e:  # try again next round, not every poll
                    self._lists_checked = time.monotonic()
                    self._round_error("lists", e)
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
            if self.private_lanes():
                self.sync_conversations()  # read here = read on the server (social.py)
                self._step("conversations")
            # followed threads: for their lane, and for Home's "threads with news"
            if self._follows_threads() or self._needs_threads():
                try:
                    sc = self.cfg["subs"]
                    new_by_source["subs"] = subs.check(
                        self.store, self.api, self.me["id"], sc["interval_minutes"],
                        sc["active_days"], sc["max_threads"])
                except Exception as e:
                    self._round_error("subs", e)
                self._step("subs")
            if self._opened_threads:  # feed.thread_recheck_minutes: open threads grow
                self.recheck_threads()
            try:  # feed.counts_minutes: the posts on screen, their numbers asked again
                self.refresh_counts()
            except Exception as e:  # noqa: BLE001 — the next round
                log.debug("counts: %s", e)
            self._step("counts")
            lazy = {lane.source for lane in self.lanes if lane.lazy}
            # a lane read through needs its sources caught up, even Local's
            lazy -= {lane.source for lane in self.lanes if not lane.lazy} | \
                {f for lane in self.lanes if lane.feeds and not lane.lazy for f in lane.feeds}
            open_names = [n for n in {self._active_lane, *self._active_lanes}
                          if n in self.lane_by_name]
            open_sources = {self.lane_by_name[n].source for n in open_names} | \
                {f for n in open_names for f in self.lane_by_name[n].feeds}
            needed = list(dict.fromkeys(lanes.sources_needed(self.lanes) +
                                        self._waiting_sources()))
            for name in needed:
                if name not in self.sources and self.api is not None:
                    # a stream named by a lane's rule (account:, link:, quotes:, remote:)
                    src = sources.prefixed_source(self.api, name, remote=self.wider.remote_lane,
                                                  rss=self.wider.rss_feed)
                    if src is not None:
                        self.sources[name] = src
                if name not in self.sources:
                    continue
                if name in lazy:  # browse lanes: only while open, newest page only
                    if name not in open_sources:
                        self._browse_extra.pop(name, None)  # closed: back to browse_keep
                        continue
                    try:
                        keep = int(self.cfg["lanes"].get("browse_keep", 200))
                        new_by_source[name] = sources.refresh_top(
                            self.store, self.sources[name], fc["page_size"], keep)
                        # the newest `keep`, and what "Older" brought into an open lane
                        shown = max((self._limits.get(x.name, 0) for x in self.lanes
                                     if x.source == name), default=0)
                        extra = self._fill_browse(name)
                        self.store.prune(name, max(keep, shown - fc["render_limit"] + keep)
                                         + extra)
                        # the server answered, and with nothing: its live feeds are off
                        # (mastodon.social and others do that) — the lane says so
                        empty = getattr(self.sources[name], "last_count", 1) == 0
                        if empty != (name in self.browse_empty):
                            (self.browse_empty.add if empty else self.browse_empty.discard)(name)
                            browse_changed.add(name)  # its lane says so (see below)
                    except Exception as e:
                        self._round_error(name, e)
                    if name in self._browse_waiting:  # answered (or failed): drawn anew
                        self._browse_waiting.discard(name)
                        browse_changed.add(name)
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
                    self._round_error(name, e)
                except Exception as e:  # network down etc.
                    self._round_error(name, e)

            self._step("sources")
            # other servers' public lanes and tags (lanes.federated_extra, tags_extra)
            fed_open = "federated" in open_sources
            if self.wider.due(fed_open):
                self.bg.submit(self.wider.run, fed_open)
            if self._carry_my_direct():  # read already: no news, no sound
                self.emit("lanes_updated", {n: [] for n in self.private_lanes()})
            self._step("my direct")
            new_requests = []
            if self._wants_event("follow_request"):
                try:
                    self.follow_requests = self.api.follow_requests() or []
                    self.note_requests(self.follow_requests)
                    ids = {a["id"] for a in self.follow_requests}
                    if self._known_requests is not None:
                        new_requests = [a for a in self.follow_requests
                                        if a["id"] not in self._known_requests]
                    changed = ids != self._known_requests
                    self._known_requests = ids
                    if changed:  # not every poll: the tab would be rebuilt for nothing
                        self._warm_lanes()  # the window counts every lane on this too
                        self.emit("requests_updated", self.follow_requests)
                        self.emit("activity_updated", len(new_requests))
                        events_in = {c.name: [] for c in self._event_lanes()
                                     if c.wants_event("follow_request")}
                        if events_in:
                            self.emit("lanes_updated", events_in)
                except Exception as e:
                    self._round_error("requests", e)

            new_activity = []
            if self._event_lanes():
                try:
                    new_activity = self._poll_activity()
                    if new_activity:
                        self._warm_lanes()  # the window counts every lane on this event
                        self.emit("activity_updated", len(new_activity))
                        events_in = {c.name: [] for c in self._event_lanes()}
                        if events_in:  # lanes showing likes, follows…: they look again
                            self.emit("lanes_updated", events_in)
                except Exception as e:
                    self._round_error("activity", e)

            if self.derived.due():  # a snapshot of my followers, in the background
                self.bg.submit(self.derived.run)
            if self.derived.likes_due():  # who liked my recent posts (activity.unlikes)
                self.bg.submit(self.derived.run_likes)
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
            # (and "state" — "subscribed" is known up a reply's parents)
            if any(c.routed and {"parent", "me", "state"} & set(c.needs)
                   for c in self.customs):
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
                pairs = [(real(st)["id"], real(st).get("in_reply_to_id"))
                         for st in new_statuses]
                self.emit("arrived", pairs)
                self._answers_in_open_threads(pairs)
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
            self._round_new = len(new_statuses) + len(new_activity) + len(new_requests)
            got = {k: len(v) for k, v in new_by_source.items() if v}
            if got or new_activity or new_requests:
                log.info("new: %s%s%s", got or "-",
                         f" activity+{len(new_activity)}" if new_activity else "",
                         f" requests+{len(new_requests)}" if new_requests else "")
