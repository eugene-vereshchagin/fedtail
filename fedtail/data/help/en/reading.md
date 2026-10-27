# Reading

Lanes, threads, read marks — how reading works here.

## Lanes

On the left, the lanes in groups:

- **Timelines**, from the widest down: "Federated" (everything your server knows), "Home" (the
  people you follow, without bots), "Local" (your whole server), "Bots".
- **Personal**: "My posts", "Direct" (messages to you alone), "To me" (replies and
  mentions), "Subscriptions" (what's new in threads you follow), "Important people" (those you
  rang the bell on — shown once there is something), "Bookmarks", "Activity" (follow requests
  in it too).
- **Unsorted** — what came and no lane took, so a lane's rule never loses a post. It shows up
  only when something is in it; `lanes.unsorted = false` in the config hides it for good.
- **Lists** — your lists from the server, each a lane of its own. Whoever you put in a list
  leaves the general lanes and is read there only.

Which lanes, in what order, and what each one takes: ≡ → "Lanes…" (or a right click on a
lane → "Edit the lane…") — the lane editor, written into the config at once.

Over a lane, two switches: "All / Posts only / New" and "Feed / Conversations"
("Conversations" — each thread as one card). The funnel next to Refresh leaves only pictures,
videos or boosts — until a restart. The ❯ button at the top left puts lanes side by side, in
columns.

In detail → [Lanes](ref/features.md#lanes) · [which lanes to turn on](ref/config.md#4-which-lanes)

## Your place and read marks

- Oldest on top, newest at the bottom — you read downwards, like RSS.
- Open a lane and you stand at the first unread. New posts come and nothing jumps, only the
  counter grows.
- A post is read once you've scrolled past the whole of it. It can be otherwise: "the whole
  lane at once" or by hand only (`read.mark_read`).
- Your place is shared with other clients (your phone): read there — read here too.
- The last Esc draws a curtain: the lanes are hidden, nothing is marked read, the new piles up
  for the morning. Enter or a click on a lane — back.

In detail → [Read marks and place](ref/features.md#read-marks-and-place)

## Threads

A click on a post or on the "↪ in reply to…" strip opens the thread as a tree: every reply under
what it answers, comments numbered `/1`, `/2`, `/2/1`, as on Point. Replies your server never saw
are fetched from the author's server — the thread grows by itself a couple of seconds later.

You can subscribe to a thread (the ⋯ menu or the button in the thread's header): new comments
come to "Subscriptions", even when you weren't mentioned.

In detail → [Threads](ref/features.md#threads)

## The post card

Under a post — reply, like, boost, thread, bookmark and the ⋯ menu with everything else: quote,
translate, mute the thread, copy the handle, to a list, "from another account". A right click on
a post's text opens the same menu.

Arts mode (on by default) shows everything as the author posted it: content warnings (CW) open,
"sensitive" pictures uncovered, server filters hide nothing. Turn it off and each of these is
set on its own.

In detail → [The post card](ref/features.md#the-post-card)

## Pictures and video

A click on a picture — the viewer (← → to flip, S to save, Esc to close). A video plays over the
window (Space — pause, ← → — seek, M — sound), gifs loop right in the card. fedtail fetches
picture previews ahead, so a lane opens with them already there.

In detail → [Pictures and video](ref/features.md#pictures-and-video)

## Lists

Make a list and put someone in it — with a right click on their post. The server takes into
lists only people you follow; if your follow is still waiting to be accepted, fedtail adds them
itself once it is. A right click on a list on the left — who is in it, "Move up" / "Move down".

In detail → [Lanes](ref/features.md#lanes) · [list settings](ref/config.md#8-lists)
