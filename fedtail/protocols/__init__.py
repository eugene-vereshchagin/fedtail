"""Protocols fedtail speaks. Each one lives in its own package here and turns its
server's objects into fedtail.model; nothing outside this folder reads a server's JSON
(docs/PROTOCOLS.md). Today there is one: ``mastodon`` — the Mastodon client API, which
GoToSocial, Akkoma, Pleroma and Mastodon itself all serve."""
