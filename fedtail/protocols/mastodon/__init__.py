"""The Mastodon client API (GoToSocial, Mastodon, Akkoma, Pleroma, glitch-soc)."""

PROTO = "mastodon"


def protocol():
    """This protocol for the core (fedtail.protocols.base.Protocol)."""
    from ..base import Protocol
    from . import adapter, api, stream
    return Protocol(PROTO, api.Api, api.ApiError, api.capabilities_from_instance, adapter,
                    stream)
