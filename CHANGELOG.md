# Changelog

## 0.3.0 — in progress

- Edit your posts: "Edit" in the ⋯ menu opens the composer with the text as you typed it
  (Markdown included); text and warning change, pictures and visibility stay. Edited posts
  say "edited", a click shows every version.
- Silence: mute or block from a post's ⋯ menu or the profile (their posts vanish from every
  lane at once); word filters kept on the server (≡ → Silence…: fold or hide, where);
  a post folded by a filter says which; muted/blocked lists with undo.
- The last `Esc` closes every lane behind a curtain instead of hiding the window: the
  sidebar with its counts stays, nothing is marked read, new posts pile up ("Piling up:
  Replies to me — 3, Home — 12"); a lane click or Enter opens again. `ui.esc` (was
  `ui.esc_hides`): `curtain`, `tray` (the old way) or `off`.
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
