// fedtail's web page: Web Push. The browser subscribed at the user's own server (the
// page handed the subscription to fedtail, fedtail to the server); the server encrypts
// each notification for this browser and sends it through the browser's push service.
// Here it is shown — even with the page closed and fedtail not running.
"use strict";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let n = {};
  try { n = event.data ? event.data.json() : {}; } catch (e) { n = {}; }
  // Mastodon's payload: title, body, icon, notification_id, notification_type, and the
  // access token, which stays here unused
  const title = String(n.title || "fedtail");
  const options = {
    body: String(n.body || ""),
    icon: typeof n.icon === "string" && n.icon.startsWith("https://") ? n.icon : undefined,
    tag: "fedtail-" + String(n.notification_id || Date.now()),
    data: { type: String(n.notification_type || "") },
  };
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true })
    .then((pages) => {
      // the page open and looked at shows its own notifications (with the post's lane):
      // not twice
      if (pages.some((p) => p.focused && p.visibilityState === "visible")) return undefined;
      return self.registration.showNotification(title, options);
    }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true })
    .then((pages) => {
      const page = pages.find((p) => new URL(p.url).origin === self.location.origin);
      if (page) return page.focus();
      return self.clients.openWindow("/");
    }));
});
