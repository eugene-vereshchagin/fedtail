# Changelog

## 0.8.0 — in progress

- Mastodon 4.5+ fetches a thread's missing replies itself and says so
  (`Mastodon-Async-Refresh`): fedtail waits for it and the open thread grows when the server
  is done — alongside its own asking of the author's server (`feed.complete_threads`).
- The read position is shared with your other clients (Mastodon markers, also in GoToSocial
  and Akkoma): Home or mentions read up to some post on the phone are read here too, and how
  far you've read here — everything from the oldest on — goes to the server for them.
  `read.sync_markers = false` keeps reading marks here only.
- @names complete while you write: the people seen most in the lanes first, then those the
  server finds (a moment later, without fetching from other servers); the list shows the
  name next to the address. `post.complete_mentions` and `post.complete_tags` turn either off.
- Quote posts (Mastodon 4.5+, Akkoma, Misskey, Fedibird): the quoted post framed inside the
  quoting one, a click opens its thread; a quote that can't be shown says why (awaiting
  approval, withdrawn, deleted, its author muted or blocked — with "open anyway"); the
  "RE: link" line servers add for older clients is gone. `feed.quotes = "card"`, `"link"`
  (one line) or `"off"`.
- Servers' own emoji (`:blobcat:`) are pictures now — in posts, content warnings, names and
  "boosted by"; the ones not downloaded yet come in by themselves. `feed.custom_emoji =
  false` keeps them as text.
- Link cards: a post that links to a page shows the page's card — site, title, a line or
  two of description, its picture — as the server collected it; a click opens the link.
  `feed.link_cards = "full"`, `"text"` (no picture, no description) or `"off"`.
## 0.7.0 — 2026-10-17

- In the debugging mode the status bar's right end says how the window is drawn: theme, Qt
  style, font, platform, scale, one-file build or source. The log adds the window's size,
  the least it needs and the widest widgets.
- The one-file build in KDE uses Plasma's default font (Noto Sans 10) when `kdeglobals` names
  none — KDE writes it there only once it's been changed — instead of Qt's bare "Sans Serif 9".
- The Linux one-file build brings all of Qt's platform plugins, Wayland's included: without
  them Plasma on Wayland ran it through XWayland, unscaled — tiny letters and a window of
  the wrong size.
- Links, the config, folders and notifications from the one-file build open with the
  system's programs in the system's environment (they were handed the build's own Qt
  libraries, so KDE asked every time what to open the config with).
- Hashtags complete while you write: `#ge` offers the tags already in use — the ones you
  follow first, then the most used in the posts fedtail has seen (`#georgia`,
  `#GeorgiaNews`…); ↑ ↓ and Enter or Tab pick one.
- Pictures stuck in "loading": with avatars and pictures asked for all the time, newest
  first, an older request could wait behind them forever — now one that has waited 6 s
  goes next, and there are six downloads at a time, not four. A preview that gave up is
  asked again as soon as its original comes (opened in the viewer), so closing the viewer
  shows it in the lane too.
- The Linux one-file build uses the system's fontconfig and freetype instead of the build
  machine's older ones, which couldn't read a newer system's font setup — every font fell
  apart. In KDE it takes the colour scheme, the font and the icon theme from `kdeglobals`
  (its Qt can't load KDE's own integration), instead of plain washed-out grey.
- The one-file build keeps its window size and place apart from the one run from the
  source: they may scale differently, and one stretched the other's window.
- The log's first lines say more about the display: Qt platform, style, font, screen scale
  and DPI, one-file build or not.

## 0.6.1 — 2026-10-17

- The config is in chapters now — look & window, reading, lanes, posts, notifications… with
  a list of them at the top and sub-headings inside `[ui]` — and every option is written with
  its default value (not commented out), so an editor colours it. A value written there stays
  yours even when a later default changes; comment it out to follow the program.
  `--rebuild-config` lays an existing config out anew in the chapters, keeping your values
  (a `.bak` keeps the old file).
- The detailed log (debugging mode) is on only in development versions from git now, not in
  releases or the one-file builds; `debug.mode = "on"` or `--debug` turns it on there.
- README: a download line at the top and a table of contents.

## 0.6.0 — 2026-10-16

- Somebody's boost of a post by a person you put in a list stays out of Home (and the other
  lanes in `lists.hide_in`) too, not only that person's own posts and boosts.
- Theme `bnw` — bnw.im: a black frame, grey posts on white, everything monospace, bright
  green buttons. Themes may now colour the left panel apart from the posts
  (`sidebar_text`, `sidebar_muted`) and give the post panel and dialogs their own background
  (`panel`); left at "auto" they follow `text`, `muted` and `window` as before.
- A lane opens at once on a click: first the switch, with "loading…" over the lane, then the
  drawing (a lane of a few hundred cards takes a moment); the same over All | Posts | New.
- Quit (from the tray or the menu) quits at once: the process no longer lingers for minutes
  after the window is gone, waiting for downloads nobody needs any more (a picture's
  original may take two minutes). The log says which were left behind.
- Notifications about one list, by its title: `notify.lanes = [..., "list:Друзья"]` —
  not all lists at once (`"lists"`), which with bots in them would never stop. The log
  says which new posts got no notification because their lane isn't in `notify.lanes`.
- A picture, avatar or profile banner that doesn't come within 30 s (a server still fetching
  it from elsewhere) is asked for once more a few seconds later, with more patience, instead
  of staying grey until a restart. A request with no answer for three minutes is asked again.
- Opening a thread no longer makes the window wider: a long title or note above a lane, thread
  or account ends in "…" and shows the whole text in its tooltip.
- Short texts (conversation lines, notifications) no longer glue words across a quote or a
  list item: "@annaquote" is "@anna quote" again.
- Feed | Conversations is offered only where it changes something — Replies to me, Mentions,
  Subscriptions (many replies to the same threads); in Home nearly every post is a
  conversation of its own and both views looked the same. The tooltip says what it does.
- Switching All | Posts | New or Feed | Conversations: the pressed button turns at once and the
  lane is redrawn after it, under a wait cursor and in one paint (it took over a second with
  both buttons lit). The choices start fresh every run — All and Feed, or what
  `lanes.posts_only` says — unless `feed.remember_choices = true`.
- The post window is a panel inside the main window now (`ui.compose = "inline"`): KDE keeps a
  keyboard layout per window, so a new window could come up in another language mid-thought.
  It sits in the middle of the window; what the post is (who sees it, language, pictures,
  warning) is one row and what to do with it (Close, Discard, Send) another, so nothing is
  cut off in a narrow window. One panel at a time (opening another keeps the first as a
  draft), ✕ or Esc closes it, pictures dropped on the window go into it. `"window"` brings the separate window back.
- A tidier lane header: what to show is one control — All | Posts | New — and how to show it
  another — Feed | Conversations (each with a tooltip saying what it does); "↓ To new" no
  longer looks like a drop-down; buttons with nothing to do grey out instead of vanishing,
  so the others stay where they were. "Posts only" and "New" are one choice now.
- Pictures come quicker: a single big picture shows its preview at once and the full file
  replaces it when it arrives (it used to wait for the full file); the picture asked for
  last loads first, so the one on screen doesn't queue behind everything scrolled past; the
  log says when a picture waited for a worker.
## 0.5.0 — 2026-10-16

- One file, no installing: every release has `fedtail-X.Y.Z-linux-x86_64` (built on Debian 12)
  and `fedtail-X.Y.Z-windows.exe` with Python and Qt inside; `--install-desktop` works from
  them; `packaging/build.py` builds one locally. Running from the source stays as it was.
- "Unread" over a lane: only what was unread when you opened it, plus what arrives. Reading
  doesn't make posts vanish under your eyes — they grey out and stay until you leave the
  lane; the next time it opens without them. Remembered per lane.
- A video a server calls a picture (an mp4 as "image") shows as a video, and a video whose
  still frame won't load says "▶ video — click to open in the browser" instead of "picture
  didn't load"; still frames of videos get a ▶ on them.

## 0.4.0 — 2026-10-16

The public beta.

- Ready to be shown: CONTRIBUTING.md, SECURITY.md (what fedtail promises about the token,
  other servers, HTML and logs), issue templates that ask for the log, a pull request
  checklist, package metadata; CI checks that `pip install` gives a working `fedtail`
  command. The README says what fedtail is now, with a screenshot.

- Windows: a zip with `fedtail.exe` in every release (built by CI with PyInstaller, no Python
  needed); config in `%APPDATA%\fedtail`, data in `%LOCALAPPDATA%\fedtail`; one window per
  profile through a named pipe; `--install-desktop` makes a Start menu shortcut; the tests
  run on Windows too.

## 0.3.0 — 2026-10-16

- A profile's card no longer looks like one more post: a tinted block with an accent edge,
  the header picture as a banner, the name in large type, and a "Posts" heading under it.
- The debugging mode can be turned off: `debug.mode` = `auto` (on before 1.0 and in
  development builds, off in releases), `on` or `off`. Off: warnings and errors only, a few
  MB in the profile's data folder, no stats, no freeze watchdog; crash traces stay.
  `--debug` turns it on for one run.
- Logs where you can find them: `~/fedtail-logs/<profile>/`, a new file at every start and
  every hour (`2026-10-16_15-04-12.log`), `latest.log` pointing at the current one, the
  folder kept under `debug.keep_mb` (500 MB) — the oldest go by themselves. `debug.log_dir`
  moves them ("" — back into the data folder). The log also tells what you did: lanes and
  tabs opened, post actions by id, what was sent (its length, not its text), how long lanes
  took to draw, slow window events. `--bug-report` takes the last two days.
- All accounts in one window (≡ → Accounts → "All accounts in one window", or `ui.merge`):
  lanes of the same name merge, the other accounts' lists are lanes of their own, a post
  another account received is marked "→ @handle" and a reply, like or boost on it goes from
  that account. A profile already open in its own window stays there.
- At start no lane is open (the curtain, with the counts on the left; Enter opens the last
  one): starting fedtail no longer reads anything for you. `ui.start_lane`: `none`, `last`
  (the old way) or a lane's name.
- The picture viewer no longer says "loading…" forever: it shows the feed's smaller copy at
  once while the original loads, and when the original won't show it says why — a format
  Qt can't read (webp/avif without `qt6-image-formats-plugins`; Save still works) or the
  server didn't answer (R tries again). An original opened in the viewer is waited for up to
  two minutes (a server may be fetching it from the author's server just then).
- A thread is the same whichever post it's opened from: a server's context of a post holds
  only its own branch, so the tree is now read from the top post.
- Threads with holes fill themselves: on opening, fedtail reads the list of replies the
  post's own server publishes and asks your server to fetch the ones it never got; the
  thread grows a moment later, the new replies answerable like any other
  (`feed.complete_threads`; requests to other servers go without your token).
- "N new" over a lane could stay after everything was read (posts of someone just put in
  a list stayed drawn in Home while the counts already left them out): lanes redraw when
  lists change, and the pill checks the read marks themselves before it says anything.
- Accounts: right-click your avatar (or ≡ → Accounts) for the list of profiles, each named
  "@you@server"; pick one and its window opens with its own theme and config, this one closes
  (`ui.switch_closes`). "Add an account…" makes a new profile and opens the login window.
  `--profiles` lists them in the terminal. A profile keeps a small `profile.json` (who and
  which server, never the token) so the list knows names without logging in. Only real
  profiles are listed (a config.toml, a login or a database), not the shared themes folder.
- Someone you put in a list leaves the general lanes — Home, Bots, Federated, Local — and
  is read in their list, so subscriptions don't clutter the feed. `lists.hide_members`:
  `all` (default), `exclusive` (only lists marked exclusive, the old way) or `off`;
  `lists.hide_in` — which lanes. Replaces `lists.exclusive_hides`.
- A profile's buttons wrap onto the next line when the window is narrow instead of being
  squeezed until their words are cut.
- The language of a post: a list in the post window (each language by its own name), the
  default in `post.language` (`""` — as in the account's settings), the list in
  `post.languages`; drafts keep it.
- The image viewer has half-transparent buttons in the top right corner: Save, open in the
  browser, close.
- A post's `#abc` is a link: a click puts it at the start of the command line (replacing the
  number already there), ready for the text; the command line takes the whole width until
  there's a hint to show.
- Polls: the options right on the card (one or several, as the poll allows) and a Vote
  button; the results — bars, percentages, your choice ticked, the leader in bold — once
  you voted, when it's over, on your own poll, or by "Results"; how many voted, until when,
  "refresh" for fresh counts.
- `--update-config` also refreshes the explanations of options already in your file (the
  themes and choices of this version) and drops commented-out options that no longer exist;
  your values and your own notes stay.
- `--install-desktop` writes the icon's full path into the menu entry: Plasma takes a
  window's icon from its entry, and a bare name in a freshly filled icon theme often came
  out as a blank page on the task bar and in the title bar. A profile's window now names
  its own entry (`fedtail-<profile>`), not the default one.
- Sidebar sections fold: a click on "Lists" (or any section title) hides its lanes and
  shows their unread as one number next to the title; remembered across restarts.
- The unread count on the icon: drawn into the tray icon and shown on the task bar button
  (the LauncherEntry signal KDE Plasma listens to; needs the menu entry from
  `--install-desktop` and QtDBus — Debian: `python3-pyside6.qtdbus`). Which lanes count:
  `ui.icon_count` (Replies to me, Mentions, Subscriptions, Follow requests; `[]` — none).
- Network failures in the log and the terminal take one line instead of a page of
  traceback (the request itself is logged with its timing); pictures give up after 30 s
  of silence instead of 60, so a server stuck on a remote original doesn't stall the rest;
  the follow-requests tab is no longer rebuilt on every poll; a picture that just failed
  isn't asked for again for 5 minutes (and is logged once, not twice).
- Post HTML goes through an allow-list: text formatting, lists, quotes, code and links
  stay; scripts, styles, frames, pictures by path, headings, fonts and tables don't (headings
  and boxes become paragraphs). Links only to the web (and mail, xmpp, gemini, magnet) or
  inside fedtail to a profile, tag or thread — a post can't carry a link that deletes,
  boosts or follows on your behalf. There never was a browser engine here to run scripts.
- An open thread takes new replies in by itself as the poll brings them (and F5 reloads
  it as before).
- A thread you don't follow but whose replies still come says why: "not followed, but
  replies by @a, @b show in Home" — the server puts into Home replies between people you
  follow; following the thread brings everyone's.
- A command line like on Point at the bottom (`Ctrl+L`): `#a3f` opens, `#a3f text` replies,
  `#a3f/2 text` answers comment /2, `S`/`U #a3f` (un)subscribes to the thread, `S`/`U @user`
  (un)follows, `! #a3f` boosts, `~ #a3f` bookmarks, `D #a3f` deletes, `@user` opens the
  profile, `@user text` writes directly, plain text posts, `?` lists it all; while you type
  it says what Enter will do; ↑ ↓ bring earlier commands back (`ui.command_line`,
  `post.plain_posts`).
- Conversations view: a button over a lane shows each conversation once — where it started,
  how many messages, how many new, who wrote last; seeing the card marks them read.
- Edit your posts: "Edit" in the ⋯ menu opens the composer with the text as you typed it
  (Markdown included); text and warning change, pictures and visibility stay. Edited posts
  say "edited", a click shows every version.
- Silence: mute or block from a post's ⋯ menu or the profile (their posts vanish from every
  lane at once); word filters kept on the server (≡ → Silence…: fold or hide, where);
  a post folded by a filter says which; muted/blocked lists with undo.
- The last `Esc` closes every lane behind a curtain instead of hiding the window: the
  sidebar with its counts stays, nothing is marked read, new posts pile up ("Piling up:
  Replies to me — 3, Home — 12"); a lane click or Enter opens again. `ui.esc` (was
  `ui.esc_hides`; an old `esc_hides = false` still means `off`): `curtain`, `tray` (the old
  way) or `off`.
- Bookmarks, like on Point: "Bookmark" in a post's ⋯ menu, a Bookmarks lane (the server's
  bookmarks; a post bookmarked here shows up at once).
- Notifications: no longer all silent while the window is active — only the lane on screen
  stays quiet; every decision and notify-send's answer go to the log; a missing notify-send
  is said out loud (with the package to install); Debugging → Send a test notification.

## 0.2.0 — 2026-10-16

- Themes `pink`, `nord` and `solarized`.
- Diagnostics on by default until 1.0: a rotating log with every request and its timing,
  polls, errors with tracebacks and stats (memory, CPU, threads, caches, widgets) every few
  minutes; crash.log with all thread stacks on a fatal crash; stacks on demand
  (`kill -USR1`, the menu) and by themselves when the window freezes; Qt's own messages
  go to the log, not the terminal; `--bug-report` packs it all (no token, no database).
- Sidebar in sections: Timelines from the widest down (Federated, Home, Local, Bots), Personal
  (My posts, Mentions, Replies to me, Subscriptions, Likes & boosts, Follow requests), Lists at
  the bottom; every lane explains itself on hover. "People" is now "Home" and opens first;
  "Activity" is "Likes & boosts". New: Federated — the whole fediverse as your server
  knows it; Local and Federated are fetched only while open, without unread counts.
- Search (`Ctrl+K`, the box under Write): people by name, @user@server or link, tags, posts;
  Follow and Follow tag right in the results; followed tags with an empty query; a tag tab
  has Follow tag; a profile opens whom they follow / their followers, each with Follow.
- New icon: a talk bubble with a curled tail and a thread inside; drawn in the current
  theme's colours for the window, tray and notifications (`[icon]` in theme files, "auto"
  follows the accent; `ui.themed_icon`).
- Decoded pictures are kept within `ui.image_cache_mb` (128 MB), least recently used out
  first — the first bug report showed 800 MB after a few minutes with a cache bounded only by
  count.
- Links stay inside: @mentions → profile tab, #hashtags → tag timeline, fediverse links →
  looked up through your server; profiles get an info card with Follow, Mention, Add to
  list; clicking the name in its own profile tab goes back to the card.
- Docs: ARCHITECTURE.md (the whole system for the next developer, human or AI),
  DEBUGGING.md (logs and bug reports), AGENTS.md (rules on one page).
- Save pictures: `S` in the viewer or a right click on a picture; to the desktop's Downloads
  folder (`ui.save_dir`), under the file's own name, never overwriting.
- Fixed: "Failed to disconnect" warning on every card rebuild.
- Notifications per lane with "Open" to the thread; privacy levels `full` / `sender` / `count`.
- App icon; `--install-desktop` adds a menu entry with it.
- Pictures by drag and drop (compose or main window) and `Ctrl+V`; thumbnails in compose;
  the content warning field is hidden behind a button.
- Themes `point` (point.im today), `juick` and `juick-classic` (juick.com of 2013 and 2011),
  `night`, `paper`, `contrast` (for weak eyes).
- Honest counters from the post's own server (`feed.honest_counters`, off by default).
- CamelCase hint for one-case hashtags in the composer (`post.camelcase_hint`).
- Activity lane and notifications: favourites, boosts, new followers, gathered per post.
- Lists as lanes in a block of their own; "Add to list" from a post's menu or a right click;
  create, rename, delete, exclusive (hidden from People and Bots).
- A right click on a post opens its menu.
- Pictures that fail to load fall back to the preview, then say so.
- Thread subscriptions like on Point: a "Subscriptions" lane with new comments in followed
  threads; own posts and threads you comment in are followed automatically; follow/unfollow
  from the ⋯ menu or the thread header; `[subs]` settings.
- My profile: a tab with counts, and an editor for name, bio, avatar, header, fields and
  switches (approve followers, bot, directory).
- Version from git: `0.2.0.devN+gSHA`; About shows build, commit date, Python/Qt, profile.
- The last `Esc` takes the window off the screen at once (to the tray) — `ui.esc_hides`.
- `Ctrl+F` → "Deeper": search everything stored for the lane, the lane grows down to the match.
- `Ctrl+F`: find in the open lane, thread or profile; `F3` / `Shift+F3`, "3 of 12".

## 0.1.0 — 2026-10-15

- Core without GUI: profiles, TOML config with validation, token file, SQLite state.
- Lanes: people, replies to me, other mentions, bots, my posts, local, follow requests.
- Forward catch-up with `min_id`: reading stays chronological, no holes.
- Read marks per post; start at the first unread; new posts never move the view.
- Reply context strip above every reply; threads as trees with `/N` numbering.
- Composer: drafts saved while typing, Markdown when the server supports it,
  attachments with alt text, reply visibility never wider than the parent.
- Qt frontend: tray, notifications.
- New look (from the mockup): sidebar with account, Write button and unread badges; lane
  header with "N new", All | Posts only; cards with round avatars, short `#ids`, quoted reply
  context, flat action buttons; "new below" divider; thread rails and `/N` numbers.
- Themes are files: `system` (follows KDE light/dark) and `terminal`; your own in
  `~/.config/fedtail/themes/`, with inheritance.
- Image viewer over the main window; "you replied" under comments; posts-only toggle;
  `--update-config`; Russian plural forms.
