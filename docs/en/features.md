# What fedtail does, what it doesn't yet, and what's next

[По-русски](/docs/ru/features.md)

As of version **0.22.0 (in progress)**. This is the full list of fedtail's features: what each one does,
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
   like, all accounts come together in one window (`accounts.merge`).
9. **Grown-ups sort things out themselves.** Arts mode (after @arts, the founder of Point.im):
   everything as the author posted it, no nannying. Anyone can be told where to go, an admin
   too — and the admin can say the same back.
<!-- /include -->

This is the list of what there is **now**, not a history: what changed in each version is in the
[CHANGELOG](/CHANGELOG.md).

**Contents:** [Lanes](#lanes) · [Threads](#threads) · [Read marks and place](#read-marks-and-place) · [The post card](#the-post-card) · [Pictures and video](#pictures-and-video) · [Profiles](#profiles) · [Writing](#writing) · [People and order](#people-and-order) · [Notifications and activity](#notifications-and-activity) · [Several accounts](#several-accounts) · [The application](#the-application) · [Interfaces](#interfaces) · [Builds and installing](#builds-and-installing) · [Five interfaces](#five-interfaces) · [Android: what the phone has and hasn't yet](#android-what-the-phone-has-and-hasnt-yet) · [ActivityPub directly](#activitypub-directly) · [Plans](#plans) · [Won't do](#wont-do) · [Not there and not decided](#not-there-and-not-decided)

---

## Lanes

On the left, the lanes in groups: “Timelines” (from the widest down to your own), “Personal”, “Lists”. Which lanes to show and in what order — `lanes.enabled`. Group headings go with `window.sidebar_groups = false`. The column's width — `window.sidebar_width`; its edge drags with the mouse, and the dragged width is kept until the number in the config changes.

| What | Status | Since | Config | API / protocol | Others |
|---|---|---|---|---|---|
| Federated, Home, Local | has | 0.2.0 | `lanes.enabled` (`"federated"`, `"home"`, `"local"`), `lanes.browse_keep` | `timelines/home`, `timelines/public` | everyone |
| Lane names in the config match their titles | has | 0.15.0 | `home`, `replies`, `federated`, `my_posts`, `my_likes`; the old `people`, `comments`, `global`, `mine`, `favourites` are understood too; a lane's word is in its tooltip on the left | — | — |
| Bots in a lane of their own | has | 0.1.0 | `lanes.enabled` (`"bots"`), `lanes.extra_bots` | the `account.bot` field | only in fedtail |
| Personal lanes | has | 0.1.0 | `lanes.preset`, `lanes.enabled` | notifications, `visibility=direct` | everyone, but laid out differently |
| Lists as lanes | has | 0.2.0 | `[lists]`: `enabled`, `refresh_minutes` | `lists`, `timelines/list/:id` | Mastodon web, Tusky, Ivory, Phanpy, Elk, Tokodon, Ice Cubes, Megalodon |
| Whose replies a list shows | has | 0.20.0 | — | `lists` `replies_policy` | Mastodon web, Ivory, Phanpy, Elk, Ice Cubes |
| Who is in a list leaves the general lanes | has | 0.3.0 | `lists.hide_members`, `lists.hide_in` | own | only in fedtail |
| Who is in a list; your own order of lists | has | 0.13.0 | — | `lists/:id/accounts` | Mastodon web, Ivory (who is in a list); the order — only in fedtail |
| Into a list — the author or the booster; only people you follow | has | 0.13.0 | — | `lists/:id/accounts` | only in fedtail |
| Into a list right after a follow | has | 0.11.0 | `lists.refresh_minutes` | `lists/:id/accounts` | only in fedtail |
| Hashtag lane, following tags | has | 0.2.0 | — | `timelines/tag/:name`, `tags/:name/follow`, `followed_tags` | everyone |
| My likes | has | 0.8.0 | `"my_likes"` in `lanes.enabled` | `/api/v1/favourites` | Mastodon web, Tusky, Ivory, Megalodon, tut |
| Bookmarks | has | 0.3.0 | `"bookmarks"` in `lanes.enabled`, `card.bookmark_button` | `/api/v1/bookmarks` | everyone |
| Trends | has | 0.11.0 | — | `/api/v1/trends` (tags, links, statuses) | Mastodon web, Tusky, Ivory, Phanpy, Elk, Ice Cubes |
| An empty live lane says why it's empty | has | 0.11.0 | — | `timelines/public` | only in fedtail |
| Filtering a lane by media and boosts | has | 0.11.0 | — (kept until restart) | own | only in fedtail |
| Repeated boosts don't bring an old post up again | has | 0.15.0 | `card.repeat_boosts` | own | only in fedtail (a Mastodon server drops a repeat only among the freshest posts) |
| All / Posts only / New; Feed / Conversations | has | 0.3.0 | `lanes.posts_only`, `reading.remember_choices` | own | Phanpy — similar to “Conversations” |
| Find in a lane | has | 0.2.0 | — | own, in the local database | only in fedtail |
| Sending to a slow server without doubles | has | 0.16.0 | `post.send_timeout` | `Idempotency-Key`, `accounts/:id/statuses` | only in fedtail |
| Find in every lane at once | has | 0.16.0 | a tick in the `Ctrl+F` bar | own, in the local database | only in fedtail |
| Finding people, tags and posts | has | 0.2.0 | — | `/api/v2/search` | everyone |
| A lane of several tags | has | 0.14.0 | `[[lanes.tag_groups]]`; from the search — “＋ to lanes” | `timelines/tag/:name` for each tag, put together here | Phanpy, Ice Cubes (“tag groups”), tut (`:tag a b`) |
| Columns side by side | has | 0.14.0 | `window.open_columns`, `window.columns`, `window.column_width`; the ❯ button at the top left | own | Sengi, Phanpy, tut, Whalebird, Mastodon web (advanced mode) |
| A messenger's layout: a roster and a messages window | has | 0.17.0 | `window.layout = "split"` or for one run `fedtail --layout split`; `window.roster_on_top`, `window.roster_threads`, `appearance.faces`, `window.dock_commands`, `window.split_tabs`, `appearance.icons` | own | — |
| Collections of people (Mastodon 4.6) | has | 0.20.0 | ≡ → “My collections”; on a profile — “Add to collection…”, “Collections” | `/api/v1/collections`, `/api/v1/accounts/:id/collections`, `…/in_collections` | Mastodon 4.6, Fedilab |
| Another server's public timeline | has | 0.20.0 | — | that server's `timelines/public?local=true` without a token, `search?resolve=true` on yours | Ice Cubes |
| A link's timeline (Mastodon 4.3+) | has | 0.20.0 | — | `/api/v1/timelines/link` | Mastodon web |
| Free lanes: a lane you assemble yourself | has | 0.21.0 | `[[lanes.custom]]`, `lanes.unsorted` | own | — |
| Federated and tags wider than your server | has | 0.21.0 | `lanes.federated_extra`, `lanes.tags_extra`, `lanes.extra_minutes` | other servers' public lanes without a token; `search?resolve=true` on yours | — |
| The lane editor | has | 0.21.0 | `lanes.enabled`, `[[lanes.custom]]` (writes them) | own | — |
| “Unsorted”: no post gets lost | has | 0.21.0 | `lanes.unsorted` | own | — |
| How fresh the lanes are, in the status line | has | 0.20.1 | — | own | — |
| Only the languages you read | has | 0.21.0 | `lanes.languages`, `lanes.languages_in`, `lanes.detect_language`, `lanes.detect_min_words` | the post's `language` field; our own guess | Mastodon — by the author's tag, in the server's settings |
| Sets of lanes “as in other clients” | has | 0.21.0 | `lanes.preset` (`"fedtail"`, `"mastodon"`, `"tusky"`, `"phanpy"`, `"fedilab"`), `--lanes-to-config` | own | — |
| “To me”: replies and mentions in one lane | has | 0.21.0 | `lanes.enabled` (`"to_me"`) | `notifications?types=mention` | Notifications everywhere, mixed with likes |
| Home's quick filters: tags, boosts, threads with news | has | 0.21.0 | — | own; followed threads (`/context`) | — |
| Important people | has | 0.21.0 | `lanes.enabled` (`"important"`) | `notifications?types=status` (the bell on a profile) | — |
| Lanes of rules: order by counts, “what did I miss”, “Why is it here?” | has | 0.21.0 | `[[lanes.custom]]`: `sort`, `mode`, `window`, `filter_context`, `any` inside a condition | own; the server's filters (`filters`), sources `trends`, `conversations`, `timelines/link`, `statuses/<id>/quotes`, other servers' public lanes | — |
| Lanes from someone's wall, a search and RSS | has | 0.21.0 | `[[lanes.custom]]`: `source = "account:<id>/posts"`, `"search:…"`, `"rss:…"`; `lanes.tags_one_request` | `accounts/<id>/statuses` with `exclude_replies`, `only_media`, `exclude_reblogs`, `tagged`, `pinned`; `/api/v2/search`; RSS and Atom without a token | Fedicat, Subway Tooter, Phanpy, Fread |
| Rules: for a while, by name, at most N per author, by author, "Not in Home" | has | 0.21.0 | `[[lanes.custom]]`: `until`, `text_in = "name"`, `per_author`, `bundle`; `people.home_hide` | own | feather, Ivory, Subway Tooter (regexes, temporary), Raccoon for Friendica (a cap per author), Phanpy (by author), Fedilab (out of Home) |
| A library of pictures for your own lanes | has | 0.21.0 | `icon = "…"` in `[[lanes.custom]]`, "Picture" in the lane editor | own | only in fedtail |

<details><summary>In detail</summary>

**Federated, Home, Local.** “Home” (`home`) — the people you follow, without bots; it opens by default. “Local” — your whole server. “Federated” — everything your server knows from all servers. Federated and Local are fetched only while open and have no unread counts: they are for browsing, not for reading to the end; they hold the newest `lanes.browse_keep` (200) of the whole stream, however fast a relay pours in. A gap between a fresh page and what was there before is allowed in them — unlike Home, which catches up with no holes (see Catching up with no holes).

**Bots in a lane of their own.** Posts of accounts with the “bot” tick leave Home for a lane of their own, “Bots”. A bot without the tick goes into `lanes.extra_bots`: on your server — `"nick"`, on another — `"nick@server"`.

**Personal lanes.**

- “My posts” (`my_posts`) — my posts and comments.
- “Direct” (`direct`) — messages visible to the mentioned only, as a dialogue: incoming and your own outgoing ones (sent from here, from another client, met in a thread), by the post's time. Yours are read at once and don't swell the count (since 0.20). While the lane is on, the incoming ones live only here and don't double up in the others (in the sets' rules that's `apart = "direct"`); yours never go there.
- “Replies to me” (`replies`) — replies to my posts and comments, even if they @ me.
- “Mentions” (`mentions`) — where I was tagged in someone else's conversation. Both lanes are in no set by default (there it's “To me”); `lanes.enabled` turns them on.
- “Subscriptions” (`subs`) — what's new in threads I'm subscribed to (see Thread subscriptions).
- “Bookmarks” (`bookmarks`), “My likes” (`my_likes`, off by default), “Activity” (`activity`), “Follow requests” (`requests`) — below, each in its own section.

Splitting “replies to me” from “mentions” is what other clients don't do: usually it all lands in one notifications lane.

**Lists as lanes.** The server's lists are lanes of their own in the “Lists” group. Create, rename, delete, make exclusive — from the menu; add a person — with a right click on their post. fedtail rereads the lists and who is in them every `lists.refresh_minutes` minutes.

**Whose replies a list shows.** A list has a choice of which replies go into its lane: replies to anyone you follow, only to the list's members, or none. It's the server's setting, the same in every client.

**Who is in a list leaves the general lanes.** Put a person or a bot in a list — their posts, their boosts and others' boosts of their posts are read in the list's lane and disappear from the general lanes, so they don't clutter them. `hide_members`: `"all"` — so with any list; `"exclusive"` — only with exclusive ones (the server itself takes such people out of Home, fedtail carries that to the other lanes); `"off"` — don't take out. Which lanes — `lists.hide_in` (by default Home, Bots, Federated, Local).

**Who is in a list; your own order of lists.** Right click on a list on the left: “Who is in it…” — a tab with its people (and those waiting for a follow to be confirmed), each with “Take out of the list”; “Move up” and “Move down” — your own order of lists. Servers keep no order of lists; fedtail remembers it, new ones go to the end.

**Into a list — the author or the booster; only people you follow.** A boost's ⋯ menu has two items: “Author to a list (@…)” and “Booster to a list (@…)” — a relay bot is a person too, as far as a list goes. The server takes into lists only people you follow: for the rest the lists in the submenu are dead (they don't click at all), signed “follow first”, with a “Follow” item. Right click on the “♻ boosted by …” line — the booster's profile or “To a list”; the name on that line links to the profile.

**Into a list right after a follow.** The server won't take into a list someone you don't follow yet (the request waits with a locked account). fedtail remembers which list you wanted them in and adds them itself as soon as the follow is confirmed.

**Hashtag lane, following tags.** A click on a #tag opens its lane inside (with `card.links_in_app`). Follow a tag — with the button in its lane's header; the server mixes followed tags into Home, and fedtail offers them first when you type `#`.

**My likes.** The posts you liked. The lane is off by default.

**Bookmarks.** “Bookmark” — with the button under a post (`card.bookmark_button = false` moves it into the ⋯ menu), the `m` key or the command `~ #a3f`. The server keeps bookmarks, so they are shared with other clients.

**Trends.** Popular tags, links and posts, as your server counts them. GoToSocial doesn't count trends.

**An empty live lane says why it's empty.** If the server turned the public timelines off (or gives them to its own users only), Federated and Local don't hang empty in silence: fedtail says the server turned them off.

**Filtering a lane by media and boosts.** Over a lane you can leave only text, only pictures, gifs, video or only boosts. It's a quick look, not a setting: after a restart everything is as it was.

**Repeated boosts don't bring an old post up again.** A post comes into a lane once — as itself or with its first boost. A boost of a post this lane has had already, or one already read (in a thread, in another lane), is not shown and not counted as unread; the post stays where it first came. `repeat_boosts = true` — every boost again, as everyone does. The server (Mastodon) drops a repeat only if the original was among the last ~40 posts of the feed — that's why old posts kept surfacing again and again.

**All / Posts only / New; Feed / Conversations.** Over a lane, two switches. “All / Posts only / New”: with all the comments, only top-level posts, or only what's unread. “Feed / Conversations”: “Conversations” gathers a thread into one card, like conversations on Point. In which lanes “posts only” is on from the start — `lanes.posts_only`. Every quick filter — these, a lane's own, the media funnel, Activity's — holds until the program closes; kept between runs with `reading.remember_choices = true`.

**Find in a lane.** `Ctrl+F` finds in the open lane by text, nick, `#id` and picture captions. It searches its own database and doesn't ask the server, so it works offline too. `Enter`, `↓`, `F3` or `Ctrl+F` again — to the next match, `Shift+Enter` — to the previous one.

**Find in every lane at once.** The “In every lane” tick in the `Ctrl+F` bar: you remember a phrase but not where you saw it. It searches everything stored in every lane at once (in the sidebar's order, newest to oldest in each, a post once), the counter says which lane the match is in; the next match opens its lane by itself and loads it down to the post. The tick is remembered.

**Finding people, tags and posts.** Search on the server: people, tags, posts (as far as the server indexes them), and a link to a post or a profile — the server finds it and fetches it.

**A lane of several tags.** Type `#грузия #georgia -#politics` in the search: one lane of all these tags opens — any of them, `+#tag` must be there, `-#tag` — without. The “＋ to lanes” button keeps it on the left, in the “Tags” group; it is fetched while open, like Federated. The same lanes can be described in the config, `[[lanes.tag_groups]]` (name, any, all, none). The server needs a request per tag (GoToSocial reads only one tag at a time), fedtail puts them together itself, without repeats.

**Columns side by side.** Several lanes on screen at once, in columns. By default — one lane at a time; the ❯ button at the top left (next to ≡ and ↔) turns columns on for now, and the window starts as `window.open_columns` says. A click on a lane on the left adds a column (or scrolls to it), ✕ takes it away, ‹ › move it; the set is remembered. These are the same lanes as in the single view: place, filters and read marks are each their own, and Federated and the other browse lanes keep updating while they stand in a column. On the web page (since 0.20) the same, by ❯ on the lane's bar: the lane in focus has its bar, keys and Ctrl+F, a click on a column beside brings it into focus; whether columns are on the browser remembers, at first as `window.open_columns` says; at a phone's width, one lane.

**A messenger's layout: a roster and a messages window.** fedtail as a messenger of the 2000s — QIP, the Mail.ru Agent, Psi. The **roster** is a narrow window, and fedtail starts with it: me and “N new in Activity” on top, a search line, folding groups — the lanes, followed threads and private talks (“Threads”, “Talks”, the freshest `window.roster_threads`) and “People” — whom I follow who follows me back (asked once a day). A group says “(15)”, or “(2/15)” when two of its items have something new; an item has its count, a line of its newest post and a face. A double click or Enter opens it, hovering a person shows their card, as in QIP. At the bottom the menu, the accounts and ⚙ — how the roster looks: compact, without the header, the search or the buttons, only what's new, without groups, above other windows (`window.roster_on_top`). Closing the roster closes fedtail (to the tray with `window.close_to_tray`); the tray icon hides and brings back both windows. The **messages window** is the main window without the sidebar: every lane, thread, profile and talk opened is a tab of its own, in more rows when they don't fit; ×, the middle button or Esc close one, and with the last the window goes (`window.split_tabs` — whether to keep the tabs for next time). A person opens as a talk with only our private messages. The **input line** is always under the posts, a bar that drags between them: in a thread it answers the thread (a private talk stays private), in a talk it writes to that person privately, in a lane — a new post; Reply on a card leads here too. Who sees it, a content warning, pictures, the language; it also takes the command line's commands (`window.dock_commands`: “#a3f text”, “! #a3f”, “?” — Enter). **Faces** (`appearance.faces`): over a lane, in one line, the author of the post under the pointer (or the cursor, or the newest whole on screen): name, address, whether we follow each other, Follow, Add to list, a private message, the profile; by the input line — whom I write to. The Agent's themes have a column on the right instead: theirs by the posts, mine by the input line. A grey silhouette while there's no face. **Pictures on buttons** — the messengers', from the theme's set (`appearance.icons`): on the input line, the author's bar, the roster (only in the split layout, or anywhere with `"additional"`), and on Reply, Favourite, Boost, Thread, Bookmark, who sees a post, the menu and the lanes in any layout; a flower for a person in the QIP themes, an “@” in the Agent's, a star in Psi's; the `psi` theme brings Psi+'s own pictures (the Crystal and Stellar iconsets, GPL). The theme decides how it all looks: the faces — `shape.faces`, the roster's items — `roster_rows`, the tabs — `tab_rows`, the pictures — `shape.icons` and the theme's `icons/` folder (docs/en/dev/layouts.md).

**Collections of people (Mastodon 4.6).** Shared sets of accounts (Mastodon 4.6): yours — made, named, described, shown on the profile or not, deleted; someone into one from their profile (if they allow being in collections) and out again; other people's from their profile; the ones you're in — leave them. A server without collections (GoToSocial) — no item.

**Another server's public timeline.** ≡ → “Another server's lane…”: a server's name — and its Local, as anyone sees it without logging in, page by page. The posts come through your server, so liking, replying and opening threads work as usual. Many servers close their lane to strangers (GoToSocial always) — fedtail says so. That server sees your address, as a browser opening it would.

**A link's timeline (Mastodon 4.3+).** “Who else shared this link” in a post's menu — see the line of that name under “Profiles”. GoToSocial can't do it.

**Free lanes: a lane you assemble yourself.** A lane made of rules, first version: where a post came from (home, local, federated, mentions, mine, bookmarks, likes, followed threads, lists, tags), who (me, the followed, my server, bots, `@nick@server`, a domain), what it is (a post, a reply, a reply to oneself, a boost, a self-boost, a quote), whether it's to me (a reply to my post or comment, a mention, private), what is in it (pictures, video, a CW, links, tags, the language, words), what a boost is of (mine, someone's, seen already), its age, its likes. A lane stands in “Personal” (or `group = "standard"` — in “Timelines”), in its place in `lanes.enabled` (`"custom:name"`) or at the end, and fills from what is stored already; anew when the rule changes. Quick filters: a condition with `switch` is a choice in the lane's header, one with `shown = false` is hidden (from the counts too) until chosen; “Older” — a page from each source through the rule; “Unsorted” (`lanes.unsorted`) — what came and no lane took. Events (likes, boosts, follows, polls) — a condition with `event`: a line among the posts, by time, never unread; follow requests stay in Activity. The plan — `docs/en/dev/feeds.md`.

**Federated and tags wider than your server.** Servers in `lanes.federated_extra` — their public lane comes into Federated while it's open; in `lanes.tags_extra` — their tag lanes come into your lanes of tags (a lane of #linux takes #linux from them too). Each new post is fetched into your server by its address, so it is answered and liked as any other, and your server knows it from then on (its Federated, a tag search). Gently: a server every `extra_minutes`, up to 20 posts; lanes closed to strangers (GoToSocial always, many Mastodons) are left alone for a few hours. Your server can take a tag's posts from a relay itself, too: a matcher `#linux` on the relay subscription.

**The lane editor.** The ≡ menu → “Lanes…” (and a right click on a lane → “Edit the lane…”; on the phone ⋮ → “Lanes…” and ⚙ on a lane): on top the set — “as in” fedtail (the default), Mastodon, Tusky, Phanpy, Fedilab — “Take” and “Take all of yours away” (the set as it is); then every lane in its order — up, down, hide, show, a new lane, delete one's own, “As in the set” for a changed one. “Edit…” — the lane as a form: title, picture, section, sources, how it's read, the order; over the form its conditions in words (“The author: I follow · Kind: a reply”), “Takes” and “Keeps out”. A condition is put together from parts with no syntax at all: “Ask” at the key wanted (the author, the kind, what the post has, the event, the language, words…) and tick the values, typing what the list hasn't (@nick@host, tag:x, “>10”); every “Takes” has its quick filter and “hidden till chosen”; a whole condition can be typed as a line too (“author: me, followed; kind: post”, “*” — every post). What doesn't read is said, and nothing is written. Everything goes into config.toml at once (a set's lane changed here becomes one of your own, of its name) and shows at once; the same in the windows, the terminal, the web page and on the phone.

**“Unsorted”: no post gets lost.** A safety net for the rules: whatever came from a read-through source (home, mentions, mine, lists…) and no lane took lands here. Not here: what another lane holds; posts of people put in a list (read in the list's lane); browse sources (federated, local while lazy) — they'd drown it. A post a lane takes later leaves. The lane is shown only while something is in it; `lanes.unsorted = false` hides it for good and stops collecting — when you deliberately don't want it.

**How fresh the lanes are, in the status line.** “⟳ updating the lanes…” while a round asks the server, “updated at 14:32” once it came through, “⚠ no answer from the server since 14:20” when rounds fail — so a lane with nothing new reads as nothing new, not as a dead network. In the windows — at the right of the status bar, in the terminal — in the header, on the web page — on the lane's bar, on the phone — under the lane's title and on the overview; with slow mode — beside its time.

**Only the languages you read.** Posts in languages not in `lanes.languages` leave Federated, Local and the tag lanes (`lanes.languages_in`; not Home: whom you follow, you read whole). When the author didn't tag the language or tagged it wrong, fedtail guesses: the script gives away Chinese, Japanese, Korean, Arabic, Georgian, Cyrillic (Ukrainian and Belarusian by their own letters) at any length; Latin text — python3-langdetect, if installed, on posts of `lanes.detect_min_words` words and more. A post whose language can't be told stays. Not an exact sorting — a guard against floods in languages you don't read.

**Sets of lanes “as in other clients”.** Every lane is a rule, and the sets are sets of rules ready to use: fedtail's (Point-style), as in Mastodon (web), Tusky, Phanpy; chosen with `lanes.preset`, on the settings page too. The sets' rules are in `fedtail/data/presets.toml`; a `[[lanes.custom]]` of the same name takes a set's lane's place, `fedtail --lanes-to-config` writes the whole set into `config.toml`. Other clients' one “Notifications” is two lanes here for now, Mentions and Activity.

**“To me”: replies and mentions in one lane.** Replies to me and mentions of me — one lane with the quick filters “Replies” and “Mentions”; by default instead of the two lanes (they stay — whoever wants them apart puts them in `lanes.enabled`). Private ones — in “Direct”, while it's on.

**Home's quick filters: tags, boosts, threads with news.** Beside “All / Posts only”: “Tags” — what followed tags brought, not people; “Boosts”; “Threads with news” — posts whose threads have unread replies (followed threads; your own are followed by themselves), the replies themselves inside the thread.

**Important people.** Posts of those you rang the bell on, as a lane of their own. Shown once there is anything in it: while no bell is on, it isn't in the sidebar either.

**Lanes of rules: order by counts, “what did I miss”, “Why is it here?”.** `sort = "likes"` (or `replies`, `boosts`, `density` — all per hour of age) — the best on top; `mode = "catch_up"` with `window = "12h"` — only what came within the window; `filter_context` — the server's filters of that context hide or fold the lane's posts. A condition may hold an `any` of its own — an AND of ORs (`author: followed; any: [has: image] [kind: reply]`). Sources `trends`, `direct`, `bubble`, `account:<id>`, `link:<url>`, `quotes:<id>`, `remote:<host>`. “Why is it here?” in a card's menu and `fedtail --explain-lane NAME` — which condition took the post or what kept it out; a lane no source can fill is marked ⚠ in the editor. A post in several lanes rings once, by its most personal lane; replies whose rules ask about the parent get it fetched before they are sorted.

**Lanes from someone's wall, a search and RSS.** Sources of lanes of rules: `account:<id>` filtered by its server — `/posts` (no replies), `/media`, `/noboosts`, `/pinned`, `/tag:linux`; `search:words` — what a search finds; `rss:https://…` — a site's feed (RSS 2.0, RSS 1.0, Atom), each item a read-only post: open it, bookmark it (here), not like or answer it. The "extra" set has the "Network" lane (Federated without your server) and "Strangers' mentions". `lanes.tags_one_request` — a lane of tags in one request where the server can (Mastodon).

**Rules: for a while, by name, at most N per author, by author, "Not in Home".** A condition's `until = "2026-11-01"`: after that date it's as if it weren't there (a mute for a week, a lane for a trip). `text_in = "name"` — words (and regexes) in the author's name and @nick too. A lane's `per_author = 3`: at most three newest posts of one person; `bundle = "author"`: each one's posts together, the busiest first ("At most from one author" and "Put together" in the editor). `people.home_hide` — on the profile of someone you follow, "Not in Home": their posts leave Home, the follow, lists and the bell stay. The "extra" set has "Strangers' mentions".

**A library of pictures for your own lanes.** 44 pictures — people, a heart, fire, a newspaper, RSS, a magnifier, a camera, film, notes, a book, code, a gamepad, mountains, a fish, a car, a plane, a cup… Each theme colours them in its own style, as its own pictures; a theme's own file of that name wins. In the lane editor — with the picture and its name.

</details>

---

## Threads

| What | Status | Since | Config | API / protocol | Others |
|---|---|---|---|---|---|
| A thread as a tree, comments numbered | has | 0.1.0 | — | `statuses/:id/context` | Phanpy — indented; numbers only in fedtail |
| Over a reply — what it answers | has | 0.1.0 | `card.show_reply_context` | `in_reply_to_id` | Sengi and Megalodon — similar |
| A whole thread: replies from the author's server | has | 0.3.0 | `threads.complete_threads` | the `replies` collection over ActivityPub, `search?resolve=true` | only in fedtail (Mastodon 4.5+ does it on the server) |
| A thread grows when Mastodon has gathered the replies | has | 0.8.0 | `threads.complete_threads` | the `Mastodon-Async-Refresh` header | Mastodon web |
| Thread subscriptions, as on Point | has | 0.2.0 | `[subs]`: `auto`, `interval_minutes`, `active_days`, `max_threads`, `replies_to_me`, `leave_mutes` | own | only in fedtail |
| Mute a thread | has | 0.11.0 | — | `statuses/:id/mute` and own | Mastodon web, Tusky, Ivory |
| Long texts and events | has | 0.14.0 | `card.long_form` | ⋯ → “📄 Read it whole”: `Article`, `Page`, `Event` from the author's server | — |
| A thread with new replies shows on its card | has | 0.21.0 | `card.thread_news` | own (followed threads) | — |
| Threads: where replies come from, growing by itself, only the followed, by branch, "Around this post" | has | 0.21.0 | `threads.thread_from`, `threads.thread_recheck_minutes`, `threads.thread_followed_only`, `threads.thread_progress`, `card.around_post` | `statuses/<id>/context`; the replies collection on the author's server; `timelines/home` with `max_id`/`min_id` | Fedilab, Ivory, Mona (thread modes), Tuba (checks by itself), Pipilo (only the followed), Voyager, Thunder (branches), Subway Tooter (around a post) |
| Commented posts: a thread a card, opened at the first new comment | has | 0.21.0 | the `commented` lane in fedtail's set (the others: the extra set); `view = "threads"` on a lane of your own | own | Point (subscriptions), Juick |
| Where a thread opens: at the post or at the first new comment | has | 0.21.0 | `threads.open_at`; a lane of rules — its own `open_at` | own | Point, Juick (not fediverse clients) |

<details><summary>In detail</summary>

**A thread as a tree, comments numbered.** A thread opens as a tree: every reply under what it answers, every comment numbered `/1`, `/2`, `/2/1`, as on Point and Juick. The command line can address a comment by its number.

**Over a reply — what it answers.** Over a reply in a lane, a strip “↪ in reply to…” with the start of the original post; a click opens the whole thread. No reply in a lane hangs as a scrap.

**A whole thread: replies from the author's server.** Your server knows only the replies that reached it, so other people's threads have holes. Open a thread — fedtail reads the list of replies straight from the author's server and asks your server to fetch what's missing; the thread grows by itself a couple of seconds later. Requests to other servers go without your token. `false` — make do with what your own server knows.

**A thread grows when Mastodon has gathered the replies.** Mastodon 4.5+ gathers missing replies itself and says when it's done; fedtail waits for that signal and rereads the thread.

**Thread subscriptions, as on Point.** The server tells you only of replies that mention you: if two people answer each other under your post, you won't know. fedtail itself rereads the threads you're subscribed to every `threads.interval_minutes` minutes (a thread quiet for an hour — three times less often, for a day — 12 times, for three days — 36) and puts what's new into the “Subscriptions” lane. Threads take at most a quarter of what the server still allows in its rate-limit window: the lanes come first. Subscribe — in a post's ⋯ menu, with the button in the thread's header or the command `S #a3f` (`U #a3f` — unsubscribe). `threads.auto` — what to subscribe to by itself: `"posts"` — your own posts, `"comments"` — threads you comment in. A thread quiet for `threads.active_days` days is not checked any more; one round checks at most `threads.max_threads` threads. Replies to you come to “Replies to me” anyway; `subs.replies_to_me = true` — show them in “Subscriptions” too. Unsubscribing mutes the thread's mentions as well (replies there tag everyone in it by themselves); `threads.leave_mutes = false` — leave “Subscriptions” only.

**Mute a thread.** Notifications from the thread stop coming and its subscription goes. A server that can do it remembers it for all clients; where it can't (GoToSocial), fedtail mutes the thread itself: its mentions are dropped as they come — even replies to posts of the thread it never saw. The item in a post's ⋯ menu is always there.

**Long texts and events.** Articles from WriteFreely, Ghost, Plume, Lemmy posts, Mobilizon events. The Mastodon API flattens them into an ordinary post with the text cut. The ⋯ menu of such a post has “📄 Read it whole”: fedtail takes the full text straight from the author's server over ActivityPub, for an event — also the time and the place.

**A thread with new replies shows on its card.** A post whose thread you follow and which has unread replies has a highlighted line “🔔 3 new in the thread” under it, in any lane; the line opens the thread. Read the replies — the line goes.

**Threads: where replies come from, growing by itself, only the followed, by branch, "Around this post".** `thread_from`: "local" — only what your server knows; "mixed" — at once, the missing ones fetched from the author's server and the thread grows; "remote" — the author's server first, the thread opens whole. `thread_recheck_minutes` — an open thread asks about new replies by itself. `thread_followed_only` — only the replies of people you follow and yours (and what they answer). In a thread `]` / `[` — between top-level comments, `-` — fold a branch (the window). `thread_progress` — "⇣ fetching replies: 3 of 12" in the thread's head, then how many came. `card.around_post` — the post menu's "Around this post": what was in Home just before and after it.

**Commented posts: a thread a card, opened at the first new comment.** Your posts, threads you commented in (`subs.auto`) and those followed by hand — the ones with new comments: a card a thread, under it "N in the conversation, new: M · the last — who". A click opens the thread right at the first new comment. A thread read stays while you're in the lane and goes when you come back. Shown by default in fedtail's set, turned on in the lane editor for the others (the extra set); the same thing — `view = "threads"` on a lane of rules of your own.

**Where a thread opens: at the post or at the first new comment.** One setting for every card: `"post"` — the thread stands at the post, `"first_unread"` — at the first unread comment (none — at the post). A lane of rules may decide for itself ("Commented posts" — at the first new one); "🔔 N new in the thread" always goes to the first new one. Every interface and the phone.

</details>

---

## Read marks and place

| What | Status | Since | Config | API / protocol | Others |
|---|---|---|---|---|---|
| Oldest on top, nothing jumps | has | 0.1.0 | `reading.order`, `reading.start_at`, `reading.on_new` | own | only in fedtail |
| Catching up with no holes | has | 0.1.0 | `reading.page_size`, `reading.catch_up_limit` | `min_id` | only in fedtail |
| When a post counts as read | has | 0.1.0 | `reading.mark_read`, `reading.read_button` | own | only in fedtail (the manual mode) |
| Your own posts are always read | has | 0.13.0 | — | own | — |
| The first run doesn't start with a pile | has | 0.1.0 | `reading.first_run_mark_read` | own | — |
| The reading place is shared with other clients | has | 0.8.0 | `sync.sync_markers` | `/api/v1/markers` | Mastodon web, Tusky, Ivory, Phanpy, Ice Cubes |
| Read marks, thread subscriptions and lane order shared by all your devices | has | 0.18.0 | `sync.url` or `sync.folder` (none — no sync), `sync.read`, `sync.threads`, `sync.lanes`, `sync.drafts`, `sync.activity`, `sync.tiles`, `sync.lane_rules`, `sync.interval_seconds`; `fedtail sync status\|key\|join\|login\|now` | own: a fedtail-sync server (one file, `fedtail_sync.py`, fedtail-syncserver), a shared folder or WebDAV; on a server the journal is the key's, made with an invite code — no login | only in fedtail (markers are just the place in Home and notifications) |
| Only the cards near the screen are in memory | has | 0.11.0 | `reading.render_limit` | own | only in fedtail |
| Esc draws a curtain instead of closing the window | has | 0.3.0 | `window.esc`, `window.start_lane` | own | only in fedtail |
| A draft's pictures travel with it | has | 0.22.0 | `sync.drafts`; the server: `max_media_kb`, `media_quota_mb`, `media_keep_days`, `media_per_minute` | own: `PUT/GET/DELETE /v1/media/<name>` of fedtail-sync, `media/` in a folder | only in fedtail |
| Sync: WebDAV spoken directly, the journal packed | has | 0.22.0 | `sync.webdav`, `sync.webdav_user` | — | — |
| New posts wait for Refresh | has | 0.21.0 | `reading.on_new = "hold"` | own | Elk |
| Sync set up in the window step by step, a new device by a password alone | has | 0.21.0 | ≡ → Sync (or a click on "⇅"); `fedtail sync keep` / `unlock` | own: the key in the journal, sealed by a password (scrypt + AES-GCM) | only in fedtail |
| A lane without a seam: older posts come by themselves | has | 0.21.0 | `reading.older_ahead` | own | Mastodon web, Tusky, Phanpy, Ivory |

<details><summary>In detail</summary>

**Oldest on top, nothing jumps.** `reading.order = "oldest_first"` — oldest on top, you read downwards, like RSS or Point (`"newest_first"` — as everyone does). `reading.start_at = "first_unread"` — open a lane and you stand at the first unread (`"newest"` — at the freshest). `reading.on_new = "keep_position"` — new posts come and the place doesn't move, only the counter grows (`"jump_to_newest"` — jump to the new).

**Catching up with no holes.** Lanes meant to be read to the end catch up forward from the last known post, page by page (`page_size` posts a request, up to `catch_up_limit` a poll — the rest on the next one). So the local copy has no holes and you can read strictly in order. The “load what's missing” button other clients keep fixing (Fedilab in 2026 — half a dozen fixes about holes and jumps, some on GoToSocial) isn't needed here.

**When a post counts as read.** `"on_scroll"` — when you've scrolled past the whole post; `"on_open"` — the whole lane as soon as you open it; `"manual"` — by hand only: “All read” over the lane, “Mark read” and “Read up to here” (this one and everything older) in the ⋯ menu. In the manual mode a lane always waits exactly where you stopped, even reading one post at a time. `reading.read_button = true` — a ✓ button under each unread post. The menu items work in any mode.

**Your own posts are always read.** A post you wrote is read, wherever it came from: from Tusky at night, through a thread, fetched after a restart.

**The first run doesn't start with a pile.** At the very first run, everything fetched counts as read.

**The reading place is shared with other clients.** Read Home or mentions to the end on the phone — here it's read too, and the other way round. Works with Mastodon, GoToSocial, Akkoma — if that client tells the server its place: Mastodon's web, Ivory, Phanpy do; Tusky keeps its place in Home to itself and shares only notifications. `false` — read marks live in fedtail only.

**Read marks, thread subscriptions and lane order shared by all your devices.** Read a post on the laptop — it's read on the desktop; follow a thread, leave it or mute it, move a list or save a tag lane — so it is on the other devices. Sync is a service of its own: it works only when the config has `sync.url` (or `sync.folder`); without it there is none, and the right of the status bar says so (“⇅ off”, “⇅ 21:40”, “⇅ !”), as does About. Marks fedtail makes by itself (everything read on the first run, older history, your own posts) stay home: a new device won't read the desktop for you. Each device writes a journal of what it did; the journals meet on a fedtail-sync server or in a folder all the devices see (a NAS share, WebDAV, Syncthing). The journals are sealed with a key only your devices have: the store doesn't see what you read. The first device makes the key; `fedtail sync key` shows it, `fedtail sync join` carries it to another. To the sync server fedtail gives not its own token but a separate one that can only tell “who am I” (`fedtail sync login`). Setting up a server of your own — docs/en/sync.md.

**Only the cards near the screen are in memory.** A lane of any length keeps widgets only for the cards on screen and a screen above and below (since 0.22: before, 40 to 120 cards with all their pictures, some 18 MB a lane); the other posts are only a place of their height. Scrolling builds the cards coming near and lets go of those gone far, remembering what was done to them (a warning opened, a translation shown). What you read doesn't move: the card on top of the screen holds it. At most `render_limit` latest posts are kept, older ones with the “older” button. A thread and a profile are built whole.

**Esc draws a curtain instead of closing the window.** Esc closes what's on top (a picture, the search), and the last Esc with `window.esc = "curtain"` draws a curtain over all lanes: the window stays, the counts on the left, nothing on the right, and nothing is marked read — open it in the morning and the new has piled up. `"tray"` — off to the tray, `"off"` — nothing. What to start with — `window.start_lane`: `"none"` (the curtain, Enter opens the last one), `"last"` or a lane's name.

**A draft's pictures travel with it.** A draft begun with a picture is finished on another device with the same picture, its description and focus point. Each picture is sealed with the account's key and named by its hash: it goes once however often the draft is saved; a sent or emptied draft takes its pictures off the store too. One too big for the store, or dropped by it, stays on its own device; the rest travels. The sync server keeps pictures under a quota of their own where the least used go first, so drafts made in a loop churn only their own pictures, not the journal or the disk.

**Sync: WebDAV spoken directly, the journal packed.** A WebDAV folder (Nextcloud, ownCloud, a NAS) without mounting: the password is asked once and kept in the profile's data folder, not in the config. Every device now and then packs its own journal into a snapshot and drops its older files or blobs (a fedtail-sync server 0.22+: `DELETE /v1/devices/<id>`), so the journal doesn't grow to the quota.

**New posts wait for Refresh.** What comes after the lane is drawn doesn't go into it: the lane's header says "N new — Refresh shows them", and ⟳ / F5 lets them in. Older posts (paging down) come at once.

**Sync set up in the window step by step, a new device by a password alone.** Three steps marked ✓ / ▶ / ·: where the devices meet (a server's address or a folder — into config.toml at once, no restart), the login to the sync server, and the fork — "this is my first device" (the key made here) or "adding to those set up" (the key from another device — there "Show the key" gives a QR code the phone scans, and the text to paste; or the key taken out of the journal with the password for new devices). The password is optional: one you make up, not the account's. The same in the terminal, on the web page and on the phone.

**A lane without a seam: older posts come by themselves.** Read nearly to the end of what a lane shows — fedtail fetches a page of older posts itself, as the "older" button does. One page at a time; an empty one — it asks no more by itself (the button stays). The old isn't counted as new.

</details>

---

## The post card

| What | Status | Since | Config | API / protocol | Others |
|---|---|---|---|---|---|
| Arts mode | has | 0.11.0 | `card.arts_mode` (on by default, recommended) | — | nobody has it as one switch |
| Content warnings (CW) | has | 0.1.0 | `card.expand_cw` | `spoiler_text` | everyone can set it |
| Open every CW in a thread at once | has | 0.18.0 | — | own | Sengi, Megalodon (the same CW across a thread) |
| Sensitive pictures | has | 0.8.0 | `card.sensitive_media` | `status.sensitive` | everyone |
| Link cards | has | 0.8.0 | `card.link_cards` | `status.card` | everyone |
| Servers' emoji as pictures | has | 0.8.0 | `appearance.custom_emoji` | `emojis` of the post and the account | everyone |
| No emoji at all | has | 0.15.0 | `appearance.emoji = false` — no server pictures, no Unicode ones, no reactions; a name made only of emoji shows the login | — | Tusky (animation only), Fedilab (only servers' own emoji) |
| Quotes: showing them | has | 0.8.0 | `card.quotes` | `status.quote` | Mastodon 4.5+, Ivory, Phanpy, Elk, Ice Cubes, Fedilab |
| Polls: seeing and voting | has | 0.3.0 | — | `polls/:id`, `polls/:id/votes` | everyone |
| Poll results without voting | has | 0.3.0 | — (the “Results” button of a poll) | — | Fedilab |
| Edit history | has | 0.3.0 | — | `statuses/:id/history` | Mastodon web, Ivory, Phanpy, Elk, tut |
| Translation by the server | has | 0.8.0 | `card.translate`, `card.translate_all` | `statuses/:id/translate` | Mastodon web, Ivory, Phanpy, Elk, Ice Cubes, Fedilab |
| Emoji reactions | has | 0.11.0 | — | `pleroma.emoji_reactions` | Phanpy, Elk, Fedilab |
| Who liked and boosted | has | 0.11.0 | — | `favourited_by`, `reblogged_by` (and from the author's server) | Mastodon web, Tusky, Ivory, Phanpy, Elk, tut |
| Honest counters | has | 0.2.0 | `card.honest_counters` (off), `card.counters_via_accounts` | the author's server's API without a token | only in fedtail |
| Who quoted my post | has | 0.11.0 | — | `statuses/:id/quotes`, `…/quotes/:id/revoke` | Mastodon 4.5+ |
| Folding hashtag padding | has | 0.14.0 | `card.collapse_tags` | own | Phanpy |
| `~~text~~` struck out when the server knows no Markdown | has | 0.14.0 | `appearance.text_markup` | own | — |
| Labels on the card | has | 0.14.0 | `card.old_days`; “bot” — always | own | Sengi |
| Sending emoji reactions | has | 0.20.0 | ⋯ → “React…” | `PUT/DELETE /api/v1/pleroma/statuses/:id/reactions/:emoji`, `POST /api/v1/statuses/:id/react\|unreact/:emoji` | Phanpy, Elk, Fedilab |

<details><summary>In detail</summary>

**Arts mode.** Everything as the author posted it, no nannying. Turns on at once: content warnings (CW) open, “sensitive” pictures without a cover, server filters neither hide nor fold posts, no “Report” item. Your own mutes and blocks work as usual; what the server itself cuts off (domain blocks) never reaches a client — that can't be got round. `false` — everything as everyone has it, and then each of these is set on its own (`card.expand_cw`, `card.sensitive_media`).
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

**Translation by the server.** “Translate” in the ⋯ menu of a post in another language — if your server can (Mastodon with DeepL or LibreTranslate). The translation is right in the card, with an “original” button. With `card.translate_all = true` (since 0.19) — on every post, as in Fedilab: in your own language too, and with none given.

**Emoji reactions.** Reactions from Akkoma, Pleroma, Misskey and their forks show under the post. Giving your own — see “Sending emoji reactions”.

**Who liked and boosted.** Lists of people at the counters. If your server doesn't know everyone, the rest is read from the author's server.

**Honest counters.** Your server knows only the likes and boosts that reached it, so the numbers on other people's posts are low. With `honest_counters = true`, when a thread opens fedtail asks the author's server for the real numbers — without a token, but with your IP. If that server won't give numbers without a login and you have other accounts (profiles), `counters_via_accounts` lets it ask as them: the author's server, if you have an account there, or a server that already has the post. Each account's token goes only to its own server.

**Who quoted my post.** The list of quotes of my post and “take my post out of this quote”.

**Folding hashtag padding.** A paragraph of nothing but hashtags (more than three) in a lane folds into the first three and “… +N” in small type; in an open thread it's whole, but small too. Hashtags inside the text aren't touched.

**Boost carousel.** Boosts in a row — as one strip scrolled sideways (as in Phanpy). Won't do: sideways is awkward to read, and it fits badly with “nothing jumps” and read marks. The same job is done by the “Boosts” tick in the filter, “without their boosts” on a profile and relays in a list of their own.

**Labels on the card.** Next to the date: “old, N days” — a post older than `card.old_days` (30) days; such posts come from someone's outbox or an old thread; “[bot]” — on bots. There is no “from another server” label yet.

**Sending emoji reactions.** ⋯ → “React…”: the usual emoji and the ones already on it as buttons (tapped again, yours comes off), any other or the server's own emoji typed (`:blobcat:`). The item is there where the server has reactions (Akkoma, Pleroma — their API; Misskey, Sharkey, Iceshrimp, Fedibird — Fedibird's), and on a post that has reactions already; GoToSocial and Mastodon don't support them.

</details>

---

## Pictures and video

| What | Status | Since | Config | API / protocol | Others |
|---|---|---|---|---|---|
| Picture viewer | has | 0.1.0 | `media.image_viewer`, `media.image_upscale`, `media.image_height` | — | everyone |
| Picture grid | has | 0.9.0 | `media.media_grid` | `meta.focus` | Mastodon web, Tusky, Phanpy, Elk |
| Picture descriptions (alt) | has | 0.9.0 | `media.alt_text` | `description` | everyone |
| Video, audio, gifs inside the window | has | 0.11.0 | `media.video_player`, `media.gifv` | `media_attachments` | everyone |
| Video without a hardware decoder (the default) | has | 0.16.0 | `media.video_decode` | — | only in fedtail |
| Save a picture, video, gif | has | 0.2.0 | `media.save_dir` | — | Tusky, Ivory |
| Pictures and video ahead of time, a disk cache | has | 0.13.0 | `media.prefetch`, `media.image_disk_mb`, `media.video_disk_mb` | own | only in fedtail |
| Memory for pictures | has | 0.2.0 | `media.image_cache_mb`, `media.image_decode` | own | — |

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
| In a profile: posts, posts and replies, media | has | 0.20.0 | `people.profile_show` | `accounts/:id/statuses` `exclude_replies`, `only_media` | Mastodon web, Tusky, Ivory, Phanpy, Elk, Ice Cubes, Fedilab |
| Who else shared a link | has | 0.20.0 | — | `/api/v1/timelines/link` | Mastodon web |
| Pinned posts | has | 0.8.0 | `people.profile_pinned` | `statuses?pinned=true` | everyone |
| Featured tags and recommended people | has | 0.9.0 | `people.profile_featured` | `featured_tags`, `endorsements` | Mastodon web |
| A little-known person's profile — from their server | has | 0.8.0 | `people.remote_profiles`, `people.remote_posts` | ActivityPub outbox | Megalodon — partly (the lists) |
| Posts older than my server knows | has | 0.11.0 | `people.remote_profiles` | ActivityPub outbox | only in fedtail |
| Followers and follows from the person's server | has | 0.8.0 | `people.remote_people` | ActivityPub `followers`, `following` | Megalodon |
| “Following since …” | has | 0.11.0 | `people.follow_date_note` | `accounts/:id/note` | only in fedtail |
| The person has moved | has | 0.14.0 | `card.show_moved` | `account.moved`, ActivityPub `Move` | Mastodon web |
| The author's server software | has | 0.14.0 | `people.server_info` | nodeinfo, in the profile “🖥 GoToSocial 0.17” | — |
| What my server can do | has | 0.17.0 | ≡ → account → “Server info” → “What it can do” → “Check” | one harmless GET with `limit=1` per feature | — |

<details><summary>In detail</summary>

**Your own and other people's profiles.** The header, bio, fields, counts, posts; “followed by people you follow” (`familiar_followers`); follows and followers.

**In a profile: posts, posts and replies, media.** Above a person's posts, a switch: “Posts” (without their replies to others; replies in their own threads stay), “Posts and replies”, “Media” (only with pictures and video). Which one first — `people.profile_show`, “Posts” by default, as in other clients. The server does the picking.

**Who else shared a link.** In the ⋯ menu of a post with a link — “Who else shared this link”: posts with it, page by page. The server (Mastodon 4.3+) keeps only links that were trending; where it can't, there's no such item.

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
| A video's cover; picture descriptions in a post's edit | has | 0.20.0 | — | `/api/v2/media` `thumbnail`; `PUT /api/v1/statuses/:id` `media_attributes` | Mastodon web, Ivory, Elk |
| The compose panel and drafts | has | 0.1.0 | `window.compose`, `window.compose_size`, `post.drafts_autosave` | `statuses` | everyone |
| Visibility: private by default, a reply never wider than the post | has | 0.1.0 | `post.default_visibility`, `post.reply_never_wider` | `visibility`, `/api/v1/preferences` | only in fedtail (never wider) |
| Markdown | has | 0.1.0 | `post.markdown`, `post.plain_posts` | `content_type` | GoToSocial and Akkoma clients |
| Preview before sending | has | 0.14.0 | `post.preview` | own | Fedilab |
| Formatting buttons | has | 0.22.0 | `post.format_bar` | own (Markdown) | Fedilab, Phanpy |
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
| A command line as on Point | has | 0.3.0 | `window.command_line`, `post.plain_posts` | own | only in fedtail (tut — vim-style commands) |
| Short post names the same on every device | has | 0.18.0 | — | own | only in fedtail (Point had the server's post numbers) |
| Spell checking in the compose panel | has | 0.20.0 | `post.spellcheck`, `post.spell_languages` | own: the system's dictionaries through Enchant | Tuba, Tusky, Mastodon web (the browser) |
| Language check, link → quote, sending in the background, scheduled → editor, Drafts | has | 0.21.0 | `post.lang_check`, `post.link_quote`, `post.send_in_background`, `post.scheduled_to_draft`, `post.drafts_place` | `/api/v2/search`, `/api/v1/scheduled_statuses` | Fedilab (language), Tuba (a quote from a link, draft ↔ scheduled), Milktea (sending in the background), Pachli (a drafts tab) |

<details><summary>In detail</summary>

**A video's cover; picture descriptions in a post's edit.** A video or a sound among the attachments gets “Cover…”: a picture shown until it's played. Editing your post, its pictures can be described anew and their focus set (in the terminal — the description only).

**The compose panel and drafts.** `window.compose = "inline"` — a panel inside the main window (the keyboard layout isn't reset: KDE keeps it per window); `"window"` — a window of its own. The panel's size — in percent of the window (`compose_size`), the ⤡ button switches normal and big. Drafts are saved as you type and survive closing.

**Visibility: private by default, a reply never wider than the post.** A new post goes to followers by default (`"private"`); `"server"` — as set on the server. A reply is never more public than the original post.

**Markdown.** `"auto"` — ask the server; GoToSocial and Akkoma understand Markdown, vanilla Mastodon doesn't.

**Preview before sending.** The “👁 Preview” button in the panel: the Markdown already rendered (if the server understands it), the CW, visibility, language, each part of a chain, how many pictures; “Send” or “Edit” from there.

**Formatting buttons.** Buttons by the text: bold, italic, strikethrough, code (several lines — a block), a link, a quote, a list. They put the Markdown marks around the selection, pressed again — take them off; Ctrl+B, Ctrl+I, Ctrl+K. Where they stand: left (the default) or right — a column, top or bottom — a row, or none; only when the server understands Markdown.

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

**Spell checking in the compose panel.** Words with mistakes are underlined; a right click — suggestions and “Add to dictionary” (your own one — `spelling.txt` next to the config). It checks in the post's language, the interface's and English — a word is fine if any dictionary knows it; links, @names, #tags, :emoji: and `code` are left alone. The dictionaries are the system's (Debian: `libenchant-2-2`, `hunspell-en-us`, `hunspell-ru`); none — no checking. In the terminal — a list on F7, in the web page — the browser's checker.

**Language check, link → quote, sending in the background, scheduled → editor, Drafts.** `lang_check` — before sending: the text is plainly in another language than the post's (by its script, and with langdetect by its words too) — "Mark it …", "Send as is" or back to the text. `link_quote` — a post's link at the end of the text becomes a quote (when its author allows) and leaves the text. `send_in_background` — the editor closes at once, the post with its pictures goes in the background; if it fails the editor comes back (on the web page and the phone, a notification, the draft kept). `scheduled_to_draft` — a scheduled post's "To the editor": off the schedule, its text in the editor. `drafts_place` — "Drafts" in the ≡ menu: every draft, to open (a reply's in its thread) or delete.

</details>

---

## People and order

| What | Status | Since | Config | API / protocol | Others |
|---|---|---|---|---|---|
| Follows and follow requests | has | 0.1.0 | `"requests"` in `lanes.enabled` | `follow`, `follow_requests` | everyone |
| Hide a person's boosts; the languages of a follow | has | 0.14.0 | `people.per_person_follow` | `follow` with `reblogs=false`, `languages[]` | Mastodon web, Tusky, tut |
| Mute, block, word filters | has | 0.3.0 | — | `mutes`, `blocks`, `/api/v2/filters` | everyone |
| Mute a hashtag in one click | has | 0.22.0 | — | `/api/v2/filters` | Fedilab — one click; Mastodon web — by hand, with a filter |
| Mute for a while; posts only | has | 0.20.0 | — | `accounts/:id/mute` `duration`, `notifications` | Mastodon web, Ivory, Fedilab |
| Hide a single post | has | 0.20.0 | — | `/api/v2/filters/:id/statuses` | Mastodon web |
| Editing a filter | has | 0.20.0 | — | `PUT /api/v2/filters/:id` | Mastodon web, Ivory, Fedilab |
| Report: which rules it breaks | has | 0.20.0 | — | `/api/v1/reports` `rule_ids` | Mastodon web, Ivory, Tusky |
| Block a whole server | has | 0.8.0 | — | `/api/v1/domain_blocks` | Mastodon web, Ivory, Phanpy |
| Report to the moderators | has | 0.8.0 | `post.report_forward` | `/api/v1/reports` | everyone |
| A private note on a person | has | 0.8.0 | — | `accounts/:id/note` | Mastodon web, Ivory, Ice Cubes |
| A bell on a person's posts | has | 0.8.0 | `"status"` in `activity.types` | `follow notify=true` | Mastodon web, Tusky, Ivory, Megalodon |
| Remove from followers without a block | has | 0.11.0 | — | `remove_from_followers` | Mastodon web, Ivory |
| Recommend people and tags on your own profile | has | 0.11.0 | — | `endorse`, `featured_tags` | Mastodon web |
| The server's suggestions, the profile directory | has | 0.11.0 | — | `/api/v2/suggestions`, `/api/v1/directory` | Mastodon web, Tusky, Ivory |
| About the server | has | 0.11.0 | — | `instance`, `instance/rules`, `extended_description` | Mastodon web, Ivory, Phanpy |
| Your profile | has | 0.2.0 | — | `update_credentials` | Mastodon web, Ivory, Phanpy, Elk, Tokodon, Ice Cubes |
| Profile: hide follows, posts found by search, article authorship, tag suggestions | has | 0.20.0 | — | `update_credentials` `hide_collections`, `indexable`, `attribution_domains`; `featured_tags/suggestions` | Mastodon web |
| About the server: terms, whom it cut off, its translator | has | 0.20.0 | — | `instance/terms_of_service`, `instance/domain_blocks`, `instance/translation_languages` | Mastodon web |
| Post visibility as set on the server | has | 0.11.0 | `post.default_visibility = "server"` | `/api/v1/preferences` | Mastodon web, Ivory |
| Unfollowed — gone from Home | has | 0.21.0 | `people.forget_unfollowed` | `GET /api/v1/accounts/relationships` | — |
| Your own names and colours for people, why a post is in Home, a post's JSON | has | 0.21.0 | `people.aliases`, `people.nick_colors`, `sync.people`, `card.why_home`, `debug.raw_json` | own | Tokodon and Fedilab (own names), Phanpy (why in the feed), Tuba (a post's JSON) |

<details><summary>In detail</summary>

**Follows and follow requests.** Follow, unfollow, accept or reject a follow request (the “Follow requests” lane).

**Hide a person's boosts; the languages of a follow.** On the profile of someone you follow: “♻ without their boosts” and “🌐 languages” — only their posts in these languages. The server keeps it, so it works in every client.

**Mute, block, word filters.** Word filters are the server's, v2: where they apply, for how long, hide or fold. All this — in the ≡ menu → “For the tender and sensitive”: word filters, muted, blocked, blocked servers and filtered notifications; with `card.arts_mode`, a line on top says the server's filters don't apply there.

**Mute a hashtag in one click.** A post's ⋯ → “Mute #tag” (for each of its tags, up to three), and on a tag's page “Mute the tag” / “Show the tag again”. The tag goes into one server filter, “fedtail: hashtags” (hide everywhere), as Fedilab does it — so it works in other clients too. Posts with it leave at once, those already here too; a tag written “#tag” in any “hide” filter of yours counts as muted as well. A tag muted by hand hides with `ui.arts_mode` too.

**Mute for a while; posts only.** “Mute” asks for how long: for good, an hour, a day, a week, a month — then the server lifts it by itself. The “Posts only” tick keeps their notifications coming. Word filters get a term too.

**Hide a single post.** “Hide this post” in the ⋯ menu: the post goes at once and everywhere — into the server's filter “fedtail: hidden posts”, so other clients don't show it either. To bring it back, remove the filter in “For the tender and sensitive”. A server that can't (Mastodon before 4.0) gets no such item.

**Editing a filter.** Each filter in “For the tender and sensitive” has “Edit…”: title, words, hide or fold, where it works and for how long more. Words taken out the server drops, new ones it adds.

**Report: which rules it breaks.** The reason “breaks the server's rules” shows your server's rules as ticks; at least one is needed — the moderators see which.

**Block a whole server.** Nobody from there in any lane, follows across the border are cut.

**Report to the moderators.** About a person from another server — a “forward to their server too” tick (they won't learn who reported). In arts mode the item isn't there.

**About the server.** The description, rules, privacy policy.

**Your profile.** Name, bio, fields, avatar, header.

**Profile: hide follows, posts found by search, article authorship, tag suggestions.** In the profile editor: hide whom you follow and who follows you; whether a search of words finds your public posts; which sites may name you the author of their articles (Mastodon 4.4). And the tags you often write about — added to your profile with one click.

**About the server: terms, whom it cut off, its translator.** “About the server” has the terms of service (4.4), the servers it cut off or limited (if it shows them) and what its translator can do. “Translate” isn't offered in a post's menu where your server's translator can't turn that language into yours.

**Unfollowed — gone from Home.** The posts and boosts of someone you stop following leave Home, as they leave your server's Home: at once when you unfollow here; within a few hours when you do it in another client or on the server's web page (fedtail asks the server about the people whose posts Home holds). Someone you never followed (a followed tag's posts) is left alone. `false` — what came stays.

**Your own names and colours for people, why a post is in Home, a post's JSON.** `people.aliases` — "My name for them…" on a profile: a name you see instead of theirs on cards and the profile (yours only, never sent to the server; empty — their own again). `people.nick_colors` — "Name colour…": their name in your colour (a name or #rrggbb). `sync.people` — those names, colours and the people taken out of Home travel to your other devices. `card.why_home` — a post in Home by someone you don't follow says "# tag": it came by a followed tag. `debug.raw_json` — the post menu's "Post JSON": as the server gave it, with a Copy button — for bug reports.

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
| Server announcements | has | 0.9.0 | `notify.announcements` | `/api/v1/announcements` | Mastodon web, Phanpy, Elk, Megalodon | — |
| The unread number on the icon | has | 0.3.0 | `window.icon_count`, `window.icon_count_except`, `appearance.app_icon`, `appearance.themed_icon` | own | Tokodon | — |
| Direct messages read here are read on the server too | has | 0.11.0 | `"direct"` in `lanes.enabled` | `/api/v1/conversations/:id/read` | only in fedtail | — |
| Activity's quick filters | has | 0.21.0 | `switch` in the rule of `[[lanes.custom]]` | own | — | — |
| Who stopped following you | has | 0.21.0 | `activity.unfollows`, `activity.unfollows_minutes`, `activity.unfollows_max`, `activity.unfollows_mass`, `activity.unlikes`, `activity.unlikes_days`, `activity.unlikes_posts` | `accounts/:id/followers`, `accounts/relationships` | only in fedtail (no server says it) | — |
| Activity says whom you followed | has | 0.21.0 | `activity.my_follows` | own (and `accounts/:id/following`) | only in fedtail | — |
| Someone new in a private talk — shown at once | has | 0.21.0 | — | own | only in fedtail | — |
| Push notifications (Web Push, UnifiedPush) | has — Web Push in the web version, UnifiedPush on Android | 0.20.0 | `phone.push` | `/api/v1/push/subscription` | Mastodon web, Elk, Phanpy, Tusky, Ivory | — |
| The server's grouped notifications (v2) | has | 0.18.0 | `activity.server_groups` | `/api/v2/notifications`, `/api/v2/notifications/:group_key/dismiss` | Mastodon web, Ivory, Phanpy | Mastodon 4.3+; where the server can't (GoToSocial) — fedtail's own grouping, see “Grouping notifications”. |
| Slow mode and “notify at most every…” | has | 0.20.0 | `server.slow_minutes`; ≡ → “Slow mode…” — with “notify at most every…” for each lane | own | only in fedtail (others have only the poll interval) | — |
| “Of them new”: what the last update brought | has | 0.20.0 | on the phone's tiles, in the sidebar of the windows, the web page and the terminal | own | only in fedtail | — |
| Follow requests in any lane | has | 0.21.0 | `activity.requests`, `event = "follow_request"` in a lane's rule | `follow_requests`, `follow_requests/<id>/authorize\|reject` | Mastodon web, Ivory, Phanpy — among notifications | — |

<details><summary>In detail</summary>

**Desktop notifications with privacy levels.** Which lanes to notify about — `notify.lanes` (the same names as in `[lanes]`; `"lists"` — all lists, `"list:Friends"` — one, `"all"` — everything); which never — `notify.except` (a blacklist over `lanes`, say with `["all"]`). `privacy`: `"full"` — who and what, `"sender"` — only who (fine to read with others around), `"count"` — only how many. About the lane in front of your eyes it keeps quiet by default (`when_focused`). `backend`: `"auto"` (notify-send, else the tray), `"desktop"`, `"tray"`.

**Activity: likes, boosts, follows.** The “Activity” lane: who liked, boosted, followed, a poll ended, a post you boosted was edited, a new post under a bell — with the time of each event. `["all"]` — everything there is and what will be added.

**Grouping notifications.** Neighbouring notifications of one kind about one post are one row: who (the first few, “and N more”), what, when. Where the server groups them itself (Mastodon 4.3+), fedtail takes its groups: 300 likes of one post are one request and one row with the count, not 300 notifications in eight pages; × on such a row dismisses the whole group on the server. GoToSocial and older Mastodon can't group — there fedtail groups them itself, as before. `activity.server_groups = false` — always itself.

**Approve a reply, like, boost (GoToSocial).** Interaction requests waiting for approval under your who-may-do-what settings come with “Approve” and “Reject” buttons.

**Notifications from strangers apart.** Mastodon holds back mentions from unknown and new accounts until you allow them. ≡ → “For the tender and sensitive” → “Filtered notifications…”: who waits, “Let in” / “Dismiss”, what to filter. `"remind"` — also a line at start, `"menu"` — in the menu only, `"off"` — not at all.

**Severed relationships and moderators' warnings.** When your server blocks another one (or the other way round) and your follows are cut, Mastodon sends a notification with the list of what was lost; moderators may send a warning. fedtail shows them in “Activity” (`activity.server_notices`).

**Server announcements.** `"banner"` — a strip over the lane until you press “Got it” (the server remembers that for other clients too); reactions to announcements. `"off"` — not shown.

**The unread number on the icon.** In the tray and on the task bar button (KDE: needs the entry from `--install-desktop` and `python3-pyside6.qtdbus`). Which lanes to count — a list, as for notifications: `"lists"` — all lists, `"list:Friends"` — one, `"all"` — everything, plus `icon_count_except` — what not to count. The icon itself — an opossum holding its own tail (`app_icon = "possum"`, also in the menu and in About), or the drawn thread bubble (`"bubble"`), which `themed_icon` paints in the theme's colours.

**Activity's quick filters.** Over Activity — its rule's switches: Likes & boosts · Followers (who followed and who stopped) · Requests (waiting for your answer) · Mine (whom you followed) · Other (polls, edits, important people's posts, the server's notices); none pressed — everything. Since 0.22 these are the lane rule's ordinary switches (`switch`), as on any lane: rename them, drop them or make your own in the lanes' editor. The empty ones aren't shown: requests in a lane of their own — no “Requests”, without `activity.my_follows` — no “Mine”. In the terminal — `s`.

**Who stopped following you.** Every hour fedtail compares the whole list of your followers with the last one: missing from two lists in a row and not following when asked — a row “stopped following you” in Activity; an account that is no more — “gone”. So as not to lie: a list that didn't come whole (fewer than the server counts) is thrown away; the first snapshot is the start, no events; the ones you removed or blocked yourself aren't news; more than `unfollows_mass` of one server at once — one row about the server. A lane of rules takes them as `event = "unfollow"` (`"unfollowed_back"`: one you follow too), `"gone"`, `"lost"`. A follower who moved is “moved”, not an unfollow (`"moved"`). With `activity.unlikes` — likes taken back too (`"unliked"`): your last `unlikes_posts` posts of `unlikes_days` days, a request a post — so it is off. A post deleted on its server is marked on its card.

**Activity says whom you followed.** Followed someone — Activity has a row “@who — you followed”, beside what others did: what you did yourself is there. Followed in another client — fedtail notices it in whom you follow (every 6 hours). No unread number for it; × takes it away here only. A lane of rules takes it as `event = "i_followed"`.

**Someone new in a private talk — shown at once.** A private message that answers a private one and brings in someone who wasn't in it (its author or one it mentions) is marked “👤 New in this private talk: @who” — they now read this message and whatever it quotes. The reply box says the same before sending: write a private answer adding `@someone` from outside the talk, and under the text — “👤 You add to the private talk: @who”. Compared with the message answered: who wrote it and whom it mentioned.

**Push notifications (Web Push, UnifiedPush).** The web page subscribes the browser to push right at your server (≡ → “Push notifications…”): notifications come with the tab closed and fedtail off. Needs https or localhost. The phone — through UnifiedPush (`phone.push = "auto"`): with a distributor installed (ntfy, Sunup, NextPush…) the server pushes to it, the app wakes and does a round — the same notes as the windows' (`notify.lanes`, `notify.privacy`); without one — a round every 15 minutes. The windows and the terminal don't need push — the live stream and polling are enough.

**Slow mode and “notify at most every…”.** The news piles up and comes in one batch every 5, 10, 15, 30, 60 minutes or more — with its counts, notifications and sound; nothing stirs between batches to get in the way of work. The live stream wakes no poll meanwhile, Refresh asks at once; on the phone a push and the background round wait for their batch too, and the overview says when the next one comes. Each lane that notifies or chimes gets its own “notify at most every N minutes”: the lane updates as usual, its notifications and sound pile up and come in one batch (what was read meanwhile stays out of it); after a long quiet the first comes at once.

**“Of them new”: what the last update brought.** Beside the unread count, smaller — how many of them the last update that brought anything brought: “300” with “56 of them new” under it on the phone's tile, “300 +56” in the sidebar (the words on hover). What's read of the batch leaves the number. With slow mode — exactly what the last batch brought.

**Follow requests in any lane.** A follow request is an event like a like or a follow: any lane whose rule has `event = "follow_request"` takes it. By default — Activity, on top, with “Approve” / “Reject” (in the terminal — a / d), counted in its number; × leaves it be. With the “Follow requests” lane on, requests are there, not in Activity (`apart`). A request's row and buttons are the same in every lane and interface.

</details>

---

## Several accounts

| What | Status | Since | Config | API / protocol | Others |
|---|---|---|---|---|---|
| Profiles and the switcher | has | 0.3.0 | `accounts.switch_closes`, the launch key `--profile` | — | every multi-account client |
| The main profile ★ | has | 0.14.0 | ≡ → “Account and server” → “Make it the main one”; the mark `~/.config/fedtail/main-profile` | own | — |
| Log in again, log out | has | 0.14.0 | ≡ → “Account and server”, with a question | OAuth | everyone |
| All accounts in one window | has | 0.3.0 | `accounts.merge` | own | Ivory, Phanpy, Elk, Tokodon, Sengi, Whalebird |
| An account's colour in the shared window | has | 0.14.0 | `accounts.account_colors` | own | Fedilab |
| Acting as another account | has | 0.14.0 | `accounts.act_as` | the shared window, ⋯ → “From another account”: the post is looked up on its server | Sengi, Tokodon |

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
| Themes as files | has | 0.1.0 | `appearance.theme`, `appearance.font_size`, `appearance.fonts`, `appearance.font`, `appearance.mono_font`, `appearance.max_width`, `window.sidebar_width`, `card.actions` | a TOML format of its own | others — light and dark, Ice Cubes and Megalodon — colours of your own |
| Trying a theme without a restart | has | 0.15.0 | ≡ → “Try a theme”; for good — `appearance.theme` | — | Phanpy, Elk, Ice Cubes (they have few) |
| The config as a file in chapters | has | 0.6.1 | the launch keys `--update-config`, `--rebuild-config` | — | tut — TOML too, but not built by chapters |
| The settings reference | has | 0.13.0 | — | `tools/docs_build.py` | tut (a man page and a site), MediaWiki (an article per setting) |
| Window, tray, keys | has | 0.8.0 | `window.tray`, `window.close_to_tray`, `window.post_keys` | — | keys — Mastodon web, Phanpy, Elk, Ivory, tut |
| Links to posts and profiles — inside | has | 0.2.0 | `card.links_in_app` | `search?resolve=true` | Ivory, Phanpy, Elk, Megalodon, Fedilab |
| Open a link in the running fedtail | has | 0.14.0 | `fedtail open URL`; `--install-desktop` installs a `web+ap://` handler | own | Megalodon (share a link into the app) |
| Everything is stored locally, readable offline | has | 0.1.0 | — | SQLite in the profile's data folder | Tusky — partly, Ice Cubes — a Home cache |
| Open for days without bloating | has | 0.11.0 | `media.unload_hidden_minutes`, `media.keep_hidden_lanes`, `media.image_cache_mb`, `debug.trim_memory` | own | — |
| Polling the server and the live stream | has | 0.9.0 | `[poll]`: `interval_seconds`, `stream`, `stream_gap_seconds` | streaming (WebSocket) | Mastodon web, Phanpy, Elk, Tokodon, Whalebird, Ice Cubes |
| Errors in plain words and without spam | has | 0.13.0 | — | own | — |
| A detailed log for bug reports | has | 0.2.0 | `[debug]`, the launch keys `--debug`, `--bug-report` | own | — |
| A bug report straight into your private repository | has | 0.19.0 | `debug.report_repo`, `tools/selfcheck.py --send` | — | — |
| Report a bug on GitHub — checked first | has | 0.19.0 | `debug.issue_repo` | — | Fedilab, Tusky (a mail to the developer) |
| Federation status: how my server is doing and what fails | has | 0.16.0 | ≡ → “Debugging” → “Federation status” | own (from what this run saw) | — |
| Leak hunting: trends, an object census, memory snapshots | has | 0.14.0 | `debug.leak_samples`, `debug.object_census`, `debug.tracemalloc`; ≡ → “Debugging” | own (gc, tracemalloc) | — |
| The database doesn't grow for ever: cleanup and a size budget | has | 0.17.0 | `[storage]`: `max_mb`, `keep_per_lane`, `keep_activity`, `gc_hours`, `grace_hours` | SQLite, incremental vacuum | — |
| Screen readers | partly | 0.9.0 | `media.alt_text`, `appearance.accessibility` | — | Mastodon web, Tusky, Ivory |
| Interface language | has | 0.1.0 | `appearance.language` | — | everyone |
| Help inside, in two languages | has | 0.17.0 | ≡ → “Help” | own: `fedtail/data/help/<lang>/` | — |
| “What's this?”: a longer hint about any button | has | 0.17.0 | ≡ → “What's this?” for now; `window.whats_this` — from the start | own: `hints.toml` | KDE apps (What's This) |
| A sound scheme | has | 0.19.0 | `sound.*`, `tui.sound`; in the theme — `[sound] source`, `from` | own: the theme's `sounds/` folder | QIP, ICQ, Mail.ru Agent, Psi |
| A proxy, Ctrl+1…9, pinned tabs, the stream on Wi-Fi only, statistics, LibreTranslate and translating by itself | has | 0.21.0 | `server.proxy`, `server.proxy_at_login`, `window.number_keys`, `window.pin_tabs`, `phone.stream`, `reading.stats`, `card.translate_auto`, `card.translate_backend`, `card.translate_url`, `card.translate_key` | `/api/v1/statuses/:id/translate` or LibreTranslate's `/translate` | Tokodon (a proxy before login), FastSMRW (Ctrl+digit, pinned lanes), iMast (the stream on Wi-Fi only), Ivory (statistics), Fedilab and Scatto (translating by itself, another translator) |
| `fedtail --check`: what the system lacks — and one apt line | has | 0.21.0 | `fedtail --check` | own | only in fedtail |

<details><summary>In detail</summary>

**Themes as files.** Built in: `system` (as in KDE), `terminal`, `juick`, `juick-classic`, `bnw`, `point`, `night`, `contrast` (for weak eyes), `pink`, `nord`, `solarized`, `paper`, `qip-retro`, `qip-modern`, `mra`, `mra-blue`, `mra-green`, `mra-violet`, `psi` (in the spirit of messengers: “Name (time)” over a post, `card_header = "chat"`; with `window.layout = "split"` the theme sets the layout too: the faces — `shape.faces`, the roster's items — `roster_rows`, tabs in more rows — `tab_rows`), `debug` (for debugging: each state of a post — unread, the j/k cursor, found, “not seen whole yet, not read yet”, the keyboard focus — in a loud frame of its own; `shape.debug = true` turns the same on in any theme of your own). Your own — a file in `~/.config/fedtail/themes/`. A theme sets the card's layout too: the avatar's shape (`avatar_shape`), the header in a line or the name over the date (`card_header = "stacked"`), where the #id stands (`short_id`: by the name or under the post with the reply count), which side the buttons are on (`actions_align`), the line between posts (`rule`: solid or dashed), a hatched band under the titles of the lane and the post window (`header_stripes`) and a dark strip over it (`header_bar`), the colour of the main buttons, of the lane's title strip and of names. A theme sets the look of the whole app, not only colours; that's why separate card templates aren't needed (see Won't do). Fonts — `appearance.fonts`: the theme’s (the built-in ones bring their own with fedtail: PT Serif, PT Sans, IBM Plex, Source Sans, Open Sans, Arimo, Comfortaa, Nunito, Fira Mono — all with Cyrillic), the system’s, or your own (`appearance.font`, `appearance.mono_font`); a theme of yours can bring fonts (`[font] files`), and .ttf/.otf files in `~/.config/fedtail/fonts/` are picked up without installing them system-wide. The width of the posts column — `max_width` (`0` — the full width; the ↔ button at the top left switches it for now and remembers the choice until the next start), labels on buttons — `actions`.

**The config as a file in chapters.** The program only reads the config. A new version brought settings — `--update-config` adds them to the right chapters with explanations; `--rebuild-config` rebuilds the file anew, keeping your values. A value written by hand stays yours when the default changes.

**The settings reference.** The config reference, built from the example configs: every setting with its description, choices and default, in tables by chapter, in Russian and in English. A test makes sure it keeps up with the files.

**Window, tray, keys.** The cross hides to the tray; the tray icon can go altogether (`window.tray = false`, since 0.19). `j`/`k` — through posts, `r` — reply, `f` — like, `b` — boost, `m` — bookmark, `o`/Enter — the thread. `post_keys = false` — the letters do nothing.

**Links to posts and profiles — inside.** @mentions, #tags and links to fediverse posts and profiles open in fedtail. Not found — the browser. Only web addresses go outside (and mailto:, xmpp:, gemini://, magnet:): fedtail won't open a link to a file or a network share from someone's post.

**Open a link in the running fedtail.** `fedtail open URL` from a terminal or a browser opens a post or a profile in the window already open (or starts it and opens it there). `--install-desktop` makes fedtail the handler of `web+ap://` links — the “open in your app” buttons on servers' pages.

**Open for days without bloating.** A lane not opened for `unload_hidden_minutes` minutes lets its cards go from memory; only the `keep_hidden_lanes` opened last keep them (since 0.22: one opened before lets them go the moment another comes to the front); the one open is never unloaded. fedtail gives the freed memory back to the system (`trim_memory`: otherwise glibc keeps the peak after a night of lanes and pictures).

**Polling the server and the live stream.** A poll every `interval_seconds` (at least 30). The live stream (`"auto"`, if the server offers it) wakes the poll at once, but not more often than every `stream_gap_seconds`. The stream only wakes, so if it drops (a laptop asleep, a proxy) nothing is lost.

**Errors in plain words and without spam.** A server behind a proxy is down — instead of Cloudflare's HTML page one line “Bad Gateway — the server is down or not answering”; the same error of every poll is shown and logged once, again only when it changes or ten minutes later.

**A detailed log for bug reports.** In the debugging mode (`mode = "auto"` — on in development versions, off in releases): a log of requests, polls, actions (without the posts' texts), errors with tracebacks, memory and thread stats every `stats_minutes`, a freeze watchdog (`watchdog_seconds`, `stall_ms`), slow requests, memory growth. `crash.log` — the stacks on a crash, `kill -USR1` — the stacks on demand. The new version deletes the old version's logs itself. `--bug-report` packs two days of it, without the token and the database. In detail — [debugging.md](/docs/en/dev/debugging.md).

**A bug report straight into your private repository.** With `debug.report_repo` set (`"user/repo"` on GitHub or any git address), the report from the Debugging menu, `--bug-report` and the nightly selfcheck's archive go there by themselves over ssh with your own keys: a commit of its own in `reports/YYYY-MM/` (`selfcheck/…`). The older reports aren't downloaded; ssh asks nothing — no key or no access, it says so. The repository must be private: a report holds the logs and the config (never the token or the database).

**Report a bug on GitHub — checked first.** ≡ → “Report a bug on GitHub…” in all four interfaces: a draft issue — what happened, how to repeat it, the version, the system, the latest errors of the log. Server addresses, nicknames, IPs, tokens and paths are already replaced by placeholders, and all of it is shown before anything leaves: the text can be edited. Then GitHub opens with it all filled in, and you send it yourself. The tracker — fedtail's own, or `debug.issue_repo`.

**Federation status: how my server is doing and what fails.** ≡ → “Debugging” → “Federation status”: problems that don't depend on the client. My server — what it runs, how many answers and how many with errors, how fast it answers (typical and slow ones), polling (the last good one, how many times it failed and why), the live stream (open since when, how many times it dropped). What the server can't do (asked and got “no”). Who waits to go into a list: the name linked to the profile (opens in a tab, with “Follow”) and why they wait — a request unanswered, no follow (refused or withdrawn), or followed and going in by itself. What fails on my server and on other servers — grouped by request (ids folded: `/api/v1/lists/:id/accounts`), how many times, when last, and what it most likely means (“deleted on that server”, “won't give strangers anything without a signature”, “lists take only people you follow”…). Other servers — who answered how much and with what errors. The window updates by itself while open; “Copy” — as text for an issue, “Count anew” — start from zero. For the window only your own server is asked — who those waiting in lists are; the rest is what this run saw. Addresses without parameters, no tokens.

**Leak hunting: trends, an object census, memory snapshots.** For days-long runs. With every stats line — a `trend` line: memory, Python objects, widgets, cards, pictures, threads, files — how many at start, how many now, how many an hour. Something that grew on each of the last `leak_samples` checks (12 — an hour) and by more than crumbs — a `possible leak` warning with the numbers; the first half hour doesn't count. In the debugging mode — a census: which Python objects and Qt widgets were added since the last check and since the start (`object_census`). `tracemalloc = true` — memory tracing from the start; a snapshot — ≡ → “Debugging” → “Memory snapshot”: a file with who holds the most and what grew, by line of code. There too: “What grows: stats and census now”, “Give free memory back to the system”, tracing on/off. The session's last line — `session summary`: hours, memory, peak, freezes, polls. How to leave it overnight — [debugging.md](/docs/en/dev/debugging.md).

**The database doesn't grow for ever: cleanup and a size budget.** Every `gc_hours` (and at the first poll after start) posts nothing points at are forgotten: no lane, followed thread, “Activity” entry or reply draft. My own posts stay, and so do the boosted post, the quoted one and the parents up the whole thread of every post that stays, so visible replies aren't fetched again. Whatever was stored recently (an open thread, a profile) lives `grace_hours` more. “Activity” keeps the latest `keep_activity` entries. The file really shrinks (incremental vacuum). If the database is still over `max_mb` (1 GB by default), lanes get 30 % shorter until it fits (never below 300) and grow back to `keep_per_lane` once there is room. Short ids (`#a3f`) are never forgotten. What was forgotten and how big the database is — the `storage gc` line in the log.

**Screen readers.** Picture descriptions and button names for screen readers are there, but the interface hasn't been tried live with Orca. The GTK window talks to the accessibility bus only while a screen reader is on (`appearance.accessibility = "auto"`; `"on"` — always): KDE runs that bus always, and with no reader a menu took two seconds to open.

**Interface language.** `"auto"` (from LANG), `"ru"`, `"en"`.

**Help inside, in two languages.** A panel in the main window, like the compose panel: the contents on the left, search through the whole help, Back and Forward. Short, by section, and at the end of each — “In detail →” into the full feature list and the settings reference: they are right here and work offline. No shortcut on purpose — F1 is next to Esc.

**“What's this?”: a longer hint about any button.** Turn it on, and hovering shows a longer hint instead of the short one: what the button does, which config key changes it and which help section says more. The same menu item turns it off.

**A sound scheme.** Sounds are part of a theme, as its pictures are. The messenger themes bring their own sets: `qip-retro` (and `qip-modern`) — bright “pip-pip” and a knock at the door when signing in, `mra` (and its colours) — round “blop”s and a xylophone, `psi` — soft chimes, `point` (and `juick`) — dry wooden ticks; `system` plays the desktop's sounds (the KDE/GNOME sound theme through `canberra-gtk-play`; without it a quiet set of fedtail's own), `terminal` and `bnw` — a beep. Your own sounds — a `sounds/` folder by the theme (`message.wav`, `reply.wav`, `mention.wav`, `direct.wav`, `thread.wav`, `request.wav`, `activity.wav`, `online.wav`, `sent.wav`); a missing one comes from the parent theme, from `[sound] from`, then a lighter sound of the same set. By default (`sound.enabled = "auto"`) development versions sound and releases are silent; `"on"` / `"off"` — always / never. A batch of news chimes once, with the weightiest sound (private → reply → mention → thread → request → activity → message), no more often than `sound.min_gap_seconds`; lanes — `sound.lanes` / `sound.except`, signing in and sending — `sound.online`, `sound.sent`; another theme's scheme whatever the look — `sound.scheme`, volume — `sound.volume`, the player — `sound.player` (by default pw-play, paplay, aplay; afplay on macOS; Windows itself). Qt and GTK alike; the terminal beeps (`tui.sound`), the web plays in the browser. ≡ → Debug → “Test the sound”. Every set is synthesised by `tools/make_sounds.py` — our own, GPL.

**A proxy, Ctrl+1…9, pinned tabs, the stream on Wi-Fi only, statistics, LibreTranslate and translating by itself.** `proxy` — a proxy for everything: the API, pictures, the live stream (through an HTTP proxy), sync, the login; `socks5h://…` — with PySocks. `proxy_at_login` — a "Proxy" field in the login window (Qt, GTK, the terminal, the web page, the phone): what you type is written into config.toml and used at once. `number_keys` — "ctrl" or "both": a lane by its number with Ctrl+1…9 too (the windows). `pin_tabs` — right-click a thread's or a profile's tab: a pinned one won't close by ×, Ctrl+W or Esc (the windows). `phone.stream = "wifi"` — the live stream on Wi-Fi only, polling on a mobile network. `stats` — "Statistics" in the ≡ menu: the week day by day (Home, my posts, activity) who fills Home the most and what was shared most. `translate_backend = "libretranslate"` with `translate_url` (and `translate_key`) — "Translate" through LibreTranslate, even when the server can't. `translate_auto` — posts in languages you neither read nor write translate by themselves, marked "translated from …".

**`fedtail --check`: what the system lacks — and one apt line.** What is a must, what each interface needs and what the extras give (the emoji font, WebP, the language check…) — whether it's there, and a ready `sudo apt install …` line for what's missing. Started without a must-have — the same line instead of a traceback.

</details>

---

## Interfaces

The core knows nothing about a GUI; interfaces are plugins. Which one to start — `window.frontend`, or `--ui` for one run.

| What | Status | Since | Config | Others |
|---|---|---|---|---|
| A Qt window | has | 0.1.0 | `window.frontend = "qt"` | the main one |
| Commands in a terminal | has | 0.9.0 | `[cli]`: `enabled`, `color`, `max_lines`, `tail_lanes` | tut (TUI), toot (CLI) |
| Android: a phone and a tablet | partly | 0.19.0 | `[phone]`: `overview`, `layout` | Tusky, Fedilab, Moshidon |
| A terminal interface (Textual) | has | 0.10.0 | `window.frontend = "tui"`, `[tui]`: `theme`, `lanes_width`, `show_context`, `pictures`, `picture_rows`, `viewer`, `video` | tut |
| Web on localhost | has | 0.10.0 | `window.frontend = "web"`, `[web]`: `host`, `port`, `open_browser` | Phanpy, Elk — web clients |
| The terminal — everything the windows have | partly | 0.19.0 | `window.frontend = "tui"`, `tui.sound` | — |
| The web — everything the windows have | partly | 0.19.0 | `window.frontend = "web"` | — |
| GTK4 + libadwaita | has | 0.17.0 | `window.frontend = "gtk"`, `appearance.adwaita` | Tuba |
| Toga (BeeWare) | planned | — | — | — |

<details><summary>In detail</summary>

**Commands in a terminal.** `fedtail lanes`, `fedtail show replies -n 20`, `fedtail tail` (the new as it comes), `fedtail post "text"`, `fedtail post --reply a3f "text"`, `fedtail read replies`. The same profile, database and read marks as the window; works without Qt.

**Android: a phone and a tablet.** An APK in every release (`fedtail-X.Y.Z-android.apk`), dev builds from CI. Native screens (Kotlin, Jetpack Compose) over the same Python core the desktop runs. Home is the overview of lanes: tiles four in a row — which and in which order is picked with a long press and travels to the other devices with sync (`sync.tiles`) — or a list with each lane's first unread post (`phone.overview`), “Read in a row” — yours first. In a lane — the lanes with news as a strip, a switcher with a search, “read → next” at the end and a swipe there. Threads as trees, replies, likes, pictures with a viewer, video and sound in a player of its own; every place of the windows' ≡ menu (search, lists, filters, silence, trends, the server, help, editing the profile, accounts), profiles with their buttons, pinned posts and “more” as far back as their own server, the windows' ⋯ menu on every card, voting, quotes; the editor — pictures with descriptions, a warning, the language, a poll, edits and quotes. Refresh — ⟳ on every screen and a pull: from the top, or, read “as a forum” (oldest first), up from the bottom; the place in the lane doesn't jump. Notifications into the shade (the windows' `notify.*`), with the app closed — every 15 minutes. The windows' themes as colours (`appearance.theme`); settings as a page (each option of the config with its explanation, written into the same file) or the file itself, read marks synced. On a tablet — two or three columns, as on the desktop (`phone.layout`). Point's command line is off on the phone (`window.command_line`).

**A terminal interface (Textual).** Lanes on the left, posts on the right, the command line at the bottom. The same keys, `x` — the lane is read, `:` — the command line. Lanes — `[` / `]`, digits `1`…`9`, `h` — into the lane list (`j` / `k` there), `l` — back to the posts, Tab — to and fro. “Activity” and “Follow requests” have rows of their own (in requests `a` — accept, `d` — reject). Pictures — the first one small right in the lane (`tui.pictures`, `tui.picture_rows`), `v` — all of them full screen, ← / → between them, `o` — the original in the browser; needs Pillow (`python3-pil`). Since 0.19 real ones (sixel in Konsole, WezTerm, foot; the kitty protocol in kitty) with `textual-image` installed, half blocks in any true colour terminal otherwise; with `chafa`, `timg` or kitty's `icat` there, `v` hands the picture to them, the interface stepping aside until Enter (`tui.viewer`). Video and gifs play in `mpv` (since 0.19): in a window of their own on a desktop, right in the terminal over ssh (sixel, kitty or coloured text); no mpv — the browser (`tui.video`). Works over ssh. Needs `python3-textual`.

**Web on localhost.** fedtail in a browser tab: lanes, threads as trees, profiles, a “Write” button (content warning, who sees it, language, drafts), pictures in a grid with a viewer, video and audio, polls with voting, link cards, quotes, custom emoji, “More” at a lane's end, the Point command line; on a phone the lanes slide in from the side, light and dark follow the system. At start a one-time link (15 minutes) is printed; the browser gets a key from the profile's folder in a cookie (`web.key`; delete it and every browser and every old link with the key is out). `host = "0.0.0.0"` — from the phone on the home network too; no encryption, for your own network only. The ≡ menu (write, my profile, refresh, all read, help, keys, about); a post's ⋯ menu — the same as the Qt and GTK windows', the same items in the same order (since 0.18: open, copy the link, the #id and the handle, reply with quote, call into the thread, bookmark, who quoted, subscribe / mute the thread, mute / block the author and the server, report, edit, pin, delete, delete and redraft — the risky ones ask first); a profile's buttons as in the windows too (follow, the bell, boosts and languages in Home, mention, mute, block, remove from followers, endorse, a note). A reply shows the whole post: select a piece and “❝ Quote in reply” puts it where the cursor is. The viewer goes through a post's pictures with ← / →.

**The terminal — everything the windows have.** Since 0.19: a post's menu `.` (⋯) — the windows' items, doing the same (links through the shared `common/links.py`, “sure?” asked); the `g` menu (≡) — every place: search (`/`), lists, tags, silence, held-back notifications, scheduled, follow requests, activity, trends, suggestions, the directory, the server, editing my profile, the help (Markdown, links between its pages), what's new, about, the federation status, a bug report, testing the sound; a profile — the windows' buttons under `1`…`9`; the post editor `w` (the warning, who sees it, the language, drafts — as in the windows; Ctrl+O — attachments with descriptions, “sensitive”, a poll, later; Ctrl+S — send); a lane as in the windows: the “new below” divider, `s` — all / posts only / new, feed / conversations, what to show; a card in the windows' words (who boosted, edited, old, what it answers, “you replied”, the quote, reactions); find in the lane Ctrl+F (again — the next one, `N` — the one before, `D` — deeper, through everything stored, `E` — in every lane, Esc — closed); `J` — to the new, `j` past the last post — older ones from the server; a poll — `u`: vote (Space, Enter), `r` — the results, refresh; a thread — how many answers, `c` — every warning at once, `s` — follow it, “comes because…”; the lane list's sections fold (Enter on a heading, one state with the windows); the editor — the count, “a chain of N posts”, the #CamelCase hint, Ctrl+R — preview, Ctrl+O — “Another language…”, “Discard” (asked first), the alt-text reminder; the picture viewer — `s` saves the original into `media.save_dir`; notifications — notify-send, and without a desktop the terminal's own code (kitty, Ghostty, WezTerm, foot, iTerm2); ≡ → “Debugging” — the corner, a test notification, the census, giving memory back, tracing, a snapshot, the config and the data folder, “every account in one window” (and “⇄ @account” on a card). The places are the web's (`common/places.py`). The behaviour is held against the windows by one scenario (`tools/behaviour.py`). What's still missing — `tools/parity.py`.

**The web — everything the windows have.** Since 0.19 the ≡ menu has every place (since 0.20 the menu is a window over the page, in groups as the windows' submenus, and the places open in a window over the page): search (`/`), lists (new, rename, exclusive, members, delete), tags, silence (word filters, muted, blocked, servers), held-back notifications, scheduled, follow requests, activity, trends, suggestions, the directory, the server, editing my profile, the help right on the page, what's new, about, the federation status; “Activity” and “Follow requests” have the windows' groups and buttons; the ⋯ menu has “Add to list”, “Read it whole”, “Translate”; a profile has all the windows' buttons (lists, whom they follow, followers, editing my own); find in the lane Ctrl+F; over the lane — “all / posts only / new”, “feed / conversations”, “show”, “to new”, the “new below” divider; a card in the windows' words (who boosted and when, edited → versions, old, what it answers, “you replied”, the quote, reactions); the editor — pictures and files with descriptions (pasted too), “sensitive”, a poll, sending later, the languages, the count against the server's limit; the browser's notifications (≡ → “Notifications in the browser” — allow) in the windows' words (`notify.privacy`); the theme's sounds. The places are the terminal's (`common/places.py`). The behaviour is held against the windows by one scenario (`tools/behaviour.py`). What's still missing — `tools/parity.py`.

**GTK4 + libadwaita.** To look native in GNOME and other GTK desktops. It has: login, lanes in groups with their unread counts, posts as cards (the face, what a reply answers, the content warning, pictures, a poll's results, the quoted post, the link's card, “you replied”), the post's buttons and menu — the same as Qt's, asking before the risky ones, seen means read, “All read”, “earlier”, threads in tabs, writing / replying / quoting / calling in / correcting with drafts, who sees it, the warning, pictures with descriptions, a poll and Tab completion, the Point command line (Ctrl+L), profiles in tabs, Activity, follow requests, notifications, fedtail's themes. Since 0.18 also: find in the lane (Ctrl+F), the split layout, the picture viewer, help as a panel, voting in polls, translating a post, “read it whole”, an edit's history, reporting, who liked and boosted, quotes of my post, “read up to here”, a profile with all of Qt's buttons and editing my own, quotes saying why one can't be shown. Also since 0.18: a thread's header (subscribe, “open every CW”, why its replies show), a profile paging back and on — from the author's server, pinned posts and featured on a profile, lists (add, members, rename, delete, exclusive), groups of tags, a tag's follow and “feature on my profile”, the server's announcements, the curtain on Esc, a video player over the window (needs `libgtk-4-media-gstreamer`), the tray (StatusNotifierItem over D-Bus), selecting text with “Quote in reply”, a contact card on hover in split, a picture's focus point and description, the account mark in the merged window, pictures and files into a post by dragging and from the clipboard (Ctrl+V, screenshots too; dropped on the window — a new post with them). In the deb package GTK is in Recommends, and the GTK window is “FedTail (GTK)” on a right click on the menu entry. What Qt has and GTK doesn't — `tools/parity.py` (but menu items' tooltips: GTK menus have none). Needs `python3-gi gir1.2-gtk-4.0`; libadwaita (`gir1.2-adw-1`) is optional.

**Toga (BeeWare).** Native widgets of Windows, macOS, GTK, Android from one code. To try out.

</details>

---

## Builds and installing

| What | Status | Since | Note |
|---|---|---|---|
| From the source: `python3 -m fedtail` | has | 0.1.0 | PySide6 and requests |
| Linux: one file | has | 0.5.0 | `fedtail-X.Y.Z-linux-x86_64`, built on Debian 12 |
| A deb package | has | 0.10.0 | built in CI on Debian 13; since 0.18 GTK 4 in Recommends, the GTK window an action of the menu entry (“FedTail (GTK)”, right click) |
| Windows: one .exe | has | 0.5.0 | `fedtail-X.Y.Z-windows.exe` |
| A menu entry with the icon | has | 0.2.0 | by itself when a window starts (`window.desktop_entry`), or `--install-desktop`; named `online.dmesg.fedtail.desktop` (since 0.18) |
| An apt repository of its own | partly — CI builds and signs it after every release — once the repository has the key (APT_GPG_KEY) and GitHub Pages is on for the `apt` branch | 0.20.0 | from the releases' deb packages (`packaging/apt_repo.py`) |
| An installer for Windows (and a signature) | has | 0.20.0 | `fedtail-X.Y.Z-windows-setup.exe` (Inno Setup): for you alone, no administrator, a Start menu entry, an uninstaller; signed once CI has a certificate |

---

## Five interfaces

fedtail is a Qt window (KDE, Windows), a GTK window (GNOME), a terminal, a web page and an Android app; they share one core. Below is only what isn't everywhere, and why. ✓ — has it, ◐ — in part, — — no, · — doesn't belong there. A test keeps the table honest: a function that appears or goes in one of the desktop interfaces doesn't pass without its line here; the phone has screens and words of its own — its column is checked against its code by hand, and all the phone lacks so far is in the next chapter.

### The window, accounts, logging in

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| Pinned tabs | ✓ | ✓ | · | · | · | ui.pin_tabs: right-click a thread's or a profile's tab. The terminal, the web page and the phone have no such tabs — a thread and a profile open over the lane and go with "back". Android: No tabs: screens stack, "back" is the one before. |
| The tray icon | ✓ | ✓ | · | · | · | A terminal and a browser tab have no tray. Android: a phone has no tray |
| The curtain (Esc closes the lanes) | ✓ | ✓ | · | · | · | In the terminal and on the web page Esc steps back; there is nothing to close. Android: a phone has no Esc |
| Lanes in columns | ✓ | ✓ | · | ✓ | ✓ | The terminal — one lane at a time. The web page — columns by ❯, as the windows' (at a phone's width, one lane); the phone — on a tablet (the overview, a lane, a thread side by side). |
| The roster and the messages window, as in QIP (`window.layout = "split"`) | ✓ | ✓ | · | · | · | The two-window layout is Qt's and GTK's only. Android: a desktop's window layout |

### Reading

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| Someone's older posts from their own server | ✓ | ✓ | ◐ | ✓ | ✓ | The web page as the windows: the page's addresses at once, the posts four at a time, a live “n of N” on the button. The terminal fetches a whole page with “more” and then says how many came — no live count. |

### Pictures and video

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| The picture viewer: leaf through, 1:1, the original, save | ✓ | ✓ | ◐ | ◐ | ✓ | The terminal shows a picture full screen (chafa, kitty) and saves the original (`s`); the web page has its viewer with Save and 1:1. The window's words about Qt's formats and “the original is loading” aren't theirs. |
| Video and sound inside the program | ✓ | ✓ | ◐ | ◐ | ✓ | The terminal plays in mpv (a window, or in the terminal itself), the web page — in the browser's player. |

### The editor

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| A picture's focus for previews | ✓ | ✓ | · | ✓ | ✓ | A terminal has nothing to click a picture with; the focus stays in the centre. |
| Formatting buttons in the editor | ✓ | ✓ | ◐ | ✓ | ✓ | post.format_bar: bold, italic, strikethrough, code, a link, a quote, a list — Markdown marks around the selection. In the terminal — by the buttons with the mouse only: Ctrl+B/I/K belong to the text field there (Ctrl+I is Tab). |
| Spell checking in the post window | ✓ | ✓ | ◐ | ◐ | ◐ | The windows underline mistakes and fix them with a right click; the terminal — as a list on F7 (its input has no underline); the web page — the browser's own checker in the post's language. Android: the phone's keyboard checks |

### The server, settings, help, debugging

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| The settings window: search, restart, “open the file” | ✓ | ✓ | ◐ | ◐ | ✓ | The terminal and the web page edit the same config.toml with a form by chapters, with a search and “Open the file” (the terminal: in $EDITOR, the web page copies its path). No restart: they're restarted the way they were started; “the file changed outside” isn't needed — the place reads the file anew each time it opens. |
| Themes: try one, the themes folder | ✓ | ✓ | ◐ | ◐ | ◐ | The terminal has themes of its own (`tui.theme`). The web page takes the windows' themes' colours and font and tries them from the ≡ menu, but doesn't open the themes folder: the page is a guest in the browser. Android: the windows' themes' colours, fonts and pictures, “try” in the menu; no themes folder |
| Open the config and the data folder | ✓ | ✓ | ✓ | · | ◐ | The terminal opens the config in $EDITOR and copies the paths (≡ → “Debugging”); the web page has no access to the machine's files. Android: the config is edited in the app; no data folder |
| Debugging: the log, a report, the sound, the stacks | ✓ | ✓ | ✓ | · | ✓ | The web page is a guest in a browser: a report is made in the window, the terminal or `fedtail --bug-report`. |
| Memory debugging: census, snapshot, tracing, giving memory back | ✓ | ✓ | ✓ | · | · | Leak hunting is the windows' and the terminal's; the web page is a guest in a browser. Android: a desktop tool |
| Tooltips and “What's this?” | ✓ | ✓ | · | ◐ | · | A terminal has no pointer to hover — its hints are in the key line at the bottom. The web page has tooltips on buttons, lanes and menu items; no “What's this?” mode (the browser shows a tooltip on hover anyway), and none for what the page doesn't have (editor size, tracing). Android: nothing to hover with |

---

## Android: what the phone has and hasn't yet

The features of the list above that the Android app lacks or has in part (◐ — in part, — — no, · — a phone doesn't need it). All the rest the phone has.

### Lanes

| What | Android | Why |
|---|---|---|
| A messenger's layout: a roster and a messages window | · | not a phone thing |
| A library of pictures for your own lanes | · | the phone's lanes wear its own icons |

### Threads

| What | Android | Why |
|---|---|---|
| Threads: where replies come from, growing by itself, only the followed, by branch, "Around this post" | ◐ | no ] [ − keys on a phone; the rest as everywhere |

### Read marks and place

| What | Android | Why |
|---|---|---|
| Esc draws a curtain instead of closing the window | · | a phone has no Esc |

### The post card

| What | Android | Why |
|---|---|---|
| No emoji at all | ◐ | the setting is there; the phone's own emoji are drawn by its font |

### Pictures and video

| What | Android | Why |
|---|---|---|
| Video without a hardware decoder (the default) | · | the phone decodes by itself |
| Memory for pictures | · | the Coil loader looks after pictures' memory |

### Writing

| What | Android | Why |
|---|---|---|
| Spell checking in the compose panel | ◐ | the phone's keyboard checks; no checking of fedtail's own |

### The application

| What | Android | Why |
|---|---|---|
| Window, tray, keys | · | a phone has no window, tray or keys |
| Leak hunting: trends, an object census, memory snapshots | · | a desktop tool |
| “What's this?”: a longer hint about any button | · | nothing to hover with |
| A sound scheme | · | no sound on the phone |
| A proxy, Ctrl+1…9, pinned tabs, the stream on Wi-Fi only, statistics, LibreTranslate and translating by itself | ◐ | The proxy, the proxy field at login, the stream on Wi-Fi only, statistics and translation — yes; the phone has no keys and no tabs. |
| `fedtail --check`: what the system lacks — and one apt line | · | the app has it all inside |

### Interfaces

| What | Android | Why |
|---|---|---|
| A Qt window | · | not a phone thing |
| Commands in a terminal | · | not a phone thing |
| A terminal interface (Textual) | · | not a phone thing |
| Web on localhost | · | not a phone thing |
| The terminal — everything the windows have | · | not a phone thing |
| The web — everything the windows have | · | not a phone thing |
| GTK4 + libadwaita | · | not a phone thing |

### Builds and installing

| What | Android | Why |
|---|---|---|
| From the source: `python3 -m fedtail` | · | not a phone thing |
| Linux: one file | · | not a phone thing |
| A deb package | · | not a phone thing |
| Windows: one .exe | · | not a phone thing |
| A menu entry with the icon | · | not a phone thing |
| An apt repository of its own | · | not a phone thing |
| An installer for Windows (and a signature) | · | not a phone thing |

---

## ActivityPub directly

Everything here is a request to other servers without your token: they see only your IP. Servers that require signed requests (secure mode) simply give nothing, and fedtail quietly makes do with what your own server knows.

| What | Status | Config |
|---|---|---|
| A whole thread: replies from the author's server | has | `threads.complete_threads` |
| A thread grows when Mastodon has gathered the replies | has | `threads.complete_threads` |
| Long texts and events | has | `card.long_form` |
| Honest counters | has | `card.honest_counters` (off), `card.counters_via_accounts` |
| A little-known person's profile — from their server | has | `people.remote_profiles`, `people.remote_posts` |
| Posts older than my server knows | has | `people.remote_profiles` |
| Followers and follows from the person's server | has | `people.remote_people` |
| The person has moved | has | `card.show_moved` |
| The author's server software | has | `people.server_info` |

---

## Plans

Each feature comes switchable, one at a time, with its entry here and a line in the CHANGELOG. The order is rough: the cheap first, the big later.

| What | Chapter | Config | Size |
|---|---|---|---|
| Toga (BeeWare) | Interfaces | — | large |

## Won't do

| What | Why |
|---|---|
| Subscribing to old threads in a batch | Taken off the queue. |
| Boost carousel | Sideways is awkward to read, and it fits badly with “nothing jumps” and read marks. Boosts are hidden with the filter, per person or with a list. |
| Card templates (like tut's `toot.tmpl`) | A theme already sets the look of the whole app; a second layer of templates over themes adds nothing. |
| AI helpers in the compose panel (as in Ice Cubes) | Writing is the author's job. |
| A node admin panel in the client | Sitting in a client logged in as an admin is irresponsible. If a node ever needs setting up, there'll be a separate tool for it. |
| Mastodon's annual report | It's about neither reading nor conversation. |
| An XMPP gateway | Taken off the queue. |

## Not there and not decided

| What | Others | Note |
|---|---|---|
| The token from an external command (`pass`, `gopass`) | tut | It's unclear what this would add over a file readable by its owner only. |
