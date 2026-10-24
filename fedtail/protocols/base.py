"""What a protocol gives the core (docs/en/dev/protocols.md, stage 3).

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

import time
from dataclasses import dataclass, field
from typing import Any


class ServerError(Exception):
    """A server's answer that is an error, whatever the protocol: status as in HTTP
    (404, 405, 410, 501 — no such thing here; 401, 403 — not for me)."""

    def __init__(self, status, message):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


class RateLimited(ServerError):
    """The server asks to wait: too many requests (HTTP 429), until `until` (a unix time).
    Also raised without asking it, while its budget is spent (the client knows)."""

    def __init__(self, message, until):
        super().__init__(429, message)
        self.until = until


@dataclass
class Budget:
    """What the server allows: requests per window, how many are left, when it starts
    anew (unix time); as its last answer said. limit 0: it doesn't say."""
    limit: int = 0
    remaining: int = 0
    reset: float = 0.0

    def spent(self, now=None):
        """Nothing left and the window still on: asking now only earns a 429."""
        now = time.time() if now is None else now
        return bool(self.limit) and self.remaining <= 0 and now < self.reset

    def low(self, reserve, now=None):
        """Fewer left than reserve (a poll round's worth and some), the window on."""
        now = time.time() if now is None else now
        return bool(self.limit) and self.remaining < reserve and now < self.reset

# every method of the client the core calls (self.api.<name>, api.<name>); and its
# attribute ``base``, the server's address
CLIENT = frozenset("""
    account account_statuses announcements answer_interaction answer_notification_request
    async_refresh authorize_follow authorize_url block block_domain blocks bookmark
    bookmarks cancel_scheduled clear_notifications context conversations create_filter
    create_list custom_emojis delete_filter delete_list delete_status directory
    dismiss_announcement dismiss_notification dismiss_notification_group
    dismiss_suggestion domain_blocks
    edit_status endorse endorsements familiar_followers favourite favourited_by
    favourites feature_tag featured_tags federated filters follow follow_options
    follow_requests follow_tag followed_tags followers following get_token home
    instance instance_page instance_rules interaction_requests list_accounts list_add
    list_remove list_timeline lists local markers me mentions mute mute_conversation
    mutes my_featured_tags notification_groups notification_policy notification_requests
    notifications
    notify_posts pin pinned poll post_status preferences quotes react_announcement
    read_conversation reblog reblogged_by register_app reject_follow relationship
    relationships remove_from_followers report revoke_quote scheduled search set_markers
    set_note set_notification_policy status status_history status_source suggestions
    instance_v2 tag tag_timeline translate trends unfeature_tag update_credentials update_list
    upload_media verify_credentials vote base
""".split())


# what is known of a server without asking it: (software, feature) -> there or not
KNOWN = {
    ("gotosocial", "dismiss_one"): False,   # it clears all notifications, never one
    ("gotosocial", "grouped"): False,       # no /api/v2/notifications (asking: a 404)
    ("gotosocial", "domain_blocks"): False,  # a user's own server blocks: admins only
}


@dataclass
class Capabilities:
    """What my server can do — one place for it (docs/en/dev/protocols.md, stage 4).

    What the server says about itself (software, version, the limits) comes with the
    connection; whether it has a feature is learned: a probe's answers (≡ → Server info
    → What it can do), an answer "no such thing here" to a call (Core._api), and what is
    known of its software (KNOWN). has(feature) is True until one of them says no — a
    button is offered, and goes once the server refuses it.

    Feature names are short words the core uses: "conversations", "dismiss",
    "dismiss_one", "mute_thread", "trends_tags", "quotes"…"""
    software: str = ""
    version: str = ""  # what the server says it runs ("4.3.0", "0.17.3 git-…")
    software_sure: bool = False  # False: software is a guess (the core asks nodeinfo)
    max_characters: int = 500
    max_media: int = 4
    markdown: bool = False
    max_poll_options: int = 4
    translation: bool = False
    streaming: str = ""  # wss://… of the live stream, "" — not said
    image_bytes: int = 0   # the largest picture the server takes, bytes (0 — not said)
    image_pixels: int = 0  # …and in pixels, width × height
    missing: set = field(default_factory=set)  # the server said no
    present: set = field(default_factory=set)  # the server said yes (a probe)

    def has(self, feature):
        if feature in self.missing:
            return False
        if feature in self.present:
            return True
        return KNOWN.get(((self.software or "").lower(), feature), True)

    def learn(self, feature, there):
        """The server answered for a feature. True: that changed what has() says."""
        before = self.has(feature)
        (self.present if there else self.missing).add(feature)
        (self.missing if there else self.present).discard(feature)
        return self.has(feature) != before

    def same_server(self, software, version):
        return (software or "") == self.software and (version or "") == self.version


@dataclass(frozen=True)
class Protocol:
    name: str
    client: type
    error: type
    capabilities: Any   # (instance dict) -> Capabilities
    adapter: Any        # module: the server's objects -> fedtail.model
    stream: Any = None  # module with the live stream, or None
