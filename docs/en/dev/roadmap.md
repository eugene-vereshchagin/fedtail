# fedtail: the plan for 0.21

What we do in 0.21 (decided on 26 Oct 2026, with 0.20.0 ready to come out): **sync between
devices brought to the end** and **free lanes** — lanes one assembles oneself. The user's
side is in the feature list with the status "planned" (`docs/src/features/*.toml` →
`docs/*/parts/roadmap.md` and the site); here — the whole plan, with the development part.

## What 0.20 brought

Android as a full fediverse client (every place, the ⋯ menu, profiles, the editor, push);
the terminal and the web with everything the windows have, the web's columns too; slow mode, "notify at most
every…", "of them new"; reactions of one's own; collections, another server's timeline, a
link's timeline; an apt repository and a Windows installer (waiting for their keys); the
robustness answers (`robustness.md`) and the self-check with real accounts on Linux,
Windows and Android. Everything — in CHANGELOG.md.

## Doing

| # | what | how we'll know it's done |
|---|---|---|
| 1 | **Sync, checked live**: Linux, Windows and Android on one account through a fedtail-sync server and through a folder; read marks, threads, lanes, drafts, activity, tiles travel; a new device doesn't mark the others' unread read | a self-check step on two profiles with one sync folder (`tools/selfcheck.py`); the same by hand on three devices |
| 2 | **Sync: what's "not yet" now** (`docs/en/sync.md`): the key carried by a QR code from the window and the phone's camera; a draft's pictures travelling with it; WebDAV spoken directly; old journals packed into a snapshot | each — a feature "has" with its `since`, the "Not yet" list empty or with the reason why not |
| 3 | **Sync in every interface**: the state, "sync now", the key, the errors in words — Qt, GTK, the terminal, the web, Android the same | `tools/parity.py` without sync lines; the behaviour scenario has a sync step |
| 4 | **Free lanes, the core** (`feeds.md` §9, steps 1–5): atoms, rules with strict checks and `explain`, the built-in lanes as presets (the same output as today), lanes over several sources, "Unsorted", "Why is it here?", `--explain-lane` | a test over a recorded store: the presets give today's lanes item for item; every key and every error of a rule tested |
| 5 | **Free lanes, outside** (§9, steps 6–7): `[[lanes.custom]]` in the config and both examples, the features and the help; the sidebar, columns, tiles, notifications by the most personal lane in every interface | a lane from the config shows the same in Qt, GTK, the terminal, the web and Android; parity — 0 differences |

## Waiting for a decision

- `feeds.md` §10: nested groups in `any`; events and posts in one lane; `in_my_thread`
  without following; the lane editor on the phone.
- The sync server: one public instance of the project's own, or only "run your own".
- The author's calls of `robustness.md`: the token's store, encrypting the database,
  checking for a new version, NTLM proxies, the system's theme on the go, a hung first copy.

## Loose ends

- The secrets: `APT_GPG_KEY` and GitHub Pages for the `apt` branch, `WINDOWS_CERT_PFX`.
- The tray icon that stays after quitting from the roster in KDE (split layout) — check
  on 0.20.0.
- Freezes on a lane's first click with many cards (`card.py` `_hint_width`): measure on
  a real account.

## Not in 0.21

Toga; the token from an external command; Mastodon's annual report and the other "won't
do" of the feature list.
