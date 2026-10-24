# Free lanes: lanes you assemble yourself

**Status: a design, no code yet** (25 Oct 2026). The idea is the author's; this page is what it
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
| `direct` | `conversations` | private dialogues as threads | — (direct goes via mentions) |
| `list:<id>` | `timelines/list/<id>` | members of a server list | list lanes |
| `tags:<spec>` | `timelines/tag/<tag>` | posts with the tags (any / all / none) | tag lanes, lazy |
| `bookmarks` | `bookmarks` | what I bookmarked | source, lazy |
| `favourites` | `favourites` | what I liked | source, lazy |
| `mine` | `accounts/<me>/statuses` | my posts and replies | source `mine` |
| `account:<id>` | `accounts/<id>/statuses` | somebody's wall | — (only the profile) |
| `subs` | — (fedtail itself, `/context`) | new comments in threads I follow, as on Point | local source `subs` |
| `context` | `statuses/<id>/context` | a thread fetched whole when opened | — (threads only) |

### 2.2 Atoms of a post

| key | values | from what |
|---|---|---|
| `author` | `me`, `followed`, `follower`, `mutual`, `stranger`, `bot`, `local`, `remote`, `"@nick@host"`, `"domain:x.org"` | the account; relationships (`relationships`, cached); `bot` — the flag or `lanes.extra_bots` |
| `visibility` | `public`, `unlisted`, `followers`, `direct`, `mutuals` (GoToSocial), `local_only` | the post's `visibility` / `local_only` |
| `kind` | `post` (not a reply, not a boost), `reply`, `boost`, `quote`, `poll`, `edited` | `in_reply_to_id`, `reblog`, `quote`, `poll`, `edited_at` |
| `me` | `reply` (to me, any), `reply_to_post` (to my post), `reply_to_comment` (to my reply), `mention` (tagged, not a reply to me), `direct`, `in_my_thread` (a thread where I wrote), `boost_of_mine`, `quote_of_mine` | `in_reply_to_account_id`, mentions, the parent (`parents_for`), `sub_members` |
| `parent` | `mine`, `followed`, `stranger`, `unknown` | the parent post, when known |
| `has` | `media`, `image`, `video`, `audio`, `cw`, `sensitive`, `link`, `poll`, `"tag:x"`, `"word:x"` | attachments, `spoiler_text`, `sensitive`, card, tags, text |
| `lang` | `"ru"`, `"en"`, …, `unknown` | `language` (as the author's client set it — often wrong) |
| `state` | `unread`, `subscribed`, `bookmarked`, `liked`, `boosted`, `in_list`, `muted_thread`, `filtered_warn` | fedtail's tables and the post's own flags |
| `age` | `"<1d"`, `">2d"`, … | the post's time (`created_at`); for a boost — of the boost or of the original (`age_of = "original"`) |

### 2.3 Events that aren't posts (`event`)

They live in Activity today (`activity` table). A free lane may take them too: such rows are
shown as Activity shows them.

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
| `any` | a list of conditions: a post goes in if it matches **any**; inside a condition every key must match (AND), a list of values means any of them |
| `none` | conditions that keep a post out, even if `any` let it in |
| `source` | narrows every condition to these sources; no `source` — the core picks the sources that can bring the atoms (§3) |
| `sort` | `arrival` (when it reached us) or `post_time` (the post's own time; lanes with notifications) |
| `read` | `through` (unread marks, counts, never jump) or `browse` (newest page, no counts — like Federated) |
| `group` | the sidebar section: `standard`, `personal`, `lists`, `tags`, or a name of one's own |

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
  (direct > reply > mention > thread > the rest), not once per lane.

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
  would drown it.
* After a change of rules what is already stored is sorted anew; nothing is re-fetched.

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

## 10. Open questions

* Should `any` allow nested groups (AND of ORs), or is "conditions + `none`" enough?
* Events and posts in one lane: allow at once, or keep events for Activity for the first
  version?
* `in_my_thread` without following the thread: worth the requests?
* The lane editor on the phone: a form over the same rules, or the config text with a check?
