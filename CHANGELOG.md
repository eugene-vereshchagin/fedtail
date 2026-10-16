# Changelog

## 0.3.0 — in progress

- The picture viewer no longer says "loading…" forever: it shows the feed's smaller copy at
  once while the original loads, and when the original won't show it says why — a format
  Qt can't read (webp/avif without `qt6-image-formats-plugins`; Save still works) or the
  server didn't answer (R tries again).
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
  which server, never the token) so the list knows names without logging in.
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
