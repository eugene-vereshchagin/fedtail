# fedtail settings

[По-русски](/docs/ru/config.md)

Every key of the config, in tables by chapter. **This file is built** from
`fedtail/data/config.example.en.toml` by `python3 tools/docs_build.py` — edit the
explanations there, not here (a test checks this file keeps up).

Which feature stands behind a key and how other clients do it —
[the feature list](/docs/en/features.md).

## How the config works

Every setting is here, with its default value and an explanation. Change what you need and restart fedtail. The program only reads this file and never writes it.

A value written here stays yours even if a new version changes the default. Want the program's default always — comment the line out (# at the start) or delete it.

A new version brought new settings — `python3 -m fedtail --update-config` adds them to the right chapters (the old file is kept as config.toml.bak). To rebuild the file anew, in chapters, with your values — `python3 -m fedtail --rebuild-config`. The full reference of the current version always lies next to it: config.example.en.toml (and config.example.ru.toml — the same in Russian).

Where it lives: ~/.config/fedtail/<profile>/config.toml  (without --profile — the main profile, ★)

## Launch keys

| Key | What it does |
|---|---|
| `-p, --profile NAME` | a profile = an account with its own config and data (without it — the main one) |
| `-c, --config FILE` | another config instead of the profile's |
| `-d, --data FOLDER` | another data folder instead of the profile's |
| `--ui qt\|tui\|web` | a window, a terminal or a browser (for one run; for good — ui.frontend) |
| `--layout single\|columns\|split` | the window's layout for one run (for good — ui.layout) |
| `--theme NAME` | the theme for one run (for good — ui.theme) |
| `--profiles` | which profiles there are — and exit |
| `--update-config` | add this version's new settings to this file with explanations — and exit |
| `--rebuild-config` | rebuild this file by chapters, with your values — and exit |
| `--install-desktop` | add fedtail (this profile) to the menu with its icon — and exit |
| `--debug` | a detailed log for this run, into the terminal too |
| `--bug-report` | pack the logs and system details into an archive for a bug report — and exit |
| `-V, --version` | the version — and exit |
| `COMMAND` | work in the terminal without a window: lanes, show, tail, read, post (fedtail COMMAND -h — about each one in detail) |

## Chapters

- [1. Look and window](#1-look-and-window) — `[ui]`
- [2. Reading the feed](#2-reading-the-feed) — `[feed]`
- [3. Read marks](#3-read-marks) — `[read]`
- [4. Which lanes](#4-which-lanes) — `[lanes]`
- [5. Posts](#5-posts) — `[post]`
- [6. Notifications](#6-notifications) — `[notify]`, `[sound]`
- [7. Activity](#7-activity) — `[activity]`
- [8. Lists](#8-lists) — `[lists]`
- [9. Thread subscriptions](#9-thread-subscriptions) — `[subs]`
- [10. Polling the server](#10-polling-the-server) — `[poll]`
- [11. The server](#11-the-server) — `[account]`, `[sync]`
- [12. Database and logs](#12-database-and-logs) — `[storage]`, `[debug]`
- [13. In a terminal](#13-in-a-terminal) — `[cli]`, `[tui]`
- [14. In a browser](#14-in-a-browser) — `[web]`
- [15. On a phone and a tablet](#15-on-a-phone-and-a-tablet) — `[phone]`

## 1. Look and window

### How it looks

| Key | Default | What it does |
|---|---|---|
| `ui.theme` | `"system"` | The theme — a file in ~/.config/fedtail/themes/<name>.toml or a built-in one:<br>"system" — light/dark, as in KDE;<br>"terminal" — green on black, everything monospace;<br>"juick" — juick.com around 2013: a light grey page, white posts, blue links;<br>"juick-classic" — juick.com around 2011: an olive background, beige posts;<br>"bnw" — bnw.im: a black frame, grey posts, everything monospace, green buttons;<br>"point" — point.im today: a white page, posts split by a thin line, square avatars, the name over the date, #id \| replies under the post, buttons on the right;<br>"night" — dark, in colours of its own, on any desktop;<br>"contrast" — for weak eyes: large, black on white, sharp lines;<br>"pink" — pink: powder and berries, soft corners, little flowers;<br>"nord" — arctic dark: cold blue-grey, frosty links;<br>"solarized" — Solarized light: warm paper, blue links;<br>"qip-retro", "qip-modern", "mra", "mra-blue", "mra-green", "mra-violet", "psi" — in the spirit of QIP under Windows XP and QIP Infium, the Mail.ru Agent (orange, blue, green, violet) and Psi+: "Name (time)" over each post, mine in a colour of its own; with layout = "split" they set its look too;<br>"paper" — warm paper and a book typeface, for long threads;<br>"debug" — for hunting what's unfinished: unread, the j/k cursor, found, "seen not whole", the keyboard focus — each in a loud frame of its own. Your own themes: see ~/.config/fedtail/themes/README.txt |
| `ui.font_size` | `0` | The font size of posts in points, 0 = the system's. |
| `ui.fonts` | `"theme"` | Whose fonts:<br>"theme" — the theme's: the built-in ones bring their own with fedtail (PT Serif in paper, IBM Plex in terminal and nord, Source Sans in night and solarized…), nothing to install; system's are the system's;<br>"system" — the system's, whatever the theme says (as in KDE);<br>"custom" — your own, from font and mono_font below. |
| `ui.font` | `""` | With fonts = "custom", the font of the whole window. A list works, the first one there is taken: "Inter, Noto Sans". The system's fonts do, the ones that come with fedtail (by name: "PT Sans", "IBM Plex Sans", "Open Sans"…), and .ttf / .otf files in ~/.config/fedtail/fonts/ — no need to install those. "" — the system's. |
| `ui.mono_font` | `""` | With fonts = "custom", the fixed-width one, for #ids and /N; "" — the system's. |
| `ui.max_width` | `760` | The width of the posts column in pixels, 0 = the full width. The ↔ button at the top left switches it for now (remembered until the next start), the config isn't touched. |
| `ui.layout` | `"single"` | How the window opens: "single" — one lane on the right, "columns" — several lanes side by side, in columns, as in TweetDeck. The ❯ button at the top left switches it too, but the window always starts as set here. "split" — as in QIP, Psi or the Mail.ru Agent: the lanes in a narrow roster window (what's new in each, a line of the newest post and its author's face), and the main window is the messages window, without the sidebar, an input line at its bottom; a double click on a roster item opens it, closing its last tab closes it. Closing the roster closes fedtail (to the tray with close_to_tray). The old name "qip" is understood too. |
| `ui.roster_on_top` | `false` | With layout = "split": the roster stays above other windows. |
| `ui.roster_threads` | `15` | With layout = "split": how many followed threads and private talks stand in the roster as items of their own ("Threads", "Talks"), the freshest; 0 — none, the lanes only. |
| `ui.faces` | `true` | With layout = "split": faces, as in QIP — over a lane's posts the author of the one under the cursor, with what to do (follow, lists, a private message, the profile); by the input line, whom I write to. |
| `ui.dock_commands` | `true` | With layout = "split": the input line at the bottom takes the command line's commands too ("#a3f text", "! #a3f", "S #a3f", "?" — Enter runs them), and the command line itself is hidden (Ctrl+L brings it). false — the input line only writes. |
| `ui.split_tabs` | `"keep"` | With layout = "split": closing the messages window "keep"s its tabs for when it opens again, or "close"s them all — it opens with only what you open from the roster. |
| `ui.icons` | `"theme"` | The pictures on the buttons and by the lanes: "theme" — as the theme decides (system and debug — the desktop's icons, terminal and bnw — none, the rest — its own set from the theme's folder); "desktop" — the desktop's icons (Breeze…); "own" — the theme's set, the messengers' pictures (the input line, the roster, a person's flower) only in the split layout; "additional" — the theme's set, and the messengers' pictures wherever their buttons are (the post window, a profile); "words" — no pictures, words and the glyphs ≡ ↔ ❯. |
| `ui.columns` | `[]` | Which lanes stand as columns, left to right, until you change them in the window (a click on a lane on the left adds a column, ✕ on a column takes it away, ‹ › move them; that is remembered). Names — as in lanes.enabled; "list:Friends" — a list by its title. [] — Home, Replies to me and Activity. |
| `ui.column_width` | `460` | The width of one column in pixels (at least 280). They don't fit the window — sideways scrolling. |
| `ui.actions` | `"both"` | The buttons under a post: "both" — an icon and a label, "icons" — icons only (the labels pop up on hover), "text" — labels only. |
| `ui.expand_cw` | `true` | Text and pictures under a content warning (CW) open at once. false — folded, opened with the "show" button. |
| `ui.bookmark_button` | `true` | The "Bookmark" button in the row under a post (otherwise — only in the ⋯ menu and with the m key). |
| `ui.arts_mode` | `true` | Arts mode (after @arts, the founder of Point.im): everything as the author posted it, no nannying. Turns on at once: CWs open (expand_cw), "sensitive" pictures without a cover (feed.sensitive_media = "show"), server filters neither hide nor fold posts, there is no "Report" item. Your own mutes and blocks work as usual, and what the server itself cuts off (domain blocks on it) never reaches the client at all — that can't be got round. Recommended. false — everything as everyone has it, each setting on its own. |
| `ui.sidebar_groups` | `true` | Lanes on the left in groups with headings: "Timelines", "Personal", "Lists". false — one list. |
| `ui.sidebar_width` | `272` | The width of the left column (the account, the lanes) in pixels, at least 180. Its edge can be dragged with the mouse too — that's remembered until the next start, and this number stays. |
| `ui.sidebar_footer` | `true` | Small at the bottom left: the version, the build and who wrote it. false — take it away. |
| `ui.app_icon` | `"possum"` | The icon of the window, the tray and notifications: "possum" — an opossum holding its own tail (also in the desktop menu and in About); "bubble" — the drawn thread bubble. |
| `ui.themed_icon` | `true` | The bubble ("bubble" above) — in the colours of the chosen theme. false — always the plain one. (The desktop menu has the opossum: --install-desktop puts it there.) |
| `ui.icon_count` | `["replies", "mentions", "subs", "requests"]` | The unread number on the icon — in the tray and on the task bar button (KDE: needs the menu entry from --install-desktop and the python3-pyside6.qtdbus package). It counts the lanes from here, except those in icon_count_except; [] — no number. Lane names — the same as on the left (a lane's word is in its tooltip too):<br>federated — Federated home — Home local — Local<br>bots — Bots my_posts — My posts direct — Direct<br>mentions — Mentions replies — Replies to me subs — Subscriptions<br>bookmarks — Bookmarks my_likes — My likes activity — Activity<br>requests — Follow requests<br>"lists" — all lists at once; one list — by its title (or id): "list:Friends".<br>"all" — every lane at once (only in the first of the pair; take the rest away in except). federated and local are never counted (they are browsed, there's no unread in them). For example: ["replies", "mentions", "lists"] or ["all"] + except = ["home", "bots"]. |
| `ui.icon_count` | `["replies", "mentions", "subs", "requests"]` | Which lanes not to count on the icon, even if they are in icon_count (say, with |
| `ui.icon_count_except` | `[]` |  |
| `ui.language` | `"auto"` | The interface language: "auto" (from LANG), "ru", "en". |
| `ui.frontend` | `"qt"` | The interface: "qt" — a window; "tui" — in a terminal (needs Textual: python3-textual or pip install textual), the same as `fedtail --ui tui`; "web" — in a browser (`--ui web`); "gtk" — a GTK 4 window for GNOME and other GTK desktops (python3-gi gir1.2-gtk-4.0; `--ui gtk`). |
| `ui.adwaita` | `"auto"` | The GTK interface: libadwaita — "auto" (when installed), "on" (don't start without it), "off" (plain GTK: looks more at home in XFCE, MATE, Cinnamon). |
| `ui.accessibility` | `"auto"` | The GTK interface: talking to screen readers (Orca) over the accessibility bus. "auto" — only while a screen reader is on: KDE runs the bus always, and with no reader GTK went to it for every widget — a menu took two seconds to open. "on" — always, "off" — never. |
| `ui.gtk_headerbar` | `"auto"` | The GTK interface: its own title bar with the buttons (as in GNOME) — "on"; the desktop's frame — "off"; "auto" — its own with libadwaita and in GNOME and its kin, the desktop's frame in KDE, XFCE, MATE, Cinnamon. |
| `ui.desktop_entry` | `true` | The menu entry and the icon (~/.local/share/applications, icons): at every start of a window (qt, gtk) check they're there and point to this fedtail (a moved checkout, a new one-file build) and mend them; old entries of the former name (fedtail.desktop) go. With the deb package its menu entry is the one: none of ours beside it. |

### Window, keys, start

| Key | Default | What it does |
|---|---|---|
| `ui.close_to_tray` | `true` | The cross hides the window to the tray instead of closing the program. |
| `ui.esc` | `"curtain"` | Esc closes what's on top (a picture, the search), and the last Esc:<br>"curtain" — draws a curtain over all lanes: the window stays, the counts on the left, nothing on the right; nothing is marked read — open it in the morning and the new has piled up;<br>"tray" — takes the window to the tray at once (without a tray — minimizes it);<br>"off" — does nothing. |
| `ui.start_lane` | `"none"` | What is open at start:<br>"none" — nothing: every lane behind the curtain, the counts on the left (Enter opens the last one);<br>"last" — the lane open last time;<br>a lane's name — always that one: "home", "replies", "subs"… (as in [lanes]). |
| `ui.compose` | `"inline"` | Where to write a post: "inline" — a panel inside the main window (the keyboard layout isn't reset: KDE keeps it per window, and a new window may open with another one); "window" — a window of its own, as before. |
| `ui.compose_size` | `0` | The size of the post panel — in percent of the main window (and following it when the window changes size): 50, 80, 100… 0 — as before, at most 820 × 540. The ⤡ button in the panel switches between normal and big (90 %) and remembers the choice. |
| `ui.command_line` | `true` | A command line as on Point at the bottom of the window (Ctrl+L shows it even if false). |
| `ui.whats_this` | `false` | "What's this?" from the start: point the mouse at a button — a longer hint on what it does, which config key changes it and where the help says more. For now it's turned on and off in the ≡ menu → "What's this?". No shortcut on purpose (F1 is next to Esc). |

### Pictures and links

| Key | Default | What it does |
|---|---|---|
| `ui.image_height` | `360` | The height of a single picture in a lane, pixels (several pictures — smaller tiles). |
| `ui.image_viewer` | `"internal"` | A click on a picture: "internal" — its own viewer (← → to flip, Esc to close), "browser" — open in the browser. |
| `ui.video_player` | `"internal"` | Video and audio: "internal" — right in the window (a video — over the window: Space — pause, ← → — seek, M — sound, O — to the browser, Esc — close; audio — a player in the card), "browser" — open in the browser. Needs QtMultimedia (Debian: python3-pyside6.qtmultimedia python3-pyside6.qtmultimediawidgets); without it — the browser. |
| `ui.video_decode` | `"software"` | What decodes video: "software" — the processor (videos in the fediverse are small, it copes easily), "hardware" — the graphics card, as Qt decides. On some cards (NVIDIA: "CUDA_ERROR_INVALID_VALUE", "more than 32 decode surfaces" in the log) hardware decoding won't start, and the video stutters, stalls or stays black. The QT_FFMPEG_DECODING_HW_DEVICE_TYPES variable set by hand beats this flag. |
| `ui.gifv` | `"play"` | Mastodon's gifs (short silent videos): "play" — loop right in the card while it's on screen (at most three at once), "click" — a still frame, a click plays it over the window. |
| `ui.image_upscale` | `2` | How many times the viewer may enlarge a small picture so that it fills the window (1 — never enlarge). |
| `ui.save_dir` | `""` | Where to save pictures (S in the viewer, a right click on a picture in a lane). "" — the desktop's Downloads folder (~/Downloads, or as set in KDE). |
| `ui.image_cache_mb` | `128` | How much memory, MB, to keep for pictures already fetched and decoded (the oldest are thrown out first; the cache stays on disk, rereading from there is instant). |
| `ui.image_decode` | `"box"` | Pictures in a lane are decoded in memory to the size of their frame (minding the screen's density): "box" — several times less memory and work for the processor; "full" — as before, up to 1200 pixels on the longer side (sharper if you stretch the window later). |
| `ui.image_disk_mb` | `1000` | How much disk space, MB, to keep for fetched pictures: over that, out go the ones not opened the longest (at start and along the way). 0 — don't clean. |
| `ui.video_disk_mb` | `10000` | The same for videos, gifs and sound — they have their own folder and their own limit, MB (a clip or two is a gigabyte already). A video opened once stays on disk and plays at once the next time. 0 — don't keep videos on disk. |
| `ui.unload_hidden_minutes` | `10` | A lane not opened for this many minutes lets its cards go from memory: a client open for days otherwise holds hundreds of cards with all their pictures (over a gigabyte). Open it again — it's drawn anew, from the first unread (that's quick). The lane open right now is never unloaded. 0 — keep everything. |
| `ui.links_in_app` | `true` | Open @mentions, #hashtags and links to fediverse posts and profiles inside fedtail (a profile, a tag's lane, a thread), not in the browser. Not found — the browser. |

### Several accounts

| Key | Default | What it does |
|---|---|---|
| `ui.switch_closes` | `true` | Accounts are profiles (--profile name): each with its own config, theme and window. A right click on the avatar (or ≡ → "Account and server") — the list, pick one and it opens. true — this window closes then; false — both stay. |
| `ui.merge` | `[]` | All accounts in one window: lanes of the same name merge (both accounts' "Home" is one), posts of other accounts are marked "→ @nick" — a reply, a like and a boost go from the account that received the post. The other accounts' lists are lanes of their own. ["all"] — every account, ["work"] — only these profiles, [] — as chosen in the accounts menu ("All accounts in one window"). |
| `ui.account_colors` | `true` | In the shared window the "→ @nick" mark on posts of other accounts is coloured: each account has its own colour, always the same. false — no colour. |
| `ui.act_as` | `true` | In the shared window a post's ⋯ menu has "From another account": a like, a boost or a reply not as the account that received the post. fedtail finds the post by its address through that account's server and does it from there. false — no such item. |
| `ui.post_keys` | `true` | Keys in a lane and a thread, as in web clients: j / k — the next / previous post, r — reply, f — like, b — boost, m — bookmark, o or Enter — open the thread. false — these letters do nothing. |
| `ui.announcements` | `"banner"` | Server announcements (from its admins: updates, rules, maintenance): "banner" — a strip over the lane until you press "Got it" (the server remembers that for other clients too); "off" — don't show. |
| `ui.media_grid` | `"natural"` | Several pictures in a post: "natural" — each whole, its own shape; "square" — an even grid of squares cut around the focus point the author set (if they did; otherwise — around the centre). A single picture is never cut. |
| `ui.alt_text` | `"tooltip"` | A picture's description (alt text, the author writes it for those who can't see): "tooltip" — on mouse hover; "caption" — also as a caption under the pictures. |

## 2. Reading the feed

### `[feed]`

| Key | Default | What it does |
|---|---|---|
| `feed.order` | `"oldest_first"` | The order: "oldest_first" — oldest on top, you read downwards (as in RSS/Point); "newest_first" — newest on top (as everyone does). |
| `feed.start_at` | `"first_unread"` | Where to stand when a lane opens: "first_unread" or "newest". |
| `feed.on_new` | `"keep_position"` | What to do when new posts come: "keep_position" — stay where you are; "jump_to_newest" — jump to the new (as everyone does). |
| `feed.show_reply_context` | `true` | The "↪ in reply to…" strip over replies. |
| `feed.page_size` | `40` | How many posts a request to the server. |
| `feed.catch_up_limit` | `400` | How many new posts to catch up a poll (the rest — with the next one). |
| `feed.render_limit` | `300` | How many latest posts to keep on screen in a lane (older ones — with the "older" button). |
| `feed.repeat_boosts` | `false` | A boost of a post that was in this lane already (itself or with someone's boost) or was read, — a repeat: false — don't show it, the post stays where it first came; true — every boost brings the post up again (as everyone does). A post that came as a post is always seen. |
| `feed.build_at_once` | `40` | How many cards to build at once when a lane opens — around where you read; the rest are built as you scroll near an edge (the screen doesn't wait for fifty cards). What you read doesn't move meanwhile. 0 — build the whole lane at once (as before: on hundreds of posts that takes seconds). |
| `feed.first_run_mark_read` | `true` | At the very first run, count everything fetched as read (don't start with a pile). |
| `feed.honest_counters` | `false` | Honest counters: opening a thread, ask the author's server for the real numbers of likes, boosts and replies of public posts (your server knows only those that reached it). That's a request to another server — without your token, but with your IP. |
| `feed.counters_via_accounts` | `true` | If the author's server won't give the numbers without a login: ask them as another account of yours (a fedtail profile) — on the author's server, if you have one there, or on a server that already has the post. Each account's token goes only to its own server. Works together with honest_counters. |
| `feed.remember_choices` | `false` | The choices over a lane — "All / Posts only / New" and "Feed / Conversations" — remembered between runs. false — every run starts afresh: "All" and "Feed" (or what [lanes] posts_only says), the choice holds until the program closes. |
| `feed.complete_threads` | `true` | Whole threads. Your server knows only the replies that reached it (from people followed on your server, or addressed to you), — that's why other people's threads have holes. Open a thread — fedtail asks the author's server for the list of replies and asks your server to fetch what's missing; the thread grows by itself a couple of seconds later. These are requests to other servers without your token (they see only the IP). false — make do with your own server. Mastodon 4.5+ gathers replies itself too — then the thread grows when the server says it's done. |
| `feed.link_cards` | `"full"` | A link card under a post — the title, description and picture of the page it links to (the server collects them):<br>"full" — with the picture; "text" — without the picture, in a line or two; "off" — not shown. A post with pictures of its own has no card. |
| `feed.custom_emoji` | `true` | Servers' own emoji (:blobcat: and the rest) — as pictures in posts and names. false — leave them as text :blobcat: (and don't fetch their pictures). |
| `feed.emoji` | `true` | Emoji in the feed at all. false — turn off every last one: servers' pictures (:blobcat:), ordinary Unicode ones (🔥 😂 🇬🇪), and the reactions line under a post. A name made only of emoji shows the login. fedtail's own glyphs (⚠ ↔ ❯) aren't touched. |
| `feed.quotes` | `"card"` | Quotes (a post inside a post: Mastodon 4.5+, Akkoma, Misskey and others):<br>"card" — the quoted post framed inside; "link" — one line with a link; "off" — as<br>the server sent it (usually a line "RE: link"). |
| `feed.remote_profiles` | `true` | The profile of a person from another server your server knows almost nothing about: fedtail reads their latest public posts straight from their server (the ActivityPub outbox) and asks your server to fetch them — how many — remote_posts. These are requests to other servers without your token (they see only the IP); servers that require signed requests simply give nothing. |
| `feed.prefetch` | `"previews"` | Fetch the pictures of new posts ahead, as soon as the posts have come — open a lane and they're on disk already. "previews" — previews (of videos too), avatars and link pictures; "all" — also the original pictures, the videos themselves and gifs (videos — one at a time, by a worker of their own, at most 300 MB each; much more traffic and disk space); "off" — only when the post is on screen. |
| `feed.per_person_follow` | `true` | On the profile of someone you follow — two buttons: "♻ without their boosts" (their boosts don't come to Home) and "🌐 languages" (only their posts in these languages). The server keeps it, so it works in every client. false — no buttons. |
| `feed.show_moved` | `true` | An account moved to another server: its profile has a "moved to @new" banner with the buttons "open" and (if you follow it) "follow there". false — no banner. |
| `feed.old_days` | `30` | A post older than this many days — marked "old, N days" next to the date: such posts come from someone's outbox or an old thread, and they aren't taken for news. 0 — no mark. |
| `feed.collapse_tags` | `true` | A paragraph of nothing but hashtags (more than three) — padding for search: in a lane it folds into the first three and "… +N" in small type, in an open thread it's whole, but small too. Hashtags inside the text aren't touched. false — as the server sent it. |
| `feed.server_info` | `true` | What the person's server runs — in the profile, "🖥 GoToSocial 0.17" (from its nodeinfo, without your token; remembered for a week). false — don't ask. |
| `feed.long_form` | `true` | "📄 Read it whole" in the ⋯ menu of a post from another server: the post as the author's server keeps it. An article (Article, Page) — whole, not a title with a link; an event (Event) — with its time and place. Without your token. false — no such item. |
| `feed.text_markup` | `true` | ~~text~~ — struck out, as the author meant: their client or server (Mastodon) knows no Markdown, and the tildes came as they were. Not in links and not in code. false — tildes as they came. |
| `feed.follow_date_note` | `true` | Servers don't keep the day you followed someone. When you follow through fedtail, I write the date as the last line of your private note on the person — "[fedtail followed 2026-10-18]": it's seen from any device and in other clients (in fedtail this line is hidden and kept when the note is edited). false — I remember it here only. |
| `feed.remote_posts` | `20` | How many latest posts to fetch this way into a profile (at most 40). |
| `feed.remote_people` | `true` | The follows and followers of a person from another server: your server knows only part of them. At the bottom of such a list there'll be a "more from their server" button — fedtail reads the lists straight from there (ActivityPub, without your token) and finds these people through your server. false — no button. |
| `feed.sensitive_media` | `"hide"` | Pictures and videos the author marked "sensitive" (without a content warning, CW):<br>"hide" — under a cover, a click shows them; "show" — seen at once. Under a CW they are hidden together with the text anyway. |
| `feed.profile_pinned` | `true` | Pinned posts — at the top of a profile, marked 📌. false — the profile simply in time order. |
| `feed.translate` | `true` | "Translate" in the ⋯ menu of a post in another language — if your server can translate (Mastodon with DeepL or LibreTranslate). The translation — right in the card, with an "original" button. |
| `feed.profile_featured` | `true` | In a profile — the person's featured tags ("Often writes about: #tags") and whom they recommend (Mastodon 4.4+). false — don't ask. |

## 3. Read marks

### `[read]`

| Key | Default | What it does |
|---|---|---|
| `read.mark_read` | `"on_scroll"` | When a post counts as read:<br>"on_scroll" — when you've scrolled past the whole of it;<br>"on_open" — the whole lane, as soon as you open it;<br>"manual" — by hand only: "All read", and in a post's ⋯ menu "Mark read" and "Read up to here" (this one and everything older). So a lane always waits for you exactly where you stopped, even reading one post at a time. The "Mark read" and "Read up to here" items are in a post's menu in any mode. |
| `read.read_button` | `false` | A ✓ "Read" button right under each unread post (handy with "manual"). |
| `read.sync_markers` | `true` | The reading place shared with other clients (Mastodon markers): read Home or mentions to the end on the phone — here it's read too, and the other way round. Works with Mastodon, GoToSocial, Akkoma. false — read marks live here only. |

## 4. Which lanes

### `[lanes]`

| Key | Default | What it does |
|---|---|---|
| `lanes.global` | `—` | Which lanes to show (and in what order within a group on the left). The groups: "Timelines" — from the widest down to your own:<br>federated — "Federated": everything your server knows from all servers<br>home — "Home": the people you follow, without bots (opens by default)<br>local — "Local": your whole server<br>bots — "Bots": the people you follow, bots only "Personal":<br>my_posts — "My posts"<br>direct — "Direct": private messages to you (visible to the mentioned only)<br>mentions — "Mentions": where you were tagged in someone else's conversation<br>replies — "Replies to me": replies to my posts and comments<br>subs — "Subscriptions": what's new in threads you're subscribed to (as on Point)<br>bookmarks — "Bookmarks": posts put "in bookmarks" (a post's ⋯ menu)<br>my_likes — "My likes": the posts you liked (off by default)<br>activity — "Activity": who liked, boosted, followed you<br>requests — "Follow requests" At the bottom — the server's "Lists" (the [lists] section). A lane's word is in its tooltip on the left too. The old names (before 0.15) are understood too: people = home, comments = replies, |
| `lanes.enabled` | `["federated", "home", "local", "bots", "my_posts", "direct", "mentions", "replies", "subs", "bookmarks", "activity", "requests"]` | federated and local are fetched only while open, and without counts: they are browsed, not read to the end. |
| `lanes.extra_bots` | `[]` | Accounts to count as bots even if they have no "bot" tick. Your server — just "nick", another one — "nick@server". |
| `lanes.posts_only` | `[]` | In which lanes "posts only" (without comments/replies) is on at start. The tick over a lane switches it too — the choice is remembered. |
| `lanes.mentions_all` | `false` | "Mentions" are mentions that are NOT replies to you: replies to your posts and comments (even with @you inside) live in "Replies to me". true — "Mentions" shows everything that mentions you, replies too (they'll be in both lanes). |
| `lanes.direct_apart` | `true` | Private messages (visible to the mentioned only), when the direct lane is on, live only in it — they don't double up in "Replies to me" and "Mentions". false — there too. |
| `lanes.tag_groups` | `[]` | Lanes of several tags — in the sidebar, in the "Tags" group (fetched while open, like "Federated"). Each is a table [[lanes.tag_groups]]: name — what to call it, any — any of the tags, all — all at once, none — without. The same can be typed in the search ("#грузия #georgia -#politics") and kept with the "＋ to lanes" button — then there's no need to write it here. An example (then take away the tag_groups = [] line below — TOML won't allow both):<br>[[lanes.tag_groups]]<br>name = "Georgia"<br>any = ["грузия", "georgia", "tbilisi"]<br>none = ["politics"] |

## 5. Posts

### `[post]`

| Key | Default | What it does |
|---|---|---|
| `post.default_visibility` | `"private"` | A new post's visibility: "public", "unlisted", "private" (followers), "direct"; "server" — as set in the settings on the server (in its web interface). |
| `post.send_timeout` | `90` | How many seconds to wait for the server's answer when sending a post. A slow server may take longer than the usual 30 seconds to make a post; no answer in time — fedtail looks itself whether the post appeared before saying "not sent" (so that a retry doesn't make a double). |
| `post.reply_never_wider` | `true` | A reply is never more public than the original post. |
| `post.drafts_autosave` | `true` | Drafts are saved as you type and survive closing the window. |
| `post.cw_field` | `false` | The "content warning / title under the cut" (CW) field is open at once. false — it hides behind the "⚠ Warning" button. |
| `post.camelcase_hint` | `true` | A hint under the text if a hashtag is written in one case (#georgianews): screen readers read #GeorgiaNews word by word. false — no hint. |
| `post.plain_posts` | `true` | The command line at the bottom (Ctrl+L), as on Point: #a3f — open, #a3f text — reply, S/U #a3f — subscribe to a thread, S/U @nick — follow a person, ! — boost, ~ — bookmark, D — delete your own, @nick — profile, ? — help. Plain text without a command — a new post (false — commands only, no accidental posts). |
| `post.language` | `""` | The language of new posts (an ISO 639 code: "ru", "en", "ka"…), servers and clients filter and translate by it. "" — don't say, the server takes the language from the account's settings. The post window can change it for one post. |
| `post.languages` | `["ru", "en", "ka", "uk"]` | The languages in the post window's list (on top — "as in the settings"). Any other — write it here as an ISO 639 code ("eo", "es", "cv", "jbo", "tok"…) or pick "Another language…" in the post window: one added there stays on the list from then on. |
| `post.complete_mentions` | `true` | Typing @ar — suggest people: first those seen most in the lanes, then those the server finds. false — no suggestions. |
| `post.complete_tags` | `true` | Typing #ge — suggest tags: first those you follow, then the most frequent in the lanes. |
| `post.report_forward` | `true` | A report to the moderators about a person from another server: the "forward to their server too" tick is on at once (they won't learn who reported). false — off by default. |
| `post.quote_policy` | `""` | Who may quote your new posts (Mastodon 4.5+): "public" — everyone, "followers" — followers, "nobody" — nobody; "" — as in the account's settings on the server. |
| `post.quote_action` | `true` | "Quote" in the ⋯ menu of a post its author allowed to quote (Mastodon 4.5+). |
| `post.invite` | `true` | "Call into the thread…" in a post's ⋯ menu: a reply to it with only "@" in it so far and the people list open — the one named gets a notification and sees the thread at home. The thread's other participants aren't mentioned (they aren't bothered). The same on the command line: #a3f @whom text. |
| `post.who_can_reply` | `""` | Who may reply to your new posts — GoToSocial only (interaction policy):<br>"" — as in the account's settings; "everyone" — everyone; "followers" — followers and<br>the mentioned; "following" — those you follow, and the mentioned; "mentioned" — only<br>the mentioned; "me" — only you. This isn't sent to other servers. |
| `post.who_can_boost` | `""` | Who may boost your new posts (GoToSocial) — the choices are the same as for who_can_reply. |
| `post.who_can_like` | `""` | Who may like your new posts (GoToSocial) — the choices are the same as for who_can_reply. |
| `post.schedule` | `true` | The "⏰ Later" button in the post window: send at a set time (the post waits on the server, even if fedtail is closed). The list of waiting ones — the ≡ menu → "Scheduled". false — no button. |
| `post.alt_reminder` | `true` | A picture without a description — before sending, ask: "Describe" or "Send as is". false — don't ask. |
| `post.redraft` | `true` | "Delete and redraft" in the ⋯ menu of your own post: the post is deleted, and its text (as you typed it), CW, visibility, language and what it answered open as a new draft. Pictures don't come back — the server deletes them with the post. false — no item. |
| `post.resize_images` | `true` | A picture bigger than the server takes (it says itself how big) — before the upload shrink a copy instead of being refused: under its pixel limit, as JPEG (with transparency — PNG) — under its byte limit. Your file isn't touched. false — send as is. |
| `post.chain` | `true` | A thread as a chain: a line of nothing but "---" splits the text into posts — they go at once, each a reply to the one before (pictures and the poll go with the first). The character counter counts each part on its own. false — "---" stays plain text (a horizontal rule in Markdown). |
| `post.preview` | `true` | The "👁 Preview" button in the post panel: how it will look — the Markdown already rendered (if the server understands it), the CW, visibility, each part of a chain; and from there "Send". false — no button. |
| `post.complete_emoji` | `true` | Typing :co — suggest the server's emoji (:cookie: and the like), Tab or Enter puts it in. false — no suggestions. |
| `post.focus_point` | `true` | A double click on a picture in a post — its description and the focus point: click the picture where the main thing is, and the preview (where it's cut) shows exactly that. false — the description only. |
| `post.quote_prefix` | `"> "` | "Reply with quote" in a post's ⋯ menu and "Quote in reply" on selected text: the reply gets a quote, every line starting with this (a Markdown quote). With the reply already open, the quote goes where the cursor is: select a sentence, quote, answer, select the next one… "" — no such items. |

## 6. Notifications

### `[notify]`

| Key | Default | What it does |
|---|---|---|
| `notify.enabled` | `true` | Desktop pop-up notifications. |
| `notify.lanes` | `["direct", "replies", "mentions", "subs", "activity", "requests"]` | What to notify about. home is quiet by default (everything comes there), lists too. Lane names — the same as on the left (a lane's word is in its tooltip too):<br>federated — Federated home — Home local — Local<br>bots — Bots my_posts — My posts direct — Direct<br>mentions — Mentions replies — Replies to me subs — Subscriptions<br>bookmarks — Bookmarks my_likes — My likes activity — Activity<br>requests — Follow requests<br>"lists" — all lists at once; one list — by its title (or id): "list:Friends".<br>"all" — every lane at once (only in the first of the pair; take the rest away in except). For example: ["replies", "mentions", "list:Friends"] or ["all"] + except = ["home", "bots"]. |
| `notify.except` | `[]` | What never to notify about, even if it's in lanes (say, with lanes = ["all"]): the same names — "bots", "federated", "lists", "list:News"… |
| `notify.privacy` | `"full"` | What to show in a notification:<br>"full" — who wrote what;<br>"sender" — only who, without the text (fine to read with others around);<br>"count" — only how many, without names and text. |
| `notify.when_focused` | `false` | Notify about the lane open in front of your eyes too (by default it keeps quiet about it; about the other lanes notifications come even when the fedtail window is active). |
| `notify.backend` | `"auto"` | How to show them: "auto" (KDE notifications if there's notify-send, otherwise through the tray), "desktop" — notify-send only, "tray" — through the tray only. |
| `notify.filtered` | `"remind"` | Filtered notifications (Mastodon 4.3+: the server holds back mentions from strangers, new accounts and the like until you allow them): ≡ → "For the tender and sensitive" → "Filtered notifications…" — who waits, "Let in" / "Dismiss", and what exactly to filter. "remind" — so, and at start a line at the bottom if someone waits; "menu" — in the menu only; "off" — neither. |

### `[sound]`

| Key | Default | What it does |
|---|---|---|
| `sound.enabled` | `"auto"` | Sounds. The sound scheme is a part of the theme, like the pictures: the messenger themes (qip-*, mra-*, psi) bring their own set, system plays the desktop's sounds (the KDE/GNOME sound theme), terminal and bnw the terminal's beep, the rest what they inherit. One program plays them all: pw-play, paplay or aplay (Linux), afplay (macOS), Windows itself; none of them — silence. "auto" — sounds in development versions (X.Y.Z.devN — git between releases), none in releases and the builds made from them; "on" — always; "off" — never. |
| `sound.lanes` | `["direct", "replies", "mentions", "subs", "requests"]` | Chime about news in these lanes (names as in notify.lanes). Each lane has its sound:<br>direct → "private", replies → "reply", mentions → "mention", subs → "in a thread",<br>requests → "request", activity → "activity", every other lane → "message". |
| `sound.except` | `[]` | Never chime about these, even if lanes names them. |
| `sound.online` | `true` | The "online" sound — when fedtail has connected to the server. |
| `sound.sent` | `true` | The "sent" sound — when a post has gone out. |
| `sound.when_focused` | `true` | Chime while the fedtail window is active too (notifications keep quiet then — sounds don't). |
| `sound.scheme` | `"theme"` | Whose scheme: "theme" — the theme's; a theme's name ("qip-retro", "mra", "psi") — its sounds whatever the look; "none" — no sounds (the same as enabled = "off"). |
| `sound.volume` | `80` | Volume, 0 to 100 — where the player can (pw-play, paplay, afplay, the browser). |
| `sound.player` | `"auto"` | What plays them: "auto" — the first found of those above; or a command of yours, {file} being the file's path: "mpv --no-video {file}". |
| `sound.min_gap_seconds` | `3` | No more than one sound in this many seconds (a batch of news chimes once — the weightiest). |

## 7. Activity

### `[activity]`

| Key | Default | What it does |
|---|---|---|
| `activity.types` | `["favourite", "reblog", "follow"]` | What to show in "Activity" (and in notifications about it):<br>"favourite" — liked, "reblog" — boosted, "follow" — followed,<br>"poll" — a poll ended, "update" — a post you boosted was edited,<br>"status" — a new post of a person whose posts you turned the bell on for. ["all"] — everything listed (and whatever new versions add). |
| `activity.approvals` | `true` | Replies, likes and boosts waiting for your approval (GoToSocial: who may reply, like and boost is set in the post settings). They come here too, with the buttons "Approve" and "Reject". false — don't show (approve on the server's site then). |
| `activity.server_notices` | `true` | The server's own notices (Mastodon 4.3+): your server (or another) blocked another one — and your follows and followers from there were cut, how many and why; a warning from the moderators. They come here too. false — don't show. |
| `activity.server_groups` | `true` | The server's own groups of notifications (Mastodon 4.3+): 300 likes of one post come as one group with its count — one request instead of eight pages, one row "and 297 more"; × dismisses the whole group on the server. Where the server can't (GoToSocial, older Mastodon), fedtail groups them itself. false — always itself. |

## 8. Lists

### `[lists]`

| Key | Default | What it does |
|---|---|---|
| `lists.enabled` | `true` | The server's lists (Mastodon, GoToSocial) — as lanes of their own under the main ones. Make a list and put a person in it — with a right click on a post. |
| `lists.hide_members` | `"all"` | You put a person or a bot in a list — their posts, their boosts and others' boosts of their posts are read in the list's lane and leave the general lanes, so they don't clutter them:<br>"all" — so with any list;<br>"exclusive" — only with lists ticked "exclusive" (the server itself takes such people out of Home);<br>"off" — don't take them out of anywhere. |
| `lists.hide_in` | `["home", "bots", "federated", "local"]` | Which lanes to take them out of (names — as in [lanes]). |
| `lists.refresh_minutes` | `10` | How often to reread the lists themselves and who is in them, minutes. |

## 9. Thread subscriptions

### `[subs]`

| Key | Default | What it does |
|---|---|---|
| `subs.auto` | `["posts", "comments"]` | Thread subscriptions, as on Point. The server tells you only of replies that mention you; if two people answer each other under your post, you won't know. fedtail itself rereads the threads you're subscribed to and puts what's new into "Subscriptions". Subscribe/unsubscribe — in a post's ⋯ menu or with the button in the thread's header. What to subscribe to by itself: "posts" — your own posts, "comments" — threads you comment in. |
| `subs.interval_minutes` | `5` | How often to reread a live thread, minutes; a quiet one is reread less often (an hour quiet — 3 times, a day — 12, three days — 36), and threads take at most a quarter of what the server still allows. |
| `subs.active_days` | `14` | A thread where nothing happened for this many days is not checked any more. |
| `subs.max_threads` | `30` | How many threads to check in one round (the rest — in the next). |
| `subs.replies_to_me` | `false` | Replies to you come to "Replies to me" anyway. true — show them in "Subscriptions" too. |
| `subs.leave_mutes` | `true` | Unsubscribing from a thread mutes its mentions too: replies there tag everyone in it by themselves, and the server (GoToSocial) can't mute a thread. false — leave "Subscriptions" only. |

## 10. Polling the server

### `[poll]`

| Key | Default | What it does |
|---|---|---|
| `poll.interval_seconds` | `90` | How often to ask the server for what's new, seconds (at least 30). |
| `poll.stream_gap_seconds` | `10` | The live stream wakes a poll as soon as something comes — but not more often than every this many seconds: on a busy server events come many times a minute, and every poll is a dozen requests and a bit of processor. Whatever comes in these seconds comes with one poll. "Refresh" isn't made to wait. 0 — at once on every event. |
| `poll.stream` | `"auto"` | The server's live stream: something new came — poll at once, not after interval_seconds. "auto" — if the server offers it (GoToSocial, Mastodon, Akkoma); "off" — polling only. The stream only wakes the poll, so if it drops (a laptop asleep, a proxy) nothing is lost. |

## 11. The server

### `[account]`

| Key | Default | What it does |
|---|---|---|
| `account.markdown` | `"auto"` | Whether the server understands Markdown: "auto" (ask the server), "on", "off". GoToSocial / Akkoma do, vanilla Mastodon doesn't. |

### `[sync]`

| Key | Default | What it does |
|---|---|---|
| `sync.enabled` | `false` | Read marks and thread subscriptions the same on all your devices (a desktop, a laptop, a phone). Off by default. What travels is sealed with a key only your devices have: whatever stores it sees no posts and no read marks. Setting up: docs/en/sync.md, in short: `fedtail sync login` (a sync server) or a folder, then `fedtail sync key` here and `fedtail sync join` on the other devices. |
| `sync.backend` | `"server"` | Where the devices meet: "server" — a fedtail-sync server; "folder" — a folder every device sees (a NAS share, WebDAV mounted, Syncthing). |
| `sync.url` | `""` | The sync server's address. Empty — the one your fediverse server names (https://<server>/.well-known/fedtail-sync), if its admin set one up. |
| `sync.folder` | `""` | The folder for backend = "folder" (~ is your home folder). |
| `sync.what` | `["read", "threads"]` | What travels: "read" — read marks you made (not the first run's "everything read"), "threads" — threads you followed, left or muted by hand. |
| `sync.interval_seconds` | `60` | How often to send and fetch, seconds (at least 15). A mark goes out a few seconds after it was made anyway. |

## 12. Database and logs

### `[storage]`

| Key | Default | What it does |
|---|---|---|
| `storage.max_mb` | `1024` | How much room the profile's database (state.db) may take, MB. Posts nothing points at any more — no lane, followed thread, activity entry or reply draft — are forgotten by themselves (every gc_hours); when needed, they are fetched from the server again. If the database is still bigger than this, lanes get shorter until it fits (never below 300 posts) and grow back once there is room. Short ids (#a3f) are never forgotten. |
| `storage.keep_per_lane` | `3000` | How many entries each lane keeps (the newest). "More" below them comes from the server. |
| `storage.keep_activity` | `3000` | How many of the latest entries "Activity" keeps (favourites, boosts, new followers). |
| `storage.gc_hours` | `6` | How often to clean the database, hours. The first time — at the first poll after start. |
| `storage.grace_hours` | `48` | A post stored recently (an open thread, somebody's profile) stays this many hours even if no lane points at it. |

### `[debug]`

| Key | Default | What it does |
|---|---|---|
| `debug.mode` | `"auto"` | Logs and diagnostics. In the debugging mode everything is detailed: the client is kept open for days, and if it crashes, freezes or bloats — there must be traces. The files are in the logs/ folder of the profile's data folder (the ≡ menu → "Debugging" → "Open the log folder"):<br>2026-10-16_15-04-12.log — the log: requests with timings, polls, actions (clicks, lanes, tabs — without the posts' texts), errors with tracebacks, stats. A new file at every start and every hour;<br>latest.log — a link to the one being written now: that's the one to send;<br>crash.log — the stacks of all threads if the process crashed (a segfault in Qt and the like);<br>stacks.log — the stacks on demand: `kill -USR1 <pid>`, the menu, or by itself when the window freezes. To pack it all into an archive for a bug report: python3 -m fedtail --bug-report (the last two days, without the token and the database). The debugging mode: "auto" — on in development versions (from git, a number with .dev), off in releases and the one-file builds made from them; "on" / "off" — always. On: the start of fedtail.log holds all --bug-report would add (versions, the system, the options changed, config.toml itself), so the log alone is enough to send. Off: warnings and errors only, a few MB in the profile's data folder, logs/, no stats and no watchdog; crash.log stays. The --debug launch key turns it on for one run, whatever is set here. |
| `debug.level` | `"debug"` | How detailed the log is in the debugging mode: "debug", "info", "warning". |
| `debug.log_dir` | `""` | Where to write. "" — into the profile's data folder, logs/ (~/.local/share/fedtail/<profile>/logs; the ≡ menu → "Debugging" → "Open the log folder"). A folder of your own — here, the profile is added by itself. A new version deletes the old version's logs at its first start: it has no use for them. |
| `debug.log_mb` | `10` | A log file over this many MB — start the next one without waiting for a new hour. |
| `debug.keep_mb` | `500` | How many MB of logs to keep in the folder: over that, the oldest are deleted. |
| `debug.stats_minutes` | `5` | Every how many minutes to write memory, CPU, threads, cache sizes (0 — don't write). |
| `debug.trim_memory` | `true` | Together with the stats, give back to the system the memory fedtail has already freed (on Linux with glibc it stays with the process otherwise: after a night of lanes and pictures it keeps its peak). The log says how much was given back. |
| `debug.watchdog_seconds` | `8` | The window doesn't answer for this many seconds — write the stacks of all threads (0 — don't watch). |
| `debug.stall_ms` | `250` | A window freeze shorter than the watchdog's: if the window didn't answer for longer than this many milliseconds, the log gets a line "GUI froze N ms" — and what it was busy with at that moment: the job's label (an event, drawing a lane, a picture) and the stack. "Qt itself" — Qt itself was laying out and painting. Only in the debugging mode; 0 — don't watch. |
| `debug.slow_request_seconds` | `5` | A request to the server longer than this many seconds — a warning in the log. |
| `debug.rss_warn_mb` | `1500` | Memory over this many MB — a warning in the log. |
| `debug.leak_samples` | `12` | Leak hunting. With every stats line the log gets a "trend" line: memory, objects, widgets, cards, pictures, threads, files — how many there were at start, how many now and by how much an hour it grows. If any of these grew on each of the last this many checks (12 × stats_minutes = an hour) and by more than crumbs — a "possible leak" warning with the numbers. The first half hour doesn't count: lanes are filling up. Less than 3 isn't allowed. |
| `debug.object_census` | `true` | In the debugging mode, with every stats line: which Python objects and which Qt widgets were added since the last time and since the start, the fastest growing first ("census" lines). The answer to "memory grows — of what exactly?". Walking all the objects takes a fraction of a second every stats_minutes. false — don't count. |
| `debug.tracemalloc` | `false` | Memory tracing from the start (tracemalloc): every memory allocation remembers which line of code it came from. Slower and about twice the memory — only for hunting a leak, say overnight. A snapshot — the ≡ menu → "Debugging" → "Memory snapshot": a memory-<time>.txt file in the log folder, who holds the most and what grew since the first snapshot. It can be turned on without a restart there too. |

## 13. In a terminal

fedtail without a window: `fedtail lanes`, `fedtail show replies -n 20`, `fedtail tail`, `fedtail post "text"`, `fedtail post --reply a3f "text"`, `fedtail read replies`. The same profile, the same database and the same read marks as the window has.

### `[cli]`

| Key | Default | What it does |
|---|---|---|
| `cli.enabled` | `true` | Commands in a terminal at all. false — fedtail always opens a window, and words after the keys are an error. |
| `cli.color` | `"auto"` | Colour: "auto" — only in a terminal (not in a pipe and not in a file) and if NO_COLOR isn't set; "always" / "never". |
| `cli.max_lines` | `0` | Cut a long post to this many lines (0 — show it whole). |
| `cli.tail_lanes` | `[]` | Which lanes `fedtail tail` shows without names. [] — those in notify.lanes. |

### `[tui]`

The interface in a terminal — `fedtail --ui tui` (or ui.frontend = "tui"): lanes on the left, posts on the right, the command line at the bottom as in the window. j / k — through posts, Enter — the thread, r — reply, f — like, b — boost, m — bookmark, n — a new post, x — the lane is read, Tab — lanes/posts, : — the command line, Esc — back, q — quit. Read marks — by read.mark_read.

| Key | Default | What it does |
|---|---|---|
| `tui.theme` | `""` | The Textual theme: "" — its usual one; or a name: "textual-light", "nord", "gruvbox", "dracula", "tokyo-night", "monokai", "solarized-light" and others (Ctrl+P → Change theme — to look). |
| `tui.sound` | `"bell"` | Sounds (sound.*) in the terminal: "bell" — the terminal's beep (reaches you over ssh too); "scheme" — the sounds of the ui.theme theme, played by this computer; "off" — silence. |
| `tui.lanes_width` | `26` | The width of the lanes column, in characters. |
| `tui.show_context` | `true` | Over a reply — a line "↳ @who: the start of what it answers". false — without it. |
| `tui.pictures` | `"inline"` | Pictures in the terminal, drawn with half blocks (needs Pillow, python3-pil; a true colour terminal). "inline" — a post's first picture small right in the lane, v — all of them full screen; "key" — on v only; "off" — none (o — open the post in the browser). |
| `tui.picture_rows` | `8` | How high a picture in the lane is, in lines. |

## 14. In a browser

`fedtail --ui web` (or ui.frontend = "web"): fedtail in a browser tab. At start it prints a link with a key (and opens it); the key lies in the profile's data folder, web.key — delete the file and there'll be a new one (old links stop working).

### `[web]`

| Key | Default | What it does |
|---|---|---|
| `web.host` | `"127.0.0.1"` | Which address to wait on. "127.0.0.1" — from this computer only; "0.0.0.0" — from the home network too (from the phone: the one-time link fedtail prints at start, with the computer's address instead of 127.0.0.1; good for 15 minutes). Everything goes unencrypted there, so for your own network only; from outside — through a VPN or a proxy with TLS. |
| `web.port` | `8765` | The port. |
| `web.open_browser` | `true` | Open the browser at start. |

## 15. On a phone and a tablet

The Android app (the android/ folder of the repository). Its config is this same file, edited right in the app: ⋮ → "Config". On a computer these settings do nothing.

### `[phone]`

| Key | Default | What it does |
|---|---|---|
| `phone.overview` | `"tiles"` | The overview of lanes — the home screen: "tiles" — tiles, four in a row (the count and the name); "list" — a list, a row per lane, with its first unread post. |
| `phone.pinned` | `[]` | Which lanes are tiles, and in which order: ["home", "replies", "mentions", "direct", "subs", "bots", "list:News", "activity"] (a list — "list:" and its title). The other lanes — rows under the tiles. [] — every lane with a count is a tile. |
| `phone.layout` | `"auto"` | How many columns: "auto" — by the screen's width (a phone — one, a phone on its side and a narrow tablet — the lanes and a lane, a wide tablet — the lanes, a lane and a thread side by side); "one", "two", "three" — always that many, if they fit. |
