# Notifications

What fedtail tells you about, how and when.

## Desktop notifications

By default — about direct messages, replies to you, mentions, subscriptions, activity and
follow requests. About the lane in front of your eyes fedtail keeps quiet.

- What to notify about — `notify.lanes` (`["all"]` — everything), what never — `notify.except`.
- What to show — `notify.privacy`: who and what, only who, or only how many (handy with others
  around).
- Nothing comes? ≡ → "Debugging" → "Send a test notification".

## Push in the web version

The web page (`fedtail --web`) shows the browser's notifications while it is open. ≡ → “Push
notifications…” — and the browser subscribes to them right at your server: it then sends
notifications to the browser itself, even with the tab closed and fedtail not running.

- It needs a “secure” address: `https://…` or `http://localhost`. Over `http://192.168.…` from a
  phone the browser won't allow push — put a reverse proxy with https in front of fedtail or open
  it through a tunnel (Tailscale, Cloudflare Tunnel).
- The server keeps one subscription per login: another browser subscribing takes it over.
- Your server must do Web Push (Mastodon does; otherwise fedtail says so).
- To turn it off — the same menu item.

## Activity

The "Activity" lane: who liked, boosted, followed, a poll ended — with the time of each event.
On GoToSocial, replies, likes and boosts waiting for your approval come here too, with "Approve"
and "Reject" buttons.

## The number on the icon

How much is unread — in the tray and on the task bar button. Which lanes count —
`ui.icon_count` and `ui.icon_count_except`.

In detail → [Notifications and activity](ref/features.md#notifications-and-activity) · [settings](ref/config.md#6-notifications)
