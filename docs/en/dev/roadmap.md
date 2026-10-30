# fedtail: the plan for 0.22

What we do in 0.22 (decided on 28 Oct 2026, the day 0.21.0 came out): **anything into any
lane by its rules** — from activity and follow requests to posts, the sets of lanes only
presets; **the lane editor on the phone**; **sync's last pieces** (the key by a QR code, a
draft's pictures, the sync server guarded against a loop of drafts); **the sync server in
a repository of its own**, released with fedtail under one number; **"Report a bug"** in
every interface; **lighter and quicker** (`memory.md`); and after all of it, the interfaces
checked again against each other. The user's side is in the feature list (`docs/src/features/*.toml`
→ `docs/*/parts/roadmap.md` and the site); here — the whole plan, with the development part.

## What 0.21 brought

Sync between devices to the end (a fedtail-sync server, a folder, WebDAV; read marks,
threads, lanes, drafts, activity, tiles) and free lanes — every lane made of rules, the
built-in ones presets of them (`feeds.md`). Everything — in CHANGELOG.md.

## Doing

| # | what | how we'll know it's done |
|---|---|---|
| 1 | **Anything into any lane**: events (likes, follows, requests) and posts in one lane by its rules; every question about a lane asked of its rule, never its name (the first lane, sounds, private messages, the roster, sections, columns) | done: `tests/test_lanes_*`, the lanes' questions in `Core` (`lane_rank`, `private_lanes`, `thread_lanes`, `lanes_fed_by`) |
| 2 | **The lane editor on the phone** | done: the common places `lanes` / `lane` (`common/places.py`) on Android |
| 3 | **Sync's last pieces**: the key by a QR code; a draft's pictures beside the journal; the server's limits for them (`max_media_kb`, `media_quota_mb`, `media_per_minute`) | done: `docs/en/sync.md` "Not yet" empty |
| 4 | **fedtail-sync in its own repository** with fedtail's version | done: CI checks `fedtail_sync.__version__` |
| 5 | **"Report a bug"** in every interface (the log gathered, the issue opened filled in, Submit pressed by the user) | done |
| 6 | **Lighter and quicker** (`memory.md`) | steps 0, 1, 5 (Qt and GTK on one `common/strip.py`), 8 done; 6 and 7 in part; 2–4 measured and left (the core's own objects are ~8 MB at 10 000 posts) |
| 7 | **The review's fixes**: logic out of the windows (silence, filters, trends, "read it whole" — common places; asking again for a profile — `common/patient.py`), `core/app.py` in parts, the core through `core/proto.py` only, outside fetches pinned to the checked address | done |
| 8 | **The interfaces checked again** | done (29.10): `tools/behaviour.py` — the same in Qt, GTK, the terminal and the web page, every step; `tools/parity.py` — Qt and GTK apart in 5 words, each explained in `parity.toml`, as every difference of the terminal and the web page (`tests/test_parity.py`) |

## Before the release (the author)

- A night in the tray on the newest build, `smem` before and after reading through lanes.
- The secrets: `APT_GPG_KEY` and GitHub Pages for the `apt` branch, `WINDOWS_CERT_PFX`.
- The tray icon that stayed after quitting from the roster in KDE (split layout).
- Sync on three devices through a fedtail-sync server with an invite code (protocol 2).

## Waiting for a decision

- `feeds.md` §10: nested groups in `any`; `in_my_thread` without following.
- The author's calls of `robustness.md`: the token's store, encrypting the database,
  checking for a new version, NTLM proxies, the system's theme on the go, a hung first copy.

## Loose ends

- The GTK window has its budget test since 30.10 (`tests/test_budgets.py`, through
  `tools/gtk_bench.py`): no step's turn over 250 ms, the start and the lanes quick. CI's
  `budgets` job has no GTK (pip's Python): it runs where python3-gi is — the night's
  self-check.
- A card is ~7 ms to build in Qt (dozens of widgets): cheaper only by building it of
  fewer — a work of its own.

## Not in 0.22

Toga; the token from an external command; Mastodon's annual report and the other "won't
do" of the feature list; `memory.md` steps 2–4 (measured: single megabytes to win) and 9.
