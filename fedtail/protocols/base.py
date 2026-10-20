"""What a protocol gives the core (docs/PROTOCOLS.md, stage 3).

A protocol is a package under ``fedtail/protocols/`` that exposes a ``PROTOCOL``:

* ``client`` — the class the core talks to the server through: ``client(server)`` before
  login, ``client(server, token)`` after; its methods are the ones in ``CLIENT``, named
  as the core calls them. A new protocol implements these (those it can't, raise
  ``NotSupported`` and the core hides the feature).
* ``error`` — the exception its client raises for an answer that is an error; it has a
  ``status`` (HTTP or alike: 404, 405, 410, 501 mean "no such thing here").
* ``capabilities(instance)`` — what the server says about itself → ``Capabilities``.
* ``adapter`` — the server's objects → ``fedtail.model`` (``post``, ``account``, …).
* ``stream`` — a live stream class, or None.

The core still keeps a server's raw objects in its store and reads some of their fields
(that is the Mastodon dialect every server of today speaks); what reaches the frontends
is the model only (core/view.py). ``tests/test_protocols.py`` keeps the API itself
inside ``protocols/``: no ``/api/v…`` path in the code anywhere else, and the core calls
only methods listed here.
"""

from dataclasses import dataclass
from typing import Any


class ServerError(Exception):
    """A server's answer that is an error, whatever the protocol: status as in HTTP
    (404, 405, 410, 501 — no such thing here; 401, 403 — not for me)."""

    def __init__(self, status, message):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status

# every method of the client the core calls (self.api.<name>, api.<name>); and its
# attribute ``base``, the server's address
CLIENT = frozenset("""
    account account_statuses announcements answer_interaction answer_notification_request
    async_refresh authorize_follow authorize_url block block_domain blocks bookmark
    bookmarks cancel_scheduled clear_notifications context conversations create_filter
    create_list custom_emojis delete_filter delete_list delete_status directory
    dismiss_announcement dismiss_notification dismiss_suggestion domain_blocks
    edit_status endorse endorsements familiar_followers favourite favourited_by
    favourites feature_tag featured_tags federated filters follow follow_options
    follow_requests follow_tag followed_tags followers following get_token home
    instance instance_page instance_rules interaction_requests list_accounts list_add
    list_remove list_timeline lists local markers me mentions mute mute_conversation
    mutes my_featured_tags notification_policy notification_requests notifications
    notify_posts pin pinned poll post_status preferences quotes react_announcement
    read_conversation reblog reblogged_by register_app reject_follow relationship
    relationships remove_from_followers report revoke_quote scheduled search set_markers
    set_note set_notification_policy status status_history status_source suggestions
    tag tag_timeline translate trends unfeature_tag update_credentials update_list
    upload_media verify_credentials vote base
""".split())


@dataclass(frozen=True)
class Protocol:
    name: str
    client: type
    error: type
    capabilities: Any   # (instance dict) -> Capabilities
    adapter: Any        # module: the server's objects -> fedtail.model
    stream: Any = None  # module with the live stream, or None
