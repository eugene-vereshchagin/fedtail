# Other clients' lanes, in our atoms

**What it is:** a survey (27 Oct 2026) of the lanes popular fediverse clients and servers offer,
each written in the atoms of [feeds.md](feeds.md), what they have that our atoms lack, and the
presets that come out of it. "(?)" marks what was not checked against a primary source (docs or
code) — check before relying on it.

## 1. Who was looked at

| group | clients | how sure |
|---|---|---|
| web | Mastodon web (simple and advanced), Phanpy, Elk, Semaphore | Mastodon, Phanpy — code and docs; Elk, Semaphore — mostly (?) |
| phones | Tusky, Fedilab, Megalodon, Moshidon, official Mastodon apps, Ice Cubes, Ivory, Mona | Tusky, Ice Cubes — code; Ivory, Mona — store pages, reviews; Fedilab, official apps — mostly (?) |
| servers with their own lanes | Misskey (Sharkey, Firefish), Akkoma / Pleroma, GoToSocial | Misskey — backend code; Akkoma — API docs; GoToSocial — docs, partly (?) |
| desktop | Tokodon, Tuba, Whalebird, TheDesk | all (?) |

## 2. The lanes, in atoms

Only what differs from the plain "one endpoint, everything" lane; the usual Home / Local /
Federated / Lists / Bookmarks / Likes everyone has.

| client | lane | in atoms | toggles on the lane |
|---|---|---|---|
| Mastodon web | Home | `source=home` (followed tags in it; members of `exclusive` lists out) | boosts / replies / quotes — client-side; API 5.0: `exclude_reblogs/replies/quotes` on the server |
| Mastodon web | Live feeds | `source=local` / `federated` / federated minus local (`remote=true`) | media only |
| Mastodon web | Hashtag | `tags:<spec>` with any / all / none, ≤ 4 tags | local only |
| Mastodon web | List | `list:<id>`; replies — `replies_policy`: none / list members / any followed | hide members in Home (`exclusive`) |
| Mastodon web | Notifications | `event=*` + `me=mention`; grouped (`group_key`) for like/boost/follow | per type: alert / push / show / sound; All / Mentions |
| Mastodon web | Filtered notifications | `event`, `author` = not followed / not following me / new (< 30 d) / moderated / bot | per category: accept / filter / drop |
| Phanpy | Home | `source=home`, duplicate boosts merged | boosts carousel; "new posts" only for a non-boost |
| Phanpy | Mentions | `me=mention` + `kind=quote`; Private — `source=direct` | "only followings" (`author=followed`) |
| Phanpy | Hashtag | `tags:<spec>`, any of ≤ 5 | media only (as a grid), another server |
| Phanpy | Public / Trending | `local` / `federated` / trends **of any server**, read without logging in | — |
| Phanpy | Catch-up | `source=home` over a window (1 h … 12 h+), mine and filtered out; each post in one category: filtered > group > boost > quote > followed tag > reply > post | sort: time / replies / likes / boosts / "density"; by author; top links; "since the last catch-up" |
| Elk | Home | `source=home`, a reply chain shown as one thread | (?) |
| Tusky | Home | `source=home` | boosts / replies / **self-boosts** (Home only) |
| Tusky | Hashtag | `tags:<spec>`, any of (?) | — |
| Fedilab | every lane | as the source | boosts / replies on Home, Local, Public and lists (3.44) |
| Fedilab | Tag timeline | `tags:<spec>` any / all / none (?) | media only, NSFW (?) |
| Fedilab | Remote instance | another server's public lane, without an account there | — |
| Fedilab | Art | `tags:mastoart` + `has=media`, as pictures | — |
| Megalodon | Edit timelines | Local / Federated / list / tag as switchable lanes inside Home, each with a name and an icon | hide replies / boosts in Home |
| Megalodon | Bubble | Akkoma `timelines/bubble` | — |
| Ice Cubes | Home | `source=home` | media out, **bots out**; fetches more when filters empty a page |
| Ice Cubes | Tag group | `tags:<spec>` any, a title and an icon, synced | — |
| Ice Cubes | Hashtag on a wall | `account:<id>` + `has="tag:x"` | — |
| Ice Cubes | Link / Quotes | `timelines/link?url=` / quotes of one post | — |
| Ivory | Hashtag list | ≤ 4 tags in one lane | — |
| Ivory | Notifications | mentions and events together, an unread dot for mentions only | flat or grouped |
| Mona | Saved filter | any lane + a filter of many criteria, kept as a tab of its own | reposts per account |
| Misskey | Social (hybrid) | `source=home` ∪ (`source=local`, `kind=post`) ∪ local replies to me | files / renotes / replies |
| Misskey | Local | `source=local`; replies only self-replies and to me unless "with replies" | files / renotes / replies |
| Misskey | List | `list:<id>`; a reply goes in if it's a self-reply, to me, or the member is marked "with replies" | per member: with replies |
| Misskey | Home | a followee's replies to others — per follow (`withReplies`) | my renotes, renotes of mine, local renotes |
| Misskey | Antenna | a rule over everything arriving: source (home / all / users / users-blacklist / list), keywords OR of AND groups over text + CW, exclude keywords alike, case, with replies, with file, local only, no bots | the rule itself; only from creation, ≤ 200 notes; goes dormant unused |
| Akkoma | Bubble | `source=federated` + `author="domain:…"` of a set the admin chose | media only, `reply_visibility` |
| Akkoma | any | `reply_visibility`: all / `following` (`parent` ∈ mine, followed) / `self` (`me=reply`) | `with_muted` |
| Akkoma | Direct | `visibility=direct` as a flat lane; conversations by recipients | — |
| TheDesk | Integrated | `home` ∪ `local` in one column (?) | words / regex per column (?) |
| Tuba | Home | `source=home` (?) | hide replies / boosts (?) |

## 3. What our atoms lack

| what | seen in | proposal for [feeds.md](feeds.md) |
|---|---|---|
| a lane of other servers chosen by me ("bubble") | Akkoma, Sharkey, Firefish, Megalodon | `author = "domain:{a,b,c}"` over `federated` — no server help needed; Akkoma's `timelines/bubble` as a source where it exists |
| another server's public lane without an account there | Phanpy, Fedilab, Ice Cubes, Mona | source `remote:<host>` (local / federated / trends), no token goes there |
| trends | everyone | source `trends` (posts) — browse only |
| posts with one link; quotes of one post | Mastodon 4.3+, Ice Cubes | sources `link:<url>`, `quotes:<id>` |
| a tag on one person's wall | Ice Cubes | `account:<id>` + `has = "tag:x"` passed to the server as `tagged=` |
| a self-boost; my boost; a boost of mine | Tusky, Misskey | `kind = "self_boost"`; `me = "my_boost"`; `boost_of_mine` is there |
| replies whose parent is mine or followed | Akkoma, Mastodon lists, Misskey | the `parent` axis is there; add it to the presets as a switch |
| replies per author ("this one with replies") | Misskey (per follow, per list member) | a condition with `author = "@x@host", kind = "reply"` — works already; a profile's ⋯ "with replies in my lanes" writes it |
| author: a new account, doesn't follow me, followed me lately, moderated | Mastodon notification policy | `author` values `new` (< 30 d), `not_follower`, `new_follower` (< 3 d), `limited` |
| words: OR of AND groups, over text, CW, alt texts, poll options; case; regex | Misskey antennas, Ivory | a key `text = [["a", "b"], ["c"]]` (outer — OR, inner — AND), `text_in = ["text", "cw", "alt", "poll"]`, `text_case`, `text_regex` |
| a lane over a time window, sorted by something else than time | Phanpy Catch-up | lane `mode = "catch_up"` with `window` and `sort` (time / replies / likes / boosts / density); not an atom, a way to read |
| one category per post with a priority | Phanpy Catch-up | the switches of §4 of feeds.md, with `priority`: a post goes only to the first chip that takes it |
| boosts gathered aside; a reply chain as one block | Phanpy, Elk | display, not atoms: `feed.boost_strip`, `feed.fold_threads` |
| which server filter context a lane uses | Tusky, Mastodon | `filter_context` of a lane: by default from its sources (home, public, notifications, account) |
| a lane goes dormant when unused | Misskey | read-through lanes not opened for `lanes.dormant_days` stop polling their own sources |
| remove one post from a lane | Misskey 2026.6 | ⋯ "not in this lane": an exception `none = [{ id = … }]` kept by the core, synced |

Where we already do better than the best of them: a new lane is filled from what is stored,
not only from the moment it exists (Misskey's antennas start empty and keep 200); a post is read
once for all lanes; the reading place is kept per lane and synced.

## 4. Presets

A preset is a set of lanes in rules (`lanes.preset = "…"`); `[[lanes.custom]]` add to it or
replace its lanes by name. The first one is what fedtail shows today.

| preset | lanes | from whom |
|---|---|---|
| `fedtail` (default) | Home, Bots, Local, Federated, My posts, Direct, Mentions, Replies to me, Subscriptions, Bookmarks, Activity, Requests | today's lanes |
| `point` | Feed: home posts + subscriptions, chip "Comments" off; Posts: mine + replies to my posts; Replies and mentions together; Direct; Activity | the author's |
| `mastodon` | Home (chips: boosts, replies), Notifications (events and mentions together, chip "Mentions only"), Local, Federated, Direct, Bookmarks, Likes | Mastodon web, Ivory |
| `social` | Social: home ∪ local posts ∪ replies to me; Local; Federated; Mentions; Direct; Activity | Misskey |
| `quiet` | Home without boosts older than 2 days and self-boosts, replies only to me and to the followed (chip); Mentions only from the followed (chip); Direct; Activity of the followed only | Akkoma `following`, Phanpy "only followings", Tusky |
| `bubble` | `fedtail` + Bubble: federated from a list of servers in `lanes.bubble` | Akkoma, Sharkey |
| `pictures` | `fedtail` + Pictures: home ∪ local with media, shown as a grid | Fedilab Art, Mastodon "media only" |
| `catch_up` | `fedtail` + Catch-up: home over 12 h, chips by category, sorted by likes | Phanpy |

## 5. Decisions wanted

* The new atoms of §3: all, or which first?
* `quiet` and `point`: which of the chips are on by default?
* Catch-up as a lane mode — now, or after the lanes themselves work?
* Bubble: our own list only, or also the server's (`timelines/bubble`) where it has one?

## 6. Sources

* Mastodon: [timelines](https://docs.joinmastodon.org/methods/timelines/),
  [notifications](https://docs.joinmastodon.org/methods/notifications/),
  [grouped notifications](https://docs.joinmastodon.org/methods/grouped_notifications/),
  [lists](https://docs.joinmastodon.org/methods/lists/),
  [markers](https://docs.joinmastodon.org/methods/markers/),
  [4.3.0](https://github.com/mastodon/mastodon/releases/tag/v4.3.0), the web UI's code
  (`app/javascript/mastodon/features/*/column_settings`, `notifications/components/policy_controls.tsx`)
* Phanpy: [README](https://github.com/cheeaun/phanpy), `src/pages/catchup.jsx`,
  `src/components/shortcuts-settings.jsx`, `src/components/timeline.jsx`
* Elk: [features](https://docs.elk.zone/guide/features); Semaphore:
  [user guide](https://raw.githubusercontent.com/NickColley/semaphore/main/docs/User-Guide.md)
* Tusky: [FAQ](https://tusky.app/faq/), `TabData.kt`, `TimelineViewModel.kt`,
  `NotificationsViewModel.kt` in [the repo](https://github.com/tuskyapp/Tusky)
* Fedilab: [F-Droid](https://f-droid.org/en/packages/fr.gouv.etalab.mastodon); Megalodon:
  [README](https://github.com/sk22/megalodon); Moshidon:
  [F-Droid](https://f-droid.org/en/packages/org.joinmastodon.android.moshinda)
* Ice Cubes: [the repo](https://github.com/Dimillian/IceCubesApp), `TimelineFilter.swift`;
  Ivory: [App Store](https://apps.apple.com/app/id6444602274); Mona:
  [MacStories](https://www.macstories.net/reviews/mona-a-unique-mix-of-customization-options-and-features-you-wont-find-in-any-other-mastodon-app/)
* Misskey: [timelines](https://misskey-hub.net/en/docs/for-users/features/timeline/),
  [antennas](https://misskey-hub.net/en/docs/for-users/features/antenna/), the backend's
  `models/Antenna.ts`, `core/AntennaService.ts`, `endpoints/notes/*-timeline.ts` in
  [the repo](https://github.com/misskey-dev/misskey)
* Akkoma: [differences in the Mastodon API](https://docs.akkoma.dev/stable/development/API/differences_in_mastoapi_responses/);
  GoToSocial: [posts](https://docs.gotosocial.org/en/latest/user_guide/posts/)
