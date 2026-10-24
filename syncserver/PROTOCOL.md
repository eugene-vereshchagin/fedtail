# fedtail-sync protocol 1

What a client (fedtail, or anything else) and a fedtail-sync server say to each other.
The server is a dumb store of opaque blobs per account; everything about what a blob means
belongs to the clients. This page is the contract between the two: either side may change
anything else, but not this without a new protocol number.

## Transport

HTTPS (the server itself speaks plain HTTP on localhost behind a proxy that does TLS).
JSON answers, `Content-Type: application/json`, `Cache-Control: no-store`. One request per
connection (HTTP/1.0 answers). Every error is `{"error": "words for a person"}` with the
status below; a client goes by the status, never by the words.

## Who is asking

Every call but `GET /v1` carries:

| header | what |
|---|---|
| `Authorization: Bearer <token>` | a token of the account on its own fediverse server, scope `read:accounts` only (never the client's main token); at most 512 characters |
| `X-Fedtail-Instance: https://<host>` | that server (`https://host`, `host` or `host:port`; nothing after the host) |

The server asks `https://<host>/api/v1/accounts/verify_credentials` with the token (no
redirects followed) and files everything under `<id>@<host>`. It believes a verified token
for 10 minutes and remembers a refused one for a minute. Which hosts it serves is its
config (`instances`; `"*"` — any public address).

## Calls

### `GET /v1`

`200 {"fedtail-sync": 1}` — the protocol number. No token needed. A client that finds
another number should go no further.

### `POST /v1/blobs`

The body is one blob, raw bytes, with an exact `Content-Length` (no chunked bodies). Header
`X-Fedtail-Device`: the sending device's id, `[A-Za-z0-9_-]{0,32}` (fedtail: 16 random hex
digits).

`200 {"seq": n}` — its place in the account's journal: a number that only grows, shared by
all the account's devices.

### `GET /v1/blobs?after=N&limit=M&exclude=DEVICE`

The account's blobs with `seq > N` (default 0), oldest first, at most `M` (default 200,
1…500), leaving out those `DEVICE` sent (same pattern as the header; empty — leave none).
`N` and `M` are decimal, at most 19 digits.

```json
{"blobs": [{"seq": 7, "device": "3f2a…", "data": "<base64>"}],
 "last": 9, "more": false}
```

`last` — the cursor for the next call: the last `seq` looked at, the left-out ones
included (so a device never asks for its own again); `N` itself when nothing came. `more`
— there are more past `last`.

### `DELETE /v1/blobs`

The whole journal of the account gone. `200 {"deleted": n}`.

## Statuses

| status | when | what a client does |
|---|---|---|
| 200 | done | — |
| 400 | a bad number, device id, query, empty blob, a body shorter than its length | a bug: report it |
| 401 | no token, the instance header missing or odd, the token refused by its server | log in again (`fedtail sync login`) |
| 403 | the instance isn't served here | another sync server |
| 404 | no such path | not a fedtail-sync |
| 411 | no `Content-Length`, or a chunked body | send the length |
| 413 | the blob is over the server's `max_blob_kb` | smaller batches |
| 429 | too many requests (per address, per account) or token checks | try again in a minute |
| 501 | another method | — |
| 502 | the fediverse server didn't answer the token check sensibly | try again later |
| 507 | over the account's quota, or the server is full | delete the journal, or another server |
| 500 | something broke inside the server (it is in its log) | try again later |

## Blobs

The server never looks inside. fedtail's blobs, for anyone writing another client:

    blob = b"FTS1" | key id (8) | nonce (12) | AES-256-GCM(zlib(json)) — the first 12 bytes as AAD

The key is 32 random bytes the account's first device makes and the others are given by
hand; the key id is 8 bytes of a hash of it (a blob sealed by another key is told at once).
The JSON is `{"v": 1, "d": device, "at": ms, "ops": [...]}`; what the ops are is fedtail's
business (`fedtail/core/sync/engine.py`) and may grow without a new protocol number.
