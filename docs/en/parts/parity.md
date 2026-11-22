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
| The lanes as tiles on the curtain | ✓ | ✓ | ◐ | ✓ | ✓ | `window.tiles`: on the curtain (every lane closed) the lanes as tiles by the sidebar's sections, the lanes' list on the left stepping aside; on the phone it is its overview (`phone.overview`). The terminal is lines of text: its curtain (the common words, `common/sidebar.curtain`) draws no tiles, its sidebar is the list. |
| The messages window above others and its tabs (`window.roster_on_top`, `window.split_tabs`) | ✓ | — | · | · | · | Qt only: GTK 4 can't keep a window above others (the desktop decides that), and closing the messages window with its tabs is Qt's for now. Android: a desktop's window layout |
| Switching the account closes this window (`accounts.switch_closes`) | ✓ | ✓ | · | · | · | The terminal and the web page are one window: another account opens in it, there's nothing to keep both in. Android: one app, one account on screen, switched in place |

### Reading

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| A thread's keys: ] [ and − | ✓ | ✓ | ✓ | — | · | `]` / `[` — the next / previous top-level comment, `-` — fold the branch and unfold it again: in the Qt and GTK windows and the terminal, by one rule (common/postkeys). On the web page a thread opens at the side, and the keys' cursor (j / k) walks only the lane there — a thread has none yet; the phone needs none: it has no keyboard. Android: The phone has no keyboard. |
| The character count's tooltip | ✓ | ✓ | · | ✓ | ✓ | Every interface shows a post's character count (`card.char_count`); the tooltip "Characters in the post's text" under the mouse — the windows and the web page. The terminal and the phone have no mouse: the number stands alone. |
| Servers' emoji as pictures | ✓ | ✓ | · | ✓ | ✓ | The Qt and GTK windows and the web page draw :blobcat: as its picture — in posts, names, the boost's line, a quote and Activity. The terminal — text: a picture doesn't go into a line of text. |
| Tools over the post under the mouse | ✓ | ✓ | · | ✓ | · | ui.hover_tools: in the Qt and GTK windows and on the web page the post under the mouse has at its top right — open in the browser, copy the link, translate, quote, follow the thread, mute it, read up to here, and on my own one edit and delete; its ⋯ menu has them no more there. The terminal has no mouse — all of it in the post's menu. Android: a phone has no mouse: all of it in the card's ⋯ menu |
| A post's menu in submenus | ✓ | ✓ | ◐ | ✓ | — | ui.menu_groups: in the Qt and GTK windows and on the web page the ⋯ menu has the frequent items on top and the submenus "Author @…", "Thread", "More". The terminal's post menu is one list (the words are in the common code; it draws no submenus yet). Android: the phone's card menu is flat for now |
| Someone's older posts from their own server | ✓ | ✓ | ◐ | ✓ | ✓ | The web page as the windows: the page's addresses at once, the posts four at a time, a live “n of N” on the button. The terminal fetches a whole page with “more” and then says how many came — no live count. |
| The buttons under a post: pictures, words or both (`card.actions`), ✓ “read” (`reading.read_button`) | ✓ | ✓ | · | ✓ | — | The terminal has no buttons under a post: all is letters and the post's menu (“Mark read” is there). Android: a phone's row has room for pictures only; the words are in the ⋯ sheet |
| How long the line over a reply and the links are (`card.reply_context_chars`, `card.link_chars`), ~~struck~~ (`appearance.text_markup`) | ✓ | ✓ | ◐ | ✓ | ✓ | The terminal cuts the line over a reply to its own width, writes links whole (the terminal itself picks them out), and leaves struck text as written. |

### Pictures and video

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| A link to a video or sound file — into the own player | ✓ | ✓ | ✓ | · | ✓ | A link in a post's text to a .mp4, .webm, .mp3, .opus… (a server that didn't take a big attachment leaves it so) plays in the same player as attachments: over the window in Qt and GTK, mpv in the terminal, the phone's player on the phone (`media.links_in_player`). The web page needs none: the browser plays such a file itself. |
| The picture viewer: leaf through, 1:1, the original, save | ✓ | ✓ | ◐ | ◐ | ✓ | The terminal shows a picture full screen (chafa, kitty) and saves the original (`s`); the web page has its viewer with Save and 1:1. The window's words about Qt's formats and “the original is loading” aren't theirs. |
| Video and sound inside the program | ✓ | ✓ | ◐ | ◐ | ✓ | The terminal plays in mpv (a window, or in the terminal itself), the web page — in the browser's player. |
| The player's settings: decoding, gifs in a lane (`media.video_decode`, `media.gifv_max`, `media.gifv_fps`) | ✓ | — | · | · | · | These are Qt's player's (FFmpeg, Qt Multimedia). GTK plays through GStreamer, the web page in the browser's player, the terminal in mpv: they have decoders of their own, and three gifs loop at once, as Qt's default. Android: video plays in the system's player (ExoPlayer) |

### The editor

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| A picture's focus for previews | ✓ | ✓ | · | ✓ | ✓ | A terminal has nothing to click a picture with; the focus stays in the centre. |
| Formatting buttons in the editor | ✓ | ✓ | ◐ | ✓ | ✓ | post.format_bar: bold, italic, strikethrough, code, a link, a quote, a list — Markdown marks around the selection. In the terminal — by the buttons with the mouse only: Ctrl+B/I/K belong to the text field there (Ctrl+I is Tab). |
| Spell checking in the post window | ✓ | ✓ | ◐ | ◐ | ◐ | The windows underline mistakes and fix them with a right click; the terminal — as a list on F7 (its input has no underline); the web page — the browser's own checker in the post's language. Android: the phone's keyboard checks |
| The post's language from a list (`post.languages`, “Another language…”) | ✓ | ✓ | ◐ | ✓ | ✓ | In the terminal the language is a field: a code is typed (`en`, `ka`); empty — `post.language`. |

### The server, settings, help, debugging

| What | Qt | GTK | Terminal | Web | Android | Why |
|---|---|---|---|---|---|---|
| The sync folder — through the system's folder picker | · | · | · | · | ✓ | On a computer a program reaches any folder of its user: the path is typed into the field. Android 11+ lets an app into a shared folder (Syncthing) only through its own picker — there a “Choose a folder” button stands beside the field. |
| The settings window: search, restart, “open the file” | ✓ | ✓ | ◐ | ◐ | ✓ | The terminal and the web page edit the same config.toml with a form by chapters, with a search and “Open the file” (the terminal: in $EDITOR, the web page copies its path). No restart: they're restarted the way they were started; “the file changed outside” isn't needed — the place reads the file anew each time it opens. |
| Themes: try one | ✓ | ✓ | ◐ | ◐ | ◐ | The terminal has themes of its own (`tui.theme`). The web page takes the windows' themes' colours and font and tries them from the ≡ menu, but doesn't open the themes folder: the page is a guest in the browser. Android: the windows' themes' colours, fonts and pictures, “try” in the menu; the themes folder is shut, themes of your own come as a zip (≡ → “Add a theme from a file…”) |
| A theme as one file: out and in | ✓ | — | — | · | ✓ | GTK has no such items yet: the themes folder is open there, and the command line makes and takes the archive (`--theme-export`, `--theme-import`) — the same for the terminal. The web page is a guest in the browser: putting files into the themes folder isn't its to do. |
| Desktop notifications and testing them | ✓ | ✓ | ✓ | ✓ | ◐ | The terminal — through notify-send or the terminal's own code (kitty, WezTerm, foot…); the web page — the browser's notifications, if allowed. Android: Notifications go into the phone's shade, but there is no test one ("Debugging → Test a notification"): Android itself shows whether they are allowed |
| Debugging: a full snapshot into an archive, the log, the sound | ✓ | ✓ | ✓ | · | ◐ | The web page is a guest in a browser: a report is made in the window, the terminal or `fedtail --bug-report`. Android: The report — ⋮ → "Send a report" (the log inside); the phone has no sound — nothing to test |
| Tooltips and “What's this?” | ✓ | ✓ | · | ◐ | · | A terminal has no pointer to hover — its hints are in the key line at the bottom. The web page has tooltips on buttons, lanes and menu items; no “What's this?” mode (the browser shows a tooltip on hover anyway), and none for what the page doesn't have (editor size, tracing). Android: nothing to hover with |
| What shows the notifications (`notify.backend`: the desktop or the tray) | ✓ | ◐ | · | · | · | GTK shows them through the desktop (Gio, else notify-send): its tray icon (StatusNotifierItem) has no balloons. Android: a phone's notifications are its shade |
| Fonts of your own and their size (`appearance.fonts`, `font`, `mono_font`, `font_size`) | ✓ | ✓ | · | ✓ | — | The terminal writes in the terminal's own font and size. Android: the phone takes the theme's font, and the size from Android's settings |
| The buttons' pictures: the system's, the theme's or your own (`appearance.icons`) | ✓ | ✓ | · | — | ✓ | The web page draws its buttons as signs (↩ ★ ♻ 🔖): a browser can't see the desktop's icons. The terminal is text. |
| The window's hang watchdog (`debug.watchdog_seconds`, `debug.stall_ms`) | ✓ | ✓ | · | · | · | The watchdog minds the main loop of the Qt and GTK window; the terminal and the web page have no window that freezes that way. Android: Android itself watches an app for hangs (ANR) |
