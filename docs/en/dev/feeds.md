# Free lanes: lanes you assemble yourself

**Status: every lane is a rule** (27 Oct 2026: the sets are rules in `fedtail/data/presets.toml`, `core/presets.py`, `core/custom.py`). Before that — the first version: the atoms (`core/atoms.py`), the rules, free lanes from `[[lanes.custom]]` fed through their own streams (`core/custom.py`). Since then: switches (chips), Unsorted, "Older" for a free lane, the sets written in rules, events in a lane (27 Oct). Not yet: follow requests in a lane of one's own (they stay in Activity), derived events (§2.4). The idea is the author's; this page is what it
becomes in fedtail, what it costs and where it bites. The current lanes are described in
[architecture.md](architecture.md) §8.

## 1. The idea

Today a lane is one source plus a filter written in Python (`core/lanes.py`). A free lane is
**several sources plus a rule from the config**: the user names what goes in it, from the list
of everything fedtail can tell apart about a post or an event — the *atoms*. Any lane can hold
any atoms: "new posts of my server + replies to me + my posts" in one lane, "everything of
mine + replies to my posts" in another.

The built-in lanes stay, but become presets written in the same rules. Whatever the user
assembles, a post that reached fedtail and fell into no lane is not lost: it lands in
**Unsorted** (§6).

Atoms are not a flat list of "types": a post is a reply *and* to me *and* followers-only *and*
from my server at once. So atoms are **axes** (keys), each with its values, and a rule combines
them: inside one condition — AND, between conditions — OR, plus exceptions.

## 2. Atoms: what can be told apart

Every atom is computed by the core from what is stored (a status, its notification, fedtail's
own tables), never by a frontend. The words below are the core's words: a protocol fills them
(§7).

### 2.1 Where it came from (`source`)

| source | Mastodon / GoToSocial API | what it brings | today |
|---|---|---|---|
| `home` | `timelines/home` | the people I follow, their boosts, my own posts; followed tags if the server puts them there | source `home` |
| `local` | `timelines/public?local=true` | my whole server | source `local`, lazy |
| `federated` | `timelines/public` | everything **my server** knows of others — not the fediverse | source `federated`, lazy |
| `mentions` | `notifications?types=mention` | every post that mentions me, replies to me included | source `mentions` |
| `watched` | `notifications?types=status` | new posts of the accounts I rang the bell on | — (only in Activity) |
| `direct` | `conversations` | private dialogues as threads | source `direct` (the last post of each talk) |
| `list:<id>` | `timelines/list/<id>` | members of a server list | list lanes |
| `tags:<spec>` | `timelines/tag/<tag>` | posts with the tags (any / all / none) | tag lanes, lazy |
| `bookmarks` | `bookmarks` | what I bookmarked | source, lazy |
| `favourites` | `favourites` | what I liked | source, lazy |
| `mine` | `accounts/<me>/statuses` | my posts and replies | source `mine` |
| `account:<id>` | `accounts/<id>/statuses` | somebody's wall | source `account:<id>` (also the profile); `/posts` — no replies, `/media`, `/noboosts`, `/pinned`, `/tag:<tag>` — filtered by the server |
| `search:<words>` | `/api/v2/search?type=statuses` | posts found by words | source `search:<words>` |
| `rss:<address>` | the feed itself (RSS 2.0, RSS 1.0, Atom) | a site's feed as read-only posts (open, bookmark here; no likes or replies) | source `rss:<address>` (`core/rss.py`; at most every `lanes.extra_minutes`) |
| `subs` | — (fedtail itself, `/context`) | new comments in threads I follow, as on Point | local source `subs` |
| `context` | `statuses/<id>/context` | a thread fetched whole when opened | — (threads only) |
| `remote:<host>` | another server's `timelines/public` (`/local`, `/federated`), `trends/statuses` (`/trends`) | another server's lanes, read without an account there; no token goes there | source `remote:<host>` (its public lane, each post fetched into my server; `lanes.extra_minutes`) |
| `trends` | `trends/statuses` | my server's trending posts; browse only | source `trends` |
| `link:<url>` / `quotes:<id>` | `timelines/link?url=` (Mastodon 4.3+) / `statuses/<id>/quotes` | posts sharing one link / quotes of one post | sources `link:<url>`, `quotes:<id>` (where the server has them) |
| `bubble` | Akkoma `timelines/bubble`; elsewhere `federated` + `author = "domain:{…}"` of `lanes.bubble` | servers chosen by the admin or by me | source `bubble` (`lanes.bubble`) |

### 2.2 Atoms of a post

| key | values | from what |
|---|---|---|
| `author` | `me`, `followed`, `follower`, `mutual`, `stranger`, `bot`, `local`, `remote`, `new` (account < 30 days), `not_follower`, `new_follower` (< 3 days), `limited` (moderated), `bell`, `boosts_off`, `in_list`, `"@nick@host"`, `"domain:x.org"`, `"domain:{a.org,b.org}"` | the account; relationships (`relationships`, cached); `bot` — the flag or `lanes.extra_bots` |
| `visibility` | `public`, `unlisted`, `followers`, `direct`, `mutuals` (GoToSocial), `local_only` | the post's `visibility` / `local_only` |
| `kind` | `post` (not a reply, not a boost), `reply`, `self_reply` (to oneself: a thread going on), `boost`, `self_boost`, `quote`, `poll`, `edited` | `in_reply_to_id`, `reblog`, `quote`, `poll`, `edited_at` |
| `me` | `reply` (to me, any), `reply_to_post` (to my post), `reply_to_comment` (to my reply), `mention` (tagged, not a reply to me), `direct`, `in_my_thread` (a thread where I wrote), `boost_of_mine`, `quote_of_mine`, `my_boost` | `in_reply_to_account_id`, mentions, the parent (`parents_for`), `sub_members` |
| `parent` | `mine`, `followed`, `stranger`, `unknown` | the parent post, when known |
| `has` | `media`, `image`, `video`, `audio`, `cw`, `sensitive`, `link`, `poll`, `alt_missing` (media without a description), `followed_tag`, `"tag:x"`, `"link:domain"`, `"word:x"` (= `text`) | attachments, `spoiler_text`, `sensitive`, card, links in the text, tags |
| `lang` | `"ru"`, `"en"`, …, `unknown` | `language` (as the author's client set it — often wrong) |
| `state` | `unread`, `read`, `subscribed`, `bookmarked`, `liked`, `boosted`, `replied` (I answered it, from any client), `in_list`, `muted_thread`, `filtered_warn` | fedtail's tables and the post's own flags |
| `target` | `my_post`, `my_comment`, `post`, `comment`, and `seen` (the original was stored before), `read` (…and read) | what a boost, a like, a boost or quote event is about |
| `via` | `followed`, `tag` (a followed tag brought it), `boost` (a followed one boosted it), `mine`, `list` | why it is in my home |
| `likes` / `boosts` / `replies` | `">10"`, `"<=3"`, `"5"` (at least) | the counts as last fetched (they get stale) |
| `text` | `[["a", "b"], ["c"]]` — OR of AND groups; `text_in` (`text`, `cw`, `alt`, `poll`; default text + CW), `text_case`, `text_regex` | the text, the CW, the media descriptions, the poll's options |
| `age` | `"<1d"`, `">2d"`, … | the post's time (`created_at`); for a boost — of the boost or of the original (`age_of = "original"`) |

### 2.3 Events that aren't posts (`event`)

They live in Activity (`activity` table). A lane of rules takes them too (done 27 Oct 2026):
a condition with `event` matches Activity's rows, not posts, and asks no stream of posts; the
lane shows them among its posts by time, one muted line each run of one kind about one post
("bob, ann — ★ favourited · 14:20 · «the post»", a click opens the post or the person) —
`core/custom.py` `Custom.takes_event`, `Core.lane_events`, `common/lane.py` `_with_events`,
`common/activity.py` `event_bit`. Events are never unread, aren't counted, and don't stop the
cursor; a quick filter (`switch`, `shown = false`) parts them as it parts posts; while "New"
or the media funnel is on, none are shown; older than the oldest post shown — none (unless the
lane has no posts). Activity is polled when its lane is shown or a lane takes events.
`follow_request` isn't taken this way: it is answered with buttons, in Activity.

```toml
[[lanes.custom]]
name = "mine"
any = [{ author = "me" },
       { event = ["favourite", "reblog"], switch = "likes" },
       { event = "follow", switch = "follows", shown = false }]
```

| event | Mastodon | GoToSocial | today |
|---|---|---|---|
| `favourite` — my post liked | yes | yes | Activity |
| `reblog` — my post boosted | yes | yes | Activity |
| `follow` — followed me | yes | yes | Activity |
| `follow_request` | yes | yes | lane Requests |
| `poll` — a poll I voted in or made is over | yes | yes | Activity (off by default) |
| `update` — a post I boosted was edited | yes | yes | Activity (off by default) |
| `status` — a watched account posted | yes | yes | Activity (off by default) |
| `quote` — my post quoted | 4.5+ | no | — |
| `quoted_update` — a post I quoted was edited | 4.5+ | no | — |
| `pending` — waiting for my yes (reply, like, boost) | no | yes | Activity (`activity.approvals`) |
| `admin` — sign-up, report (admins only) | yes | yes | not shown (no admin in fedtail) |
| `severed` — relationships cut by a server block | 4.3+ | no | Activity (`activity.server_notices`) |
| `warning` — moderation warning to me | 4.3+ | no | Activity |
| `annual_report` | 4.3+ | no | — |
| `i_followed` — I followed someone (fedtail's own row: through fedtail, or seen in whom I follow) | — | — | Activity (`activity.my_follows`) |

### 2.4 Derived events (comparing snapshots)

Done 27 Oct 2026 (`core/derived.py`): `unfollow`, `unfollowed_back`, `gone`, and `lost` (a server's followers gone at once) — settings `activity.unfollows*` in place of `derived.*`; and `moved` (a follower moved: not an unfollow), `unliked` (`activity.unlikes`, off by default: the last `activity.unlikes_posts` posts of `activity.unlikes_days` days), `deleted` (a post answering 404/410 when fetched again gets a mark on its card; `state = "deleted"`).

What the server never tells a client (an unfollow, a like taken back, a deleted post) is not in
the notifications: fedtail derives it itself, comparing its store with what the server gives now.
Every `derived.interval_minutes` (60 by default) — a snapshot; the difference from the last one —
an event.

| event | what is compared | cost | how not to lie |
|---|---|---|---|
| `unfollow` — someone stopped following me | `accounts/<me>/followers`, the whole list | a page per 40–80; 1000 followers — 15–25 requests | see below |
| `removed_follower` — I removed / blocked them myself | the same | 0 (my own action) | not an `unfollow`: the core records my own actions and subtracts them |
| `moved` — a follower moved to a new account | the `moved` field of the one gone | one `accounts/<id>` | not an unfollow: the new account follows by itself |
| `gone` — the account deleted / suspended by its server | 404/410 on `accounts/<id>` | one request | not an unfollow, an event of its own |
| `unfollowed_back` — I follow them, they no longer follow me | the overlap with `following` | as many pages again | only together with `unfollow` |
| `unliked` — a like taken back | `favourited_by` of my recent posts | a request per post — dear | only the last N posts of `derived.like_days` days, off by default |
| `deleted` — a post I have stored was deleted | 404/410 when fetched again | 0 (noticed on the way) | a mark on the card, not a notification |

Guarding against false unfollows (the main trouble of such features):

* A snapshot counts only if the list came **whole**: every page without an error, and the count
  matches `followers_count` (± changes already known). Otherwise it is thrown away.
* The one gone is confirmed: `relationships` must say `followed_by = false`, and they are absent
  from **two** snapshots in a row (a server sometimes gives a list with a hole).
* Their server is down or defederated us — a mass "everyone from x.org unfollowed": more than
  `derived.mass_threshold` from one domain at once — one event "lost x.org", not a hundred.
* The first snapshot is the baseline and gives no events.
* Unfollowed and followed back within the hour — not seen, and needn't be.
* Two machines with sync see one unfollow: the event's key is the account + the day, sync merges.
* Hidden follower lists (`hide_collections` in GoToSocial, "hide followers" in Mastodon) are
  usually given to their owner; if the server refuses, the event is off with a mark in
  ≡ → Server info.
* An option: `derived.unfollow` (on/off) — a flag of its own, not tied to `arts_mode` (the
  author's call, 25 Oct 2026: `arts_mode` is about what not to show, not about feelings).

## 3. What can be reached and what can't

A client filters only what it got. A rule is a promise; this table is what stands behind it.

| want | where it comes from | the catch |
|---|---|---|
| replies to me | `mentions` | arrives only if the author's client tagged me (Mastodon and GoToSocial do by default) |
| replies under my post, not to me | `subs` (my threads auto-followed) or `context` | costs a `/context` per thread per check |
| new posts of my server, read through | `local` polled like `home` | `local` stops being lazy: requests every poll |
| what the followed write to strangers | — | Mastodon's home drops replies to people I don't follow; only via `account:<id>` |
| the whole fediverse | — | `federated` is only what my server knows |
| boosts of my post as posts | `event = "reblog"` | there is no "post" of a boost of mine in any timeline — only the event |
| who read / saw | — | not in ActivityPub at all |
| unlisted posts of strangers | `account:<id>`, `context`, search | not in public timelines by definition |
| followers-only of people I don't follow | — | the server never gives them to me |
| edits of a post nobody boosted | the post itself, when fetched again | no event; `kind = "edited"` is known once the post is seen again |

## 4. Rules in the config

A free lane is a table `[[lanes.custom]]`; its keys:

| key | meaning |
|---|---|
| `name` | the lane's word (stable: the window, sync and the tiles remember lanes by it) |
| `title` | what the sidebar shows; no title — the word |
| `any` | a list of conditions: a post goes in if it matches **any**; inside a condition every key must match (AND), a list of values means any of them; a condition may hold an `any` of its own — a list of tables, one of which must match too (an AND of ORs: `{ author = "followed", any = [{ has = "image" }, { kind = "reply" }] }`; in the editor's line `author: followed; any: [has: image] [kind: reply]`) |
| `none` | conditions that keep a post out, even if `any` let it in |
| `source` | narrows every condition to these sources; no `source` — the core picks the sources that can bring the atoms (§3) |
| `sort` | `arrival` (when it reached us), `post_time` (the post's own time; lanes with notifications), or by counts: `replies`, `likes`, `boosts`, `density` (all three per hour of age) — the best where reading starts |
| `mode` | `lane` (as always) or `catch_up` — only what came within `window` (12h by default): "what did I miss" |
| `window` | a lane shows only posts younger than this (`"12h"`, `"2d"`) |
| `filter_context` | the server's filters of this context (`home`, `public`, `notifications`, `thread`, `account`) hide or fold the lane's posts, whichever source they came by |
| `per_author` | at most so many posts of one author — their newest (a noisy one doesn't drown the lane); 0 — any |
| `bundle` | `"author"` — each author's posts together, the busiest first (a catch-up read person by person) |
| `view` | `"threads"` — a card a thread (its post) with how many new comments, the threads with something new only; opening one goes to its first new comment (Point's way: the extra set's "Commented posts") |
| `until` (of a condition) | the condition holds till then — a date `"2026-11-01"` or a moment; after it, as if it weren't there (a mute for a week in `none`, a lane for a trip) |
| `text_in = "name"` (of a condition) | `text` looks in the author's name and @nick too (with `text_regex` — a regular expression) |
| `author = "hidden_home"` | someone taken out of Home on their profile ("Not in Home", `people.home_hide`), still followed; every set's Home has it in `none` |
| `read` | `through` (unread marks, counts, never jump) or `browse` (newest page, no counts — like Federated) |
| `group` | the sidebar section: `standard`, `personal`, `lists`, `tags`, or a name of one's own |
| `icon` | the lane's picture from the built-in set: `home`, `local`, `federated`, `bots`, `my_posts`, `direct`, `replies`, `mentions`, `subs`, `bookmarks`, `my_likes`, `activity`, `requests`, `list`, `tags`, `star_full`, and the library (`fedtail/data/icons/lanes`, drawn by `tools/lane_pictures.py`, coloured by each theme): `important`, `commented`, `person`, `people`, `heart`, `fire`, `sparkle`, `bolt`, `news`, `megaphone`, `rss`, `search`, `link`, `quote`, `inbox`, `image`, `camera`, `film`, `music`, `palette`, `book`, `code`, `game`, `bulb`, `flask`, `wrench`, `chart`, `shield`, `clock`, `calendar`, `flag`, `pin`, `globe`, `mountain`, `sun`, `moon`, `cloud`, `leaf`, `paw`, `fish`, `car`, `plane`, `cup`, `food` (a theme's own file of that name wins); none — the one its name has (a set's lane), a list's for one's own |
| `switch` (of a condition) | the condition is a switch: a chip over the lane with this word; `shown = false` — hidden by default (like today's "posts only") |

The author's two lanes from the first talk:

```toml
[[lanes.custom]]
name = "feed"
title = "Лента"
any = [
  { author = "local", kind = "post" },        # new posts of my server
  { me = "reply" },                            # replies to me
  { author = "me" },                           # my posts
]

[[lanes.custom]]
name = "home_plus"
title = "Feed"
any = [
  { source = "home", kind = "post" },                               # posts
  { source = "subs" },                                              # followed threads
  { source = "home", kind = "reply", switch = "Comments", shown = false },  # hidden
]

[[lanes.custom]]
name = "posts"
title = "Посты"
any = [
  { author = "me" },                           # everything of mine, to anyone
  { me = "reply_to_post" },                    # replies to me under my posts
]
none = [{ kind = "boost", age = ">2d", age_of = "original" }]   # no old posts brought up again
```

## 5. How it behaves

* **One post, many lanes.** A post may sit in several lanes; it is **one** post: read in one
  lane — read everywhere (and synced). A boost and its original are one post too
  (`feed.dedupe_boosts`, already planned as an option).
* **Sources from rules.** `lanes.sources_needed()` is computed from the rules: the union of the
  sources every condition needs. A source no lane needs is not fetched.
* **Lazy or not.** A lane with `read = "through"` makes its sources polled with `catch_up`,
  even `local`; `browse` lanes fetch their sources only while open.
* **Order.** `sort` decides; a lane mixing notifications and timelines sorts by the post's
  time by default (what reaches us late goes into its place, above the separator if read).
* **What comes first.** Blocks, mutes, server filters "hide" and hidden list members apply
  **before** the rules: no rule brings back a muted person.
* **Notifications and sounds** go once per post, by the most personal lane it fell into
  (direct > reply > mention > thread > the rest), not once per lane. Done (`lane_rank`,
  `_once_per_post`).
* **Switches** (`switch`) — chips over the lane, like today's "posts only"; the state is
  remembered per lane for this run (across restarts only with `reading.remember_choices`) and not
  synced — decided 27 Oct 2026: a chip is a glance, not a setting. What a switch hides the lane has still *taken*: it doesn't
  go to Unsorted, counts and notifications leave it out, switched on it stands in its place and
  the reading place doesn't move. Today's `posts_only`, `mentions_all`, `direct_apart` become
  the presets' switches.

## 6. Defaults and the "Unsorted" lane

The built-in lanes become presets written in rules; their words stay (and the old ones —
`lanes.RENAMED`). Whoever writes no `[[lanes.custom]]` sees exactly what they see today.

| preset | rule |
|---|---|
| `home` | source `home`, `none = [{ author = "bot" }]` |
| `bots` | source `home`, `any = [{ author = "bot" }]` |
| `my_posts` | `any = [{ author = "me" }]` |
| `direct` | `any = [{ me = "direct" }]` |
| `replies` | `any = [{ me = "reply" }]`, not mine |
| `mentions` | `any = [{ me = "mention" }]` |
| `subs` | source `subs`, not `me = "reply"` |
| `activity` | `any = [{ event = ["favourite", "reblog", "follow"] }]` |

* **Unsorted** (`unsorted`) — every item of a *read-through* source that no lane took. It
  appears only when something is in it, and says in a tooltip which rule was nearest
  ("Why is it here?"). Browse sources (`federated`, `local` while lazy) don't go there: they
  would drown it. Not there either: what another lane holds, posts of people put in a list
  (read in the list's lane). Collected with any set — of views or of routed lanes; while empty
  it isn't in the sidebar; `lanes.unsorted = false` hides it for good and stops collecting.
* After a change of rules what is already stored is sorted anew; nothing is re-fetched.
* **Why is it here?** — a card's menu item (and `fedtail --explain-lane NAME`): which
  condition took the post, or for each one the first key that kept it out. A lane whose
  condition no source can fill is marked ⚠ in the lane editor and says why.
* **Parents first.** A round's replies whose rules ask about the parent or about me
  (`parent`, `me`) get their parents fetched before the rules sort them (up to 20 a round),
  so a reply doesn't jump lanes after it is shown.

## 7. Protocols and new atoms

* Atoms are the core's words (`core/atoms.py`), protocols fill them. Each protocol says which
  atoms it can fill (`Capabilities.atoms`); a condition on an atom the server can't fill never
  matches, and ≡ → Server info shows such lanes as "can't be filled here" instead of silently
  empty.
* New raw kinds come with updates: an atom gets a `since` (the version), the config example
  and `docs/src/features`. An unknown key or value in the config is a warning in the log and a
  mark on the lane, never a crash or a silently empty lane.
* Mastodon-only atoms (`quote`, `severed`) are simply not filled by GoToSocial; Matrix and the
  like will fill what they have (no boosts there, for instance).

## 8. Problems of this approach

Besides "setting up becomes programming":

| problem | why it bites | what we do |
|---|---|---|
| A lane promises what no source gives | "replies of the followed to strangers", "the whole fediverse" look writable and stay empty | §3 as a check: a condition that no source can fill — a warning and a mark on the lane |
| Request budget | every read-through `local`, every `in_my_thread` (a `/context` per thread) spends the server's 300 requests per 5 minutes | count requests per lane in the log and ≡ → Server info; `context` checks only for followed threads, as now |
| Pruning by source | `prune` keeps N items per **source**; a lane over several sources may lose its tail while another lane is short | keep per lane (the oldest item any lane still shows), budget stays 1 GB |
| Holes in read-through | a lazy source has holes; put into a read-through lane it breaks "nothing is skipped" | a source in a read-through lane is always caught up whole; the lane says so in the log |
| Atoms known late | `reply_to_post` vs `reply_to_comment`, `parent`, `in_my_thread` need the parent or the thread, fetched in the background | the post waits as "being sorted" (seconds) and shows when known; with no answer — goes by what is known, never jumps after it is shown |
| Atoms that change | an unlike, unbookmark, an unfollow (`followed` → `stranger`), an edit adding a CW move posts between lanes after the fact | a post already shown stays until the lane is reopened; counts recalculated, the reading place never moves |
| Duplicates | one post from `home`, `local` and `mentions`; a boost and its original | one card per post per lane; which context it shows (a reply quote, "boosted by") — from the most personal source |
| "Mark all read" across lanes | read in a narrow lane is read in all, and the wide one loses its unread | the expected Point way; an option for "read in this lane only" is not planned — it breaks sync |
| Notification storm | a post in three lanes — three sounds | once per post, by the most personal lane (§5) |
| Unsorted overflows | a wide source no rule takes (federated read through) floods it | Unsorted takes read-through sources only; over N items — a hint which source floods it |
| Typos | `me = "replys"` — a lane silently empty | strict check at start: unknown keys and values — a warning and the lane marked; `fedtail --explain-lane NAME` and "Why is it here?" on a card |
| Rule cost | every lane × every stored item on each refresh: thousands × dozens | atoms computed once per post and stored (cache by `status_version`); a rule is a check on a few bits |
| Names and sync | the window, columns, tiles, sync and `notify.lanes` remember lanes by word; a renamed lane loses all of it | `name` is the id and doesn't change; `title` is free; renaming `name` — like 0.15's `RENAMED` |
| Old switches | `mentions_all`, `direct_apart`, `posts_only`, `lists.hide_in` overlap the rules | they stay as shorthand for the presets; a custom lane gets none of them, its rule says it all |
| Lanes and events in one list | a like row is not a post: no thread, no reply, a different card, a different "read" | allowed, but a lane with events counts only its posts; events — Activity's own "seen" |
| Four interfaces and Android | each must draw any lane and the sidebar sections; the phone has no comfortable config | the lanes come from the core already built (as now); the Android settings page gets a lane editor later |
| A lane between profiles | rules about `author = "me"` mean another person in a second profile; "my other accounts" needs multi-account | per profile, like the config; `my_accounts` — when one window holds several accounts |
| Protocol drift | atoms are Mastodon-shaped; another network may have neither boosts nor visibility | `Capabilities.atoms` (§7); a lane says "can't be filled here" |

## 9. Steps

1. `core/atoms.py`: every atom of §2 as a function of a stored post (and fedtail's tables),
   tests for each on `tests/fakes.py`; atoms stored per post.
2. The rule: parsing, strict checks, `explain`; tests for every key and every error.
3. The built-in lanes as presets: the same output as `LANES` today, item for item (a test over
   a recorded store).
4. Lanes over several sources: `lane_entries`, `sources_needed`, pruning per lane, read-through
   `local`.
5. Unsorted, "Why is it here?", `--explain-lane`.
6. The config (`[[lanes.custom]]`, both examples), `docs/src/features`, the help.
7. The interfaces: the sidebar, columns, tiles, notifications by the most personal lane;
   parity in `docs/src/parity.toml`.

## 10. Open questions (closed 27 Oct 2026)

* Nested groups in `any`: yes — a condition's own `any` (an AND of ORs), §4.
* Events and posts in one lane: allowed (`event = …` conditions); a lane counts only its posts
  as unread, events keep Activity's "seen".
* `in_my_thread` without following the thread: no — only followed threads, it costs a
  `/context` per thread.
* The lane editor on the phone: a form over the same rules (≡ → Lanes), a condition as one
  line to type, checked on save — the same place in all four interfaces.

## 11. Decisions of 27 Oct 2026

| # | what | how |
|---|---|---|
| 1 | Federated wider than my server knows | done (0.21, `core/wider.py`): `lanes.federated_extra` and `lanes.tags_extra` — other servers' public and tag lanes, each post fetched into my server by address (search with resolve), so ids are mine and actions just work; trends not merged. The plan was: `federated` = my federated ∪ trends ∪ public lanes of chosen servers (`remote:<host>`, no account there) — merged, no duplicates, through the languages filter; the list — `lanes.federated_extra`; a like/reply to such a post — through my server's search (`resolve`), one request on the action |
| 2 | Languages to read | done (0.21): `lanes.languages`, `languages_in` (federated, local, tags by default), `detect_language` (the script + python3-langdetect from 12 words) |
| 3 | Stop words | the server's filters (they work already and are shared by every client); none of our own |
| 4 | Followed tags and Home | tags, like people, go to Home; a tag lane can be taken apart with a tick "not in Home" (like lists' `exclusive`) — when made from the search and in the config; Home's quick filters: all · posts only · tags · boosts |
| 5 | A stranger in a private talk | done (0.21): a banner "someone new was added to the conversation" when a private thread mentions someone not among its participants: on an incoming post and in the reply box before sending |
| 6 | Replies and mentions | one lane "To me" with quick filters "replies / mentions" by default; whoever wants two makes them |
| 7 | Threads with news | a thread with new comments is highlighted; a quick filter "posts with new replies": posts (not comments) with something new from anyone, the replies themselves only inside the thread |
| 8 | Important people | a default lane: posts of those with the bell on; shown once the bell is on for anyone |
| 9 | Activity | + quotes of my posts, polls over, edits of what I boosted, derived unfollows; follow requests — a quick filter here, not a lane |
| 10 | Bookmarks | kept by the server, shared by every client; nothing to sync ourselves |

Decided (27 Oct): Subscriptions (Point-style threads) become a quick filter of Home, "threads I
took part in" — a preset's setting, not code. `lanes.federated_extra` is empty by default: which servers to read is the reader's choice.
