"""The protocol this core speaks — its one door into fedtail/protocols/ (docs/en/dev/
protocols.md, stage 3). Nothing else in the core imports a protocol's modules: the
client, its error, the model adapter, the probe, the counters, the addresses of other
servers' pages all come through here, from the registry (protocols.get). Today that is
Mastodon's client API, which every server fedtail speaks to serves."""

from .. import protocols
from ..protocols.base import Capabilities, RateLimited, ServerError  # noqa: F401 — the core's

PROTO = protocols.get()
Error = PROTO.error          # what the client raises for an error answer
adapter = PROTO.adapter      # the server's objects → fedtail.model
probe = PROTO.probe          # "what can the server do"
counters = PROTO.counters    # a post's honest counts from its own server
urls = PROTO.urls            # other servers' public pages
address = PROTO.address      # what a person typed → the server's URL
