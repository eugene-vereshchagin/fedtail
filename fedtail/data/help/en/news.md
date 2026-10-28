# What's new and what's next

What's new in the latest versions, and the plans.

## What's new

<!-- include: parts/whats-new -->
**0.22.0 (in progress):**

- A draft's pictures travel with it
- Formatting buttons

**0.21.0:**

- Free lanes: a lane you assemble yourself
- Federated and tags wider than your server
- The lane editor
- “Unsorted”: no post gets lost
- Only the languages you read
- Sets of lanes “as in other clients”
- “To me”: replies and mentions in one lane
- Home's quick filters: tags, boosts, threads with news
- Important people
- Lanes of rules: order by counts, “what did I miss”, “Why is it here?”
- Lanes from someone's wall, a search and RSS
- Rules: for a while, by name, at most N per author, by author, "Not in Home"
- A library of pictures for your own lanes
- A thread with new replies shows on its card
- Threads: where replies come from, growing by itself, only the followed, by branch, "Around this post"
- Commented posts: a thread a card, opened at the first new comment
- Where a thread opens: at the post or at the first new comment
- New posts wait for Refresh
- Sync set up in the window step by step, a new device by a password alone
- A lane without a seam: older posts come by themselves
- Language check, link → quote, sending in the background, scheduled → editor, Drafts
- Unfollowed — gone from Home
- Your own names and colours for people, why a post is in Home, a post's JSON
- Activity's quick filters
- Who stopped following you
- Activity says whom you followed
- Someone new in a private talk — shown at once
- Follow requests in Activity
- A proxy, Ctrl+1…9, pinned tabs, the stream on Wi-Fi only, statistics, LibreTranslate and translating by itself
- `fedtail --check`: what the system lacks — and one apt line
<!-- /include -->

Everything that changed, fixes included, is in the
[CHANGELOG](https://github.com/eugene-vereshchagin/fedtail/blob/main/CHANGELOG.md).

## What's next

<!-- include: parts/roadmap shift=1 -->
### Plans

Each feature comes switchable, one at a time, with its entry here and a line in the CHANGELOG. The order is rough: the cheap first, the big later.

| What | Chapter | Config | Size |
|---|---|---|---|
| Sync: WebDAV, a snapshot of the journal | Read marks and place | `[sync]` | medium |
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
