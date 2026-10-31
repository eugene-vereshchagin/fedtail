## Five interfaces

fedtail is a Qt window (KDE, Windows), a GTK window (GNOME), a terminal, a web page and an Android app; they share one core. Below is only what isn't everywhere, and why. ✓ — has it, ◐ — in part, — — no, · — doesn't belong there. A test keeps the table honest: a function that appears or goes in one of the desktop interfaces doesn't pass without its line here; the phone has screens and words of its own — its column is checked against its code by hand, and all the phone lacks so far is in the next chapter.

### The window, accounts, logging in

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| Pinned tabs | ✓ | ✓ | · | · | · | ui.pin_tabs: right-click a thread's or a profile's tab. The terminal, the web page and the phone have no such tabs — a thread and a profile open over the lane and go with "back". Android: No tabs: screens stack, "back" is the one before. |
| The tray icon | ✓ | ✓ | · | · | · | A terminal and a browser tab have no tray. Android: a phone has no tray |
| The curtain (Esc closes the lanes) | ✓ | ✓ | · | · | · | In the terminal and on the web page Esc steps back; there is nothing to close. The curtain is there at start (`window.start_lane = "none"`), Enter opens the last lane. Android: a phone has no Esc |
| Lanes in columns | ✓ | ✓ | · | ✓ | ✓ | The terminal — one lane at a time. The web page — columns by ❯, as the windows' (at a phone's width, one lane); the phone — on a tablet (the overview, a lane, a thread side by side). |
| The roster and the messages window, as in QIP (`window.layout = "split"`) | ✓ | ✓ | · | · | · | The two-window layout is Qt's and GTK's only. Android: a desktop's window layout |

### Reading

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| Servers' emoji as pictures | ✓ | ✓ | · | ✓ | ✓ | The Qt and GTK windows and the web page draw :blobcat: as its picture — in posts, names, the boost's line, a quote and Activity. The terminal — text: a picture doesn't go into a line of text. |
| Someone's older posts from their own server | ✓ | ✓ | ◐ | ✓ | ✓ | The web page as the windows: the page's addresses at once, the posts four at a time, a live “n of N” on the button. The terminal fetches a whole page with “more” and then says how many came — no live count. |

### Pictures and video

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| A link to a video or sound file — into the own player | ✓ | ✓ | ✓ | · | ✓ | A link in a post's text to a .mp4, .webm, .mp3, .opus… (a server that didn't take a big attachment leaves it so) plays in the same player as attachments: over the window in Qt and GTK, mpv in the terminal, the phone's player on the phone (`media.links_in_player`). The web page needs none: the browser plays such a file itself. |
| The picture viewer: leaf through, 1:1, the original, save | ✓ | ✓ | ◐ | ◐ | ✓ | The terminal shows a picture full screen (chafa, kitty) and saves the original (`s`); the web page has its viewer with Save and 1:1. The window's words about Qt's formats and “the original is loading” aren't theirs. |
| Video and sound inside the program | ✓ | ✓ | ◐ | ◐ | ✓ | The terminal plays in mpv (a window, or in the terminal itself), the web page — in the browser's player. |

### The editor

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| A picture's focus for previews | ✓ | ✓ | · | ✓ | ✓ | A terminal has nothing to click a picture with; the focus stays in the centre. |
| Formatting buttons in the editor | ✓ | ✓ | ◐ | ✓ | ✓ | post.format_bar: bold, italic, strikethrough, code, a link, a quote, a list — Markdown marks around the selection. In the terminal — by the buttons with the mouse only: Ctrl+B/I/K belong to the text field there (Ctrl+I is Tab). |
| Spell checking in the post window | ✓ | ✓ | ◐ | ◐ | ◐ | The windows underline mistakes and fix them with a right click; the terminal — as a list on F7 (its input has no underline); the web page — the browser's own checker in the post's language. Android: the phone's keyboard checks |

### The server, settings, help, debugging

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| The settings window: search, restart, “open the file” | ✓ | ✓ | ◐ | ◐ | ✓ | The terminal and the web page edit the same config.toml with a form by chapters, with a search and “Open the file” (the terminal: in $EDITOR, the web page copies its path). No restart: they're restarted the way they were started; “the file changed outside” isn't needed — the place reads the file anew each time it opens. |
| Themes: try one | ✓ | ✓ | ◐ | ◐ | ◐ | The terminal has themes of its own (`tui.theme`). The web page takes the windows' themes' colours and font and tries them from the ≡ menu, but doesn't open the themes folder: the page is a guest in the browser. Android: the windows' themes' colours, fonts and pictures, “try” in the menu; no themes folder |
| A notification taken back once its posts are read | — | — | — | — | ✓ | The phone takes a lane's note out of the shade once nothing is unread there — read there, on another device or by the server's marker: the shade keeps a note till it is tapped. The desktop's and the browser's notifications go by themselves in a few seconds. |
| Debugging: a full snapshot into an archive, the log, the sound | ✓ | ✓ | ✓ | · | ✓ | The web page is a guest in a browser: a report is made in the window, the terminal or `fedtail --bug-report`. |
| Tooltips and “What's this?” | ✓ | ✓ | · | ◐ | · | A terminal has no pointer to hover — its hints are in the key line at the bottom. The web page has tooltips on buttons, lanes and menu items; no “What's this?” mode (the browser shows a tooltip on hover anyway), and none for what the page doesn't have (editor size, tracing). Android: nothing to hover with |
