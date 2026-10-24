# What fedtail does, what it doesn't yet, and what's next

[По-русски](/docs/ru/features.md)

As of version **0.19.0 (in progress)**. This is the full list of fedtail's features: what each one does,
what turns it on and off, since which version it's there, which API or protocol it stands on
and how other clients do the same. The plans are here too, and what was turned down, with the
reasons.

The full settings reference is [config.md](/docs/en/config.md), in tables by chapter. The same
as one "fedtail and other clients" matrix — [comparison.md](/docs/en/comparison.md). How the
code is built — [architecture.md](/docs/en/dev/architecture.md); the spec and the queue —
[design.md](/docs/en/dev/design.md).

> **This file is built** from `docs/src/features/*.toml` by `python3 tools/docs_build.py` —
> edit there, not here. A test checks this file keeps up.

## How to read it

Each chapter is a table: the feature, its status, since which version, the config key, the API
or protocol, how others do it. Under the table, in "In detail", is what each one does, in words.

- **Statuses:** *has* · *partly* · *no* · *planned*; at the end — *won't do* and *not decided*.
- **Since** — the fedtail version it first came in. For the very first features it's 0.1.0–0.3.0
  roughly: not everything was written down then.
- **Config** — the key as `section.key`. "—" means there's no key of its own: the feature is
  simply in a menu or a window and does nothing until you call it. For *planned* features the
  key's name is tentative and may change once it's made.
- **Others** — the same things in other clients: Mastodon web, Tusky, Ivory, Phanpy, Elk,
  Tokodon, Ice Cubes, Fedilab, Sengi, Megalodon, tut, Tuba, Whalebird. From their READMEs and
  release notes (as of autumn 2026) and general knowledge about them, without trying each one
  live. **Only in fedtail** means none of those listed has it so.
- What a particular server supports (GoToSocial above all), check on yours. fedtail itself
  hides what the server can't do: it explains an empty lane and draws no needless buttons.

The main principles everything else grows from:

<!-- include: parts/principles -->
1. **Nothing jumps.** Open a lane and you stand at the first unread. New posts come and your
   place doesn't move, only the counter grows. You read in order, like RSS.
2. **Every reply knows what it answers.** Over a reply, a strip with the start of the original
   post; under someone's comment, what you said back to it: come back to a thread a week later
   and you see at once where you were. A click opens the whole thread as a tree.
3. **Lanes are apart.** People apart, bots apart, replies to me apart from other mentions.
4. **Private by default.** A new post goes to followers only. A reply is never more public than
   the original.
5. **Every behaviour is a config key.** There's no settings window and there won't be. The
   defaults are as the author likes them; "like everyone else" is a flag away. New features
   come switchable.
6. **Other servers get no token of yours.** Whatever fedtail takes straight from the author's
   server over ActivityPub goes anonymously: they see only your IP.
7. **The core knows nothing of a GUI.** Interfaces are plugins: a Qt window, a terminal, a
   browser; GTK next.
8. **One profile, one account.** A second account is a second profile (`--profile`); if you
   like, all accounts come together in one window (`ui.merge`).
9. **Grown-ups sort things out themselves.** Arts mode (after @arts, the founder of Point.im):
   everything as the author posted it, no nannying. Anyone can be told where to go, an admin
   too — and the admin can say the same back.
<!-- /include -->

This is the list of what there is **now**, not a history: what changed in each version is in the
[CHANGELOG](/CHANGELOG.md).

**Contents:** [Lanes](#lanes) · [Threads](#threads) · [Read marks and place](#read-marks-and-place) · [The post card](#the-post-card) · [Pictures and video](#pictures-and-video) · [Profiles](#profiles) · [Writing](#writing) · [People and order](#people-and-order) · [Notifications and activity](#notifications-and-activity) · [Several accounts](#several-accounts) · [The application](#the-application) · [Interfaces](#interfaces) · [Builds and installing](#builds-and-installing) · [ActivityPub directly](#activitypub-directly) · [Plans](#plans) · [Won't do](#wont-do) · [Not there and not decided](#not-there-and-not-decided)

---

## Lanes

On the left, the lanes in groups: “Timelines” (from the widest down to your own), “Personal”, “Lists”. Which lanes to show and in what order — `lanes.enabled`. Group headings go with `ui.sidebar_groups = false`. The column's width — `ui.sidebar_width`; its edge drags with the mouse, and the dragged width is kept until the number in the config changes.

| What | Status | Since | Config | API / protocol | Others |
|---|---|---|---|---|---|
| Federated, Home, Local | has | 0.2.0 | `lanes.enabled` (`"federated"`, `"home"`, `"local"`) | `timelines/home`, `timelines/public` | everyone |
| Lane names in the config match their titles | has | 0.15.0 | `home`, `replies`, `federated`, `my_posts`, `my_likes`; the old `people`, `comments`, `global`, `mine`, `favourites` are understood too; a lane's word is in its tooltip on the left | — | — |
| Bots in a lane of their own | has | 0.1.0 | `lanes.enabled` (`"bots"`), `lanes.extra_bots` | the `account.bot` field | only in fedtail |
| Personal lanes | has | 0.1.0 | `lanes.enabled`, `lanes.mentions_all`, `lanes.direct_apart` | notifications, `visibility=direct` | everyone, but laid out differently |
| Lists as lanes | has | 0.2.0 | `[lists]`: `enabled`, `refresh_minutes` | `lists`, `timelines/list/:id` | Mastodon web, Tusky, Ivory, Phanpy, Elk, Tokodon, Ice Cubes, Megalodon |
| Who is in a list leaves the general lanes | has | 0.3.0 | `lists.hide_members`, `lists.hide_in` | own | only in fedtail |
| Who is in a list; your own order of lists | has | 0.13.0 | — | `lists/:id/accounts` | Mastodon web, Ivory (who is in a list); the order — only in fedtail |
| Into a list — the author or the booster; only people you follow | has | 0.13.0 | — | `lists/:id/accounts` | only in fedtail |
| Into a list right after a follow | has | 0.11.0 | `lists.refresh_minutes` | `lists/:id/accounts` | only in fedtail |
| Hashtag lane, following tags | has | 0.2.0 | — | `timelines/tag/:name`, `tags/:name/follow`, `followed_tags` | everyone |
| My likes | has | 0.8.0 | `"my_likes"` in `lanes.enabled` | `/api/v1/favourites` | Mastodon web, Tusky, Ivory, Megalodon, tut |
| Bookmarks | has | 0.3.0 | `"bookmarks"` in `lanes.enabled`, `ui.bookmark_button` | `/api/v1/bookmarks` | everyone |
| Trends | has | 0.11.0 | — | `/api/v1/trends` (tags, links, statuses) | Mastodon web, Tusky, Ivory, Phanpy, Elk, Ice Cubes |
| An empty live lane says why it's empty | has | 0.11.0 | — | `timelines/public` | only in fedtail |
| Filtering a lane by media and boosts | has | 0.11.0 | — (kept until restart) | own | only in fedtail |
| Repeated boosts don't bring an old post up again | has | 0.15.0 | `feed.repeat_boosts` | own | only in fedtail (a Mastodon server drops a repeat only among the freshest posts) |
| All / Posts only / New; Feed / Conversations | has | 0.3.0 | `lanes.posts_only`, `feed.remember_choices` | own | Phanpy — similar to “Conversations” |
| Find in a lane | has | 0.2.0 | — | own, in the local database | only in fedtail |
| Sending to a slow server without doubles | has | 0.16.0 | `post.send_timeout` | `Idempotency-Key`, `accounts/:id/statuses` | only in fedtail |
| Find in every lane at once | has | 0.16.0 | a tick in the `Ctrl+F` bar | own, in the local database | only in fedtail |
| Finding people, tags and posts | has | 0.2.0 | — | `/api/v2/search` | everyone |
| A lane of several tags | has | 0.14.0 | `[[lanes.tag_groups]]`; from the search — “＋ to lanes” | `timelines/tag/:name` for each tag, put together here | Phanpy, Ice Cubes (“tag groups”), tut (`:tag a b`) |
| Columns side by side | has | 0.14.0 | `ui.layout`, `ui.columns`, `ui.column_width`; the ❯ button at the top left | own | Sengi, Phanpy, tut, Whalebird, Mastodon web (advanced mode) |
| A messenger's layout: a roster and a messages window | has | 0.17.0 | `ui.layout = "split"` or for one run `fedtail --layout split`; `ui.roster_on_top`, `ui.roster_threads`, `ui.faces`, `ui.dock_commands`, `ui.split_tabs`, `ui.icons` | own | — |
| Collections (Mastodon 4.6) | planned | — | — | `/api/v1/collections` | Mastodon 4.6, Fedilab |

<details><summary>In detail</summary>

**Federated, Home, Local.** “Home” (`home`) — the people you follow, without bots; it opens by default. “Local” — your whole server. “Federated” — everything your server knows from all servers. Federated and Local are fetched only while open and have no unread counts: they are for browsing, not for reading to the end. A gap between a fresh page and what was there before is allowed in them — unlike Home, which catches up with no holes (see Catching up with no holes).

**Bots in a lane of their own.** Posts of accounts with the “bot” tick leave Home for a lane of their own, “Bots”. A bot without the tick goes into `lanes.extra_bots`: on your server — `"nick"`, on another — `"nick@server"`.

**Personal lanes.**

- “My posts” (`my_posts`) — my posts and comments.
- “Direct” (`direct`) — messages visible to the mentioned only. With `lanes.direct_apart = true` (the default) they live only here and don't double up in “Replies to me” and “Mentions”.
- “Replies to me” (`replies`) — replies to my posts and comments, even if they @ me.
- “Mentions” (`mentions`) — where I was tagged in someone else's conversation. `lanes.mentions_all = true` — show everything that mentions me here, replies too (they'll be in both lanes).
- “Subscriptions” (`subs`) — what's new in threads I'm subscribed to (see Thread subscriptions).
- “Bookmarks” (`bookmarks`), “My likes” (`my_likes`, off by default), “Activity” (`activity`), “Follow requests” (`requests`) — below, each in its own section.

Splitting “replies to me” from “mentions” is what other clients don't do: usually it all lands in one notifications lane.

**Lists as lanes.** The server's lists are lanes of their own in the “Lists” group. Create, rename, delete, make exclusive — from the menu; add a person — with a right click on their post. fedtail rereads the lists and who is in them every `lists.refresh_minutes` minutes.

**Who is in a list leaves the general lanes.** Put a person or a bot in a list — their posts, their boosts and others' boosts of their posts are read in the list's lane and disappear from the general lanes, so they don't clutter them. `hide_members`: `"all"` — so with any list; `"exclusive"` — only with exclusive ones (the server itself takes such people out of Home, fedtail carries that to the other lanes); `"off"` — don't take out. Which lanes — `lists.hide_in` (by default Home, Bots, Federated, Local).

**Who is in a list; your own order of lists.** Right click on a list on the left: “Who is in it…” — a tab with its people (and those waiting for a follow to be confirmed), each with “Take out of the list”; “Move up” and “Move down” — your own order of lists. Servers keep no order of lists; fedtail remembers it, new ones go to the end.

**Into a list — the author or the booster; only people you follow.** A boost's ⋯ menu has two items: “Author to a list (@…)” and “Booster to a list (@…)” — a relay bot is a person too, as far as a list goes. The server takes into lists only people you follow: for the rest the lists in the submenu are dead (they don't click at all), signed “follow first”, with a “Follow” item. Right click on the “♻ boosted by …” line — the booster's profile or “To a list”; the name on that line links to the profile.

**Into a list right after a follow.** The server won't take into a list someone you don't follow yet (the request waits with a locked account). fedtail remembers which list you wanted them in and adds them itself as soon as the follow is confirmed.

**Hashtag lane, following tags.** A click on a #tag opens its lane inside (with `ui.links_in_app`). Follow a tag — with the button in its lane's header; the server mixes followed tags into Home, and fedtail offers them first when you type `#`.

**My likes.** The posts you liked. The lane is off by default.

**Bookmarks.** “Bookmark” — with the button under a post (`ui.bookmark_button = false` moves it into the ⋯ menu), the `m` key or the command `~ #a3f`. The server keeps bookmarks, so they are shared with other clients.

**Trends.** Popular tags, links and posts, as your server counts them. GoToSocial doesn't count trends.

**An empty live lane says why it's empty.** If the server turned the public timelines off (or gives them to its own users only), Federated and Local don't hang empty in silence: fedtail says the server turned them off.

**Filtering a lane by media and boosts.** Over a lane you can leave only text, only pictures, gifs, video or only boosts. It's a quick look, not a setting: after a restart everything is as it was.

**Repeated boosts don't bring an old post up again.** A post comes into a lane once — as itself or with its first boost. A boost of a post this lane has had already, or one already read (in a thread, in another lane), is not shown and not counted as unread; the post stays where it first came. `repeat_boosts = true` — every boost again, as everyone does. The server (Mastodon) drops a repeat only if the original was among the last ~40 posts of the feed — that's why old posts kept surfacing again and again.

**All / Posts only / New; Feed / Conversations.** Over a lane, two switches. “All / Posts only / New”: with all the comments, only top-level posts, or only what's unread. “Feed / Conversations”: “Conversations” gathers a thread into one card, like conversations on Point. In which lanes “posts only” is on from the start — `lanes.posts_only`. Remember the choice between runs — `feed.remember_choices = true`; by default every run starts afresh.

**Find in a lane.** `Ctrl+F` finds in the open lane by text, nick, `#id` and picture captions. It searches its own database and doesn't ask the server, so it works offline too. `Enter`, `↓`, `F3` or `Ctrl+F` again — to the next match, `Shift+Enter` — to the previous one.

**Find in every lane at once.** The “In every lane” tick in the `Ctrl+F` bar: you remember a phrase but not where you saw it. It searches everything stored in every lane at once (in the sidebar's order, newest to oldest in each, a post once), the counter says which lane the match is in; the next match opens its lane by itself and loads it down to the post. The tick is remembered.

**Finding people, tags and posts.** Search on the server: people, tags, posts (as far as the server indexes them), and a link to a post or a profile — the server finds it and fetches it.

**A lane of several tags.** Type `#грузия #georgia -#politics` in the search: one lane of all these tags opens — any of them, `+#tag` must be there, `-#tag` — without. The “＋ to lanes” button keeps it on the left, in the “Tags” group; it is fetched while open, like Federated. The same lanes can be described in the config, `[[lanes.tag_groups]]` (name, any, all, none). The server needs a request per tag (GoToSocial reads only one tag at a time), fedtail puts them together itself, without repeats.

**Columns side by side.** Several lanes on screen at once, in columns. By default — one lane at a time; the ❯ button at the top left (next to ≡ and ↔) turns columns on for now, and the window starts as `ui.layout` says. A click on a lane on the left adds a column (or scrolls to it), ✕ takes it away, ‹ › move it; the set is remembered. These are the same lanes as in the single view: place, filters and read marks are each their own, and Federated and the other browse lanes keep updating while they stand in a column.

**A messenger's layout: a roster and a messages window.** fedtail as a messenger of the 2000s — QIP, the Mail.ru Agent, Psi. The **roster** is a narrow window, and fedtail starts with it: me and “N new in Activity” on top, a search line, folding groups — the lanes, followed threads and private talks (“Threads”, “Talks”, the freshest `ui.roster_threads`) and “People” — whom I follow who follows me back (asked once a day). A group says “(15)”, or “(2/15)” when two of its items have something new; an item has its count, a line of its newest post and a face. A double click or Enter opens it, hovering a person shows their card, as in QIP. At the bottom the menu, the accounts and ⚙ — how the roster looks: compact, without the header, the search or the buttons, only what's new, without groups, above other windows (`ui.roster_on_top`). Closing the roster closes fedtail (to the tray with `ui.close_to_tray`); the tray icon hides and brings back both windows. The **messages window** is the main window without the sidebar: every lane, thread, profile and talk opened is a tab of its own, in more rows when they don't fit; ×, the middle button or Esc close one, and with the last the window goes (`ui.split_tabs` — whether to keep the tabs for next time). A person opens as a talk with only our private messages. The **input line** is always under the posts, a bar that drags between them: in a thread it answers the thread (a private talk stays private), in a talk it writes to that person privately, in a lane — a new post; Reply on a card leads here too. Who sees it, a content warning, pictures, the language; it also takes the command line's commands (`ui.dock_commands`: “#a3f text”, “! #a3f”, “?” — Enter). **Faces** (`ui.faces`): over a lane, in one line, the author of the post under the pointer (or the cursor, or the newest whole on screen): name, address, whether we follow each other, Follow, Add to list, a private message, the profile; by the input line — whom I write to. The Agent's themes have a column on the right instead: theirs by the posts, mine by the input line. A grey silhouette while there's no face. **Pictures on buttons** — the messengers', from the theme's set (`ui.icons`): on the input line, the author's bar, the roster (only in the split layout, or anywhere with `"additional"`), and on Reply, Favourite, Boost, Thread, Bookmark, who sees a post, the menu and the lanes in any layout; a flower for a person in the QIP themes, an “@” in the Agent's, a star in Psi's; the `psi` theme brings Psi+'s own pictures (the Crystal and Stellar iconsets, GPL). The theme decides how it all looks: the faces — `shape.faces`, the roster's items — `roster_rows`, the tabs — `tab_rows`, the pictures — `shape.icons` and the theme's `icons/` folder (docs/en/dev/layouts.md).

**Collections (Mastodon 4.6).** Shared sets of accounts. Coming once GoToSocial has them.

</details>

---

## Threads

| What | Status | Since | Config | API / protocol | Others |
|---|---|---|---|---|---|
| A thread as a tree, comments numbered | has | 0.1.0 | — | `statuses/:id/context` | Phanpy — indented; numbers only in fedtail |
| Over a reply — what it answers | has | 0.1.0 | `feed.show_reply_context` | `in_reply_to_id` | Sengi and Megalodon — similar |
| A whole thread: replies from the author's server | has | 0.3.0 | `feed.complete_threads` | the `replies` collection over ActivityPub, `search?resolve=true` | only in fedtail (Mastodon 4.5+ does it on the server) |
| A thread grows when Mastodon has gathered the replies | has | 0.8.0 | `feed.complete_threads` | the `Mastodon-Async-Refresh` header | Mastodon web |
| Thread subscriptions, as on Point | has | 0.2.0 | `[subs]`: `auto`, `interval_minutes`, `active_days`, `max_threads`, `replies_to_me`, `leave_mutes` | own | only in fedtail |
| Mute a thread | has | 0.11.0 | — | `statuses/:id/mute` and own | Mastodon web, Tusky, Ivory |
| Long texts and events | has | 0.14.0 | `feed.long_form` | ⋯ → “📄 Read it whole”: `Article`, `Page`, `Event` from the author's server | — |

<details><summary>In detail</summary>

**A thread as a tree, comments numbered.** A thread opens as a tree: every reply under what it answers, every comment numbered `/1`, `/2`, `/2/1`, as on Point and Juick. The command line can address a comment by its number.

**Over a reply — what it answers.** Over a reply in a lane, a strip “↪ in reply to…” with the start of the original post; a click opens the whole thread. No reply in a lane hangs as a scrap.

**A whole thread: replies from the author's server.** Your server knows only the replies that reached it, so other people's threads have holes. Open a thread — fedtail reads the list of replies straight from the author's server and asks your server to fetch what's missing; the thread grows by itself a couple of seconds later. Requests to other servers go without your token. `false` — make do with what your own server knows.

**A thread grows when Mastodon has gathered the replies.** Mastodon 4.5+ gathers missing replies itself and says when it's done; fedtail waits for that signal and rereads the thread.

**Thread subscriptions, as on Point.** The server tells you only of replies that mention you: if two people answer each other under your post, you won't know. fedtail itself rereads the threads you're subscribed to every `subs.interval_minutes` minutes (a thread quiet for an hour — three times less often, for a day — 12 times, for three days — 36) and puts what's new into the “Subscriptions” lane. Threads take at most a quarter of what the server still allows in its rate-limit window: the lanes come first. Subscribe — in a post's ⋯ menu, with the button in the thread's header or the command `S #a3f` (`U #a3f` — unsubscribe). `subs.auto` — what to subscribe to by itself: `"posts"` — your own posts, `"comments"` — threads you comment in. A thread quiet for `subs.active_days` days is not checked any more; one round checks at most `subs.max_threads` threads. Replies to you come to “Replies to me” anyway; `subs.replies_to_me = true` — show them in “Subscriptions” too. Unsubscribing mutes the thread's mentions as well (replies there tag everyone in it by themselves); `subs.leave_mutes = false` — leave “Subscriptions” only.

**Mute a thread.** Notifications from the thread stop coming and its subscription goes. A server that can do it remembers it for all clients; where it can't (GoToSocial), fedtail mutes the thread itself: its mentions are dropped as they come — even replies to posts of the thread it never saw. The item in a post's ⋯ menu is always there.

**Long texts and events.** Articles from WriteFreely, Ghost, Plume, Lemmy posts, Mobilizon events. The Mastodon API flattens them into an ordinary post with the text cut. The ⋯ menu of such a post has “📄 Read it whole”: fedtail takes the full text straight from the author's server over ActivityPub, for an event — also the time and the place.

</details>

---

## Read marks and place

| What | Status | Since | Config | API / protocol | Others |
|---|---|---|---|---|---|
| Oldest on top, nothing jumps | has | 0.1.0 | `feed.order`, `feed.start_at`, `feed.on_new` | own | only in fedtail |
| Catching up with no holes | has | 0.1.0 | `feed.page_size`, `feed.catch_up_limit` | `min_id` | only in fedtail |
| When a post counts as read | has | 0.1.0 | `read.mark_read`, `read.read_button` | own | only in fedtail (the manual mode) |
| Your own posts are always read | has | 0.13.0 | — | own | — |
| The first run doesn't start with a pile | has | 0.1.0 | `feed.first_run_mark_read` | own | — |
| The reading place is shared with other clients | has | 0.8.0 | `read.sync_markers` | `/api/v1/markers` | Mastodon web, Tusky, Ivory, Phanpy, Ice Cubes |
| Read marks, thread subscriptions and lane order shared by all your devices | has | 0.18.0 | `sync.url` or `sync.folder` (none — no sync), `sync.read`, `sync.threads`, `sync.lanes`, `sync.drafts`, `sync.activity`, `sync.tiles`, `sync.interval_seconds`; `fedtail sync status\|key\|join\|login\|now` | own: a fedtail-sync server (one file, `syncserver/fedtail_sync.py`) or a shared folder; it is entered with a `read:accounts`-only token | only in fedtail (markers are just the place in Home and notifications) |
| Cards are built around the reading place | has | 0.11.0 | `feed.build_at_once`, `feed.render_limit` | own | only in fedtail |
| Esc draws a curtain instead of closing the window | has | 0.3.0 | `ui.esc`, `ui.start_lane` | own | only in fedtail |

<details><summary>In detail</summary>

**Oldest on top, nothing jumps.** `feed.order = "oldest_first"` — oldest on top, you read downwards, like RSS or Point (`"newest_first"` — as everyone does). `feed.start_at = "first_unread"` — open a lane and you stand at the first unread (`"newest"` — at the freshest). `feed.on_new = "keep_position"` — new posts come and the place doesn't move, only the counter grows (`"jump_to_newest"` — jump to the new).

**Catching up with no holes.** Lanes meant to be read to the end catch up forward from the last known post, page by page (`page_size` posts a request, up to `catch_up_limit` a poll — the rest on the next one). So the local copy has no holes and you can read strictly in order. The “load what's missing” button other clients keep fixing (Fedilab in 2026 — half a dozen fixes about holes and jumps, some on GoToSocial) isn't needed here.

**When a post counts as read.** `"on_scroll"` — when you've scrolled past the whole post; `"on_open"` — the whole lane as soon as you open it; `"manual"` — by hand only: “All read” over the lane, “Mark read” and “Read up to here” (this one and everything older) in the ⋯ menu. In the manual mode a lane always waits exactly where you stopped, even reading one post at a time. `read.read_button = true` — a ✓ button under each unread post. The menu items work in any mode.

**Your own posts are always read.** A post you wrote is read, wherever it came from: from Tusky at night, through a thread, fetched after a restart.

**The first run doesn't start with a pile.** At the very first run, everything fetched counts as read.

**The reading place is shared with other clients.** Read Home or mentions to the end on the phone — here it's read too, and the other way round. Works with Mastodon, GoToSocial, Akkoma — if that client tells the server its place: Mastodon's web, Ivory, Phanpy do; Tusky keeps its place in Home to itself and shares only notifications. `false` — read marks live in fedtail only.

**Read marks, thread subscriptions and lane order shared by all your devices.** Read a post on the laptop — it's read on the desktop; follow a thread, leave it or mute it, move a list or save a tag lane — so it is on the other devices. Sync is a service of its own: it works only when the config has `sync.url` (or `sync.folder`); without it there is none, and the right of the status bar says so (“⇅ off”, “⇅ 21:40”, “⇅ !”), as does About. Marks fedtail makes by itself (everything read on the first run, older history, your own posts) stay home: a new device won't read the desktop for you. Each device writes a journal of what it did; the journals meet on a fedtail-sync server or in a folder all the devices see (a NAS share, WebDAV, Syncthing). The journals are sealed with a key only your devices have: the store doesn't see what you read. The first device makes the key; `fedtail sync key` shows it, `fedtail sync join` carries it to another. To the sync server fedtail gives not its own token but a separate one that can only tell “who am I” (`fedtail sync login`). Setting up a server of your own — docs/en/sync.md.

**Cards are built around the reading place.** When a lane opens, `build_at_once` cards are built around where you read; the rest — as you scroll near an edge, and far behind they are let go (more than three `build_at_once` — back to one behind and two ahead). What you read doesn't move; a filter and “unread only” also build only around the reading place. At most `render_limit` latest posts are kept on screen, older ones with the “older” button. `0` in `build_at_once` — build everything at once (on hundreds of posts that takes seconds).

**Esc draws a curtain instead of closing the window.** Esc closes what's on top (a picture, the search), and the last Esc with `ui.esc = "curtain"` draws a curtain over all lanes: the window stays, the counts on the left, nothing on the right, and nothing is marked read — open it in the morning and the new has piled up. `"tray"` — off to the tray, `"off"` — nothing. What to start with — `ui.start_lane`: `"none"` (the curtain, Enter opens the last one), `"last"` or a lane's name.

</details>

---

## The post card

| What | Status | Since | Config | API / protocol | Others |
|---|---|---|---|---|---|
| Arts mode | has | 0.11.0 | `ui.arts_mode` (on by default, recommended) | — | nobody has it as one switch |
| Content warnings (CW) | has | 0.1.0 | `ui.expand_cw` | `spoiler_text` | everyone can set it |
| Open every CW in a thread at once | has | 0.18.0 | — | own | Sengi, Megalodon (the same CW across a thread) |
| Sensitive pictures | has | 0.8.0 | `feed.sensitive_media` | `status.sensitive` | everyone |
| Link cards | has | 0.8.0 | `feed.link_cards` | `status.card` | everyone |
| Servers' emoji as pictures | has | 0.8.0 | `feed.custom_emoji` | `emojis` of the post and the account | everyone |
| No emoji at all | has | 0.15.0 | `feed.emoji = false` — no server pictures, no Unicode ones, no reactions; a name made only of emoji shows the login | — | Tusky (animation only), Fedilab (only servers' own emoji) |
| Quotes: showing them | has | 0.8.0 | `feed.quotes` | `status.quote` | Mastodon 4.5+, Ivory, Phanpy, Elk, Ice Cubes, Fedilab |
| Polls: seeing and voting | has | 0.3.0 | — | `polls/:id`, `polls/:id/votes` | everyone |
| Poll results without voting | has | 0.3.0 | — (the “Results” button of a poll) | — | Fedilab |
| Edit history | has | 0.3.0 | — | `statuses/:id/history` | Mastodon web, Ivory, Phanpy, Elk, tut |
| Translation by the server | has | 0.8.0 | `feed.translate` | `statuses/:id/translate` | Mastodon web, Ivory, Phanpy, Elk, Ice Cubes, Fedilab |
| Emoji reactions | partly — shown only | 0.11.0 | — | `pleroma.emoji_reactions` | Phanpy, Elk, Fedilab |
| Who liked and boosted | has | 0.11.0 | — | `favourited_by`, `reblogged_by` (and from the author's server) | Mastodon web, Tusky, Ivory, Phanpy, Elk, tut |
| Honest counters | has | 0.2.0 | `feed.honest_counters` (off), `feed.counters_via_accounts` | the author's server's API without a token | only in fedtail |
| Who quoted my post | has | 0.11.0 | — | `statuses/:id/quotes`, `…/quotes/:id/revoke` | Mastodon 4.5+ |
| Folding hashtag padding | has | 0.14.0 | `feed.collapse_tags` | own | Phanpy |
| `~~text~~` struck out when the server knows no Markdown | has | 0.14.0 | `feed.text_markup` | own | — |
| Labels on the card | has | 0.14.0 | `feed.old_days`; “bot” — always | own | Sengi |

<details><summary>In detail</summary>

**Arts mode.** Everything as the author posted it, no nannying. Turns on at once: content warnings (CW) open, “sensitive” pictures without a cover, server filters neither hide nor fold posts, no “Report” item. Your own mutes and blocks work as usual; what the server itself cuts off (domain blocks) never reaches a client — that can't be got round. `false` — everything as everyone has it, and then each of these is set on its own (`ui.expand_cw`, `feed.sensitive_media`).
Named after @arts — the founder of Point.im and the author of its rules. The principle comes from there too: on a grown-up site grown-ups sort things out themselves. Anyone can be told where to go, an admin too — and the admin can say the same back.

**Content warnings (CW).** `true` — text and pictures under a CW open at once; `false` — folded, opened with the “show” button.

**Open every CW in a thread at once.** Not needed with arts mode on. If people who turned it off ask — a button in the thread's header.

**Sensitive pictures.** Pictures the author marked sensitive (without a CW): `"hide"` — under a cover, a click shows them; `"show"` — seen at once. Under a CW they are hidden together with the text anyway.

**Link cards.** The title, description and picture of the page a post links to (the server collects them): `"full"` — with the picture, `"text"` — a line or two, `"off"` — not shown. A post with its own pictures has no card.

**Servers' emoji as pictures.** `:blobcat:` and the rest — as pictures in posts and names. `false` — leave them as text and don't fetch the pictures.

**Quotes: showing them.** A post inside a post (Mastodon 4.5+, Akkoma, Misskey and others): `"card"` — framed inside, `"link"` — a line with a link, `"off"` — as the server sent it (usually “RE: link”).

**Polls: seeing and voting.** Options, percentages, the deadline; voting for one or several options, as the author set.

**Poll results without voting.** The “Results” button next to “Vote” — look without voting.

**Edit history.** An edited post is marked so and has all its earlier versions.

**Translation by the server.** “Translate” in the ⋯ menu of a post in another language — if your server can (Mastodon with DeepL or LibreTranslate). The translation is right in the card, with an “original” button.

**Emoji reactions.** Reactions from Akkoma, Pleroma, Misskey and their forks show under the post. Adding your own isn't possible yet; GoToSocial doesn't support them.

**Who liked and boosted.** Lists of people at the counters. If your server doesn't know everyone, the rest is read from the author's server.

**Honest counters.** Your server knows only the likes and boosts that reached it, so the numbers on other people's posts are low. With `honest_counters = true`, when a thread opens fedtail asks the author's server for the real numbers — without a token, but with your IP. If that server won't give numbers without a login and you have other accounts (profiles), `counters_via_accounts` lets it ask as them: the author's server, if you have an account there, or a server that already has the post. Each account's token goes only to its own server.

**Who quoted my post.** The list of quotes of my post and “take my post out of this quote”.

**Folding hashtag padding.** A paragraph of nothing but hashtags (more than three) in a lane folds into the first three and “… +N” in small type; in an open thread it's whole, but small too. Hashtags inside the text aren't touched.

**Boost carousel.** Boosts in a row — as one strip scrolled sideways (as in Phanpy). Won't do: sideways is awkward to read, and it fits badly with “nothing jumps” and read marks. The same job is done by the “Boosts” tick in the filter, “without their boosts” on a profile and relays in a list of their own.

**Labels on the card.** Next to the date: “old, N days” — a post older than `feed.old_days` (30) days; such posts come from someone's outbox or an old thread; “[bot]” — on bots. There is no “from another server” label yet.

</details>

---

## Pictures and video

| What | Status | Since | Config | API / protocol | Others |
|---|---|---|---|---|---|
| Picture viewer | has | 0.1.0 | `ui.image_viewer`, `ui.image_upscale`, `ui.image_height` | — | everyone |
| Picture grid | has | 0.9.0 | `ui.media_grid` | `meta.focus` | Mastodon web, Tusky, Phanpy, Elk |
| Picture descriptions (alt) | has | 0.9.0 | `ui.alt_text` | `description` | everyone |
| Video, audio, gifs inside the window | has | 0.11.0 | `ui.video_player`, `ui.gifv` | `media_attachments` | everyone |
| Video without a hardware decoder (the default) | has | 0.16.0 | `ui.video_decode` | — | only in fedtail |
| Save a picture, video, gif | has | 0.2.0 | `ui.save_dir` | — | Tusky, Ivory |
| Pictures and video ahead of time, a disk cache | has | 0.13.0 | `feed.prefetch`, `ui.image_disk_mb`, `ui.video_disk_mb` | own | only in fedtail |
| Memory for pictures | has | 0.2.0 | `ui.image_cache_mb`, `ui.image_decode` | own | — |

<details><summary>In detail</summary>

**Picture viewer.** A click on a picture — its own viewer (`"internal"`: ← → to flip, Esc to close) or the browser (`"browser"`). Small pictures are enlarged to the window at most `image_upscale` times. The height of a single picture in a lane — `image_height`.

**Picture grid.** Several pictures in a post: `"natural"` — each whole, its own shape; `"square"` — an even grid of squares cut around the author's focus point. A single picture is never cut.

**Picture descriptions (alt).** `"tooltip"` — on hover; `"caption"` — also as a caption under the pictures. Descriptions are found by `Ctrl+F`.

**Video, audio, gifs inside the window.** A video plays over the window (Space — pause, ← → — seek, M — sound, O — to the browser, Esc — close), audio — with a player in the card. Needs QtMultimedia (Debian: `python3-pyside6.qtmultimedia python3-pyside6.qtmultimediawidgets`); without it — a still frame with ▶ and the browser. Mastodon's gifs (short silent videos): `"play"` — loop in the card while it's on screen (at most three at once), `"click"` — a still frame, a click plays it over the window.

**Save a picture, video, gif.** The ⤓ button, the S key in the viewer, a right click on a picture in a lane. `""` — into the desktop's Downloads.

**Pictures and video ahead of time, a disk cache.** As soon as a poll brings new posts, their pictures are fetched to disk by background workers of their own — open a lane and everything is there. `"previews"` (the default) — previews (of videos too), avatars and link pictures; `"all"` — also originals, the videos themselves and gifs (videos one at a time, up to 300 MB each); `"off"` — only when a post is on screen. The picture cache keeps within `image_disk_mb` (1 GB), videos — in their own folder, `video_disk_mb` (10 GB); over the limit go the ones not opened the longest. A video opened once plays from disk the next time.

**Memory for pictures.** Decoded pictures are held in memory up to `image_cache_mb` MB, the oldest thrown out first (reread from disk at once). `image_decode = "box"` — decode to the size of the frame, minding the screen's density: several times less memory; `"full"` — up to 1200 pixels on the longer side, sharper when the window is stretched.

</details>

---

## Profiles

| What | Status | Since | Config | API / protocol | Others |
|---|---|---|---|---|---|
| Your own and other people's profiles | has | 0.2.0 | — | `accounts/:id`, `accounts/:id/statuses` | everyone |
| Pinned posts | has | 0.8.0 | `feed.profile_pinned` | `statuses?pinned=true` | everyone |
| Featured tags and recommended people | has | 0.9.0 | `feed.profile_featured` | `featured_tags`, `endorsements` | Mastodon web |
| A little-known person's profile — from their server | has | 0.8.0 | `feed.remote_profiles`, `feed.remote_posts` | ActivityPub outbox | Megalodon — partly (the lists) |
| Posts older than my server knows | has | 0.11.0 | `feed.remote_profiles` | ActivityPub outbox | only in fedtail |
| Followers and follows from the person's server | has | 0.8.0 | `feed.remote_people` | ActivityPub `followers`, `following` | Megalodon |
| “Following since …” | has | 0.11.0 | `feed.follow_date_note` | `accounts/:id/note` | only in fedtail |
| The person has moved | has | 0.14.0 | `feed.show_moved` | `account.moved`, ActivityPub `Move` | Mastodon web |
| The author's server software | has | 0.14.0 | `feed.server_info` | nodeinfo, in the profile “🖥 GoToSocial 0.17” | — |
| What my server can do | has | 0.17.0 | ≡ → account → “Server info” → “What it can do” → “Check” | one harmless GET with `limit=1` per feature | — |

<details><summary>In detail</summary>

**Your own and other people's profiles.** The header, bio, fields, counts, posts; “followed by people you follow” (`familiar_followers`); follows and followers.

**Pinned posts.** At the top of a profile, marked 📌. `false` — the profile simply in time order.

**Featured tags and recommended people.** “Often writes about: #tags” and whom the person recommends (Mastodon 4.4+).

**A little-known person's profile — from their server.** If your server knows almost nothing about a person from another server, fedtail reads their latest public posts straight from there (`remote_posts` of them, at most 40) and asks your server to fetch them. Without a token; servers that require signed requests simply give nothing.

**Posts older than my server knows.** Your server knows a person's posts only from the moment someone on it followed them. fedtail pages through older ones straight from the author's server.

**Followers and follows from the person's server.** At the bottom of such lists — a “more from their server” button: fedtail reads them there and finds these people through your server.

**“Following since …”.** Servers don't keep the day you followed someone. When you follow through fedtail, the date is written as the last line of your private note on the person (`[fedtail followed 2026-10-18]`): it's seen from any device and in other clients. In fedtail the line is hidden and kept when the note is edited. `false` — remember it locally only.

**The person has moved.** A moved person's profile has a “📦 Moved to @new” banner with “Open” and “Follow there” buttons.

**The author's server software.** fedtail asks the person's server for its nodeinfo (Mastodon, GoToSocial, Akkoma, Misskey, Lemmy…) and writes “🖥 GoToSocial 0.17.3” in the profile. The answer is kept a week per server.

**What my server can do.** A score of “show me one” requests (nothing changes on the server), a few seconds in the background — the window doesn't freeze. Each feature gets an answer: yes, no, there but closed to me, unclear; limits (characters, attachments, poll options) as numbers. What can't be asked without changing something (dismissing one notification, muting a thread) is told from what server this is. The last check is kept and shown at once; the answers also tell fedtail which buttons to show.

</details>

---

## Writing

| What | Status | Since | Config | API / protocol | Others |
|---|---|---|---|---|---|
| The compose panel and drafts | has | 0.1.0 | `ui.compose`, `ui.compose_size`, `post.drafts_autosave` | `statuses` | everyone |
| Visibility: private by default, a reply never wider than the post | has | 0.1.0 | `post.default_visibility`, `post.reply_never_wider` | `visibility`, `/api/v1/preferences` | only in fedtail (never wider) |
| Markdown | has | 0.1.0 | `account.markdown`, `post.plain_posts` | `content_type` | GoToSocial and Akkoma clients |
| Preview before sending | has | 0.14.0 | `post.preview` | own | Fedilab |
| Content warning (CW) | has | 0.2.0 | `post.cw_field` | `spoiler_text` | everyone |
| Pictures: drag, paste, description, focus | has | 0.2.0 | `post.alt_reminder`, `post.focus_point` | `/api/v2/media`, `focus` | everyone (focus — Mastodon web, Ivory) |
| Shrinking pictures to the server's limit | has | 0.14.0 | `post.resize_images` | `instance.configuration.media_attachments` | Fedilab |
| Completing #tags, @nicks, :emoji: | has | 0.7.0 | `post.complete_tags`, `post.complete_mentions`, `post.complete_emoji` | `accounts/search`, `custom_emojis` | everyone |
| CamelCase hint for hashtags | has | 0.2.0 | `post.camelcase_hint` | own | only in fedtail |
| The post's language | has | 0.3.0 | `post.language`, `post.languages` | `language` | everyone |
| A poll in a post | has | 0.8.0 | — | `poll[options]` | everyone |
| Call someone into a thread | has | 0.16.0 | `post.invite` | a reply with a mention | only in fedtail (in others — by hand) |
| Reply with quotes, piece by piece | has | 0.17.0 | `post.quote_prefix` | own (the reply's text) | Thunderbird and mail clients — for mail; no fediverse client |
| Copy the handle @user@server | has | 0.16.0 | — | own | Mastodon web (Copy handle) |
| Quoting a post; who may quote mine | has | 0.8.0 | `post.quote_action`, `post.quote_policy` | `quoted_status_id`, `quote_approval_policy` | Mastodon 4.5+, Ivory, Phanpy |
| Who may reply, boost, like (GoToSocial) | has | 0.8.0 | `post.who_can_reply`, `post.who_can_boost`, `post.who_can_like` | `interaction_policy` | GoToSocial clients |
| A scheduled post | has | 0.8.0 | `post.schedule` | `scheduled_at`, `scheduled_statuses` | Mastodon web, Ivory, Phanpy, Megalodon |
| Edit, delete, pin your own post | has | 0.3.0 | — | `PUT statuses/:id`, `statuses/:id/source`, `statuses/:id/pin` | everyone |
| Delete and redraft | has | 0.14.0 | `post.redraft` | `statuses/:id/source` + `DELETE statuses/:id` | Mastodon web, Megalodon |
| A thread as a chain | has | 0.14.0 | `post.chain` | `in_reply_to_id` | Ice Cubes (up to five posts) |
| A command line as on Point | has | 0.3.0 | `ui.command_line`, `post.plain_posts` | own | only in fedtail (tut — vim-style commands) |
| Short post names the same on every device | has | 0.18.0 | — | own | only in fedtail (Point had the server's post numbers) |

<details><summary>In detail</summary>

**The compose panel and drafts.** `ui.compose = "inline"` — a panel inside the main window (the keyboard layout isn't reset: KDE keeps it per window); `"window"` — a window of its own. The panel's size — in percent of the window (`compose_size`), the ⤡ button switches normal and big. Drafts are saved as you type and survive closing.

**Visibility: private by default, a reply never wider than the post.** A new post goes to followers by default (`"private"`); `"server"` — as set on the server. A reply is never more public than the original post.

**Markdown.** `"auto"` — ask the server; GoToSocial and Akkoma understand Markdown, vanilla Mastodon doesn't.

**Preview before sending.** The “👁 Preview” button in the panel: the Markdown already rendered (if the server understands it), the CW, visibility, language, each part of a chain, how many pictures; “Send” or “Edit” from there.

**Content warning (CW).** The CW field is open at once or hidden behind the “⚠ Warning” button. In a reply, the original post's CW is filled in by itself.

**Pictures: drag, paste, description, focus.** Drag a file in or paste from the clipboard. A double click on a picture — the description and the focus point. A picture without a description — before sending, ask “Describe” or “Send as is”. Marking pictures sensitive — with a tick.

**Shrinking pictures to the server's limit.** The server says what picture it takes (in pixels and bytes). Bigger — before the upload fedtail shrinks a copy to the pixel limit and recompresses it as JPEG (with transparency — PNG) under the byte limit, instead of being refused. Your file isn't touched, gifs aren't flattened. `post.resize_images = false` — as is.

**Completing #tags, @nicks, :emoji:.** `#ge` — first the tags you follow, then the frequent ones in the lanes. `@ar` — first the people seen most in the lanes, then those the server finds. `:co` — the server's emoji, Tab or Enter puts it in.

**CamelCase hint for hashtags.** A hashtag in one case (`#georgianews`) gets a hint: screen readers read `#GeorgiaNews` word by word.

**The post's language.** The default language and a list in the post window (any ISO 639 code; “Another language…” adds to the list for good).

**Call someone into a thread.** A post's ⋯ menu → “Call into the thread…”: a reply to this post with only “@” in it so far and the people list open at once — pick whom (several are fine), write a couple of words. The person gets a notification, a click — and the thread is open on their side, on their server, ready for a reply; no scary links with service ids. The thread's other participants aren't mentioned, the call has its own draft. If the thread isn't public, the person called sees your reply, and the rest only as far as they could anyway. The same from the command line: `#a3f @whom take a look`.

**Reply with quotes, piece by piece.** A post's ⋯ menu → “Reply with quote”: a reply with the post's text already in it as a quote (`> `, the leading mentions left out), or only what's selected in the post. A right click on a selection → “Quote in reply”. With a reply to this post already open, the quote goes where its cursor is, an empty line after it: select a sentence, quote, answer, select the next one — and so on through the post. The quote's line start is `post.quote_prefix`; `""` — no such items.

**Copy the handle @user@server.** The “Copy handle” button on a profile, the “Copy handle @…” item in a post's ⋯ menu (the author and, for a boost, the booster) and in the menu of the “♻ boosted by” line. Always the full `@user@server`: people from your server come as just `user`, your server's name is added — any client can find and mention a person by such a handle.

**Quoting a post; who may quote mine.** “Quote” in the ⋯ menu of a post its author lets quote. Who may quote my new posts: `"public"`, `"followers"`, `"nobody"` or `""` — as on the server.

**Who may reply, boost, like (GoToSocial).** `"everyone"`, `"followers"` (and the mentioned), `"following"` (and the mentioned), `"mentioned"`, `"me"` or `""` — as in the account's settings. Not sent to other servers.

**A scheduled post.** The “⏰ Later” button: the post waits on the server, even if fedtail is closed. The list of waiting ones — ≡ → “Scheduled”.

**Delete and redraft.** An item in the ⋯ menu of your own post: the post is deleted, and its text (as typed), CW, visibility, language and what it answered open in the panel as a new draft; the server deletes the pictures with the post, you add them again — for servers without editing and for when an edit won't do (changing visibility).

**A thread as a chain.** A line of nothing but `---` splits the text into posts: they go at once, each a reply to the one before, with the same visibility, CW and language; pictures and the poll go with the first. The character counter counts each part on its own. `post.chain = false` — `---` stays text.

**A command line as on Point.** At the bottom of the window (`Ctrl+L`): `#a3f` — open, `#a3f text` — reply, `S`/`U #a3f` — subscribe to a thread, `S`/`U @nick` — follow a person, `!` — boost, `~` — bookmark, `D` — delete your own, `@nick` — profile, `?` — help. Plain text without a command — a new post (`post.plain_posts = false` — commands only, no accidental posts).

**Short post names the same on every device.** A name like `#kq3zt` is derived from the post's id, so the same post is called the same on the desktop, the laptop and the phone — read it out on one, open it on another. Five characters; when two known posts begin the same, their names are shown longer. Names fedtail gave earlier (three or four characters, by a counter) stay with their posts and still open them.

</details>

---

## People and order

| What | Status | Since | Config | API / protocol | Others |
|---|---|---|---|---|---|
| Follows and follow requests | has | 0.1.0 | `"requests"` in `lanes.enabled` | `follow`, `follow_requests` | everyone |
| Hide a person's boosts; the languages of a follow | has | 0.14.0 | `feed.per_person_follow` | `follow` with `reblogs=false`, `languages[]` | Mastodon web, Tusky, tut |
| Mute, block, word filters | has | 0.3.0 | — | `mutes`, `blocks`, `/api/v2/filters` | everyone |
| Block a whole server | has | 0.8.0 | — | `/api/v1/domain_blocks` | Mastodon web, Ivory, Phanpy |
| Report to the moderators | has | 0.8.0 | `post.report_forward` | `/api/v1/reports` | everyone |
| A private note on a person | has | 0.8.0 | — | `accounts/:id/note` | Mastodon web, Ivory, Ice Cubes |
| A bell on a person's posts | has | 0.8.0 | `"status"` in `activity.types` | `follow notify=true` | Mastodon web, Tusky, Ivory, Megalodon |
| Remove from followers without a block | has | 0.11.0 | — | `remove_from_followers` | Mastodon web, Ivory |
| Recommend people and tags on your own profile | has | 0.11.0 | — | `endorse`, `featured_tags` | Mastodon web |
| The server's suggestions, the profile directory | has | 0.11.0 | — | `/api/v2/suggestions`, `/api/v1/directory` | Mastodon web, Tusky, Ivory |
| About the server | has | 0.11.0 | — | `instance`, `instance/rules`, `extended_description` | Mastodon web, Ivory, Phanpy |
| Your profile | has | 0.2.0 | — | `update_credentials` | Mastodon web, Ivory, Phanpy, Elk, Tokodon, Ice Cubes |
| Post visibility as set on the server | has | 0.11.0 | `post.default_visibility = "server"` | `/api/v1/preferences` | Mastodon web, Ivory |

<details><summary>In detail</summary>

**Follows and follow requests.** Follow, unfollow, accept or reject a follow request (the “Follow requests” lane).

**Hide a person's boosts; the languages of a follow.** On the profile of someone you follow: “♻ without their boosts” and “🌐 languages” — only their posts in these languages. The server keeps it, so it works in every client.

**Mute, block, word filters.** Word filters are the server's, v2: where they apply, for how long, hide or fold. All this — in the ≡ menu → “For the tender and sensitive”: word filters, muted, blocked, blocked servers and filtered notifications; with `ui.arts_mode`, a line on top says the server's filters don't apply there.

**Block a whole server.** Nobody from there in any lane, follows across the border are cut.

**Report to the moderators.** About a person from another server — a “forward to their server too” tick (they won't learn who reported). In arts mode the item isn't there.

**About the server.** The description, rules, privacy policy.

**Your profile.** Name, bio, fields, avatar, header.

</details>

---

## Notifications and activity

| What | Status | Since | Config | API / protocol | Others | Note |
|---|---|---|---|---|---|---|
| Desktop notifications with privacy levels | has | 0.2.0 | `[notify]`: `enabled`, `lanes`, `except`, `privacy`, `when_focused`, `backend` | own | only in fedtail (Tokodon — without privacy) | — |
| Activity: likes, boosts, follows | has | 0.2.0 | `activity.types` | `/api/v1/notifications` | everyone | — |
| Grouping notifications | has | 0.2.0 | `activity.types`, `activity.server_groups` | its own grouping; since 0.18 the server's too, `/api/v2/notifications` (Mastodon 4.3+) | Mastodon web, Ivory, Phanpy, Ice Cubes | — |
| Approve a reply, like, boost (GoToSocial) | has | 0.13.0 | `activity.approvals` | `/api/v1/interaction_requests` | only in fedtail | — |
| Notifications from strangers apart | has | 0.9.0 | `notify.filtered` | `/api/v2/notifications/policy`, `notifications/requests` | Mastodon 4.3+ | — |
| Severed relationships and moderators' warnings | has | 0.14.0 | `activity.server_notices` | notifications `severed_relationships`, `moderation_warning` | Mastodon web | — |
| Dismiss a notification, clear them all | has | 0.11.0 | — | `notifications/:id/dismiss`, `notifications/clear` | everyone | — |
| Server announcements | has | 0.9.0 | `ui.announcements` | `/api/v1/announcements` | Mastodon web, Phanpy, Elk, Megalodon | — |
| The unread number on the icon | has | 0.3.0 | `ui.icon_count`, `ui.icon_count_except`, `ui.app_icon`, `ui.themed_icon` | own | Tokodon | — |
| Direct messages read here are read on the server too | has | 0.11.0 | `"direct"` in `lanes.enabled` | `/api/v1/conversations/:id/read` | only in fedtail | — |
| The server's grouped notifications (v2) | has | 0.18.0 | `activity.server_groups` | `/api/v2/notifications`, `/api/v2/notifications/:group_key/dismiss` | Mastodon web, Ivory, Phanpy | Mastodon 4.3+; where the server can't (GoToSocial) — fedtail's own grouping, see “Grouping notifications”. |

<details><summary>In detail</summary>

**Desktop notifications with privacy levels.** Which lanes to notify about — `notify.lanes` (the same names as in `[lanes]`; `"lists"` — all lists, `"list:Friends"` — one, `"all"` — everything); which never — `notify.except` (a blacklist over `lanes`, say with `["all"]`). `privacy`: `"full"` — who and what, `"sender"` — only who (fine to read with others around), `"count"` — only how many. About the lane in front of your eyes it keeps quiet by default (`when_focused`). `backend`: `"auto"` (notify-send, else the tray), `"desktop"`, `"tray"`.

**Activity: likes, boosts, follows.** The “Activity” lane: who liked, boosted, followed, a poll ended, a post you boosted was edited, a new post under a bell — with the time of each event. `["all"]` — everything there is and what will be added.

**Grouping notifications.** Neighbouring notifications of one kind about one post are one row: who (the first few, “and N more”), what, when. Where the server groups them itself (Mastodon 4.3+), fedtail takes its groups: 300 likes of one post are one request and one row with the count, not 300 notifications in eight pages; × on such a row dismisses the whole group on the server. GoToSocial and older Mastodon can't group — there fedtail groups them itself, as before. `activity.server_groups = false` — always itself.

**Approve a reply, like, boost (GoToSocial).** Interaction requests waiting for approval under your who-may-do-what settings come with “Approve” and “Reject” buttons.

**Notifications from strangers apart.** Mastodon holds back mentions from unknown and new accounts until you allow them. ≡ → “For the tender and sensitive” → “Filtered notifications…”: who waits, “Let in” / “Dismiss”, what to filter. `"remind"` — also a line at start, `"menu"` — in the menu only, `"off"` — not at all.

**Severed relationships and moderators' warnings.** When your server blocks another one (or the other way round) and your follows are cut, Mastodon sends a notification with the list of what was lost; moderators may send a warning. fedtail shows them in “Activity” (`activity.server_notices`).

**Server announcements.** `"banner"` — a strip over the lane until you press “Got it” (the server remembers that for other clients too); reactions to announcements. `"off"` — not shown.

**The unread number on the icon.** In the tray and on the task bar button (KDE: needs the entry from `--install-desktop` and `python3-pyside6.qtdbus`). Which lanes to count — a list, as for notifications: `"lists"` — all lists, `"list:Friends"` — one, `"all"` — everything, plus `icon_count_except` — what not to count. The icon itself — an opossum holding its own tail (`app_icon = "possum"`, also in the menu and in About), or the drawn thread bubble (`"bubble"`), which `themed_icon` paints in the theme's colours.

</details>

---

## Several accounts

| What | Status | Since | Config | API / protocol | Others |
|---|---|---|---|---|---|
| Profiles and the switcher | has | 0.3.0 | `ui.switch_closes`, the launch key `--profile` | — | every multi-account client |
| The main profile ★ | has | 0.14.0 | ≡ → “Account and server” → “Make it the main one”; the mark `~/.config/fedtail/main-profile` | own | — |
| Log in again, log out | has | 0.14.0 | ≡ → “Account and server”, with a question | OAuth | everyone |
| All accounts in one window | has | 0.3.0 | `ui.merge` | own | Ivory, Phanpy, Elk, Tokodon, Sengi, Whalebird |
| An account's colour in the shared window | has | 0.14.0 | `ui.account_colors` | own | Fedilab |
| Acting as another account | has | 0.14.0 | `ui.act_as` | the shared window, ⋯ → “From another account”: the post is looked up on its server | Sengi, Tokodon |

<details><summary>In detail</summary>

**Profiles and the switcher.** One profile — one account with its own config, theme, database and window. A right click on the avatar (or ≡ → “Account and server”) — the list, “My profile”, “About the server…” (it has the “Edit profile” button), “Add an account…”; `switch_closes` — whether to close the current window when switching. Which profile and account this is — on the left of the status bar: “default: @nick@server ★”.

**The main profile ★.** The one started without `--profile` and from the “fedtail” menu entry. It isn't a folder with a special name but a mark — the `main-profile` file next to the profile folders; without the mark the main one is `default`. “Make it the main one” in the accounts menu moves it; in the list (and in `--profiles`) the main one is marked ★.

**Log in again, log out.** Both are in the accounts menu, both ask first. “Log in again…” — for a revoked token or new permissions: the old token lives until you're in, cancelling changes nothing, and you can log in this way only to the same account (another one — “Add an account…”). “Log out…” deletes the token (read marks, drafts and the config stay); if that was the main profile, ★ goes to another one you're logged in to and the window switches to it; if there are none — the login window. In the window of all accounts both items are unavailable.

**All accounts in one window.** Lanes of the same name merge, posts of other accounts are marked “→ @nick” — a reply, a like and a boost go from the account that received the post. Lists — lanes of their own. `["all"]`, profile names or `[]` — as chosen in the menu.

**An account's colour in the shared window.** A coloured strip or mark on the posts that came to each account — to see in a merged window whose it is without reading “→ @nick”.

**Acting as another account.** Like, boost or reply not as the account that received the post: in the shared window, a post's ⋯ menu has “From another account”: fedtail finds the post through that account's server and does it from there; a reply opens in the editor as that account.

</details>

---

## The application

| What | Status | Since | Config | API / protocol | Others |
|---|---|---|---|---|---|
| Themes as files | has | 0.1.0 | `ui.theme`, `ui.font_size`, `ui.fonts`, `ui.font`, `ui.mono_font`, `ui.max_width`, `ui.sidebar_width`, `ui.actions` | a TOML format of its own | others — light and dark, Ice Cubes and Megalodon — colours of your own |
| Trying a theme without a restart | has | 0.15.0 | ≡ → “Try a theme”; for good — `ui.theme` | — | Phanpy, Elk, Ice Cubes (they have few) |
| The config as a file in chapters | has | 0.6.1 | the launch keys `--update-config`, `--rebuild-config` | — | tut — TOML too, but not built by chapters |
| The settings reference | has | 0.13.0 | — | `tools/docs_build.py` | tut (a man page and a site), MediaWiki (an article per setting) |
| Window, tray, keys | has | 0.8.0 | `ui.close_to_tray`, `ui.post_keys` | — | keys — Mastodon web, Phanpy, Elk, Ivory, tut |
| Links to posts and profiles — inside | has | 0.2.0 | `ui.links_in_app` | `search?resolve=true` | Ivory, Phanpy, Elk, Megalodon, Fedilab |
| Open a link in the running fedtail | has | 0.14.0 | `fedtail open URL`; `--install-desktop` installs a `web+ap://` handler | own | Megalodon (share a link into the app) |
| Everything is stored locally, readable offline | has | 0.1.0 | — | SQLite in the profile's data folder | Tusky — partly, Ice Cubes — a Home cache |
| Open for days without bloating | has | 0.11.0 | `ui.unload_hidden_minutes`, `ui.image_cache_mb`, `debug.trim_memory` | own | — |
| Polling the server and the live stream | has | 0.9.0 | `[poll]`: `interval_seconds`, `stream`, `stream_gap_seconds` | streaming (WebSocket) | Mastodon web, Phanpy, Elk, Tokodon, Whalebird, Ice Cubes |
| Errors in plain words and without spam | has | 0.13.0 | — | own | — |
| A detailed log for bug reports | has | 0.2.0 | `[debug]`, the launch keys `--debug`, `--bug-report` | own | — |
| Federation status: how my server is doing and what fails | has | 0.16.0 | ≡ → “Debugging” → “Federation status” | own (from what this run saw) | — |
| Leak hunting: trends, an object census, memory snapshots | has | 0.14.0 | `debug.leak_samples`, `debug.object_census`, `debug.tracemalloc`; ≡ → “Debugging” | own (gc, tracemalloc) | — |
| The database doesn't grow for ever: cleanup and a size budget | has | 0.17.0 | `[storage]`: `max_mb`, `keep_per_lane`, `keep_activity`, `gc_hours`, `grace_hours` | SQLite, incremental vacuum | — |
| Screen readers | partly | 0.9.0 | `ui.alt_text`, `ui.accessibility` | — | Mastodon web, Tusky, Ivory |
| Interface language | has | 0.1.0 | `ui.language` | — | everyone |
| Help inside, in two languages | has | 0.17.0 | ≡ → “Help” | own: `fedtail/data/help/<lang>/` | — |
| “What's this?”: a longer hint about any button | has | 0.17.0 | ≡ → “What's this?” for now; `ui.whats_this` — from the start | own: `hints.toml` | KDE apps (What's This) |
| A sound scheme | has | 0.19.0 | `sound.*`, `tui.sound`; in the theme — `[sound] source`, `from` | own: the theme's `sounds/` folder | QIP, ICQ, Mail.ru Agent, Psi |

<details><summary>In detail</summary>

**Themes as files.** Built in: `system` (as in KDE), `terminal`, `juick`, `juick-classic`, `bnw`, `point`, `night`, `contrast` (for weak eyes), `pink`, `nord`, `solarized`, `paper`, `qip-retro`, `qip-modern`, `mra`, `mra-blue`, `mra-green`, `mra-violet`, `psi` (in the spirit of messengers: “Name (time)” over a post, `card_header = "chat"`; with `ui.layout = "split"` the theme sets the layout too: the faces — `shape.faces`, the roster's items — `roster_rows`, tabs in more rows — `tab_rows`), `debug` (for debugging: each state of a post — unread, the j/k cursor, found, “not seen whole yet, not read yet”, the keyboard focus — in a loud frame of its own; `shape.debug = true` turns the same on in any theme of your own). Your own — a file in `~/.config/fedtail/themes/`. A theme sets the card's layout too: the avatar's shape (`avatar_shape`), the header in a line or the name over the date (`card_header = "stacked"`), where the #id stands (`short_id`: by the name or under the post with the reply count), which side the buttons are on (`actions_align`), the line between posts (`rule`: solid or dashed), a hatched band under the titles of the lane and the post window (`header_stripes`) and a dark strip over it (`header_bar`), the colour of the main buttons, of the lane's title strip and of names. A theme sets the look of the whole app, not only colours; that's why separate card templates aren't needed (see Won't do). Fonts — `ui.fonts`: the theme’s (the built-in ones bring their own with fedtail: PT Serif, PT Sans, IBM Plex, Source Sans, Open Sans, Arimo, Comfortaa, Nunito, Fira Mono — all with Cyrillic), the system’s, or your own (`ui.font`, `ui.mono_font`); a theme of yours can bring fonts (`[font] files`), and .ttf/.otf files in `~/.config/fedtail/fonts/` are picked up without installing them system-wide. The width of the posts column — `max_width` (`0` — the full width; the ↔ button at the top left switches it for now and remembers the choice until the next start), labels on buttons — `actions`.

**The config as a file in chapters.** The program only reads the config. A new version brought settings — `--update-config` adds them to the right chapters with explanations; `--rebuild-config` rebuilds the file anew, keeping your values. A value written by hand stays yours when the default changes.

**The settings reference.** The config reference, built from the example configs: every setting with its description, choices and default, in tables by chapter, in Russian and in English. A test makes sure it keeps up with the files.

**Window, tray, keys.** The cross hides to the tray. `j`/`k` — through posts, `r` — reply, `f` — like, `b` — boost, `m` — bookmark, `o`/Enter — the thread. `post_keys = false` — the letters do nothing.

**Links to posts and profiles — inside.** @mentions, #tags and links to fediverse posts and profiles open in fedtail. Not found — the browser. Only web addresses go outside (and mailto:, xmpp:, gemini://, magnet:): fedtail won't open a link to a file or a network share from someone's post.

**Open a link in the running fedtail.** `fedtail open URL` from a terminal or a browser opens a post or a profile in the window already open (or starts it and opens it there). `--install-desktop` makes fedtail the handler of `web+ap://` links — the “open in your app” buttons on servers' pages.

**Open for days without bloating.** A lane not opened for `unload_hidden_minutes` minutes lets its cards go from memory; the one open is never unloaded. fedtail gives the freed memory back to the system (`trim_memory`: otherwise glibc keeps the peak after a night of lanes and pictures).

**Polling the server and the live stream.** A poll every `interval_seconds` (at least 30). The live stream (`"auto"`, if the server offers it) wakes the poll at once, but not more often than every `stream_gap_seconds`. The stream only wakes, so if it drops (a laptop asleep, a proxy) nothing is lost.

**Errors in plain words and without spam.** A server behind a proxy is down — instead of Cloudflare's HTML page one line “Bad Gateway — the server is down or not answering”; the same error of every poll is shown and logged once, again only when it changes or ten minutes later.

**A detailed log for bug reports.** In the debugging mode (`mode = "auto"` — on in development versions, off in releases): a log of requests, polls, actions (without the posts' texts), errors with tracebacks, memory and thread stats every `stats_minutes`, a freeze watchdog (`watchdog_seconds`, `stall_ms`), slow requests, memory growth. `crash.log` — the stacks on a crash, `kill -USR1` — the stacks on demand. The new version deletes the old version's logs itself. `--bug-report` packs two days of it, without the token and the database. In detail — [debugging.md](/docs/en/dev/debugging.md).

**Federation status: how my server is doing and what fails.** ≡ → “Debugging” → “Federation status”: problems that don't depend on the client. My server — what it runs, how many answers and how many with errors, how fast it answers (typical and slow ones), polling (the last good one, how many times it failed and why), the live stream (open since when, how many times it dropped). What the server can't do (asked and got “no”). Who waits to go into a list: the name linked to the profile (opens in a tab, with “Follow”) and why they wait — a request unanswered, no follow (refused or withdrawn), or followed and going in by itself. What fails on my server and on other servers — grouped by request (ids folded: `/api/v1/lists/:id/accounts`), how many times, when last, and what it most likely means (“deleted on that server”, “won't give strangers anything without a signature”, “lists take only people you follow”…). Other servers — who answered how much and with what errors. The window updates by itself while open; “Copy” — as text for an issue, “Count anew” — start from zero. For the window only your own server is asked — who those waiting in lists are; the rest is what this run saw. Addresses without parameters, no tokens.

**Leak hunting: trends, an object census, memory snapshots.** For days-long runs. With every stats line — a `trend` line: memory, Python objects, widgets, cards, pictures, threads, files — how many at start, how many now, how many an hour. Something that grew on each of the last `leak_samples` checks (12 — an hour) and by more than crumbs — a `possible leak` warning with the numbers; the first half hour doesn't count. In the debugging mode — a census: which Python objects and Qt widgets were added since the last check and since the start (`object_census`). `tracemalloc = true` — memory tracing from the start; a snapshot — ≡ → “Debugging” → “Memory snapshot”: a file with who holds the most and what grew, by line of code. There too: “What grows: stats and census now”, “Give free memory back to the system”, tracing on/off. The session's last line — `session summary`: hours, memory, peak, freezes, polls. How to leave it overnight — [debugging.md](/docs/en/dev/debugging.md).

**The database doesn't grow for ever: cleanup and a size budget.** Every `gc_hours` (and at the first poll after start) posts nothing points at are forgotten: no lane, followed thread, “Activity” entry or reply draft. My own posts stay, and so do the boosted post, the quoted one and the parents up the whole thread of every post that stays, so visible replies aren't fetched again. Whatever was stored recently (an open thread, a profile) lives `grace_hours` more. “Activity” keeps the latest `keep_activity` entries. The file really shrinks (incremental vacuum). If the database is still over `max_mb` (1 GB by default), lanes get 30 % shorter until it fits (never below 300) and grow back to `keep_per_lane` once there is room. Short ids (`#a3f`) are never forgotten. What was forgotten and how big the database is — the `storage gc` line in the log.

**Screen readers.** Picture descriptions and button names for screen readers are there, but the interface hasn't been tried live with Orca. The GTK window talks to the accessibility bus only while a screen reader is on (`ui.accessibility = "auto"`; `"on"` — always): KDE runs that bus always, and with no reader a menu took two seconds to open.

**Interface language.** `"auto"` (from LANG), `"ru"`, `"en"`.

**Help inside, in two languages.** A panel in the main window, like the compose panel: the contents on the left, search through the whole help, Back and Forward. Short, by section, and at the end of each — “In detail →” into the full feature list and the settings reference: they are right here and work offline. No shortcut on purpose — F1 is next to Esc.

**“What's this?”: a longer hint about any button.** Turn it on, and hovering shows a longer hint instead of the short one: what the button does, which config key changes it and which help section says more. The same menu item turns it off.

**A sound scheme.** Sounds are part of a theme, as its pictures are. The messenger themes bring their own sets: `qip-retro` (and `qip-modern`) — bright “pip-pip” and a knock at the door when signing in, `mra` (and its colours) — round “blop”s and a xylophone, `psi` — soft chimes, `point` (and `juick`) — dry wooden ticks; `system` plays the desktop's sounds (the KDE/GNOME sound theme through `canberra-gtk-play`; without it a quiet set of fedtail's own), `terminal` and `bnw` — a beep. Your own sounds — a `sounds/` folder by the theme (`message.wav`, `reply.wav`, `mention.wav`, `direct.wav`, `thread.wav`, `request.wav`, `activity.wav`, `online.wav`, `sent.wav`); a missing one comes from the parent theme, from `[sound] from`, then a lighter sound of the same set. By default (`sound.enabled = "auto"`) development versions sound and releases are silent; `"on"` / `"off"` — always / never. A batch of news chimes once, with the weightiest sound (private → reply → mention → thread → request → activity → message), no more often than `sound.min_gap_seconds`; lanes — `sound.lanes` / `sound.except`, signing in and sending — `sound.online`, `sound.sent`; another theme's scheme whatever the look — `sound.scheme`, volume — `sound.volume`, the player — `sound.player` (by default pw-play, paplay, aplay; afplay on macOS; Windows itself). Qt and GTK alike; the terminal beeps (`tui.sound`), the web plays in the browser. ≡ → Debug → “Test the sound”. Every set is synthesised by `tools/make_sounds.py` — our own, GPL.

</details>

---

## Interfaces

The core knows nothing about a GUI; interfaces are plugins. Which one to start — `ui.frontend`, or `--ui` for one run.

| What | Status | Since | Config | Others |
|---|---|---|---|---|
| A Qt window | has | 0.1.0 | `ui.frontend = "qt"` | the main one |
| Commands in a terminal | has | 0.9.0 | `[cli]`: `enabled`, `color`, `max_lines`, `tail_lanes` | tut (TUI), toot (CLI) |
| A terminal interface (Textual) | has | 0.10.0 | `ui.frontend = "tui"`, `[tui]`: `theme`, `lanes_width`, `show_context`, `pictures`, `picture_rows` | tut |
| Web on localhost | has | 0.10.0 | `ui.frontend = "web"`, `[web]`: `host`, `port`, `open_browser` | Phanpy, Elk — web clients |
| The terminal — everything the windows have | partly | 0.19.0 | `ui.frontend = "tui"`, `tui.sound` | — |
| The web — everything the windows have | partly | 0.19.0 | `ui.frontend = "web"` | — |
| GTK4 + libadwaita | has | 0.17.0 | `ui.frontend = "gtk"`, `ui.adwaita` | Tuba |
| Toga (BeeWare) | planned | — | — | — |

<details><summary>In detail</summary>

**Commands in a terminal.** `fedtail lanes`, `fedtail show replies -n 20`, `fedtail tail` (the new as it comes), `fedtail post "text"`, `fedtail post --reply a3f "text"`, `fedtail read replies`. The same profile, database and read marks as the window; works without Qt.

**A terminal interface (Textual).** Lanes on the left, posts on the right, the command line at the bottom. The same keys, `x` — the lane is read, `:` — the command line. Lanes — `[` / `]`, digits `1`…`9`, `h` — into the lane list (`j` / `k` there), `l` — back to the posts, Tab — to and fro. “Activity” and “Follow requests” have rows of their own (in requests `a` — accept, `d` — reject). Pictures are drawn with half blocks: the first one small right in the lane (`tui.pictures`, `tui.picture_rows`), `v` — all of them full screen, ← / → between them, `o` — the original in the browser; needs Pillow (`python3-pil`) and a true colour terminal. Works over ssh. Needs `python3-textual`.

**Web on localhost.** fedtail in a browser tab: lanes, threads as trees, profiles, a “Write” button (content warning, who sees it, language, drafts), pictures in a grid with a viewer, video and audio, polls with voting, link cards, quotes, custom emoji, “More” at a lane's end, the Point command line; on a phone the lanes slide in from the side, light and dark follow the system. At start a one-time link (15 minutes) is printed; the browser gets a key from the profile's folder in a cookie (`web.key`; delete it and every browser and every old link with the key is out). `host = "0.0.0.0"` — from the phone on the home network too; no encryption, for your own network only. The ≡ menu (write, my profile, refresh, all read, help, keys, about); a post's ⋯ menu — the same as the Qt and GTK windows', the same items in the same order (since 0.18: open, copy the link, the #id and the handle, reply with quote, call into the thread, bookmark, who quoted, subscribe / mute the thread, mute / block the author and the server, report, edit, pin, delete, delete and redraft — the risky ones ask first); a profile's buttons as in the windows too (follow, the bell, boosts and languages in Home, mention, mute, block, remove from followers, endorse, a note). A reply shows the whole post: select a piece and “❝ Quote in reply” puts it where the cursor is. The viewer goes through a post's pictures with ← / →.

**The terminal — everything the windows have.** Since 0.19: a post's menu `.` (⋯) — the windows' items, doing the same (links through the shared `common/links.py`, “sure?” asked); the `g` menu (≡) — every place: search (`/`), lists, tags, silence, held-back notifications, scheduled, follow requests, activity, trends, suggestions, the directory, the server, editing my profile, the help (Markdown, links between its pages), what's new, about, the federation status, a bug report, testing the sound; a profile — the windows' buttons under `1`…`9`; the post editor `w` (the warning, who sees it, the language, drafts — as in the windows; Ctrl+O — attachments with descriptions, “sensitive”, a poll, later; Ctrl+S — send); a lane as in the windows: the “new below” divider, `s` — all / posts only / new, feed / conversations, what to show; a card in the windows' words (who boosted, edited, old, what it answers, “you replied”, the quote, reactions); find in the lane Ctrl+F (again — the next one). The places are the web's (`common/places.py`). The behaviour is held against the windows by one scenario (`tools/behaviour.py`). What's still missing — `tools/parity.py`.

**The web — everything the windows have.** Since 0.19 the ≡ menu has every place, at the side: search (`/`), lists (new, rename, exclusive, members, delete), tags, silence (word filters, muted, blocked, servers), held-back notifications, scheduled, follow requests, activity, trends, suggestions, the directory, the server, editing my profile, the help right on the page, what's new, about, the federation status; “Activity” and “Follow requests” have the windows' groups and buttons; the ⋯ menu has “Add to list”, “Read it whole”, “Translate”; a profile has all the windows' buttons (lists, whom they follow, followers, editing my own); find in the lane Ctrl+F; over the lane — “all / posts only / new”, “feed / conversations”, “show”, “to new”, the “new below” divider; a card in the windows' words (who boosted and when, edited → versions, old, what it answers, “you replied”, the quote, reactions); the editor — pictures and files with descriptions (pasted too), “sensitive”, a poll, sending later, the languages, the count against the server's limit; the browser's notifications (≡ → “Notifications in the browser” — allow) in the windows' words (`notify.privacy`); the theme's sounds. The places are the terminal's (`common/places.py`). The behaviour is held against the windows by one scenario (`tools/behaviour.py`). What's still missing — `tools/parity.py`.

**GTK4 + libadwaita.** To look native in GNOME and other GTK desktops. It has: login, lanes in groups with their unread counts, posts as cards (the face, what a reply answers, the content warning, pictures, a poll's results, the quoted post, the link's card, “you replied”), the post's buttons and menu — the same as Qt's, asking before the risky ones, seen means read, “All read”, “earlier”, threads in tabs, writing / replying / quoting / calling in / correcting with drafts, who sees it, the warning, pictures with descriptions, a poll and Tab completion, the Point command line (Ctrl+L), profiles in tabs, Activity, follow requests, notifications, fedtail's themes. Since 0.18 also: find in the lane (Ctrl+F), the split layout, the picture viewer, help as a panel, voting in polls, translating a post, “read it whole”, an edit's history, reporting, who liked and boosted, quotes of my post, “read up to here”, a profile with all of Qt's buttons and editing my own, quotes saying why one can't be shown. Also since 0.18: a thread's header (subscribe, “open every CW”, why its replies show), a profile paging back and on — from the author's server, pinned posts and featured on a profile, lists (add, members, rename, delete, exclusive), groups of tags, a tag's follow and “feature on my profile”, the server's announcements, the curtain on Esc, a video player over the window (needs `libgtk-4-media-gstreamer`), the tray (StatusNotifierItem over D-Bus), selecting text with “Quote in reply”, a contact card on hover in split, a picture's focus point and description, the account mark in the merged window, pictures and files into a post by dragging and from the clipboard (Ctrl+V, screenshots too; dropped on the window — a new post with them). In the deb package GTK is in Recommends, and the GTK window is “fedtail (GTK)” on a right click on the menu entry. What Qt has and GTK doesn't — `tools/parity.py` (but menu items' tooltips: GTK menus have none). Needs `python3-gi gir1.2-gtk-4.0`; libadwaita (`gir1.2-adw-1`) is optional.

**Toga (BeeWare).** Native widgets of Windows, macOS, GTK, Android from one code. To try out.

</details>

---

## Builds and installing

| What | Status | Since | Note |
|---|---|---|---|
| From the source: `python3 -m fedtail` | has | 0.1.0 | PySide6 and requests |
| Linux: one file | has | 0.5.0 | `fedtail-X.Y.Z-linux-x86_64`, built on Debian 12 |
| A deb package | has | 0.10.0 | built in CI on Debian 13; since 0.18 GTK 4 in Recommends, the GTK window an action of the menu entry (“fedtail (GTK)”, right click) |
| Windows: one .exe | has | 0.5.0 | `fedtail-X.Y.Z-windows.exe` |
| A menu entry with the icon | has | 0.2.0 | by itself when a window starts (`ui.desktop_entry`), or `--install-desktop`; named `online.dmesg.fedtail.desktop` (since 0.18) |
| An apt repository of its own | planned | — | from the releases' deb packages |
| An installer and a signature for Windows | planned | — | once there are users on Windows |

---

## ActivityPub directly

Everything here is a request to other servers without your token: they see only your IP. Servers that require signed requests (secure mode) simply give nothing, and fedtail quietly makes do with what your own server knows.

| What | Status | Config |
|---|---|---|
| A whole thread: replies from the author's server | has | `feed.complete_threads` |
| A thread grows when Mastodon has gathered the replies | has | `feed.complete_threads` |
| Long texts and events | has | `feed.long_form` |
| Honest counters | has | `feed.honest_counters` (off), `feed.counters_via_accounts` |
| A little-known person's profile — from their server | has | `feed.remote_profiles`, `feed.remote_posts` |
| Posts older than my server knows | has | `feed.remote_profiles` |
| Followers and follows from the person's server | has | `feed.remote_people` |
| The person has moved | has | `feed.show_moved` |
| The author's server software | has | `feed.server_info` |

---

## Plans

Each feature comes switchable, one at a time, with its entry here and a line in the CHANGELOG. The order is rough: the cheap first, the big later.

| What | Chapter | Config | Size |
|---|---|---|---|
| Collections (Mastodon 4.6) | Lanes | — | once GoToSocial has them |
| Toga (BeeWare) | Interfaces | — | large |
| An apt repository of its own | Builds and installing | — | — |
| An installer and a signature for Windows | Builds and installing | — | — |

## Won't do

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

## Not there and not decided

| What | Others | Note |
|---|---|---|
| Another server's public timeline | Ice Cubes | Reading another server's Local without logging in. Many servers close it to strangers. |
| A link's timeline (Mastodon 4.3+) | Mastodon web | Every post about a popular link. GoToSocial can't do it. |
| Sending emoji reactions | Phanpy, Elk, Fedilab | Akkoma, Pleroma, Misskey; GoToSocial can't do it. |
| Spell checking in the compose panel | Tuba | Not a priority. Qt has none of its own: it needs an outside library (hunspell or enchant) as an optional dependency. |
| The token from an external command (`pass`, `gopass`) | tut | It's unclear what this would add over a file readable by its owner only. |
