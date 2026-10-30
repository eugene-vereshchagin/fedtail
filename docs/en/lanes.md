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

## A lane's keys

| Key | What goes there | What it means |
|---|---|---|
| `any` | a list of tables: `[{ author = "me" }, { me = "reply" }]` | A list of conditions: a post is in the lane if it matches any of them. |
| `badge` | `hot`, `quiet` | The colour of the lane's counter in the sidebar: “hot” is something to answer, “quiet” is no hurry. Empty means the usual one. |
| `bundle` | `author` | Each author's posts together, the busiest first: catching up by people. |
| `filter_context` | `account`, `home`, `notifications`, `public`, `thread` | The server's filters of this context hide or fold the lane's posts, whatever source they came from. |
| `group` | a word: `standard` or a name of your own | The sidebar section the lane sits in: `standard`, `personal`, `lists`, `tags`, or a name of your own. |
| `hide_empty` | `true` | `true` shows the lane in the sidebar only when something is in it. |
| `icon` | see below | The lane's picture: one of the built-in lanes' icons or the library's (`fire`, `book`, `globe`…). Without it, by the lane's name; a custom lane gets the list icon. |
| `mode` | `catch_up`, `lane` | `lane` is an ordinary lane; `catch_up` shows only what came within `window`: “what I missed”. |
| `name` | a word: `home_plus` | The lane's name. It never changes: the window, sync and tiles remember the lane by it. |
| `none` | a list of tables, as in `any` | Conditions that keep a post out: one matching any of them is left out even if `any` let it in. |
| `open_at` | `first_unread`, `post` | Where a thread opens from the lane's card: at the post or at the first unread comment (none: at the post). Without the key the general thread setting applies. |
| `per_author` | a number: `3` | At most this many posts of one author, the newest, so a noisy one doesn't fill the lane. 0 means no limit. |
| `read` | `browse`, `through` | How the lane is read: with unread marks and counters, or as a fresh page without them. |
| `sort` | `arrival`, `boosts`, `density`, `likes`, `post_time`, `replies` | Post order: by arrival, by the post's time, or by a counter (per hour of age). The best sit where reading starts. |
| `source` | see below | Narrows every condition to these sources. Without it the app picks the sources that can bring what the conditions ask for. |
| `start` | `true` | `true` makes this lane of a set open first when the start lane in the settings names none of its lanes. |
| `switches` | `posts_only`, `unread_only` | Quick filters above the lane: “posts only”, “unread only”. `[]` means none. Without the key, as in lanes before 0.22. |
| `title` | text, or one per language: `{ ru = "Посты", en = "Posts" }` | What the sidebar shows. Without it the name is shown. |
| `view` | `threads` | `threads` shows one card per thread: its post and the number of new comments; only threads with something new. |
| `window` | `"12h"`, `"2d"` | The lane shows only posts younger than this. In `catch_up` the default is 12 hours. |

## A condition's keys

| Key | What goes there | What it means |
|---|---|---|
| `age` | `"<1d"`, `">2d"` | The post's age: younger (`<`) or older (`>`) than a span. |
| `age_of` | `post`, `original` | Whose age `age` counts for a boost: the boost's or the original's. |
| `any` | a list of tables: `[{ author = "me" }, { me = "reply" }]` | An inner OR: one of these tables must match too, along with the condition's other keys (an AND of ORs). |
| `apart` | a lane's name: `"direct"` | A `none` condition that counts only while the named lane is shown: the private posts are read in Direct when it is on, and stay here otherwise. |
| `author` | see below | Who wrote the post (for a boost, who boosted) and how they relate to me. |
| `boosts` | `">10"`, `"<=3"`, `"5"` (at least) | The number of boosts when the post was fetched (it goes stale afterwards). |
| `event` | see below | An event that isn't a post: a like, a follow, an unfollow and so on. Such a condition matches Activity rows. |
| `has` | see below | What the post contains: attachments, a warning, links, tags, words. |
| `id` | an id or a list of ids: `"1122334455"` | One particular post by its id on the server (for a boost, the original's id matches too). |
| `kind` | see below | The kind of post: plain, reply, boost, quote and so on. |
| `lang` | `"ru"`, `"en"`, `"unknown"` | The post's language as the author's client set it, which is often wrong. `unknown` means no language given. |
| `likes` | `">10"`, `"<=3"`, `"5"` (at least) | The number of likes when the post was fetched (it goes stale afterwards). |
| `me` | see below | How the post relates to me: a reply to me, a mention, a boost of my post… |
| `parent` | `followed`, `mine`, `stranger`, `unknown` | Whose post is being replied to, when that is known. |
| `priority` | a number: `1` | Which of the `any` conditions to name as the reason when several match: the larger number goes first. It doesn't change which posts get in. |
| `replies` | `">10"`, `"<=3"`, `"5"` (at least) | The number of replies when the post was fetched (it goes stale afterwards). |
| `shown` | `false` | `false` leaves the switch off by default: posts under it stay hidden until you click it. |
| `source` | see below | Where the post came from: which server timeline, list, search and so on. |
| `state` | see below | What state the post is in for me: read, bookmarked, liked, deleted and so on. |
| `switch` | the chip's word: `"Comments"` | Makes the condition a switch: a chip with this word appears above the lane. |
| `target` | `comment`, `my_comment`, `my_post`, `post`, `read`, `seen` | What a boost, like or other event is about: a post or a comment, mine or someone else's. |
| `text` | `[["a", "b"], ["c"]]`: (a and b) or c | Words in the post's text and its warning (CW). The outer list is OR, the inner one AND. |
| `text_case` | `true` | `true` makes `text` tell capital and small letters apart. |
| `text_in` | `alt`, `cw`, `name`, `poll`, `text` | Where `text` looks: the text, the warning (CW), media descriptions, poll options, the author's name. The default is text and CW. |
| `text_regex` | `true` | `true` reads the words in `text` as regular expressions. |
| `until` | a date or a moment: `"2026-11-01"` | The condition holds until then and afterwards is as if absent: a mute for a week, a lane for a trip. |
| `via` | `boost`, `followed`, `list`, `mine`, `tag` | Why the post is in my Home. |
| `visibility` | `direct`, `followers`, `local_only`, `mutuals`, `public`, `unlisted` | Who can see the post. |

## Words

### The words of `source`

| Word | What it means |
|---|---|
| `bookmarks` | My bookmarks. |
| `bubble` | Servers picked by the admin or by me (the bubble). |
| `context` | A whole thread, once it is opened. |
| `direct` | Direct conversations (the last post of each). |
| `favourites` | Posts I liked. |
| `federated` | Everything my server knows of other servers (not the whole fediverse). |
| `home` | My Home: people I follow, their boosts, my own posts and followed tags. |
| `local` | Every post of my server. |
| `mentions` | Posts that mention me, including replies to me. |
| `mine` | My posts and replies. |
| `subs` | New comments in the threads I follow. |
| `trends` | My server's trending posts (view only). |
| `watched` | New posts of people whose bell I rang. |
| `list:…` | A list's members: `list:<id>`. |
| `tags:…` | Posts with tags: `tags:<tags>` (any, all or none of them). |
| `account:…` | One account's wall: `account:<id>`. |
| `remote:…` | Another server's public timeline without an account there: `remote:<host>`. The token never goes there. |
| `link:…` | Posts sharing one link: `link:<url>` (Mastodon 4.3+). |
| `quotes:…` | Quotes of one post: `quotes:<id>`. |
| `search:…` | Posts found by words: `search:<words>`. |
| `rss:…` | A site's feed as read-only posts: `rss:<url>`. |

### The words of `author`

| Word | What it means |
|---|---|
| `bell` | Someone whose bell I rang. |
| `boosts_off` | Someone whose boosts I hid. |
| `bot` | A bot: by the account's flag or by my own list of bots. |
| `followed` | Someone I follow. |
| `follower` | Someone who follows me. |
| `hidden_home` | Taken out of Home by hand (“Not in Home” on the profile); still followed. |
| `in_list` | A member of one of my lists. |
| `limited` | The account is limited by moderators. |
| `local` | From my server. |
| `me` | Me. |
| `mutual` | We follow each other. |
| `new` | The account is under 30 days old. |
| `new_follower` | Started following me under 3 days ago. |
| `not_follower` | I follow them, they don't follow me. |
| `remote` | From another server. |
| `stranger` | Neither of us follows the other. |
| `@nick@host` | One particular person: `"@nick@host"`. |
| `domain:…` | Everyone from one server: `"domain:x.org"`, or several: `"domain:{a.org,b.org}"`. |

### The words of `visibility`

| Word | What it means |
|---|---|
| `direct` | Only the people mentioned. |
| `followers` | Followers only. |
| `local_only` | Stays on the author's server. |
| `mutuals` | Only for people who follow each other (GoToSocial). |
| `public` | Visible to everyone. |
| `unlisted` | Left out of public timelines, but open to anyone with the link. |

### The words of `kind`

| Word | What it means |
|---|---|
| `boost` | A boost of a post. |
| `edited` | A post that was edited. |
| `poll` | A post with a poll. |
| `post` | A plain post: not a reply, not a boost. |
| `quote` | A quote of another post. |
| `reply` | A reply (comment). |
| `self_boost` | An author boosting their own post. |
| `self_reply` | A reply to oneself: a thread continued. |

### The words of `me`

| Word | What it means |
|---|---|
| `boost_of_mine` | A boost of my post. |
| `direct` | A direct message to me. |
| `in_my_thread` | A post in a thread where I wrote. |
| `mention` | I'm mentioned, but it is not a reply to me. |
| `my_boost` | A boost made by me. |
| `quote_of_mine` | A quote of my post. |
| `reply` | Any reply to me. |
| `reply_to_comment` | A reply to my comment. |
| `reply_to_post` | A reply to my post. |

### The words of `parent`

| Word | What it means |
|---|---|
| `followed` | Replying to a post of someone I follow. |
| `mine` | Replying to my post. |
| `stranger` | Replying to a stranger's post. |
| `unknown` | The post being replied to is not known to me. |

### The words of `has`

| Word | What it means |
|---|---|
| `alt_missing` | Has media without a description. |
| `audio` | Has audio. |
| `cw` | Has a content warning (CW). |
| `followed_tag` | Has a tag I follow. |
| `image` | Has an image. |
| `link` | Has a link or a link card. |
| `media` | Has an attachment: image, video or audio. |
| `poll` | Has a poll. |
| `sensitive` | Marked sensitive. |
| `video` | Has a video. |
| `tag:…` | Has this tag: `"tag:x"`. |
| `link:…` | Links to this site: `"link:domain"`. |
| `word:…` | The text has this word: `"word:x"` (same as `text`). |

### The words of `state`

| Word | What it means |
|---|---|
| `bookmarked` | Bookmarked. |
| `boosted` | I boosted it. |
| `deleted` | Deleted on its own server: it answered that the post is gone when asked again. We keep it, marked. |
| `filtered_warn` | A server filter set to “warn” matched this post. |
| `in_list` | The author is in one of my lists. |
| `liked` | I liked it. |
| `muted_thread` | The thread is muted. |
| `new_replies` | In a thread I follow, there are unread replies. |
| `read` | Read. |
| `replied` | I replied (from any client). |
| `subscribed` | I follow the thread. |
| `unbookmarked` | The server says it is not bookmarked (taken back; no answer doesn't count). |
| `unliked` | The server says it is not liked (taken back; no answer doesn't count). |
| `unread` | Not read yet. |

### The words of `via`

| Word | What it means |
|---|---|
| `boost` | Boosted by someone I follow. |
| `followed` | The author is someone I follow. |
| `list` | The author is in one of my lists. |
| `mine` | It is my own post. |
| `tag` | Brought by a tag I follow. |

### The words of `target`

| Word | What it means |
|---|---|
| `comment` | Someone else's comment. |
| `my_comment` | My comment. |
| `my_post` | My post. |
| `post` | Someone else's post. |
| `read` | The original is already read. |
| `seen` | The original was already in my database. |

### The words of `event`

| Word | What it means |
|---|---|
| `admin` | An admin event: a sign-up, a report. |
| `annual_report` | The server's annual report (Mastodon 4.3+). |
| `deleted` | A post I have stored was deleted. |
| `favourite` | My post was liked. |
| `follow` | Someone followed me. |
| `follow_request` | A follow request waiting for my decision. |
| `gone` | A follower's account was deleted or blocked by the server. |
| `i_followed` | I followed someone. |
| `lost` | Followers of one server vanished at once: contact with that server was lost. |
| `moved` | A follower moved to a new account; this isn't an unfollow. |
| `pending` | A reply, like or boost waits for my approval (GoToSocial). |
| `poll` | A poll I voted in or created has ended. |
| `quote` | My post was quoted (Mastodon 4.5+). |
| `quoted_update` | A post I quoted was edited (Mastodon 4.5+). |
| `reblog` | My post was boosted. |
| `removed_follower` | I removed or blocked a follower myself. |
| `severed` | Connections were cut by a server block (Mastodon 4.3+). |
| `status` | A new post from an account whose bell I rang. |
| `unfollow` | Someone unfollowed me (fedtail notices it by comparing lists). |
| `unfollowed_back` | I follow them, but they no longer follow me. |
| `unliked` | A like was taken off my post (off by default). |
| `update` | A post I boosted was edited. |
| `warning` | A moderation warning to me (Mastodon 4.3+). |

### The words of `text_in`

| Word | What it means |
|---|---|
| `alt` | Descriptions of images and other media. |
| `cw` | The content warning (CW). |
| `name` | The author's name and @nick. |
| `poll` | The poll's options. |
| `text` | The post's text. |

### The words of `age_of`

| Word | What it means |
|---|---|
| `post` | The post's own time; for a boost, the boost's time. |
| `original` | The original's time, so an old post lifted by a boost still counts as old. |

### The words of `sort`

| Word | What it means |
|---|---|
| `arrival` | When the post reached us. |
| `boosts` | By boosts per hour of age. |
| `density` | By replies, likes and boosts together, per hour of age. |
| `likes` | By likes per hour of age. |
| `post_time` | The post's own time. |
| `replies` | By replies per hour of age. |

### The words of `read`

| Word | What it means |
|---|---|
| `browse` | Browse: a fresh page without counters, like Federated. |
| `through` | Read through: unread marks and counters, no jumps. |

### The words of `mode`

| Word | What it means |
|---|---|
| `catch_up` | Only what came within `window` (12 hours by default): “what I missed”. |
| `lane` | An ordinary lane. |

### The words of `filter_context`

| Word | What it means |
|---|---|
| `account` | Filters set for profiles. |
| `home` | Filters set for Home. |
| `notifications` | Filters set for notifications. |
| `public` | Filters set for public timelines. |
| `thread` | Filters set for threads. |

### The words of `bundle`

| Word | What it means |
|---|---|
| `author` | Each author's posts together, the busiest first. |

### The words of `view`

| Word | What it means |
|---|---|
| `threads` | One card per thread, with the number of new comments. |

### The words of `open_at`

| Word | What it means |
|---|---|
| `first_unread` | The thread opens at the first unread comment (none: at the post). |
| `post` | The thread opens at the post. |

### The words of `badge`

| Word | What it means |
|---|---|
| `hot` | A hot counter: something to answer (“To me”). |
| `quiet` | A quiet counter: no hurry (bots, Activity). |

### The words of `switches`

| Word | What it means |
|---|---|
| `posts_only` | The “posts only” chip: hides comments. |
| `unread_only` | The “unread only” chip: keeps what is unread. |

### Pictures (`icon`)

A theme's own picture of that name wins; no `icon` — a set's lane wears the one of its name, one's own a list's.

`home`, `local`, `federated`, `bots`, `my_posts`, `direct`, `replies`, `mentions`, `subs`, `bookmarks`, `my_likes`, `activity`, `requests`, `list`, `tags`, `star_full`, `bolt`, `book`, `bulb`, `calendar`, `camera`, `car`, `chart`, `clock`, `cloud`, `code`, `commented`, `cup`, `film`, `fire`, `fish`, `flag`, `flask`, `food`, `game`, `globe`, `heart`, `image`, `important`, `inbox`, `leaf`, `link`, `megaphone`, `moon`, `mountain`, `music`, `news`, `palette`, `paw`, `people`, `person`, `pin`, `plane`, `quote`, `rss`, `search`, `shield`, `sparkle`, `sun`, `wrench`
