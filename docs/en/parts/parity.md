## Four interfaces

fedtail is a Qt window (KDE, Windows), a GTK window (GNOME), a terminal and a web page; they share one core, and nearly everything is in all of them. Below is only what isn't everywhere, and why. ✓ — has it, ◐ — in part, — — no, · — doesn't belong there. A test keeps the table honest: a function that appears or goes in one interface doesn't pass without its line here.

### The window, accounts, logging in

| What | Qt | GTK | Terminal | Web | Why |
|---|---|---|---|---|---|
| Logging in | ✓ | ✓ | — | — | You log in in the window (Qt or GTK); the terminal and the web page open a profile already logged in and tell you to log in in the window. |
| Accounts: add, make main, log out | ✓ | ✓ | — | — | Profiles are added and switched in the window; the terminal and the web page work with the one they were started with (`--profile`). |
| The tray icon | ✓ | ✓ | · | · | A terminal and a browser tab have no tray. |
| The curtain (Esc closes the lanes) | ✓ | ✓ | · | · | In the terminal and on the web page Esc steps back; there is nothing to close. |
| Lanes in columns | ✓ | ✓ | — | — | One lane at a time; columns are the window's. |
| The roster and the messages window, as in QIP (`ui.layout = "split"`) | ✓ | ✓ | — | — | The two-window layout is Qt's and GTK's only. |

### Reading

| What | Qt | GTK | Terminal | Web | Why |
|---|---|---|---|---|---|
| Someone's older posts from their own server | ✓ | ✓ | ◐ | ◐ | They come page by page with a “more” button at the bottom, without a live “n of N” count. |

### Pictures and video

| What | Qt | GTK | Terminal | Web | Why |
|---|---|---|---|---|---|
| The picture viewer: leaf through, 1:1, the original, save | ✓ | ✓ | ◐ | ◐ | The terminal shows a picture full screen (chafa, kitty) and saves the original (`s`); the web page has its viewer with Save and 1:1. The window's words about Qt's formats and “the original is loading” aren't theirs. |
| Video and sound inside the program | ✓ | ✓ | ◐ | ◐ | The terminal plays in mpv (a window, or in the terminal itself), the web page — in the browser's player. |

### The editor

| What | Qt | GTK | Terminal | Web | Why |
|---|---|---|---|---|---|
| A picture's focus for previews | ✓ | ✓ | — | ✓ | A terminal has nothing to click a picture with; the focus stays in the centre. |

### The server, settings, help, debugging

| What | Qt | GTK | Terminal | Web | Why |
|---|---|---|---|---|---|
| The settings window: search, restart, “open the file” | ✓ | ✓ | ◐ | ◐ | The terminal and the web page edit the same config.toml with a form by chapters, with a search and “Open the file” (the terminal: in $EDITOR, the web page copies its path). No restart: they're restarted the way they were started; “the file changed outside” isn't needed — the place reads the file anew each time it opens. |
| Themes: try one, the themes folder | ✓ | ✓ | ◐ | ◐ | The terminal has themes of its own (`tui.theme`). The web page takes the windows' themes' colours and font and tries them from the ≡ menu, but doesn't open the themes folder: the page is a guest in the browser. |
| Open the config and the data folder | ✓ | ✓ | ✓ | · | The terminal opens the config in $EDITOR and copies the paths (≡ → “Debugging”); the web page has no access to the machine's files. |
| Debugging: the log, a report, the sound, the stacks | ✓ | ✓ | ✓ | — | The web page is a guest in a browser: a report is made in the window, the terminal or `fedtail --bug-report`. |
| Memory debugging: census, snapshot, tracing, giving memory back | ✓ | ✓ | ✓ | — | Leak hunting is the windows' and the terminal's; the web page is a guest in a browser. |
| Tooltips and “What's this?” | ✓ | ✓ | · | ◐ | A terminal has no pointer to hover — its hints are in the key line at the bottom; the web page has tooltips on some buttons. |
