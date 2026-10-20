# Getting started

What fedtail is, how to log in and where things are.

fedtail is a fediverse client (GoToSocial, Mastodon, Akkoma and anything that speaks the
Mastodon API) for people who remember Juick and Point and are tired of scraps of other people's
conversations. Its whole point is giving the context back: every reply shows what it answers,
a thread opens as a tree, and a lane remembers where you stopped.

## What's different

<!-- include: parts/whats-different -->
- **Nothing jumps.** A lane opens at the first unread post. New posts arrive below and never
  move what you're reading. You read in chronological order, like RSS.
- **Every reply says what it replies to.** A strip above the reply quotes the start of the
  parent post; click it to open the whole conversation.
- **Threads are trees — whole ones.** Indented by depth, comments numbered `/1 /2 …`, the post
  you came from highlighted; replies your server never got are fetched from the author's
  server, so a thread looks the same from wherever you open it.
- **Separate lanes, in sections.** Timelines from the widest down (Federated, Home, Local,
  Bots), Personal (My posts, Direct, Mentions, Replies to me, Subscriptions, Bookmarks, Likes &
  boosts, Follow requests), and your Lists at the bottom.
- **Private by default.** New posts go to followers only; a reply is never more public than
  the post it answers.
- **Drafts survive.** Text is saved while you type; closing the window loses nothing.
- **Config file, not a settings dialog.** Every behaviour is a flag. Defaults are opinionated;
  "like every other client" is one line away.
- **Several accounts.** One profile per account, each with its own config and theme; switch
  with a right click on your avatar, or put them all in one window.
<!-- /include -->

## Logging in

1. Type your server's address, say `https://example.social`.
2. Press "Open the login page in the browser". Log in there and let fedtail in.
3. The server shows a code — paste it into fedtail's window.

The token is kept in a file only you can read and never goes to other servers. fedtail won't
take an address without `https://`: the token would travel in the clear (except for a server at
home: `localhost`, a local address, `.local`).

## The window

- **On the left** — the lanes in groups: "Timelines", "Personal", "Lists". The number is how
  much is unread. A click on a group's title folds it.
- **On the right** — the posts of the open lane, with the switches and Refresh over them.
- **At the bottom** — a command line, as on Point (`Ctrl+L`).
- **At the top left**, three buttons: ≡ — the menu, ↔ — posts across the full width, ❯ — lanes
  in columns.

"What's this?" in the ≡ menu explains any button you point the mouse at.

## Profiles and accounts

One profile is one account, with its own config, theme and database. A right click on your
avatar — the list of accounts, "Add an account…", "Make it the main one ★". The main profile is
the one started without `--profile`. All accounts can come together in one window: ≡ → "Account
and server" → "All accounts in one window".

In detail → [Several accounts](ref/features.md#several-accounts)

## Where the files are

| What | Where |
|---|---|
| The config | `~/.config/fedtail/<profile>/config.toml` — ≡ → "Open config" |
| The config reference | next to it: `config.example.en.toml`, `config.example.ru.toml` |
| Themes | `~/.config/fedtail/themes/` — ≡ → "Open themes folder" |
| The token (mode 0600) | `~/.local/share/fedtail/<profile>/auth.json` |
| Database, drafts, read marks | `~/.local/share/fedtail/<profile>/state.db` |
| Pictures and videos | `~/.local/share/fedtail/<profile>/cache/` |
| Logs | `~/.local/share/fedtail/<profile>/logs/` — ≡ → "Debugging" → "Open the logs folder" |

On Windows the config is in `%APPDATA%\fedtail\<profile>\`, the data in `%LOCALAPPDATA%\fedtail\<profile>\`.
