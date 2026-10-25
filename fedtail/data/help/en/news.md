# What's new and what's next

What's new in the latest versions, and the plans.

## What's new

<!-- include: parts/whats-new -->
**0.20.0 (in progress):**

- Whose replies a list shows
- Collections of people (Mastodon 4.6)
- Another server's public timeline
- A link's timeline (Mastodon 4.3+)
- In a profile: posts, posts and replies, media
- Who else shared a link
- A video's cover; picture descriptions in a post's edit
- Spell checking in the compose panel
- Mute for a while; posts only
- Hide a single post
- Editing a filter
- Report: which rules it breaks
- Profile: hide follows, posts found by search, article authorship, tag suggestions
- About the server: terms, whom it cut off, its translator
- Push notifications (Web Push, UnifiedPush)

**0.19.0:**

- A bug report straight into your private repository
- Report a bug on GitHub — checked first
- A sound scheme
- Android: a phone and a tablet
- The terminal — everything the windows have
- The web — everything the windows have
<!-- /include -->

Everything that changed, fixes included, is in the
[CHANGELOG](https://github.com/eugene-vereshchagin/fedtail/blob/main/CHANGELOG.md).

## What's next

<!-- include: parts/roadmap shift=1 -->
### Plans

Each feature comes switchable, one at a time, with its entry here and a line in the CHANGELOG. The order is rough: the cheap first, the big later.

| What | Chapter | Config | Size |
|---|---|---|---|
| Toga (BeeWare) | Interfaces | — | large |
| An apt repository of its own | Builds and installing | — | — |
| An installer and a signature for Windows | Builds and installing | — | — |

### Won't do

| What | Why |
|---|---|
| Subscribing to old threads in a batch | Taken off the queue. |
| Boost carousel | Sideways is awkward to read, and it fits badly with “nothing jumps” and read marks. Boosts are hidden with the filter, per person or with a list. |
| Card templates (like tut's `toot.tmpl`) | A theme already sets the look of the whole app; a second layer of templates over themes adds nothing. |
| AI helpers in the compose panel (as in Ice Cubes) | Writing is the author's job. |
| A node admin panel in the client | Sitting in a client logged in as an admin is irresponsible. If a node ever needs setting up, there'll be a separate tool for it. |
| Mastodon's annual report | It's about neither reading nor conversation. |
| An XMPP gateway | Taken off the queue. |

### Not there and not decided

| What | Others | Note |
|---|---|---|
| Sending emoji reactions | Phanpy, Elk, Fedilab | Akkoma, Pleroma, Misskey; GoToSocial can't do it. |
| The token from an external command (`pass`, `gopass`) | tut | It's unclear what this would add over a file readable by its owner only. |
<!-- /include -->
