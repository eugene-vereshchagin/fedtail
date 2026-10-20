# What's new and what's next

What's new in the latest versions, and the plans.

## What's new

<!-- include: parts/whats-new -->
**0.17.0 (in progress):**

- What my server can do
- Reply with quotes, piece by piece
- The database doesn't grow for ever: cleanup and a size budget
- Help inside, in two languages
- “What's this?”: a longer hint about any button

**0.16.0:**

- Sending to a slow server without doubles
- Find in every lane at once
- Video without a hardware decoder (the default)
- Call someone into a thread
- Copy the handle @user@server
- Federation status: how my server is doing and what fails
<!-- /include -->

Everything that changed, fixes included, is in the
[CHANGELOG](https://github.com/eugene-vereshchagin/fedtail/blob/main/CHANGELOG.md).

## What's next

<!-- include: parts/roadmap shift=1 -->
### Plans

Each feature comes switchable, one at a time, with its entry here and a line in the CHANGELOG. The order is rough: the cheap first, the big later.

| What | Chapter | Config | Size |
|---|---|---|---|
| Collections (Mastodon 4.6) | Lanes | — | once GoToSocial has them |
| GTK4 + libadwaita | Interfaces | — | large |
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
| Push notifications (Web Push, UnifiedPush) | A desktop has enough with the live stream and polling; push is for phones. |
| A node admin panel in the client | Sitting in a client logged in as an admin is irresponsible. If a node ever needs setting up, there'll be a separate tool for it. |
| Mastodon's annual report | It's about neither reading nor conversation. |
| An XMPP gateway | Taken off the queue. |

### Not there and not decided

| What | Others | Note |
|---|---|---|
| Another server's public timeline | Ice Cubes | Reading another server's Local without logging in. Many servers close it to strangers. |
| A link's timeline (Mastodon 4.3+) | Mastodon web | Every post about a popular link. GoToSocial can't do it. |
| Sending emoji reactions | Phanpy, Elk, Fedilab | Akkoma, Pleroma, Misskey; GoToSocial can't do it. |
| Spell checking in the compose panel | Tuba | Not a priority. Qt has none of its own: it needs an outside library (hunspell or enchant) as an optional dependency. |
| The server's grouped notifications (v2) | Mastodon web, Ivory, Phanpy | fedtail's own grouping is there already. |
| The token from an external command (`pass`, `gopass`) | tut | It's unclear what this would add over a file readable by its owner only. |
<!-- /include -->
