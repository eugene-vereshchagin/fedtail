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
- **One profile = one account = one window.** `fedtail --profile work` runs another account.

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

Squares instead of emoji and flags mean there is no colour emoji font:
`sudo apt install fonts-noto-color-emoji`.

Anywhere else with Python ≥ 3.11: `pip install requests PySide6-Essentials`, then the same.

On first start fedtail asks for your server, opens the login page in the browser and waits
for the code the server shows you.

## Profiles and files

```sh
fedtail                        # profile "default"
fedtail --profile croco        # another account
fedtail -c ~/my.toml -d ~/fd/  # explicit config file and data dir
```

| what | where |
|---|---|
| config (read-only for the app) | `~/.config/fedtail/<profile>/config.toml` |
| token, mode 0600 | `~/.local/share/fedtail/<profile>/auth.json` |
| cache, read marks, drafts | `~/.local/share/fedtail/<profile>/state.db` |
| images | `~/.local/share/fedtail/<profile>/cache/` |

The config is created on first run as a fully commented copy of
[`fedtail/data/config.example.toml`](fedtail/data/config.example.toml) and never touched again.

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
