# fedtail

*`tail -f` for the fediverse.* A desktop client for GoToSocial, Mastodon, Akkoma and anything
else that speaks the Mastodon API — made for people who remember Juick and Point.im and are
tired of reading scraps of other people's conversations.

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

## Notifications

New comments, mentions and follow requests pop up as KDE notifications; "Open" goes straight to
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
| `Ctrl+Q` | quit (closing the window only hides it to the tray) |

## Development

```sh
python3 -m unittest discover -s tests -t .   # core tests need no display
ruff check .
```

How it's built and what comes next: [docs/DESIGN.md](docs/DESIGN.md) (in Russian for now).

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
