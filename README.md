# fedtail

[![CI](https://github.com/eugene-vereshchagin/fedtail/actions/workflows/ci.yml/badge.svg)](https://github.com/eugene-vereshchagin/fedtail/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/eugene-vereshchagin/fedtail)](https://github.com/eugene-vereshchagin/fedtail/releases)
[![License: GPL v3+](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

*`tail -f` for the fediverse.* A desktop client for GoToSocial, Mastodon, Akkoma and anything
else that speaks the Mastodon API — made for people who remember Juick and Point.im and are
tired of reading scraps of other people's conversations.

It is for people who are sick of hunting for where a reply came from and what the conversation
was even about — who get pulled away from work by a toot and come back with no idea what was
being discussed. So the whole point is giving that context back: every reply shows what it
answers; under someone's comment you see what you said back; a thread opens as a tree right
where you came from; a lane remembers where you stopped and never jumps.

**Download:** one file, nothing to install — [the latest release](https://github.com/eugene-vereshchagin/fedtail/releases/latest): `fedtail-…-linux-x86_64` for Linux, `fedtail-…-windows.exe` for Windows ([how](#one-file-no-installing)); for Debian 13 and the like, `fedtail_…_all.deb` — `sudo apt install ./fedtail_…_all.deb` brings Qt from Debian and puts fedtail in the menu. Or [run it from the source](#running-from-source).

[Русскоязычная версия](README.ru.md)

> **Status: public beta.** Used every day by its author on GoToSocial; Mastodon, Akkoma and
> Friendica work through the same API. Linux (Debian 13 and newer) first, Windows on trial.
> Found a bug? [Open an issue](https://github.com/eugene-vereshchagin/fedtail/issues) with `latest.log` — see
> [docs/TESTING.md](docs/TESTING.md).

**Contents**

- *Start:* [What's different](#whats-different) · [For Juick and Point.im people](#for-juick-and-pointim-people) · [One file, no installing](#one-file-no-installing) · [Running from source](#running-from-source) · [Accounts, profiles and files](#accounts-profiles-and-files)
- *Reading:* [Lanes](#lanes) · [Posts](#posts) · [Lists](#lists) · [Finding people and tags](#finding-people-and-tags) · [Command line, like on Point](#command-line-like-on-point) · [In the terminal](#in-the-terminal) · [In a browser](#in-a-browser) · [Silence](#silence) · [Links stay inside](#links-stay-inside) · [Honest counters and readable hashtags](#honest-counters-and-readable-hashtags) · [Notifications](#notifications)
- *Writing and you:* [Writing](#writing) · [Your profile](#your-profile) · [Themes](#themes) · [Keys](#keys)
- *More:* [If it breaks](#if-it-breaks) · [Development](#development) · [Who wrote it](#who-wrote-it) · [License](#license)

![A thread as a tree, in the default theme](https://raw.githubusercontent.com/eugene-vereshchagin/fedtail/screenshots/light-thread.png)

## What's different

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

## For Juick and Point.im people

fedtail aims to feel like Point on top of the fediverse: you read the feed in order and never
lose your place; every comment shows the thread it belongs to; threads are trees numbered
`/1 /2 …`, whole — replies your server never got are fetched from the author's server;
thread subscriptions (like `S #abc` on Point) and a command line: `#abc text`, `S #abc`,
`@user`; private by default. Trying it out: [docs/TESTING.md](docs/TESTING.md).

## One file, no installing

Every [release](https://github.com/eugene-vereshchagin/fedtail/releases) has fedtail as a single file with Python and Qt inside:

* **Linux** (x86-64; Debian 12 and newer, Ubuntu 22.04 and newer, and the like):
  `fedtail-X.Y.Z-linux-x86_64` — `chmod +x` it and run. `--install-desktop` adds it to the
  menu with its icon.
* **Windows** (10 and 11): `fedtail-X.Y.Z-windows.exe` — run it. `--install-desktop` adds a
  Start menu shortcut. The config lives in `%APPDATA%\fedtail\<profile>\`, the data in
  `%LOCALAPPDATA%\fedtail\<profile>\`; notifications come through the tray icon. Windows
  warns about an unknown app the first time (the file isn't signed): "More info" → "Run anyway".

The file unpacks itself on start, so the first window takes a few seconds. Everything else is
the same as running from the source — the same config, profiles and logs.

## Running from source

Debian 13 (trixie) or newer:

```sh
sudo apt install python3-pyside6.qtwidgets python3-pyside6.qtdbus python3-requests \
    qt6-image-formats-plugins
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

On Windows from the source: the same, with `pip install requests PySide6-Essentials` and
`python -m fedtail`. To build the one-file version yourself: `pip install pyinstaller` and
`python3 packaging/build.py` (it lands in `dist/`).

On first start fedtail asks for your server, opens the login page in the browser and waits
for the code the server shows you.

## Accounts, profiles and files

An account is a profile: its own config (so its own theme), its own data, its own window.

```sh
python3 -m fedtail                        # profile "default"
python3 -m fedtail --profile croco        # another account (the first time: the login window)
python3 -m fedtail --profiles             # which profiles there are, and who they are
python3 -m fedtail --install-desktop --profile croco   # a menu entry of its own
python3 -m fedtail -c ~/my.toml -d ~/fd/  # explicit config file and data dir
```

In the window, right-click your avatar (or ≡ → Accounts): the other accounts are listed;
pick one and its window opens with its theme, this one closes (`ui.switch_closes = false`
keeps both). "Add an account…" asks for a profile name and opens the login window.

Or all accounts in one window (the same menu, "All accounts in one window", or
`ui.merge = ["all"]`): lanes of the same name become one (both Homes are one Home), the
other accounts' lists come as lanes of their own, and a post another account received
says so — "→ @work"; a reply, a like or a boost goes from that account. New posts, the
command line, likes & boosts and follow requests are the main account's.

| what | where |
|---|---|
| config (read-only for the app) | `~/.config/fedtail/<profile>/config.toml` |
| token, mode 0600 | `~/.local/share/fedtail/<profile>/auth.json` |
| cache, read marks, drafts | `~/.local/share/fedtail/<profile>/state.db` |
| images | `~/.local/share/fedtail/<profile>/cache/` |

The config is created on first run as a copy of
[`fedtail/data/config.example.toml`](fedtail/data/config.example.toml) — in chapters (look &
window, reading, lanes, posts, notifications…), every option set to its default with an
explanation, so an editor colours it — and never touched again. A value written there stays
yours even if a later version changes the default; comment it out (or delete it) to follow
the program's default. `config.example.toml` next to it is always the full reference for the
running version. When an update brings new options, fedtail says so at start, and
`python3 -m fedtail --update-config` adds them to your file in the right sections, refreshes the
explanations of the options already there and drops commented-out ones that are gone (a `.bak`
copy is kept; your values and notes stay). `python3 -m fedtail --rebuild-config` lays the
file out anew in the current chapters with your values in place (your own comments don't
survive that; the `.bak` does).

## Themes

The look is a theme file. Built in:

- `system` — light or dark, whatever KDE uses: every colour comes from the desktop palette;
- `terminal` — green on black, monospace, posts divided by lines, buttons in words.
- `juick` — juick.com around 2013: a light warm-grey page, white posts, blue links.
- `juick-classic` — juick.com around 2011: an olive page, beige posts, brown-orange links.
- `bnw` — bnw.im: a black frame, grey posts on white, all monospace, bright green buttons.
- `point` — point.im as it is today: a white page, posts divided by thin lines, Open Sans.
- `night` — dark, with its own colours, on any desktop.
- `contrast` — for weak eyes: big type, black on white, firm lines.
- `pink` — powder rose and berry links, soft corners, little flowers.
- `nord` — the arctic palette: cold blue-grey, frosty links, dark.
- `solarized` — Solarized light: warm paper, blue links.
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

New posts arrive at once: the server's live stream wakes fedtail the moment something comes,
and the regular poll (`poll.interval_seconds`) fetches it — so a dropped stream (a laptop
asleep, a proxy) loses nothing. `poll.stream = "off"`: polling only.

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

Over every lane, **All | Posts | New** picks what to show (New: what was unread when you opened
the lane, staying put while you read it). **Feed | Conversations** over Replies to me, Mentions
and Subscriptions: Conversations shows a thread's replies as one card — where it started, how
many messages and how many new, who wrote last; a click opens the whole thread.

## Posts

A post shows what's in it the way its server meant: the server's own emoji (`:blobcat:`) as
pictures; a link as the page's card (site, title, a line of description, its picture); a quote
(Mastodon 4.5+, Akkoma, Misskey) as the quoted post framed inside, or a line saying why it
can't be shown. Each is a switch in `[feed]`: `custom_emoji`, `link_cards`, `quotes`.

Where you stopped reading is shared with your other clients (`read.sync_markers`): Home and
mentions read on the phone are read here too, and the other way round — as far as the other
client tells the server (Mastodon web, Ivory, Phanpy do; Tusky keeps Home's place to itself
and shares only the notifications). Your own posts are read here whatever wrote them.

Someone from another server your server knows little about: their profile fills in with their
newest public posts read from their own server, and their followers and follows can be read
from there too (`feed.remote_profiles`, `feed.remote_people`) — ActivityPub requests without
your token, like completing threads.

Several pictures in a post come each whole, in its own shape; `ui.media_grid = "square"` lays
them out as even squares cut around the focus point their author set.

A picture's description (alt text) shows on hover; `ui.alt_text = "caption"` also puts it
under the pictures. Sending a picture without one asks first — describe it or send as is
(`post.alt_reminder`).

## Lists

Your server's lists (Mastodon, GoToSocial) appear as lanes in a block of their own under the
main ones. Right-click a post (or its ⋯ menu) → "Add to list" ticks its author into any list
or a new one; right-click a list for rename, delete and **exclusive**. Whoever you put in a
list is read there and leaves the general lanes — Home, Bots, Local, Federated — with their
boosts and other people's boosts of their posts: sort the bots into "Memes", "News" and the
rest, and Home is people again. `lists.hide_members = "exclusive"` keeps that to exclusive
lists, `"off"` to nothing. `[lists]` in the config.

### A morning "global": relay bots

The fediverse has relay bots: follow one and it boosts, to all its followers, the posts of
whoever follows it (often by language — Russian-speaking ones, say, set up when people moved
over from Twitter). The result is a random but living circle of people, without the noise of
the real Federated lane. Such bots land in the Bots lane, which then works as a hand-picked
global one.

To read it apart: make a list ("Morning", say), put the relays in it (right-click a boost of
theirs → "Add to list") and make it exclusive — they leave Bots and Home for a lane of their
own, for the morning coffee. Someone who came that way is worth following: follow them from
their profile (click the name in the boost). The filter next to Refresh does the opposite
too: untick "Boosts" to see people's own posts only.

## Finding people and tags

The search box under Write (`Ctrl+K`) finds people by name, `@user@server` or a profile link,
hashtags and posts — with Follow right in the results; tags can be followed too (their posts
come to Home). A profile shows whom the person follows and who follows them, each with a
Follow button: the easiest way to find more people is through people you already read.

## Command line, like on Point

At the bottom of the window (`Ctrl+L`): `#a3f` opens a post, `#a3f text` replies, `#a3f/2 text`
answers comment /2 of its thread, `S #a3f` / `U #a3f` subscribe to a thread or leave it,
`S @user` / `U @user` follow or unfollow, `! #a3f` boosts, `~ #a3f` bookmarks, `D #a3f`
deletes your post, `@user` opens a profile, `@user text` writes to them directly, plain text
is a new post, `?` shows it all. While you type it says what Enter will do — which post a reply
goes to and who will see it. `↑` `↓` bring back earlier commands.

## In the terminal

The same profile without the window — over ssh, in a script, in a pipe:

```
fedtail lanes                         # the lanes and how much is unread in each
fedtail show comments -n 20           # the newest posts of a lane (--unread, --mark-read)
fedtail tail comments mentions        # new posts as they arrive, until Ctrl+C
fedtail post "text"                   # a new post; "-" or no text: read it from stdin
fedtail post --reply a3f "text"       # a reply to #a3f (#a3f/2: to comment /2)
fedtail read comments                 # mark a lane read
fedtail -p work show people           # another profile
```

Lists go by their title (`fedtail show Friends`). It shares the database and the read marks
with the window, so it works with the window open. Colour only on a terminal (`NO_COLOR` is
respected); `[cli]` in the config: `color`, `max_lines`, `tail_lanes`, and `enabled = false`
to turn the commands off.

The whole interface in a terminal: `fedtail --ui tui` (or `ui.frontend = "tui"`) — lanes on the
left, posts with what they answer, threads as trees, the same command line at the bottom. Keys:
`j` / `k`, `Enter` — the thread, `r` — reply, `f` — like, `b` — boost, `m` — bookmark, `n` — a
new post, `p` — the author's profile (`F` there follows), `x` — the lane read, `Tab` — lanes / posts, `Esc` — back, `q` — quit. It needs
[Textual](https://textual.textualize.io/): `sudo apt install python3-textual` on Debian 13, or
`pip install textual`. `[tui]` in the config: `theme`, `lanes_width`, `show_context`.

## In a browser

`fedtail --ui web` (or `ui.frontend = "web"`) runs fedtail as a page in your browser: lanes,
posts with what they answer, threads, profiles, writing and the command line, live updates, the
same read marks; `j` / `k`, `r`, `f`, `b`, `m`, `p`, `x`, `Enter`, `Esc` as in the window. It
needs nothing beyond Python. At start it prints a link with a key (and opens it): the key is
kept in the profile's data folder (`web.key` — delete it for a new one). `[web]` in the config:
`host` (`"127.0.0.1"` — this computer only; `"0.0.0.0"` — a phone on your home network too,
unencrypted, so only there), `port`, `open_browser`.

## Silence

A post's ⋯ menu (or the profile) mutes or blocks its author: their posts vanish from every
lane at once. ≡ → Silence… keeps word filters on your server — "fold" shows a post folded with
a note, "hide" drops it — and lists who you muted or blocked, with undo.

## Links stay inside

@mentions open the person's profile in a tab (bio, fields, "follows you", Follow, Mention,
Add to list), #hashtags open the tag's timeline, links to posts and profiles on other servers
are looked up through your server and open as a thread or a profile — the browser only gets
what fedtail can't find. `ui.links_in_app = false` sends everything to the browser.

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

A profile also shows what its owner puts forward: the tags they feature and the people they
recommend (`feed.profile_featured`).

## Notifications

**Activity** is a lane of its own: who favourited or boosted your posts and who followed you,
gathered per post ("Kot, Arsen and 3 more — ★ favourited «…»"). `[activity] types` picks the
kinds.

New comments, mentions, activity and follow requests pop up as KDE notifications (in the tray
on Windows); "Open" goes straight to the thread. Home and the lists stay quiet unless asked.
Which lanes notify, and how much a notification tells, is set in `[notify]`:

```toml
[notify]
lanes = ["comments", "mentions", "requests", "list:Friends"]   # one list by its title
privacy = "full"     # "sender": only who, never the text; "count": only "3 new comments"
```

`privacy = "count"` is for screen sharing and open-plan offices: nothing readable leaves the
window. A lane you're looking at doesn't notify about itself (`when_focused = true` to change).

For the icon in the launcher and in notifications, install a menu entry once:

```sh
python3 -m fedtail --install-desktop          # or --profile work --install-desktop
```

Filtered notifications (Mastodon 4.3+ holds back mentions from strangers, new accounts and
the like): ≡ → Filtered notifications… shows who is waiting — let them through or dismiss —
and what to hold back. `notify.filtered`: `"remind"` also says at start that someone waits,
`"menu"` only the menu item, `"off"` neither.

Server announcements (what the admins post: updates, rules, maintenance) come as a strip
above the lanes until "Got it" — the server remembers that for its web interface and other
apps too. `ui.announcements = "off"` hides them.

## Writing

A new post opens as a panel in the middle of the window (`ui.compose = "window"` for a separate
window). `@na` and `#ta` complete as you type — people and tags seen in the lanes first, then what the
server finds (`post.complete_mentions`, `post.complete_tags`); `:bl` offers the server's own
emoji (`post.complete_emoji`). Pictures can be dropped onto it (or onto the main window — that starts a new post) and pasted with `Ctrl+V`, screenshots included. Double-click a picture to describe it and, with a click on it, set its focus point — the part
a cropped preview keeps (`post.focus_point`).
The content warning field is hidden behind "⚠ Content warning" (`post.cw_field = true` to keep
it open).

## Keys

| | |
|---|---|
| `S` (in the picture viewer) | save the picture to Downloads (`ui.save_dir`); also a right click on a picture |
| `Ctrl+K` | search people, tags, posts |
| `Ctrl+N` | new post |
| `Ctrl+Enter` | send |
| `F5` | refresh |
| `Alt+1…9` | switch lane |
| `Ctrl+W` | close tab |
| `Esc` | closes what's on top (picture, find bar); the last `Esc` closes every lane behind a curtain — nothing is marked read, new posts pile up for later (`ui.esc = "tray"` hides the window instead) |
| `Ctrl+F`, `F3`, `Shift+F3` | find in the lane / thread on screen (text, name, `@handle`, `#id`, alt text); "Deeper" searches everything stored for the lane |
| `Ctrl+Q` | quit (closing the window only hides it to the tray) |

## Development

```sh
python3 -m unittest discover -s tests -t .   # core tests need no display
ruff check .
```

* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how it is built: modules, threads, the store,
  lanes, the poll cycle, events, the Qt frontend, themes, config, tests, recipes.
* [docs/DEBUGGING.md](docs/DEBUGGING.md) — the logs, and what to send when it breaks.
* [docs/FEATURES.md](docs/FEATURES.md) — what fedtail does and doesn't, next to other clients,
  with the config switch for each (Russian tables, English summary).
* [docs/CONFIG.md](docs/CONFIG.md) — every config option in tables by chapter, with its
  default (Russian; built from `config.example.toml` by `tools/config_doc.py`).
* [docs/DESIGN.md](docs/DESIGN.md) — the spec and the queue of planned work (Russian).
* [AGENTS.md](AGENTS.md) — the rules in one page, for coding agents and humans in a hurry.
* [CONTRIBUTING.md](CONTRIBUTING.md) — reporting bugs, proposing changes, running the tests.

## If it breaks

The debugging mode (`debug.mode`: on by itself in development versions from git, off in
releases and the one-file builds; `--debug` for one run) keeps logs in the profile's data folder, `logs/` (the menu opens it), a file per start
and per hour, `latest.log` the current one (`debug.log_dir`). Attach `latest.log`, or run
`python3 -m fedtail --bug-report` and send the archive it makes in your home folder — logs,
crash traces, config and a system summary, without the token and the database. A frozen
window: `kill -USR1 <pid>` first, it writes where every thread is stuck. Details in
[docs/DEBUGGING.md](docs/DEBUGGING.md).

## Who wrote it

The code, from the first line to the icon, is written by Claude (Anthropic), an AI. A human
came up with the idea, tested every build on his own fediverse node and reported what was
wrong. Commits carry a `Co-Authored-By: Claude` line.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
