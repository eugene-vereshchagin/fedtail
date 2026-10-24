# fedtail: the plan for 0.19

What we do in 0.19 (decided on 22 Oct 2026, after 0.18.0 came out). The user's side is
in the feature list with the status "planned" (`docs/src/features/*.toml` → `docs/*/parts/roadmap.md`
and the site); here — the whole plan, with the development part.

## Doing

| # | what | how we'll know it's done |
|---|---|---|
| 1 | **A sound scheme**: sounds are part of the theme, like icons (the theme's folder, a set of their own for the messenger themes: a new message, a reply, a mention, signing in), can be switched off; Qt, GTK, the terminal if possible (bell) | the feature `sound-scheme` — "has"; a test: an event → the theme's sound; without a sound system — silence |
| 2 | **Tests on Windows**: fill in what's skipped now or holds on Linux only (paths, the Start menu entry, the tray, notifications, single-instance, debugging logs); `docs/en/dev/windows.md` runs whole | the same set as in CI for Windows, green on your virtual machine; skips — only what Windows doesn't have by nature (GTK, `.desktop`, D-Bus) |
| 3 | **The same behaviour in every toolkit**: not only the interface's words (`tools/parity.py`), but what the same actions do in Qt, GTK, the web and the terminal — a shared scenario (open a lane, read, reply, like, a thread, a profile, a post's menu, Esc, quit) on a fake server, the same results | `tools/parity.py` + a new scenario test; differences — in the self-check report, 0 at a release |
| 4 | **A complete terminal (TUI)**: everything the windows have, within a terminal's means — a post's menu, a profile with all its buttons, lists, search, silence, help, "what's new", account settings | the TUI's parity by `parity.md` — like GTK's (≥ 90 % of the words), the scenario of item 3 passes |
| 5 | **A complete web**: the same for the web — lists, silence, find in a lane, editing the profile, requests, "Activity" with groups, browser notifications | the web's parity ≥ 90 %, the scenario of item 3 passes |

## Where we are (22 Oct 2026, evening)

| # | state |
|---|---|
| 1 | the sound scheme — there (Qt, GTK, the terminal, the web); `sound.enabled = "auto"`: sound in dev, silence in releases |
| 2 | `tests/test_windows.py` (Windows simulated — everywhere), `tools/windows_check.py` (docs/en/dev/windows.md whole, the self-check's `windows` step); a run on the virtual machine — your move |
| 3 | `tools/behaviour.py`: the web and the terminal match the shared code over the whole scenario; the Qt and GTK drivers are written blind — waiting for a run |
| 4 | the terminal: ⋯, ≡, all places, the profile, the editor, Ctrl+F, the lane as in the windows; parity by words 51 % |
| 5 | the web: all places, the lane and the card as in the windows, the editor with attachments/a poll/"later", Ctrl+F, notifications; parity by words 49 % |

## Loose ends we also close in 0.19

- GTK: check Wayland live, the colour match with Qt (`SameAsQtTest` in CI), GNOME and XFCE.
- Screen readers: go through the interface with Orca (Qt and GTK), fix what isn't read out.
- Showing reactions — there; giving my own — when the server can (GoToSocial can't).
- The first start on a new machine: check live on Windows (delete
  `%LOCALAPPDATA%\fedtail\default` and start) — what's unread from another machine is kept.
- Mastodon 4.3+ notification groups — check on a live account.
- Logging in through the browser on the Windows VM (the server got the wrong password) — find out what
  changes on pasting.

## Waiting for a decision

A public lane of another server; a lane by link (Mastodon 4.3+); giving emoji reactions;
the token through `pass`/`gopass`; spell checking (you said it's not needed: move it to "won't
do"?).

## Not in 0.19

Collections (waiting for GoToSocial), Toga, an apt repository of our own, an installer and signing for Windows,
Android (postponed).
