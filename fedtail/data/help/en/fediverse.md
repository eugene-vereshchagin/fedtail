# The fediverse for newcomers

How the fediverse works and why it sometimes behaves oddly.

## Servers and accounts

The fediverse is thousands of independent servers (also called nodes or instances) that swap
posts over the ActivityPub protocol. Every account has an address like an e-mail:
`@nick@server`. People on different servers read each other, reply and follow as if they sat on
one. You can change servers: the old account keeps a "moved to…" banner, and your followers move
after you.

## Who sees what

| Visibility | Who sees it |
|---|---|
| Public | everyone, in the shared timelines too |
| Unlisted | everyone by the link and on your profile, but not in the shared timelines |
| Followers | only your followers (fedtail's default) |
| Mentioned | only those you mentioned — a direct message |

Mind: "followers" and "mentioned" aren't encryption. Server admins can technically read them.

## Why replies are missing

Your server knows only what reached it: the posts of people someone on it follows, and what's
addressed to you. That's why other people's threads have holes, and the like counts on their
posts are low. fedtail mends that: it reads the thread from the author's server and (if you like,
`card.honest_counters`) asks there for the real numbers.

## Hashtags, CW, alt

- **Hashtags** are the only way strangers find a post. Write them in CamelCase (`#GeorgiaNews`):
  screen readers read it word by word.
- **CW** (a content warning) hides the text behind a button. It's the custom with spoilers,
  heavy topics and very long texts.
- **Alt** (a picture's description) is for those who can't see it. Without one, fedtail asks
  before sending.

In detail → [ActivityPub directly](ref/features.md#activitypub-directly)
