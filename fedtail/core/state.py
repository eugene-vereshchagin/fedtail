"""The Core's working state, declared in one place: what each part of it (core/app.py and
its mixins — poll.py, counts.py, thread_ops.py…) keeps between calls, what it starts as,
and which lock guards it. The parts used to make these up where they first needed them
(``self.__dict__.setdefault(...)``, ``getattr(self, "_x", None)``), so nothing said what
state there is (the audit of 23.11).

``CoreState`` is a base of ``Core``. What starts as a plain value is a class attribute
here — a bare ``Core.__new__(Core)`` (a test's) has it too; what every core needs a fresh
one of — a dict, a set, a lock — is made by ``_init_state()``, the first thing
``Core.__init__`` does (a bare core calls it itself)."""

import threading
from collections import OrderedDict
from typing import Any


class CoreState:
    # ---- the rounds (poll.py) --------------------------------------------------------
    _poll_count = 0  # rounds made since the start
    _poll_failures = 0  # …and how many of them failed
    _poll_max_s: float = 0.0  # the longest round so far, seconds
    _fails_in_row = 0  # rounds failed in a row: the next waits longer (backoff)
    _last_poll_ok: float | None = None  # when the last round came through (unix time)
    _offline_since: float | None = None  # when the server went out of reach; None — it answers
    _paused = False  # out of sight (a phone in the background): no rounds
    _polling = False  # a round is going on
    _starting = False  # from the making until the first round is over
    _urgent = False  # a round asked for by hand goes before the quiet time
    _quiet_said: float | None = None  # the rate limit's window said once (its reset time)
    _quiet_until: float = 0  # no round before this time: the server asked to wait
    _round_costs: list[int] | None = None  # requests the last six rounds took ([] once one ran)
    _round_new = 0  # what the last round brought
    # the thread a round runs in: only its steps are timed
    _round_thread: threading.Thread | None = None
    _steps: dict[str, float] | None = None  # {step: seconds} of the round going on
    _step_at: float | None = None  # when the last step ended (monotonic)
    _stream: Any = None  # the live stream, when one is on
    _poller: threading.Thread | None = None  # the thread of the rounds

    _last_poll_s: float | None = None  # how long the last round took
    _unrouted: dict[Any, list[Any]] | None = None  # a cut round's new posts, for the next
    _lists_checked: float | None = None  # when the lists were last asked (monotonic)
    _announced_at: float | None = None  # …and the announcements
    _silence_checked: float | None = None  # …and whom I muted and blocked
    _known_requests: set[Any] | None = None  # follow requests seen; None — not fetched
    _following: set[Any] | None = None  # account ids I follow; None — not asked yet

    # ---- the lanes (app.py) ----------------------------------------------------------
    _followed_tag_names: set[str] | None = None  # the tags I follow; None — not asked yet
    _caps_unsure = False  # the server's limits didn't come: asked again with the rounds
    # {error's words: when shown}: the same one isn't said again
    _errors_seen: dict[str, float] | None = None
    _thread_news: tuple | None = None  # threads with news, for Home's "threads with news"
    _waiting_accounts: dict | None = None  # accounts whose posts a lane waits for
    _warmed_at: tuple | None = None  # when the lanes were last made ready (monotonic)
    _warmed_for: Any = None  # …and for which state of the store
    _warming: int | bool = 0  # the lanes are being made ready right now
    _last_mark: float | None = None  # when the last read mark came (the reading's moments)
    _reading_run: list | None = None  # the run of reading going on
    _counts_at: float = -1e9  # when the counts on screen were last asked (monotonic)
    _no_batches: bool | None = None  # the server gives no counts in batches: one by one
    _no_markers = False  # the server has no markers: not asked again
    _others_cache: tuple | None = None  # (when, the other servers' copies) of honest counters
    _aliases_cache: Any = None  # people's aliases as last read from the store
    _colors_cache: Any = None  # …and their nick colours
    _tags_seen_muted: Any = None  # the muted tags as the server last said them
    _my_roots_cache: tuple | None = None  # (key, roots) of the threads I wrote in
    _completion_warm = False  # the editor's suggestions were warmed once
    _emoji: list | None = None  # the server's own emoji; None — not asked yet

    def _init_state(self):
        """A fresh one of everything a core keeps in a container, and its locks."""
        # ---- the lanes -----------------------------------------------------------------
        self._unread_cache = {}        # lane → (store versions, the unread ids)
        self._filter_out_ids = {}      # lane → ids the server's filters keep out
        self._lang_out_counts = {}     # lane → how many the languages filter hides
        self._older_busy = set()       # lanes whose "Older" is being fetched
        self._older_none = set()       # lanes the server has nothing older for
        self._browse_waiting_set = set()  # browse lanes opened, not answered yet
        self._dismissed_ann = set()    # announcements closed in this run
        self._stats_links = []         # the day's links, for the statistics
        self._relations = {}           # account id → (when, my relationship to them)
        self._late_checked = {}        # source → when it was last looked through (poll.py)
        self._events_cache = {}        # the activity's events as last read (activity.py)
        # ---- threads (thread_ops.py) ---------------------------------------------------
        self._thread_root_of = {}      # post id → the root of the thread being fetched
        self._thread_steps = {}        # root → how its fetching goes (thread_progress)
        # ---- what is on screen (counts.py): guarded by _counts_lock ---------------------
        self._counts_lock = threading.Lock()
        self._on_screen = {}           # post id → when it was last seen there (monotonic)
        # ---- the threads' sizes (threadsize.py): all guarded by _ts_lock ----------------
        self._ts_lock = threading.Lock()
        self._ts_root = {}             # post id → its thread's root id
        self._ts_size = {}             # root id → (comments, monotonic time)
        self._ts_busy = set()          # roots (or posts) being asked now
        self._ts_spent = []            # monotonic times of the requests made
        self._ts_failed = {}           # root or post id → when it wasn't given
        self._ts_wanted = set()        # posts on screen, waiting to be looked at
        self._ts_looking = False       # a look through _ts_wanted is under way
        # ---- translations (translate.py) -----------------------------------------------
        self._translated = OrderedDict()  # post id → its translation ({} — it failed)
        self._translating = set()      # posts being translated now
