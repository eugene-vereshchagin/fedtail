# Making fedtail lighter

Status: **the goal reached on the bench** (30 Oct 2026): the Qt window on the synthetic day
(10 000 posts, 24 h) USS 227 MB, 220 after the trim — 453 at the baseline below (28 Oct).
The rest of the plan stays as written; a real, long-running window is the next measure.
The plan is the author's.

## Why

Measured on the author's laptop (Qt on KDE, `python3 -m fedtail`, open for long): USS 484 MB,
PSS 516 MB, RSS 656 MB. It isn't a leak — the nightly self-check grows by less than 10 MB a
night — it is the ordinary volume of fedtail's own data, so the cure is in the architecture.
No rewrite in another language: a bare interpreter with PySide6 is 100–150 MB, the rest is
ours.

The goal: **150–250 MB USS** in the same use, and a noticeably brisker lane.

## Principles

* One systemic approach for all the code and every interface (Qt, GTK, the terminal, the
  web page, Android) — no fix for one platform only.
* The core decides what is in memory; an interface gets only what is on screen.
* Measure first, then change; every change is confirmed by numbers of the bench.
* In batches: no CI after every change; for the author's own check — a push with
  `[skip ci]` and a plain "pull now".
* No release without the author's word.
* The developer docs in both languages at once; the feature list and the options' reference
  too.

## The steps

| step | what | status |
|---|---|---|
| 0 | **The bench**: a synthetic day — 10 000 posts, 20 lanes of rules, pictures, a day of polling; memory by parts (posts, lanes, the picture cache, the interface's widgets, modules; Qt's C++ side through its caches' sizes and object counts, tracemalloc doesn't see it); timings — the cold start to the first lane, opening a lane, scrolling 1000 posts, applying the lanes' rules; in a dev build these numbers in the log every few minutes; the first run's numbers here as the baseline | done: the baseline below |
| 1 | **One store of posts**: one identity map in the core — one object per post for the whole program; lanes keep ids and order, no copies of posts; the same for accounts, attachments, threads | done: `Store._parse` — one read-only `Stored` per post while anyone holds it (weak), shared by every lane; `View.entry` — one `Post` per stored post (accounts and attachments live inside them) |
| 2 | **Compact objects instead of raw JSON**: the server's JSON only in SQLite; in memory light structures with the fields shown (`__slots__`, or msgspec Structs if Debian has the package); parsed in `protocols/` straight into them; repeated strings (accounts' URLs, servers, language codes) interned | measured, deferred: at most ~25 MB of the core's 61 (29.10) |
| 3 | **The database computes the lanes**: the lanes' rules compiled into SQL (WHERE + ORDER + LIMIT) with the indexes they need instead of loading posts into Python to filter them; the atoms SQL can't say computed when a post is stored and kept as columns (language, the event's kind, mine or not, seen already…); EXPLAIN QUERY PLAN checked for every set of lanes; the database's budget of about 1 GB of text a year kept | measured, deferred: at most ~25 MB of the core's 61 (29.10) |
| 4 | **Only what is seen in memory**: the core's "window of a lane" — an interface asks for a range around a cursor (say 50 posts), the core gives it and keeps a small buffer around it; lanes not open aren't loaded; unread counts are COUNTs in the database; "where reading stopped" — a cursor in the database, not a loaded lane; one API for every interface and Android | measured, deferred: at most ~25 MB of the core's 61 (29.10) |
| 5 | **Interfaces without a widget per post**: Qt — QListView / QAbstractListModel and a delegate that paints; GTK — Gtk.ListView with a model and reused rows; the web page, the terminal, Android — the same window, added lazily while scrolling; row heights cached, text not laid out again without need | Qt done: `qt/feedview.py` builds only the cards within a screen of the screen (the rest are places of their height); only the lanes opened last keep theirs (`ui.keep_hidden_lanes`). GTK — its own window of cards, as before |
| 6 | **Pictures and media**: decoded right at the size shown (Qt: QImageReader.setScaledSize), the full size only when opened; one picture cache with a limit in MB (an option, a sensible default), LRU; thumbnails cached on disk; media off screen not decoded; video — still a preview only | partly: `media.image_cache_mb` (64 MB by default since 0.22, measured), `image_disk_mb`, `image_decode` |
| 7 | **A lazy start**: heavy modules (language detection, spelling, sound, anything rare) imported at first use; the opossum's curtain drawn first, then the open lane, the rest in the background; every heavy operation (parsing, requests, language detection, the lanes' rules) off the GUI thread | partly: the curtain first (0.22) |
| 8 | **Budgets as tests**: the bench of step 0 a test with ceilings of memory and time (the start, opening a lane, scrolling); over the ceiling — the test fails, so the lightness doesn't creep back with new features; run in the full CI, not on every small change | done: `tests/test_budgets.py` (`FEDTAIL_BUDGETS=1`), CI's `budgets` job — a release waits for it; the ceilings a quarter over the numbers of 28.10 |
| 9 | **Only if 1–8 aren't enough**: the hot computing parts found by the profile and moved to Rust through PyO3, without touching the core's and the interfaces' architecture | — |

The order: 0 → 1 → … → 8, the bench after every step and its numbers compared with the
baseline below; after all of it — a check that the interfaces on every platform didn't drift
apart (`tools/parity.py`, `tools/behaviour.py`).

## The bench

`tools/membench.py` — no network, nothing of yours touched:

```sh
python3 tools/membench.py                  # the core and the common layer
python3 tools/membench.py --ui qt          # and the Qt window (offscreen)
python3 tools/membench.py --trace          # where Python's memory is, by package (slower)
python3 tools/membench.py --json out.json --md out.md
```

The scenario: a fake server (`tests/fakes.py`) with `--posts` posts in Home (a picture in every
fourth, replies, mentions, Local fed too, likes and follows for Activity), the store filled as
after days of polling, fedtail's own set of lanes plus lanes of one's own up to `--lanes`, a new
start over that store, then `--hours` of polling, a dozen new posts every five minutes.

What it says: USS / PSS / RSS (`/proc/self/smaps_rollup`), with `--trace` Python's part by
package; the core's counters (`Core.diag_stats`); with `--ui qt` the number of widgets and the
picture cache (`--ui qt` puts a real JPEG of every picture and avatar of the fake server
into the disk cache first, as after days of reading — the window decodes and keeps them as it
would; `--image-mb N` sets `media.image_cache_mb`). Times: the cold start (core, connect, the first round), the first lane, opening
every lane and the slowest of them, the rules applied anew, the day of polling, and with
`--ui qt` scrolling Home through 1000 posts.

A dev build writes USS and PSS into its log with every stats line (`diag.smaps`, every
`debug.stats_minutes`).

## The baseline

The first full run, 28 Oct 2026 (`python3 tools/membench.py --ui qt`: 10 000 posts, 20 lanes
of which 19 shown, 24 h; Python 3.13, the cloud's 2 cores, Qt offscreen; no picture got
downloaded — the fake server's addresses lead nowhere — so the picture cache is empty here):

| memory | MB |
|---|---|
| USS | 453.3 |
| PSS | 483.8 |
| RSS | 516.3 |

The author's laptop said USS 484 MB: the bench reproduces the problem without pictures,
so it is in our structures, not only in images (pictures came to the bench later — see below:
they are a good part of it too).

| time | ms |
|---|---|
| cold start: core, connect, first round | 1935 |
| first lane (Home) built | 49 |
| Qt window up, Home drawn | 2113 |
| open every lane (19) | 12 689 |
| the slowest lane | 1819 |
| the lanes' rules applied anew | 1319 |
| 24 h of polling (288 rounds) | 195 679 |
| Home scrolled through 1000 posts | 396 |

Counters at the end: 13 457 statuses and 15 656 items in the store (32.6 MB on disk),
294 031 Python objects (gc), 518 modules, **14 497 Qt widgets** — step 5's target; every
lane keeps its own parsed copy of each post it shows (`Core.lane_entries` → `json.loads`
per lane) — step 1's.

What the numbers say, three runs later (28 Oct):

* **Python's own objects are a small part.** With `--trace` (2 h of polling) tracemalloc
  sees about 95 MB of Python allocations of a USS of 517 MB: the core 18, the Qt layer's
  Python 20, the common layer 4.5, json and the rest the remainder. The bulk is Qt's C++
  side — widgets, their text layouts and styles.
* **Freed memory stays in the process until it is trimmed.** `--ui qt --hours 2`: USS 349 MB
  with every lane visited; the hidden lanes unloaded (as `ui.unload_hidden_minutes` does
  after 10 minutes) — 854 widgets left of 9382, and still 349 MB; after glibc's
  `malloc_trim(0)` — **193.5 MB**. A running fedtail trims every `debug.stats_minutes`
  (`diag.trim_memory`), so that last number is the one to compare with life; the bench
  prints all three.
* **Step 1 on the core alone** (`--hours 2`, no window): USS 110.3 → 102.5 MB, opening
  every lane 656 → 362 ms, two hours of polling 9.2 → 5.4 s (no lane parses a post another
  lane has parsed already).

So the order of the plan holds for the core, but the window's weight is in the cards
(step 5): every card a score of widgets.

* **Step 1 on the model's side** (one `Post` per stored post for every lane, `View.entry`):
  `--ui qt --hours 2` USS 401.0 → 399.5 MB, after the trim 245.3 → 245.0 MB, Python
  objects 228 169 → 222 232. Next to nothing: the Post objects were never the weight.
* **Pictures** (28 Oct: a real window's stats line — USS 465–547 MB, `qt.images_mb` 127.9 of
  174 pictures, 3342 widgets; the bench saw none of it, its addresses led nowhere). With the
  pictures on its disk (`--ui qt --posts 4000 --hours 4`), after the trim:

  | `media.image_cache_mb` | before the trim | after it |
  |---|---|---|
  | 128 (the old default) | 600.1 | 378.4 |
  | 64 | 570.7 | 318.8 |
  | 32 | 553.8 | 318.8 |

  Below 64 nothing more goes: the pictures on screen are held by their cards whatever the
  cache. The default is 64 MB now (step 6) — 60 MB of the 380 a window kept open holds.
* **Faces decoded at their box** (`images.face`: twice the box, at least 64 px — they
  were decoded as feed pictures, up to 1200 px, a 400-px avatar whole for a 40-px circle):
  after the trim −3…−13 MB (two runs each, A/B). Tried and dropped: keeping in the cache a
  card's picture as its box shows it instead of the decoded one (each on screen was there
  twice) — +12…+23 MB, measured, so not done. The bench left a different lane in front
  from run to run (1062 widgets or 1936, 20 MB apart): it puts Home in front now.
* **Lanes kept drawn** (`ui.keep_hidden_lanes`, 3, `common/lanekeep.py`, Qt and GTK; GTK now
  heeds `unload_hidden_minutes` too): every lane opened kept its cards for 10 minutes — a
  lane drawn is some 18 MB (the window with Home alone: 175 MB; every lane opened: 500 MB
  after the trim). Now only the 3 opened last stay; one opened before goes the moment
  another comes to the front. Every lane opened, 4000 posts: 573 → 405 MB before the trim,
  319 → 298 after; going through them all again adds nothing (2255 widgets either way). The
  bench deletes the widgets let go after each lane, as a running window does (before, it
  counted 10 147 widgets that were only waiting to be deleted).
* **Step 5 in Qt: only the cards near the screen** (`qt/feedview.py`, 29.10). Every card had
  been a set of widgets, and a lane built 40 of them at once and kept up to 120. Now the
  body has a place for every post (its height measured once built, else the mean) and
  widgets only within a screen above and below. Not a delegate painting cards: the cards
  on screen are the same widgets as before (links, selection, menus, a screen reader all
  as they were) — what counted was how many of them exist. 4000 posts, every lane opened:

  | | before | after |
  |---|---|---|
  | USS, MB | 405 | 263 |
  | after the trim, MB | 298 | 244 |
  | widgets | 2255 | 1252 |
  | the pictures kept, MB | 64 | 33 |
  | the window up, Home drawn, ms | 1860 | 767 |
  | every lane opened (19), ms | 11 306 | 2651 |
  | the slowest lane, ms | 1355 | 313 |

  `reading.build_at_once` is gone (said so, if a config still has it). The budgets
  (`tests/test_budgets.py`) moved down with it.
* **Cards built a few at a time; memory back soon** (29.10, the author's report). The
  window's log had six freezes of 300–430 ms, five of them a lane opened or a far jump
  building the cards of a screen above and below all at once (`card.__init__`,
  `_measure`), one a lane redrawn looking its posts up one by one. Now the cards on screen
  are built at once and the others `SLICE_MS` (8 ms) at a time between the window's
  work, nearest first (`FeedView._build_more`); a list of posts handed to the core is one
  query (`View._in`). The bench, 4000 posts, opening the lanes: `_lay_out` at most 210 →
  110 ms, stalls over 100 ms 13 → 1. A card is ~6 ms of `QLayout.activate` alone here
  (its real height) — the slice holds one card at least. And `smem` right after reading
  through lanes said 145 → 387 MB with the freed memory not yet given back (the stats
  tick 5 minutes later gave 81 MB back): `diag.trim_soon` trims 5 s after cards are let go
  (scrolled past, a lane unloaded), one thread, no gc pass.
* **Steps 2–4 measured again, at 10 000 posts** (29.10): the core alone, a day of
  polling: USS 55 MB at 2000 posts, 82 MB at 10 000 — but the bench's fake server lives
  in the same process (its 13 000 statuses as dicts), and `--trace` had counted it as
  "fedtail, the rest" (its file is `fedtail/tests/fakes.py`: fixed, the bench's groups
  now look at `tests/` first). The core's own Python objects at 10 000 posts are about
  8 MB. Steps 2–4 stay deferred: a window of a lane in the core would win single
  megabytes; the phone's weight is its interpreter and `requests`, not the posts.
* **A card measured once, not three times** (Qt, 29.10): right after a card was shown
  Qt asked it to lay itself out again, and the watcher measured it anew — 9185 measures
  for 2962 cards. The request is served when the card is built, before the watcher is
  on; the second look then finds the height cached (the median measure 2.1 → 0.9 ms,
  the measures from the event loop 7028 → 3878).
* **langdetect** (`core/langs.py`, `core/atoms.py`, 30.10). The core alone at 2000 posts
  was 110 MB on this machine, 57 of them langdetect's 55 profiles — a list of 55 Python
  floats for each of 87 000 n-grams. Loaded with no languages filter and no rule asking:
  each Activity row worked out every atom of its post, its language guessed too
  (`event_facts` takes the rule's needs now) — 110 → 52 MB. When a guess is needed, only
  the Latin and Cyrillic profiles are read (the other scripts are told by their letters;
  `lanes.detect_among = "all"` — every one), as 4-byte floats: 60 → 11 MB, the same
  answers. The core's budget 75 → 65 MB.
* **A new lane's fill** (`store.link_items`, `core/custom.py`, 29.10). Where the core alone
  was heavy: a free lane (and Unsorted) takes its feeds' posts, stored already, and wrote
  them back through `put_items` — each one serialised anew, its stored text read in to
  compare, and up to 3000 parsed posts a feed held by the fill — a peak of 25 MB in
  Python, kept by the process after it. Now only the items are linked, by ids. 4000 posts,
  the core alone: 89.5 → 72.5 MB, a round after a new lane 83 → 63 MB; every lane's rule
  applied anew ~1000 → 700 ms; the Qt window 274 → 267 MB. Measured the wrong way first:
  under `tracemalloc` the core looked 120 MB with 55 MB "outside Python" — the tracing's own
  bookkeeping; the untraced numbers are the ones to read.
* **The bench and deferred deletes**: `processEvents()` never deletes what was let go with
  `deleteLater()`, so the cards let go while polling and scrolling stayed counted (305
  cards held, 48 shown: 6299 widgets, 393 MB at 4000 posts); `membench.pump()` now does
  what a running loop does, everywhere the bench lets the window run (1077 widgets).
  `qt_bench.py` had the same hole till 30.10: after its scrolls 57 000 widgets waited to
  be deleted, and the first theme tried paid for all of them — 30–170 s, which looked like
  a slow theme (nord) and bisected to the near-the-screen cards (f2a579a3). Its turns
  flush the deletions now: a theme 1.1 s, the worst scroll frame 80 → 34 ms.
* **Steps 2–4, measured before doing**: the core alone at 2000 posts is 61 MB, of which
  33 MB are the imports — steps 2–4 can win at most some 25 MB of it; the window is the
  bulk (220 MB: widgets, fonts, pictures). Left until a profile of a real, long-running
  window says the core's share has grown.
* **Step 7, the imports measured**: the core's imports are 33 MB — 15 the interpreter itself,
  13 `requests` (OpenSSL, urllib3), needed the moment the core connects; nothing heavy
  besides is imported at start. Lazy imports have no memory to win in the core; what step 7
  has left is the window's start.

## Decisions

| question | decision |
|---|---|
| another language? | no: the architecture first; Rust through PyO3 only for hot spots, step 9 |
| what is measured | USS — what fedtail itself holds; PSS and RSS beside it |
