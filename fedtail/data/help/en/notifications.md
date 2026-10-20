# Notifications

What fedtail tells you about, how and when.

## Desktop notifications

By default — about direct messages, replies to you, mentions, subscriptions, activity and
follow requests. About the lane in front of your eyes fedtail keeps quiet.

- What to notify about — `notify.lanes` (`["all"]` — everything), what never — `notify.except`.
- What to show — `notify.privacy`: who and what, only who, or only how many (handy with others
  around).
- Nothing comes? ≡ → "Debugging" → "Send a test notification".

## Activity

The "Activity" lane: who liked, boosted, followed, a poll ended — with the time of each event.
On GoToSocial, replies, likes and boosts waiting for your approval come here too, with "Approve"
and "Reject" buttons.

## The number on the icon

How much is unread — in the tray and on the task bar button. Which lanes count —
`ui.icon_count` and `ui.icon_count_except`.

In detail → [Notifications and activity](ref/features.md#notifications-and-activity) · [settings](ref/config.md#6-notifications)
