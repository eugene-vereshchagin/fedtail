# fedtail's alpha test

Thanks for trying it. fedtail is an early version: things will break, and that's fine;
what matters is that every breakage leaves a trace to fix it by.

## Installing

The simplest — one file from a [release](https://github.com/eugene-vereshchagin/fedtail/releases): `fedtail-…-linux-x86_64` (`chmod +x`, run it)
or `fedtail-…-windows.exe`. To update — download a newer file.

From the source on Windows — [windows.md](windows.md) (Python, git, running, tests, the self-check).

From the source, Debian 13 (trixie), KDE or any other desktop:

```sh
sudo apt install python3-pyside6.qtwidgets python3-pyside6.qtdbus python3-requests \
    qt6-image-formats-plugins libnotify-bin fonts-noto-color-emoji
git clone https://github.com/eugene-vereshchagin/fedtail.git
cd fedtail
python3 -m fedtail                      # the first start: the server's address → logging in in the browser
python3 -m fedtail --install-desktop    # a menu entry and an icon (if you want them)
```

To update: `git pull`, then `python3 -m fedtail --update-config` — it adds the new
settings with explanations to the config (your values aren't touched), and restart the program.

Any server with the Mastodon API will do: GoToSocial, Mastodon, Akkoma, Friendica. Log in with
an ordinary account, not the admin one.

## What to look at first

- **Threads.** Open a discussion (the "Thread" button or a click on a post's time): it's a tree,
  numbered `/1 /2 …`, whole — and replies your server never got come in
  a couple of seconds later. The same thread opened from different places should look the same.
- **Nothing gets lost.** Close the lanes with Esc, leave the program overnight — in the morning the
  counters are on the left, the new things wait unread, a lane opens where you stopped.
- **Replies to me, thread subscriptions** (the "Follow" button above a thread, `S #abc` on
  the command line): replies in your threads come even if you weren't mentioned.
- **Notifications**: the ≡ menu → "Debugging" → "Test a notification".
- **The command line** at the bottom (`Ctrl+L`, `?` — help), as on Point.
- **Several accounts**: a right click on your own avatar.
- **Themes**: `appearance.theme` in the config (≡ → "Open the config"), the list is in its explanation.
- **A day without a restart.** Leave the window overnight — send the log in the morning: it has
  `trend` lines and, if something leaks, `possible leak`. How to set up a serious leak hunt
  (memory tracing, snapshots) — [debugging.md](debugging.md#an-overnight-run-hunting-leaks).

## Found a problem

1. Say it in a few words: what you did, what you expected, what you got. A screenshot helps a lot.
2. Attach the log: the `latest.log` file from the logs folder (the ≡ menu → "Debugging" → "Open the logs folder";
   usually `~/.local/share/fedtail/default/logs/`).
   A one-file build from a release doesn't write the detailed log: set `debug.mode = "on"` in the
   config (or start it with `--debug`) and repeat.
   If the program was restarted already — the files are in the same place, by the date and hour in the name.
   Or in one archive: `python3 -m fedtail --bug-report` — it appears in your home folder.
3. The window hung — first `kill -USR1 <pid>` (the pid is in the log), then send.

The log has no token and no post texts: only request addresses, post ids, times and errors.
The `--bug-report` archive takes neither the token nor the database. The config goes into it — check
there's nothing in it you don't want to share.
