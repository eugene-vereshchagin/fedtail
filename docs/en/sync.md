# Sync between your devices

[По-русски](/docs/ru/sync.md)

fedtail on the desktop, on a laptop, later on a phone — one account, one set of read
marks. Read a post on one, it is read on the others; follow a thread, leave it or mute
it, move a list up the sidebar — and so it is everywhere.

Sync is a **service of its own**, apart from your fediverse server: fedtail syncs only
when you tell it where (`sync.url` or `sync.folder`). Without that there is no sync —
the status bar says "⇅ off", About says why.

What travels — a switch for each in `[sync]` (all on by default; off keeps that thing on
this device only):

| switch | what it means | how two devices agree |
|---|---|---|
| `sync.read` | read marks **you** made: scrolling, opening, "mark read" | a mark is never taken back, so they simply add up |
| `sync.threads` | a thread you followed, left or muted by hand | the newest setting wins |
| `sync.lanes` | your lanes as you arranged them: the order of lists (servers keep none, so every device would show them as they came) and the tag lanes you saved | the newest arrangement wins |
| `sync.drafts` | drafts: begun on one device, finished on another; sent or emptied — gone everywhere. Text, content warning, poll, who sees it; pictures are files of each computer and stay where they were added | the newest version of each draft wins |
| `sync.activity` | notifications you dismissed from Activity | they only add up, like read marks |
| `sync.tiles` | which lanes the phone pins as tiles | the newest set wins |

What stays on each device: the marks fedtail makes by itself (everything read on the
first run, older history, your own posts), automatic subscriptions to your own posts
(every device makes them), the posts themselves, the config. So a new phone won't mark
the desktop's unread lanes read.

Short post names (`#kq3zt`) are the same on every device without any of this: they are
derived from the post's id.

## How it works

Every device keeps a journal of what it did and sends it, sealed, to a place all your
devices reach; there it picks up the others' journals. The place is either

* a **fedtail-sync server** — one small program on a name of its own (`sync.url`); or
* a **folder** every device sees — a NAS share, a WebDAV folder mounted (davfs2, rclone),
  a Syncthing folder.

The journals are encrypted (AES-256-GCM) with a key only your devices have. The server
or the folder sees opaque blobs: who sent them, how big, when — not what you read, not
which threads. Losing every device with the key loses only the read marks: they can't
be recovered, and they aren't worth much.

To the sync server fedtail never gives its own token (that one opens your whole account).
`fedtail sync login` asks your fediverse server for a second one, limited to
`read:accounts` — it can only tell "who am I". The sync server checks it with your server
and files your journal under that answer: no accounts or passwords of its own.

## Turning it on

In every device's config — one line, the address its admin gave you:

```toml
[sync]
url = "https://sync.example.org"
```

or, instead of a server, a folder every device sees:

```toml
[sync]
folder = "~/Sync/fedtail"
```

Nothing is looked up by itself: no address, no sync.

With a **sync server**, on every device, once:

```sh
fedtail sync login      # opens a page on your server: allow "fedtail sync", paste the code
```

The **key**: the first device makes it at its first sync. Show it there and carry it to
the others (by hand, a password manager, a QR app — it is a secret: whoever has it and
your token can read your journal):

```sh
fedtail sync now        # on the first device: makes the key, sends what's there
fedtail sync key        # shows it: XXXX-XXXX-…
fedtail sync join XXXX-XXXX-…   # on every other device
```

`fedtail sync status` says where it syncs, the key's id, what's waiting to be sent and
how the last round went. The window syncs by itself every `sync.interval_seconds` and a
few seconds after you read something. The right of the status bar shows it: "⇅ 21:40" —
synced then (hover for where, what went and came), "⇅ …" — not yet, "⇅ !" — a problem
(hover for which), "⇅ off" — no address in the config. About has the same in a row.

A device without the key that finds someone's journal already there doesn't make a key
of its own: it asks for `fedtail sync join`.

## Running a fedtail-sync server

The server is a project of its own, with its own page: [`syncserver/README.md`](/syncserver/README.md)
— installing it (one file, Python 3.11+, SQLite), the config, a systemd unit, putting it
behind Cloudflare Tunnel, nginx or Caddy, how it guards itself, and serving people of
other servers. What it speaks is in [`syncserver/PROTOCOL.md`](/syncserver/PROTOCOL.md).

## Not yet

* Carrying the key with a QR code from the window (now: `fedtail sync key` / `join`).
* Pictures of a draft travelling with it (now: they stay on the device they were added on).
* WebDAV spoken directly (now: mounted as a folder).
* Packing old journals into a snapshot (now: they just add up, within the quota).
