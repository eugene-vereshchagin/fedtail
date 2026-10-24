## Four interfaces

fedtail is a Qt window (KDE, Windows), a GTK window (GNOME), a terminal and a web page; they share one core, and nearly everything is in all of them. Below is only what isn't everywhere, and why. ✓ — has it, ◐ — in part, — — no, · — doesn't belong there. A test keeps the table honest: a function that appears or goes in one interface doesn't pass without its line here.

### The window, accounts, logging in

| What | Qt | GTK | Terminal | Web | Why |
|---|---|---|---|---|---|
| Logging in | ✓ | ✓ | — | — | You log in in the window (Qt or GTK); the terminal and the web page open a profile already logged in and tell you to log in in the window. |
| Accounts: add, make main, log out | ✓ | ✓ | — | — | Profiles are added and switched in the window; the terminal and the web page work with the one they were started with (`--profile`). |
| Every account in one window | ✓ | ✓ | ◐ | ◐ | The terminal and the web page merge the lanes too (`ui.merge`), but have no switch in the menu and no “received by @…” mark on a post. |
| The tray icon | ✓ | ✓ | · | · | A terminal and a browser tab have no tray. |
| The curtain (Esc closes the lanes) | ✓ | ✓ | · | · | In the terminal and on the web page Esc steps back; there is nothing to close. |
| Lanes in columns | ✓ | ✓ | — | — | One lane at a time; columns are the window's. |
| The roster and the messages window, as in QIP (`ui.layout = "split"`) | ✓ | ✓ | — | — | The two-window layout is Qt's and GTK's only. |
| The lanes on the left in groups | ✓ | ✓ | ◐ | ◐ | The web page and the terminal list the lanes in one list — in the same order, but without the groups' headings and folding. |
| The order of the lists: up, down | ✓ | ✓ | — | — | Lists are moved in the window; the order is shared (sync), and the terminal and the web page keep it. |
| The server's announcements | ✓ | ✓ | — | — | The announcement banner is the window's only. |

### Reading

| What | Qt | GTK | Terminal | Web | Why |
|---|---|---|---|---|---|
| Find in a lane: deeper, in every lane | ✓ | ✓ | ◐ | ◐ | The terminal and the web page find in what's on screen; in the archive and in every lane — the window only. |
| Find: previous, close | ✓ | ✓ | ◐ | ✓ | In the terminal Ctrl+F finds forward only. |
| A thread's head: how many posts, every CW at once, Follow as a button | ✓ | ✓ | ◐ | ◐ | A thread is followed from a post's ⋯ menu; there is no count and no “open every CW”. |
| A lane's view: as talks, posts only, unread only, “to the new” | ✓ | ✓ | ◐ | ✓ | The terminal shows a lane post by post; the media filter and “posts only” are on `s`. |
| Voting in a poll | ✓ | ✓ | — | ✓ | The terminal shows that a post has a poll, but you vote in the window or on the web page. |
| A poll: results, refresh, how many people | ✓ | ✓ | — | ◐ | The web page shows the votes at the options, without “results” and “refresh”. |
| Someone's older posts from their own server | ✓ | ✓ | — | — | “▼ older still — from …” on a profile is the window's only. |
| A profile: counts, “since”, people you both follow, featured, moved | ✓ | ✓ | ◐ | ◐ | The terminal and the web page show a profile as lines, without these details of the head. |
| Changing my avatar and header | ✓ | ✓ | — | — | The name, the bio and the fields are edited everywhere; the pictures — in the window only. |
| A tag on my profile; dropping a tag lane | ✓ | ✓ | — | — | Following a tag and “to lanes” are everywhere; “on my profile” and “drop from the lanes” — in the window. |

### Pictures and video

| What | Qt | GTK | Terminal | Web | Why |
|---|---|---|---|---|---|
| The picture viewer: leaf through, 1:1, the original, save | ✓ | ✓ | ◐ | ◐ | The terminal shows a picture full screen (chafa, kitty) or on a screen of its own; the web page — in its viewer, with “open the original”. Saving — in the window (on the web page — the browser's own). |
| Video and sound inside the program | ✓ | ✓ | ◐ | ◐ | The terminal plays in mpv (a window, or in the terminal itself), the web page — in the browser's player. |

### The editor

| What | Qt | GTK | Terminal | Web | Why |
|---|---|---|---|---|---|
| A warning about a picture without a description | ✓ | ✓ | — | — | Only the window asks before sending. |
| A picture's focus for previews | ✓ | ✓ | — | — | The focus is set by clicking the picture — the window's. |
| Previewing a post | ✓ | ✓ | — | — | How a post will look — in the window only. |
| The editor: “discard”, another language, the #CamelCase hint | ✓ | ✓ | — | — | A draft is kept everywhere; discarding with a question, typing a language not in the list and the accessibility hint — in the window. |

### The server, settings, help, debugging

| What | Qt | GTK | Terminal | Web | Why |
|---|---|---|---|---|---|
| “What the server can do” — the capability check | ✓ | ✓ | — | — | The federation's state is everywhere; the check of a score of capabilities is a tab of the window. |
| The federation's state: copy, refresh, reset | ✓ | ✓ | ◐ | ◐ | The terminal and the web page show the state, without the buttons. |
| What notifications to hold back (the server's policy) | ✓ | ✓ | — | — | What's held back shows everywhere; the policy itself is changed in the window. |
| The arts mode: its mark in the menu | ✓ | ✓ | — | — | `ui.arts_mode` works everywhere; the reminder of it is in the window's menu. |
| The settings window: search, restart, “open the file” | ✓ | ✓ | ◐ | ◐ | The terminal and the web page edit the same config.toml with a form by chapters; there's no search, no restart button and no “open the file”. |
| Themes: try one, the themes folder | ✓ | ✓ | ◐ | — | The terminal has themes of its own (`tui.theme`); the web page knows no themes yet. |
| Open the config and the data folder | ✓ | ✓ | — | · | The terminal prints the paths (≡ → “Debugging”); the web page has no access to the machine's files. |
| Help: search, back, forward | ✓ | ✓ | ◐ | ◐ | The help opens everywhere and its links work; there's no search and no history. |
| About: copy the information | ✓ | ✓ | — | — | The same information; no “copy” button — the text can be selected. |
| Desktop notifications and testing them | ✓ | ✓ | — | ◐ | The terminal tells by a sound (`tui.sound`); the web page — by the browser's notifications, if allowed. |
| Debugging: the log, a report, the sound, the stacks | ✓ | ✓ | ✓ | — | The web page is a guest in a browser: a report is made in the window, the terminal or `fedtail --bug-report`. |
| Memory debugging: census, snapshot, tracing, giving memory back | ✓ | ✓ | — | — | Leak hunting is the window's, where leaks happen. |
| Tooltips and “What's this?” | ✓ | ✓ | · | ◐ | A terminal has no pointer to hover — its hints are in the key line at the bottom; the web page has tooltips on some buttons. |
