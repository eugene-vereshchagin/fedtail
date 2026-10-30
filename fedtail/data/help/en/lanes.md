# Writing lanes

A lane is a rule: which posts (and which events of Activity) go into it. The built-in sets'
lanes are rules in the same words, so a lane of your own can do whatever theirs do.

- ≡ → “Lanes…” (or a right click on a lane → “Edit the lane…”) — the lane editor: the order,
  which are shown, each one's title, picture, sources and conditions. Written into
  `config.toml` at once; a set's lane changed there becomes your own.
- A lane takes a post that fits **any** condition of “Takes” and none of “Keeps out”. A
  condition fits when **each** of its parts does; within a part — any of the words.
- A condition can be typed as one line: `author: me, followed; kind: post` (a comma — any of
  them); `text: tbilisi + georgia` (a “+” — all together); `*` — every post.
- Over a lane: its own quick filters (`switches`: “Posts only”, “New”) and a condition's
  (`switch` — a button with that word, `shown = false` — hidden until pressed).
- Not sure why a post is where it is: its menu → “Why is it here?”.

In detail → [every key and every word](ref/lanes.md) · [examples](ref/lanes.md#examples)
