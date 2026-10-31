# Changelog

## 0.22.1 — in progress

- **Logging in on the phone, in one go.** The code the browser brings back is no longer
  lost when the phone closed the app meanwhile (or when it comes before the app is up):
  the login begun waits on disk (`login.json`, an hour, never in a bug report). A wrong
  server is said under the button — not a snackbar hidden by the keyboard — and a site
  that isn't a fediverse server is said so, not "HTTP 404". The button says it opens the
  browser; the keyboard's "Go" logs in; "logging in…" while the token comes.
- **Sync: a new device no longer marks the others' lanes read.** Its first run marks
  everything it fetched read (as it should, there), but the snapshot it sent on joining
  — and every packed journal — carried those marks too, so the desktop's custom lanes
  went read when the phone came. Only the marks a person made (here or on another
  device) travel now; the store keeps them apart (`read_shared`).
- **Phone: the reply editor tidied.** The post answered stands in a box of its own, six
  lines of it in sight; a longer one says so ("Show it all · quote") and opens whole,
  where a piece is selected to quote. Who sees the reply is shown chosen (the core's
  pick, as the post answered) instead of no chip lit. The formatting buttons are a row
  under the text: a column beside it (post.format_bar "left"/"right", the desktop's)
  took a third of the screen.
- A round's timing in the log is the round's own: a lane count made after a read mark
  (another thread) took the round's slow request for itself — "warm lanes 21.77 s" was
  a server answering in 20 s.
- Markers (where reading stopped, shared with other clients) wait 10 s, not 30: a server
  stuck on them once an hour held the whole round.
- A picture of a few dozen bytes is called a server's stub in the log, not a format a
  missing plugin would read.
- Phone: `read.dwell_ms` is heeded (it was a fixed 350 ms), as in the windows.
- Docs (sync): the lanes' counts may be off for the first minutes of a newly joined
  device, until the other devices' read marks have come in — and why.

## 0.22.0 — 2026-10-30

**In short.**

<!-- For the site's builder (an agent): this release goes out together with fedtail-sync
     0.22.0, the sync server — its first release of its own, in its own repository:
     https://github.com/eugene-vereshchagin/fedtail-syncserver/releases/tag/v0.22.0
     (assets: fedtail_sync.py, PROTOCOL.md, SHA256SUMS; its notes are its CHANGELOG.md's
     0.22.0). Say so on the release's page and wherever the site tells how to set up sync
     (docs/<lang>/sync.md): the server is downloaded from that repository now, not from
     fedtail's. One number for both; protocol 2 (an older client stops: update both). -->

- **The lane editor builds a condition from its parts** — no syntax, no service words to
  remember — in every interface, the phone's too.
- **"Writing lanes"**, a guide in the docs and in the help: every key and every word,
  with examples.
- **"In a thread I wrote in"** works for threads not followed too.
- **Federated and Local fill themselves** with older pages when the languages filter left
  them a few posts.
- **The funnel** ("only video") over something rare asks several pages at once.
- **"Comments"** (was "Commented posts"), as on Point: every thread you took part in, a
  card a thread, those with new comments together past the "new below" line.
- **A comment is `#post/N`**, as on Point: the number given once and kept; the command
  line takes `#post/N text`.
- **A thread's card**: "14 comments · 1 new · bob: “…”" — the whole thread counted, the
  theme's own thread picture before it.
- **Following a thread by an act**: a boost, a like, a bookmark, a quote, a vote.
- **My answer shows in the open thread** at once, in every interface.
- **Refresh says how it went**: "Updated: 3 new", "nothing new", "Not updated: …", "the
  server asks to wait".
- **A click on a tag** in a post shows that author's posts with the tag, as on Point.
- **The post under the mouse** lights its buttons, as on point.im.
- **Sync without logging in**: through a fedtail-sync server (an invite code) or a WebDAV
  folder (Nextcloud, ownCloud, a NAS).
- **The next device's key is a QR code.**
- **fedtail-sync in a repository of its own**, released with fedtail under one number:
  [fedtail-sync 0.22.0](https://github.com/eugene-vereshchagin/fedtail-syncserver/releases/tag/v0.22.0)
  — one file, `fedtail_sync.py` (the standard library only, Python 3.11+), protocol 2.
- **The Qt and GTK windows build only the cards near the screen**: the window's memory on
  a synthetic day 325 → 227 MB.
- **No more freezes** on marking read, on opening a lane, on writing to the database.
- **The web page**: columns, replies, pictures through fedtail itself, servers' emoji in
  names; checked in Chromium by a CI job of its own.
- **"Report a bug"** in every interface; the report's archive carries the night in short:
  the memory as smem says it before and after reading, the freezes, the errors.
- **Formatting buttons** in the editor: B, I, S, code, a link.
- **Debian packages one per interface**: GNOME pulls no Qt, KDE no GTK; from the apt
  repository as before, `sudo apt install fedtail`.

Everything:

- A bug report carries `summary.md`, the night in short — leave the client on, read in
  the morning, send the report: the memory as smem says it (USS / PSS / RSS) at the
  start, lowest, highest and last, and at "reading began" / "reading ended" (the core
  notes them by the read marks), the freezes, the rounds, warnings and errors.
- A dismissed announcement no longer comes back when a round asked the server before the
  dismissal reached it.
- A hung first copy no longer keeps fedtail from starting: its window silent for
  `window.hung_copy_seconds` (20), it answers the new start "hung", is ended (asked, then
  made to) and the new one takes its place.
- A lane's `me = "in_my_thread"` works — it never matched (its set was never filled) — and
  for threads not followed too: from the store, a post of mine above or a top I wrote
  under.
- A rare one, off by default (no button even): `people.watch_replies` — a profile's
  "Follow replies to all their posts": their latest posts' threads followed at once,
  each new post's as the round brings it — who answers a bot of yours.
- A link in a post to a video or sound file (…/clip.mp4 — what a server leaves when it
  didn't take a big attachment) plays in the own player, as an attachment: Qt, GTK, the
  terminal's mpv, the phone's player (`media.links_in_player`); it went to the browser.
- `threads.auto` takes my acts on someone's post too: `"boosts"`, `"likes"`, `"bookmarks"`,
  `"quotes"`, `"votes"` — its thread followed, news from then on. Off by default.
- A thread card's line is short and draws in any font: "14 comments · 1 new · bob: “…”"
  (it was "💬 14 messages in the conversation, new: 1 · the last — …", the 💬 a box where
  the font lacked it); it opens with the theme's own "thread" picture in Qt, GTK and on
  the web page.
- A comment is `#post/N`, as on Point: on every card (Home, To me, the thread) its post's
  #id and its number, given once and kept — not a #id of its own, as if it were a post.
  The thread's /N no longer move when a reply comes in between (they were the places in
  the tree). `threads.comment_ids = "own"` — as before.
- Refresh says how it went: "Updated: 3 new", "nothing new", "Not updated: …" or "the
  server asks to wait — updating at 14:20" — a press that brought nothing looked like a
  button doing nothing. The web page reads its lanes once the round is over (it read
  them before it began); the phone too.
- A clip its server called a picture is no longer downloaded whole (36 MB) to be told
  "can't show this format": the answer's type says video, nothing is read.
- Marking read no longer makes the window count every lane itself (330 ms): the core
  counts them in a thread of its own and says `counts_ready`; Qt, GTK and the terminal
  draw the sidebar's numbers on it. A module read at the first lane click (460 ms on a
  cold disk) is read at the start.
- The funnel ("only video") with something rare: "Older" and the lane's end in sight asked
  one page and the lane grew by a post or two; now pages on, up to
  `lanes.funnel_fill_pages` (5), till some ten pass it. A browse lane fills itself so too.
- A thread's card says how many comments the whole thread has, as fedtail's own check of
  it found — not only those that came after you followed it.
- "Commented posts" is "Comments" now. In fedtail's set it shows every thread you took
  part in (your post, your comment, one you follow), those with new comments together
  where reading starts, past the "new below" line — "read below" when the newest come
  first (`threads_shown = "all"`, a new key of a lane's rule; "new", as before, in the
  extra set). The lane editor has it as "Which threads".
<!-- For the site's builder (an agent): from this release the Debian tab must change.
     fedtail_<v>_all.deb is now a meta-package and does NOT install alone. The release
     carries fedtail-common_<v>_all.deb (the program), fedtail-qt_, fedtail-gtk_,
     fedtail-tui_<v>_all.deb (each a toolkit) and fedtail_<v>_all.deb (common + Qt or GTK).
     Download by hand: `sudo apt install ./fedtail_<v>_all.deb ./fedtail-common_<v>_all.deb
     ./fedtail-qt_<v>_all.deb` (KDE and the rest), or `./fedtail-common_<v>_all.deb
     ./fedtail-gtk_<v>_all.deb` (GNOME, no Qt); `./fedtail-tui_<v>_all.deb` adds the
     terminal. From the apt repository nothing changes: `sudo apt install fedtail`
     (or fedtail-gtk on GNOME). Link every .deb of the release, not only fedtail_. -->
- Debian packages one per interface: `fedtail-common` (the program, no toolkit),
  `fedtail-qt`, `fedtail-gtk`, `fedtail-tui`, and `fedtail` (common and a window, Qt or
  GTK) — GNOME no longer pulls Qt, KDE no GTK, a server only requests. An old `fedtail`
  is replaced cleanly. `ui.frontend = "auto"`, the new default: the window installed —
  Qt, else GTK, else the terminal (started in one) or the browser.
- The READMEs say fedtail in numbers: lines of each part, tests, coverage
  (`tools/stats.py`, written by the night's self-check).
- The network gone: a round stops at the first "no way to the server" instead of asking
  every source in turn, each failure said to the user; it is said once an outage, and the
  rounds wait longer each time (as for a server down) till it answers again. A dead RSS
  site or another server's lane stops nothing.
- "Writing lanes" (`docs/<lang>/lanes.md`, in the help too): how a lane's rule is built,
  every key of a lane and of a condition, every word each takes, examples — the words
  generated from the program's own, a test fails on one left unexplained.
- A lane says which quick filters stand over it: `switches = ["posts_only", "unread_only"]`
  in `[[lanes.custom]]` and the presets (the editor's "Switches"); none said — as
  before. The built-in sets name theirs.
- Federated and Local: a lane the languages filter left short of a page asks pages older
  by itself while open (`lanes.browse_fill_pages`, 5) and keeps them — it showed one post
  of two hundred. Where one opens: `lanes.browse_start` — "last" (where you stood; that
  place gone from the store — the first post of the last `browse_start_hours`), "hours",
  "newest". Decided once for every interface (common/lane.py).
- The languages filter: a post's links, @names, #tags and :emoji: no longer count when its
  language is told — a Japanese post with a link had more Latin letters than Japanese
  ones, its own "ja" was taken for a lie, the language came out unknown and it passed a
  "ru only" lane.
- A post changed anywhere else — edited, liked, boosted — is shown changed at once in
  the terminal (it heard of no change it hadn't made itself) and, its words, in the GTK
  window (an edit stayed old there; only the counters moved).
- Web page: a column counts a card read only once it stayed seen `reading.dwell_ms`, as
  the lane does — it marked it the moment it showed, however fast it went by. The phone:
  the booster's emoji in the "boosted by" line as pictures.
- A server's emoji (:blobcat:) as pictures in the GTK window — in posts, names, the boost's
  line, quotes and Activity: it showed them as text everywhere (Pango puts no picture in a
  line; the text block keeps a square for each and draws the picture there). Qt draws
  them in Activity's names too, the phone in Activity's names and a quote's author.
- Web page: the thread open beside grows by itself — someone's answer that a round
  brings, my own answer sent from another place; it stayed as it was opened (the page
  now follows the server's thread count, as the phone does).
- Terminal: a post read anywhere else (another window, the phone, another device
  through sync) loses its ● in the lane on screen at once; the terminal never heard of
  read marks it hadn't made itself till the lane was drawn anew.
- GTK and the web page: a quote is shown once — the server's "RE: <link>" line for clients
  without quotes stood in the text over the quote fedtail drew; Qt alone took it out.
  Decided once now (`cardtext.shown_text`). GTK has a test of quotes of its own.
- A quote that quotes too gets one line under it, "❝ quotes Bob's post", a link to that
  thread — as Mastodon's own page does, never a card in a card (Mastodon gives that level
  as an id only). Decided once (`cardtext.inner_quote_bit`), drawn by every interface;
  that level showed nothing before.
- `window.message_percent`: how long passing messages stay (the status line, pop-ups), in
  per cent of the usual — one setting for some forty of them in every interface (200 —
  twice as long).
- A profile's fields: as many as the server takes (GoToSocial and Akkoma say how many;
  Mastodon keeps 4), in every interface. The terminal's, the web page's and the phone's
  editor cut them at 4, and a fifth one was gone once the profile was saved.
- The server's announcements are asked again by the core, every
  `server.announcements_minutes` (30; 0 — only at the start), for every interface — the
  Qt and GTK windows each kept a timer of their own; `announcements_updated` tells them.
- More options out of the code: `post.autosave_ms` (one delay for the windows: Qt kept
  700 ms, GTK 1500), `card.link_chars` (where a bare link's text is cut; 0 — never),
  `media.gifv_max` and `media.gifv_fps` (gifvs looping at once in the Qt window, their
  frames a second).
- One reading rule in every interface: what is on screen counts once the feed has stood
  `reading.dwell_ms` (350; the windows and the web page had 350, 400 and 250 ms), and a
  window out of focus counts only while scrolled by hand and `reading.unfocused_seconds`
  after (5) — Qt did so, GTK never counted one, the web page always did (its columns even
  in a hidden tab).
- Numbers that were nailed into the code are options now, each read in one place for every
  interface: `threads.thread_recheck_for_minutes` (30), `lanes.extra_posts` (20),
  `lanes.rss_items` (60) and `rss_summary_chars` (1200), `people.following_max` (1000:
  the mutuals and the rules' "followed" — wrong for those following more),
  `people.search_limit` (20), `activity.names_shown` (3), `notify.max_lines` (3),
  `notify.seconds` (the desktop's), `card.thread_indent_max` (8),
  `card.reply_context_chars` (160), `card.mute_tags_shown` (3), `window.default_columns`
  (4).
- How deep a thread's posts indent is one number for every interface (the model's): the
  phone stopped at 6 levels, the others at 8; the reply's context line is as long in Qt
  as elsewhere (140 → 160 characters).
- Lighter core: python3-langdetect is loaded only when a guess is wanted — each Activity row
  guessed its post's language for rules that never asked, loading all of it (the core
  alone 110 → 52 MB; the Qt window on a synthetic day 325 → 227 MB, within the goal of
  150–250). When it is wanted, only its Latin and Cyrillic profiles, as 4-byte
  floats: 60 → 11 MB, the same answers (`lanes.detect_among = "all"` — every one).
  Telugu, Kannada, Malayalam, Gujarati and Punjabi are told by their script now.
- Web page: its own errors (a script's, an unhandled promise) go into fedtail's log as
  `web page error:` lines with their stack — they stayed in a browser's console nobody
  looks at. Addresses lose their query, at most 20 a load.
- Qt: notifications name fedtail's desktop entry (`online.dmesg.fedtail`, a profile's own
  for another profile): they said "fedtail", an entry that doesn't exist, so the desktop
  showed them without the app's icon and outside its group in the notification settings.
- Web page: a reply starts as the core says — who sees it (`post.reply_never_wider`) and
  its warning (`post.reply_warning`), as in the windows and on the phone. The page
  narrowed it and copied the warning by a rule of its own, whatever the config said.
- My answer shows in the open thread at once — in the Qt and GTK windows and the
  terminal (the web page did already); so does a round's new answer in GTK and the
  terminal (Qt alone had a rule of its own for it). The core decides which opened
  thread an answer belongs to — any post shown in it knows its root — and says
  `thread_grew`; the interfaces only reload the thread they show.
- Web page: the card a lane opens on stays where it stood while pictures come in — in
  one lane and in every column. A picture whose size the server didn't say, emoji,
  link cards pushed it off the screen; it is held till the reader moves (wheel, touch,
  a click, a key) or six seconds pass. `tools/web_check.py` checks it in Chromium.
- Web page: a server's emoji in a name show as pictures in Activity's rows too, as on a
  card — they stood as `:blob:`. Each event row carries its people's emoji
  (`EventParts.emojis`), for the windows to use as well.
- The terminal keeps a server's custom emoji and pictures stored on S3 in the picture
  cache: they come as `application/octet-stream`, and only `image/*` was kept, so they
  were downloaded again at every look. Whether a file is a whole picture is told by its
  bytes now, the same check for every interface (`core/imagesniff.py`).
- Qt: the ≡ menu's Debugging and People submenus, and a list's "whose replies" in its
  lane menu, could open empty or vanish: made by `addMenu(title)`, they were Python's
  and went with the code that built them before the menu showed (PySide6 6.8). Each is
  made with its parent menu now.
- GTK: the ≡ menu didn't open at all — it still looked for the memory-tracing toggle
  the one Debugging submenu took out.
- The terminal plays video and gifs right in itself, a console player, when it shows real
  pictures (sixel in Konsole, kitty) — `tui.video = "auto"` opened mpv's window over it on
  a desktop. mpv's status line (time, length, a bar) under the picture, its messages kept
  to errors; space, the arrows, q back to the lanes.
- A post read once is read everywhere: reading a boost marks its post read too, and a boost
  counts read when its post is — as itself in another lane, or as someone else's boost. Each
  was read by its own id: the same post stood unread in the next lane, interface or device
  (sync carries both ids now).
- One profile open in several processes at once (the window in the tray, the terminal, the
  web page): what one marks read the others see as read. Each kept the read marks in
  memory, the table read once a run, and posts read in the window and the browser stayed
  unread in the terminal; the store now notices another process's commit (SQLite's
  `data_version`) and reads the marks again (`Store.others_wrote`).
- The terminal shows real pictures (sixel in Konsole, WezTerm, foot; kitty's protocol) out
  of the box: fedtail carries textual-image (LGPL-3, not in Debian) in `fedtail/_vendor/`,
  the PyPI wheel as it is, its checksum checked (`_vendor/VENDORED.toml`); a copy
  installed in the system or by pip wins. `tools/vendor.py --check` says when PyPI has a
  newer one — every night in CI (`vendor.yml`, job `vendored`); `--update` brings it in.
- Qt: FFmpeg's errors are quiet too — "[h264] Failed setup for format vdpau…" at every
  video, though it plays; a video that won't play is Qt's error, in the log.
- Qt: FFmpeg (behind the video player and the looping gifs) says only its errors: a gif of an
  old pixel format flooded the terminal with "[swscaler] deprecated pixel format used",
  a line every frame. Every player is made by one function that quiets it (Qt resets the
  level as its plugin loads); `FEDTAIL_FFMPEG_LOG=1` lets FFmpeg say everything.
- Qt: a closed tab lets its cards go the lanes' way (hidden, deleted); its card dict swapped
  for an empty one left them standing, owned by no one, until the tab was deleted — what
  the lanes' sweep of unowned cards kept finding in the tests.
- The post under the mouse lit, as on point.im (`card.additional_highlight`, on): its buttons
  brighter, and on my own post ✎ and ✕ at the top right (the menu's Edit and Delete). Every
  theme; Qt, GTK and the web page, the terminal tints the post under the mouse.
- A click on a tag in a post opens that author's posts with the tag, as on Point where each
  blog has its own tags (`card.tag_click = "author"`; `"everywhere"` — the tag's lane as
  before): "#tag everywhere" and the author's profile on top; a right click on a tag offers
  both and muting it (Qt, GTK). The link names the post's author (`fedtail:tag/<tag>
  by:<id>`); the place is common (`places._author_tag`), so the terminal, the web page and
  the phone have it too.
- The numbers under the posts on screen are kept fresh (`card.counts_minutes`, 5): every
  interface and the phone say which posts they show, and the round asks my server again
  for them in one request (`GET /api/v1/statuses?id[]=`, one by one where it can't); with
  `honest_counters` the authors' servers too. Only a post's row of buttons is redrawn. A
  followed thread whose post shows more replies is checked at the next round, so
  "Commented posts" learns of new comments at once (`core/counts.py`). A lane kept each
  post as it came, its numbers of that moment, mostly none.
- Requests (to follow me, to answer, to boost) are a row each, with whose they are: 62 follow
  requests were glued into one row — three names "and 59 more" over 62 pairs of buttons
  that didn't say whose. Every interface and the phone (`common/activity.groups`).
- Qt: any empty stretch on screen (40 px and more, the gaps between cards aside) counts as a
  hole in a lane — one card's room left blank at the lane's end too, not only a screen
  mostly empty; said in the log with what stands where, and mended.
- The web page's lane counts are circles coloured as the windows' (it showed bare
  numbers). The colour is the lane's rule's, `badge = "hot" | "quiet"` (feeds.md §4) — the
  windows kept it by the lanes' names, twice; now one rule for every interface.
- Qt: a layout inside a layout left the cards at the old places. The body's new size
  moved the scroll, the scroll built cards and laid the lane out again inside the first
  call — which then put every card back at its own, older places: all of them drawn a
  card lower than they stood, a post's height of nothing above them and under the last
  post (the hole check's log: drawn at 90327, its place 88346). The outer layout stops
  when an inner one has done the work.
- GTK, the terminal, the phone: the card a lane opens on is held there too while the
  pictures come in, as on the web page — GTK by the card's bottom (an offset from its
  height then went stale when its own picture came), the terminal and the phone till the
  reader moves (10 s at most); where it stood is said only once it stands.
- Web: the card a lane opens on is held where it stands while the pictures above it come
  in — they pushed it down, and the page showed posts five back, older and read, at every
  opening and every switch of lanes; where it stood is said only once it stands (it
  crept up into the read ones too). Held till the reader moves; `tools/web_check.py`
  checks it with slow pictures.
- The ≡ menu, shorter, in every interface: debugging is in one submenu — "A full snapshot
  into an archive" (the threads' stacks, the stats, the census of objects and widgets, the
  memory snapshot when tracing is on, then the logs, the config and the system: one archive,
  `diag.full_snapshot`), the log, the federation status, testing a notification and the
  sound, "Report a bug on GitHub…". Gone from the menu: the stacks, the census, giving
  memory back, memory tracing (`debug.tracemalloc`) and its snapshot — the full snapshot
  does them — and opening the config, themes, data and logs folders (the config: from
  Settings).
- Qt: the hole check looks at what is drawn, not at the places as they should be — a card
  hidden or left where it stood is a blank; said in the log with each card's real place,
  and mended (shown again, put back). Cards waiting to be built with nothing building
  them are said and built. The blank under the last post after a new one came said
  nothing in the log.
- A follow request waiting stands among the events by when it came (when fedtail first
  saw it: the API gives no time of it) — it took the account's creation date ("asks to
  follow you · 9 Oct 2024") and stood on top of a lane read oldest first, its "followed
  you" at the bottom. Waiting, it stays new till answered, and a lane of posts keeps it
  though it is older than the posts shown.
- The window froze for 21 s, the disk busy: the commit that crossed SQLite's 1000 WAL
  pages checkpointed the database itself, fsync and all, and it was the window's (a
  lane's place saved). The WAL is checkpointed by the store's own thread now
  (`wal_autocheckpoint = 0`), and the interfaces' small states (`set_state`) are written
  by it a moment later, seen at once.
- Web: custom emoji in names are drawn (the page had the server's `name_html` and showed
  the plain name); a picture is taken by its bytes, not by the type its server names —
  emoji kept on S3 come as `application/octet-stream` and stood as `:code:`.
- Web: my answer shows in the thread open beside as it is sent (the thread is drawn
  again, the screen on it); before, only after opening the thread anew.
- Web: ✎ ✕ of my own post stand in the head's row, before the #code and the time — they
  covered both; the bar's columns and full-width buttons are drawn alike, one size.
- The place a lane opens at is the last card seen whole at the bottom of the screen —
  what was read last — and it opens there, at the bottom (on top when new posts came
  under it). It was the card on top: opened on top, the one above peeked in and was taken
  next time, and the place crept up into old read posts with every opening, in every
  interface.
- A lane read to its end opens as ever — at "new below" or its end: the place kept was the
  card on top of the screen there, 5–10 posts back, and the lane opened on it.
- Qt: a card on the lane that the lane doesn't own goes, said in the log; a card built
  twice keeps one; the same card twice in a lane takes one place (`LaneModel` shows each
  once) — two posts were drawn in one place, a post's height of nothing above them.
- A lane opens where you stood in it last, in whatever interface: the window, GTK, the
  terminal, the web page and the phone each say which card was read last once
  the scroll stands (`LaneModel.stood`, the state `stood.<lane>`), and every one opens the
  lane there (`reading.start_at = "first_unread"`; the first unread only when the place is
  gone). Each opened it at its first unread before: a post jumped over or folded away in
  the window, which kept its place in memory for days in the tray, sent the terminal and
  the web page days back.
- The terminal and the web page open on the curtain too (`window.start_lane = "none"`):
  the opossum, what piles up, Enter opens the last lane — the words the windows' own
  (`common/sidebar.curtain`). They opened the lane of last time instead.
- The terminal says in its log how many posts on screen have a picture, and aloud (once)
  when a picture came but this Pillow can't read it — "no pictures" was silent then.
- Qt: a lane whose screen stands empty with cards to show there builds them, not only
  says so in the log (the log line now tells the scroll's maximum, the hidden cards and
  the target too).
- "Report a bug on GitHub" opens the page again: the address held up to 7500 characters of
  the report, too long for KDE's opener, which then opened nothing. Now it holds the start,
  the whole text goes on the clipboard (the page says to paste it where it was cut), and
  if no browser comes the window says so and copies the address. A link Qt can't open is
  tried with the desktop's opener (`xdg-open`) and said when that fails too.
- Qt: a lane no longer smears on a refresh. A card made again kept its old body on screen
  till the event loop deleted it — two rows of buttons, an old picture over the next card;
  every widget that goes is now hidden at once (`qt/gone.py`). New counts of likes and
  boosts make only the row of buttons again, not the whole card: no pictures loading anew,
  no 0.5 s freeze on each refresh of a lane of pictures.
- The terminal says how its pictures are drawn (textual-image, chafa, half blocks or none, and
  why): in the log at start and in `tools/tui_check.py`'s notes, with a sample drawn; chafa
  failing is a warning once in the log, not a silent fall back to half blocks.
- The terminal: with chafa installed the pictures in the lane and in the app's picture
  view are chafa's (true colour, its many glyph shapes) — installing it changed nothing
  there before, only the v viewer used it; our half blocks without it.
- The web page counts a post read by the windows' rule (`common/lane.py` seen()): one
  taller than the screen once its end has been in view, and what the screen went past in
  a scroll — "90% of it in view" kept tall posts unread for good, and posts scrolled
  through stayed unread (16 of Home in the check): the next opening started days back.
  Pictures keep their place before they come (their size from the server). The same
  "went past in a scroll" in the terminal.
- A lane's line says what lanes.languages took out ("ru only: 39 posts in other languages
  hidden") and that a browse lane is still loading — a lane of one post of forty had
  explained nothing (every interface: the line is the common one).
- `post.reply_warning`: a reply starts with the post's warning ("copy", as Mastodon's own
  page, the default) or with none ("none").
- The terminal: a lane builds the rows near where reading stands, more as the cursor
  comes near an end — a lane of thousands of posts built every row at once; find and
  J look through the whole lane. What scrolled over the screen is read, as in the
  windows, not only the post under the cursor (posts read with the wheel stayed unread,
  and the next start offered a score of them). A post says what it holds ("video — v",
  "pictures — v"), and with no chafa / timg / kitty the pictures are coarse blocks: the
  terminal says once to install chafa; `--check` lists it.
- The web page shows every picture through fedtail itself (`/pic`: the windows' disk
  cache, fetched the checked way when missing): some servers give their pictures to no
  other site, and the browser asked them itself — avatars stayed grey; the browser no
  longer tells other servers who looks either (`img-src 'self'`).
- The web page: ↔, the posts across the whole width or in a column of `ui.max_width`,
  the same remembered state as the windows' (the column was 760 px, always); "▲ earlier"
  no longer stuck at "loading…" when the core didn't ask for a page — nothing older came.
- Fixed (Qt): a gap above the last post of a lane (or one card over another) for 15–30 s,
  till the lane's next refresh: a card whose height changed without saying so (a picture
  in, a warning opened) kept its old place, and a lane opened among tall pictures could
  stop laying its places out before they agreed. The cards on screen are measured again
  once the screen stands still, and the last round of places is never left undone.
- Fixed (Qt, GTK): a one-line field of a window's place (≡ → Sync's address and invite
  code, a filter's words, a list's name…) had its words only as grey text inside it, so
  an empty one looked switched off; its words are above it now, as every other field's
  (the terminal, the web page and the phone had them already). And a field to type in
  has a frame of its own in every theme (`field`, `field_border` — "auto": a good way
  from the view's colour towards the text's), not a card's pale one; one switched off
  looks so (greyed, a dashed frame).
- Much smoother, the GTK window: a lane is one strip of places with only the cards near
  the screen built (as Qt's, the same code: `common/strip.py`), a few at a time between
  frames — no more laying out every card at each scroll step nor waiting at the edge of
  what was built (in the bench, turns over 100 ms while scrolling 421 → 1).
- A card that fails to build says so in its place ("This post couldn't be drawn"), the
  log has why — the cards after it are built as ever (Qt and GTK; one broken card left
  holes in the lane).
- GTK asks again for who a profile is when the answer fails or doesn't come, and offers
  "Again" (it said "failed" once and stayed so) — one `common/patient.py` with Qt.
- Fixed: a #tag in a post from some servers (Pleroma, Akkoma, Misskey, Friendica, any
  that marks its tags its own way) opened that server's web page, which asked to log in;
  a tag is known now by the post's own list of tags, `rel="tag"`, its class, or its words
  being "#name" on a tag page's address — and opens the tag's lane in fedtail.
- Smoother, the Qt window: a lane opened or a jump far builds at once only the cards on
  screen, the ones a screen above and below a few at a time between the window's other
  work (built all at once they froze it for 300–430 ms; in the bench the stalls over
  100 ms opening the lanes went from 13 to 1); a lane's posts are looked up in one query,
  not one each (a 342 ms freeze when a lane was redrawn).
- Memory freed goes back to the system a few seconds after cards are let go (scrolled
  past, a lane unloaded), not only at the next stats tick: `smem` right after reading
  through lanes showed the freed memory as still used.
- Fixed: someone waiting to go into a list, followed by now and already in it, was asked
  for again every round (a 422 "already in list" each time, two of them in a log of an
  hour); followed and still refused — let go.
- Fixed (the phone): after ⟳ the thin bar under the title stayed for 8 s when the round
  brought nothing new, the lane pushed down by it; it goes as the round ends now.
- Fixed (Windows): a secret file written by two at once (the sync key: the round's and the
  window's) could fail with "Access is denied"; the second writer waits its turn.
- Fixed: a picture from another server can't be turned into a request to this computer or
  one at home by its name answering differently the second time (DNS rebinding): every
  outside fetch (pictures, link previews, other servers' pages) connects to the address
  that was checked, the name kept for TLS and `Host`.
- Every window draws the same places: silence (filters, muted, blocked, servers), a
  filter's own form, filtered notifications, trends and "Read it whole" are the common
  pages in Qt and GTK too (each had a dialog of its own with its own gaps); an event's
  start and end show in local time.
- Inside: the core reaches a protocol only through `core/proto.py` (it called the Mastodon
  module directly in places — counters, search addresses, the slow-server tune, the
  server's probe), a test keeps it so; `core/app.py` is split into parts by what they do
  (silence, lists, activity, sync, polling, people, threads, writing, …).

- More of the lanes by their rules: a lane waits out of the sidebar till it has something
  by its rule's `hide_empty` (the fedtail set's "Important people"), not its name; the
  columns with nothing chosen are the set's first lane, its replies and mentions and a lane
  of events; `fedtail tail` follows `notify.lanes` as the notifications do (`except`,
  lists by title) and `fedtail lanes` counts as the sidebar does; GTK's tray number heeds
  `ui.icon_count` as Qt's does. The Qt window takes events as the model (it read the
  server's JSON). Leftovers gone: the old profile handlers of the Qt window, unused names.

- Fixed: two keys could be made at once when sync was set up — the first device's key from
  ≡ → Sync and the one a round makes by itself for an empty journal — and the one kept
  wasn't always the one in use (seen as "No such file … sync.tmp" now and then). Every
  change of the key waits for the round; a secret file is written through a temporary
  file of its own.
- The same rules in every interface, decided once: "Read up to here" counts by time over
  what's shown, a boost where it was boosted (the web page and the phone counted by place,
  the terminal never matched a boost); where a lane opens follows `feed.start_at` on the
  phone too (it went to the first unread whatever the option said); a thread read as it
  opens (or not, with `read.mark_read = "manual"`) and what is seen marked read are one
  decision for Qt, GTK, the terminal, the web page and the phone. The phone's overview
  sorts lanes by their rules (it had a list of names).

- Lanes behave by their rules, not their names — a set of lanes of one's own (or another
  preset) gets everything the built-in names had:
  - the lane opened first (`ui.start_lane`) is decided once for every interface: the
    terminal, the web page and the phone ignored the option, and five places fell back to
    a lane called "home" — now each set marks its own (`start = true` in its rule);
  - leaving or muting a thread, a bookmark taken back, another device's thread state:
    the lanes those sources fill look again (they were told by source names — "subs",
    "mentions" — that the fedtail set has no lanes of, so "Commented posts" and "To me"
    stayed as they were);
  - a lane's sound comes from its rule: followed threads sound as threads ("Commented
    posts" was a plain "message", the thread sound never played), a lane of one's own
    with private posts as a private message;
  - private messages — the server's conversations kept read, my own messages in the
    dialogue, the chat window of the split layout — work with any lane that takes them,
    not only one named "direct";
  - the split layout's roster shows followed threads from the set's lane of them (with
    no lane called "subs" it showed none);
  - the sidebar's sections are the rules' `group`: a lane in two sections at once, or in
    the section its name had rather than its rule's, is gone;
  - "posts only", "as conversations", checking my replies, "via #tag" and
    `activity.requests` go by what a lane's rule takes, not a list of names.

- Safer with what others send and what the config holds:
  - the bug report and the debugging log keep the config with its secrets taken out
    (`feed.translate_key`, a password in `net.proxy` or any other address);
  - a post's `mailto:` link keeps only its subject and body (`attach=` went to the mail
    client);
  - the terminal shows a post's words in its dialogs as text (`[/b]` broke the "delete?"
    dialog, `[@click=…]` was an action);
  - someone's name, handle or "about" line in a Qt tooltip is never drawn as HTML;
  - `sync.url`, `sync.webdav` and `feed.translate_url` take `http://` only to this
    computer or one at home, by the host as parsed ("http://localhost.evil.example" passed
    before), from the config and from ≡ → Sync alike;
  - a login of long ago to a plain `http://` server on the internet no longer sends its
    token: log in anew with `https://`;
  - logs that can't go where they should go to a folder of the temporary one that is the
    owner's only (another user's folder of that name, or a link, is refused);
  - the phone's self-check fetches pictures the way the app does (public addresses only,
    the size capped).

- Automatic translation through LibreTranslate (`feed.translate_auto`) sends out only
  public posts: a direct or followers-only post went to the outside service as it arrived.
  Such a post is translated on a click now (the server's own translation refuses them
  anyway).

- Sync, the key under a password on a sync server: kept under an id of the password and
  the fediverse account, not of the password alone — a guess tested every person on the
  server at once, and a journal could put its key in another's place (now refused, 409).
  The id goes in a header, never in a URL a log keeps; scrypt is four times as hard
  (`FTK2`; the older blobs still open); a password is 10 characters at least. The sync
  client follows no redirect (the journal's id and the invite code went along), reads no
  answer bigger than any a store should give, and a server's code makes at most
  `journals_per_invite` journals (fedtail-syncserver).

- Lighter core: a new free lane (or one whose rule changed) fills from the stored posts by
  linking them, not writing every one back — the fill had held its posts three times over,
  a 25 MB peak the process kept. The core alone, 4000 posts: 89.5 → 72.5 MB; every lane's
  rule applied anew ~1.0 → 0.7 s.

- Much lighter and quicker, the Qt window: a lane builds only the cards near the screen —
  a screen above and below; the other posts are a place of their height, built as the
  scroll comes near and let go when it's gone far (what was done to a card — a warning
  opened, a translation shown — is kept for it). The cards themselves are as before.
  Every lane opened, 4000 posts in the bench: 405 → 263 MB, opening all 19 lanes
  11.3 → 2.7 s (the slowest 1.4 → 0.3 s), the window up 1.9 → 0.8 s. `reading.build_at_once`
  is gone (a config that still has it is told so).

- Lightness held by a test: `tests/test_budgets.py` runs the memory bench (2000 posts, 20
  lanes, an hour of polling) — the core alone and the Qt window — against ceilings of
  memory, time, widgets and the picture cache; CI's `budgets` job runs it and a release
  waits for it.

- Lighter: only the lanes opened last keep their cards out of sight (`ui.keep_hidden_lanes`,
  3) — one opened before lets them go the moment another lane comes to the front, besides
  `unload_hidden_minutes`. Every lane opened in the bench's window: 573 → 405 MB (a lane
  drawn is some 18 MB). The same rule in the GTK window, which now heeds
  `unload_hidden_minutes` too (it kept every lane drawn for ever).

- Sync without logging in to the fediverse server: on a fedtail-sync server (protocol 2,
  fedtail-syncserver 0.22) the journal is the key's — an id and a secret derived from it,
  the key never sent. The first device makes the journal with an invite code the server's
  admin gave (≡ → Sync → Where, `fedtail sync invite CODE`; kept in the data folder, not the
  config); the others need only the key. The steps are where and the key; a login is left
  for WebDAV alone. `fedtail sync first` makes the first key from a terminal (on a server
  the key is never made by itself: nothing there can be seen without one). The key under a
  password is kept on the server apart from the journal, under an id derived from the
  password. A server of protocol 1 is told, not talked to; after updating both, every
  device sends its state once more. When the server wants the invite code, ≡ → Sync goes
  back to step 1 by itself, says why on top, and the code typed there makes the journal at
  once (the error named a "Where" one couldn't find).

- Fixed: a lane's funnel ("only video…") and a free lane's switches filtered the newest
  posts after the lane's window was cut — a handful of videos out of the newest few
  hundred, none of the many further down, and "Older" asked the server while the store had
  them. Now they count before the window (the core does it — every interface the same), and
  "Older" first looks deeper into what is stored, then asks the server.

- Lighter: avatars are decoded at their box (twice it for HiDPI) in every window, not as
  feed pictures up to 1200 px — measured, 3–13 MB less in the bench's window.

- The phone quotes piece by piece, as the windows and the web page: a tap on the post
  answered shows it whole, select a piece, "❝ Quote in reply" puts it where the cursor is.

- Sync through a WebDAV folder spoken directly — Nextcloud, ownCloud, a NAS, nothing to
  mount: `sync.webdav` and `sync.webdav_user`, the password asked once (≡ → Sync → Login,
  `fedtail sync login`), checked there and kept in the profile's data folder (0600), never
  in the config. The same files as a shared folder; the folder is made if it isn't there.
- Sync packs the journal: once a device has sent more than a megabyte and several times
  what a snapshot of its state would be, it sends the snapshot (every setting with its own
  time and device, the newest read marks, how far events are seen, what was dismissed)
  and drops its older files — a folder, WebDAV — or blobs, on a fedtail-sync server that
  says `compact` (0.22). Before, journals only added up to the quota.

- Lighter: `media.image_cache_mb` is 64 MB by default (was 128). Measured: with pictures on
  its disk the bench window holds 378 MB at 128, 319 MB at 64 and no less at 32 (the pictures
  on screen are held by their cards anyway); a picture scrolled back to is reread from the
  disk cache. `tools/membench.py --ui qt` now has real pictures in its disk cache, and
  `--image-mb` to set the budget. The phone's settings test looked for `ui.command_line`,
  which the file keeps under `[window]` since 0.21.

- Fixed (the phone): writing crashed with the formatting buttons on a side (the default,
  left) — a scrolling column of them inside the scrolling editor. The UI tests waited for
  the overview's "Read in a row", gone since that button went: they wait for its title.

- The phone: "Mark all read" on a lane's bar, as the windows' button — the whole lane in
  the core, not only the posts loaded; "to the new" says how many there are ("↓ 12")
  instead of a bare arrow; the end of a lane is one row (✓ read · the next lane with news),
  not a card half the screen high.

- Windows (and any pip install): video opened in the browser because the player's part of
  Qt, QtMultimedia, is in PySide6-Addons, which the install line left out. The README says
  `pip install requests PySide6-Essentials PySide6-Addons` now (`pip install .[qt,media]`),
  `--check` asks for Addons at the version of the Essentials there (a mismatched pair
  doesn't load) with quotes cmd takes too, and the window says once, at the first video
  going to the browser that way, what would bring the player.

- Fixed: Activity froze the window for good (28.10): with its short rows, building cards
  near an edge and letting far ones go undid each other every few hundred ms. Far cards go
  by distance now (four screens either side), never within what building reaches. Seen
  events only lose their marks in place (Qt, GTK) — every event lane was rebuilt at each
  mark. And no "Older ↑" in a lane of events only: there is nothing older to fetch.
- A hashtag muted in one click (as in Fedilab): a post's ⋯ → "Mute #tag", or the tag's
  page → "Mute the tag" / "Show the tag again" — into one server filter of muted hashtags
  ("fedtail: hashtags"); its posts leave at once, those already here too.

- Fixed: a profile copied to another computer (state.db and all) synced with nothing — both
  carried one device id, and each took the other's journal for its own (28.10's report: a
  Linux profile moved onto a Windows VM). The id is bound to the computer and the folder it
  was made in now: a copy makes its own and reads the journal from the start. Ids from
  before are made anew once, the same way.

- Sync: the first time a device syncs under a key it sends once what it knew already —
  the order of lists, saved tag lanes, tiles, how far events are seen, the read marks of
  the posts it keeps. A device added later got only the changes made after it came: lists
  in another order, posts read elsewhere still unread (28.10's report). A real change
  anywhere still beats that first picture.
- Windows: the user's themes and fedtail's small cache live in `%APPDATA%\fedtail\themes`
  and `%LOCALAPPDATA%\fedtail\cache`, not in a `~/.config` / `~/.cache` of their own.

- Fixed: an event's row in the window (Activity, Requests, a lane taking events) cut its
  text's last line off, and its × shrank to a dot in a roomy theme (28.10's report): the
  words take the height they need, the button the width its padding needs.
- Sync carries how far the events are seen too: Activity read on one device is read on
  the others (`sync.activity`; the mark only goes forward). Before, every device kept its
  own, and a home computer showed the day's events as new after a day at the office.
- Lighter and quicker: the store parses a post once and every lane shares that one
  (read-only) object, instead of each lane parsing its own copy; a post nobody holds goes
  (docs/en/dev/memory.md, step 1). On the bench's day: the core 110 → 102 MB, opening every
  lane 656 → 362 ms, polling ~40 % quicker.

- The lane editor builds a condition from its parts, with no syntax to remember: a lane's
  conditions stand in words over its form ("The author: I follow · Kind: a reply"), each
  opens a page of its own — "Ask" at a key (the author, the kind, what the post has, the
  event, the language, words, counts…), tick its values, type what the list hasn't
  (`@nick@host`, `tag:x`, `>10`); the quick filter and the whole line are there too. Every
  key and value has its words in both languages. On the phone the editor has its own doors
  now: ⋮ → "Lanes…" in the overview and ⚙ on a lane's bar (it was only among the places).

- Any event in any lane: events are posts' equals in the lanes' rules. Activity and
  Follow requests are now lanes of events only, built by the same lane model as every other
  lane (one counter, one "seen", the same ×, the same "mark all read"); Activity's quick
  filters are its rule's switches (`switch`), editable like any lane's. A follow request
  is an event a lane's rule may take (`event = "follow_request"`) — beside posts too — and
  its row with "Approve" / "Reject" is the same in every lane and every interface (one
  description, `fedtail:` links). The special Activity and Requests places of every
  interface are gone; a lane of one's own written as `kind = "activity"` before 0.22 is
  read as the set's rule.

- Sync: a draft's pictures travel with it — the same picture, its description and focus
  point on the other device. Each is sealed with the account's key and named by a keyed
  hash, so it goes once however often the draft is saved; a sent or emptied draft takes
  its pictures off the store. Too big for the store, or dropped by it — that one stays
  where it was added. fedtail-sync 0.22 keeps them (`PUT/GET/DELETE /v1/media/…`, still
  protocol 1) under a quota of their own where the least used go first, so drafts made in
  a loop churn only their own pictures; a folder keeps them in `media/`.

- Sync: the key for the next device is a QR code now. ≡ → Sync → "Show the key" (after a
  "sure?") shows the code and its text with "Copy"; on the phone "Add to those set up" has
  "Scan the QR code" by the key's field (the camera is asked only then; the scanner is
  zxing-android-embedded, no Google services). The code is fedtail's own (common/qr.py,
  no library), drawn by every interface: a picture in the windows, SVG on the web page,
  half blocks in the terminal, a canvas on the phone.

- Fixed: a comment in a followed thread that came only as a mention (an unlisted reply into
  a public thread, say) went to "To me" and not to Commented posts. The thread is now found
  through the comment's chain of parents (up to 40 known posts), and its comments are
  counted as the thread's from then on.

- Fixed: "Translate" could vanish though the server translates (28.10's report). Whether
  it does is now also asked of the list of what it translates (a server whose instance
  document doesn't say so, or whose newer document came late), and a late or broken
  `/api/v2/instance` no longer costs the server's other facts (limits, Markdown) — they
  were all forgotten with it. The log says at every start what was found.

- The phone too: its start shows the swinging opossum, not a spinner, while Python, the
  core and the lanes come up.

- fedtail-sync, the sync server, lives in a repository of its own now:
  https://github.com/eugene-vereshchagin/fedtail-syncserver (with its history). Its version
  is fedtail's — one number, released together (both CIs check it).

- The window opens on the curtain with the opossum swinging from its very first frame;
  connecting, counting the lanes and fetching the news start only once it is on screen
  (before, the window thought first and showed the curtain after). The core counts
  "starting" as busy until the first round ends (all accounts in one window too); GTK
  asks the session bus for the tray without waiting, Qt loads QtMultimedia at the first
  video or audio, not at start (the windows, GTK).

- Fixed: "Why is it here?" fell over on a lane whose condition didn't match the post
  (its words had a field named like the lookup's own argument); a test keeps every word
  of the interface clear of it.

- The status line at the bottom ("⟳ updating the lanes…", "updated at 16:18", the sync
  mark, the account) is written in the text's colour, not the faint one — it couldn't be
  read on a light theme (the windows, GTK; its labels have a style of their own now,
  `statusText` / `ft-status`, not the cards' faint one).

- Fixed: the config reference (`docs/<lang>/config.md`, the help's "Settings") listed a few
  options twice or in one language only — an explanation that begins with "open_at = …"
  was taken for an option of its own. Now only live `key = value` lines are options, and a
  test keeps the Russian and English tables row for row.

- Fixed (Qt): a place closed within 8 s of a "done" (adding someone to a list) crashed —
  its timer reached for a label already gone. Every timer of the windows now names the
  object it belongs to and dies with it (a test keeps it so).

- Fixed: "Commented posts" (a card a thread) said "64 +64" over a handful of cards — the
  number counted every new comment. A lane of a card a thread now counts the threads with
  news, as many as its cards, "of them new" too; the core counts it, every interface and
  the phone show the same (all accounts in one window as well).

- Sync says why it can't reach its server, naming it: "cannot find the server
  "fedsync.example.org" — check the address (a typo?) and DNS", refused, no answer in
  time, a wrong certificate — instead of a bare "sync server: ConnectionError"
  (`core/neterr.py`, for whatever else reaches a server that isn't the account's own).

- **Formatting buttons by the text** (`post.format_bar`): B, I, S, code (several lines —
  a block), a link, a quote, a list — the Markdown marks put around the selection, pressed
  again taken off; Ctrl+B, Ctrl+I, Ctrl+K. Where they stand: "left" (the default) or
  "right" — a column beside the text, "top" or "bottom" — a row, "off" — none; only when
  the server understands Markdown. The windows, GTK, the web page, the phone; the terminal
  by the buttons (its Ctrl keys belong to the text field).
- Fixed: "Report a bug on GitHub…" said the interface the config wished, not the one
  running (`fedtail --ui web` — "qt"), and from the phone "Linux <kernel>" with no model
  and no Android; now the phone's model, Android and screen, and the interface that runs —
  in the issue, the bug report and the log's session line.
- Fixed (GTK): in the windows of rows with buttons (≡ → Lanes and every other place, the
  settings, the profile editor, the lists of filters, scheduled and filtered posts) the
  scrollbar was drawn over the buttons at the right edge ("Take", "Edit…"); now it has
  a strip of its own beside them, as in Qt.

## 0.21.0 — 2026-10-28

Sync set up in the window step by step, "Commented posts" as on Point, a library of lane
pictures, where a thread opens as one setting, lanes of rules brought to the end, and a
crash on a flaky connection fixed:

- Fixed (GTK, before it ever shipped): opening a thread or a lane failed on the "loading…"
  box — it asked the Qt notifier's question of GTK's; it reads `ui.app_icon` as the curtain
  does.

- Fixed: the spell check underlined every word of a Russian post written with an English
  interface — the English dictionary judged Cyrillic. A word now goes to the dictionaries
  of its own script: those asked for, else the installed ones of that script; none — it
  isn't judged.

- **A lane without a seam** (`reading.older_ahead`, off by default): read to within a
  screen of what a lane shows, and fedtail fetches a page of older posts itself, as the
  "older" button does — one at a time, and none any more once a page brought nothing (the
  button still may). The frontends only say "the end is in sight" (`core.older_ahead`
  decides): the windows, GTK, the terminal (a few posts from the end), the web page and
  the phone.

- **Where a thread opens, one setting for everything:** `threads.open_at` — "post" (the
  default) or "first_unread" (the first unread comment; none — the post); a lane of
  rules may say its own (`open_at`, "A thread opens" in the lane editor — "Commented
  posts" has "first_unread"); "🔔 N new in the thread" always goes to the first new one.
  The card's links carry it (`fedtail:thread/` / `fedtail:threadnew/`), the thread finds
  its place once loaded — the windows, GTK, the terminal, the web page and the phone
  alike. It replaces the one-off jump "Commented posts" had.

- fedtail's set of lanes: "Subscriptions" (every comment of the followed threads, one by
  one) is out of it, "Commented posts" (a card a thread with news) does that now; it
  stays in the extra set, and the notifications, sounds and the icon's number count
  "Commented posts" as they counted it.
- A server without markers (Sharkey, Misskey; 28.10's report): "markers: HTTP 404" in
  every round — now said once, in words, and not asked again until a restart.

- **Pictures for lanes, a library of 44** (`fedtail/data/icons/lanes`, drawn by
  `tools/lane_pictures.py`): people, heart, fire, news, RSS, search, link, camera, film,
  music, book, code, a gamepad, mountains, a fish, a car, a plane, a cup… — for one's own
  lanes (the lane editor's "Picture" shows each with its name; `icon = "…"` in the file),
  coloured by every theme's [pictures] style as its own pictures are; a theme's own file
  of that name wins. "Commented posts" wears speech bubbles, "Important people" a bell —
  it wore the star Point's theme draws for Bookmarks too.
- Fixed: the windows' sidebar dropped the picture a lane of rules asks for (`icon`) —
  the label's name hid it.

- Fixed: ≡ → Sync → "What to sync…" drew the settings as a heap of bare fields inside the
  sync window; it opens the settings window at its Sync chapter now (Qt, GTK, the phone).

- ≡ → Sync: the password for new devices is its own page now, saying plainly what it is
  (not the account's nor the server's — one you make up, so a new device needs it instead
  of the long key) and that it's optional; the done page only shows whether it's set.

- Fixed: a poll of several choices whose server's "how many voted" lags behind its
  counts showed 400 % — a share is now never over 100 % and "N people" never fewer than
  one option's votes (every interface and the phone).
- Federated and Local, just opened: "loading…" with the opossum till their server
  answers, instead of an empty lane (Qt, the web page and the phone).
- The exit no longer drags on a slow network: everything still running gets 4 s in all
  (it was 3–5 s for each part), so starting again doesn't find the old one "already
  running".

- **"Commented posts"** (`commented`, as on Point; shown by default in fedtail's set, the others may turn it on — the extra set): your posts, threads
  you commented in and those followed by hand — the ones with new comments, a card a
  thread with how many are new; a click opens the thread at the first new comment. Any
  lane of rules can be shown so: `view = "threads"` (the editor's "Show: threads"). The
  condition `state = "subscribed"` works now (it never matched before).

- **Fixed: the window crashed on a flaky connection (mobile internet).** A picture came
  cut short or wasn't what its name said, and Qt handed it to every image plugin installed
  to guess its format — KDE's kimageformats among them, some of which read far past the
  end and abort the process. Now fedtail names the format by its first bytes and only
  that decoder reads it; a file that ended early never reaches a decoder or the disk
  cache (it's asked for again later); the rarer formats (AVIF, HEIF, JXL, TIFF…) are
  decoded one at a time. GTK reads with the named loader the same way.
- "Loading…" comes with the swinging opossum: over a lane being drawn and a thread
  waiting for its replies (Qt, GTK, the web page), "fetching replies: 3 of 12" on it
  while a "remote" thread waits.

- **Sync set up in the window, step by step, no terminal:** ≡ → Sync (or a click on
  "⇅") — three steps marked ✓ / ▶ / ·: where the devices meet (written into config.toml
  and used at once, no restart), the login to the sync server, then the fork — **"this is
  my first device"** (the key made here) or **"I'm adding this device to those already
  syncing"** (the key pasted from another device, or **taken out of the journal with its
  password alone**, or started anew). Done — how it goes, "Copy the key" for the next
  device, the key put into the journal under a password, what to sync, turning it off. The same in Qt, GTK, the terminal, the web page
  and the phone; `fedtail sync keep` / `unlock` in the terminal.

- `fedtail --check`: what fedtail needs from the system — the must-haves, each
  interface's, the extras — what is there, what each gives, and one `sudo apt install …`
  (or pip) line for what is missing. At start, a missing must-have (or the interface's)
  is said with that line instead of a traceback; a missing extra in one line, once.
  packaging/deb.py takes its Depends / Recommends / Suggests from the same table.
  The README and the site's quick start: four steps from the source, and every package
  in one apt line.
- The login's server address forgives the usual slips — a comma for a dot (the other
  keyboard layout), spaces, @me@host, a link to a page there — and an address that
  can't be reached is said in words, not as a urllib3 trace.

- **From the competitors' report** (every one behind a key, off by default):
  - lanes of rules from someone's wall filtered by its server
    (`account:<id>/posts|media|noboosts|pinned|tag:<tag>`), from a search (`search:…`)
    and from RSS / Atom feeds (`rss:…` — read-only posts); a lane of tags in one request
    (`lanes.tags_one_request`, Mastodon); "Network" and "Strangers' mentions" in the extra
    set;
  - rules: a condition `until` a date, words in the author's name (`text_in = "name"`),
    at most N posts per author (`per_author`), each author's posts together (`bundle`);
    "Not in Home" on a profile (`people.home_hide`) — out of Home, still followed;
  - threads: where replies come from (`threads.thread_from` local / mixed / remote), an
    open thread asking again by itself (`threads.thread_recheck_minutes`), only the
    followed (`threads.thread_followed_only`), `]` / `[` between top comments and `-`
    folding a branch, "Around this post" in the post menu (`card.around_post`), how
    fetching replies from the author's server goes (`threads.thread_progress`); GTK and
    the terminal take a thread that grew, as the window and the web page do.
  - people: my own name for someone (`people.aliases`, "My name for them…" on a
    profile) and a colour for their name (`people.nick_colors`, "Name colour…"); `sync.people` carries those names and the people out of Home to the other
    devices; why a post is in Home — "# tag" when it came by a followed tag
    (`card.why_home`); the post's JSON in its menu (`debug.raw_json`).
  - writing: a question when the text reads as another language than the post's
    (`post.lang_check`), a post's link at the end becoming a quote (`post.link_quote`),
    the editor closing at once with the post going in the background
    (`post.send_in_background`), a scheduled post back to the editor
    (`post.scheduled_to_draft`), "Drafts" in the ≡ menu (`post.drafts_place`).
  - the application: a proxy for everything (`server.proxy`), also typed at login
    (`server.proxy_at_login`, every interface and the phone); a lane by Ctrl+1…9
    (`window.number_keys`), pinned tabs (`window.pin_tabs`); the phone's live stream on
    Wi-Fi only (`phone.stream`); "Statistics" in the ≡ menu (`reading.stats`);
    LibreTranslate for "Translate" (`card.translate_backend`, `translate_url`,
    `translate_key`) and posts in languages you don't read translated by themselves
    (`card.translate_auto`); new posts waiting for Refresh (`reading.on_new = "hold"`);
    the week's most shared links in Statistics.

- The opossum's swing no longer stops dead when a round ends: it runs to the end of its
  swing (where it stands still) and stops there — the windows, GTK, the web page and the
  phone.

- **config.toml and the settings window by what one sets up.** 18 chapters, the same in
  the file and in the window: Appearance `[appearance]`, Window and layout `[window]`,
  Lanes `[lanes]` `[lists]`, Reading `[reading]`, The post card `[card]`, Threads
  `[threads]`, People and profiles `[people]`, Pictures and video `[media]`, Writing posts
  `[post]`, Notifications and sounds `[notify]` `[sound]`, Activity `[activity]`, Several
  accounts `[accounts]`, **Sync `[sync]`** (a chapter of its own now, `sync_markers` with
  it), The server `[server]`, Database and logs, the terminal, the browser, the phone. The
  keys keep their names; `[ui]` (63 options), `[feed]`, `[read]`, `[subs]`, `[poll]` and
  `[account]` are spread over the new tables. A file of 0.20 still reads as it was (the
  start says once that there are options to move); a change in the settings window
  writes the option in its new place and takes the old line out; `--rebuild-config`
  moves the whole file, values kept. Errors name options the new way. A test holds the
  layout, both reference files and the window to one another.

- **Android caught up with the windows** (a read-through of the whole app against them):
  - the card's lines: "🔔 N new in the thread", "👤 new in this private talk" (and the
    warning in the reply box before sending), "↳ you replied…", the conversation line,
    "♻ boosted by … · time" opening the booster, "the post it answers is gone / fetching";
  - the marks under a name are links: "edited" opens the post's edits;
  - #tags and fediverse links inside a post open here (they did nothing);
  - a post a server filter says "warn" for is folded, with the filter's name; a quoted
    post's warning is shown instead of its words, a quote hidden for a block or mute has
    "show anyway", `feed.quotes = "off"` holds;
  - a lane of rules shows its events (likes, follows…) among its posts;
  - an open thread grows by itself when replies come from other servers;
  - "in every lane" finds reach back past what a lane shows;
  - "Quote in reply" uses `post.quote_prefix` and leaves the leading @mentions out;
  - the character count is the windows' (a chain part by part);
  - the server's announcements as a strip with reactions and "Got it";
  - launchers that show a number on the icon get `ui.icon_count`'s;
  - a browsed lane its server gives nothing for says so; a lane's info line shows while
    it has posts too; link cards show their description.
- Web and phone: a tail of nothing but #tags is folded to "… +N" (`feed.collapse_tags`),
  as in the windows.

- Android: the overview of tiles stays the home screen; the lanes under the tiles stand as
  the chosen set has them (`lanes.preset`), under its sections' titles, instead of a fixed
  order of fedtail's own. The big "Read in a row" button is gone (swipe left or "what's
  next" at a lane's end still go on to the next lane with news); how fresh the lanes are
  moved into the bar under the account.
- A fifth set of lanes: `lanes.preset = "fedilab"` — as Fedilab's tabs: Home, Local,
  Federated, Mentions (private ones too) and Activity, Direct, Bookmarks, Favourites.
- The lane editor: lanes of the set copied into config.toml as they are (Activity, lists,
  tags…) no longer stop saving ("unknown key 'kind'") nor show as changed.

- **Lanes of rules, the rest of the plan** (docs/en/dev/feeds.md):
  - `sort` by counts — `replies`, `likes`, `boosts`, `density` (all three per hour of age);
    `mode = "catch_up"` with `window` ("12h", "2d") — only what came within it;
    `filter_context` — the server's filters of that context over the lane's posts, whatever
    source they came by.
  - Nested conditions: a condition may hold an `any` of its own (an AND of ORs); in the
    editor's line `author: followed; any: [has: image] [kind: reply]`.
  - More sources for a lane: `trends`, `direct`, `bubble` (`lanes.bubble`), `account:<id>`,
    `link:<url>`, `quotes:<id>`, `remote:<host>`.
  - "Why is it here?" in a card's menu and `fedtail --explain-lane NAME`: which condition took
    the post, or which key kept it out of each. A lane no source can fill is marked ⚠ in the
    editor.
  - A post in several lanes rings once, by its most personal lane.
  - Replies whose rules ask about the parent or about me get their parents fetched before
    they are sorted: they no longer jump lanes after showing.
  - Derived: a follower who moved is "moved", not an unfollow; likes taken back
    (`activity.unlikes`, off by default); a post deleted on its server is marked on its card.

- The web page on a phone: the "in reply to…" line (a link since the cards' words became
  common) didn't wrap or cut and widened the lane past the screen, the cards slid aside.
- Every quick filter holds until the program closes and is kept between runs only with
  `feed.remember_choices`: Activity's and the media funnel now too (Activity's was kept
  always, the funnel never).
- `ui.layout` is two layouts now: "single" and "split". Columns side by side are the single
  window's option, `ui.open_columns` (`layout = "columns"` still reads, as single with it on;
  "qip", split's old name, as split); the settings window offered "columns" and "qip" as
  layouts of their own.
- **Wider than your server knows** (core/wider.py): `lanes.federated_extra` — other servers'
  public lanes into Federated while it's open; `lanes.tags_extra` — their tag lanes into your
  lanes of tags. Read without an account, each new post fetched into your server by its
  address (so liking and answering just work); a server at most every `extra_minutes`, lanes
  closed to strangers left alone for a while.
- **Activity's quick filters**: all · likes & boosts · followers · requests · mine · other, over
  the lane (the windows), its tabs (the web page), `s` (the terminal); the choice holds till
  the program closes. Only the filters that can show something: no "Requests" with follow
  requests in a lane of their own (and no approvals waiting), no "Mine" without
  `activity.my_follows`.
- **Threads with news on the cards** (`feed.thread_news`): a post whose followed thread has new
  replies says "🔔 3 new in the thread" under it, the line opening the thread.
- The lane editor starts with the set: fedtail (the default), Mastodon, Tusky, Phanpy —
  "Take" one, and "Take all of yours away" for the set as it is. A lane of tags saved from a
  search gets "In Home too" in its sidebar menu (and the tags place): off, its posts leave
  Home.
- A place's window (the lane editor among them) says what a button did in the window itself:
  it went to the main window's status line, behind the dialog — "Save" seemed to do nothing.
  The settings window marks each option saved ("✓ saved"), says it takes effect after a
  restart, and a field's tip says Enter saves it.
- **Who stopped following you** (`activity.unfollows`, core/derived.py): the whole list of
  followers compared hourly; one missing twice and not following when asked is a row in
  Activity. A list not whole is thrown away, the first is the start, your own removals and
  blocks aren't news, a server's followers gone at once are one row about the server.
- A profile could stay "@…" for good (who it is never came: the one request failed, or
  answered with no account, and nothing was said) until a restart. Now Qt's profile asks
  again by itself, says what didn't come, offers "Again", and after 20 s of silence writes
  what every thread is doing into the log.
- **Whom you followed, in Activity** (`activity.my_follows`): a row of your own for each follow
  — through fedtail, or seen in whom you follow when it was another client. Not counted as
  news; a lane of rules takes it as `event = "i_followed"`.
- **The lane editor.** ≡ → "Lanes…" (and a lane's right-click menu → "Edit the lane…"):
  the order, shown or hidden, new lanes of one's own, and each lane as a form — title,
  picture, section, sources, how it's read, its conditions one line each with their quick
  filters. Written into config.toml at once (`[[lanes.custom]]`, `lanes.enabled`) and shown
  at once; every interface (a place of common/places.py).
- `sync.lane_rules` (off by default): the lanes themselves travel between devices — the set,
  which lanes in what order, one's own lanes, `lanes.posts_only` — written into the other
  device's config.toml.
- Federated and Local keep the newest `lanes.browse_keep` (200) of the whole stream while
  open: pages back from the newest until they meet what is stored. One page a round lost
  most of what a relay brought.
- The bell on a profile shows on a follow still waiting for the other server's yes too
  (GoToSocial says "requested" until then, even for unlocked accounts): it wasn't there.
- A lane of rules picks its picture: `icon` (one of the built-in lanes' — `my_posts`, `direct`,
  `star_full`…); one's own lane without one shows a list's, not none. The settings window no
  longer shows `lanes.custom` / `lanes.tag_groups` as a line to type: saving it wrote the
  tables back as text; they live in the file.
- **Events in a lane.** A condition of a lane of rules with `event` (`favourite`, `reblog`,
  `follow`, `poll`, `update`, `status`…) shows those rows of Activity among the lane's posts, by
  time: one muted line for each run of one kind about one post, a click opens it. Never unread,
  not counted; quick filters part them as they part posts; Activity is polled for such a lane
  even without its own. Follow requests stay in Activity (they are answered there).
- **Someone new in a private talk.** A private answer that brings in someone the message it
  answers neither came from nor mentioned says so on its card ("👤 New in this private talk:
  @who"); the reply box says it before sending when a private answer adds `@someone` new.
  Every window: Qt, GTK, the web page, the terminal.
- Lanes of the set written into the config (`--lanes-to-config`) without a `title` showed
  their bare names ("home", "to_me"): they take the built-in words again; with every account
  in one window a lane's own title was lost too.
- Unsorted kept its number on the sidebar after a lane took its posts (shown empty, "12"):
  what leaves it redraws the lane and the number.
- "Unsorted" is collected with any set of lanes (not only with routed lanes of your own) and
  shown only while something is in it; `lanes.unsorted = false` hides it for good and stops
  collecting.
- Unsorted took the posts of people put in a list: Home leaves them to the list's lane
  (`lists.hide_in`), and Unsorted only asked lanes of the same source. Now a post another lane
  holds, or one of a list's member, isn't unsorted, and what got there by mistake leaves.
- **Every lane is a rule.** Home, Bots, To me, Direct, Subscriptions, Bookmarks and the rest are
  written in `fedtail/data/presets.toml` with the same keys as `[[lanes.custom]]`; the sets
  (`lanes.preset`: "fedtail", "mastodon", "tusky", "phanpy") are sets of such rules, and a
  `[[lanes.custom]]` of the same name takes a set's lane's place. `lanes.enabled` only orders and
  picks (`[]`, the default — the set's own order); a lane of one source is a view of its stream,
  of several — a stream of its own. `fedtail --lanes-to-config` writes the chosen set into
  config.toml. Gone (the rules say it now): `lanes.mentions_all`, `lanes.direct_apart`,
  `lanes.bots_in_home`, `subs.replies_to_me`; `lanes.preset = "own"` reads as "fedtail". A
  private message stays out of the other lanes only while Direct is shown (`apart = "direct"`).
- Free lanes can be named in `notify.lanes`, `sound.lanes`, `ui.icon_count` (and their except
  lists) and `ui.start_lane` as `"custom:<name>"`.
- A free lane's title can be given per language: `title = { ru = "Посты", en = "Posts" }` —
  the interface's language is shown, else English.
- Follow requests in Activity (`activity.requests`, on): on top, with "Approve" / "Reject", in
  every interface — so the "Follow requests" lane is no longer among the defaults (it stays; with
  it on, requests are there, not in Activity, and counted once).
- The Qt sidebar named a free lane by its raw key (`lane_custom:posts`), not its title.
- `--rebuild-config`: options a version no longer has are kept under a note in the file's own
  language (it was always Russian).
- "To me" (`to_me`): replies to me and mentions of me in one lane, with quick filters for each —
  by default instead of "Replies to me" and "Mentions" (they stay, for whoever wants them apart).
- Home's quick filters: tags (what followed tags brought), boosts, threads with news (posts whose
  followed threads have unread replies; the replies themselves are in the thread).
- "Important people" (`important`): posts of those you rang the bell on; shown once there is any.
- A lane of tags can keep its posts out of Home (`not_in_home` in `[[lanes.tag_groups]]`, and for
  the saved ones `core.set_tag_group_in_home` — the switch in the windows comes next).
- Free lanes: quick filters — a condition with `switch = "…"` is a choice in the lane's
  header, one with `shown = false` is hidden (from the counts and the news too) until its
  choice is on, and "Main" shows the rest; "Older" fetches a page from each of a free lane's
  sources and puts through its rule what fits; "Unsorted" (`lanes.unsorted`) gathers what came
  to the lanes read through and no lane took.
- `--update-config` and the settings page with `[[lanes.custom]]` or `[[lanes.tag_groups]]`
  in the file: new `[lanes]` options went after the last such table — TOML read them as that
  table's keys, and the lane or tag group broke. Now they stay in `[lanes]`, before its tables;
  `--rebuild-config` writes the tables as tables at the end, not as one long line.
- Free lanes, first version: `[[lanes.custom]]` — a lane of rules over where a post came from,
  who wrote it, what it is, whether it's to me, what's in it, what a boost is of (docs/en/dev/
  feeds.md). They stand in "Personal" (`group = "standard"`: in "Timelines") — where
  `lanes.enabled` names them (`"custom:posts"`), else at the end — count and notify like any lane,
  fill from what is stored and anew when their rule changes. Mistakes in a rule are warnings,
  the condition with one never matches.
- Sets of lanes as in other clients (`lanes.preset`, in the settings): "mastodon" (the web
  page), "tusky", "phanpy", fedtail's own "fedtail" — or "own", your `[lanes]` as it is.
  `lanes.bots_in_home`: bots in Home too (the presets switch it on: they have no Bots lane).
- Only the languages you read (`lanes.languages`, e.g. `["ru", "en"]`): posts in others
  leave Federated, Local and the tag lanes (`lanes.languages_in`). A post with no language
  tag — or a wrong one, Cyrillic or Chinese characters tagged "en" — gets a guess
  (`lanes.detect_language`): by its script for free, Latin text by python3-langdetect when it is
  installed (Recommends of the deb), on posts of `lanes.detect_min_words` words and more.
  What can't be told stays.
- The opossum swings while the lanes update: on the curtain (Esc, every lane closed) in
  the Qt and GTK windows, over an empty lane on the web page and the phone — and stands
  still once the round is over. The animated sticker is credited as the icon is.
- The name people see is "FedTail": under the phone's icon, in the Start menu and the
  installer, the Linux menu entry, the windows' titles, About, the notifications. The
  command, the packages, the folders and the release files stay "fedtail".
- Unfollowed, someone's posts and boosts leave Home, as they leave the server's Home
  (`feed.forget_unfollowed`, on): at once when you unfollow here, within a few hours when
  you do it elsewhere. Kept, they stayed — and showed up anew when the unfollow also took
  them out of a list that had kept them out of Home.
- The plan for 0.21 (docs/en/dev/roadmap.md): sync between devices brought to the end,
  and free lanes — lanes you assemble yourself.

## 0.20.1 — 2026-10-27

Fixes for 0.20.0, and the lanes' freshness in the status line:

- Qt: a profile's buttons (Follow, Unfollow, Mute…) work again — they called a method a
  second one of the same name had replaced; a test now finds any method defined twice.
- How fresh the lanes are, in every interface's status line: "⟳ updating the lanes…"
  while a round asks the server, "updated at 14:32" after, "⚠ no answer from the server
  since 14:20" when rounds fail — an empty lane no longer leaves you guessing.
- Android: the notifications' small icon is the possum, not a speech bubble.
- The settings window opens again after it was closed (a crash: the closed one was
  deleted, the window still held it).
- The tray's number is drawn again when the icon under it changed (a theme tried put the
  plain icon back, and the same number never redrew it).
- Pictures: at most four asked of one server at a time (a small server answered every one
  late with all the workers on it at once, the pool full); a preview's first timeout,
  asked again with patience, is info in the log.
- The apt repository: its job installs `apt-utils` where the runner lacks it (0.20.0's
  failed so), says what failed, and runs by hand too for a release already out (`apt.yml`).

## 0.20.0 — 2026-10-26

**In short.** Every interface catching up with the windows, and a phone of its own:

- **Android, a first whole version to try**: every place of the ≡ menu, a post's ⋯,
  profiles with their buttons, the editor with pictures, a poll and "later", notifications
  in the shade and push through UnifiedPush, columns on a tablet, a screen reader.
- **The terminal and the web page with what the windows have**: every place, the menus,
  profiles, the editor, Ctrl+F, accounts; the web page also columns, ≡ as a window with
  groups, push in the browser, the windows' themes, logging in from the page.
- **Reading at your own pace**: slow mode, "notify at most every…" per lane, "of them new"
  beside the counts, mute for a while, hide one post, a profile's posts / replies / media.
- **More of the fediverse**: another server's public lane, a link's lane and who shared
  it, collections (Mastodon 4.6), reactions of your own (Akkoma, Pleroma, Misskey), a
  list's replies, filters edited, reports by the server's rules, spell checking, a
  video's cover.
- **Installing**: a Windows installer, `SHA256SUMS` with every release, an apt repository
  (built once its key is set).
- **Sturdier**: odd networks (a captive portal, a huge answer, a server asking to wait)
  explained instead of failing, polls backing off and catching up after sleep, a broken
  config explained, leaks and freezes found by the self-check fixed, the tray icon gone
  with fedtail.

Next, 0.21 (docs/en/dev/roadmap.md): sync between devices brought to the end, and free
lanes — lanes you assemble yourself.

The whole list:

- From the evening's self-check: the split layout's roster goes with its window however
  that one goes (a window deleted without being closed left it, 129 widgets each); a
  server's "wait" (HTTP 429) and "notifications have nowhere to go", said already in the
  window, are info in the log, not warnings. The self-check tools: a real server's slow
  first tabs waited for, an account that keeps one column remembered.
- The web page's ≡ is a window over the page, as the windows' menu: the everyday buttons
  on top (write, my profile, refresh, all read, columns), the rest in groups — lanes and
  lists, for the tender, whom to read, the account and the server, the look, debugging,
  help — a group's items beside it (↑ ↓ → ← and Esc too). A place opened from it is a
  window over the page as well, moved by its title, instead of the column at the right;
  threads and profiles stay docked beside the lanes.
- The tray icon leaving with fedtail, on Windows and in KDE: destroyed at once on the way
  out instead of only hidden (it stayed in the panel until the mouse passed over it);
  the log says "quit" and "tray icon removed".
- Columns on the web page, as in the windows: ❯ on the lane's bar puts lanes side by side
  (as left last time — the same set as the windows', else `ui.columns`, else Home,
  Replies to me, Activity); a lane picked on the left joins them, ‹ › move one, ✕ takes it
  away; the lane in focus has its bar, keys and Ctrl+F, a click on a column beside brings
  it into focus, each column marks what's read in it. At a phone's width — one lane.
- The window no longer freezes for a third of a second after a thread or a post came in
  in the background: the lanes' counts are worked out there, before the window is told.
- From the self-check runs on Linux and Windows: a lane's header in a narrow window (or
  a big font) puts its switches on a second row instead of cutting the buttons; in the
  split layout the roster window goes with the window, and GTK's closed tabs let go of
  their profiles; collections are offered on Mastodon only (others answered 404); a
  server that says "too many requests" for pictures is left alone for the time it asks;
  missing pictures and features an absent API says no to are info in the log, not
  warnings, and "nowhere to show a notification" is warned once; the terminal no longer
  fails drawing a picture after it closed. The self-check tools: a real lane's word for
  Ctrl+F, pictures the server failed are notes, a test that relaunched a mock.
- Android: every place of the windows' ≡ menu (search, lists, filters, silence, trends,
  the server, help, editing your profile…), profiles with their buttons (follow, mute for a
  while, block, lists, a note), the windows' own ⋯ menu on every card (edit, delete,
  redraft, quote, translate, report, hide…), polls to vote on, quotes in the card; the
  editor with pictures and their descriptions, a warning, the language and a poll.
- Android: notifications in the shade — the windows' notes (`notify.*`), while the app is
  open and, closed, from a round every 15 minutes; a tap opens the thread. Video, gifs and
  sound play in the app. Accounts: add, switch, log in again and out (≡ → Accounts). The
  windows' themes paint the phone (`ui.theme` in Settings).
- Android: ⟳ over threads, places and profiles too; a refresh no longer moves the lane
  (the "new below" line is a row of its own, places' rows keep their place by key). Read
  "as a forum" (oldest first), a lane is refreshed by pulling up past its end — where its
  newest posts are.
- Android: push through UnifiedPush (`phone.push`): with a distributor on the phone (ntfy,
  Sunup…) the server pushes, the app wakes for a round — notes at once with the app
  closed. All accounts in one window (≡), whose post in the editor. The themes' fonts
  (the ones that come with fedtail) and their own pictures on the buttons.
- All accounts in one, on the web page and the phone: a post's ⋯ offers ★ ♻ ↩ from
  another of them (`ui.act_as`), as the windows' menu does; the web page no longer refuses
  the other account's posts and people (their ids, "work~123", were taken for bad ones).
  The phone tries a theme for the run (⋮ → Try a theme…).
- The phone's editor: #tags, @names and :emoji: offered as they are typed (the web page's
  too), drafts in the core as the windows keep them (synced, `post.drafts_autosave`),
  "Discard", the preview, "Later…" (scheduled). Servers' emoji as pictures in posts, names
  and profiles; "Save" in the viewer (Pictures/fedtail); a link or words shared from
  another app open here (a post, a profile — or a search).
- The phone's lanes: the windows' switches (all / posts only / unread only, a whole
  conversation a card, the media funnel) and why a lane is empty; finding in a lane,
  deeper and in every lane; the cards' marks (old, bot, edited, whose), reactions, a poll's
  fresh counts; ⚠ opens every warning of a thread; a #tag opens its place.
- Followers and follows of someone from another server: "more — from their server" at the
  list's end, on the web page and the phone (the windows had it).
- The window no longer waits for a poll's write to read a lane: reads have a connection
  of their own (SQLite's WAL lets them go on) — the short freezes on the store's lock.
- Collections (Mastodon 4.6) in every interface: yours made, named, described, shown on
  the profile or not, deleted; someone into one from their profile (if they allow it); other
  people's from their profile; the ones you're in — leave them. The windows show them, and
  any place without a widget of its own, in a place window (qt/place.py, gtk/place.py).
- Windows: an installer too, `fedtail-X.Y.Z-windows-setup.exe` — for you alone, no
  administrator, a Start menu entry and an uninstaller (signed once CI has a certificate).
- The apt repository: built and signed by CI after every release, once the repository's key
  is set (`APT_GPG_KEY`, GitHub Pages for the `apt` branch).
- Profiles, on the web page and the phone: pinned posts on top, "often writes about" and
  recommendations, whom of yours they follow, their server's software, a move — and
  "more" page after page, further back from their own server.
- The test run's end no longer crashes Python 3.12 in Qt's teardown (exit 139 after "OK").
- Spell checking in the post window: mistakes underlined, suggestions and "Add to
  dictionary" on a right click, any of the post's languages; the system's dictionaries
  through Enchant (`post.spellcheck`, `post.spell_languages`). The terminal: a list on F7;
  the web page: the browser's own.
- Another server's public lane (≡ → "Another server's lane…"): read without an account,
  the posts fetched through your server so they can be liked and answered.
- The terminal and the web page add accounts, log in, switch and log out, as the windows.
- GTK: a closed tab no longer stays in memory (every card of it did — 30 MB a round of
  tabs in the stress test); a picture still on its way no longer keeps its card alive (Qt
  too).
- Settings: `config.toml.bak` is the file as it was before this run's first change — the
  window saves at every tick, and the backup used to hold only the step before the last; a
  symlinked config is written through the link instead of being replaced by a file.
- fedtail for Android (`android/`; Kotlin and Jetpack Compose over the same Python core):
  the overview of lanes as home — tiles or a list (`phone.overview`), the tiles picked
  and ordered in the app and carried by sync (`sync.tiles`), "read in a row", "read —
  next" at a lane's end, "300+" where a lane holds as many unread as it shows,
  "Earlier"; two or three columns on a tablet (`phone.layout`); threads as trees,
  replies, likes, a card's ⋯ menu, pictures with a viewer, live links; the settings
  page — the desktop's settings window (`common/settings.py`), only what the phone
  heeds; read marks synced; Point's command line off on the phone; a self-check in dev
  builds. The APK is built with every release (`fedtail-X.Y.Z-android.apk`).
- "Direct" is a dialogue: your own direct messages are in it too (sent from here, from
  another client or met in a thread), by the posts' time, read at once — the count is
  only what came to you. They never show in "Replies to me" or "Mentions".
- The rest of the 0.19 plan: the full terminal interface and the full web page (the
  "Four interfaces" table shows what is left).
- A profile shows "Posts", "Posts and replies" or "Media", switched above the posts;
  which one first is `feed.profile_show` ("posts" by default, as in other clients).
- Mute for a while (an hour, a day, a week, a month) and "posts only" — their notifications
  still come; word filters get a term too.
- "Hide this post" in the ⋯ menu: one post out of sight everywhere, through a filter of the
  server's ("fedtail: hidden posts"), in other clients too.
- A list's replies: to anyone you follow, to its members, or none (the server's setting).
- The rest of the Mastodon client API, in all four interfaces: filters edited ("Edit…"),
  a cover for a video or a sound, an edited post's picture descriptions and focus, a report
  by the server's rules, the profile's newer switches (hide follows, search of my posts,
  article authorship) and tag suggestions, "Who else shared this link", and the server's
  terms, blocked servers and translator (Translate is offered only where it can).
- Web Push in the web page: ≡ → "Push notifications…" subscribes the browser at your
  server itself, so notifications come with the tab closed and fedtail off (over https or
  on localhost — the browser's rule; see the help, "Notifications").
- The web page takes the windows' themes: their colours and font, and ≡ → "Try a theme"
  for the run (`ui.theme` gives the one it starts with).
- The help in the web page and the terminal goes back and forward between its pages
  (← → on the page; Alt+← Alt+→ in the terminal), as in the windows.
- The web page's ≡ menu: "All accounts in one window" and a test notification; the
  settings in the web page and the terminal: "Find a setting…", "Open the file" and each
  option's default in its tip.
- Slow mode (`poll.slow_minutes`, ≡ → "Slow mode…" everywhere): the news piles up and
  comes in one batch every 5–240 minutes, with its counts, notifications and sound; the
  live stream wakes nothing meanwhile, Refresh asks at once; on the phone a push and the
  background round wait their turn too, and the overview says when the next batch comes.
  In the same place, for each lane that notifies or chimes: "notify at most every N
  minutes" — the lane updates as usual, its notifications and sound come in one batch.
  While slow mode is on, the status line (the title bar on the web page and in the
  terminal, the overview on the phone) says when the next batch comes.
- "Of them new": beside a lane's unread count, how many of them the last update brought —
  under the count on the phone's tiles ("300", "56 of them new"), "300 +56" in the
  sidebar of the windows, the web page and the terminal.
- Emoji reactions of your own (Akkoma, Pleroma, Misskey and kin): ⋯ → "React…" — the
  usual emoji and those already on the post as buttons (tapped again, yours comes off),
  any other or the server's own one typed (`:blobcat:`). Offered only where the server
  has reactions, in every interface.
- The web page starts for a profile not logged in yet too: it asks for the server and
  the code itself (the login place), then goes on as the whole page.
- Someone's older posts from their own server on the web page as in the windows: the
  addresses at once, the posts four at a time, "n of N" counting on the button.
- Debug → "The log" (≡ → "The log" on the web page, in the terminal and on the phone):
  the last lines of this run's log, to read or copy into a bug report.
- All accounts in one: "→ @account" in that account's colour on the web page and the
  phone too (ui.account_colors), as in the windows.
- Android: a poll's results as bars (✓ by my choice, the leader marked; how many people,
  until when, ⟳); the thread's head (how many answers, its #id, why it reaches me,
  Follow); "to the new" in a lane; "Another language…" in the editor, and its hints as
  you type (a chain's parts, #CamelCase for screen readers); help goes forward again;
  the pictures of the next posts fetched ahead (feed.prefetch); "arts mode" marked in
  ≡; older posts from someone's own server say how many came.
- Android: a screen reader names every button and picture — a picture without a
  description says what it is ("A video without a description"), the viewer's arrows
  say previous and next.
- A long picture description no longer covers the picture or runs off: in the viewer it
  takes a third of the height at most and scrolls (Qt, GTK, the web page, Android); under
  a card on the web page three lines, a click shows it whole; the terminal's picture
  screen shows it whole with d.
- What the network may throw: an answer that isn't JSON (a captive portal, a provider's
  page) is an error that says so; an answer over 32 MB is refused, not read; failing
  rounds wait longer each time (up to 15 minutes; Refresh still asks at once); waking
  from sleep brings a round at once; the logs go to the temporary folder when theirs
  can't be written; a broken config.toml started from a menu is said in a window, with
  a run on the defaults; logging out (SIGTERM) quits as the menu does; with debugging
  off nothing wakes the processor every second.
- Android: the activity lane read "as a forum" opens on its first unseen row (or at the
  end) and is refreshed by a pull from the bottom, as the GTK window does.

## 0.19.0 — 2026-10-24

- An intermediate release of the 0.19 plan (docs/en/dev/roadmap.md): the sound schemes,
  the Windows tests, the same behaviour checked across Qt, GTK, the web and the terminal
  are in; the full terminal interface and the full web page go on in 0.20 — what each
  interface lacks so far, and why, is the "Four interfaces" table of the feature list.
- Windows: a new avatar or header no longer goes to the server under the picture's whole
  local path (with the user's folder name in it) — only the file's own name.
- GTK matches Qt where it didn't: ⏸ in the video player and the gif's own key hint, the
  menu items' tooltips (where GTK shows them), the profile's tooltip in the status bar, a
  click on a post's face opens the profile (and a screen reader names it), the columns'
  tab is called so, `?` in the command line opens the commands' help in a window.
- The web page and the terminal get what only the windows had, as places of their own:
  "What the server can do", the server's notification policy, the server's announcements
  (dismiss, react), the federation's state with Copy / Refresh / Reset, a profile's details
  (counts, since, people you both follow, featured, pinned, moved) and their older posts
  from their own server, a tag on my profile, a new avatar and header, the lists moved up
  and down, About's Copy, the arts mode's note, and a search in the help.
- The web page matches the windows where it didn't: the sidebar's sections fold (one state
  for every interface), a thread has its head (first words, answers, #id, Follow, why it
  comes, every warning at once), Ctrl+F goes "Deeper" and "In every lane", a poll shows how
  many people voted and refreshes, the editor has Preview, Discard (after a question),
  "Another language…", a picture's focus point, the alt-text reminder before sending, the
  chain and #CamelCase line under the text and "an edit keeps the pictures"; the viewer
  saves the original (S), shows it at its own size (Z, double click), leafs with the wheel;
  the windows' tooltips, the ● of the new and "→ @account" (which of mine got it).
- The terminal matches the windows where it didn't: a poll to vote in (`u`: Space, Enter;
  `r` — the results, refresh; how many people, until when), Ctrl+F's `N` (back), `D`
  (deeper), `E` (every lane) and Esc, `J` — to the new, older posts past a lane's end, the
  sidebar's sections fold, a thread's head (answers, `c` — every warning, `s` — follow,
  why it comes), the editor's count, chain and #CamelCase line, Ctrl+R — preview, "Another
  language…", "Discard", the alt-text reminder, "an edit keeps the pictures"; the viewer
  saves the original (`s`); notifications through notify-send or the terminal's own code
  (kitty, Ghostty, WezTerm, foot, iTerm2); ≡ → Debugging (census, trim, tracing, snapshot,
  the config and data folders, every account in one window, "⇄ @account" on a card).
- Qt: a follow request's @name opens the person's profile in fedtail, as GTK's does — no
  more "profile ↗" link out to the browser.
- "Four interfaces" in the feature list (docs/{ru,en}/features.md, and so the site): a table
  of what isn't in all of Qt, GTK, the terminal and the web page, and why — kept honest by a
  test (tests/test_parity.py): a function added to or lost in one interface doesn't pass
  without its line in docs/src/parity.toml.
- Bug reports leave the machine by themselves if you like: `debug.report_repo = "user/repo"`
  (or any git address) — the report from the Debugging menu, `--bug-report` and the nightly
  selfcheck's text zip (`--send`, `--send-full` for the whole) are pushed into that private
  repository over ssh with your own keys, a commit each; the reports already there are never
  downloaded.
- "Report a bug on GitHub…" in the ≡ menu of every interface: a draft issue with the
  version, the system and the latest errors of the log, server addresses, nicknames, IPs,
  tokens and paths replaced by placeholders — shown to read and edit first; then GitHub opens
  with it filled in and you send it yourself.
- "Translate" on every post if you like (`feed.translate_all = true`, as in Fedilab): in your
  own language too, and on posts that give none.
- No tray icon if you don't want one (`ui.tray = false`): notifications then go through the
  desktop only and the cross closes fedtail. Windows: the tray icon no longer stays behind
  after fedtail quits — every restart used to leave one more until the mouse passed over.
- The terminal shows pictures for real and plays video. With the `textual-image` package
  (`pip install textual-image`) pictures go out as sixel (Konsole, WezTerm, foot) or the kitty
  protocol (kitty) — in the lane and full screen; without it, half blocks as before
  (`tui.pictures = "auto"`, `"blocks"`, `"key"`, `"off"`; the old `"inline"` is `"auto"`).
  `v` hands the pictures to `chafa`, `timg` or kitty's `icat` when one is installed, the
  interface stepping aside until Enter (`tui.viewer`). Video and gifs play in `mpv`: a
  window of their own on a desktop, right in the terminal over ssh (sixel, kitty or
  coloured text); no mpv — the browser, and it says so (`tui.video`).
- The terminal: `#abc` or `@name` typed in the command line no longer closes it on
  Textual 2 (Debian 13) — the thread or profile it opened wasn't drawn yet when the line
  gave the focus back; "Reply with a quote" quotes the post's words, not its HTML; a
  redraw or an answer from the server arriving as the terminal closes is dropped quietly
  instead of an error on the way out.
- fedtail-sync gets ready to leave for a repo of its own: its own version (1.0.0) and
  changelog, `--version`, README in both languages with the install guide (moved there from
  docs/*/sync.md), the protocol written down (`syncserver/PROTOCOL.md`), and its own tests
  in `syncserver/tests/` — the standard library only, every line of the server run
  (`syncserver/tools/coverage.py --fail-under 100`, in CI's security job).
- The language of a post: Georgian is named «ქართული (ka)» again, not in Mtavruli capitals
  («Ქართული»): Georgian text has no capital letters.
- fedtail-sync guards itself — it faces the internet and didn't: a silent or trickling
  connection is dropped (`timeout_seconds`; it held a thread for ever), at most
  `max_connections` at once, `requests_per_minute_per_ip`; random tokens can no longer make
  it hammer a fediverse server with checks (`verifications_per_minute_per_ip`,
  `verifications_per_minute`); a body is read only with an honest Content-Length (a
  negative one read to the end of the stream); `total_mb` caps the disk for everyone; the
  token check follows no redirect (one carried the token on) and with `"*"` talks only to
  public addresses, checked on the connected socket; an error inside says "internal error"
  only. Behind cloudflared or nginx, `client_ip_header` (`CF-Connecting-IP`, `X-Real-IP`)
  gives the limits the real address — believed from a loopback peer only. Tests for each
  (`syncserver/tests/test_security.py`) and bandit run in a CI job a release waits for.
- Sync: an action on one device always wins over what it has already seen from the
  others, however their clocks differ (a draft sent on the phone came back from the
  desktop when the desktop's clock was a little ahead).
- A settings window (≡ → Settings, in Qt, GTK, the web page and the terminal): the
  chapters of config.toml on the left, their options as cards on the right — a switch,
  a number, a choice (each choice with what it means), ticks for lists of lanes — with
  the reference's explanation under each, "Default" where it is set otherwise, and a
  search over all of them. The file stays the one place the settings live: a change
  goes into it at once, that one line (a commented-out option is switched on in place,
  a missing one goes into its section with its explanation), the comments and the rest
  stay as they are, the old file is kept as config.toml.bak, and a change that wouldn't
  read back or pass the checks is refused with the file untouched. Edited outside while
  the window is open, the file is read again. Most options are read at start: after a
  change the window offers Restart. What the window shows and does is
  `frontends/common/settings.py` (for the phone too), the line editing
  `core/config_edit.py`.
- Sync is a service of its own now, apart from the fediverse server: it is on when the
  config says where (`sync.url`, or `sync.folder`) and off otherwise. `sync.enabled` and
  `sync.backend` are gone (a config still having them gets a warning, nothing breaks), and
  so is the lookup through `/.well-known/fedtail-sync` on the account's server — in fedtail
  and in fedtail-sync (its `public_url` is ignored with a warning). The right of the status
  bar shows how it goes (Qt, GTK): "⇅ 21:40" — synced then, "⇅ …", "⇅ !" — a problem (the
  tooltip says which), "⇅ off"; About has a "Sync" row everywhere.
- What sync carries is a switch for each in `[sync]`, all on by default (`sync.what` is
  gone; a config still having it gets its list turned into the switches, with a warning):
  `read`, `threads`, and new — `lanes`: the order of lists (servers keep none, so every
  device showed them as they came) and the tag lanes saved from a search; `drafts`: begun
  on one device, finished on another, sent or emptied — gone everywhere (pictures stay on
  the device they were added on); `activity`: notifications dismissed from Activity go on
  every device; `tiles`: which lanes the phone pins as tiles (`Core.pinned_tiles` /
  `set_pinned_tiles`).
- Faster after reading: which posts are read is kept in memory (the sidebar counted every
  lane from the database after each read mark and froze the window for 0.4 s on a big
  profile). A followed thread the server times out on no longer stops the others nor
  shows an error: it waits its turn (it was asked again every poll).
- KDE: a theme's font now reaches labels, lists, buttons and the status bar too (KDE
  gives those classes fonts of its own, and they won: bnw's monospace came out sans
  everywhere but the inputs). A profile or a tag opened while still connecting says
  "connecting…" instead of an error in the window. The terminal: a thread or profile
  that loads after its screen was closed no longer brings the terminal down; j / k step
  over the "new below" line.
- GTK, closer to Qt (the KDE window is the reference): the messenger themes head a
  card "Name (time)" in their colours as Qt does; a theme's fonts that come with fedtail
  (PT Sans, Arimo, Fira Mono…) are loaded and its whole list of families is used — GTK
  took only the first and fontconfig chose for it; the lane header shows the theme's
  pictures for "all read", the funnel and refresh, as Qt.
- Pictures where the desktop has none: on Windows (and macOS) Qt drew no pictures on the
  lanes but one and an empty Refresh button (Windows' own icon engine knows a few names,
  and answers the rest with nothing); fedtail's own drawings stand in there, and in GTK
  wherever the icon theme lacks a picture. GTK's sidebar rows are as dense as Qt's, its
  lane title and "N new" pill the size of Qt's.
- The editor (Qt and GTK): what the post is and what to do with it in one row when there's room
  — the two halves keep to their sides and go into two rows only in a narrow window; the
  character count sits in the text field's own bottom right corner.
- Trying a theme (≡ → Try a theme) stops the videos and the gifs looping in cards first:
  with one decoding, the restyle brought the program down (a segfault in Qt). The Qt tour
  now tries every theme on its living window.
- Themes say which window layout they're made for (layouts = ["split"]: qip, mra, psi);
  ui.themes_by_layout offers in "Try a theme" only those of the layout on — "auto": so in
  releases, every theme in development versions.
- The sidebar's ≡ ↔ ❯: their pictures a third bigger (they looked lost in the buttons).
- Pictures are plain shapes by default ([pictures] style = "silhouette"); the messengers
  keep theirs (mra "agent", qip "qip"). In a development version a picture a theme's set
  lacks (and the desktop's icon theme has not) is drawn from the fallback set in bright
  red, so a theme's gaps are seen at once (FEDTAIL_MARK_MISSING=0: as usual).
- Themes' pictures: nord, contrast, juick, night, paper and solarized draw plain shapes
  (the "silhouette" style) instead of the messengers' glossy buttons; the sidebar's ≡ ↔ ❯
  are plain in every theme (qip's looked like a button on a button); psi's ≡ was Psi's
  "info" picture — now a menu; "whole width" in the system theme is the desktop's own
  "fit to width" (Breeze), not arrows drawn by fedtail.
- night, solarized, pink: their fonts as fixed weights (Source Sans 3, Source Code Pro,
  Nunito — the variable files start at ExtraLight, and Qt drew night's text thin and hard
  to read).
- point: its pictures as on point.im — plain warm grey silhouettes (no blue, no raised
  rim; a menu's lines, an envelope's flap cut out of the shape: [pictures] style =
  "silhouette"), and bigger by the lanes and on the sidebar's top buttons ([shape]
  icon_size, 22 here; 18 elsewhere).
- "＋ to lanes ▾" beside a tag's Follow — in a search's results and on the tag's tab: the
  tag as a lane of its own, or one more tag of a lane of tags already in the sidebar.
- One hashtag kept as a lane of its own: its tab has "＋ to lanes" too (only a group of
  several tags had it), and it lives in the sidebar's "Tags" — Qt, GTK, the web page, the
  terminal.
- Self-check: a step that runs out of time or is stopped takes everything it started
  with it (xvfb-run, the tool, its children): before, only xvfb-run went, and a tour
  went on for hours in a window nobody saw. A run says when tools of earlier runs are
  still alive; --clean stops them.
- About, as cards (Qt and GTK): the opossum and the name, tiles — version, platform,
  architecture, build, commit date, profile — and rows: Python, the toolkit, the commit,
  the accounts, the server and what it runs, the theme, the data folder; "Copy the
  information" for a bug report. The web page and the terminal say the same in rows
  (common/about.py).
- All accounts in one window: the editor has "From @name@server" — a new post from any of
  them (it was the main one only), a reply from another account than the one that got
  the post (found on its server first). The accounts are named whole everywhere — "→
  @name@server" on a card, the "As…" items — the same name on two servers no longer
  looks like one account. Qt, GTK, the web page, the terminal.
- All accounts in one window: switching it on or off no longer leaves nothing running
  (the restart waited 1.5 s, a window still closing was "already running", the new one
  left — now it waits for the old one to be gone). Liking, boosting or replying as
  another account looks the post up there by its id and then by its address, and says
  plainly when that server can't find it.
- A lane opening: the post buttons' widths measured once per kind of button, not on
  every card (0.4–0.5 s of a frozen window).
- A video whose server gives the video itself as its preview (no thumbnails: Akkoma and
  kin) is no longer fetched as a picture (which failed and threw in the picture
  thread); the card shows ▶ — Qt, GTK, the terminal. Empty lines at the start and end of
  a post are gone (a WordPress article came with a screenful of nothing first).
- fedtail's own sounds are 48 kHz (the sound server's rate: a 22 kHz chime could make it
  switch the card's clock, and a USB headset's microphone with it) and are played as
  notifications, not music (pw-play --media-role, paplay media.role=event).
- The tests and the self-check no longer play anything (FEDTAIL_SOUND=off, set by them;
  sound.enabled is "auto" — on — in development versions, and a run played hundreds of
  chimes and beeps through the desktop's sound server).
- Self-check: many tabs opened and closed round after round in Qt, GTK and the terminal
  (tools/tabs_stress.py — leaks, slowing down), each theme's Qt and GTK windows side by
  side with their colours compared (tools/theme_compare.py).
- Sounds, as a part of the theme like its pictures: the messenger themes bring sets of
  their own (qip-retro, mra, psi, point — synthesised by tools/make_sounds.py, ours),
  system plays the desktop's sound theme, terminal and bnw beep. A batch of news chimes
  once with its weightiest sound; `sound.*` says which lanes, the volume, the player,
  signing in and sending (`sound.enabled = "auto"`: on in development versions, off in
  releases; "on" / "off"); a theme's own set is a `sounds/` folder by it. Qt, GTK, the
  terminal (its bell, `tui.sound`) and the web page (in the browser) alike.
  ≡ → Debug → "Test the sound".
- The places beyond the lanes are decided once, without a toolkit (common/places.py):
  search, lists, tags, silence, held-back notifications, scheduled posts, follow
  requests, activity, trends, suggestions, the directory, the server, editing my
  profile, the help, what's new, about, the federation status; a tag, whom someone
  follows, who liked a post, its quotes and versions, a report, the whole text, a
  translation. The web page and the terminal draw them, so they behave alike.
- Web: every place in the ≡ menu; Activity and Follow requests with the windows'
  groups and buttons; ⋯ → Add to list, Read it whole, Translate; every profile button;
  find in the lane (Ctrl+F); the help right on the page; the browser's notifications
  (≡ → Notifications in the browser), in the windows' words.
- Terminal: a post's ⋯ menu (`.`), the ≡ menu (`g`) with every place, search (`/`), a
  profile's buttons under 1…9, the post editor (`w`, Ctrl+S sends, drafts as in the
  windows), find in the lane (Ctrl+F), "sure?" before the risky things; links, menu
  items and profile buttons do what they do in the windows (common/links.py,
  common/profile.py through the terminal's own host).
- The web page and the terminal draw a lane the windows' way (common/lane.py LaneModel):
  the "new below" divider where reading stood, All | Posts only | New, Feed |
  Conversations, the media funnel (the web: a bar over the lane; the terminal: `s`);
  and a card says what the windows' cards say (common/cardtext.py): who boosted it and
  when, edited (→ its versions), old, what it answers, a server filter's fold, the
  quote or why it isn't shown, reactions, "you replied", the conversation's line.
- Web editor: pictures and files (📎, or pasted) with a description each, "sensitive",
  a poll (choices, how long, several or one), later (a date and time), the languages
  of `post.languages`, the server's character limit counted.
- Terminal editor: Ctrl+O — attach a file (with its description), "sensitive", a poll,
  later.
- Qt: a profile's buttons come from common/profile.py too, as in GTK, the web and the
  terminal.
- One scenario, four interfaces (tests/scenario.py, tests/drivers.py,
  tools/behaviour.py): open a lane, the ⋯ menu, like, boost, bookmark, a thread, follow
  and mute a thread, reply, a profile, follow someone, delete, the command line, read up
  to here, all read — through each interface's own way in, held against
  frontends/common; and whether each window has every place a link may ask for. A step
  of `tools/selfcheck.py`, a table in its report.
- Windows: tests that hold Windows' ways on any machine (where the files go, the Start
  menu shortcut's PowerShell, the single-instance pipe's key, the sounds through
  winsound); `tools/windows_check.py` runs docs/en/dev/windows.md on Windows in a profile of
  its own (the self-check's `windows` step).
- Web: a page that left while waiting for news (a reload, a closed tab) no longer
  prints two BrokenPipeError tracebacks on the terminal.

## 0.18.0 — 2026-10-22

- The four interfaces offer the same things. The web page's ⋯ menu of a post is the
  windows' own (common/actions.py: the same items, the same order) and its links are
  done the way the windows do them — editing, delete and redraft, calling into a
  thread, who quoted, blocking a server, report, read up to here; a profile's buttons
  come from one place (common/profile.py) for GTK and the web — the bell, boosts and
  languages in Home, remove from followers, endorse, a private note. GTK caught up with
  Qt on: find in the lane (Ctrl+F), voting in polls, translating a post, reading the
  whole text from its server, an edit's history, reporting, who liked or boosted, the
  quotes of my post, read up to here, editing my profile, quotes that say why they
  can't be shown, "old" and "edited" marks, what each lane is (its tooltip).
  tools/parity.py says what is still missing where.
- Scrolling a long lane fast: the benches measure how often the reader hits the edge
  of what's built and waits (a hand's 6 and 15 screens a second, a fling, the thumb
  dragged); GTK builds ahead faster — while the reader keeps coming to an end, and
  while standing at it.
- Kinder to the server's rate limit. A followed thread that has gone quiet is reread
  less often (quiet an hour — 3× `subs.interval_minutes`, a day — 12×, three days —
  36×), and threads take at most a quarter of what the server still allows: a night
  with 97 followed threads spent 56% of its requests on them and waited 1.7 h of 10
  for the limit. A 429 no longer fails a whole round with "poll failed"; the pause
  after one counts what a full round costs, and waits a little past the server's reset.
- Smoother: the same posts fetched again keep the lanes' caches (the sidebar's counts
  stopped reading the store in the window's thread every round: 0.3–0.6 s stalls); a
  gifv in a Qt card draws at most 12 frames a second, made small first; the dock stops
  asking the X server for the pointer while the window is in the background.
- GTK caught up with Qt in nearly all: a thread's header (subscribe, why its replies
  come, "open every CW" — Qt has it too now), profiles paging back and then from the
  author's own server, pinned and featured posts and people, groups of tags, a tag's
  "feature on my profile", the curtain on Esc, the status line's words, the federation
  status's Copy and Count anew, a picture's focus point, the camelCase hint, text
  selected with "Quote in reply", a contact card on hover (split), the account a post
  came by (merged window), a video player over the window (Gtk.Video) and a tray icon
  (StatusNotifierItem over D-Bus, KDE's and the AppIndicator extension's).
- Qt: a suggestion (@name, #tag, :emoji:) goes in with Enter or Tab — it took a click.
- The server's own groups of notifications (Mastodon 4.3+, `/api/v2/notifications`,
  `activity.server_groups`): 300 likes of one post are one request and one row with its
  count ("and 297 more"), not 300 notifications in eight pages; × dismisses the whole
  group on the server. GoToSocial and older Mastodon: fedtail groups them itself, as
  before (the first 404 settles it).
- A new machine's first start keeps what you left unread elsewhere: posts newer than the
  server's home marker (another fedtail, the server's web) stay unread, and the marker
  isn't moved to "all read" by the new one — a fresh Windows install had moved the
  Linux one's place by fifty posts.
- GTK is quicker on KDE: it talks to the accessibility bus only while a screen reader
  is on (`ui.accessibility = "auto"`; "on" — always): with KDE's bus up and nobody
  reading, the ≡ menu took 2 s to open. The tray answers the panel without rebuilding
  the icon's pixels each time (0.1–0.3 s per new post).
- GTK: pictures in a lane at their full size again — a lane is a ListBox, which gives
  its rows their least height, and a picture's least height was a strip of it (cut, then
  shrunk to 96 px wide); its least height is now its shape's at the width it gets. A
  picture whose size the server didn't say is shown whole, not cut to a square.
- GTK on X11 follows the desktop's 125 % / 150 %: with no text DPI of its own (KDE gives
  GTK apps one only through its GTK settings daemon) it takes X's Xft.dpi, or Plasma's
  scale from kdeglobals — it sat at 100 % beside Qt's 125 %. The text grows; pictures
  and gaps keep their pixels, as in every GTK 4 app on X11. Wayland scales GTK itself.
- GTK: Esc closes the picture viewer (and the video player) wherever the keyboard is —
  the card clicked to open it kept the keys, and Esc closed the lane under it; the
  viewer takes the keys once on screen. ≡ → Quit quits (it ran inside the menu's own
  click and left the window up; the tray's Quit worked). Activity's × at the right end.
  GTK's own containers (pictures, headers, wrapping rows) let their children go when
  they go — they were kept ("Finalizing … still has children left"). The ≡ menu says
  in the log how long it took to make and to show.
- GTK's split layout starts with the roster only, as Qt's (both windows came up), and
  closing the last tab hides the messages window, the roster staying. The
  first menu GTK builds in a run took 1.5–2 s on KDE (later ones: milliseconds), and the
  click's release, handled after that freeze, closed the menu it had opened — ≡ took a
  double click. Every ≡ is now made after start, timed in the log; one click opens it.
- Debug → Federation status works again in GTK and the web: someone waiting to go into
  a list (a name and a link) was taken for a hashtag on the way to the window.
- A Qt window started in a terminal where the tests had set `QT_QPA_PLATFORM=offscreen`
  showed nowhere (Windows): fedtail now drops that setting for its window and says so.
  GoToSocial isn't asked for grouped notifications or a user's server blocks any more
  (it has neither: a 404 at every start).
- fedtail from the source says at start where its logs are (`fedtail: logs in …`);
  docs/en/dev/windows.md has every Windows path and the commands to open and follow the log.
- The debugging corner of the status bar says the same in Qt and GTK, in one order:
  theme · toolkit and version · style · font · display · scale · build (Qt's had an
  empty "· ·" where its style's name was).
- docs/en/dev/windows.md: fedtail on Windows from the source — Python and git by winget, the
  packages, running, the tests as CI runs them, the selfcheck; tests/test_windows_doc.py
  keeps it the same as CI and the code.
- GTK: pictures and files go into a post by dragging them onto the editor or pasting
  them (Ctrl+V — a file manager's copied files, a screenshot; Ctrl+Shift+V — always as
  text); dropped on the window, they start a new post (as in Qt). The deb package
  recommends GTK 4 (`python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`), and the GTK window
  is "fedtail (GTK)" on a right click on the menu entry. GTK is no longer "partly".
- The chosen lane shows in dark themes left at "auto" (Adwaita dark, Breeze dark): its
  row was nearly the sidebar's own colour.
- Qt opens a lane faster: a lane of 41–80 posts no longer builds every card at once
  (one first build, 40 by default, as for longer ones), and a post's ⋯ menu is made
  when it's first opened, not an empty one with every card.
- The gallery (`tools/gallery.py`) and the README's screenshots are made only when
  asked: `selfcheck.py --only gallery`, and CI's screenshots job by hand (Actions → CI
  → Run workflow) — not every night and every push.
- GTK 4.18: no "reported min height … natural height" warnings by the thousand — a
  card, a lane's header, a profile's top and a person's row are no longer horizontal
  boxes with wrapping text in them (4.18 takes such a box's least height at its least
  width); `gtk/measure.py` checks for it, on 4.14 too.
- GTK in a narrow window (or with big fonts): the lane never goes past the window's
  edge any more — a picture narrows with the window, its shape kept (it asked for its
  full width and held the lane wider); the words on a post's buttons end in "…"; the
  lane's header wraps its buttons to a second row instead of cutting the last ones;
  the sidebar's rows have no theme's pills under them (Breeze), the name in it is never
  cut to "М…"; Clear in Activity; a tag's tab
  with "Feature on my profile"; a picture's right-click menu (save, open, copy link);
  a poll's "refresh".
- selfcheck: `--night` runs every window on a display of its own (xvfb-run) — a locked
  screen made GTK draw a frame a second and the benches meaningless; the tests run
  there too, away from the desktop's focus. The window is tried at the sizes of real
  screens up to 4K, portrait too, at shares of the screen (half, quarter, three
  quarters, half the height), and with its bottom dragged as well as its side; at scale
  1.5 and 2 (Qt), twice the pixels and the text 1.5× (GTK) — `sizes.txt` says what each
  did. `gtk_bench --measure` names a widget that tells GTK a least height above its
  natural one.
- Sync between your devices: read marks you made and threads you followed, left or
  muted travel to your other devices (`sync.*`, off by default; docs/en/sync.md). Each
  device keeps a journal, sealed with AES-256-GCM under a key only your devices have, and
  exchanges it through a fedtail-sync server or a folder they all see (a NAS share, WebDAV
  mounted, Syncthing). Marks fedtail makes by itself (the first run, older history) stay
  home. The server finds itself through `/.well-known/fedtail-sync` on your server; it is
  given a separate token limited to `read:accounts`, never the main one. New terminal
  command `fedtail sync status|key|join|login|now`. Needs the `cryptography` package
  (Debian: python3-cryptography) — only for sync.
- fedtail-sync: the server for it, one file of the standard library
  (`syncserver/fedtail_sync.py`): who is who is asked of each account's own server, which
  servers' people are served is a list (or anyone's), a quota and a request limit per
  account; it can't read what it keeps.
- Short post names are derived from the post's id (`#kq3zt`, five characters, longer
  where two known posts begin alike): the same post has the same name on every device.
  Names given earlier by the counter (`#a3f`) stay with their posts and still work.
- tools/push_probe.py: does your server push? Subscribes your account to Web Push with
  an endpoint on an ntfy topic, decrypts what comes (RFC 8291) and shows it, then
  unsubscribes — the check before relying on UnifiedPush on a phone.

- Windows: `latest.log` exists there too — a hard link to the current log where symlinks
  aren't allowed (no developer mode), so the file the docs tell you to send is there.
  The tests pass on Windows with pip's user installs and its connection resets.

- tools/gallery.py: the pictures for the site's gallery and the docs — every interface
  on one made-up world (tools/showcase.py, now shared by Qt's and GTK's screenshots),
  with gallery.toml (titles and a line each, Russian and English); part of
  selfcheck --night. The walks also take your own themes (~/.config/fedtail/themes),
  never published.
- The split layout: the roster stands beside the conversation window, never over it —
  on its left or right where the screen has room, else at the screen's edge with the
  window narrowed beside it (a place saved over the window is corrected once).
- selfcheck: stopped by hand (Ctrl+C, the terminal closed, killed) it says so in its
  report and makes no zip; --clean removes such runs and the tools' leftover temporary
  folders (--clean all: every run); the temporary folders — with --real a copy of your
  login among them — are removed after every run.
- The web interface writes dates and times in fedtail's language, not the browser's.
- GTK: the lanes' counters are pills, not ovals as high as the row. A lane's column
  measured its cards narrower than they can be ("needs at least 814", some 20 000
  warnings in a night's log, and heights worked out for a width never given); the
  desktop theme's scroll bars no longer warn of negative sizes either.
- selfcheck --night: everything in one run, for the night — the tests (each by name,
  the slowest, and where a hung one stood), the walks of every interface, the window at
  six sizes with what each cut or pushed out, its edge and the sidebar's dragged and
  timed, widgets left alive after a window closed, the benches, the parity of the four
  interfaces (tools/parity.py), and then the same on your own account (read-only,
  screenshots blurred). docs/en/dev/testplan.md: what is checked, what is left to the eye.
- From the first night's report: Qt's own buttons (Close, Cancel) in the interface's
  language; nord's and night's outline pictures (a star, an @, refresh) were the
  background's colour — an outline too close to it is drawn light; check boxes and
  radio buttons in the theme's colours (bnw's empty box was as green as a ticked one);
  the sidebar's scroll bar in the theme's colours; the terminal theme's name in the
  sidebar cut to "mi" — now with "…"; a lane's title keeps a few letters; trying a
  theme no longer restyles the cards it is about to throw away (columns: 6–9 s); the
  help's sticky header after its page changed; events after the database closed.
  GTK: the Write button's words were the sidebar's colour (invisible in terminal and
  point) and now the theme's, as in Qt; the sidebar's name and avatar as the theme
  says; tab titles, the lane title and the chosen filter readable under a dark desktop.
  Terminal: a picture coming back while the app closed hung it (and the test suite);
  the first picture that fails to load is said in the log.
- tools/selfcheck.py: every check the dev tools have, on your own machine, in one go —
  the tests; a walk through the Qt window (every theme, the split layout, every menu
  with the list of what's in it, every dialog the ≡ menu opens; tools/qt_tour.py); how
  fast Qt and GTK are (tools/qt_bench.py, gtk_bench.py); GTK screenshots; the terminal
  interface (every lane, the thread, the profile, the pictures screen, every key, and
  whether pictures are drawn; tools/tui_check.py); the web page in a real browser
  (every lane, the ≡ and ⋯ menus, the editor, the picture viewer, a phone's width, the
  page's console; tools/web_check.py). What can't run there is skipped; at the end a
  report.md and one zip to send back. Linux, Windows, macOS. The Qt walk opens every
  menu the window has — each button's, each right click's (caught instead of waiting
  for a click), the roster's, the tray's — and says which are empty; --maximized,
  --pace for a slow machine. The tools take --real[=PROFILE]: your own account and
  database instead of the fake server, from a copy of the profile, the server only
  asked (every request but GET stopped before it goes out).
- GTK, faster: a post's text is one Pango layout now, not a wrapping label (that laid
  the text out several times to learn its size: nine tenths of what a card cost), so a
  lane lays out four times faster; cards come a batch a frame, as many as the last
  frame had room for (several batches between two frames made one long freeze); marking
  posts read while scrolling no longer rebuilds the whole lane each time (only the marks
  change, as in Qt); a long lane keeps 120 cards at most (every one is laid out again at
  each scroll step); the first card on screen is found by bisection, not row by row.
  On a fake lane of 2000 posts under Xvfb: opening a lane 1.4 s → 0.4 s, the longest
  freeze 390 → 80 ms; scrolling it no longer stops for a third of a second at a time.
- tools/gtk_bench.py: how fast the GTK window is — the start, opening lanes, scrolling,
  the menu, the editor, themes, the roster and tabs — on a fake server, in every layout,
  with --profile for where the time goes. Run it on your desktop: the accessibility bus,
  fonts and GPU are half of it.
- The point theme's pictures are point.im's look — plain grey-blue silhouettes, a
  megaphone for the feed, a house for my posts, a speech bubble for replies — drawn for
  fedtail; [pictures] color gives all of a theme's pictures one colour.
- The copies of the built-in themes (and their pictures) are made once a run and only
  when changed — every start and every theme tried read them all.
- The pictures on the buttons are the theme's. [shape] icons says where they come from:
  "desktop" — the desktop's icon theme (system, debug), "own" — a set of the theme's own,
  "words" — none (terminal, bnw); ui.icons may choose otherwise, "additional" putting the
  messengers' pictures outside the split layout too. A theme's set is a folder next to
  it, themes/<theme>/icons/, a file a picture; what it lacks comes from the themes it
  inherits, then from [pictures] from (mra-blue takes mra's), then from an emergency set
  — and the log says which pictures the theme lacked. Pictures are standard (the menu,
  the width, the columns, the lanes, the buttons under a post, who sees it — there
  whenever the theme has pictures) or the messengers' (the split layout's). Every
  built-in theme but those four has its whole set now, 21 new pictures among them (the
  lanes, ↔, ❯, ✕, ⋯, refresh, mark read…). ui.additional_icons is ui.icons now
  ("layout" → "theme", "all" → "additional", "none" → "words"; the config is updated
  by itself); a theme's old shape.icons = true / false, lane_icons and icon_set are
  read the new way.
- GTK draws the theme's pictures too, as Qt does: ≡ ↔ ❯, the lanes, a post's buttons and
  who sees it, ⋯, the input line, the author's bar, the roster, a silhouette for nobody
  (SVG through gdk-pixbuf's loader, librsvg; without it PNGs only).
- Qt: a status bar message no longer lies over the profile's name at the left.
- GTK: pictures in a post keep their shape, as in Qt — one alone ui.image_height tall
  (not a strip cut to 180 px), several as tiles three in a row; a gif or a video with ▶;
  "sensitive" ones covered until clicked. A click opens the picture viewer over the
  window (ui.image_viewer): ← → to flip, Z or a double click for 100 %, S to save, O to
  the browser, Esc or a click to close.
- GTK: the help is a panel over the lanes (as the editor and as in Qt), not a window:
  contents on the left, back and forward, a search over all pages, links to headings.
- GTK, split: the messages window's tabs in as many rows as they take (shape.tab_rows),
  over the author bar, as in Qt; another theme tried redraws the lanes' tabs too.
- GTK: ≡ → Quit quits (in the split layout it only hid the messages window); the
  command line sits under the lanes, beside the sidebar, not under the whole window.
- GTK: desktop notifications went nowhere — PyGObject knows Gio.Notification's
  set_default_action_and_target_value by another name; both are tried now.
- GTK on KDE: the ≡ menu is made when it first opens and again only when it changed (it
  held the start for 4.7 s and each opening for most of a second); the roster's rows
  no longer set their tooltips and texts anew on every count (a third of a second each).
- GTK: the status bar's corner says the theme tried, not the one started with.
- Help → "The look" tells where your own themes live and how fedtail reads them (from
  `~/.config/fedtail/themes/`, never copied; `builtin/` is only a sample), and how to keep
  them in a git repository of your own; the README in the themes folder says the same.

- GTK, the split layout in the Mail.ru Agent themes (mra…): the other side's face in a
  column beside the posts, the name under it, a click — the profile; in a talk whom I
  talk to, over a lane the author under the pointer.
- "You replied" shows under the post at once after replying from fedtail (it waited for
  something else to change in that lane — in "Replies to me", often for good).
- The split layout's input line completes #tags, @names and :emoji: as the Compose window
  does (one completer for both now).
- A development version writes into its log, at the start of every session, all that
  `--bug-report` would add — the versions (fedtail, Python, Qt or GTK, libadwaita), the
  system, the options changed from the defaults and `config.toml` itself — so the log
  alone is enough to send.
- The GTK window grows up (stage 2–3 of docs/en/dev/gtk.md): faces, pictures, the poll's
  results, the quoted post, the link's card, "you replied" under a post; the buttons
  and the ⋯ menu of a post — the same as in Qt (copy the link, the #id or the address,
  quote, call into the thread, bookmark, read up to here, mute or follow the thread,
  mute, block, report, edit, pin, delete, delete and redraft), each risky one asked
  first; writing — a new post, a reply, a quote, a call, my post corrected — with drafts
  kept, who sees it, the warning, #tags and @names completed by Tab, Ctrl+Enter to send;
  pictures with descriptions (a reminder when one has none; made to fit the server) or a
  poll; the Point command line (Ctrl+L) with ↑ ↓; a profile in a tab (face, bio, fields,
  Follow, Mention, posts); Activity (a row per kind and post, approve or reject, ×) and
  follow requests; desktop notifications whose click opens the thread or the lane; a
  fediverse link opens the post or the profile here.
- Inside: what a link does, which actions a post offers, the rules of writing and the
  command line now live once in `frontends/common/`, for both windows; Qt's theme
  colours come from `frontends/palette.py`. The Qt window behaves as before. The command
  line's "#abc text" for a post not known here goes out as a post, as before, only in the
  windows; the terminal and the web page still say there's no such post.
- The GTK window: a lane's header has what Qt's has — everything / posts only / what's
  new, as conversations, and the funnel (only posts with pictures, video…, boosts or
  not); sidebar sections fold away, showing what's unread in them; pictures come from
  the same disk cache as in Qt, read small, asked again when a server was only busy,
  fetched ahead for posts just come; "mark read on open" works there too.
- The GTK window, after the first real try: a ☰ menu (write, refresh, all read, the
  command line, my profile, the config, themes, data and log folders, about, quit); the
  lanes no longer go past the window's edge (ui.max_width was taken for the narrowest
  width); building cards no longer holds the window for a third of a second at a time
  on KDE (tooltips are given when asked for — setting them ahead went over the
  accessibility bus); the view is held still until new cards above are laid out (it
  scrolled by itself on a slow frame); the sidebar counts no "unread" in Local and
  Federated; the server's "slow down" is a sentence, not `{'until': …}`, and status
  lines go away after a while; WebP pictures (GoToSocial's) are read through Pillow when
  GTK can't (else the log says to install webp-pixbuf-loader).
- The GTK window, by the Qt one (screenshots of it as the reference): the sidebar's head
  — my face and name (a click: my profile; a right click: the other accounts), ≡ ↔ ❯,
  a big Write, "Find people, tags…", "+" by Lists, the version at the foot; ↔ posts
  across the window (remembered), ❯ lanes side by side (or `ui.layout = "columns"`),
  each column with ‹ › ✕; the lane's header as Qt's (All | Posts only | New, ↓ To new,
  Mark all read, ▾ Show, Refresh); the ≡ menu item for item — for the tender and
  sensitive (word filters, muted, blocked, blocked servers, filtered notifications),
  scheduled posts, find people (suggestions, the directory, trends), account and
  server (switch, all in one window, add, make main, log in again, log out, about the
  server and what it can do), config, themes, try a theme, data, the whole Debugging
  submenu, help, What's this?, about; the editor a panel over the window (⤡ bigger,
  the post's language, Later, Preview, Discard, Close — the draft stays; one at a
  time), or a window with `ui.compose = "window"`; a search tab, a tag's posts; the
  card's header with who boosted and when, the visibility, "edited"; a profile with
  its banner, Copy handle, Open in browser; the status bar with the account. A warning
  is open or closed as `ui.expand_cw` / `ui.arts_mode` say (the pictures were hidden
  under it), a post folded by a "warn" filter stays closed; `--layout split` says the
  GTK window has no such layout yet. Switching accounts from a `--ui gtk` window opens
  the other one in GTK too.
- The split layout in the GTK window (`--layout split`, `ui.layout = "split"`): the
  roster in a window of its own — groups that fold, rows with the face and the newest
  post, the search (Enter: the only one found, or a search of the server), a double
  click opens, "mark all read", the look (⚙), ≡ and the accounts at the bottom; the
  messages window — a tab per lane, thread, profile and private talk; over a lane the
  author of the post under the pointer (Follow, write privately, the profile); the
  input line at the bottom answering the thread in front, writing privately in a talk,
  taking Point commands on Enter. Closing the messages window keeps the roster; closing
  the roster closes fedtail.
- Qt, split layout: the author bar's Follow / Unfollow keeps one width — it no longer
  jumps as the post under the cursor changes.
- Both windows say "Getting the lanes from the server…" until the first round of
  polling is in — on a slow connection the empty lanes looked broken.
- Inside: the rest of the decisions moved out of the Qt window into `frontends/common/`
  — what a lane shows (the divider, the filters, conversations, where reading starts,
  what counts as read), the picture cache, the sidebar's numbers and folds, the split
  layout's input line and the roster's rows, Ctrl+F, the server's page and the probe's
  table, the profile editor's changes; the announcements bar and the Silence dialog get
  `fedtail.model` objects, not the server's JSON. The Qt window behaves as before.
- fedtail has an app id, `online.dmesg.fedtail` (from the project's website): the menu
  entry is now `online.dmesg.fedtail.desktop` (another profile's:
  `online.dmesg.fedtail.<profile>.desktop`), and both the Qt and the GTK window say they
  are it — on Wayland that is how the task bar finds the icon. Every start of a window
  checks the entry and the icon are there and point to this fedtail (a moved checkout, a
  new one-file build) and mends them; the old `fedtail.desktop` goes (only one fedtail
  made). With the deb package its own entry is the one. `ui.desktop_entry = false` —
  leave the menu alone.
- The GTK window (0.17's frame) no longer freezes at the start on a big lane (it
  built a card for every post stored — seconds per thousand, the desktop stuck under a
  frozen title bar): only a window of posts around where reading starts is built, in
  small batches between frames, more as the view nears an end, the far end let go past
  a few hundred; lanes not on screen catch up when shown. Outside GNOME it keeps the
  desktop's own frame (`ui.gtk_headerbar = auto | on | off`), and the freeze watchdog
  and stall meter of the debug log work for GTK too.

## 0.17.1 — 2026-10-21

- The split layout's input line says in words where a post goes and who will see it:
  "into the thread, a reply to andy · seen by: followers", "new post · seen by: all",
  "✉ privately to sn4il · seen by: only those mentioned". In a thread it answers the
  post you came for, else the thread's newest — not the last branch of the tree.
- A private message sent from a talk's tab shows in the talk at once (it opened a
  thread tab of its own and the talk waited for the next poll).
- A quick scroll reads what it went over: a post the screen passed whole while you
  scrolled by the wheel or the keys is read, without dwelling on each (a jump — the
  scroll bar dragged far, End — still counts nothing). The check looks at the cards on
  screen only, not at every card of the lane.
- Less CPU with the split layout open for long: the roster is worked out in the
  background (it read every lane on the window's thread, a third of a second each
  time), and the face over a lane finds the post under the pointer or the lowest whole
  one without measuring every card of the lane twice a second.

## 0.17.0 — 2026-10-21

- **A GTK 4 window, the frame of it** (`fedtail --ui gtk`, or `ui.frontend = "gtk"`;
  `ui.adwaita = auto | on | off` — libadwaita if installed, required, or never): login,
  the lanes in their groups with unread counts, posts as cards with what they answer,
  the content warning and attachments, seen posts marked read, "All read", "earlier",
  threads in tabs, ★ and ♻, every fedtail theme. The rest comes stage by stage
  (docs/en/dev/gtk.md); needs `python3-gi gir1.2-gtk-4.0`. Inside: the theme colours
  (`frontends/palette.py`) and post text for GTK labels (`frontends/pango.py`) are
  worked out without a toolkit, ready for Qt to share.
- The server's rate limit is kept to: fedtail reads its X-RateLimit headers, keeps
  quiet once fewer requests are left than two poll rounds and a reserve, until the
  server's window starts anew, and asks nothing while it is spent. One line in the
  status bar says until when — instead of a "429" for every lane, every round (as on
  GoToSocial with a few lists, the live stream waking the poller every few seconds).
- **The split layout** (`ui.layout = "split"`, for one run `fedtail --layout split`;
  `"qip"`, its first name, is still understood) — fedtail as a messenger of the 2000s,
  QIP, the Mail.ru Agent or Psi (docs/en/dev/layouts.md):
  - The **roster**, a narrow window of its own, and fedtail starts with it alone: who I
    am and what's new in Activity on top, a search line, then folding groups — the
    lanes, followed threads and private talks ("Threads", "Talks", the freshest
    `ui.roster_threads`), and "People": whom I follow who follows me back (asked once a
    day). A group says "(15)", or "(2/15)" when two of its items have something new.
    Each item has its count, a line of its newest post and a face. A double click (or
    Enter) opens it; hovering a person shows their card, as QIP did. At the bottom: the
    menu, the accounts, and ⚙ for how it looks — compact, without the header, the
    search or the buttons, only what's new, without groups, above other windows
    (`ui.roster_on_top`). Closing the roster closes fedtail (to the tray with
    `ui.close_to_tray`); the tray icon hides and brings back both windows.
  - The **messages window** is the main one, without the sidebar: every lane, thread,
    profile and talk opened is a tab of its own, in more rows when they don't fit; ×,
    the middle button or Esc close one, and with the last the window goes
    (`ui.split_tabs`: whether it keeps its tabs for next time). A person opens as a
    talk with only our private messages.
  - The **input line** is always under the posts, a bar that drags between them: in a
    thread it answers the thread (a private talk stays private), in a talk it writes to
    that person privately, in a lane it writes a new post; Reply on a card goes there
    too. Who sees it, a content warning, pictures, the language; it also runs the
    command line's commands (`ui.dock_commands`: "#a3f text", "! #a3f", "?" — Enter).
  - **Faces** (`ui.faces`): over a lane, in one line, the author of the post under the
    pointer (or the cursor, or the newest whole on screen) — name, address, whether we
    follow each other, Follow, Add to list, a private message, the profile; by the input
    line, whom I write to. The Agent's themes put them in a column on the right instead,
    theirs by the posts and mine by the input line. A grey silhouette stands in for a
    face not there yet.
  - **Pictures on buttons** of fedtail's own, drawn the theme's way
    (`ui.additional_icons = "layout" | "all" | "none"`, in the split layout by default):
    the input line's, the author's bar's, the roster's, a post's Reply, Favourite, Boost,
    Thread and Bookmark and who sees it. A flower for a person in the QIP themes, an "@"
    in the Agent's, a star in Psi's; the `psi` theme brings Psi+'s own pictures (the
    Crystal and Stellar iconsets, GPL).
- **The messenger themes**, made from the originals' screenshots, square or nearly
  square, glossy where they were: `qip-retro` (QIP under Windows XP: beige, white panes
  in grey-blue frames, XP tabs with an orange line), `qip-modern` (QIP Infium: pale blue,
  the posts on a white-to-blue diagonal), `mra`, `mra-blue`, `mra-green`, `mra-violet`
  (the Mail.ru Agent's skins), `psi` (Psi+ on KDE). They write a post as a message:
  "Name (15:25:43 23/06/2007)" over it, mine and the others' in colours of their own.
  New theme keys for any theme: `shape.card_header = "chat"`, `colors.chat_me` /
  `chat_them`, `words.chat` / `chat_date`; for the split layout `shape.faces`,
  `roster_rows`, `roster_face`, `tab_rows`, `icon_set`, `colors.view_end`, `window_end`,
  `button_end`, `header_end`, `tab_mark`, `words.roster_group` / `roster_group_quiet`.
  Their colours and pictures are fedtail's own, in the spirit, not anyone's skin.
- `fedtail --layout single|columns|split` and `--theme NAME`: the layout or the theme for
  one run, the config untouched; an account switched to from there gets them too.
- Less freezing: trying a theme no longer stops the window for seconds (the lanes out of
  sight let their cards go first), the split layout no longer lays the whole window out
  twice a second, and the roster fills in a batch of rows at a time.
- In the split layout Help (and the big Compose window) from the roster's menu brings
  the messages window up: they are panels of it, and stayed invisible while it was
  closed.
- `--update-config` moves an option that changed its name (`ui.button_icons` of the 0.17
  development builds is `ui.additional_icons`), and the start says what it is now
  instead of "unknown key".
- Less freezing after a poll: the lanes and their unread counts are worked out in the
  poll thread before the window hears of news, and unread counts are cached until a
  lane or a read mark changes — the sidebar asked every lane after every event, reading
  thousands of stored posts between two frames (250 ms to a second).
- `fedtail --layout single|columns|split` and `--theme NAME`: the layout or the theme for
  one run, the config untouched.
- Help gets a "Server and federation" part under its contents: About the server, What it
  can do (the probe) and Federation status open on its right side, as pages of the same
  panel — the settings-like window of Psi or QIP, only for what to read, not to set
  (settings stay a file).
- fedtail took GoToSocial 0.22 for Mastodon: its version says only "0.22.1+git-…".
  Now it reads the instance document's `source_url` and GoToSocial's own keys, and asks
  the server's nodeinfo when still unsure — so × in Activity hides here instead of
  asking the server, and the probe says right what GoToSocial can't. Translating is
  read from the newer instance document (Mastodon said "no" before when it could).
- Server info → What it can do: "Copy" (a Markdown table, for a bug report or a chat),
  "Save…" to a file, Ctrl+C copies the selected rows.
- ≡ → Server info has a "What it can do" tab: "Check" asks the server about two dozen
  features with harmless one-item GETs (a few seconds, in the background) and lists yes /
  no / closed to me / unclear, with the limits; the last check is kept. The answers also
  decide which buttons fedtail offers.
- Help: in the comparison tables the header row stays on top while the rows scroll under
  it, so a ✓ always says whose it is.
- Every built-in theme comes with its fonts (all SIL OFL 1.1, all with Cyrillic, nothing
  to install): PT Serif in `paper`, IBM Plex Mono in `terminal`, IBM Plex Sans in `nord`,
  Source Sans 3 and Source Code Pro in `night` and `solarized`, Open Sans in `point`,
  Arimo in `juick`, Comfortaa and Nunito in `pink`, PT Sans in `contrast`, Fira Mono in
  `bnw` where DejaVu is missing. `ui.fonts` chooses whose: the theme's (default), the
  system's, or your own (`ui.font`, `ui.mono_font` — any of these by name too).
- × on a row of Activity on GoToSocial: the server can't dismiss one notification (only
  clear them all), and fedtail used to ask it anyway — a 404 in the log, the row stayed,
  and "Clear" went missing until a restart. Now × hides the row here (and stays hidden
  after the next fetch); on Mastodon it goes from the server too. It never mutes
  anything: new ones of the kind come as before. The tooltip says which it is.
- Fonts of your own: `ui.fonts = "custom"` with `ui.font` (a list works: the first one
  there), `ui.mono_font` for #ids. Fonts needn't be installed: .ttf / .otf in
  `~/.config/fedtail/fonts/` are picked up at start, and a theme can bring its own
  (`[font] files`, next to its .toml).
- Muting a thread works on GoToSocial: the server can't, so fedtail mutes it itself — the
  thread's mentions are dropped as they come (replies there tag everyone in the thread by
  themselves), even replies under posts fedtail never saw, and what came before leaves
  the lanes. It used to say "Your server can't do that" and hide the item; now the item
  is always in the ⋯ menu, and on Mastodon it asks the server as well.
- Reply with quotes: ⋯ → "Reply with quote" puts the post (or what's selected in it) into
  the reply as a `> ` quote; a right click on selected text → "Quote in reply". With the
  reply already open the quote goes where the cursor is, so a long post can be answered
  sentence by sentence without copying. `post.quote_prefix`.
- Web: the ≡ menu (write, my profile, refresh, all read, help, keys, about) and a post's
  ⋯ menu (reply with quote, subscribe / leave / mute the thread, copy the link, delete my
  post); `q` replies with a quote. A reply shows the whole post it answers: select a piece,
  "❝ Quote in reply" puts it at the cursor. The picture viewer goes through the post's
  pictures with ← / → and the side buttons.
- Terminal interface: `p` shows the profile for real — the screen used to scroll its header
  away as the first post was highlighted, and what stayed looked like a lane. Lanes by
  keyboard: `[` / `]`, `1`…`9`, `h` into the lane list (`j` / `k` move there), `l` back;
  Tab now really goes between lanes and posts. "Activity" and "Follow requests" show
  their rows (they were empty: they aren't post lanes); `a` / `d` answer a request.
  Pictures drawn with half blocks: a post's first one small in the lane
  (`tui.pictures`, `tui.picture_rows`), `v` — all of them full screen, ← / →, `o` — the
  original in the browser. Needs Pillow (`python3-pil`).
- Unsubscribing from a thread mutes its mentions too (`subs.leave_mutes`, on): leaving
  used to stop "Subscriptions" only, while auto-tagged replies kept coming.

- The opossum holding its own tail is back: the app's icon (`ui.app_icon`) and the picture
  in About. It is a sticker from an official Telegram sticker pack.
- The config's reference comes in English too: `config.example.en.toml` lies next to
  `config.example.ru.toml` (the old `config.example.toml` goes). A new config is written in
  the desktop's language; `--update-config` and `--rebuild-config` keep the language your
  file is in.
- Help inside: ≡ → "Help" opens it as a panel over the lanes, like the compose panel —
  the contents on the left, search through it all, Back and Forward. Short pages, each
  ending in "In detail →" links into the full feature list and the settings reference,
  which come with it and work offline. In Russian and in English.
- ≡ → "What's this?": point the mouse at a button and get the longer story — what it
  does, which config key changes it, where the help says more. For the session from the
  menu, or from the start with `ui.whats_this`. Neither has a key: F1 is next to Esc.
  The hint is a window of its own, beside the cursor and never under it: a long Qt
  tooltip there was hidden and shown again round and round until the window froze.
- The docs come in Russian and English, `docs/ru/` and `docs/en/`: the feature list now says
  since which version each feature is there, and fedtail next to thirteen other clients is
  one matrix a chapter (`comparison.md`). All of it, the config reference and the shared
  pieces of the READMEs are built by `tools/docs_build.py`; a test keeps them in step.

- The database no longer grows for ever. Every `storage.gc_hours` (6) fedtail forgets posts
  nothing points at any more — no lane, followed thread, activity entry or reply draft;
  boosted and quoted posts and parents of kept ones up the thread stay, and so do your own
  posts and anything stored in the last `storage.grace_hours` (48). A forgotten post is
  fetched again when needed; short ids are kept for good. The file really shrinks
  (incremental vacuum; an older file is converted once, at the first start — it may take
  a moment). If it is still over `storage.max_mb` (1 GB), lanes get shorter until it fits
  and grow back later. New `[storage]` options; `storage gc:` lines in the log.
- Pictures that didn't come no longer stay blank until a restart. When the server answered
  with an error twice (busy, restarting, still fetching a remote post's media), fedtail
  asks again by itself in 1, 5 and 30 minutes for the cards still waiting, and a card
  that gave up gets the picture when it comes. The log now says the HTTP status
  ("HTTP 503") instead of just "HTTPError".
- The web interface, rebuilt: a "Write" button (and ✎ on a phone) opens a composer with a
  content warning, who sees it, the language and a character count; drafts are kept in
  the browser. Replies start with the right @names and never go wider than what they
  answer. Pictures in a grid with a viewer, video, gifs and audio; a picture that doesn't
  come says so, links to the original and is tried again later. Polls with bars and
  voting, link cards, quotes, custom emoji, a profile's header, fields with ✓ verified,
  follow / requested. "More" at the end of a lane loads older posts. The command line has
  a line of its own. Lanes slide in on a phone; light and dark follow the system.
- Inside: the terminal, the TUI and the web interface work on fedtail's own data model
  (`fedtail/model`, `fedtail/core/view.py`) instead of the server's JSON — stage 2 of
  docs/en/dev/protocols.md; so does the Qt window, all of it. The Mastodon API itself lives in
  `fedtail/protocols/mastodon/` behind a protocol interface (stage 3), and what the server
  can do is kept in one place (stage 4): a button the server refuses goes at once, and
  stays gone after a reconnect. Nothing changes in what they
  show, except that the web page and `fedtail post -v` say "followers" (`private` still
  works).

## 0.16.0 — 2026-10-19

- Faster reading deep into big lanes: stored posts are paged from where the last page
  ended instead of skipping the newer ones again each time, and text is pulled out of a
  post's HTML with patterns compiled once. Ctrl+F "in every lane" goes through lanes that
  share a source together, each post parsed and matched once — on 20 000 stored posts
  it takes 0.4 s instead of 0.9 s; "Deeper" and long lanes gain the same way.

- A click on the time slider of a video or an audio jumps right there; it used to move
  only one step towards the click, and only dragging the handle really seeked.

- Sending no longer gives up after 30 seconds on a slow server: it waits `post.send_timeout`
  (90 s). When the answer still doesn't come, fedtail looks among your latest posts first —
  the post was usually made, only the answer lost — and treats it as sent if it's there.
  If it can't tell, the message says "maybe sent: look before retrying" instead of a raw
  "Read timed out". Each post carries an Idempotency-Key: Mastodon gives back the post
  already made instead of a double when the same text is sent again.

- Ctrl+F "In every lane": a tick in the find bar searches everything stored in every lane
  at once; the counter says which lane the match is in, and the next match opens its lane
  and loads it down to the post. Ctrl+F pressed again in the find bar goes to the next
  match, as in a browser (Enter, ↓ and F3 still do too).

- The `point` theme closer to point.im: square avatars, the name bold in dark blue with
  @address · date under it, the post's #id under the text on the left with the number of
  replies (`#a3f | 4`), the buttons on the right, a hatched grey band behind the lane's
  and the new post's title, solid and clearer lines between posts, a dark "Create"
  button. New theme keys for any theme: `shape.avatar_shape` (circle,
  square, rounded), `shape.card_header = "stacked"`, `shape.short_id` (header, footer),
  `shape.actions_align` (left, right), `shape.rule` (solid, dashed), `shape.header_stripes`,
  `shape.header_bar` (a band above the title strip, point.im's dark top bar),
  `colors.primary` / `on_primary`, `colors.header`, `colors.header_bar`, `colors.name`.
- The lane's and the new post's title strip is tinted with the theme's accent in every
  theme (`colors.header` left at "auto"), with a 3 px band of the accent above it
  (`shape.header_bar`, 0 turns it off); bnw and contrast keep a white strip under the band.
  Lines between posts in "rule" style are solid by default (`terminal` keeps its dashes).
- "Add to list" for someone you don't follow: the lists are dead now, not just greyed —
  a click on them does nothing at all (it used to send a request the server refused and
  stall the window). While fedtail is still asking the server whether you follow them,
  the lists are dead too, with "Checking…" above them, instead of looking clickable.
- Video is decoded by the processor by default (`ui.video_decode = "software"`): on some
  cards Qt's hardware decoding fails ("CUDA_ERROR_INVALID_VALUE", "more than 32 decode
  surfaces") and the video stutters or stalls. `"hardware"` brings the old way back.

- The opossum is gone from the icon and About: it comes from an official Telegram sticker
  pack, and its artist says the rights are Telegram's, not theirs to give. The drawn
  thread bubble is the icon again (in the theme's colours with `ui.themed_icon`);
  `ui.app_icon` is gone with it.

- "Activity" counts as seen what came on screen, like the other lanes, checked when you
  scroll or come back to the window. It used to mark everything once, on opening — rows
  far off screen too — and a window in the background at that moment left the newest
  unread for good.
- The `debug` theme: for finding what's wrong, not for reading. Each state of a post in a
  loud frame of its own — unread, "on screen but not all of it yet" (not counted read
  yet), the j/k cursor, what Ctrl+F found, the post you came to — plus the keyboard focus
  and disabled buttons. `shape.debug = true` turns the same on in any theme of your own.

- "Copy handle": a button in a profile, "Copy handle @…" in a post's ⋯ menu (the author,
  and the booster of a boost) and on the "boosted by" line. Always the full `@user@server`
  — people of your own server come as a bare `user`, your server's name is added.

- ⋯ → "Call into the thread…": a reply to that post with only "@" in it and the people list
  open — pick who, add a word, send. They get a notification and open the thread at home;
  no links with service ids. The thread's others aren't mentioned; the call has its own
  draft. `post.invite = false` hides the item.

- ≡ → Debug → "Federation status": how your server is doing — what it runs, how many answers
  and how fast, polls and the live stream — and what keeps failing that isn't the client's
  doing: what the server can't do, who waits to go into a list, and every request that
  keeps getting 404/410/401/timeouts, on your server and on other servers, grouped (ids
  folded), counted, with when it last happened and what it most likely means. Live while
  open; "Copy" as text for an issue; "Count anew". Only what this run saw: nothing is asked
  of the network for it, no queries or tokens are kept.
- Federation status: who waits to go into a list is named (my server is asked who an id
  is when no post of theirs is here), linked to their profile in a tab, with why they
  wait — a follow request unanswered, not followed (refused or withdrawn), or followed and
  going in with the next refresh.

- A slow answer about direct conversations no longer fails the whole poll ("Read timed
  out" on screen, the lanes not fetched): it is only a nicety, skipped till next time.
- Someone waiting to go into a list is tried only once they're followed; while the follow
  request waits nothing is asked, and once it's refused or withdrawn they're let go. (A
  refused follow was retried with a 404 every ten minutes, for a month.)
- What the server hasn't got — blocked domains on GoToSocial, the notification policy —
  is asked once a run, not on every silence refresh. Muted and blocked lists no longer
  ask for an empty second page.
- A post's ⋯ menu is built when it opens, not with every card: two dozen actions and
  submenus per card were most of a lane's widgets and of its drawing time; what it shows
  (unread, subscribed, pinned) is how things are at that moment.
- The log's trend line gives the rate over the whole session beside start → now (and the
  last minutes apart): 245 → 763 MB over a night read "+1950/h", the rate of three minutes.

## 0.15.0 — 2026-10-19

- `feed.prefetch` is `"previews"` by default: new posts' previews, avatars and link
  pictures come ahead of time; the videos themselves and full originals only with
  `"all"` (it fetched every new post's video before).
- Logging in to a plain `http://` server is refused unless it is at home (localhost, a
  private address, `.local`/`.lan`): the token would travel in the clear.
- The web interface prints and opens a one-time link (good for 15 minutes) instead of one
  with its key; at most 32 connections, a silent client dropped after a minute; `#tag`
  links open the tag's page on your server.
- Leaving fedtail no longer throws "cannot schedule new futures" and "closed database"
  into the log: late jobs are turned away, running ones finish first.
- `state.db` is private (0600) like the token's file; on Windows the single-instance pipe
  needs the profile's key; no query string (search words, signed addresses) reaches the
  log.

- fedtail has a face: an opossum holding its own tail — the icon of the window, the tray,
  notifications and the menu entry (`--install-desktop`, the .deb, the Windows .exe), and
  the picture in About. `ui.app_icon = "bubble"` brings back the drawn thread bubble
  (in the theme's colours with `ui.themed_icon`).

- A boost no longer brings an old post into the feed again and again: a post comes into a
  lane once — as itself or with its first boost. A boost of a post the lane has had already,
  or of one read already (in a thread, in another lane), is not shown, not counted as
  unread and not notified about. `feed.repeat_boosts = true` shows every boost again, as
  other clients do. (The server drops a repeat only while the post is among the last
  few dozen of the feed.)

- The unread number on the icon (`ui.icon_count`) picks lanes the way notifications do:
  `"lists"` (all lists — it was accepted and counted nothing), `"list:Друзья"`, `"all"`,
  and the new `ui.icon_count_except` takes lanes away. The config's comments for both
  name every lane in the sidebar.

- Security: a post's link could wrap anything in `fedtail:resolve/…` — a local file (the
  token's `auth.json` too), a network share, `javascript:` — and a click on its text opened it
  when the server found nothing. Now that wrapper holds web addresses only, and nothing from
  a post or another server goes to the desktop but web, mail, XMPP, Gemini and magnet links:
  on Windows opening `file://host/share` alone hands the login's NTLM hash to that host.
  Profile, thread and account links from a post take an id, never a path.
- Security: someone else's words are shown as text, not markup — the content warning in an
  edited post's history, the alt text under a video and in picture tooltips, a link card's
  picture description, a cut name's tooltip, a link's hover address (it could show one
  address and lead to another). Desktop notifications too: a post saying `<a href=…>` in
  plain letters no longer becomes a link there; a name starting with `--` is a name.
- Links whose address has `&not=`, `&copy=`, `&para=`… in it are no longer garbled
  (`?a=1&not=2` became `?a=1¬=2`).
- The web interface: a POST with a negative Content-Length is refused instead of read to
  the end of the connection; a fediverse link it can't find opens in the browser only when
  it is a web address.
- Security: what other servers and posts point at — ActivityPub objects, nodeinfo,
  pictures, videos — is fetched from public addresses only (not this computer, the home
  network, a cloud's metadata service; your own server is exempt), each redirect checked
  again, and only so much: 2 MB of JSON, 20 MB a picture, 100 MB an original, 300 MB a
  video on disk. A server's nodeinfo is read only from that server.
- Security: logging out revokes the token on the server too (it used to stay good there);
  logging in anew revokes the old one.
- `D #id` asks first in the web interface (a "sure?" in the page) and in the terminal
  (Enter again within half a minute), as the window always did.
- The live stream goes through the same proxy as everything else (HTTPS_PROXY; a SOCKS
  proxy means polling only), only to your server's own site and only over TLS.
- Profile names start with a letter, a digit or `_`: `..` pointed outside the profiles.
  A broken `auth.json` or profile card means "log in", not a crash; the token's file is
  private even when a crash left a temp file behind.

- "Activity" follows `feed.order` like every other lane: with "oldest_first" the newest
  is at the bottom, it opens where the unseen begins (`feed.start_at`) and stays put when
  more comes (`feed.on_new`). It used to be newest-on-top whatever the config said.

- `feed.emoji = false`: no emoji in the feed at all — no server pictures (:blobcat:), no
  Unicode ones (🔥 🇬🇪 👨‍👩‍👧), no reactions line; a name made only of emoji shows the login.
  fedtail's own glyphs (⚠ ↔ ❯) stay.
- ≡ → "Try a theme", next to "Open themes folder": any theme at once, until restart — the
  sidebar and every card are drawn again in place, the reading place kept. `ui.theme` in
  the config stays what the next start brings.
- Lanes are named in the config as their titles say: `people` → `home`, `comments` →
  `replies`, `global` → `federated`, `mine` → `my_posts`, `favourites` → `my_likes`. The old
  names still work everywhere (config, command line, web API); the lane open, the columns
  and the choices over a lane that the window remembered move over by themselves. A lane's
  tooltip in the sidebar names its word. "Likes & boosts" is "Activity" now — it was always
  the follows and polls too, and its word was `activity` all along.
- `notify.lanes = ["all"]`: notifications about everything that arrives, in any lane; and
  `notify.except` — lanes never to notify about, whatever `notify.lanes` says (`"bots"`,
  `"federated"`, `"lists"`, `"list:News"`…).
- Why a notification didn't come is in the log at the normal level now: "not asked for"
  (notify.lanes / notify.except) or "that lane is on screen" (notify.when_focused).

## 0.14.0 — 2026-10-18

- Leak hunting for days-long runs. With every stats line a "trend" line: memory, Python
  objects, widgets, cards, pictures, threads, files — at start, now, per hour; a number that
  rose on each of the last `debug.leak_samples` checks (12: an hour), by more than noise,
  gets a "possible leak" warning (the first half hour doesn't count). In the debugging mode
  a census of Python objects by type and Qt widgets by class says what grew since the last
  check and since the start (`debug.object_census`). `debug.tracemalloc` traces every
  allocation from the start. The session ends with a summary line: hours, memory, peak,
  freezes, polls. Memory snapshots go next to the logs and leave with them.
- ≡ → Debugging: "What grows: stats and object census now", "Give free memory back to the
  system", "Memory tracing (tracemalloc)" on and off, "Memory snapshot" — who holds the
  most and what grew since the first snapshot, by line of code.
- TUI: new counts arriving before a lane's line was on screen no longer crash it (CI caught
  it now and then).
- A poll slower than `debug.slow_request_seconds` says where the time went: `poll #N took
  6.20 s (markers 5.80, home 0.30, …)`; the stats line has `core.max_poll_s` since the
  last one.
- The stats thread no longer walks Qt's widgets itself (from another thread that could
  crash a window kept open for days): the window counts them every 30 s and the stats
  line reads that.
- Scrolling up a big lane no longer jumps: while cards are built above the screen, the
  next step took the place from the scroll bar before it had caught up, so a card just
  built became "the post on top" and the reading place moved by thousands of pixels. The
  held anchor decides until it is let go (CI caught it, one run in two).
- ≡ → "Account and server" (was "Accounts") also holds "About the server…": one place for
  this account, its server and the other profiles.
- ≡ → "For the tender and sensitive": word filters, muted, blocked, blocked servers and
  filtered notifications in one submenu, each opening where it is; with `ui.arts_mode` on, a
  line on top says server filters don't apply there (mutes and blocks still do).
- The ≡ menu is shorter: no Write, Refresh and Search (they are on screen, and their keys
  stay), no My profile / Edit profile (My profile is under Accounts; the Edit button is on
  your profile page), no "Posts across the full width" — that is a button now, ↔ between ≡
  and ❯, a drawn ↔ (icon themes have no plain one).
- The sidebar's edge drags: a long name gets room. `ui.sidebar_width` (272) is the start;
  a dragged width is kept till the config's number changes. A long name is cut, not
  pushing the sidebar wider.
- ≡ ↔ ❯ at the top left are one size, icons from one set (or all glyphs), centred; ≡ no
  longer reserves room for a popup arrow that pushed its icon aside. ↔ and ❯ show when on.
- The main profile ★ is a mark, not a folder named "default": `~/.config/fedtail/main-profile`
  names the profile started without `--profile` (none: "default", as before). Accounts →
  "Make it the main one ★"; `--profiles` marks it with *.
- "Log in again" was dangerous: it threw the token away at once, and a cancelled login left
  the main profile logged out. Now, under "Account and server", with a question first: "Log in again…"
  keeps the old token until the new one is in and refuses another account; "Log out…"
  deletes the token, hands the main profile's ★ to another logged-in profile and switches
  the window there (none left: the login window).
- About links to the code on GitHub and to the author in the fediverse — that one opens
  in fedtail, with Follow. Which profile and account this is moved from About to the left
  of the status bar: "default: @me@server ★".

- Lanes side by side, in columns: ❯ right of the menu switches for now, `ui.layout` says how
  the window starts. A lane clicked on the left comes as one more column (or is scrolled
  to), ✕ takes one away, ‹ › move it; the set is remembered (`ui.columns` at first,
  `ui.column_width` each). The same lane widgets move over: place, filters and read marks
  as they were; browse lanes keep fetching while they stand in a column.
- `~~text~~` that came as it was typed (a Mastodon server knows no Markdown) is shown
  struck out, as the writer meant; not in links or code (`feed.text_markup`).
- All accounts in one window: "From another account" in a post's ⋯ menu — like, boost or
  reply as an account that didn't receive it; the post is looked up on that account's
  server by its address and the action goes from there (`ui.act_as`).
- "📄 Read it whole" in the ⋯ menu of a post from another server: the post as the author's
  server keeps it — an article whole, not a title and a link; an event with its time and
  place (asked without your token; `feed.long_form`).
- A profile says what the person's server runs, "🖥 GoToSocial 0.17.3", from its nodeinfo
  (asked without your token, kept a week per server; `feed.server_info`).
- `docs/FEATURES.md`: the boost carousel moves to "won't do", with the reasons.
- A post as a chain: a line of just `---` splits it into posts sent at once, each answering
  the one before (pictures and the poll with the first); the counter counts each part
  (`post.chain`).
- "👁 Preview" in the compose panel: the Markdown made into text (when the server takes
  it), the CW, who sees it, each part of a chain; Send or back to Edit from there
  (`post.preview`).
- A paragraph of nothing but hashtags (more than three) folds into the first three and
  "… +N", small, in a lane; whole but small in a thread (`feed.collapse_tags`).
- The server's own notices in Likes & boosts (Mastodon 4.3+): follows cut because a server
  was blocked — which, why, how many — and warnings from the moderators
  (`activity.server_notices`).
- All accounts in one window: the "→ @nick" mark of each account has a colour of its own,
  the same every time (`ui.account_colors`).
- A picture bigger than the server takes is made to fit before the upload (its pixel
  limit, then JPEG — PNG with transparency — under its size limit), instead of a refusal
  after it; your file stays as it is, gifs are never flattened (`post.resize_images`).
- An old post says so next to its date — "old, 45 days" — when it's older than
  `feed.old_days` (30): ones pulled from an outbox or an old thread aren't read as news.
- `fedtail open URL` opens a post or a profile in the running window (or starts it and
  opens it there); `--install-desktop` also makes fedtail the handler of `web+ap://` links.
- In the profile of someone you follow: "♻ hide their boosts" and "🌐 languages" (only their
  posts in these) — kept by the server, for every client (`feed.per_person_follow`).
- A moved account says so: "📦 Moved to @new" on the profile, with Open and Follow there
  (`feed.show_moved`).
- "Delete and redraft" in the ⋯ menu of a post of mine: deleted, and its text as typed,
  CW, visibility, language and what it answered open as a new draft; pictures go with the
  post on the server and are added again (`post.redraft`).
- Several hashtags as one lane: `#georgia #грузия -#politics` in the search (`+#tag` must
  have, `-#tag` without) opens one lane of them; "＋ to lanes" keeps it in the sidebar's new
  Tags group, browsed while open like Federated (right click: remove). Or in the config,
  `[[lanes.tag_groups]]` with name, any, all, none. Each tag is asked for on its own
  (GoToSocial reads one at a time) and put together by fedtail, each post once.

## 0.13.0 — 2026-10-18

**In short:** GoToSocial approvals of replies, likes and boosts; lists — who is in them,
your own order, author or booster, only people you follow; pictures and videos fetched
ahead to a disk cache with its own limits (1 GB pictures, 10 GB videos); a big lane lets go
of cards far behind and never builds them all at once (no more 6-second freezes and
gigabytes on a filter); freed memory goes back to the system; your own posts are always
read; the player goes between a post's videos; full-width posts, any post language,
a bigger compose panel, a boosts filter; errors in one line and once; `docs/CONFIG.md`
and a rewritten `docs/FEATURES.md`.

Everything in detail:

- Arts mode is called by its name: it is named after @arts, the founder of Point.im, and
  is not translated as «искусство» any more (config reference, docs).
- `docs/FEATURES.md`: each chapter is a table — feature, status, setting, API, other
  clients — with the details folded under it.
- `docs/CONFIG.md`: every option in tables by chapter, with its default — built from
  `config.example.toml` by `tools/config_doc.py` (a test keeps it in step).
  `docs/FEATURES.md` rewritten: every feature with its switch, API and the other clients,
  the plans and what won't be done, with reasons.
- Pictures of new posts are fetched to disk as soon as the posts come, by workers of their
  own: a lane opens with its pictures there, not loading for seconds from a slow server
  (`feed.prefetch`: "all" — the default, originals, videos and gifs too; "previews";
  "off").
- Videos, gifs and sounds have a disk cache of their own (`ui.video_disk_mb`, 10 GB): a
  video played once plays from disk the next time; with "all" they're fetched ahead, one
  at a time.
- The picture cache on disk keeps to `ui.image_disk_mb` (1000 MB): the ones not used the
  longest go, at start and along the way. It only grew before.
- Who is in a list: a server that answers "everyone at once" (limit=0) with nobody is asked
  again page by page; the log says how many came each way.
- Right click on a list in the sidebar: "Who is in it…" opens its people (the ones waiting
  to go in too), each with "Take out of the list"; "Move up" / "Move down" put the lists in
  your own order, kept by fedtail (servers have none) — new lists come at the end.
- The same error from every poll while a server is down is shown and logged once, again
  only when it changes or ten minutes later.
- A server behind a proxy that's down (a 502 from Cloudflare) showed the proxy's whole HTML
  page as the error; now "Bad Gateway — the server is down or not answering".
- "Add to list" for someone you don't follow: the lists are greyed out under "lists take
  only people you follow: follow first", with Follow right there (the server is asked when
  the menu opens, and the answer kept a few minutes).
- A right click on "♻ boosted by …": the booster's profile, or into a list.
- "♻ boosted by …" over a boost: the name opens the booster's profile.
- A boost's ⋯ menu says whom it puts in a list: "Author to a list (@…)" and "Booster to a
  list (@…)" (a relay bot, say), each its own submenu.
- A new list made from a post's menu with someone not followed stayed invisible until a
  restart (and a second try said it already exists): the refused add stopped the job
  before the lists were read again. The list now shows at once and the person waits to go
  in — the message says the server takes only people you follow.
- The short-buttons check measured every button on every resize of every card (a second's
  freeze when a lane opened); it measures once.
- Buttons under a post too wide for the card go short — icon (or glyph) and the count —
  instead of a label cut in half ("В избран…"); the full label stays in the tooltip.
- ≡ → "Posts across the full width": the column of posts takes the whole window (or back
  to `ui.max_width`), remembered for the next start.
- The language list of a post has "Another language…" at the bottom: any ISO 639 code (eo,
  es, cv, jbo, tok…), kept on the list after that; Toki Pona, Lojban and a few others
  get their names.
- The compose panel's size follows the window: `ui.compose_size` in % of it, and a ⤢
  button in the panel for normal / big (90 %), remembered.
- The filter next to Refresh can hide boosts too (for this run, like the rest of it).
- Switching the media filter (or "unread only") on a big lane froze the window for six
  seconds and took gigabytes: the lane decided the cards built reached both ends and built
  all of them. It now builds around the post on screen, as when it opens.
- A click on "older" at the very top ("nothing older") no longer jumps a few posts down:
  the button took the focus, and handed it to a card further down while it waited.
- My own posts are never unread, from whatever client: ones written in Tusky overnight came
  in as unread when they reached fedtail some other way than a lane (a catch-up after a
  restart, a thread). Ones stored before are put right on connect.
- A long lane lets go of the cards far behind the reading place (past 3 × build_at_once:
  back to that many behind and twice ahead; the post on top stays put). Reading a night's
  hundred posts kept every card built — over a megabyte each, pictures included — and took
  the client from 700 MB to 1.1 GB.
- A list add waiting for a follow to be confirmed, retried while the server was slow, showed
  "Read timed out" as an error; it now just waits for the next try.
- Approving: only the very request is answered — the same person, the same post, still
  waiting. It used to fall back to "something similar" and once approved a like for a
  reply. A request already answered elsewhere says so instead of an error; a miss logs what
  the server listed.
- Memory freed by fedtail goes back to the system every few minutes (glibc keeps it
  otherwise: a client open all night stayed at 1.3 GB holding almost nothing);
  `debug.trim_memory`. The stats show how much came back and open files by kind.
- Replies, likes and boosts waiting for my approval (GoToSocial interaction policies) come
  to Likes & boosts — "reply waiting for your approval" — with ✔ approve and ✘ reject
  right on the row; the server's request is answered and the notification goes. They came
  before only to clients that ask for every kind (`activity.approvals`).

## 0.12.0 — 2026-10-18

**In short:** tabs stop jumping (to the lanes, to the bots, from under the curtain); the
player goes between a post's gifs and videos; older posts of a profile from servers that
hide their outbox; `--update-config` puts new options where they belong; less memory for
pictures and fewer polls on a busy stream; old logs of the first versions cleaned up.

- Less memory and CPU for pictures: a feed picture is decoded at the size of its box
  (times the screen's pixel density), not at 1200 px — most of a lane's memory was
  pictures held at several times the pixels shown (`ui.image_decode = "box"`; "full" as
  before).
- The live stream wakes a poll at most every 10 s (`poll.stream_gap_seconds`): a busy server
  sends events many times a minute and each poll asks every lane. Refresh doesn't wait.
- The stats every 5 minutes count Python objects too (`py_objects`), to tell a leak.
- The log of the first versions (`fedtail.log`, `fedtail.log.1`…) now goes with the other
  old logs when a new version starts. Tabs coming to the front, the curtain lifting and
  Enter on the curtain are in the log.
- With every lane closed (Esc, the curtain), opening something whose tab was already open
  (my own profile from my name, a thread, a search) did nothing visible: the tab came to
  the front under the curtain. It now lifts the curtain.
- Several gifs or videos in a post: ‹ › at the top right of the player and the keys go
  between them without closing it (← → or the wheel for gifs; PgUp / PgDn for videos, where
  ← → seek), with "2 / 3" next to them and the keys in a faint line at the bottom.
- With every lane closed (the curtain), Enter in the sidebar search box opened the search
  and then the last lane on top of it: the box let its Enter go on to the window, where
  Enter on the curtain means "back to the lane". A tab opened from the curtain now shows.
- `--update-config`: a new option went under the next chapter's banner (inside the next
  section's comments) instead of at the end of its own section; and a file without blank
  lines between options stayed packed. Now options sit where they belong, a blank line
  between each.
- A search, thread or profile tab no longer jumps back to the lanes: when the sidebar was
  rebuilt (lists refreshed, say), choosing the lane again brought the lanes tab to the
  front. The lanes tab comes forward only when I choose a lane (a click, the sidebar
  keys, Alt+N, start-up). Enter in the search field stays in the search field.
- Older posts of a profile from a server that won't show its outbox to strangers
  (GoToSocial, Mastodon with authorized fetch): read through that server's public API
  instead, when it answers without a token.
- Those older posts show four at a time as my server fetches them (it takes seconds a
  post), with "n of total" on the button, instead of all at once a minute later.

## 0.11.0 — 2026-10-18

**In short:** no more freezes when a lane opens (cards are built around where you read,
the rest as you scroll); video, audio and gifs play in the window, with a download button;
who liked and boosted, quotes of your posts, muted threads, trends, suggestions, the
directory, server info; a media filter next to Refresh; older posts of a profile straight
from the author's server; lists right after a follow; times in Likes & boosts and the
follow date in your private note; logs in the profile's folder, much more detailed.
Video needs `python3-pyside6.qtmultimedia` and `python3-pyside6.qtmultimediawidgets`.

Everything in detail:

- Likes & boosts: each row says when (for a group, from when to when; the tooltip lists
  everyone with their time). A profile says "following since …" for people followed
  through fedtail — the server itself doesn't keep that date, so fedtail writes it as the
  last line of my private note on them, `[fedtail followed YYYY-MM-DD]`: seen on every
  device and in other clients, hidden in fedtail and kept when the note is edited, taken
  out on unfollow (`feed.follow_date_note`).
- The player has a ⤓ download button (key S), for gifs too; right click on a video or a
  gif in a post says "Download". Big files go to disk a piece at a time.
- A profile from another server: once my server has nothing older, "▼ further back —
  from their server" reads on in their own outbox, a page at a time (`feed.remote_profiles`).
- Putting someone just followed into a list: the server refuses until the follow is
  confirmed (a 404). They now go into the list in fedtail at once, and fedtail puts them
  into the server's list by itself on a later lists refresh (given up after 30 days).
- `docs/FEATURES.md`: what fedtail does and doesn't, next to other clients, with the config
  switch for each; linked from both READMEs.
- Terminal interface: a poll landing while a thread, a profile or the composer was open
  (right after sending a reply, say) failed and printed its traceback over the screen. The
  update now finds the lanes on the main screen, and no log lines go to the terminal while
  the interface owns it (they are in the log file).
- Logs live in the profile's data folder, `logs/` (≡ → Debugging → Open the log folder),
  not in `~/fedtail-logs` any more; `debug.log_dir` still sends them elsewhere. A new
  version deletes the old version's logs at its first start, and the old home folder ones.
- Read on scroll (`read.mark_read = "on_scroll"`) marks what you actually scrolled through:
  a post that was on screen and that you went on past counts as read even if it never
  stood all on screen at a pause; scrolling a window without focus with the wheel (KDE
  does that) counts too; and pictures still arriving no longer hold the marks back.
- `ui.arts_mode` (on by default): every post as its author made it — content warnings
  open, sensitive pictures uncovered, server filters neither hide nor fold posts, no
  "Report" item. Your own mutes and blocks keep working; what the server itself cuts off
  never reaches a client. `false` brings back the separate switches.
- Pictures: originals (a single picture made sharp, the viewer, saving) have their own
  workers and no longer hold up the previews; a preview that hasn't come in 12 s is asked
  again 1.5 s later with a minute of patience (a server fetching it from elsewhere usually
  has it by then — before, all workers sat 30 s on such pictures and the rest waited);
  pictures are decoded straight at the size they're shown (a big JPEG is read at a fraction
  of its size), which costs less time and memory; a broken picture is retried after a
  minute, not five.
- A like, a boost or an edit redraws only the cards of that post. Every card in every lane
  used to be fetched from the database again — over a second of frozen window with a few
  hundred cards open.
- `ui.unload_hidden_minutes` (10): a lane not opened that long lets its cards go; opened
  again, it's drawn anew at the first unread. A client kept open for days held over a
  gigabyte in cards and their pictures. The lane in front is never unloaded; 0 keeps all.
- A funnel next to Refresh in lanes, profiles and tags: show only posts with pictures,
  gifs, video, audio or plain text; for this run only.
- "To new" with nothing unread scrolls to the newest end instead of going grey.
- Video, gifv and audio in the window (`ui.video_player`, QtMultimedia): a video plays over
  the window (Space, ← →, M, O for the browser, Esc); gifvs loop in their cards, muted,
  only while on screen and at most three at once (`ui.gifv`); audio gets a player in its
  card. Without QtMultimedia, or with `"browser"`, they open in the browser as before.
- Around posts and people, where the server can (a feature it hasn't got disappears after
  its first "no"): who liked and who boosted a post (also the rest from the post's own
  server; a right click on ★ or ♻), mute a thread, who quoted my post and taking my post
  out of a quote; on profiles — remove a follower, feature someone, people in common; a
  tag on my profile; ≡ → Find people (server suggestions, profile directory, trends) and
  About the server (rules, description, privacy); Activity — dismiss one, clear all;
  emoji reactions shown on posts from servers that have them; reactions to announcements.
- `post.default_visibility = "server"`: what you set on the server's web side.
- Direct messages read here are read on the server too (Mastodon conversations).
- A right click on a post's text opens the post's menu.
- Read by hand, one post at a time: "Mark read" and "Read up to here" (this one and
  everything older) in every post's menu; with `read.mark_read = "manual"` the lane waits
  exactly where you stopped. `read.read_button` puts a ✓ under each unread post.
- A bookmark button under every post (`ui.bookmark_button`; it was only in the ⋯ menu).
- Opening a lane no longer builds a card for every post in it: only those around the place
  reading starts at (`feed.build_at_once`, 40), the rest a few at a time as you scroll near
  an edge. Cards built above the screen are held in place by the same anchor that keeps
  your place when new posts come, so nothing jumps; finding (Ctrl+F), "to the first
  unread" and "all read" still cover the whole lane. `0` builds everything at once.
- Lanes with many posts under content warnings opened in seconds instead of tens of
  seconds: every such card made, and threw away, a native window of its own while it was
  built (the log showed a 16 s freeze for a list of 300 posts). Word-wrapped text also no
  longer lays itself out twice for every resize.
- Threads from other servers come whole faster: where the post's server keeps a list of
  the whole conversation (its "context", Mastodon 4.5 and others), it is read in one go
  instead of walking replies of replies; the missing posts are fetched four at a time.
- Someone from another server with no pins known here: their pins as their own server
  lists them (`feed.remote_profiles`).
- Honest counters (`feed.honest_counters`): when the author's server won't tell a
  stranger, the numbers are asked as one of your other accounts — on the author's server
  if you have one there, or on another server that already has the post
  (`feed.counters_via_accounts`, on). Each token goes only to its own server.
- `activity.types = ["all"]`: every kind of activity, now and those added later.
- The config reference reads easier: a blank line between options, and every launch key
  (`--profile`, `--ui`, `--debug`, `--bug-report`…) listed at the top of the file.
  `--rebuild-config` lays your file out the new way, with your values kept.
- The log tells where a freeze is: any freeze of the window over `debug.stall_ms` (250 ms)
  gets a line with how long it was and what the window was busy with — an event, a
  lane being drawn, a picture coming in, or Qt itself laying out and painting — with the
  stack. Every picture gets its queue, download and decode time; the stats line counts
  freezes (`freezes.*`) and pictures (`img.*`).

## 0.10.0 — 2026-10-17

- The whole interface in a terminal: `fedtail --ui tui` (or `ui.frontend = "tui"`) — lanes,
  posts with what they answer, threads as trees, profiles, the command line; keys as in the
  window (`j` / `k`, `Enter`, `r`, `f`, `b`, `m`, `n`, `p`, `x`, `Esc`, `q`); log in from it too.
  Needs Textual (`python3-textual`, or `pip install fedtail[tui]`). New `[tui]`: `theme`,
  `lanes_width`, `show_context`.
- fedtail in a browser: `fedtail --ui web` (or `ui.frontend = "web"`) — lanes, threads,
  profiles, writing, the command line, live updates, keys as in the window; standard library
  only. A link with a key (kept in the profile, `web.key`) lets you in; the page loads scripts
  from fedtail only, server HTML is cleaned before it gets there. New `[web]`: `host`, `port`,
  `open_browser`.
- A Debian package with every release: `fedtail_<version>_all.deb` — `sudo apt install ./…`
  brings Qt and requests from Debian and puts fedtail in the menu (`packaging/deb.py`).

## 0.9.0 — 2026-10-17

- In the terminal: `fedtail lanes`, `fedtail show LANE`, `fedtail tail [LANE…]`,
  `fedtail post [--reply ALIAS] TEXT|-`, `fedtail read LANE` — the same profile, database and
  read marks as the window, no Qt needed. New config chapter `[cli]`: `enabled`, `color`,
  `max_lines`, `tail_lanes`.
- Server announcements: a strip above the lanes, one at a time, until "Got it" (dismissed on
  the server, so for other apps too). `ui.announcements = "off"` hides them.
- Filtered notifications (Mastodon 4.3+): ≡ → Filtered notifications… — the senders held back
  (let through, dismiss, open the profile) and the policy for each kind of sender;
  `notify.filtered` = `"remind"` (also a line at start when someone waits), `"menu"`, `"off"`.
- A profile shows the person's featured tags and the people they recommend
  (`feed.profile_featured`).
- `ui.media_grid = "square"`: several pictures as even squares, cut around the author's
  focus point (the default, `"natural"`, keeps each whole). Your own pictures get one too:
  double-click a picture in a new post, click where the main thing is (`post.focus_point`).
- Accessibility: alt text as a caption under pictures (`ui.alt_text = "caption"`), a question
  before sending a picture without one (`post.alt_reminder`), names for screen readers on the
  post buttons, avatars and pictures.
- `:bl` in a post offers the server's custom emoji (`post.complete_emoji`).
- Live stream: the server's WebSocket stream wakes the poll the moment something arrives
  instead of up to 90 s later (`poll.stream = "auto"`; `"off"` — polling only). No new
  dependency; a dropped stream reconnects and loses nothing.

## 0.8.0 — 2026-10-17

- "My likes" lane: the posts you liked (`"favourites"` in `lanes.enabled`; off by default).
- The bell on a profile of someone you follow: each of their new posts comes as a
  notification (shown in Likes & boosts when `activity.types` includes `"status"`).
- Scheduled posts: "⏰ Later" in the post panel sends it at a set time — the server keeps it,
  fedtail needn't be running; ≡ → Scheduled posts lists what's waiting, with cancel.
  `post.schedule = false` hides both.
- Who may reply to, boost and like your new posts, on GoToSocial: `post.who_can_reply`,
  `who_can_boost`, `who_can_like` — everyone, followers, those you follow, the mentioned, or
  just you; left empty, the account's settings decide. Other servers aren't sent it.
- Block a whole server from a post's ⋯ menu: nobody from there in any lane; ≡ → Silence →
  Servers lists them, with unblock.
- A private note on someone ("Note…" on their profile): only you see it, it's kept on your
  server and shows under their card.
- Quote a post (Mastodon 4.5+): "Quote" in the ⋯ menu of a post its author lets quote ("the
  author approves" when they decide by hand); the post panel shows what you quote.
  `post.quote_policy` says who may quote your new posts (everyone, followers, nobody, or as
  set on the server); `post.quote_action = false` drops the menu item.
- "Translate" in the ⋯ menu of a post in another language, when your server translates
  (Mastodon with DeepL or LibreTranslate): the translation shows in the card, with
  "original" to go back. `feed.translate = false` drops the menu item.
- Keys in lanes and threads: j / k walk the posts (the current one framed), r replies, f
  likes, b boosts, m bookmarks, o or Enter opens the thread. `ui.post_keys = false` turns the
  letters off.
- Report a post to your server's moderators from its ⋯ menu: what kind, what's wrong, and
  for someone from another server whether their moderators hear too (without your name;
  `post.report_forward` sets that tick's default).
- Pinned posts come first on a profile, marked 📌 (`feed.profile_pinned`); your own public
  posts can be pinned and unpinned from their ⋯ menu.
- Pictures the author marked sensitive (without a content warning) stay covered until
  clicked — not even downloaded before that (`feed.sensitive_media = "show"` to see them at
  once). Your own pictures can be marked so: "🔞 Sensitive" in the post panel.
- Polls in the post panel: "📊 Poll" — up to as many choices as the server allows, how long
  it runs, one choice or several; a draft keeps it. A post has either pictures or a poll.
- "Direct" lane: private messages to you (posts only the mentioned can see), in Personal and
  notified about by default; they no longer double up in Replies to me and Mentions
  (`lanes.direct_apart = false` to keep them there too). A config written earlier lists its
  lanes itself: add `"direct"` to `lanes.enabled` (and `notify.lanes`) to get it.
- Followers and follows of someone from another server: your server knows only part of
  them; the end of such a list offers "more — from their server", read there (ActivityPub,
  without your token) and found through yours, with the total their server reports.
  `feed.remote_people = false` hides that button.
- A profile of someone from another server that yours knows little about fills in: fedtail
  reads their newest public posts from their own server's outbox (ActivityPub, without your
  token) and has your server fetch them, so they are ordinary posts — answerable, likeable;
  the header says how many came and from where. `feed.remote_profiles`, `feed.remote_posts`.
- Mastodon 4.5+ fetches a thread's missing replies itself and says so
  (`Mastodon-Async-Refresh`): fedtail waits for it and the open thread grows when the server
  is done — alongside its own asking of the author's server (`feed.complete_threads`).
- The read position is shared with your other clients (Mastodon markers, also in GoToSocial
  and Akkoma): Home or mentions read up to some post on the phone are read here too, and how
  far you've read here — everything from the oldest on — goes to the server for them.
  `read.sync_markers = false` keeps reading marks here only.
- @names complete while you write: the people seen most in the lanes first, then those the
  server finds (a moment later, without fetching from other servers); the list shows the
  name next to the address. `post.complete_mentions` and `post.complete_tags` turn either off.
- Quote posts (Mastodon 4.5+, Akkoma, Misskey, Fedibird): the quoted post framed inside the
  quoting one, a click opens its thread; a quote that can't be shown says why (awaiting
  approval, withdrawn, deleted, its author muted or blocked — with "open anyway"); the
  "RE: link" line servers add for older clients is gone. `feed.quotes = "card"`, `"link"`
  (one line) or `"off"`.
- Servers' own emoji (`:blobcat:`) are pictures now — in posts, content warnings, names and
  "boosted by"; the ones not downloaded yet come in by themselves. `feed.custom_emoji =
  false` keeps them as text.
- Link cards: a post that links to a page shows the page's card — site, title, a line or
  two of description, its picture — as the server collected it; a click opens the link.
  `feed.link_cards = "full"`, `"text"` (no picture, no description) or `"off"`.
## 0.7.0 — 2026-10-17

- In the debugging mode the status bar's right end says how the window is drawn: theme, Qt
  style, font, platform, scale, one-file build or source. The log adds the window's size,
  the least it needs and the widest widgets.
- The one-file build in KDE uses Plasma's default font (Noto Sans 10) when `kdeglobals` names
  none — KDE writes it there only once it's been changed — instead of Qt's bare "Sans Serif 9".
- The Linux one-file build brings all of Qt's platform plugins, Wayland's included: without
  them Plasma on Wayland ran it through XWayland, unscaled — tiny letters and a window of
  the wrong size.
- Links, the config, folders and notifications from the one-file build open with the
  system's programs in the system's environment (they were handed the build's own Qt
  libraries, so KDE asked every time what to open the config with).
- Hashtags complete while you write: `#ge` offers the tags already in use — the ones you
  follow first, then the most used in the posts fedtail has seen (`#georgia`,
  `#GeorgiaNews`…); ↑ ↓ and Enter or Tab pick one.
- Pictures stuck in "loading": with avatars and pictures asked for all the time, newest
  first, an older request could wait behind them forever — now one that has waited 6 s
  goes next, and there are six downloads at a time, not four. A preview that gave up is
  asked again as soon as its original comes (opened in the viewer), so closing the viewer
  shows it in the lane too.
- The Linux one-file build uses the system's fontconfig and freetype instead of the build
  machine's older ones, which couldn't read a newer system's font setup — every font fell
  apart. In KDE it takes the colour scheme, the font and the icon theme from `kdeglobals`
  (its Qt can't load KDE's own integration), instead of plain washed-out grey.
- The one-file build keeps its window size and place apart from the one run from the
  source: they may scale differently, and one stretched the other's window.
- The log's first lines say more about the display: Qt platform, style, font, screen scale
  and DPI, one-file build or not.

## 0.6.1 — 2026-10-17

- The config is in chapters now — look & window, reading, lanes, posts, notifications… with
  a list of them at the top and sub-headings inside `[ui]` — and every option is written with
  its default value (not commented out), so an editor colours it. A value written there stays
  yours even when a later default changes; comment it out to follow the program.
  `--rebuild-config` lays an existing config out anew in the chapters, keeping your values
  (a `.bak` keeps the old file).
- The detailed log (debugging mode) is on only in development versions from git now, not in
  releases or the one-file builds; `debug.mode = "on"` or `--debug` turns it on there.
- README: a download line at the top and a table of contents.

## 0.6.0 — 2026-10-16

- Somebody's boost of a post by a person you put in a list stays out of Home (and the other
  lanes in `lists.hide_in`) too, not only that person's own posts and boosts.
- Theme `bnw` — bnw.im: a black frame, grey posts on white, everything monospace, bright
  green buttons. Themes may now colour the left panel apart from the posts
  (`sidebar_text`, `sidebar_muted`) and give the post panel and dialogs their own background
  (`panel`); left at "auto" they follow `text`, `muted` and `window` as before.
- A lane opens at once on a click: first the switch, with "loading…" over the lane, then the
  drawing (a lane of a few hundred cards takes a moment); the same over All | Posts | New.
- Quit (from the tray or the menu) quits at once: the process no longer lingers for minutes
  after the window is gone, waiting for downloads nobody needs any more (a picture's
  original may take two minutes). The log says which were left behind.
- Notifications about one list, by its title: `notify.lanes = [..., "list:Друзья"]` —
  not all lists at once (`"lists"`), which with bots in them would never stop. The log
  says which new posts got no notification because their lane isn't in `notify.lanes`.
- A picture, avatar or profile banner that doesn't come within 30 s (a server still fetching
  it from elsewhere) is asked for once more a few seconds later, with more patience, instead
  of staying grey until a restart. A request with no answer for three minutes is asked again.
- Opening a thread no longer makes the window wider: a long title or note above a lane, thread
  or account ends in "…" and shows the whole text in its tooltip.
- Short texts (conversation lines, notifications) no longer glue words across a quote or a
  list item: "@annaquote" is "@anna quote" again.
- Feed | Conversations is offered only where it changes something — Replies to me, Mentions,
  Subscriptions (many replies to the same threads); in Home nearly every post is a
  conversation of its own and both views looked the same. The tooltip says what it does.
- Switching All | Posts | New or Feed | Conversations: the pressed button turns at once and the
  lane is redrawn after it, under a wait cursor and in one paint (it took over a second with
  both buttons lit). The choices start fresh every run — All and Feed, or what
  `lanes.posts_only` says — unless `feed.remember_choices = true`.
- The post window is a panel inside the main window now (`ui.compose = "inline"`): KDE keeps a
  keyboard layout per window, so a new window could come up in another language mid-thought.
  It sits in the middle of the window; what the post is (who sees it, language, pictures,
  warning) is one row and what to do with it (Close, Discard, Send) another, so nothing is
  cut off in a narrow window. One panel at a time (opening another keeps the first as a
  draft), ✕ or Esc closes it, pictures dropped on the window go into it. `"window"` brings the separate window back.
- A tidier lane header: what to show is one control — All | Posts | New — and how to show it
  another — Feed | Conversations (each with a tooltip saying what it does); "↓ To new" no
  longer looks like a drop-down; buttons with nothing to do grey out instead of vanishing,
  so the others stay where they were. "Posts only" and "New" are one choice now.
- Pictures come quicker: a single big picture shows its preview at once and the full file
  replaces it when it arrives (it used to wait for the full file); the picture asked for
  last loads first, so the one on screen doesn't queue behind everything scrolled past; the
  log says when a picture waited for a worker.
## 0.5.0 — 2026-10-16

- One file, no installing: every release has `fedtail-X.Y.Z-linux-x86_64` (built on Debian 12)
  and `fedtail-X.Y.Z-windows.exe` with Python and Qt inside; `--install-desktop` works from
  them; `packaging/build.py` builds one locally. Running from the source stays as it was.
- "Unread" over a lane: only what was unread when you opened it, plus what arrives. Reading
  doesn't make posts vanish under your eyes — they grey out and stay until you leave the
  lane; the next time it opens without them. Remembered per lane.
- A video a server calls a picture (an mp4 as "image") shows as a video, and a video whose
  still frame won't load says "▶ video — click to open in the browser" instead of "picture
  didn't load"; still frames of videos get a ▶ on them.

## 0.4.0 — 2026-10-16

The public beta.

- Ready to be shown: CONTRIBUTING.md, SECURITY.md (what fedtail promises about the token,
  other servers, HTML and logs), issue templates that ask for the log, a pull request
  checklist, package metadata; CI checks that `pip install` gives a working `fedtail`
  command. The README says what fedtail is now, with a screenshot.

- Windows: a zip with `fedtail.exe` in every release (built by CI with PyInstaller, no Python
  needed); config in `%APPDATA%\fedtail`, data in `%LOCALAPPDATA%\fedtail`; one window per
  profile through a named pipe; `--install-desktop` makes a Start menu shortcut; the tests
  run on Windows too.

## 0.3.0 — 2026-10-16

- A profile's card no longer looks like one more post: a tinted block with an accent edge,
  the header picture as a banner, the name in large type, and a "Posts" heading under it.
- The debugging mode can be turned off: `debug.mode` = `auto` (on before 1.0 and in
  development builds, off in releases), `on` or `off`. Off: warnings and errors only, a few
  MB in the profile's data folder, no stats, no freeze watchdog; crash traces stay.
  `--debug` turns it on for one run.
- Logs where you can find them: `~/fedtail-logs/<profile>/`, a new file at every start and
  every hour (`2026-10-16_15-04-12.log`), `latest.log` pointing at the current one, the
  folder kept under `debug.keep_mb` (500 MB) — the oldest go by themselves. `debug.log_dir`
  moves them ("" — back into the data folder). The log also tells what you did: lanes and
  tabs opened, post actions by id, what was sent (its length, not its text), how long lanes
  took to draw, slow window events. `--bug-report` takes the last two days.
- All accounts in one window (≡ → Accounts → "All accounts in one window", or `ui.merge`):
  lanes of the same name merge, the other accounts' lists are lanes of their own, a post
  another account received is marked "→ @handle" and a reply, like or boost on it goes from
  that account. A profile already open in its own window stays there.
- At start no lane is open (the curtain, with the counts on the left; Enter opens the last
  one): starting fedtail no longer reads anything for you. `ui.start_lane`: `none`, `last`
  (the old way) or a lane's name.
- The picture viewer no longer says "loading…" forever: it shows the feed's smaller copy at
  once while the original loads, and when the original won't show it says why — a format
  Qt can't read (webp/avif without `qt6-image-formats-plugins`; Save still works) or the
  server didn't answer (R tries again). An original opened in the viewer is waited for up to
  two minutes (a server may be fetching it from the author's server just then).
- A thread is the same whichever post it's opened from: a server's context of a post holds
  only its own branch, so the tree is now read from the top post.
- Threads with holes fill themselves: on opening, fedtail reads the list of replies the
  post's own server publishes and asks your server to fetch the ones it never got; the
  thread grows a moment later, the new replies answerable like any other
  (`feed.complete_threads`; requests to other servers go without your token).
- "N new" over a lane could stay after everything was read (posts of someone just put in
  a list stayed drawn in Home while the counts already left them out): lanes redraw when
  lists change, and the pill checks the read marks themselves before it says anything.
- Accounts: right-click your avatar (or ≡ → Accounts) for the list of profiles, each named
  "@you@server"; pick one and its window opens with its own theme and config, this one closes
  (`ui.switch_closes`). "Add an account…" makes a new profile and opens the login window.
  `--profiles` lists them in the terminal. A profile keeps a small `profile.json` (who and
  which server, never the token) so the list knows names without logging in. Only real
  profiles are listed (a config.toml, a login or a database), not the shared themes folder.
- Someone you put in a list leaves the general lanes — Home, Bots, Federated, Local — and
  is read in their list, so subscriptions don't clutter the feed. `lists.hide_members`:
  `all` (default), `exclusive` (only lists marked exclusive, the old way) or `off`;
  `lists.hide_in` — which lanes. Replaces `lists.exclusive_hides`.
- A profile's buttons wrap onto the next line when the window is narrow instead of being
  squeezed until their words are cut.
- The language of a post: a list in the post window (each language by its own name), the
  default in `post.language` (`""` — as in the account's settings), the list in
  `post.languages`; drafts keep it.
- The image viewer has half-transparent buttons in the top right corner: Save, open in the
  browser, close.
- A post's `#abc` is a link: a click puts it at the start of the command line (replacing the
  number already there), ready for the text; the command line takes the whole width until
  there's a hint to show.
- Polls: the options right on the card (one or several, as the poll allows) and a Vote
  button; the results — bars, percentages, your choice ticked, the leader in bold — once
  you voted, when it's over, on your own poll, or by "Results"; how many voted, until when,
  "refresh" for fresh counts.
- `--update-config` also refreshes the explanations of options already in your file (the
  themes and choices of this version) and drops commented-out options that no longer exist;
  your values and your own notes stay.
- `--install-desktop` writes the icon's full path into the menu entry: Plasma takes a
  window's icon from its entry, and a bare name in a freshly filled icon theme often came
  out as a blank page on the task bar and in the title bar. A profile's window now names
  its own entry (`fedtail-<profile>`), not the default one.
- Sidebar sections fold: a click on "Lists" (or any section title) hides its lanes and
  shows their unread as one number next to the title; remembered across restarts.
- The unread count on the icon: drawn into the tray icon and shown on the task bar button
  (the LauncherEntry signal KDE Plasma listens to; needs the menu entry from
  `--install-desktop` and QtDBus — Debian: `python3-pyside6.qtdbus`). Which lanes count:
  `ui.icon_count` (Replies to me, Mentions, Subscriptions, Follow requests; `[]` — none).
- Network failures in the log and the terminal take one line instead of a page of
  traceback (the request itself is logged with its timing); pictures give up after 30 s
  of silence instead of 60, so a server stuck on a remote original doesn't stall the rest;
  the follow-requests tab is no longer rebuilt on every poll; a picture that just failed
  isn't asked for again for 5 minutes (and is logged once, not twice).
- Post HTML goes through an allow-list: text formatting, lists, quotes, code and links
  stay; scripts, styles, frames, pictures by path, headings, fonts and tables don't (headings
  and boxes become paragraphs). Links only to the web (and mail, xmpp, gemini, magnet) or
  inside fedtail to a profile, tag or thread — a post can't carry a link that deletes,
  boosts or follows on your behalf. There never was a browser engine here to run scripts.
- An open thread takes new replies in by itself as the poll brings them (and F5 reloads
  it as before).
- A thread you don't follow but whose replies still come says why: "not followed, but
  replies by @a, @b show in Home" — the server puts into Home replies between people you
  follow; following the thread brings everyone's.
- A command line like on Point at the bottom (`Ctrl+L`): `#a3f` opens, `#a3f text` replies,
  `#a3f/2 text` answers comment /2, `S`/`U #a3f` (un)subscribes to the thread, `S`/`U @user`
  (un)follows, `! #a3f` boosts, `~ #a3f` bookmarks, `D #a3f` deletes, `@user` opens the
  profile, `@user text` writes directly, plain text posts, `?` lists it all; while you type
  it says what Enter will do; ↑ ↓ bring earlier commands back (`ui.command_line`,
  `post.plain_posts`).
- Conversations view: a button over a lane shows each conversation once — where it started,
  how many messages, how many new, who wrote last; seeing the card marks them read.
- Edit your posts: "Edit" in the ⋯ menu opens the composer with the text as you typed it
  (Markdown included); text and warning change, pictures and visibility stay. Edited posts
  say "edited", a click shows every version.
- Silence: mute or block from a post's ⋯ menu or the profile (their posts vanish from every
  lane at once); word filters kept on the server (≡ → Silence…: fold or hide, where);
  a post folded by a filter says which; muted/blocked lists with undo.
- The last `Esc` closes every lane behind a curtain instead of hiding the window: the
  sidebar with its counts stays, nothing is marked read, new posts pile up ("Piling up:
  Replies to me — 3, Home — 12"); a lane click or Enter opens again. `ui.esc` (was
  `ui.esc_hides`; an old `esc_hides = false` still means `off`): `curtain`, `tray` (the old
  way) or `off`.
- Bookmarks, like on Point: "Bookmark" in a post's ⋯ menu, a Bookmarks lane (the server's
  bookmarks; a post bookmarked here shows up at once).
- Notifications: no longer all silent while the window is active — only the lane on screen
  stays quiet; every decision and notify-send's answer go to the log; a missing notify-send
  is said out loud (with the package to install); Debugging → Send a test notification.

## 0.2.0 — 2026-10-16

- Themes `pink`, `nord` and `solarized`.
- Diagnostics on by default until 1.0: a rotating log with every request and its timing,
  polls, errors with tracebacks and stats (memory, CPU, threads, caches, widgets) every few
  minutes; crash.log with all thread stacks on a fatal crash; stacks on demand
  (`kill -USR1`, the menu) and by themselves when the window freezes; Qt's own messages
  go to the log, not the terminal; `--bug-report` packs it all (no token, no database).
- Sidebar in sections: Timelines from the widest down (Federated, Home, Local, Bots), Personal
  (My posts, Mentions, Replies to me, Subscriptions, Likes & boosts, Follow requests), Lists at
  the bottom; every lane explains itself on hover. "People" is now "Home" and opens first;
  "Activity" is "Likes & boosts". New: Federated — the whole fediverse as your server
  knows it; Local and Federated are fetched only while open, without unread counts.
- Search (`Ctrl+K`, the box under Write): people by name, @user@server or link, tags, posts;
  Follow and Follow tag right in the results; followed tags with an empty query; a tag tab
  has Follow tag; a profile opens whom they follow / their followers, each with Follow.
- New icon: a talk bubble with a curled tail and a thread inside; drawn in the current
  theme's colours for the window, tray and notifications (`[icon]` in theme files, "auto"
  follows the accent; `ui.themed_icon`).
- Decoded pictures are kept within `ui.image_cache_mb` (128 MB), least recently used out
  first — the first bug report showed 800 MB after a few minutes with a cache bounded only by
  count.
- Links stay inside: @mentions → profile tab, #hashtags → tag timeline, fediverse links →
  looked up through your server; profiles get an info card with Follow, Mention, Add to
  list; clicking the name in its own profile tab goes back to the card.
- Docs: ARCHITECTURE.md (the whole system for the next developer, human or AI),
  DEBUGGING.md (logs and bug reports), AGENTS.md (rules on one page).
- Save pictures: `S` in the viewer or a right click on a picture; to the desktop's Downloads
  folder (`ui.save_dir`), under the file's own name, never overwriting.
- Fixed: "Failed to disconnect" warning on every card rebuild.
- Notifications per lane with "Open" to the thread; privacy levels `full` / `sender` / `count`.
- App icon; `--install-desktop` adds a menu entry with it.
- Pictures by drag and drop (compose or main window) and `Ctrl+V`; thumbnails in compose;
  the content warning field is hidden behind a button.
- Themes `point` (point.im today), `juick` and `juick-classic` (juick.com of 2013 and 2011),
  `night`, `paper`, `contrast` (for weak eyes).
- Honest counters from the post's own server (`feed.honest_counters`, off by default).
- CamelCase hint for one-case hashtags in the composer (`post.camelcase_hint`).
- Activity lane and notifications: favourites, boosts, new followers, gathered per post.
- Lists as lanes in a block of their own; "Add to list" from a post's menu or a right click;
  create, rename, delete, exclusive (hidden from People and Bots).
- A right click on a post opens its menu.
- Pictures that fail to load fall back to the preview, then say so.
- Thread subscriptions like on Point: a "Subscriptions" lane with new comments in followed
  threads; own posts and threads you comment in are followed automatically; follow/unfollow
  from the ⋯ menu or the thread header; `[subs]` settings.
- My profile: a tab with counts, and an editor for name, bio, avatar, header, fields and
  switches (approve followers, bot, directory).
- Version from git: `0.2.0.devN+gSHA`; About shows build, commit date, Python/Qt, profile.
- The last `Esc` takes the window off the screen at once (to the tray) — `ui.esc_hides`.
- `Ctrl+F` → "Deeper": search everything stored for the lane, the lane grows down to the match.
- `Ctrl+F`: find in the open lane, thread or profile; `F3` / `Shift+F3`, "3 of 12".

## 0.1.0 — 2026-10-15

- Core without GUI: profiles, TOML config with validation, token file, SQLite state.
- Lanes: people, replies to me, other mentions, bots, my posts, local, follow requests.
- Forward catch-up with `min_id`: reading stays chronological, no holes.
- Read marks per post; start at the first unread; new posts never move the view.
- Reply context strip above every reply; threads as trees with `/N` numbering.
- Composer: drafts saved while typing, Markdown when the server supports it,
  attachments with alt text, reply visibility never wider than the parent.
- Qt frontend: tray, notifications.
- New look (from the mockup): sidebar with account, Write button and unread badges; lane
  header with "N new", All | Posts only; cards with round avatars, short `#ids`, quoted reply
  context, flat action buttons; "new below" divider; thread rails and `/N` numbers.
- Themes are files: `system` (follows KDE light/dark) and `terminal`; your own in
  `~/.config/fedtail/themes/`, with inheritance.
- Image viewer over the main window; "you replied" under comments; posts-only toggle;
  `--update-config`; Russian plural forms.
