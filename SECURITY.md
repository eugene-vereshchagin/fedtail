# Security

Please report vulnerabilities **privately**, through GitHub:
[Report a vulnerability](https://github.com/eugene-vereshchagin/fedtail/security/advisories/new)
(the Security tab of the repository). Don't open a public issue for them.

What fedtail promises, so you know what counts as a hole:

* The access token lives only in `auth.json` in the profile's data folder (mode 0600 on Linux)
  and is sent only to your own server. It never goes into logs, bug reports or requests to
  other servers.
* Requests to other servers (honest counters, filling in threads, pictures) carry no token —
  only your IP address shows. They go to public addresses only (never this computer or the
  local network, your own server excepted), every redirect checked, every answer size-capped.
* Logging out revokes the token on the server as well as deleting it here.
* Post HTML is rebuilt from an allow-list before display; no browser engine, no scripts. A post
  can't hold a link that acts on your behalf (deleting, boosting, following), and nothing from
  a post or another server opens a local file or a network share: fedtail hands the desktop
  only web addresses (and mail, XMPP, Gemini, magnet links). Someone else's text — names, alt
  text, content warnings, notifications — is shown as text, never as markup.
* Logs hold API paths, ids, timings and errors — not post texts. `--bug-report` leaves out the
  token and the database.

* fedtail-sync, the sync server (`syncserver/`), never sees what you read: journals are
  sealed with a key only your devices have. It can't be made to hang, to flood a fediverse
  server with token checks, to fill its disk past its caps, or to call into its own network
  (docs/en/sync.md, "How it guards itself").

A way to break any of these is a security issue. Supported versions: the latest release.
