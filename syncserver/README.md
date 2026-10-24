# fedtail-sync

[По-русски](README.ru.md)

The meeting point of one fediverse account's devices for
[fedtail](https://github.com/eugene-vereshchagin/fedtail): every device sends it a sealed
journal — read marks, threads followed or muted, lanes, drafts — and picks up the others'.
It can't read them: they are encrypted (AES-256-GCM) with a key only the devices have. All
it learns is whose they are, how big and when.

Whose: a device sends a token of its fediverse account limited to `read:accounts` (all it
allows is "who am I") and names its server; fedtail-sync asks that server who the token
belongs to and files the journal under the answer. No accounts or passwords of its own.

One file, the Python standard library only (3.11+), SQLite. Version 1.0.0, protocol 1
([PROTOCOL.md](PROTOCOL.md)); changes — [CHANGELOG.md](CHANGELOG.md). License GPL-3.0-or-later.

```sh
python3 fedtail_sync.py --version
python3 fedtail_sync.py --config /srv/fedtail-sync/config.toml
```

## Installing


It is one file of the standard library: [`fedtail_sync.py`](fedtail_sync.py)
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
total_mb = 1024               # all accounts together; 0 — no cap
timeout_seconds = 30          # a silent connection is dropped (a whole request: twice that)
max_connections = 64          # served at once; more are closed at the door
requests_per_minute_per_ip = 240
verifications_per_minute_per_ip = 10   # token checks at a fediverse server, per address
verifications_per_minute = 60          # ... in all
client_ip_header = "CF-Connecting-IP"  # behind cloudflared/nginx on this machine; "" — none
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

## How it guards itself

It faces the internet, so every limit is on by default (the values above are the
defaults, but for `client_ip_header`):

| what someone might try | what stops it |
|---|---|
| open connections and stay silent, or trickle a byte now and then | dropped after `timeout_seconds` of silence; a whole request gets twice that |
| open thousands of connections | `max_connections` at once; the rest are closed at the door |
| flood it with requests | `requests_per_minute_per_ip` per address, `requests_per_minute` per account |
| send random tokens so that it hammers someone's fediverse server with checks | a known token is believed for 10 minutes, a refused one is refused for a minute; real checks are capped per address and in all (`verifications_per_minute_per_ip`, `verifications_per_minute`) |
| a lying or missing `Content-Length`, a chunked body | refused before reading (411, 400, 413); a body shorter than promised doesn't hold a thread |
| fill the disk | `quota_mb` per account and `total_mb` for everyone (with `"*"` anyone with a server of their own could make accounts) |
| make it call into your LAN (with `"*"`) | only public addresses, checked on the connected socket — a name that changes its address between the check and the call is caught; no redirect is followed, so the token goes nowhere else |
| make it show its insides | an error inside answers "internal error"; the details go to its log |

**Behind a proxy on the same machine** — cloudflared, nginx, Caddy — every request comes
from 127.0.0.1, and the per-address limits would treat the whole world as one client. Set
`client_ip_header` to the header that proxy puts the real address in: `CF-Connecting-IP`
for Cloudflare, `X-Real-IP` for nginx with `proxy_set_header X-Real-IP $remote_addr;`. It
is believed only from a loopback peer, and only if it holds an address — a client can't
fake its way around the limit. Listening on anything but 127.0.0.1 makes it warn at start:
it speaks plain HTTP.

The tests of each of these are in [`tests/test_security.py`](tests/test_security.py); CI runs
them, with bandit, on every push, and a release can't go out without them.

What the server keeps: per account (its id on its server), sealed blobs with the sending
device's random id and a time. What it logs: one line per request — the address, the
path, the answer — never a token. `DELETE /v1/blobs` with the account's token removes its
whole journal.

## Serving people of other servers

`instances = ["*"]` serves anyone whose server answers the token check (public addresses
only: nothing in your LAN is ever asked). The journals are sealed, so it costs you disk
and traffic, not privacy; the quota and the request limit keep that small. A beta tester
of yours on another server puts the same `url = "https://sync.your.domain"` in their
config.


## Tests

```sh
python3 -m unittest discover -s tests -t .      # from this folder; the standard library only
python3 tools/coverage.py --fail-under 100      # line coverage (Python 3.12+), must stay 100 %
```

`tests/test_server.py` — the journal, limits, the token check, old journals, the config and
the program; `tests/test_security.py` — every way to hang, flood or fill it, or turn it
against someone. Report a vulnerability privately: [SECURITY](https://github.com/eugene-vereshchagin/fedtail/security/advisories/new).
