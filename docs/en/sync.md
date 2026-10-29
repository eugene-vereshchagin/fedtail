# Sync between your devices

[По-русски](/docs/ru/sync.md)

fedtail on the desktop, on a laptop, later on a phone — one account, one set of read
marks. Read a post on one, it is read on the others; follow a thread, leave it or mute
it, move a list up the sidebar — and so it is everywhere.

Sync is a **service of its own**, apart from your fediverse server: fedtail syncs only
when you tell it where (`sync.url`, `sync.folder` or `sync.webdav`). Without that there is no sync —
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
* a **folder** every device sees — a NAS share, a Syncthing folder; or
* a **WebDAV folder** — Nextcloud, ownCloud, a NAS — spoken to directly, nothing mounted
  (`sync.webdav`, `sync.webdav_user`; the password is asked once and kept in the profile's
  data folder, readable by you only, never in the config). The same files as in a folder.

A journal only grows, so every device packs its own now and then: once what it has sent
is past a megabyte and several times what a snapshot of it would be, it sends the
snapshot — every setting with the time and the device it came from, the read marks of
the newest 5000 posts kept, how far events are seen, what was dismissed — and drops its
older files (a folder, WebDAV) or blobs (a fedtail-sync server of 0.22 and later). A
device away for a while reads the snapshot instead: the same state, but for read marks of
posts older than those.

The journals are encrypted (AES-256-GCM) with a key only your devices have. The server
or the folder sees opaque blobs: who sent them, how big, when — not what you read, not
which threads. Losing every device with the key loses only the read marks: they can't
be recovered, and they aren't worth much.

On a sync server the journal is **the key's**: fedtail derives from the key a journal id
and a secret (the key itself never goes there), so whoever has the key has the journal — no
login, no accounts, your fediverse server isn't asked anything. A journal is made only with
an **invite code** the server's admin gives (one per person, and taken back when they
want — the journals made with it go with it). Only the first device needs it.

## Turning it on

All of it is in the window: **≡ → Sync** (or a click on "⇅" in the status bar). On top —
three steps marked ✓ (done), ▶ (now) and · (later); below — only what the current step
needs. The same in the Qt window, GTK, the terminal, the web page and the phone.

1. **Where the devices meet** — the sync server's address your admin gave you
   (`https://sync.example.org`), a folder all your devices see (`~/Sync/fedtail`), or a
   WebDAV folder (`https://cloud.example.org/remote.php/dav/files/me/fedtail` — made if
   it isn't there). "Next" writes it into config.toml (`sync.url` / `sync.folder` /
   `sync.webdav`) and turns sync on at once, no restart. With a server — also the **invite
   code** its admin gave you (the first device only; kept in the data folder, not the
   config).
2. **Login** — to a WebDAV folder only: its user and password (with Nextcloud, better an
   app password: Settings → Security), checked there at once. A sync server and a folder
   need none.
3. **The key** — a fork, what this device is:
   * **"This is my first device"** — sync isn't set up anywhere yet: the key is made
     here, and this device starts the journal (on a server — with the invite code). If a
     folder holds someone's journal already, fedtail says so and offers the other way.
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
key. Forgot it — nothing breaks: the key can always be copied from a working device. At
least 10 characters; a phrase of a few words is best. On a sync server the key is kept
under an id made of the password *and your fediverse account* (a new device logs into it
anyway) — so a guess tests only you, and two people with one password never meet; the
server keeps no one's key in another's place.

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
url = "https://sync.example.org"   # or folder = "~/Sync/fedtail",
                                   # or webdav = "https://…" with webdav_user = "me"
```

```sh
fedtail sync invite CODE        # the server's invite code (the first device only)
fedtail sync first              # this is the first device: the key made here
fedtail sync login              # WebDAV only: the user (or webdav_user), the password asked
fedtail sync now                # a round now (a folder: on the first device it makes the key)
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

Nothing of what was planned: WebDAV is spoken directly and the journals are packed since
0.22.
