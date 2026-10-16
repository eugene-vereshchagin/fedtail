# Security

Please report vulnerabilities **privately**, through GitHub:
[Report a vulnerability](https://github.com/eugene-vereshchagin/fedtail/security/advisories/new)
(the Security tab of the repository). Don't open a public issue for them.

What fedtail promises, so you know what counts as a hole:

* The access token lives only in `auth.json` in the profile's data folder (mode 0600 on Linux)
  and is sent only to your own server. It never goes into logs, bug reports or requests to
  other servers.
* Requests to other servers (honest counters, filling in threads, pictures) carry no token —
  only your IP address shows.
* Post HTML is rebuilt from an allow-list before display; no browser engine, no scripts. A post
  can't hold a link that acts on your behalf (deleting, boosting, following).
* Logs hold API paths, ids, timings and errors — not post texts. `--bug-report` leaves out the
  token and the database.

A way to break any of these is a security issue. Supported versions: the latest release.
