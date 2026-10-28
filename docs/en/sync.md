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
| `sync.drafts` | drafts: begun on one device, finished on another; sent or emptied — gone everywhere. Text, content warning, poll, who sees it, and the pictures (sealed, each sent once; too big for the store — it stays where it was added) | the newest version of each draft wins |
| `sync.activity` | notifications you dismissed from Activity | they only add up, like read marks |
| `sync.tiles` | which lanes the phone pins as tiles | the newest set wins |
| `sync.lane_rules` (off by default) | the lanes themselves: the set, which lanes in what order, your own lanes, `lanes.posts_only` — written into the other device's config.toml. They go when they change (by hand or in the lane editor); a device just started sends nothing of its own | the newest wins |

What stays on each device: the marks fedtail makes by itself (everything read on the
first run, older history, your own posts), automatic subscriptions to your own posts
(every device makes them), the posts themselves, the config. So a new phone won't mark
the desktop's unread lanes read.

Short post names (`#kq3zt`) are the same on every device without any of this: they are
derived from the post's id.

## How it works

Every device keeps a journal of what it did and sends it, sealed, to a place all your
devices reach; there it picks up the others' journals. The first time a device syncs
under a key, it also sends once what it knew already — the order of lists, saved tag
lanes, how far the events are seen, the read marks of the posts it keeps — so a device
added later gets the state, not only what changed after it came (a real change anywhere
beats that first picture). The place is either

* a **fedtail-sync server** — one small program on a name of its own (`sync.url`); or
* a **folder** every device sees — a NAS share, a WebDAV folder mounted (davfs2, rclone),
  a Syncthing folder.

The journals are encrypted (AES-256-GCM) with a key only your devices have. The server
or the folder sees opaque blobs: who sent them, how big, when — not what you read, not
which threads. Losing every device with the key loses only the read marks: they can't
be recovered, and they aren't worth much.

To the sync server fedtail never gives its own token (that one opens your whole account).
Logging in to the sync server asks your fediverse server for a second one, limited to
`read:accounts` — it can only tell "who am I". The sync server checks it with your server
and files your journal under that answer: no accounts or passwords of its own.

## Turning it on

All of it is in the window: **≡ → Sync** (or a click on "⇅" in the status bar). On top —
three steps marked ✓ (done), ▶ (now) and · (later); below — only what the current step
needs. The same in the Qt window, GTK, the terminal, the web page and the phone.

1. **Where the devices meet** — the sync server's address your admin gave you
   (`https://sync.example.org`), or a folder all your devices see (`~/Sync/fedtail`).
   "Next" writes it into config.toml (`sync.url` / `sync.folder`) and turns sync on at
   once, no restart.
2. **Login to the sync server** (with a server only) — "Open the login page": your
   fediverse server's page opens, allow "fedtail sync", paste the code, "Next".
3. **The key** — a fork, what this device is:
   * **"This is my first device"** — sync isn't set up anywhere yet: the key is made
     here, and this device starts the journal. If the store holds someone's journal
     already, fedtail says so and offers the other way.
   * **"I'm adding this device to those already syncing"** — on the old device
     ≡ → Sync → "Show the key": a QR code and its text — the phone scans the code
     ("Scan the QR code" by the field), elsewhere paste the text. Or, if a "password for new
     devices" was set there, that alone, no old device needed. Neither
     at hand — "Start again with a new key…" (what was read before won't come here, and
     the other devices will have to take the new key later).

Once it's all done, the same page shows how it goes, "Sync now", "Show the key" (its QR code
and text) for the next device, what to sync, changing the server, turning it off.

**A password for new devices** (optional, there too — "Set a password…"). It's not your
account's password nor the server's: you make it up. The key goes into the sync journal
sealed by it (scrypt + AES-GCM), and a new device needs the password instead of the long
key. Forgot it — nothing breaks: the key can always be copied from a working device.

A device without the key that finds someone's journal in the store doesn't make a key of
its own: it says the key is needed (and that it can be taken by a password, if it is in
the journal).

The status bar shows how it goes: "⇅ 21:40" — synced then (the tooltip: where, how much
went out and came in), "⇅ …" — not yet, "⇅ !" — trouble (the tooltip says which), "⇅ off"
— nowhere set. The window syncs by itself every `sync.interval_seconds` and a few seconds
after you read something.

### The same from a terminal

```toml
[sync]
url = "https://sync.example.org"   # or folder = "~/Sync/fedtail"
```

```sh
fedtail sync login              # log in to the sync server (the code from the page)
fedtail sync now                # a round now; on the first device it makes the key too
fedtail sync key                # show the key: XXXX-XXXX-…
fedtail sync join XXXX-XXXX-…   # take the key on another device
fedtail sync keep               # put the key into the journal under a password (asked twice)
fedtail sync unlock             # take the key out of the journal by its password
fedtail sync status             # where, the key's id, what waits to go, how last time went
```

## Running a fedtail-sync server

The server is a project of its own, with its own page: [fedtail-syncserver](https://github.com/eugene-vereshchagin/fedtail-syncserver#readme)
— installing it (one file, Python 3.11+, SQLite), the config, a systemd unit, putting it
behind Cloudflare Tunnel, nginx or Caddy, how it guards itself, and serving people of
other servers. What it speaks is in [`PROTOCOL.md`](https://github.com/eugene-vereshchagin/fedtail-syncserver/blob/main/PROTOCOL.md).

## Not yet

* WebDAV spoken directly (now: mounted as a folder).
* Packing old journals into a snapshot (now: they just add up, within the quota).
