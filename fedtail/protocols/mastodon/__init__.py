"""The Mastodon client API (GoToSocial, Mastodon, Akkoma, Pleroma, glitch-soc)."""

PROTO = "mastodon"


def _tune(slow_seconds=None):
    """The client's own settings: how long a request may take before it is logged slow."""
    from . import api
    if slow_seconds is not None:
        api.SLOW_SECONDS = float(slow_seconds)


def protocol():
    """This protocol for the core (fedtail.protocols.base.Protocol)."""
    from types import SimpleNamespace

    from ..base import Protocol
    from . import adapter, api, counters, probe, stream
    urls = SimpleNamespace(search=api.search_url, lookup=api.lookup_url,
                           statuses=api.statuses_url, public=api.public_url, tag=api.tag_url)
    return Protocol(PROTO, api.Api, api.ApiError, api.capabilities_from_instance, adapter,
                    stream, address=api.server_address, tune=_tune, probe=probe,
                    counters=counters, urls=urls)
