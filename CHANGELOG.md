# Changelog

## 0.1.0 — in progress

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
- Notifications per lane with "Open" to the thread; privacy levels `full` / `sender` / `count`.
- App icon; `--install-desktop` adds a menu entry with it.
- Pictures by drag and drop (compose or main window) and `Ctrl+V`; thumbnails in compose;
  the content warning field is hidden behind a button.
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
- `Ctrl+F`: find in the open lane, thread or profile; `F3` / `Shift+F3`, "3 of 12".
- Image viewer over the main window; "you replied" under comments; posts-only toggle;
  `--update-config`; Russian plural forms.
