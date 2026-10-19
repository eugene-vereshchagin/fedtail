# Changelog

## 0.16.0 — in progress

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
