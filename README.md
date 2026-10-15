# fedtail

*`tail -f` for the fediverse.* A desktop client for GoToSocial, Mastodon, Akkoma and anything
else that speaks the Mastodon API — made for people who remember Juick and Point.im and are
tired of reading scraps of other people's conversations.

It is for people who are sick of hunting for where a reply came from and what the conversation
was even about — who get pulled away from work by a toot and come back with no idea what was
being discussed. So the whole point is giving that context back: every reply shows what it
answers; under someone's comment you see what you said back; a thread opens as a tree right
where you came from; a lane remembers where you stopped and never jumps.

[Русская версия](README.ru.md)

> Status: early development (0.1). Works for the author; expect rough edges.

## What's different

- **Nothing jumps.** A lane opens at the first unread post. New posts arrive below and never
  move what you're reading. You read in chronological order, like RSS.
- **Every reply says what it replies to.** A strip above the reply quotes the start of the
  parent post; click it to open the whole conversation.
- **Threads are trees.** Indented by depth, comments numbered `/1 /2 …`, the post you came
  from highlighted.
- **Separate lanes.** People and bots apart; replies to your posts apart from other mentions.
- **Private by default.** New posts go to followers only; a reply is never more public than
  the post it answers.
- **Drafts survive.** Text is saved while you type; closing the window loses nothing.
- **Config file, not a settings dialog.** Every behaviour is a flag. Defaults are opinionated;
  "like every other client" is one line away.
- **One profile = one account = one window.** `--profile work` runs another account.

## For Juick and Point.im people

fedtail aims to feel like Point on top of the fediverse: you read the feed in order and never
lose your place; every comment shows the thread it belongs to; threads are trees numbered
`/1 /2 …`; private by default. Next on the list: thread subscriptions (like `S #abc` on Point)
and an XMPP-client-style command line: `#abc text`, `S #abc`, `@user`.

## Running from source

Debian 13 (trixie) or newer:

```sh
sudo apt install python3-pyside6.qtwidgets python3-requests
git clone https://github.com/eugene-vereshchagin/fedtail.git
cd fedtail
python3 -m fedtail
```

**How to run.** From the source folder both forms work:

```sh
python3 -m fedtail           # as a module — the proper way
python3 fedtail              # as a folder — works too
```

Options are the same for both: `python3 -m fedtail --profile croco`,
`python3 fedtail --update-config` and so on. A bare `fedtail` command appears once the app is
installed as a package (a deb is planned); until then use `python3 -m fedtail` in the examples
below. All options: `python3 -m fedtail --help`.

Squares instead of emoji and flags mean there is no colour emoji font:
`sudo apt install fonts-noto-color-emoji`.

Anywhere else with Python ≥ 3.11: `pip install requests PySide6-Essentials`, then the same.

On first start fedtail asks for your server, opens the login page in the browser and waits
for the code the server shows you.

## Profiles and files

```sh
python3 -m fedtail                        # profile "default"
python3 -m fedtail --profile croco        # another account
python3 -m fedtail -c ~/my.toml -d ~/fd/  # explicit config file and data dir
```

| what | where |
|---|---|
| config (read-only for the app) | `~/.config/fedtail/<profile>/config.toml` |
| token, mode 0600 | `~/.local/share/fedtail/<profile>/auth.json` |
| cache, read marks, drafts | `~/.local/share/fedtail/<profile>/state.db` |
| images | `~/.local/share/fedtail/<profile>/cache/` |

The config is created on first run as a fully commented copy of
[`fedtail/data/config.example.toml`](fedtail/data/config.example.toml) and never touched again.
`config.example.toml` next to it is always the full reference for the running version. When
an update brings new options, fedtail says so at start, and `python3 -m fedtail --update-config` adds
them to your file, commented out, in the right sections (a `.bak` copy is kept).

## Themes

The look is a theme file. Built in:

- `system` — light or dark, whatever KDE uses: every colour comes from the desktop palette;
- `terminal` — green on black, monospace, posts divided by lines, buttons in words.
- `juick` — juick.com around 2013: a light warm-grey page, white posts, blue links.
- `juick-classic` — juick.com around 2011: an olive page, beige posts, brown-orange links.
- `point` — point.im as it is today: a white page, posts divided by thin lines, Open Sans.
- `night` — dark, with its own colours, on any desktop.
- `contrast` — for weak eyes: big type, black on white, firm lines.
- `paper` — warm paper and a book face, for long threads.

Pick one in the config: `[ui] theme = "terminal"`. Your own themes go to
`~/.config/fedtail/themes/<name>.toml` (shared by all profiles); `builtin/` next to them always
holds fresh copies of the built-ins to start from. The easy way is to inherit and change a line:

```toml
name = "My green"
inherit = "terminal"

[colors]
text = "#a8ff60"
```

A theme sets colours, fonts, corner radii, card style (boxes or rules), avatars, icons, and even
wording — `[ write ]`, `== people ==`, `---- new below ----`. Every key is explained in
`builtin/system.toml`. A broken theme is reported in the status bar and `system` is used instead.

## Lanes

"Replies to me" holds every reply to your posts and comments; "Mentions" holds the rest, the
places where you were tagged in someone else's conversation. A reply that also says `@you`
is a reply, so it is not repeated in Mentions — set `lanes.mentions_all = true` if you want
Mentions to show everything.

**Subscriptions**, like on Point: a server tells you only about replies that mention you, so
when two people answer each other under your post you never hear of it. fedtail follows
threads itself and puts what's new in them into "Subscriptions". You follow your own posts and
threads you comment in automatically; any other thread — from a post's ⋯ menu or the
"Follow thread" button in its header. Unfollowing is remembered: commenting there again won't
bring the thread back. Settings are in `[subs]` (how often to check, when a quiet thread is
dropped, what to follow automatically).

## Lists

Your server's lists (Mastodon, GoToSocial) appear as lanes in a block of their own under the
main ones. Right-click a post (or its ⋯ menu) → "Add to list" ticks its author into any list
or a new one; right-click a list for rename, delete and **exclusive**. Whoever is in an
exclusive list is gone from People and Bots and shows up only there — sort the bots into
"Memes", "News" and the rest. `[lists]` in the config.

## Honest counters and readable hashtags

Your server knows only the favourites and boosts that reached it. With
`feed.honest_counters = true`, opening a thread asks each public post's own server for the real
numbers (without your token, but it is a request from your IP — hence off by default).

When a hashtag is written in one case (`#georgianews`), the composer suggests `#GeorgiaNews`:
screen readers read it word by word. `post.camelcase_hint = false` turns the hint off.

## Your profile

Click your avatar or name in the sidebar: your profile opens in a tab, with post and follower
counts and an "Edit profile" button — name, about, avatar, header, profile fields, and
whether to approve followers by hand, mark the account as a bot, show it in the directory.
Only what you changed is sent to the server.

## Notifications

**Activity** is a lane of its own: who favourited or boosted your posts and who followed you,
gathered per post ("Kot, Arsen and 3 more — ★ favourited «…»"). `[activity] types` picks the
kinds.

New comments, mentions, activity and follow requests pop up as KDE notifications; "Open" goes straight to
the thread. Which lanes notify, and how much a notification tells, is set in `[notify]`:

```toml
[notify]
lanes = ["comments", "mentions", "requests"]
privacy = "full"     # "sender": only who, never the text; "count": only "3 new comments"
```

`privacy = "count"` is for screen sharing and open-plan offices: nothing readable leaves the
window. While fedtail is the active window it stays quiet (`when_focused = true` to change).

For the icon in the launcher and in notifications, install a menu entry once:

```sh
python3 -m fedtail --install-desktop          # or --profile work --install-desktop
```

## Writing

Pictures can be dropped onto the compose window (or onto the main window — that starts a new
post) and pasted with `Ctrl+V`, screenshots included. Double-click a picture to describe it.
The content warning field is hidden behind "⚠ Content warning" (`post.cw_field = true` to keep
it open).

## Keys

| | |
|---|---|
| `Ctrl+N` | new post |
| `Ctrl+Enter` | send |
| `F5` | refresh |
| `Alt+1…9` | switch lane |
| `Ctrl+W` | close tab |
| `Esc` | closes what's on top (picture, find bar); the last `Esc` takes the window off the screen at once |
| `Ctrl+F`, `F3`, `Shift+F3` | find in the lane / thread on screen (text, name, `@handle`, `#id`, alt text); "Deeper" searches everything stored for the lane |
| `Ctrl+Q` | quit (closing the window only hides it to the tray) |

## Development

```sh
python3 -m unittest discover -s tests -t .   # core tests need no display
ruff check .
```

How it's built and what comes next: [docs/DESIGN.md](docs/DESIGN.md) (in Russian for now).

## Who wrote it

The code, from the first line to the icon, is written by Claude (Anthropic), an AI. A human
came up with the idea, tested every build on his own fediverse node and reported what was
wrong. Commits carry a `Co-Authored-By: Claude` line.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
