# fedtail-sync changelog

The server is versioned apart from fedtail; the protocol number (`GET /v1`,
[PROTOCOL.md](PROTOCOL.md)) changes only when a client would have to.

## 1.0.0 — in progress

The first version on its own (until now it came inside fedtail, with fedtail's numbers).

- Protocol 1: store, fetch and delete an account's sealed blobs; who is who asked of each
  account's own fediverse server with a `read:accounts` token.
- No more `/.well-known/fedtail-sync`: the server is a service of its own, and a client
  takes its address from its config. `public_url` is ignored with a warning.
- Guards itself — it faces the internet: `timeout_seconds` for a silent connection (a whole
  request within twice that), `max_connections`, `requests_per_minute_per_ip`, token checks
  capped per address and in all (`verifications_per_minute_per_ip`,
  `verifications_per_minute`), an honest `Content-Length` required, `total_mb` for the
  disk, no redirects and (with `"*"`) public peers only for the token check, a plain
  "internal error" for anything broken inside. `client_ip_header` for a proxy on the same
  machine (`CF-Connecting-IP`, `X-Real-IP`), believed from loopback only.
- `--version`; its own tests (`tests/`, the standard library only) at 100 % of lines
  (`tools/coverage.py --fail-under 100`), bandit, in a CI job a release waits for.
