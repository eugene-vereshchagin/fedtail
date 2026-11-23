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
  // notify.privacy (the server writes PRIVACY above this file): "sender" — who, not
  // what; "count" — neither, as every window's notifications
  const privacy = typeof PRIVACY === "string" ? PRIVACY : "full";
  const title = privacy === "count" ? "fedtail" : String(n.title || "fedtail");
  const options = {
    body: privacy === "full" ? String(n.body || "") : "",
    // their face says who: not with "count"
    icon: privacy !== "count" && typeof n.icon === "string" && n.icon.startsWith("https://")
      ? n.icon : undefined,
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

// A press on the note: the page, at the lane its kind of event is read in — as a press
// on a window's note goes to its lane (it only opened "/", 23.11). Which lane, the
// server says (/api/push_lane: the core's rule); it not answering — the page as it is.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const type = (event.notification.data && event.notification.data.type) || "";
  const lane = fetch("/api/push_lane?type=" + encodeURIComponent(type), { credentials: "same-origin" })
    .then((r) => (r.ok ? r.json() : {})).then((got) => String(got.lane || "")).catch(() => "");
  event.waitUntil(Promise.all([
    lane, self.clients.matchAll({ type: "window", includeUncontrolled: true }),
  ]).then(([name, pages]) => {
    const page = pages.find((p) => new URL(p.url).origin === self.location.origin);
    if (page) {
      if (name) page.postMessage({ lane: name });
      return page.focus();
    }
    return self.clients.openWindow(name ? "/#" + encodeURIComponent(name) : "/");
  }));
});
