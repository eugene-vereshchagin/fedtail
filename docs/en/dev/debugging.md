# Debugging and logs

A development version (from git, a number like `0.7.0.dev0`) writes a detailed log by itself —
that's the debugging mode, `debug.mode = "auto"`. The client is kept open for days, and if it
crashes, hangs, starts eating memory or CPU — the log shows what was going on.
In releases (and the one-file builds made from them) the mode is off: the profile's data folder,
`logs/`, keeps only warnings and errors, a few MB, and crash.log. To turn it on —
`debug.mode = "on"` in the config or, for one run, the `--debug` flag
(`python3 -m fedtail --debug`, `./fedtail-0.6.0-linux-x86_64 --debug`, `fedtail-….exe --debug`).

## Where it lives

In the profile's data folder, `logs/` — `~/.local/share/fedtail/<profile>/logs/` (the ≡ menu →
"Debugging" → "Open the logs folder"; another place — `debug.log_dir`). The logs of the previous version
are deleted by the new one at its first start (the folder holds a `version` file — whose they are):

```
~/.local/share/fedtail/default/logs/
    2026-10-16_15-04-12.log   the log: a new file at every start and every hour
                              (and at debug.log_mb), no more than debug.keep_mb in all —
                              the oldest are deleted by themselves
    latest.log       a link to the file being written now — send this one
    crash.log        the stacks of all threads if the process crashed (a segfault in Qt and such)
    stacks.log       stacks on demand and when the window hangs
```

Besides requests and polls, the log records actions too: which lane is open, which tabs,
clicks on a post's actions (like, reply, thread — by id, no texts), what was sent
(the length and where, not the text), how many rows were drawn and how long it took, long window events.

To open it quickly: the ≡ menu → "Debugging" → "Open the logs folder".

## What's in the log

* the header of every start: the version and commit, Python, Qt/PySide6, the desktop,
  the PID, the profile;
* every request to the server: method, path, paging parameters, response code, time,
  size. Slow ones (longer than `debug.slow_request_seconds`) and failed ones are marked
  WARNING. **No token, no post texts and no request bodies in the log**;
* every poll of the server: how long it took and what came;
* errors — with a full traceback, including errors in background threads;
* every `debug.stats_minutes` minutes — a `stats` line: memory (rss_mb, peak_mb),
  CPU (cpu_pct over the interval), threads, open files, the database's size and its number
  of rows, the pools' queues, caches, the number of Qt widgets and lane rows, the picture
  cache. These lines show a leak: what grows over time;
* Qt's own messages (they used to pour into the terminal);
* if the window doesn't answer for longer than `debug.watchdog_seconds` seconds — the stacks of all
  threads (what exactly it hangs on) and then "responsive again after N s";
* shorter freezes — from `debug.stall_ms` (250 ms): a line `GUI froze N ms: [label] stack`.
  The label says what the window was busy with: `event lanes_updated`, `lane home: draw`,
  `picture in (3 cards)`, `result …` (a server answer reached the window). `Qt itself` —
  our code wasn't running, Qt was laying out and painting by itself (long texts, many cards).
  The `stats` line has `freezes.count`, `freezes.total_ms`, `freezes.worst_ms`;
* every picture (at the debug level): `image feed|big …: queue 0.10 s, download
  52002 B 0.26 s, decode 12 ms -> 400x300` — how long it waited for a worker, downloaded,
  decoded; `… ms in the window for N cards` — if putting it into cards took longer than
  50 ms. `stats` has `img.*`: how many were downloaded and broke, from the cache, the queues, the average
  and worst download and decode times, the time in the window.

**Where it's slow, by the log.** Look for `GUI froze`: the label and the stack say whether it's drawing,
an event or a picture. Pictures appear slowly but there are no freezes — then they're waiting for the network:
look at `queue` (not enough workers) and `download` (a slow server), `ReadTimeout`
and `second try`.

## If something happened

**A development version (a number with .dev, from git).** The debugging mode is on by itself there, and
the start of every session's `fedtail.log` already has everything `--bug-report` would add: the versions
(fedtail, Python, Qt / GTK), the system, the changed options and the `config.toml` itself. So
sending one log is enough (the logs folder is in the session's first line, `"logs": …`). There's no token and
no database in the log.

**It crashed.** Run `python3 -m fedtail --bug-report` — your home folder gets
`fedtail-report-<profile>-<date>.tar.gz`. Send that file. It has the logs,
crash.log, stacks.log, config.toml and a summary of the system. The token's file
(`auth.json`) and the database (`state.db`) aren't in it.

**It hangs / is slow.** Without closing the client:

* the ≡ menu → "Debugging" → "Write the threads' stacks and stats", or
* in a terminal: `kill -USR1 $(pgrep -f "python3 -m fedtail")` — the stacks go to
  `stacks.log` even if the window doesn't answer at all;

then `--bug-report` (or the menu → "Make a report for analysis") and send it.

**No notifications.** The ≡ menu → "Debugging" → "Test a notification". If none came —
the log will have `notifications:` lines (which way was chosen and why) and `notify-send exit …`
(what the system answered). Without the `libnotify-bin` package notifications go through the tray.

**It eats memory or CPU.** A `--bug-report` after it has run for a while is enough:
the log has the `stats` lines for the whole time. In detail — the next section.

## The state of the federation

≡ → "Debugging" → "Federation status" — a summary of what doesn't depend on the client: how
your server answers (how much, how fast, how much with errors), the poll and the live stream, what the server can't do,
who's waiting in lists (the nick is a link to the profile, and why they wait), and which requests get 404/410/401/a timeout again and again — at your server and
at other servers, with a note on "what it means". "Copy" gives the same as text — you can
attach it to a report instead of digging through logs. It's the memory of one run: after a restart the count
starts again.

## An overnight run: hunting leaks

Leave the window overnight (or for a day) and find out in the morning what grew, and what exactly.

1. A development version (from git) — the debugging mode is on by itself. A release — `debug.mode = "on"`.
2. For a serious hunt — `debug.tracemalloc = true` in the config (or ≡ → "Debugging" →
   "Memory tracing" after the start). Slower and up to twice the memory: only
   for the time of the hunt. Everything else works without it too.
3. Start it, open your usual lanes, a couple of threads and profiles, close them — as in the daytime.
   A minute later ≡ → "Debugging" → "Memory snapshot" (if tracing is on) — the starting point.
4. Leave it. In the morning: "Memory snapshot" once more, "What grows: stats and object census
   now", then `--bug-report` (or just the logs folder) — and send it.

What to read in the log (`grep` by the start of the line):

* `stats {…}` — every `stats_minutes`: `rss_mb` (the process's memory), `py_objects`,
  `qt.widgets`, `qt.rows` (cards built), `qt.model` (posts in lanes),
  `qt.images_mb`, `threads`, `fds`, `gc.uncollectable`, `core.*` (queues, caches, database
  rows, `db_mb`);
* `trend over N h {…}` — right after: for each of these numbers "at start → now (± an hour over
  the whole session; last M min ± an hour over the last minutes)";
* `possible leak: X rose on each of the last 12 checks: A -> B (+N/h over H h; +M since
  start)` — the number grew at every check for the last hour, and not by crumbs. Quiet for the first half hour
  (the lanes fill up), says it again when the growth since start has doubled;
* `census python: … since last: dict +1200, fedtail.frontends.qt.card.PostRow +40 …;
  since start: …` — which Python objects were added (in the debugging mode, with every
  stats line); `census qt_widgets: …` — the same for Qt widgets by class. `PostRow`/`QLabel`
  grows while `qt.rows` stays the same — widgets aren't deleted; `dict`/`list` grow
  while widgets are level — something hoards data;
* `memory: N MB given back to the system` — how much memory went back after cleaning:
  if rss grows but a lot is given back here, it's not a leak but peaks;
* `storage gc: {…}; X MB of N, K per lane, T s` — cleaning the database (every `storage.gc_hours`):
  how much of what was forgotten, how much the database weighs after and how many entries each lane keeps.
  `storage: still … after gc` — the database didn't fit into `storage.max_mb` even with short lanes.
* `python3 tools/model_check.py [PROFILE]` — run your database through the new data model
  (read only, sends nothing). Prints counters and the share of filled fields,
  no texts and no names — can be sent as it is.
* `session summary {…}` and `session trend {…}` — the session's last lines: hours, memory, peak,
  freezes, polls and the verdict on the trends.

Memory snapshots are `memory-<time>.txt` files in the logs folder: "top by size" — which lines of code
hold the most memory now, "grew most since the first snapshot" — what grew since the
first snapshot, and where the main growing chunk was allocated. They hold only places in the code —
no post texts, no token. They go together with old logs.

Mind: **rss grows normally too** for the first half hour to an hour (lanes, pictures, caches) and jumps when
big lanes are opened. A leak is when it grows steadily all the time, with the same
actions; that's what trend and possible leak are for.

## Settings — the `[debug]` section

```toml
[debug]
level = "debug"            # "debug" | "info" | "warning" — how detailed the log is
log_mb = 10                # the size of one log file
keep_mb = 500              # how many MB of logs to keep
stats_minutes = 5          # 0 — don't write stats
trim_memory = true         # give freed memory back to the system
watchdog_seconds = 8       # 0 — don't watch for the window hanging
stall_ms = 250             # window freezes shorter than the watchdog; 0 — don't watch
slow_request_seconds = 5
rss_warn_mb = 1500
leak_samples = 12          # "possible leak": growth over this many checks in a row
object_census = true       # a census of objects and widgets (in the debugging mode)
tracemalloc = false        # memory tracing from the start (for hunting a leak)
```

`--debug` also prints the whole log to the terminal.
