# Sync between your devices

[По-русски](/docs/ru/sync.md)

fedtail on the desktop, on a laptop, later on a phone — one account, one set of read
marks. Read a post on one, it is read on the others; follow a thread, leave it or mute
it, and so it is everywhere.

What travels (`sync.what`):

| what | what it means | how two devices agree |
|---|---|---|
| `read` | read marks **you** made: scrolling, opening, "mark read" | a mark is never taken back, so they simply add up |
| `threads` | a thread you followed, left or muted by hand | the newest setting wins |

What stays on each device: the marks fedtail makes by itself (everything read on the
first run, older history, your own posts), automatic subscriptions to your own posts
(every device makes them), the posts themselves, the config. So a new phone won't mark
the desktop's unread lanes read.

Short post names (`#kq3zt`) are the same on every device without any of this: they are
derived from the post's id.

## How it works

Every device keeps a journal of what it did and sends it, sealed, to a place all your
devices reach; there it picks up the others' journals. The place is either

* a **fedtail-sync server** — one small program, usually next to your fediverse server; or
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

In every device's config:

```toml
[sync]
enabled = true
backend = "server"   # or "folder"
url = ""             # empty: the server your fediverse server names; or https://…
folder = ""          # for backend = "folder"
```

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
few seconds after you read something; a problem shows once in the status bar and stays
in `fedtail sync status`.

A device without the key that finds someone's journal already there doesn't make a key
of its own: it asks for `fedtail sync join`.

## Running a fedtail-sync server

It is one file of the standard library: [`syncserver/fedtail_sync.py`](/syncserver/fedtail_sync.py)
(Python 3.11+, SQLite). Copy it to the server, nothing else of fedtail is needed there.

`/etc/fedtail-sync.toml`:

```toml
listen = "127.0.0.1:8471"
db = "/srv/fedtail-sync/sync.db"
instances = ["your.server"]   # whose people are served; ["*"] — anyone's (public servers only)
public_url = "https://your.server/fedtail-sync"   # how devices reach it (for the well-known)
quota_mb = 20                 # per account; a year of reading is a few MB
max_blob_kb = 512
requests_per_minute = 120     # per account
keep_days = 0                 # 0: kept until the account deletes its journal
```

A systemd unit, `/etc/systemd/system/fedtail-sync.service`:

```ini
[Unit]
Description=fedtail-sync
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 /srv/fedtail-sync/fedtail_sync.py --config /etc/fedtail-sync.toml
User=fedtail-sync
StateDirectory=fedtail-sync
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/srv/fedtail-sync
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

It speaks plain HTTP on localhost: put it behind the web server that already does TLS for
your fediverse server. nginx, inside the server's `server { … }`:

```nginx
location /fedtail-sync/ {
    proxy_pass http://127.0.0.1:8471/;
    client_max_body_size 1m;
}
# fedtail finds the sync server by itself through this
location = /.well-known/fedtail-sync {
    proxy_pass http://127.0.0.1:8471/.well-known/fedtail-sync;
}
```

Caddy:

```
handle_path /fedtail-sync/* {
    reverse_proxy 127.0.0.1:8471
}
handle /.well-known/fedtail-sync {
    reverse_proxy 127.0.0.1:8471
}
```

With the well-known in place, your people need only `enabled = true` and
`fedtail sync login`: the address comes by itself.

What the server keeps: per account (its id on its server), sealed blobs with the sending
device's random id and a time. What it logs: one line per request — the address, the
path, the answer — never a token. `DELETE /v1/blobs` with the account's token removes its
whole journal.

### Serving people of other servers

`instances = ["*"]` serves anyone whose server answers the token check (public addresses
only: nothing in your LAN is ever asked). The journals are sealed, so it costs you disk
and traffic, not privacy; the quota and the request limit keep that small. A beta tester
of yours on another server just puts `url = "https://your.server/fedtail-sync"` in their
config.

## Not yet

* Carrying the key with a QR code from the window (now: `fedtail sync key` / `join`).
* Drafts started on one device, finished on another.
* WebDAV spoken directly (now: mounted as a folder).
* Packing old journals into a snapshot (now: they just add up, within the quota).
