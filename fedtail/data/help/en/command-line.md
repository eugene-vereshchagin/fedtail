# The command line

As on Point: Ctrl+L and the commands.

## Commands

| Command | What it does |
|---|---|
| `#a3f` | open the post |
| `#a3f text` | reply to the post |
| `#a3f/2 text` | reply to comment /2 of its thread |
| `#a3f @who text` | call someone into the thread |
| `S #a3f` / `U #a3f` | subscribe to the thread / unsubscribe |
| `S @nick` / `U @nick` | follow a person / unfollow |
| `! #a3f` | boost |
| `~ #a3f` | bookmark |
| `D #a3f` | delete your own post (asks first) |
| `@nick` | open the profile |
| `@nick text` | a direct message |
| plain text | a new post |
| `?` | the list of commands |

While you type, the right end says what Enter will do: which post the reply goes to and who
sees it. ↑ ↓ — earlier commands. A click on a post's `#id` puts it at the start of the line.
`post.plain_posts = false` — commands only, so stray text never goes out as a post.

## In a terminal

The same profile without a window — over ssh, in a script, in a pipe:

```
fedtail lanes                     # lanes and what's unread
fedtail show replies -n 20        # a lane's latest posts
fedtail tail replies mentions     # the new as it comes
fedtail post "text"               # a new post
fedtail post --reply a3f "text"   # a reply
fedtail read replies              # mark a lane read
```

`fedtail --ui tui` — the whole interface in a terminal, `fedtail --ui web` — in a browser tab.

In detail → [Interfaces](ref/features.md#interfaces) · [terminal settings](ref/config.md#16-in-a-terminal)
