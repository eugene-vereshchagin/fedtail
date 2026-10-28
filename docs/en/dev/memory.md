# Making fedtail lighter

Status: **step 0 (the bench) done**, the baseline below; 28 Oct 2026. The plan is the author's.

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
| 1 | **One store of posts**: one identity map in the core — one object per post for the whole program; lanes keep ids and order, no copies of posts; the same for accounts, attachments, threads | — |
| 2 | **Compact objects instead of raw JSON**: the server's JSON only in SQLite; in memory light structures with the fields shown (`__slots__`, or msgspec Structs if Debian has the package); parsed in `protocols/` straight into them; repeated strings (accounts' URLs, servers, language codes) interned | — |
| 3 | **The database computes the lanes**: the lanes' rules compiled into SQL (WHERE + ORDER + LIMIT) with the indexes they need instead of loading posts into Python to filter them; the atoms SQL can't say computed when a post is stored and kept as columns (language, the event's kind, mine or not, seen already…); EXPLAIN QUERY PLAN checked for every set of lanes; the database's budget of about 1 GB of text a year kept | — |
| 4 | **Only what is seen in memory**: the core's "window of a lane" — an interface asks for a range around a cursor (say 50 posts), the core gives it and keeps a small buffer around it; lanes not open aren't loaded; unread counts are COUNTs in the database; "where reading stopped" — a cursor in the database, not a loaded lane; one API for every interface and Android | — |
| 5 | **Interfaces without a widget per post**: Qt — QListView / QAbstractListModel and a delegate that paints; GTK — Gtk.ListView with a model and reused rows; the web page, the terminal, Android — the same window, added lazily while scrolling; row heights cached, text not laid out again without need | — |
| 6 | **Pictures and media**: decoded right at the size shown (Qt: QImageReader.setScaledSize), the full size only when opened; one picture cache with a limit in MB (an option, a sensible default), LRU; thumbnails cached on disk; media off screen not decoded; video — still a preview only | partly: `media.image_cache_mb`, `image_disk_mb`, `image_decode` |
| 7 | **A lazy start**: heavy modules (language detection, spelling, sound, anything rare) imported at first use; the opossum's curtain drawn first, then the open lane, the rest in the background; every heavy operation (parsing, requests, language detection, the lanes' rules) off the GUI thread | partly: the curtain first (0.22) |
| 8 | **Budgets as tests**: the bench of step 0 a test with ceilings of memory and time (the start, opening a lane, scrolling); over the ceiling — the test fails, so the lightness doesn't creep back with new features; run in the full CI, not on every small change | — |
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
picture cache. Times: the cold start (core, connect, the first round), the first lane, opening
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
so it is in our structures, not in images.

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

## Decisions

| question | decision |
|---|---|
| another language? | no: the architecture first; Rust through PyO3 only for hot spots, step 9 |
| what is measured | USS — what fedtail itself holds; PSS and RSS beside it |
