# Writing lanes

A lane in fedtail is a rule: which posts (and which events of Activity) go into it. Every
lane of the built-in sets is such a rule too, written in the same words — so whatever a set's
lane does, a lane of your own can do, and a set's lane can be changed.

This page is the whole vocabulary: how a rule is built, every key, every word each key
takes. The words are fedtail's own, not a server's: they are checked when the config is read,
and a word unknown here never silently matches nothing — the lane gets a warning instead.

## Where lanes are made

- **≡ → “Lanes…”** (or a right click on a lane → “Edit the lane…”) — the lane editor, in
  every interface. The order, which lanes are shown, and each lane's title, picture, sources
  and conditions; written into `config.toml` at once and taken by the running program.
- **`config.toml`** by hand — a table `[[lanes.custom]]` a lane. The editor writes the same
  tables, so the two never disagree.

A set's lane changed in the editor becomes your own: a `[[lanes.custom]]` of the same name in
its place. “As in the set” takes your version away again. Which set the lanes come from —
`lanes.preset`; which of its lanes are on — `lanes.enabled` (see [the settings](/docs/en/config.md)).

## How a rule works

```toml
[[lanes.custom]]
name = "pics"                     # the lane's word: latin letters, digits, _ and -
title = { en = "Pictures", ru = "Картинки" }
any = [                           # it takes a post that fits ANY of these conditions…
  { author = "followed", has = "image" },
  { source = "tags:photography" },
]
none = [{ has = "sensitive" }]    # …and keeps out one that fits any of these
```

- **`any`** — the conditions that take a post in. One fitting is enough.
- **`none`** — the conditions that keep a post out, even when `any` took it.
- **A condition** is a table of keys: it fits when **every** key fits (an “and”). A list of
  words in a key means **any** of them: `author = ["followed", "mutual"]`.
- **An “or” inside a condition** — its own `any`, a list of tables, one of which must fit
  too: `{ author = "followed", any = [{ has = "image" }, { kind = "reply" }] }` — pictures or
  replies, of the people you follow.
- **`source`** of the lane narrows every condition to those sources; none given — fedtail
  picks the sources that can bring what the conditions ask for (a condition about replies to
  you reads your mentions, one about tags reads the tags).
- **A post no lane took** goes to “Unsorted”: a rule never loses a post.

A lane of events — `event = "favourite"` and the like — shows Activity's rows among its
posts, one quiet line each (“bob, ann — ★ favourited · 14:20 · «the post»”); a lane of
events only is a lane like Activity, its events unread until seen.

## A condition as one line

The editor writes a condition as a line, and you can type it so:

```
author: me, followed; kind: post          a comma — any of them
text: tbilisi + georgia, грузия            in text a “+” — all together in one group
any: [has: image] [kind: reply]            an “or” inside
*                                          every post (asks nothing)
```

The same in `config.toml`: `{ author = ["me", "followed"], kind = "post" }`,
`{ text = [["tbilisi", "georgia"], ["грузия"]] }`.

## Quick filters over a lane

Two kinds of buttons sit over a lane; neither changes what the lane takes, only what of it
is shown:

- **The lane's own** — `switches = ["posts_only", "unread_only"]`: “All / Posts only / New”.
  `switches = []` — none. Without the key fedtail guesses as before: “Posts only” where the
  lane reads through its sources, “New” where it marks read.
- **A condition's** — `switch = "Comments"` on a condition makes a button with that word
  showing only what this condition took; `shown = false` — those posts are hidden until the
  button is pressed:

```toml
any = [
  { source = "home", kind = "post" },
  { source = "home", kind = "reply", switch = "Comments", shown = false },
]
```

## Is it right?

- A post's menu → **“Why is it here?”** — which condition took it, and what kept it out of
  the other lanes.
- `python3 -m fedtail --explain-lane NAME` — what the lane's rule does with everything
  stored.
- A word the rule doesn't know, a key misspelt, a condition no server can ever fill
  (followers-only posts of strangers) — a warning in the editor and in `--explain-lane`; a
  condition with a word it doesn't know takes nothing, the rest of the lane works.

## Examples

```toml
[[lanes.custom]]                  # Home with followed threads; comments behind a button
name = "home_plus"
title = "Feed"
any = [
  { source = "home", kind = "post" },
  { source = "subs" },
  { source = "home", kind = "reply", switch = "Comments", shown = false },
]

[[lanes.custom]]                  # what I missed overnight, person by person
name = "overnight"
mode = "catch_up"
window = "10h"
bundle = "author"
per_author = 3
any = [{ author = "followed", kind = ["post", "quote"] }]

[[lanes.custom]]                  # the best of my server today, most liked first
name = "local_best"
sort = "likes"
read = "browse"
any = [{ source = "local", age = "<1d", likes = ">5" }]

[[lanes.custom]]                  # a trip: posts about Georgia, till the end of it
name = "trip"
icon = "plane"
any = [{ text = [["tbilisi"], ["georgia"], ["грузия"]], until = "2026-11-20" }]
none = [{ kind = "boost", age = ">2d", age_of = "original" }]

[[lanes.custom]]                  # likes and boosts of my posts beside my posts
name = "mine"
any = [{ author = "me" },
       { event = ["favourite", "reblog"], switch = "likes" }]
```

The tables below are generated from fedtail's own code: a word appears here the moment the
program knows it.
