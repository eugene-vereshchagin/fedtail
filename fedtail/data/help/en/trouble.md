# If it breaks

Logs, a bug report, the federation status.

## Logs and the report

- ≡ → "Debugging" → "Open the logs folder". The one to send is `latest.log`, a link to the
  current log.
- ≡ → "Debugging" → "Make a report for diagnosis" (or `fedtail --bug-report`) — an archive of two
  days: logs, crash traces, the config and system details. No token, no database.
- Report a bug on [GitHub](https://github.com/eugene-vereshchagin/fedtail/issues) — attach
  `latest.log` or the archive.

The detailed log is on in development versions and off in releases; `--debug` turns it on for
one run.

## Logging in: a saved password doesn't work

Seen on a phone with GoToSocial: the server's sign-in page opens in the browser, and a
password filled in by a password manager or pasted from the clipboard is refused — only one
typed by hand from scratch gets in. Why is not known yet. The way round: type the password.
It is needed once: after that fedtail keeps a token, not the password.

## Federation status

≡ → "Debugging" → "Federation status…": how your server is doing, how many requests and with
which errors, polling and the live stream, what the server can't do, who waits to go into a
list — and what keeps failing on other servers, with what it most likely means. "Copy" — as text
for an issue.

## Frozen, memory leaking

- The window froze — `kill -USR1 <pid>`: `stacks.log` gets where every thread is stuck.
- Memory grows — ≡ → "Debugging" → "What grows: stats and object census now". For a night,
  turn memory tracing on, make a "Memory snapshot" in the morning and send it.

In detail → [The application](ref/features.md#the-application) · [Logs and debugging](ref/config.md#debug)
