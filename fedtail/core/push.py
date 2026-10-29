"""Web Push: the web page's browser subscribes at my server itself (the server pushes to
it); fedtail only hands over the key and the subscription."""

import logging

from .proto import Error as ApiError  # the protocol's error answer (core/proto.py)

log = logging.getLogger("fedtail.core.app")  # the Core's log: one name for all its parts


class PushMixin:
    """A part of Core (core/app.py): see the module's words."""

    def vapid_key(self):
        """The server's public key a browser's push subscription is made with ("" —
        the server has no Web Push)."""
        def job():
            v2 = self.api.instance_v2() or {}
            key = ((v2.get("configuration") or {}).get("vapid") or {}).get("public_key")
            return str(key or "")
        return self.submit(job)

    # what a push subscription is told about: everything the activity shows
    PUSH_ALERTS = {"mention": True, "status": True, "reblog": True, "follow": True,
                   "follow_request": True, "favourite": True, "poll": True, "update": True}

    def push_subscribe(self, endpoint, p256dh, auth, alerts=None, policy="all"):
        return self.call_api("push_subscribe", endpoint, p256dh, auth,
                             alerts or self.PUSH_ALERTS, policy)

    def push_subscription(self):
        def job():
            try:
                return self.api.push_subscription()
            except ApiError as e:
                if e.status == 404:  # none yet
                    return None
                raise
        return self.submit(job)

    def push_unsubscribe(self):
        return self.call_api("push_unsubscribe")
