# Sync between your devices

[По-русски](/docs/ru/sync.md)

fedtail on the desktop, on a laptop, later on a phone — one account, one set of read
marks. Read a post on one, it is read on the others; follow a thread, leave it or mute
it, move a list up the sidebar — and so it is everywhere.

Sync is a **service of its own**, apart from your fediverse server: fedtail syncs only
when you tell it where (`sync.url` or `sync.folder`). Without that there is no sync —
the status bar says "⇅ off", About says why.

What travels (`sync.what`):

| what | what it means | how two devices agree |
|---|---|---|
| `read` | read marks **you** made: scrolling, opening, "mark read" | a mark is never taken back, so they simply add up |
| `threads` | a thread you followed, left or muted by hand | the newest setting wins |
| `lanes` | your lanes as you arranged them: the order of lists (servers keep none, so every device would show them as they came) and the tag lanes you saved | the newest arrangement wins |

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

It is one file of the standard library: [`syncserver/fedtail_sync.py`](/syncserver/fedtail_sync.py)
(Python 3.11+, SQLite). Copy it to the server, nothing else of fedtail is needed there.

A folder of its own, say `/srv/fedtail-sync/`, with the file, its config and its
database; a system user for it:

```sh
sudo useradd --system --no-create-home --shell /usr/sbin/nologin fedtail-sync
sudo mkdir -p /srv/fedtail-sync
sudo cp fedtail_sync.py /srv/fedtail-sync/
sudo chown -R fedtail-sync: /srv/fedtail-sync
```

`/srv/fedtail-sync/config.toml`:

```toml
listen = "127.0.0.1:8471"
db = "/srv/fedtail-sync/sync.db"
instances = ["your.server"]   # whose people are served; ["*"] — anyone's (public servers only)
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
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 /srv/fedtail-sync/fedtail_sync.py --config /srv/fedtail-sync/config.toml
User=fedtail-sync
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/srv/fedtail-sync
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload && sudo systemctl enable --now fedtail-sync
curl -s http://127.0.0.1:8471/v1        # {"fedtail-sync": 1}
```

It speaks plain HTTP on localhost; TLS is done in front of it, on a name of its own
(say `sync.your.domain`) — the fediverse server is left alone.

**Cloudflare Tunnel** (the tunnel run from the dashboard): Zero Trust → Networks →
Tunnels → your tunnel → Published application routes (Public Hostname) → add one:
subdomain `sync`, your domain, path empty, service `http://127.0.0.1:8471`. `http`, not
`https` (Cloudflare does TLS), and `127.0.0.1`, not `localhost` (that may go to IPv6,
where the server doesn't listen). The DNS record is made by itself. With the tunnel in a
config file, the same as an ingress rule:

```yaml
  - hostname: sync.your.domain
    service: http://127.0.0.1:8471
```

**nginx**, a `server { … }` of its own:

```nginx
server {
    server_name sync.your.domain;
    # listen / ssl_certificate as for your other sites
    location / {
        proxy_pass http://127.0.0.1:8471;
        client_max_body_size 1m;
    }
}
```

**Caddy**:

```
sync.your.domain {
    reverse_proxy 127.0.0.1:8471
}
```

Check from outside: `curl -s https://sync.your.domain/v1` → `{"fedtail-sync": 1}`. Your
people put that address in `sync.url` and run `fedtail sync login`.

What the server keeps: per account (its id on its server), sealed blobs with the sending
device's random id and a time. What it logs: one line per request — the address, the
path, the answer — never a token. `DELETE /v1/blobs` with the account's token removes its
whole journal.

### Serving people of other servers

`instances = ["*"]` serves anyone whose server answers the token check (public addresses
only: nothing in your LAN is ever asked). The journals are sealed, so it costs you disk
and traffic, not privacy; the quota and the request limit keep that small. A beta tester
of yours on another server puts the same `url = "https://sync.your.domain"` in their
config.

## Not yet

* Carrying the key with a QR code from the window (now: `fedtail sync key` / `join`).
* Drafts started on one device, finished on another.
* WebDAV spoken directly (now: mounted as a folder).
* Packing old journals into a snapshot (now: they just add up, within the quota).
