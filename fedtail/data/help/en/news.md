# What's new and what's next

What's new in the latest versions, and the plans.

## What's new

<!-- include: parts/whats-new -->
**0.22.0:**

- A tag as its author writes it, as on Point
- Following the replies to all of someone's posts
- A draft's pictures travel with it
- Sync: WebDAV spoken directly, the journal packed
- The post under the mouse lit
- The numbers under the posts on screen kept fresh
- Formatting buttons
- A comment is #post/N, as on Point
- Mute a hashtag in one click
- A hung copy doesn't stop a start
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
| The token from an external command (`pass`, `gopass`) | tut | It's unclear what this would add over a file readable by its owner only. |
<!-- /include -->
