# Robustness: questions and answers

What fedtail does in awkward situations: the network, the OS, the disk, the interface,
security, state, installing, resources. Each row says how it is now and what was
decided. "Done in 0.20" means this version added the behaviour; the checks are in
`tests/test_robust.py` and nearby. "The author's call" is a choice that changes the
product, not only the code.

## 1. Network and API

| question | answer | decision |
|---|---|---|
| Connection timeout | `requests` with `timeout=30` on every request: for connecting and for each read. A poll that times out writes a log line and waits for the next round | there |
| The server took the request and stays silent | the same: 30 s a read; sending a post — 90 s (`post.send_timeout`). Sending again goes with the same `Idempotency-Key`, so the post is never doubled | there |
| TCP cut in the middle of an answer | `requests` raises `ConnectionError`/`ChunkedEncodingError`; the poll round counts as failed, nothing is spoiled: only a parsed answer is written to the database, in one transaction | there |
| Retries of failed requests | not within a round; the next round is the retry. Sending a post — one retry with the same key | there |
| Exponential backoff | rounds failing in a row wait longer each time: 90 s, 3, 6, 12 min, at most 15 min; Refresh asks at once. The live stream reconnects after 5, 15, 30, 60, 120, 300 s | done in 0.20 |
| The IP changes on the fly (Wi-Fi → mobile, a VPN) | the old connection breaks; the next round opens a new one. The live stream notices the silence by its ping (60 s) and reconnects. Nothing is lost: polling catches up from the last known id | there |
| A network but no internet (a captive portal) | an answer that isn't JSON (the network's login page, a provider's stub) is an error saying "not an API answer — the network's login page or a proxy?"; the log gets its content type and size | done in 0.20 |
| HTTP 429 | no requests until the server's window ends (`X-RateLimit-Reset`, `Retry-After`); rounds slow down beforehand when the budget is nearly spent, keeping a reserve for what is done by hand | there |
| Invalid JSON | see the captive portal: an error that explains, no crash | done in 0.20 |
| 1 GB instead of 10 KB | nothing over 32 MB is read: refused by `Content-Length`, or without it at the 32nd megabyte; the connection is closed. A live stream frame — 16 MB at most | done in 0.20 |
| SSL validation, MITM | `requests` checks the certificate and the name always; a self-signed one won't pass. The token goes to one's own server only, over https; the stream — wss to the same site only. A corporate CA of one's own — `REQUESTS_CA_BUNDLE` | there |
| WebSocket: a drop | the stream only wakes polling and brings nothing itself, so nothing is lost in a drop: the poll brings it | there |
| Proxies with NTLM/Kerberos | `HTTP(S)_PROXY` from the environment work; NTLM/Kerberos don't. Way round: a local proxy in between (cntlm, px) | the author's call |

## 2. OS and the process's life

| question | answer | decision |
|---|---|---|
| Sleep and waking | the wait for the next round notices the computer slept (the wall clock went on, the monotonic one stood) and polls at once; the stream reconnects by itself | done in 0.20 |
| The time or the zone changed | intervals are measured by the monotonic clock; posts' dates come in UTC and are shown in the zone of the moment they're drawn. A clock badly wrong breaks TLS checks — the connection error says so | there |
| Several copies | one window a profile; different profiles run side by side. A second copy of the same profile brings up the first and exits | there |
| How the single instance works; the first copy hung | a unix socket in the profile's folder (0600) or a Windows named pipe with a key from the profile's folder. A hung first copy isn't replaced: its listening thread answers, the window doesn't come. Ending the process cures it | the author's call |
| `kill -9` / End Task | no lock files; a stale socket is removed at the next start, a Windows pipe goes with its process. SQLite in WAL mode recovers by itself; the config and the login are written atomically | there |
| Fast user switching | everything is in the user's home (`%APPDATA%`, `~/.local/share`); each user has a pipe and a key of their own, another's process can't reach the window | there |
| Cyrillic, spaces in paths | paths are `pathlib`, calls without a shell; tests on Windows paths | there |
| SIGTERM, shutting down | Qt and GTK quit on SIGTERM as from the menu: the window's place, drafts and read marks kept; the web page too | done in 0.20 |
| Administrator rights | not needed: the Windows installer installs into the user's folder, the deb the usual way, the data in the home folder | there |

## 3. Files and data

| question | answer | decision |
|---|---|---|
| The disk filled up while writing | the config and the login go to a temporary file and replace the old in one step, the old stay whole; the database — an SQLite transaction, the poll round fails and waits longer | there |
| Atomic writes | yes: `config_edit.save` (with `.bak` and fsync), `auth.save`, `--update-config`, `--rebuild-config`, the sync files | done in 0.20 (`--update-config`) |
| A config with a syntax error | from a terminal — a message with where it is, and exit; from a menu or a shortcut — a window: "Start with the default settings", "Open the file", "Quit". The file isn't touched | done in 0.20 |
| The logs' or the cache's folder made read-only | the logs go to the temporary folder (and if not there either — to the terminal only), the start doesn't fail; pictures are shown from memory | done in 0.20 |
| Locking the database | SQLite's own locks; `busy_timeout` 5 s; no two processes on one database (one copy a profile, the web page refuses a busy profile) | there |
| Clearing the cache, limits | the database: `storage.max_mb` (1 GB), `keep_per_lane`, cleaned every `gc_hours`; pictures on disk — `media.image_disk_mb` (1 GB), video — `media.video_disk_mb`; in memory — `media.image_cache_mb` (128 MB) | there |
| A file deleted or changed while uploading | an error for that picture, in words; the editor and the text stay, it can be attached again | there |
| Log rotation | a new file every hour and by size (`debug.log_mb`), at most `debug.keep_mb` in all (500 MB when debugging; without debugging 1 MB a file and 5 MB in all, warnings only) | there |

## 4. Interface

| question | answer | decision |
|---|---|---|
| Is the main thread blocked | the network and the database work in background threads, the window gets finished answers only; a connection of its own for reading the database; a watchdog logs freezes (when debugging). Benches measure scrolling and menus | there |
| Monitors with different scaling | Qt 6 and GTK 4 redraw for each monitor's scale themselves | there |
| The window's size and state | Qt keeps the geometry and "maximized"; GTK — the size (on Wayland the compositor places windows) | there |
| A monitor unplugged | Qt moves the restored window onto a visible screen; GTK doesn't keep the position | there |
| The system's light/dark switched | the `system` theme takes the desktop's colours at start; on the go — after a restart or through ≡ → "Try a theme" | the author's call |
| Hammering Send | the button goes grey while sending in every interface; the server gets an `Idempotency-Key`, a repeat makes no second post | there |
| Keyboard navigation | j/k, Enter, ←/→, Tab, shortcuts all over the window; the terminal entirely by keyboard; labels for screen readers | there |
| 100 000 items | a lane holds at most `reading.render_limit` in the window, cards are built for the visible stretch only; the database keeps `keep_per_lane` a lane | there |
| An empty string, null, a word without spaces | the adapter brings fields to their types with safe values; long words get invisible break points (Qt, GTK), the web page `overflow-wrap: anywhere`; a long picture description scrolls | there; the description — done in 0.20 |

## 5. Security

| question | answer | decision |
|---|---|---|
| Where the token is kept | `auth.json` with 0600 in the profile's data folder; on Android in the app's private data. The system's store (Secret Service, DPAPI, Keychain) isn't used — a long-standing decision | the author's call |
| Tokens and PII in the logs | never written: the log gets the method, the path, paging parameters and timing; bodies, posts' text and headers — no. A bug report takes neither `auth.json` nor the database | there |
| Passwords in memory | fedtail never sees a password: logging in goes through the browser (OAuth), memory holds only the token — as a Python string, as in any Python client | there |
| Encrypting the database | no: the database is in the user's home, under their account's rights. Encryption (SQLCipher) is a dependency of its own | the author's call |
| Injections | SQL with parameters only; HTML from the server cleaned by a whitelist of tags; a post's text goes out as JSON | there |
| Obfuscation | none: open source under the GPL | there |

## 6. State and logic

| question | answer | decision |
|---|---|---|
| Deleted here, already deleted there | the server answers 404 — the post just goes here too, no error | done in 0.20 |
| Offline | drafts save themselves; read marks pile up and go when there's a connection (the server's markers and sync between devices); a post won't go without the network — it stays in the editor | there |
| Sync conflicts | Last Write Wins for each key: the time and the device in `sync_lww` | there |
| Asleep for 3 days | a round at once on waking; scheduled posts and timed mutes live on the server; the database's cleaning runs once | done in 0.20 (the round on waking) |
| Races | the database under a lock, reading through a connection of its own; the core's events reach the window through the main thread's queue | there |

## 7. Installing and updating

| question | answer | decision |
|---|---|---|
| An update's authenticity | no auto-update. A GitHub release carries `SHA256SUMS`; the apt repository is signed with a key; the exe is signed with a certificate when there is one; the apk with the release key | `SHA256SUMS` done in 0.20; the keys — the author's call |
| Atomic updates | the Inno Setup installer and dpkg roll an unfinished install back; the profile's data isn't touched | there |
| Database migrations | missing columns are added at start; each step checks itself and is done again at the next start if it didn't finish | there |
| A migration failed | the next start goes on from there; no data is deleted | there |
| Back to an older version | the old version works with the new database: columns were only added | there |
| The uninstaller | removes the program and its shortcuts; the profile in `%APPDATA%\fedtail` is left on purpose — it's the user's data | there |
| Updating without administrator rights | the installer installs into the user's folder, no rights needed | there |

## 8. Performance and resources

| question | answer | decision |
|---|---|---|
| A week without closing | a lane is capped by `render_limit`, the database is cleaned, the picture cache in memory is an LRU with a budget. `tools/tabs_stress.py` (tabs and "a day's work"): memory levels off; Qt keeps a trifle — Python wrappers of closed tabs' deleted menus | there |
| Closed tabs' cache | a closed tab lets go of its cards and what refers to them; pictures stay in the shared cache until the budget pushes them out | there |
| Battery, processor wake-ups | a poll every 90 s (or slow mode), the stream wakes on an event; without debugging no timers every second; Qt looks for signals once a second. Android — every 15 minutes and push | done in 0.20 (the timers) |
| The GPU with the window minimized | a window not seen isn't drawn, in Qt or GTK | there |
| Logs and the disk | a buffered file handler; without debugging warnings only | there |

## The author's calls

| question | options |
|---|---|
| Where the token is kept | keep the 0600 file; DPAPI on Windows, no dependencies; Secret Service through QtDBus on Linux |
| Encrypting the database | don't; SQLCipher (a dependency and a password at start) |
| Auto-update | none (apt, a store, downloading by hand); a check for a new version with a hint in the menu |
| NTLM/Kerberos proxies | document a go-between; add `requests-ntlm` |
| The system's dark theme on the go | apply at once (Qt: `colorSchemeChanged`); keep it at start |
| A hung first copy | the window answers with a timeout, and offers to end the old process |
| The Windows certificate, the apt key | the secrets `WINDOWS_CERT_PFX`, `APT_GPG_KEY` |
