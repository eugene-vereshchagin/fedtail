# fedtail settings

[По-русски](/docs/ru/config.md)

Every key of the config, in tables by chapter. **This file is built** from
`fedtail/data/config.example.en.toml` by `python3 tools/docs_build.py` — edit the
explanations there, not here (a test checks this file keeps up).

Which feature stands behind a key and how other clients do it —
[the feature list](/docs/en/features.md).

## How the config works

Every setting is here, with its default value and an explanation. Change what you need and restart fedtail. Or open ≡ → Settings: the window edits this very file — just the line you changed, the comments and the rest stay as they are (the old file is config.toml.bak). The program never rewrites it on its own.

A value written here stays yours even if a new version changes the default. Want the program's default always — comment the line out (# at the start) or delete it.

A new version brought new settings — `python3 -m fedtail --update-config` adds them to the right chapters (the old file is kept as config.toml.bak). To rebuild the file anew, in chapters, with your values — `python3 -m fedtail --rebuild-config`. The full reference of the current version always lies next to it: config.example.en.toml (and config.example.ru.toml — the same in Russian).

Where it lives: ~/.config/fedtail/<profile>/config.toml  (without --profile — the main profile, ★)

## Launch keys

| Key | What it does |
|---|---|
| `-p, --profile NAME` | a profile = an account with its own config and data (without it — the main one) |
| `-c, --config FILE` | another config instead of the profile's |
| `-d, --data FOLDER` | another data folder instead of the profile's |
| `--ui qt\|tui\|web` | a window, a terminal or a browser (for one run; for good — window.frontend) |
| `--layout single\|split` | the window's layout for one run (for good — window.layout); columns — single with its lanes side by side (window.open_columns) |
| `--theme NAME` | the theme for one run (for good — appearance.theme) |
| `--profiles` | which profiles there are — and exit |
| `--update-config` | add this version's new settings to this file with explanations — and exit |
| `--rebuild-config` | rebuild this file by chapters, with your values — and exit |
| `--lanes-to-config` | write the set's lanes (lanes.preset) here as [[lanes.custom]] — and exit |
| `--explain-lane NAME` | a lane of rules: what it takes of what is stored, by which condition — and exit |
| `--install-desktop` | add fedtail (this profile) to the menu with its icon — and exit |
| `--debug` | a detailed log for this run, into the terminal too |
| `--bug-report` | pack the logs and system details into an archive for a bug report — and exit |
| `--check` | what the system lacks and how to install it — and exit |
| `-V, --version` | the version — and exit |
| `COMMAND` | work in the terminal without a window: lanes, show, tail, read, post (fedtail COMMAND -h — about each one in detail) |

## Chapters

- [1. Appearance](#1-appearance) — `[appearance]`
- [2. Window and layout](#2-window-and-layout) — `[window]`
- [3. Lanes](#3-lanes) — `[lanes]`, `[lists]`
- [4. Reading](#4-reading) — `[reading]`
- [5. The post card](#5-the-post-card) — `[card]`
- [6. Threads and following them](#6-threads-and-following-them) — `[threads]`
- [7. People and profiles](#7-people-and-profiles) — `[people]`
- [8. Pictures and video](#8-pictures-and-video) — `[media]`
- [9. Writing posts](#9-writing-posts) — `[post]`
- [10. Notifications and sounds](#10-notifications-and-sounds) — `[notify]`, `[sound]`
- [11. Activity](#11-activity) — `[activity]`
- [12. Several accounts](#12-several-accounts) — `[accounts]`
- [13. Sync](#13-sync) — `[sync]`
- [14. The server](#14-the-server) — `[server]`
- [15. Database and logs](#15-database-and-logs) — `[storage]`, `[debug]`
- [16. In a terminal](#16-in-a-terminal) — `[cli]`, `[tui]`
- [17. In a browser](#17-in-a-browser) — `[web]`
- [18. On a phone and a tablet](#18-on-a-phone-and-a-tablet) — `[phone]`

## 1. Appearance

### `[appearance]`

| Key | Default | What it does |
|---|---|---|
| `appearance.language` | `"auto"` | The interface language: "auto" (from LANG), "ru", "en". |
| `appearance.theme` | `"system"` | The theme — a file in ~/.config/fedtail/themes/<name>.toml or a built-in one:<br>"system" — light/dark, as in KDE;<br>"terminal" — green on black, everything monospace;<br>"juick" — juick.com around 2013: a light grey page, white posts, blue links;<br>"juick-classic" — juick.com around 2011: an olive background, beige posts;<br>"bnw" — bnw.im: a black frame, grey posts, everything monospace, green buttons;<br>"point" — point.im today: a white page, posts split by a thin line, square avatars, the name over the date, #id \| replies under the post, buttons on the right;<br>"night" — dark, in colours of its own, on any desktop;<br>"contrast" — for weak eyes: large, black on white, sharp lines;<br>"pink" — pink: powder and berries, soft corners, little flowers;<br>"nord" — arctic dark: cold blue-grey, frosty links;<br>"solarized" — Solarized light: warm paper, blue links;<br>"qip-retro", "qip-modern", "mra", "mra-blue", "mra-green", "mra-violet", "psi" — in the spirit of QIP under Windows XP and QIP Infium, the Mail.ru Agent (orange, blue, green, violet) and Psi+: "Name (time)" over each post, mine in a colour of its own; with layout = "split" they set its look too;<br>"paper" — warm paper and a book typeface, for long threads;<br>"debug" — for hunting what's unfinished: unread, the j/k cursor, found, "seen not whole", the keyboard focus — each in a loud frame of its own. Your own themes: see ~/.config/fedtail/themes/README.txt |
| `appearance.font_size` | `0` | The font size of posts in points, 0 = the system's. |
| `appearance.fonts` | `"theme"` | Whose fonts:<br>"theme" — the theme's: the built-in ones bring their own with fedtail (PT Serif in paper, IBM Plex in terminal and nord, Source Sans in night and solarized…), nothing to install; system's are the system's;<br>"system" — the system's, whatever the theme says (as in KDE);<br>"custom" — your own, from font and mono_font below. |
| `appearance.font` | `""` | With fonts = "custom", the font of the whole window. A list works, the first one there is taken: "Inter, Noto Sans". The system's fonts do, the ones that come with fedtail (by name: "PT Sans", "IBM Plex Sans", "Open Sans"…), and .ttf / .otf files in ~/.config/fedtail/fonts/ — no need to install those. "" — the system's. |
| `appearance.mono_font` | `""` | With fonts = "custom", the fixed-width one, for #ids and /N; "" — the system's. |
| `appearance.max_width` | `760` | The width of the posts column in pixels, 0 = the full width. The ↔ button at the top left switches it for now (remembered until the next start), the config isn't touched. |
| `appearance.faces` | `true` | With layout = "split": faces, as in QIP — over a lane's posts the author of the one under the cursor, with what to do (follow, lists, a private message, the profile); by the input line, whom I write to. |
| `appearance.icons` | `"theme"` | The pictures on the buttons and by the lanes: "theme" — as the theme decides (system and debug — the desktop's icons, terminal and bnw — none, the rest — its own set from the theme's folder); "desktop" — the desktop's icons (Breeze…); "own" — the theme's set, the messengers' pictures (the input line, the roster, a person's flower) only in the split layout; "additional" — the theme's set, and the messengers' pictures wherever their buttons are (the post window, a profile); "words" — no pictures, words and the glyphs ≡ ↔ ❯. |
| `appearance.app_icon` | `"possum"` | The icon of the window, the tray and notifications: "possum" — an opossum holding its own tail (also in the desktop menu and in About); "bubble" — the drawn thread bubble. |
| `appearance.themed_icon` | `true` | The bubble ("bubble" above) — in the colours of the chosen theme. false — always the plain one. (The desktop menu has the opossum: --install-desktop puts it there.) |
| `appearance.adwaita` | `"auto"` | The GTK interface: libadwaita — "auto" (when installed), "on" (don't start without it), "off" (plain GTK: looks more at home in XFCE, MATE, Cinnamon). |
| `appearance.gtk_headerbar` | `"auto"` | The GTK interface: its own title bar with the buttons (as in GNOME) — "on"; the desktop's frame — "off"; "auto" — its own with libadwaita and in GNOME and its kin, the desktop's frame in KDE, XFCE, MATE, Cinnamon. |
| `appearance.accessibility` | `"auto"` | The GTK interface: talking to screen readers (Orca) over the accessibility bus. "auto" — only while a screen reader is on: KDE runs the bus always, and with no reader GTK went to it for every widget — a menu took two seconds to open. "on" — always, "off" — never. |
| `appearance.emoji` | `true` | Emoji in the feed at all. false — turn off every last one: servers' pictures (:blobcat:), ordinary Unicode ones (🔥 😂 🇬🇪), and the reactions line under a post. A name made only of emoji shows the login. fedtail's own glyphs (⚠ ↔ ❯) aren't touched. |
| `appearance.custom_emoji` | `true` | Servers' own emoji (:blobcat: and the rest) — as pictures in posts and names. false — leave them as text :blobcat: (and don't fetch their pictures). |
| `appearance.text_markup` | `true` | ~~text~~ — struck out, as the author meant: their client or server (Mastodon) knows no Markdown, and the tildes came as they were. Not in links and not in code. false — tildes as they came. |

## 2. Window and layout

### `[window]`

| Key | Default | What it does |
|---|---|---|
| `window.frontend` | `"qt"` | The interface: "qt" — a window; "tui" — in a terminal (needs Textual: python3-textual or pip install textual), the same as `fedtail --ui tui`; "web" — in a browser (`--ui web`); "gtk" — a GTK 4 window for GNOME and other GTK desktops (python3-gi gir1.2-gtk-4.0; `--ui gtk`). |
| `window.layout` | `"single"` | How the window opens:<br>"single" — one window: the lanes on the left, one lane on the right (or several side by side, in columns — open_columns below, and the ❯ button at the top left);<br>"split" — as in QIP, Psi or the Mail.ru Agent: the lanes in a narrow roster window (what's new in each, a line of the newest post and its author's face), and the messages window, without the sidebar, an input line at its bottom; a double click on a roster item opens it, closing its last tab closes it. Closing the roster closes fedtail (to the tray with close_to_tray). |
| `window.open_columns` | `false` | With layout = "single": open with the lanes side by side, in columns, as in TweetDeck (the ❯ button at the top left switches it any time). |
| `window.columns` | `[]` | Which lanes stand as columns, left to right, until you change them in the window (a click on a lane on the left adds a column, ✕ on a column takes it away, ‹ › move them; that is remembered). Names — as in lanes.enabled; "list:Friends" — a list by its title. [] — Home, Replies to me and Activity. |
| `window.column_width` | `460` | The width of one column in pixels (at least 280). They don't fit the window — sideways scrolling. |
| `window.themes_by_layout` | `"auto"` | Themes for this window layout: "Try a theme" offers only those made for it (a theme says layouts = ["split"]: the messengers' qip, mra, psi are for split; the rest for both). "auto" — so in releases, every theme in development versions; "on"; "off". |
| `window.roster_on_top` | `false` | With layout = "split": the roster stays above other windows. |
| `window.roster_threads` | `15` | With layout = "split": how many followed threads and private talks stand in the roster as items of their own ("Threads", "Talks"), the freshest; 0 — none, the lanes only. |
| `window.split_tabs` | `"keep"` | With layout = "split": closing the messages window "keep"s its tabs for when it opens again, or "close"s them all — it opens with only what you open from the roster. |
| `window.dock_commands` | `true` | With layout = "split": the input line at the bottom takes the command line's commands too ("#a3f text", "! #a3f", "S #a3f", "?" — Enter runs them), and the command line itself is hidden (Ctrl+L brings it). false — the input line only writes. |
| `window.sidebar_groups` | `true` | Lanes on the left in groups with headings: "Timelines", "Personal", "Lists". false — one list. |
| `window.sidebar_width` | `272` | The width of the left column (the account, the lanes) in pixels, at least 180. Its edge can be dragged with the mouse too — that's remembered until the next start, and this number stays. |
| `window.sidebar_footer` | `true` | Small at the bottom left: the version, the build and who wrote it. false — take it away. |
| `window.start_lane` | `"none"` | What is open at start:<br>"none" — nothing: every lane behind the curtain, the counts on the left (Enter opens the last one);<br>"last" — the lane open last time;<br>a lane's name — always that one: "home", "replies", "subs"… (as in [lanes]). |
| `window.tray` | `true` | The tray icon (qt, gtk). false — no icon at all: notifications then go through the desktop only (notify-send), the cross closes the program, Esc with window.esc = "tray" minimizes. |
| `window.close_to_tray` | `true` | The cross hides the window to the tray instead of closing the program. |
| `window.esc` | `"curtain"` | Esc closes what's on top (a picture, the search), and the last Esc:<br>"curtain" — draws a curtain over all lanes: the window stays, the counts on the left, nothing on the right; nothing is marked read — open it in the morning and the new has piled up;<br>"tray" — takes the window to the tray at once (without a tray — minimizes it);<br>"off" — does nothing. |
| `window.post_keys` | `true` | Keys in a lane and a thread, as in web clients: j / k — the next / previous post, r — reply, f — like, b — boost, m — bookmark, o or Enter — open the thread. false — these letters do nothing. |
| `window.number_keys` | `"alt"` | A lane by its number in the sidebar: "alt" — Alt+1…9, "ctrl" — Ctrl+1…9, "both" — either (the windows; a browser and a terminal keep these keys for themselves). |
| `window.pin_tabs` | `false` | Pin tabs (a thread, a profile): right-click a tab — "Pin the tab". A pinned one has no ×, and Ctrl+W / Esc pass it by (the windows). |
| `window.command_line` | `true` | A command line as on Point at the bottom of the window (Ctrl+L shows it even if false). |
| `window.whats_this` | `false` | "What's this?" from the start: point the mouse at a button — a longer hint on what it does, which config key changes it and where the help says more. For now it's turned on and off in the ≡ menu → "What's this?". No shortcut on purpose (F1 is next to Esc). |
| `window.compose` | `"inline"` | Where to write a post: "inline" — a panel inside the main window (the keyboard layout isn't reset: KDE keeps it per window, and a new window may open with another one); "window" — a window of its own, as before. |
| `window.compose_size` | `0` | The size of the post panel — in percent of the main window (and following it when the window changes size): 50, 80, 100… 0 — as before, at most 820 × 540. The ⤡ button in the panel switches between normal and big (90 %) and remembers the choice. |
| `window.icon_count` | `["to_me", "replies", "mentions", "subs", "commented", "important", "requests"]` | The unread number on the icon — in the tray and on the task bar button (KDE: needs the menu entry from --install-desktop and the python3-pyside6.qtdbus package). It counts the lanes from here, except those in icon_count_except; [] — no number. Lane names — the same as on the left (a lane's word is in its tooltip too):<br>federated — Federated home — Home local — Local<br>bots — Bots my_posts — My posts direct — Direct<br>mentions — Mentions replies — Replies to me subs — Subscriptions<br>bookmarks — Bookmarks my_likes — My likes activity — Activity<br>requests — Follow requests to_me — To me important — Important people<br>unsorted — Unsorted (shown while not empty)<br>"lists" — all lists at once; one list — by its title (or id): "list:Friends".<br>"all" — every lane at once (only in the first of the pair; take the rest away in except).<br>"custom:<name>" — a lane of your own ([[lanes.custom]]). federated and local are never counted (they are browsed, there's no unread in them). For example: ["replies", "mentions", "lists"] or ["all"] + except = ["home", "bots"]. |
| `window.icon_count_except` | `[]` | Which lanes not to count on the icon, even if they are in icon_count (say, with icon_count = ["all"]): the same names — "home", "bots", "lists", "list:News"… |
| `window.desktop_entry` | `true` | The menu entry and the icon (~/.local/share/applications, icons): at every start of a window (qt, gtk) check they're there and point to this fedtail (a moved checkout, a new one-file build) and mend them; old entries of the former name (fedtail.desktop) go. With the deb package its menu entry is the one: none of ours beside it. |

## 3. Lanes

### `[lanes]`

| Key | Default | What it does |
|---|---|---|
| `lanes.preset` | `"fedtail"` | Every lane is a rule (docs/en/dev/feeds.md); a set of them comes with fedtail — pick one:<br>"fedtail" — Point-style: To me (replies and mentions, quick filters for each), followed threads, Important people, bots apart;<br>"mastodon" — as Mastodon's web page: Home with everything, Mentions + Activity (follow requests on top), Direct, Local, Federated, Bookmarks, Favourites;<br>"tusky" — as Tusky's tabs: Home, Mentions (private ones too) + Activity, Local, Federated, Direct;<br>"phanpy" — as Phanpy: Home, Mentions (private ones too), Direct, Activity, Bookmarks, Likes, Local;<br>"fedilab" — as Fedilab's tabs: Home, Local, Federated, Mentions (private ones too) + Activity, Direct, Bookmarks, Favourites. The rules of each are in fedtail/data/presets.toml; `fedtail --lanes-to-config` writes the chosen set's lanes here, as [[lanes.custom]], to read and change. A [[lanes.custom]] of the same name takes a set's lane's place; a new name adds a lane. |
| `lanes.enabled` | `[]` | Which lanes to show, in this order (within a section on the left: Timelines, Personal); [] — all of the set's, in its order. A lane's word is in its tooltip on the left too:<br>federated — "Federated": everything your server knows from all servers<br>home — "Home": the people and tags you follow (fedtail's: without bots)<br>local — "Local": your whole server<br>bots — "Bots": the people you follow, bots only<br>my_posts — "My posts"<br>direct — "Direct": private messages (visible to the mentioned only)<br>to_me — "To me": replies and mentions in one lane, with quick filters for each<br>important — "Important people": posts of those you rang the bell on (a profile's 🔔); shown once there is any<br>subs — "Subscriptions": what's new in threads you follow (as on Point)<br>bookmarks — "Bookmarks" my_likes — "My likes"<br>activity — "Activity": who liked, boosted, followed you; follow requests on top<br>mentions, replies, requests — the lanes before To me, and follow requests as a lane: in no set, any list here may name them<br>"lists", "tags" — where the server's lists and the saved tag lanes stand (else at the end);<br>a lane of your own — by its name ("posts"). The old names are understood too: people = home, comments = replies, global = federated, mine = my_posts, favourites = my_likes, "custom:posts" = posts. federated and local are fetched only while open, and without counts: they are browsed. |
| `lanes.extra_bots` | `[]` | Accounts to count as bots even if they have no "bot" tick. Your server — just "nick", another one — "nick@server". |
| `lanes.posts_only` | `[]` | In which lanes "posts only" (without comments/replies) is on at start. The tick over a lane switches it too — the choice is remembered. |
| `lanes.unsorted` | `true` | "Unsorted": what came from the lanes read through (Home, Mentions, lists…) and no lane took, so a rule never loses a post. Shown only while something is in it. false — hidden for good and not collected. |
| `lanes.browse_keep` | `200` | Lanes you browse rather than read through (Federated, Local while lazy): the newest this many of the whole stream, taken while the lane is open — something to scroll through however fast a relay pours in. "Older" goes further back; what's beyond it goes at the next update. |
| `lanes.custom` | `[]` | Your own lanes ("free lanes", docs/en/dev/feeds.md): each is a table [[lanes.custom]] — name (a word, stays), title (what the sidebar shows; per language — { ru = "…", en = "…" }), icon (its picture: home, local, federated, bots, my_posts, direct, replies, mentions, subs, bookmarks, my_likes, activity, requests, list, tags, star_full and the library: important, commented, people, heart, fire, news, rss, mountain, fish, car… — the lane editor lists them), any (conditions: a post goes in if it matches any of them; inside a condition every key must match), none (conditions that keep a post out). Keys of a condition: source (home, local, federated, mentions, mine, bookmarks, favourites, subs, "list:<id>"; none — guessed from the rest), author (me, followed, local, remote, bot, stranger, "@nick@server", "domain:server"…), kind (post, reply, self_reply, boost, self_boost, quote, poll), me (reply, reply_to_post, reply_to_comment, mention, direct), visibility, has (media, image, video, cw, link, "tag:x"), lang, state (unread, bookmarked…), target (for boosts: my_post, my_comment, post, comment, seen, read), age ("<1d", ">2d"; age_of = "original" — of a boosted post), likes / boosts / replies (">10"), text ([["word", "and word"], ["or this"]]), event (favourite, reblog, follow, poll, update, status: those rows of Activity, a line each among the posts). A lane stands in "Personal" (group = "standard" — in "Timelines"): where lanes.enabled names it ("custom:feed"), else at the end. The free lanes fill from what is stored already. An example (then take away the custom = [] line below):<br>[[lanes.custom]]<br>name = "feed"<br>title = "Feed"<br>any = [{ author = "local", kind = "post" }, { me = "reply" }, { author = "me" }]<br>none = [{ kind = "boost", target = "seen" }] |
| `lanes.tag_groups` | `[]` | Lanes of several tags — in the sidebar, in the "Tags" group (fetched while open, like "Federated"). Each is a table [[lanes.tag_groups]]: name — what to call it, any — any of the tags, all — all at once, none — without. The same can be typed in the search ("#грузия #georgia -#politics") and kept with the "＋ to lanes" button — then there's no need to write it here. An example (then take away the tag_groups = [] line below — TOML won't allow both):<br>[[lanes.tag_groups]]<br>name = "Georgia"<br>any = ["грузия", "georgia", "tbilisi"]<br>none = ["politics"] |
| `lanes.languages` | `[]` | Languages you read: posts in others leave the lanes of languages_in. Empty — every language. Two or three small letters (ISO 639), like ["ru", "en"]. A post in a language that can't be told (no tag, too short to guess) always stays. |
| `lanes.languages_in` | `["federated", "local", "tags"]` | Where the languages filter works: lane words, "lists" — every list, "tags" — every tag lane. Home isn't there by default: whom you follow, you read whole. |
| `lanes.detect_language` | `"untagged"` | Telling a post's language when its author didn't — or tagged it wrong:<br>"untagged" — guess when there is no tag, or when the letters say the tag can't be right (an "en" post in Cyrillic or in Chinese characters);<br>"always" — the guess beats the author's tag whenever there is one;<br>"off" — the author's tag only. Scripts that give the language away (Chinese, Japanese, Korean, Arabic, Georgian, Cyrillic…) are told for free; Latin text — by python3-langdetect, if it is installed. |
| `lanes.detect_min_words` | `12` | The shortest post (in words) the guess by words is tried on: shorter ones it gets wrong. |
| `lanes.federated_extra` | `[]` | Wider than your server knows. Servers whose public lane (their own people's posts) also comes into Federated while it's open, and servers whose tag lanes come into your lanes of tags (a lane of #linux takes #linux from them too): read without an account, each new post fetched into your server by its address — so it is answered and liked as any other, and your server knows it from then on. A server at most every extra_minutes, up to 20 posts a time. Many keep these lanes closed to strangers (GoToSocial always): then it's left for a few hours. Like ["mastodon.social", "fosstodon.org"]. |
| `lanes.tags_extra` | `[]` |  |
| `lanes.bubble` | `[]` | The servers of your "bubble": a lane of rules with source = "bubble" reads Federated, only their people's posts (like Akkoma's bubble timeline). Like ["fosstodon.org", "mas.to"]. |
| `lanes.extra_minutes` | `10` |  |
| `lanes.tags_one_request` | `false` | Ask a lane of tags (several tags in one) in one request, not one per tag — where the server can (Mastodon: any[], all[], none[]). false — a tag at a time. |

### `[lists]`

| Key | Default | What it does |
|---|---|---|
| `lists.enabled` | `true` | The server's lists (Mastodon, GoToSocial) — as lanes of their own under the main ones. Make a list and put a person in it — with a right click on a post. |
| `lists.hide_members` | `"all"` | You put a person or a bot in a list — their posts, their boosts and others' boosts of their posts are read in the list's lane and leave the general lanes, so they don't clutter them:<br>"all" — so with any list;<br>"exclusive" — only with lists ticked "exclusive" (the server itself takes such people out of Home);<br>"off" — don't take them out of anywhere. |
| `lists.hide_in` | `["home", "bots", "federated", "local"]` | Which lanes to take them out of (names — as in [lanes]). |
| `lists.refresh_minutes` | `10` | How often to reread the lists themselves and who is in them, minutes. |

## 4. Reading

### `[reading]`

| Key | Default | What it does |
|---|---|---|
| `reading.order` | `"oldest_first"` | The order: "oldest_first" — oldest on top, you read downwards (as in RSS/Point); "newest_first" — newest on top (as everyone does). |
| `reading.start_at` | `"first_unread"` | Where to stand when a lane opens: "first_unread" or "newest". |
| `reading.on_new` | `"keep_position"` | What to do when new posts come: "keep_position" — stay where you are; "jump_to_newest" — jump to the new (as everyone does); "hold" — keep the new out of the lane, "N new" in its header, Refresh (⟳, F5) shows them (as Elk does). |
| `reading.page_size` | `40` | How many posts a request to the server. |
| `reading.catch_up_limit` | `400` | How many new posts to catch up a poll (the rest — with the next one). |
| `reading.render_limit` | `300` | How many latest posts to keep on screen in a lane (older ones — with the "older" button). |
| `reading.older_ahead` | `false` | Read to the end of what a lane shows — fedtail fetches another page of older posts by itself (as the "older" button does), and the lane goes on without a seam. None left — it asks no more until a restart. Every interface and the phone. false — by the button only. |
| `reading.build_at_once` | `40` | How many cards to build at once when a lane opens — around where you read; the rest are built as you scroll near an edge (the screen doesn't wait for fifty cards). What you read doesn't move meanwhile. 0 — build the whole lane at once (as before: on hundreds of posts that takes seconds). |
| `reading.remember_choices` | `false` | The quick filters, remembered between runs: over a lane — "All / Posts only / New", a lane's own quick filters, "Feed / Conversations", the media funnel — and Activity's. false — every run starts afresh ("All", "Feed", or what [lanes] posts_only and a lane's rule say); a choice holds until the program closes. |
| `reading.first_run_mark_read` | `true` | At the very first run, count everything fetched as read (don't start with a pile). |
| `reading.stats` | `false` | "Statistics" in the ≡ menu: how many posts came into Home, how many you wrote and how much activity there was — over the week, day by day, and who fills Home the most. |
| `reading.mark_read` | `"on_scroll"` | When a post counts as read:<br>"on_scroll" — when you've scrolled past the whole of it;<br>"on_open" — the whole lane, as soon as you open it;<br>"manual" — by hand only: "All read", and in a post's ⋯ menu "Mark read" and "Read up to here" (this one and everything older). So a lane always waits for you exactly where you stopped, even reading one post at a time. The "Mark read" and "Read up to here" items are in a post's menu in any mode. |
| `reading.read_button` | `false` | A ✓ "Read" button right under each unread post (handy with "manual"). |

## 5. The post card

### `[card]`

| Key | Default | What it does |
|---|---|---|
| `card.show_reply_context` | `true` | The "↪ in reply to…" strip over replies. |
| `card.thread_news` | `true` | A post whose thread you follow and that has new replies there: "🔔 3 new in the thread" under it, the line opening the thread. |
| `card.repeat_boosts` | `false` | A boost of a post that was in this lane already (itself or with someone's boost) or was read, — a repeat: false — don't show it, the post stays where it first came; true — every boost brings the post up again (as everyone does). A post that came as a post is always seen. |
| `card.quotes` | `"card"` | Quotes (a post inside a post: Mastodon 4.5+, Akkoma, Misskey and others):<br>"card" — the quoted post framed inside; "link" — one line with a link; "off" — as<br>the server sent it (usually a line "RE: link"). |
| `card.link_cards` | `"full"` | A link card under a post — the title, description and picture of the page it links to (the server collects them):<br>"full" — with the picture; "text" — without the picture, in a line or two; "off" — not shown. A post with pictures of its own has no card. |
| `card.old_days` | `30` | A post older than this many days — marked "old, N days" next to the date: such posts come from someone's outbox or an old thread, and they aren't taken for news. 0 — no mark. |
| `card.collapse_tags` | `true` | A paragraph of nothing but hashtags (more than three) — padding for search: in a lane it folds into the first three and "… +N" in small type, in an open thread it's whole, but small too. Hashtags inside the text aren't touched. false — as the server sent it. |
| `card.long_form` | `true` | "📄 Read it whole" in the ⋯ menu of a post from another server: the post as the author's server keeps it. An article (Article, Page) — whole, not a title with a link; an event (Event) — with its time and place. Without your token. false — no such item. |
| `card.sensitive_media` | `"hide"` | Pictures and videos the author marked "sensitive" (without a content warning, CW):<br>"hide" — under a cover, a click shows them; "show" — seen at once. Under a CW they are hidden together with the text anyway. |
| `card.around_post` | `false` | In a post's menu — "Around this post": what came to Home just before and right after it (if Home never had it — on the author's wall). |
| `card.why_home` | `false` | Under a post in Home by someone you don't follow — "via #tag": which of your followed tags brought it. |
| `card.arts_mode` | `true` | Arts mode (after @arts, the founder of Point.im): everything as the author posted it, no nannying. Turns on at once: CWs open (expand_cw), "sensitive" pictures without a cover (card.sensitive_media = "show"), server filters neither hide nor fold posts, there is no "Report" item. Your own mutes and blocks work as usual, and what the server itself cuts off (domain blocks on it) never reaches the client at all — that can't be got round. Recommended. false — everything as everyone has it, each setting on its own. |
| `card.expand_cw` | `true` | Text and pictures under a content warning (CW) open at once. false — folded, opened with the "show" button. |
| `card.actions` | `"both"` | The buttons under a post: "both" — an icon and a label, "icons" — icons only (the labels pop up on hover), "text" — labels only. |
| `card.bookmark_button` | `true` | The "Bookmark" button in the row under a post (otherwise — only in the ⋯ menu and with the m key). |
| `card.links_in_app` | `true` | Open @mentions, #hashtags and links to fediverse posts and profiles inside fedtail (a profile, a tag's lane, a thread), not in the browser. Not found — the browser. |
| `card.show_moved` | `true` | An account moved to another server: its profile has a "moved to @new" banner with the buttons "open" and (if you follow it) "follow there". false — no banner. |
| `card.honest_counters` | `false` | Honest counters: opening a thread, ask the author's server for the real numbers of likes, boosts and replies of public posts (your server knows only those that reached it). That's a request to another server — without your token, but with your IP. |
| `card.counters_via_accounts` | `true` | If the author's server won't give the numbers without a login: ask them as another account of yours (a fedtail profile) — on the author's server, if you have one there, or on a server that already has the post. Each account's token goes only to its own server. Works together with honest_counters. |
| `card.translate` | `true` | "Translate" in the ⋯ menu of a post in another language — if your server can translate (Mastodon with DeepL or LibreTranslate). The translation — right in the card, with an "original" button. |
| `card.translate_all` | `false` | "Translate" on every post, not only those in another language: in your own language too, and on posts with no language given (the server works it out). As in Fedilab. |
| `card.translate_auto` | `false` | Translate posts in languages you neither read nor write (not the interface's, not post.language / post.languages) by themselves: the translation in place of the text, marked "translated from …". The original — in the browser or "Post JSON". Your server translates (if it can) or LibreTranslate below; a few posts at a time, in the background. |
| `card.translate_backend` | `"server"` | Who translates: "server" — your server (its /translate; not every one has it) or "libretranslate" — your own or a public LibreTranslate at translate_url. |
| `card.translate_url` | `""` | LibreTranslate's address: "https://translate.example" (http:// — on your own network). |
| `card.translate_key` | `""` | LibreTranslate's API key, if it asks for one. |

## 6. Threads and following them

### `[threads]`

| Key | Default | What it does |
|---|---|---|
| `threads.complete_threads` | `true` | Whole threads. Your server knows only the replies that reached it (from people followed on your server, or addressed to you), — that's why other people's threads have holes. Open a thread — fedtail asks the author's server for the list of replies and asks your server to fetch what's missing; the thread grows by itself a couple of seconds later. These are requests to other servers without your token (they see only the IP). false — make do with your own server. Mastodon 4.5+ gathers replies itself too — then the thread grows when the server says it's done. |
| `threads.thread_from` | `"mixed"` | Where a thread's replies come from: "local" — only what your server knows; "mixed" — yours at once, and your server fetches the missing ones from the author's, the thread growing by itself; "remote" — ask the author's server first, the thread opens whole (slower). |
| `threads.thread_recheck_minutes` | `0` | An open thread (opened in the last half hour) asks the server about new replies every so many minutes and grows when there are some. 0 — no, only when it opens. |
| `threads.thread_followed_only` | `false` | In a thread — only the replies of people you follow and yours (and what they answer, so the tree holds together). false — every reply. |
| `threads.thread_progress` | `false` | While replies come from the author's server — "⇣ fetching replies: 3 of 12" in the thread's head, then "replies fetched: N" (for a few seconds). Every interface and the phone. |
| `threads.open_at` | `"post"` | Where a thread opened from a card opens: "post" — at that post, "first_unread" — at the first unread comment (none — at the post). A lane of rules may decide for itself: open_at = "…" in its table ("Commented posts" — "first_unread"); the line "🔔 N new in the thread" always goes to the first new one. Every interface and the phone. |
| `threads.auto` | `["posts", "comments"]` | Thread subscriptions, as on Point. The server tells you only of replies that mention you; if two people answer each other under your post, you won't know. fedtail itself rereads the threads you're subscribed to and puts what's new into "Subscriptions". Subscribe/unsubscribe — in a post's ⋯ menu or with the button in the thread's header. What to subscribe to by itself: "posts" — your own posts, "comments" — threads you comment in. |
| `threads.interval_minutes` | `5` | How often to reread a live thread, minutes; a quiet one is reread less often (an hour quiet — 3 times, a day — 12, three days — 36), and threads take at most a quarter of what the server still allows. |
| `threads.active_days` | `14` | A thread where nothing happened for this many days is not checked any more. |
| `threads.max_threads` | `30` | How many threads to check in one round (the rest — in the next). |
| `threads.leave_mutes` | `true` | Unsubscribing from a thread mutes its mentions too: replies there tag everyone in it by themselves, and the server (GoToSocial) can't mute a thread. false — leave "Subscriptions" only. |

## 7. People and profiles

### `[people]`

| Key | Default | What it does |
|---|---|---|
| `people.remote_profiles` | `true` | The profile of a person from another server your server knows almost nothing about: fedtail reads their latest public posts straight from their server (the ActivityPub outbox) and asks your server to fetch them — how many — remote_posts. These are requests to other servers without your token (they see only the IP); servers that require signed requests simply give nothing. |
| `people.remote_people` | `true` | The follows and followers of a person from another server: your server knows only part of them. At the bottom of such a list there'll be a "more from their server" button — fedtail reads the lists straight from there (ActivityPub, without your token) and finds these people through your server. false — no button. |
| `people.remote_posts` | `20` | How many latest posts to fetch this way into a profile (at most 40). |
| `people.server_info` | `true` | What the person's server runs — in the profile, "🖥 GoToSocial 0.17" (from its nodeinfo, without your token; remembered for a week). false — don't ask. |
| `people.profile_show` | `"posts"` | What a profile shows under its header first: "posts" — posts without replies to others (as other clients do), "all" — posts and replies, "media" — only those with pictures and video. Switched right there, above the posts. |
| `people.profile_pinned` | `true` | Pinned posts — at the top of a profile, marked 📌. false — the profile simply in time order. |
| `people.profile_featured` | `true` | In a profile — the person's featured tags ("Often writes about: #tags") and whom they recommend (Mastodon 4.4+). false — don't ask. |
| `people.per_person_follow` | `true` | On the profile of someone you follow — two buttons: "♻ without their boosts" (their boosts don't come to Home) and "🌐 languages" (only their posts in these languages). The server keeps it, so it works in every client. false — no buttons. |
| `people.follow_date_note` | `true` | Servers don't keep the day you followed someone. When you follow through fedtail, I write the date as the last line of your private note on the person — "[fedtail followed 2026-10-18]": it's seen from any device and in other clients (in fedtail this line is hidden and kept when the note is edited). false — I remember it here only. |
| `people.forget_unfollowed` | `true` | Someone you stop following: their posts and boosts leave Home, as they leave your server's Home — at once when you unfollow here, and within a few hours when you do it elsewhere (another client, the server's web page). false — what came stays. |
| `people.home_hide` | `false` | On the profile of someone you follow — "Not in Home": their posts stay out of Home while the follow, lists and the bell stay. In this program only. |
| `people.aliases` | `false` | On a profile — "My name for them…": a name you see instead of theirs (yours only; with sync.people — on your other devices too). |
| `people.nick_colors` | `false` | On a profile — "Name colour…": their name on cards in your colour (a name from the list or #rrggbb; yours only; with sync.people — on your other devices too). |

## 8. Pictures and video

### `[media]`

| Key | Default | What it does |
|---|---|---|
| `media.image_height` | `360` | The height of a single picture in a lane, pixels (several pictures — smaller tiles). |
| `media.media_grid` | `"natural"` | Several pictures in a post: "natural" — each whole, its own shape; "square" — an even grid of squares cut around the focus point the author set (if they did; otherwise — around the centre). A single picture is never cut. |
| `media.alt_text` | `"tooltip"` | A picture's description (alt text, the author writes it for those who can't see): "tooltip" — on mouse hover; "caption" — also as a caption under the pictures. |
| `media.image_viewer` | `"internal"` | A click on a picture: "internal" — its own viewer (← → to flip, Esc to close), "browser" — open in the browser. |
| `media.video_player` | `"internal"` | Video and audio: "internal" — right in the window (a video — over the window: Space — pause, ← → — seek, M — sound, O — to the browser, Esc — close; audio — a player in the card), "browser" — open in the browser. Needs QtMultimedia (Debian: python3-pyside6.qtmultimedia python3-pyside6.qtmultimediawidgets); without it — the browser. |
| `media.video_decode` | `"software"` | What decodes video: "software" — the processor (videos in the fediverse are small, it copes easily), "hardware" — the graphics card, as Qt decides. On some cards (NVIDIA: "CUDA_ERROR_INVALID_VALUE", "more than 32 decode surfaces" in the log) hardware decoding won't start, and the video stutters, stalls or stays black. The QT_FFMPEG_DECODING_HW_DEVICE_TYPES variable set by hand beats this flag. |
| `media.gifv` | `"play"` | Mastodon's gifs (short silent videos): "play" — loop right in the card while it's on screen (at most three at once), "click" — a still frame, a click plays it over the window. |
| `media.image_upscale` | `2` | How many times the viewer may enlarge a small picture so that it fills the window (1 — never enlarge). |
| `media.save_dir` | `""` | Where to save pictures (S in the viewer, a right click on a picture in a lane). "" — the desktop's Downloads folder (~/Downloads, or as set in KDE). |
| `media.prefetch` | `"previews"` | Fetch the pictures of new posts ahead, as soon as the posts have come — open a lane and they're on disk already. "previews" — previews (of videos too), avatars and link pictures; "all" — also the original pictures, the videos themselves and gifs (videos — one at a time, by a worker of their own, at most 300 MB each; much more traffic and disk space); "off" — only when the post is on screen. |
| `media.image_cache_mb` | `64` | How much memory, MB, to keep for pictures already fetched and decoded (the oldest are thrown out first; the cache stays on disk, rereading from there is instant). |
| `media.image_decode` | `"box"` | Pictures in a lane are decoded in memory to the size of their frame (minding the screen's density): "box" — several times less memory and work for the processor; "full" — as before, up to 1200 pixels on the longer side (sharper if you stretch the window later). |
| `media.image_disk_mb` | `1000` | How much disk space, MB, to keep for fetched pictures: over that, out go the ones not opened the longest (at start and along the way). 0 — don't clean. |
| `media.video_disk_mb` | `10000` | The same for videos, gifs and sound — they have their own folder and their own limit, MB (a clip or two is a gigabyte already). A video opened once stays on disk and plays at once the next time. 0 — don't keep videos on disk. |
| `media.unload_hidden_minutes` | `10` | A lane not opened for this many minutes lets its cards go from memory: a client open for days otherwise holds hundreds of cards with all their pictures (over a gigabyte). Open it again — it's drawn anew, from the first unread (that's quick). The lane open right now is never unloaded. 0 — keep everything. |
| `media.keep_hidden_lanes` | `3` | How many lanes out of sight keep their cards for coming back at once, besides the one in front: the ones opened last. One opened before them lets its cards go the moment another lane comes to the front (a lane drawn is some 15–20 MB with its pictures; reading through a dozen held half a gigabyte). Opened again — drawn anew, at the first unread. 0 — only unload_hidden_minutes decides. |

## 9. Writing posts

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
| `post.spellcheck` | `true` | Spell checking in the post window: words with mistakes underlined, a right click — the suggestions and "Add to dictionary" (your own one — spelling.txt in the config folder). The dictionaries are the system's, through Enchant (Hunspell, Aspell…); none — no checking, the rest as it was. |
| `post.spell_languages` | `[]` | Which languages to check in: [] — the post's language, the interface's and English (a word is fine if any of the dictionaries knows it). Or your own: ["ru", "en", "uk"]. |
| `post.complete_mentions` | `true` | Typing @ar — suggest people: first those seen most in the lanes, then those the server finds. false — no suggestions. |
| `post.complete_tags` | `true` | Typing #ge — suggest tags: first those you follow, then the most frequent in the lanes. |
| `post.complete_emoji` | `true` | Typing :co — suggest the server's emoji (:cookie: and the like), Tab or Enter puts it in. false — no suggestions. |
| `post.report_forward` | `true` | A report to the moderators about a person from another server: the "forward to their server too" tick is on at once (they won't learn who reported). false — off by default. |
| `post.quote_policy` | `""` | Who may quote your new posts (Mastodon 4.5+): "public" — everyone, "followers" — followers, "nobody" — nobody; "" — as in the account's settings on the server. |
| `post.quote_action` | `true` | "Quote" in the ⋯ menu of a post its author allowed to quote (Mastodon 4.5+). |
| `post.quote_prefix` | `"> "` | "Reply with quote" in a post's ⋯ menu and "Quote in reply" on selected text: the reply gets a quote, every line starting with this (a Markdown quote). With the reply already open, the quote goes where the cursor is: select a sentence, quote, answer, select the next one… "" — no such items. |
| `post.invite` | `true` | "Call into the thread…" in a post's ⋯ menu: a reply to it with only "@" in it so far and the people list open — the one named gets a notification and sees the thread at home. The thread's other participants aren't mentioned (they aren't bothered). The same on the command line: #a3f @whom text. |
| `post.who_can_reply` | `""` | Who may reply to your new posts — GoToSocial only (interaction policy):<br>"" — as in the account's settings; "everyone" — everyone; "followers" — followers and<br>the mentioned; "following" — those you follow, and the mentioned; "mentioned" — only<br>the mentioned; "me" — only you. This isn't sent to other servers. |
| `post.who_can_boost` | `""` | Who may boost your new posts (GoToSocial) — the choices are the same as for who_can_reply. |
| `post.who_can_like` | `""` | Who may like your new posts (GoToSocial) — the choices are the same as for who_can_reply. |
| `post.schedule` | `true` | The "⏰ Later" button in the post window: send at a set time (the post waits on the server, even if fedtail is closed). The list of waiting ones — the ≡ menu → "Scheduled". false — no button. |
| `post.alt_reminder` | `true` | A picture without a description — before sending, ask: "Describe" or "Send as is". false — don't ask. |
| `post.redraft` | `true` | "Delete and redraft" in the ⋯ menu of your own post: the post is deleted, and its text (as you typed it), CW, visibility, language and what it answered open as a new draft. Pictures don't come back — the server deletes them with the post. false — no item. |
| `post.resize_images` | `true` | A picture bigger than the server takes (it says itself how big) — before the upload shrink a copy instead of being refused: under its pixel limit, as JPEG (with transparency — PNG) — under its byte limit. Your file isn't touched. false — send as is. |
| `post.focus_point` | `true` | A double click on a picture in a post — its description and the focus point: click the picture where the main thing is, and the preview (where it's cut) shows exactly that. false — the description only. |
| `post.chain` | `true` | A thread as a chain: a line of nothing but "---" splits the text into posts — they go at once, each a reply to the one before (pictures and the poll go with the first). The character counter counts each part on its own. false — "---" stays plain text (a horizontal rule in Markdown). |
| `post.preview` | `true` | The "👁 Preview" button in the post panel: how it will look — the Markdown already rendered (if the server understands it), the CW, visibility, each part of a chain; and from there "Send". false — no button. |
| `post.format_bar` | `"left"` | The formatting buttons by the text (B, I, S, code, link, quote, list): they put the Markdown marks around the selection, pressed again — take them off; Ctrl+B, Ctrl+I, Ctrl+K. Where they stand: "left", "right" (a column beside the text), "top", "bottom" (a row), or "off" — none. Shown only when the server understands Markdown (post.markdown): elsewhere the marks would come out as they are. |
| `post.lang_check` | `false` | Check the post's language: when the text is plainly in another language than the one the post is marked with, ask before sending — mark it that one, send as is, or go back to the text. Readers who filter the post's language out won't see it. langdetect is needed for Latin and Cyrillic; short texts aren't checked. |
| `post.link_quote` | `false` | A post's link at the end of the text becomes a quote of that post (when its author lets it be quoted), and the link leaves the text. |
| `post.send_in_background` | `false` | The editor closes as soon as you press Send, and the post (pictures and videos too) goes in the background. If it fails, you're told; the draft stays. |
| `post.scheduled_to_draft` | `false` | In "Scheduled", each post gets "To the editor": taken off the schedule and opened in the editor, to fix and send again. |
| `post.drafts_place` | `false` | "Drafts" in the ≡ menu: every kept draft — the new post, replies, quotes — to open or delete. |
| `post.markdown` | `"auto"` | Whether the server understands Markdown: "auto" (ask the server), "on", "off". GoToSocial / Akkoma do, vanilla Mastodon doesn't. |

## 10. Notifications and sounds

### `[notify]`

| Key | Default | What it does |
|---|---|---|
| `notify.enabled` | `true` | Desktop pop-up notifications. |
| `notify.lanes` | `["direct", "to_me", "replies", "mentions", "subs", "commented", "important", "activity", "requests"]` | What to notify about. home is quiet by default (everything comes there), lists too. Lane names — the same as on the left (a lane's word is in its tooltip too):<br>federated — Federated home — Home local — Local<br>bots — Bots my_posts — My posts direct — Direct<br>mentions — Mentions replies — Replies to me subs — Subscriptions<br>bookmarks — Bookmarks my_likes — My likes activity — Activity<br>requests — Follow requests to_me — To me important — Important people<br>unsorted — Unsorted (shown while not empty)<br>"lists" — all lists at once; one list — by its title (or id): "list:Friends".<br>"all" — every lane at once (only in the first of the pair; take the rest away in except).<br>"custom:<name>" — a lane of your own ([[lanes.custom]]). For example: ["replies", "mentions", "list:Friends"] or ["all"] + except = ["home", "bots"]. |
| `notify.except` | `[]` | What never to notify about, even if it's in lanes (say, with lanes = ["all"]): the same names — "bots", "federated", "lists", "list:News"… |
| `notify.privacy` | `"full"` | What to show in a notification:<br>"full" — who wrote what;<br>"sender" — only who, without the text (fine to read with others around);<br>"count" — only how many, without names and text. |
| `notify.when_focused` | `false` | Notify about the lane open in front of your eyes too (by default it keeps quiet about it; about the other lanes notifications come even when the fedtail window is active). |
| `notify.backend` | `"auto"` | How to show them: "auto" (KDE notifications if there's notify-send, otherwise through the tray), "desktop" — notify-send only, "tray" — through the tray only. |
| `notify.filtered` | `"remind"` | Filtered notifications (Mastodon 4.3+: the server holds back mentions from strangers, new accounts and the like until you allow them): ≡ → "For the tender and sensitive" → "Filtered notifications…" — who waits, "Let in" / "Dismiss", and what exactly to filter. "remind" — so, and at start a line at the bottom if someone waits; "menu" — in the menu only; "off" — neither. |
| `notify.announcements` | `"banner"` | Server announcements (from its admins: updates, rules, maintenance): "banner" — a strip over the lane until you press "Got it" (the server remembers that for other clients too); "off" — don't show. |

### `[sound]`

| Key | Default | What it does |
|---|---|---|
| `sound.enabled` | `"auto"` | Sounds. The sound scheme is a part of the theme, like the pictures: the messenger themes (qip-*, mra-*, psi) bring their own set, system plays the desktop's sounds (the KDE/GNOME sound theme), terminal and bnw the terminal's beep, the rest what they inherit. One program plays them all: pw-play, paplay or aplay (Linux), afplay (macOS), Windows itself; none of them — silence. "auto" — sounds in development versions (X.Y.Z.devN — git between releases), none in releases and the builds made from them; "on" — always; "off" — never. |
| `sound.lanes` | `["direct", "to_me", "replies", "mentions", "subs", "commented", "important", "requests"]` | Chime about news in these lanes (names as in notify.lanes). Each lane has its sound:<br>direct → "private", replies → "reply", mentions → "mention", subs → "in a thread",<br>requests → "request", activity → "activity", every other lane → "message". |
| `sound.except` | `[]` | Never chime about these, even if lanes names them. |
| `sound.online` | `true` | The "online" sound — when fedtail has connected to the server. |
| `sound.sent` | `true` | The "sent" sound — when a post has gone out. |
| `sound.when_focused` | `true` | Chime while the fedtail window is active too (notifications keep quiet then — sounds don't). |
| `sound.scheme` | `"theme"` | Whose scheme: "theme" — the theme's; a theme's name ("qip-retro", "mra", "psi") — its sounds whatever the look; "none" — no sounds (the same as enabled = "off"). |
| `sound.volume` | `80` | Volume, 0 to 100 — where the player can (pw-play, paplay, afplay, the browser). |
| `sound.player` | `"auto"` | What plays them: "auto" — the first found of those above; or a command of yours, {file} being the file's path: "mpv --no-video {file}". |
| `sound.min_gap_seconds` | `3` | No more than one sound in this many seconds (a batch of news chimes once — the weightiest). |

## 11. Activity

### `[activity]`

| Key | Default | What it does |
|---|---|---|
| `activity.types` | `["favourite", "reblog", "follow"]` | What to show in "Activity" (and in notifications about it):<br>"favourite" — liked, "reblog" — boosted, "follow" — followed,<br>"poll" — a poll ended, "update" — a post you boosted was edited,<br>"status" — a new post of a person whose posts you turned the bell on for. ["all"] — everything listed (and whatever new versions add). |
| `activity.approvals` | `true` | Replies, likes and boosts waiting for your approval (GoToSocial: who may reply, like and boost is set in the post settings). They come here too, with the buttons "Approve" and "Reject". false — don't show (approve on the server's site then). |
| `activity.requests` | `true` | Follow requests here too, on top, with "Approve" / "Reject" — so the "Follow requests" lane isn't needed (it stays for whoever wants it, in lanes.enabled: then they're there, not here). false — only in that lane. |
| `activity.my_follows` | `true` | Whom you followed — here or in another client (seen in whom you follow) — as a row of its own: what you did, beside what others did. Not news: no number for it. A lane of rules takes it as event = "i_followed". |
| `activity.unfollows` | `true` | Who stopped following you: no server says it, so fedtail compares the whole list of your followers every unfollows_minutes; one gone from two lists in a row, and still not following when asked — a row "stopped following you" (an account its server no longer has — "gone"). Not a word unless the list came whole; the ones you removed or blocked yourself aren't news; more than unfollows_mass of one server at once — one row: that server is lost, not them. Over unfollows_max followers it doesn't look (a page is 80 of them). A lane of rules takes them as event = "unfollow" ("unfollowed_back": one you follow too), "gone", "lost". |
| `activity.unfollows_minutes` | `60` |  |
| `activity.unfollows_max` | `5000` |  |
| `activity.unfollows_mass` | `10` |  |
| `activity.unlikes` | `false` | Likes taken back: who liked your posts of the last unlikes_days days (unlikes_posts of them at most) asked again every unfollows_minutes — someone gone from it is a row "took the like back". A request a post each time: off by default. |
| `activity.unlikes_days` | `3` |  |
| `activity.unlikes_posts` | `20` |  |
| `activity.server_notices` | `true` | The server's own notices (Mastodon 4.3+): your server (or another) blocked another one — and your follows and followers from there were cut, how many and why; a warning from the moderators. They come here too. false — don't show. |
| `activity.server_groups` | `true` | The server's own groups of notifications (Mastodon 4.3+): 300 likes of one post come as one group with its count — one request instead of eight pages, one row "and 297 more"; × dismisses the whole group on the server. Where the server can't (GoToSocial, older Mastodon), fedtail groups them itself. false — always itself. |

## 12. Several accounts

### `[accounts]`

| Key | Default | What it does |
|---|---|---|
| `accounts.merge` | `[]` | All accounts in one window: lanes of the same name merge (both accounts' "Home" is one), posts of other accounts are marked "→ @nick" — a reply, a like and a boost go from the account that received the post. The other accounts' lists are lanes of their own. ["all"] — every account, ["work"] — only these profiles, [] — as chosen in the accounts menu ("All accounts in one window"). |
| `accounts.switch_closes` | `true` | Accounts are profiles (--profile name): each with its own config, theme and window. A right click on the avatar (or ≡ → "Account and server") — the list, pick one and it opens. true — this window closes then; false — both stay. |
| `accounts.account_colors` | `true` | In the shared window the "→ @nick" mark on posts of other accounts is coloured: each account has its own colour, always the same. false — no colour. |
| `accounts.act_as` | `true` | In the shared window a post's ⋯ menu has "From another account": a like, a boost or a reply not as the account that received the post. fedtail finds the post by its address through that account's server and does it from there. false — no such item. |

## 13. Sync

### `[sync]`

| Key | Default | What it does |
|---|---|---|
| `sync.url` | `""` | Read marks, thread subscriptions and the order of your own lanes the same on all your devices (a desktop, a laptop, a phone). Sync is a service of its own, apart from your fediverse server: without an address below there is simply no sync (the status bar and About say so). What travels is sealed with a key only your devices have: whatever stores it sees no posts and no read marks. How to set it up: docs/en/sync.md; in short — the address here (and, with a server, `fedtail sync invite CODE` on the first device), then `fedtail sync first` on the first device, `fedtail sync key` there and `fedtail sync join` on the others. url — the fedtail-sync server's address, as its admin gave it (say, "https://sync.example.org"). Empty — no sync server. No login: the journal is the key's; the first device makes it with the invite code the admin gave (kept in the data folder, not here). |
| `sync.folder` | `""` | Or, instead of a server, a folder every device sees: a NAS share, a Syncthing folder (~ is your home folder). One of the three: url, folder or webdav. |
| `sync.webdav` | `""` | Or a WebDAV folder, spoken to directly — nothing to mount: Nextcloud, ownCloud, a NAS (say, "https://cloud.example.org/remote.php/dav/files/me/fedtail"; made if it isn't there). The user here; the password is asked once (≡ → Sync → Login, or `fedtail sync login`) and kept in the profile's data folder, readable by you only — never in this file. With Nextcloud, better an app password. |
| `sync.webdav_user` | `""` |  |
| `sync.interval_seconds` | `60` | How often to send and fetch, seconds (at least 15). A mark goes out a few seconds after it was made anyway. |
| `sync.read` | `true` | What travels — a switch for each; off keeps it on this device only. Read marks you made (not the first run's "everything read", not older history). |
| `sync.threads` | `true` | Threads you followed, left or muted by hand. |
| `sync.lanes` | `true` | Your lanes as you arranged them: the order of lists (servers keep none) and the tag lanes you saved. |
| `sync.drafts` | `true` | Drafts: begun on one device, finished on another; sent or emptied — gone everywhere. Text, content warning, poll, who sees it; pictures are files of each computer and stay where they were added. |
| `sync.activity` | `true` | Notifications you dismissed from Activity: gone on every device. |
| `sync.tiles` | `true` | Which lanes the phone pins as tiles. |
| `sync.lane_rules` | `false` | The lanes themselves: the set (lanes.preset), which lanes in what order (lanes.enabled), your own lanes ([[lanes.custom]]), lanes.posts_only. A device that gets them writes them into its config.toml. Off by default: it changes the file. They go out when they change here (by hand or in the lane editor); a device that has just started sends nothing of its own. |
| `sync.people` | `false` | Your own names and colours for people (people.aliases, people.nick_colors) and those taken out of Home (people.home_hide). |
| `sync.sync_markers` | `true` | The reading place shared with other clients (Mastodon markers): read Home or mentions to the end on the phone — here it's read too, and the other way round. Works with Mastodon, GoToSocial, Akkoma. false — read marks live here only. |

## 14. The server

### `[server]`

| Key | Default | What it does |
|---|---|---|
| `server.interval_seconds` | `90` | How often to ask the server for what's new, seconds (at least 30). |
| `server.stream` | `"auto"` | The server's live stream: something new came — poll at once, not after interval_seconds. "auto" — if the server offers it (GoToSocial, Mastodon, Akkoma); "off" — polling only. The stream only wakes the poll, so if it drops (a laptop asleep, a proxy) nothing is lost. |
| `server.stream_gap_seconds` | `10` | The live stream wakes a poll as soon as something comes — but not more often than every this many seconds: on a busy server events come many times a minute, and every poll is a dozen requests and a bit of processor. Whatever comes in these seconds comes with one poll. "Refresh" isn't made to wait. 0 — at once on every event. |
| `server.slow_minutes` | `0` | Slow mode: the news piles up and comes once every this many minutes — in one batch, with its counts, notifications and sound; between batches nothing stirs to get in the way of work. The live stream wakes no poll meanwhile; Refresh asks at once. 0 — off (news comes as it arrives). Also on the go: ≡ → "Slow mode…" (with "notify at most every…" for each lane there). |
| `server.proxy` | `""` | A proxy for the whole of fedtail — the API, pictures, the live stream, sync, the login: "http://host:port", "socks5h://host:port" (SOCKS needs the PySocks package; the live stream doesn't go through SOCKS, polling does). A user and password — "http://user:pass@host:port". "" — as the system says (HTTPS_PROXY and the like). |
| `server.proxy_at_login` | `false` | A "Proxy" field in the login window: set it before the first request to the server (when the server can't be reached without it). What you type is written here, in proxy. |

## 15. Database and logs

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
| `debug.level` | `"debug"` | How detailed the log is in the debugging mode: "debug", "info", "warning". |
| `debug.mode` | `"auto"` | Logs and diagnostics. In the debugging mode everything is detailed: the client is kept open for days, and if it crashes, freezes or bloats — there must be traces. The files are in the logs/ folder of the profile's data folder (the ≡ menu → "Debugging" → "Open the log folder"):<br>2026-10-16_15-04-12.log — the log: requests with timings, polls, actions (clicks, lanes, tabs — without the posts' texts), errors with tracebacks, stats. A new file at every start and every hour;<br>latest.log — a link to the one being written now: that's the one to send;<br>crash.log — the stacks of all threads if the process crashed (a segfault in Qt and the like);<br>stacks.log — the stacks on demand: `kill -USR1 <pid>`, the menu, or by itself when the window freezes. To pack it all into an archive for a bug report: python3 -m fedtail --bug-report (the last two days, without the token and the database). The debugging mode: "auto" — on in development versions (from git, a number with .dev), off in releases and the one-file builds made from them; "on" / "off" — always. On: the start of fedtail.log holds all --bug-report would add (versions, the system, the options changed, config.toml itself), so the log alone is enough to send. Off: warnings and errors only, a few MB in the profile's data folder, logs/, no stats and no watchdog; crash.log stays. The --debug launch key turns it on for one run, whatever is set here. |
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
| `debug.report_repo` | `""` | Where bug reports go (≡ → "Debugging" → "Collect a report", `--bug-report`, the nightly tools/selfcheck.py): a private git repository, over ssh, with your own keys. "user/repo" — on GitHub, or a full address: "git@host:user/repo.git", "ssh://…". A report goes into reports/YYYY-MM/ as a commit of its own; the older ones aren't downloaded. Nothing is asked (no key or no access — it says so). "" — a file on disk only. This is for the developer and those he gave access: the repository must be private. |
| `debug.issue_repo` | `""` | Where "Report a bug on GitHub…" leads: the public tracker. Before it opens you see the text — the version, the system and the latest errors, with addresses, nicknames and paths already replaced by placeholders; you may edit it, and you send it yourself in the browser. "" — fedtail's own tracker; "user/repo" — another (your own build, a fork). |
| `debug.raw_json` | `false` | In a post's menu — "Raw JSON": the post as the server gave it (for bug reports). |

## 16. In a terminal

fedtail without a window: `fedtail lanes`, `fedtail show replies -n 20`, `fedtail tail`, `fedtail post "text"`, `fedtail post --reply a3f "text"`, `fedtail read replies`. The same profile, the same database and the same read marks as the window has.

### `[cli]`

| Key | Default | What it does |
|---|---|---|
| `cli.enabled` | `true` | Commands in a terminal at all. false — fedtail always opens a window, and words after the keys are an error. |
| `cli.color` | `"auto"` | Colour: "auto" — only in a terminal (not in a pipe and not in a file) and if NO_COLOR isn't set; "always" / "never". |
| `cli.max_lines` | `0` | Cut a long post to this many lines (0 — show it whole). |
| `cli.tail_lanes` | `[]` | Which lanes `fedtail tail` shows without names. [] — those in notify.lanes. |

### `[tui]`

The interface in a terminal — `fedtail --ui tui` (or window.frontend = "tui"): lanes on the left, posts on the right, the command line at the bottom as in the window. j / k — through posts, Enter — the thread, r — reply, f — like, b — boost, m — bookmark, n — a new post, x — the lane is read, Tab — lanes/posts, : — the command line, Esc — back, q — quit. Read marks — by reading.mark_read.

| Key | Default | What it does |
|---|---|---|
| `tui.theme` | `""` | The Textual theme: "" — its usual one; or a name: "textual-light", "nord", "gruvbox", "dracula", "tokyo-night", "monokai", "solarized-light" and others (Ctrl+P → Change theme — to look). |
| `tui.sound` | `"bell"` | Sounds (sound.*) in the terminal: "bell" — the terminal's beep (reaches you over ssh too); "scheme" — the sounds of the appearance.theme theme, played by this computer; "off" — silence. |
| `tui.lanes_width` | `26` | The width of the lanes column, in characters. |
| `tui.show_context` | `true` | Over a reply — a line "↳ @who: the start of what it answers". false — without it. |
| `tui.pictures` | `"auto"` | Pictures in the terminal (need Pillow, python3-pil). "auto" — real pictures where the terminal can show them: sixel (Konsole, WezTerm, foot, xterm in vt340 mode) or the kitty protocol (kitty), with the textual-image package installed (pip install textual-image); elsewhere drawn with half blocks (any true colour terminal). A post's first picture small right in the lane, v — all of them big. "blocks" — half blocks always; "key" — on v only; "off" — none (o — open the post in the browser). |
| `tui.picture_rows` | `8` | How high a picture in the lane is, in lines. |
| `tui.viewer` | `"auto"` | v on a post with pictures: "auto" — shown by chafa, timg or kitty's icat when one of them is installed (the interface steps aside, Enter brings it back): real size and colours in Konsole, kitty, WezTerm and the rest; without them — in the interface itself. "app" — always in the interface. |
| `tui.video` | `"auto"` | Video and gifs (v on a post with a video, Enter on it among the pictures) play in mpv: "auto" — in a window of its own on a desktop, drawn right in the terminal otherwise (over ssh: sixel, kitty, or coloured text); "window" — always a window; "terminal" — always in the terminal; "browser" — open in the browser. No mpv — the browser, and it says so. |

## 17. In a browser

`fedtail --ui web` (or window.frontend = "web"): fedtail in a browser tab. At start it prints a link with a key (and opens it); the key lies in the profile's data folder, web.key — delete the file and there'll be a new one (old links stop working).

### `[web]`

| Key | Default | What it does |
|---|---|---|
| `web.host` | `"127.0.0.1"` | Which address to wait on. "127.0.0.1" — from this computer only; "0.0.0.0" — from the home network too (from the phone: the one-time link fedtail prints at start, with the computer's address instead of 127.0.0.1; good for 15 minutes). Everything goes unencrypted there, so for your own network only; from outside — through a VPN or a proxy with TLS. |
| `web.port` | `8765` | The port. |
| `web.open_browser` | `true` | Open the browser at start. |

## 18. On a phone and a tablet

The Android app (the android/ folder of the repository). Its config is this same file: in the app ⋮ → "Settings" (each option with its explanation) or "Config" (the file itself). On a computer these settings do nothing.

### `[phone]`

| Key | Default | What it does |
|---|---|---|
| `phone.overview` | `"tiles"` | The overview of lanes — the home screen: "tiles" — tiles, four in a row (the count and the name); "list" — a list, a row per lane, with its first unread post. |
| `phone.layout` | `"auto"` | How many columns: "auto" — by the screen's width (a phone — one, a phone on its side and a narrow tablet — the lanes and a lane, a wide tablet — the lanes, a lane and a thread side by side); "one", "two", "three" — always that many, if they fit. |
| `phone.push` | `"auto"` | Notifications at once, with the app closed: "auto" — through UnifiedPush when the phone has a distributor for it (ntfy, Sunup, NextPush…): your server pushes to it, the app wakes and asks; without one, or "off" — a round every 15 minutes (Android's least). |
| `phone.stream` | `"always"` | The live stream on the phone: "always", "wifi" — on Wi-Fi only (on a mobile network, polling every server.interval_seconds), "off" — polling only. |
