# fedtail — design and spec

A desktop client for the fediverse (GoToSocial, Mastodon, Akkoma — anything that speaks the
Mastodon API) for those who remember Juick and Point.im and can't stand the noodles of other
people's conversations cut to pieces.

How the code is built — [architecture.md](architecture.md) (in detail);
logs and diagnostics — [debugging.md](debugging.md).

## Principles

<!-- include: parts/principles lang=en -->
1. **Nothing jumps.** Open a lane and you stand at the first unread. New posts come and your
   place doesn't move, only the counter grows. You read in order, like RSS.
2. **Every reply knows what it answers.** Over a reply, a strip with the start of the original
   post; under someone's comment, what you said back to it: come back to a thread a week later
   and you see at once where you were. A click opens the whole thread as a tree.
3. **Lanes are apart.** People apart, bots apart, replies to me apart from other mentions.
4. **Private by default.** A new post goes to followers only. A reply is never more public than
   the original.
5. **Every behaviour is a config key.** There's no settings window and there won't be. The
   defaults are as the author likes them; "like everyone else" is a flag away. New features
   come switchable.
6. **Other servers get no token of yours.** Whatever fedtail takes straight from the author's
   server over ActivityPub goes anonymously: they see only your IP.
7. **The core knows nothing of a GUI.** Interfaces are plugins: a Qt window, a terminal, a
   browser; GTK next.
8. **One profile, one account.** A second account is a second profile (`--profile`); if you
   like, all accounts come together in one window (`accounts.merge`).
9. **Grown-ups sort things out themselves.** Arts mode (after @arts, the founder of Point.im):
   everything as the author posted it, no nannying. Anyone can be told where to go, an admin
   too — and the admin can say the same back.
<!-- /include -->

## Architecture

The detailed and current description is in [architecture.md](architecture.md): the module map,
threads, the database schema, sources and lanes, the poll cycle, events, the Qt interface,
themes, the config, tests and recipes for "how to add a lane / option / event / frontend". In
short: the core (`fedtail/core`) knows nothing of GUIs and talks to the interface through
futures and events; interfaces are plugins in `fedtail/frontends`; all behaviour is flags in
`config.toml`.

## Flags

The full list with comments — `fedtail/data/config.example.en.toml` (and `.ru.toml`),
as tables — [config.md](../config.md); features — [features.md](../features.md).

## What's done

Version by version — in the [CHANGELOG](../../../CHANGELOG.md). What's next — in "The queue" below.

### Frontends

The core knows nothing of GUIs, interfaces are plugins (`--ui`). Besides Qt, planned, roughly in order:

| frontend | for whom |
|---|---|
| **CLI** | `fedtail tail comments` — new comments to the terminal as they come, `fedtail post "text"`; scripts and pipes |
| **TUI** (Textual) | a full interface in the terminal, mouse and colour, works over ssh |
| **GTK4 + libadwaita** | GNOME, Cinnamon and other GTK desktops, to look native |
| **web on localhost** | open it in a browser, the phone on the home network too |
| **Toga** (BeeWare) | native Windows/macOS/GTK/Android/iOS widgets from one code base; to try |

## The queue

What's done is in the CHANGELOG. Now — a public beta: installing, feedback, fixing what people
find. Next, roughly in order:

1. ~~**Bookmarks**~~ — done. Like on Point: "bookmark" on a post and a "Bookmarks" lane (the server's bookmarks).
2. ~~**Silence**~~ — done. Hide a person (mute), block, word filters (the server's filters v2):
   so the federation doesn't turn into a dump.
3. ~~**Editing my own posts**~~ — done (with the edit history, as the server gives it).
4. ~~The command line as on Point and the "conversations" view~~ — done.
5. ~~**Polls**~~ — done: show and vote.
6. ~~**Several accounts**~~ — done: profiles, a switcher on a right click on the avatar, all accounts in one window.
7. ~~**A Windows port**~~ — done: paths in AppData, one window per profile through a named
   pipe, a Start menu entry, one .exe in every release. Next —
   an installer (MSI/Inno Setup) and signing, when there are Windows users.
7½. ~~**Like everyone else, but configurable**~~ — done in 0.8: a shared reading position (markers),
   link cards, the servers' emoji, quotes (shown and my own), completion of @names and #tags,
   private messages as a lane of their own, "My likes", polls, scheduled posts, translation,
   pinned posts, reports, blocking servers, notes, the bell, j/k; ActivityPub —
   the outbox and followers from the author's server, Mastodon-Async-Refresh. Each one is a config flag.
8. **Frontends:** ~~CLI~~ (0.9) → ~~TUI~~ (0.10) → GTK4 → ~~web~~ (0.10) → Toga.
9. ~~A one-file build~~ — done: PyInstaller in CI, `fedtail-X.Y.Z-linux-x86_64` (built on
   Debian 12) and `fedtail-X.Y.Z-windows.exe` in every release; `packaging/build.py`.
10. **A deb package** with a build number — at the very end. Built in CI (a Debian 13 container),
   attached to the release, later — an apt repository of its own.
   Dependencies (Debian 13): `python3 (>= 3.11)`, `python3-pyside6.qtwidgets`,
   `python3-requests`; Recommends: `python3-pyside6.qtdbus` (the number on the taskbar
   button), `qt6-image-formats-plugins` (webp/avif/tiff in the viewer — without it such
   originals aren't shown), `libnotify-bin` (notify-send, notifications),
   `python3-cryptography` (sync between devices, docs/en/sync.md), `python3-langdetect`
   (telling the language of a Latin-script post, `lanes.detect_language`).

11. ~~**Cleaning the database.**~~ — done (0.17.0): `Store.gc`, `[storage]`, the `max_mb` budget.

12. **Protocols and a data model of our own.** The Mastodon API is the first protocol, not the
   shape of the program; frontends see only our own model. The plan and the stages — [protocols.md](protocols.md).

Taken out of the queue (not needed for now): an XMPP gateway, following old threads in bulk.

## Known server limits

- A server notifies only about replies where you were mentioned. Two people answering each other
  in your thread won't land in "Replies to me" — thread subscriptions catch that: the client rereads
  threads every `threads.interval_minutes` by itself. You see what your server knows: if neither you
  nor anyone on your server follows the author of a reply, the server may never get it.
- Vanilla Mastodon doesn't understand Markdown. The client finds that out by itself (`post.markdown = "auto"`).
