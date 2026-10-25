## Five interfaces

fedtail is a Qt window (KDE, Windows), a GTK window (GNOME), a terminal, a web page and an Android app; they share one core. Below is only what isn't everywhere, and why. ✓ — has it, ◐ — in part, — — no, · — doesn't belong there. A test keeps the table honest: a function that appears or goes in one of the desktop interfaces doesn't pass without its line here; the phone has screens and words of its own — its column is checked against its code by hand, and all the phone lacks so far is in the next chapter.

### The window, accounts, logging in

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| Logging in | ✓ | ✓ | ◐ | ◐ | ✓ | The terminal and the web page log in the same way: the server's address, the login page in a browser, the code. The web page itself won't start for a profile not logged in — you log in from another profile's page. |
| The tray icon | ✓ | ✓ | · | · | · | A terminal and a browser tab have no tray. Android: a phone has no tray |
| The curtain (Esc closes the lanes) | ✓ | ✓ | · | · | · | In the terminal and on the web page Esc steps back; there is nothing to close. Android: a phone has no Esc |
| Lanes in columns | ✓ | ✓ | · | · | ✓ | One lane at a time; columns are the window's and the tablet's (the overview, a lane, a thread side by side). |
| The roster and the messages window, as in QIP (`ui.layout = "split"`) | ✓ | ✓ | · | · | · | The two-window layout is Qt's and GTK's only. Android: a desktop's window layout |

### Reading

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| Someone's older posts from their own server | ✓ | ✓ | ◐ | ◐ | ✓ | They come page by page with a “more” button at the bottom, without a live “n of N” count. |

### Pictures and video

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| The picture viewer: leaf through, 1:1, the original, save | ✓ | ✓ | ◐ | ◐ | ✓ | The terminal shows a picture full screen (chafa, kitty) and saves the original (`s`); the web page has its viewer with Save and 1:1. The window's words about Qt's formats and “the original is loading” aren't theirs. |
| Video and sound inside the program | ✓ | ✓ | ◐ | ◐ | ✓ | The terminal plays in mpv (a window, or in the terminal itself), the web page — in the browser's player. |

### The editor

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| A picture's focus for previews | ✓ | ✓ | · | ✓ | ✓ | A terminal has nothing to click a picture with; the focus stays in the centre. |
| Spell checking in the post window | ✓ | ✓ | ◐ | ◐ | ◐ | The windows underline mistakes and fix them with a right click; the terminal — as a list on F7 (its input has no underline); the web page — the browser's own checker in the post's language. Android: the phone's keyboard checks |

### The server, settings, help, debugging

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| The settings window: search, restart, “open the file” | ✓ | ✓ | ◐ | ◐ | ✓ | The terminal and the web page edit the same config.toml with a form by chapters, with a search and “Open the file” (the terminal: in $EDITOR, the web page copies its path). No restart: they're restarted the way they were started; “the file changed outside” isn't needed — the place reads the file anew each time it opens. |
| Themes: try one, the themes folder | ✓ | ✓ | ◐ | ◐ | ◐ | The terminal has themes of its own (`tui.theme`). The web page takes the windows' themes' colours and font and tries them from the ≡ menu, but doesn't open the themes folder: the page is a guest in the browser. Android: the windows' themes' colours, fonts and pictures, “try” in the menu; no themes folder |
| Open the config and the data folder | ✓ | ✓ | ✓ | · | ◐ | The terminal opens the config in $EDITOR and copies the paths (≡ → “Debugging”); the web page has no access to the machine's files. Android: the config is edited in the app; no data folder |
| Debugging: the log, a report, the sound, the stacks | ✓ | ✓ | ✓ | · | ✓ | The web page is a guest in a browser: a report is made in the window, the terminal or `fedtail --bug-report`. |
| Memory debugging: census, snapshot, tracing, giving memory back | ✓ | ✓ | ✓ | · | · | Leak hunting is the windows' and the terminal's; the web page is a guest in a browser. Android: a desktop tool |
| Tooltips and “What's this?” | ✓ | ✓ | · | ◐ | · | A terminal has no pointer to hover — its hints are in the key line at the bottom. The web page has tooltips on buttons, lanes and menu items; no “What's this?” mode (the browser shows a tooltip on hover anyway), and none for what the page doesn't have (column width, editor size, tracing). Android: nothing to hover with |
