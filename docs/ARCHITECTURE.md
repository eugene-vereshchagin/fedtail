# fedtail — architecture

This document is for whoever works on the code next, human or AI. It describes
how fedtail is put together, why, and where to change what. Read it top to
bottom once; later use it as a map. `docs/DESIGN.md` (Russian) holds the product
spec and the queue of planned work; `docs/DEBUGGING.md` explains the logs.

Contents

1. What fedtail is
2. Repository map
3. Start-up sequence
4. Threads and the rules that keep them apart
5. Data: Mastodon objects, ids, ordering
6. The store (SQLite)
7. Sources and catch-up
8. Lanes
9. One poll, step by step
10. Read state and "never jump"
11. Reply context and "you replied"
12. Features built on top: threads, subscriptions, lists, activity, search,
    honest counters, saving, hashtags
13. Events (core → frontend)
14. The Qt frontend
15. Themes
16. Configuration
17. Strings (i18n)
18. Diagnostics
19. Tests and CI
20. Recipes: how to add things
21. Conventions and traps

---

## 1. What fedtail is

A desktop client for the fediverse (GoToSocial, Mastodon, Akkoma — anything with
the Mastodon REST API), written in Python. Its point is **context**: people get
pulled away by a toot and come back not remembering what the talk was about, so
every reply shows what it answers, your own answer is shown under a comment,
threads open as trees at the post you came from, and lanes remember where you
stopped and never jump. It takes after Point.im and Juick.

Principles that shape the code (from DESIGN.md):

* **Nothing jumps.** New posts never move what you are reading.
* **Every reply knows its parent.** A quote of the parent is above every reply.
* **Lanes are separate.** Home, bots, replies to me, other mentions, …
* **Private by default.** A new post goes to followers; a reply is never more
  public than its parent.
* **All behaviour is flags in a config file.** No settings window, ever.
  (Server-side data such as your profile is edited in a dialog: that's not a
  client setting.)
* **The core knows nothing of GUIs.** Frontends are plugins; Qt is the first.
* **One process = one account.** A second account is a second profile.

## 2. Repository map

```
fedtail/
  __init__.py        __version__ (the release being worked towards, PEP 440)
  __main__.py        CLI: parses flags, loads config, sets up diagnostics,
                     single-instance check, picks a frontend, runs it
  version.py         the displayed version: 0.2.0.devN+gSHA from git, or _build.py
  diag.py            logs, crash traces, stack dumps, stats, freeze watchdog,
                     bug-report archive (no Qt)
  desktop.py         --install-desktop: .desktop entry + icon in ~/.local/share
  i18n.py            interface strings, ru/en, Russian plural forms
  sysenv.py          the one-file build: start other programs with the system's environment
  core/              everything that is not GUI
    app.py           Core: the facade the frontends talk to (see §4, §9)
    stream.py        the live stream: a stdlib WebSocket client that wakes the poller
    api.py           Mastodon REST client (blocking, requests) + request logging
    auth.py          token file (JSON, 0600)
    config.py        DEFAULTS, validation (types, choices, minimums)
    config_update.py --update-config: adds missing options; refreshes our
                     explanations above existing ones; drops commented-out options that are gone
    counters.py      honest counters: ask the post's own server
    replies.py       ActivityPub reading without my token: a post's replies collection,
                     an actor's outbox (newest public posts), followers/following lists
    events.py        tiny event bus (handlers run in the emitting thread)
    hashtags.py      one-case hashtags for the CamelCase hint
    links.py         @mentions, #tags, fediverse links → in-app links
    instance.py      one window per profile (unix socket)
    merged.py        MergedCore: several Cores behind one face (all accounts in one window);
                     other accounts' ids are prefixed "profile~id", actions routed by it
    profiles.py      the profiles there are (profile.json: acct + server, no token), how to
                     start another one (the account switcher, --profiles)
    lanes.py         Lane = source + filter; built-in lanes; list lanes
    model.py         helpers over status/account dicts (real(), snippet(), …)
    paths.py         where a profile's files live (XDG)
    saving.py        where/how to save pictures
    search.py        Ctrl+F matching (haystack / matches)
    sources.py       server streams, forward catch-up with min_id
    store.py         SQLite: statuses, items, read marks, drafts, aliases, …
    subs.py          thread subscriptions (Point-style)
    threads.py       context → flat tree with depth and /N numbers
  frontends/
    __init__.py      registry: name -> module with run(core, instance, argv)
    web/             the browser interface: server.py — http.server + a JSON API over the
                     Core, key in a cookie, CSP; the page is data/web/ (index.html, app.js,
                     app.css)
    richtext.py      server HTML → the safe subset shown (QLabel, the web page); no Qt
    tui/             the terminal interface (Textual): model.py — posts as lines and the
                     command line, no Textual (tested alone); app.py — the screens
    cli.py           terminal commands (lanes/show/tail/post/read): plain stdout,
                     no Qt, no single-instance lock; `fedtail COMMAND …`
    notifytext.py    what a desktop notification says (no Qt, tested)
    iconart.py       the app icon as SVG, drawn from a theme's [icon] colours
    themefile.py     theme TOML files: find, inherit, validate (no Qt)
    qt/              the Qt Widgets frontend (PySide6)
      __init__.py    run(): QApplication, theme, Bridge, MainWindow, diagnostics
      bridge.py      core futures and events → GUI thread (Qt signals)
      window.py      MainWindow: sidebar, tabs, menu, event dispatch, actions
      feed.py        FeedView (scrolling list of cards), LaneWidget,
                     ThreadWidget, AccountWidget, RequestsWidget, ActivityWidget
      card.py        PostRow (one post), CardSpec, SeparatorRow, media grid
      compose.py     the compose dialog (drafts, media, drag&drop, CW, hint)
      text.py        server HTML → QLabel rich text (an allow-list sanitizer: no scripts,
                     no pictures from paths, links only to the web or inside); dates;
                     emojify(): :shortcodes: → our own <img> of the cached emoji file
      kde.py         the one-file build in KDE: colours, font, icons from kdeglobals
      opener.py      links and files to the desktop's programs (via sysenv when frozen)
      theme.py       Theme object, palette, the generated QSS
      images.py      avatars/pictures: disk+memory cache, own thread pool, save
      viewer.py      picture viewer drawn over the main window
      find.py        Ctrl+F bar
      notify.py      desktop notifications (notify-send, tray fallback)
      profile.py     "edit my profile" dialog
      login.py       first-run login dialog (OAuth out-of-band code)
      diagnostics.py Qt messages → log, freeze watchdog, widget counts
  data/
    config.example.toml  the full config in chapters (Russian), the reference
    themes/*.toml        built-in themes (system.toml lists every key)
    icons/fedtail.svg    app icon
tests/               unittest; fakes.py is an in-memory Mastodon
tools/screenshots.py renders the window with made-up data (CI publishes PNGs)
.github/             CI workflow; annotate.py turns test failures into annotations
docs/                DESIGN.md (spec, queue), ARCHITECTURE.md, DEBUGGING.md
```

## 3. Start-up sequence

`python3 -m fedtail [--profile NAME] …` → `fedtail/__main__.py:main()`:

1. Parse flags. `--install-desktop` exits right away.
2. `paths.resolve(profile, config, data)`: config file
   `~/.config/fedtail/<profile>/config.toml`, data dir
   `~/.local/share/fedtail/<profile>/` (0700). Overridable by `--config/--data`.
3. `config.load()` → validated `cfg` dict (see §16). A broken config prints the
   reason and exits with code 2.
4. Writes `config.example.toml` next to the user's config (always the current
   reference) and reports options the user's file doesn't mention yet;
   `--update-config` inserts them and exits.
5. `--bug-report` packs the logs (§18) and exits.
6. `i18n.setup(cfg.ui.language)`.
7. `SingleInstance`: if another process of this profile answers on its unix
   socket, it is asked to raise its window and we exit.
8. `diag.setup()` — log file, crash/stack files, exception hooks — then the
   session header and the stats thread.
9. `frontends.load(name)` imports the frontend module; `Core(cfg, paths)` opens
   the store and creates the thread pools (no network yet).
    A terminal command (`fedtail show comments`) stops before the lock:
    `__main__._terminal()` → `cli.run(core, argv)`, which connects, polls once,
    prints, and leaves.
10. `frontend.run(core, instance, argv)` — for Qt (`frontends/qt/__init__.py`):
    QApplication → `theme.apply()` → `Bridge(core)` → `MainWindow` →
    `diagnostics.install()` → `win.show()` → `win.start()`.
11. `MainWindow.start()`: no token → `LoginDialog` (OAuth OOB: the browser shows
    a code, the user pastes it). Then `core.connect()` (in the pool): verify the
    account, read instance capabilities, build sources, read lists → `ready`.
    `_connected()` fills the sidebar, selects the last lane, and
    `core.start_polling()` starts the poller thread.

## 4. Threads and the rules that keep them apart

| thread | what runs there |
|---|---|
| GUI (main) | all Qt objects; Bridge slots; never blocks on the network |
| `fedtail-poll` | `Core._poll_loop`: `poll_once()` every `poll.interval_seconds` or when woken (`poll_now()`) |
| `fedtail-stream` | `core/stream.py`: the server's WebSocket stream (`poll.stream`); an `update` / `notification` only calls `poll_now()` — the poll still fetches, so a dropped stream loses nothing; reconnects with backoff 5 s…5 min; the token goes in the handshake headers, never the URL or the log |
| `fedtail_*` pool (4) | user actions: post, favourite, open thread, profile… (`core.submit`) |
| `fedtail-bg` pool (2) | background work: parents, "did I reply?", subscriptions on demand, honest counters |
| `fedtail-img` pool (4) | image downloads and saving (in `Images`) — a backlog of avatars never delays sending a post |
| `fedtail-instance` | the single-instance socket |
| `fedtail-stats`, `fedtail-watchdog` | diagnostics (§18) |

Rules:

* **The core never imports Qt.** It returns `concurrent.futures.Future`s and
  emits events. Everything Qt lives in `frontends/qt`.
* **Qt objects are touched only in the GUI thread.** `Bridge.call(future, ok,
  fail)` runs the callbacks in the GUI thread (via a queued signal). Core events
  arrive through `Bridge.event` (also queued). `QImage` may be built in workers
  (images.py does), `QPixmap` only in the GUI thread.
* **The store has one SQLite connection guarded by an `RLock`.** Every method
  takes the lock for a short transaction (`with self._tx()` for writes). WAL mode.
* `Core.poll_once` holds `_poll_lock`, so polls never overlap, and shutdown
  closes the store only after the poller has stopped.
* Widgets can be deleted while a future is in flight: callbacks that touch a
  widget catch `RuntimeError("…already deleted")` (Bridge does it centrally).

## 5. Data: Mastodon objects, ids, ordering

* Statuses and accounts are kept as the **server's JSON dicts**, unchanged. No
  model classes. `model.real(st)` returns the boosted status for a boost, else the
  status itself — use it whenever you mean "the post".
* Ids are opaque strings: GoToSocial uses ULIDs, Mastodon snowflakes. Never
  compare ids numerically. For ordering, `store.sort_key(created_at, id)` builds
  `"<iso time>|<id left-padded to 32>"`, which sorts chronologically for both.
* A **short id** (Point's `#a3f`) is a local alias: `aliases` table, a letter
  then base-36 (`a00`…`zzz`, then 4 chars). Stable, never reused, per profile.
* `in_reply_to_account_id == me` means "a reply to me" (`model.is_comment_to_me`).
* Bots: `account.bot` or listed in `lanes.extra_bots`.

## 6. The store (SQLite, `state.db` in the data dir)

| table | holds |
|---|---|
| `statuses(id, data, created_at, reply_to, author)` | every status we've seen, JSON; `reply_to`/`author` columns for fast "my replies to X" |
| `items(source, item_id, status_id, sort)` | the entries of each source (a timeline is a list of items pointing at statuses; mentions use notification ids) |
| `read(status_id)` | read marks |
| `missing(status_id)` | parents the server refused (404/403/410) — shown as "post unavailable" |
| `drafts(key, data, updated)` | compose drafts; key `new` or `reply:<id>` |
| `aliases(n, status_id)` | short ids |
| `subs(root_id, since, last_activity, checked, auto)` | followed threads |
| `sub_members(status_id, root_id)` | posts already seen in a followed thread |
| `unsubs(root_id)` | threads the user left (auto-subscribe never returns) |
| `activity(id, type, account, status_id, sort)` | favourites/boosts/follows notifications |
| `kv(key, value)` | small JSON state: `initialized`, `source_since:<src>`, `activity_seen`, GUI state (`geometry`, `lane`, `posts_only.<lane>`, …), `replies_checked:<id>` |

* `Store.items_version[source]` and `status_version` are bumped on every change;
  `Core.lane_entries` uses them as a cache key.
* Schema changes: `CREATE TABLE IF NOT EXISTS` for new tables; column additions
  go in `Store._migrate()` (see the v2 `reply_to` migration). Never drop data.
* `prune(source, keep)` keeps the newest `KEEP_PER_SOURCE` (3000) items per source.

## 7. Sources and catch-up (`core/sources.py`)

A **source** is a server stream: `home`, `mentions` (notifications of type
mention), `mine` (my statuses), `local`, and `list:<id>` for each list. A Source
has `fetch(limit, max_id, min_id)` and `entry(raw) → (item_id, status, created)`.

* `catch_up()` walks **forward** from the newest stored item with `min_id`, page
  by page, until a short page or `feed.catch_up_limit`. So the local copy has no
  holes and reading can be chronological.
* First time (`_fill_empty`): one page. If the source was watched before but was
  empty (`kv source_since:<name>`), it walks back to that moment so nothing that
  arrived meanwhile is skipped.
* `fetch_older()` is the "Older" button: one page with `max_id` of the oldest item.
  Older history counts as read.
* `subs` is a *local* source (filled by `core/subs.py`, not fetched);
  `lanes.LOCAL_SOURCES` keeps it out of `sources_needed`.

## 8. Lanes (`core/lanes.py`)

A lane is what the sidebar shows: `Lane(name, source, keep, by_status_time)`.
`keep(status, ctx)` filters the source's items; `ctx` is a `LaneContext(me_id,
extra_bots, mentions_all, subs_replies_to_me, hidden)`.

| lane | source | keeps |
|---|---|---|
| `people` ("Home") | home | not bots, not in an exclusive list |
| `comments` ("replies to me") | mentions | replies to my posts/comments |
| `mentions` | mentions | other mentions (`lanes.mentions_all` → all) |
| `subs` ("Subscriptions") | subs (local) | new comments in followed threads, minus replies to me |
| `bookmarks` | bookmarks | still bookmarked; *lazy*; paged by the Link header (`sources._Cursor`); `core.bookmark()` adds/removes at once |
| `activity` ("Likes & boosts") | — (own table) | favourites, boosts, follows (`ActivityWidget`) |
| `bots` | home | bots, not in an exclusive list |
| `mine` | mine | everything |
| `local` | local | everything; *lazy* |
| `global` ("Federated") | federated | everything; *lazy* |
| `requests` | — | follow requests (`RequestsWidget`) |
| `list:<id>` | list:<id> | everything (one per server list, appended after the built-ins) |

* **Lazy (browse) lanes** — `local`, `global`: fetched only while on screen
  (`core.set_active_lane`, called by the window on every lane switch), newest page
  only (`sources.refresh_top`; a hole is fine there), no unread marks or badges.
* **Sidebar sections** — `lanes.GROUPS` / `lanes.grouped()`: Timelines, from the
  widest down (global, people, local, bots), Personal (mine, mentions, comments,
  subs, bookmarks, activity, requests), Lists at the bottom; the configured order holds inside
  a section
  (`ui.sidebar_groups = false` → one flat list). `MainWindow._rebuild_sidebar()`
  builds it (again on `lists_changed`); Alt+1…9 follow `lane_order`, not rows.

* `lanes.enabled(cfg, lists)` builds the list from `lanes.enabled` plus list lanes.
  `Core._apply_lists()` replaces `Core.lanes`/`lane_by_name` when lists change.
* `Core.lane_entries(name)` returns `[(item_id, status)]` oldest → newest, at most
  `feed.render_limit` (raised by "Older" and by Ctrl+F "Deeper" via `_limits`),
  filtered by `keep` and by "posts only". Cached until the store changes.
  `by_status_time` lanes (notifications) are sorted by the post's own time.
* List members leave the general lanes: `Core._hidden_authors()` collects members of
  every list (`lists.hide_members = "all"`; or only exclusive lists, or none) and
  `lanes.keeps()` drops their posts and boosts from the lanes in `lists.hide_in`
  (people, bots, global, local by default); their list lane shows them.

## 9. One poll, step by step (`Core._poll_once`)

1. Lists and members re-read every `lists.refresh_minutes` (`_refresh_lists`).
2. Subscriptions checked (`subs.check`) → new items in source `subs`.
3. Every needed source caught up (`sources.catch_up`) and pruned. 401/403 →
   event `auth_failed` and stop.
4. Follow requests fetched; new ones (vs. the previous poll) noted.
5. Activity notifications fetched forward (`_poll_activity`); the very first
   fetch is history (marked seen).
6. Read rules: on the very first run everything is marked read
   (`feed.first_run_mark_read`); my own posts are always read; a post I replied
   to (from any client) is read.
7. My new posts/comments are auto-subscribed (`subs.auto`).
8. New items are split per lane → event `lanes_updated {lane: [item ids]}`.
9. Desktop notifications for the lanes in `notify.lanes` (unread ones only) →
   event `notify [(lane, status|account|notification)]`.
10. Parents of new replies fetched in the background (event `parents`).
11. A log line with what came and how long it took.

## 10. Read state and "never jump"

* Marks live in `read`. The GUI decides what was *seen*: `FeedView._emit_seen`
  (350 ms after scrolling stops) reports cards fully on screen (or tall cards
  scrolled past, or the tail at the end) → `core.mark_read`. Modes:
  `read.mark_read = on_scroll | on_open | manual`.
* Opening a lane stands on the first unread (`feed.start_at`); a separator row
  "new below · N" is fixed where the reader stood when the lane opened.
* Keeping position: `FeedView` keeps a **target** (`("anchor", key, offset)`,
  `("row", key, top|bottom)` or `("end", …)`) and re-applies it on every
  `rangeChanged` until the user scrolls or 1.5 s pass — word-wrapped labels get
  their real height several layout passes later, so a one-shot scroll would miss.
  `set_specs()` re-uses existing rows and keeps the top card where it was.
* Hidden lanes only set `dirty`; they rebuild when shown.

## 11. Reply context and "you replied"

* `core.parents_for(statuses)` → `{id: parent | "missing" | None}` in two
  queries. Unknown parents are fetched by `ensure_parents` (bg); refusals go to
  `missing`. Cards show the quote above the text (`card._context_html`).
* `core.my_replies(statuses)` → my replies per post from the `reply_to/author`
  columns. `check_my_replies` (comments/mentions lanes) fetches the context of
  posts with replies we don't know, once per reply count, so answers made from
  other clients show up as "you replied".

## 12. Features built on top

* **Threads** — `core.thread(id)`: status + `/context`, stored, flattened by
  `threads.build()` into depth-first order with `/N` numbers; replies whose parent
  is invisible hang under the root. `ThreadWidget` focuses the post you came from.
* **Subscriptions** (`core/subs.py`) — Mastodon has none. A followed thread is a
  `subs` row (root id) + `sub_members` (posts already seen). `check()` re-reads the
  context of due threads (`interval_minutes`, only threads active within
  `active_days`, `max_threads` per round) and puts posts that aren't members, are
  newer than `since` and aren't mine into source `subs`. Manual subscribe: every
  current post is "seen". Auto (own posts/comments): posts after mine are news.
  Unsubscribing records `unsubs` so auto never comes back.
* **Lists** — server lists, see §8. CRUD and membership go straight to the API,
  then `_refresh_lists()` → event `lists_changed` → sidebar rebuild.
* **Activity** — `notifications?types[]=…` (`activity.types`) stored in
  `activity`; unread = newer than `kv activity_seen`; `ActivityWidget` groups
  neighbouring entries of one kind about one post.
* **Search** — `core/search.py`: a case/ё-insensitive haystack (text, CW, alt
  texts, author name and @handle, booster, `#id`); every query word must occur.
  `FindBar` searches the rows on screen; `core.deep_find()` walks everything
  stored for the lane and raises its render limit down to the next match.
* **Honest counters** — `core/counters.py`: for public posts from other servers,
  GET `https://<origin>/api/v1/statuses/<id>` *without the token*, keep the bigger
  numbers; once per post per 10 minutes; off by default (`feed.honest_counters`).
* **Whole threads** — `Core._thread_nodes()` reads the context of the *top* post (a
  post's context has its own branch only), so a thread looks the same from any post.
  `core/replies.py` + `Core._complete_thread()`: the top post's ActivityPub object is
  fetched from its server (no token), its `replies` collection walked a few levels
  down, and every reply address my server doesn't know is resolved through my server
  (`/api/v2/search?resolve=true`); then `thread_grew` makes the open thread reload.
  Once per thread per 5 minutes; `feed.complete_threads`.
* **Saving pictures** — `core/saving.py` (where, file name, no overwrite) +
  `Images.save()` (from the cache when possible).
* **CamelCase hint** — `core/hashtags.flat_tags()`, shown under the compose text.
* **Links stay inside** — `core/links.in_app(html, status)` rewrites hrefs before
  `text.clean()`: known @mentions → `fedtail:account/<id>`, hashtags →
  `fedtail:tag/<name>`, fediverse-looking profile/post addresses (and unknown
  mentions) → `fedtail:resolve/<quoted url>`. `core.resolve(url)` asks the user's
  server (`/api/v2/search?resolve=true`) and the window opens the thread or the
  profile; the browser only if nothing is found. Flag `ui.links_in_app`.
* **Command line** — `core/commands.py` parses a line into a `Command` (pure,
  tested); `qt/cmdline.py: CommandBar` previews what Enter will do and runs it
  through `core.target(alias, n)` (a short id, or comment /N of its thread),
  `core.find_user`, `core.post/boost/bookmark/subscribe/follow`.
* **Conversations view** — `threads.conversations(entries, get_status, unread)`
  groups lane entries by the highest known post of their thread; `LaneWidget`
  builds one card per group (`extra["conversation"]`), and a seen card marks all
  its members read. Offered over Replies to me, Mentions and Subscriptions only
  (`feed.CONVERSATION_LANES`); kept for the run by `core.choice()` (or in `kv` with
  `feed.remember_choices`), like All | Posts | New.
* **Editing** — `core.source()` (`/statuses/:id/source`, the typed text) →
  `Compose(edit=st)` → `core.edit()` (`PUT /statuses/:id`, media ids passed again so
  they stay); `core.history()` feeds `MainWindow.show_history`; cards show "edited"
  when `edited_at` is set. Drafts of edits use the key `edit:<id>`.
* **Silence** — `core.mute/block` (server) + `core.muted/blocked` sets refreshed every
  `lists.refresh_minutes`; `core.silenced(st)` (author or booster muted/blocked, or a
  server filter with action "hide") is applied in `lane_entries` and `_notify`; "warn"
  filters fold the card like a CW (`card._build`). Filters: `/api/v2/filters`
  (`core.filters/add_filter/delete_filter`), `qt/silence.py` is the dialog.
* **Search and follow** — `core.search(q)` (`/api/v2/search?resolve=true` +
  relationships), `core.people(acc, "following"|"followers", max_id)` (Link-header
  paging via `Api.get_page`), `core.follow`, `core.follow_tag`/`tag_info`/
  `followed_tags`. Qt: `SearchWidget` (the sidebar box, Ctrl+K), `PeopleWidget`,
  reusable `AccountRow` and `TagRow` with their own Follow buttons.
* **Post content** (`card.py`) — `_link_card` (status.card; `feed.link_cards`),
  `_emoji_label` (custom emoji: `text.emojify` points `<img>` at the picture already in
  `Images` cache, `Images.local(url)`, and re-renders the label when a missing one
  arrives; `feed.custom_emoji`), `_quote` (`model.quoted()` understands Mastodon 4.5
  Quote/ShallowQuote, Akkoma/Fedibird whole-status quotes; states other than
  "accepted" are explained; `model.without_quote_fallback` drops the "RE:" paragraph;
  `feed.quotes`), sensitive media covered until clicked (`feed.sensitive_media`),
  translation via `ctx.translate` (`feed.translate`; the card keeps it and toggles).
* **Completion in the composer** — `#` from `store.tag_counts()` + followed tags, `@` from
  `store.people_counts()` then `core.search_people()` (no resolve), both built lazily in
  one SQL pass (json_each) and kept up to date by `put_statuses`; `Compose._offer`.
* **Markers** — `Core._sync_markers()` after each poll (`read.sync_markers`): pull —
  everything up to another client's `last_read_id` (home → source home, notifications →
  source mentions) is marked read once per new marker; push — the newest item such that
  everything older is read goes to the server. Ids compare with `model.id_after`
  (numbers or same-length ULIDs).
* **Async refresh** — Mastodon 4.5 answers `/context` with `Mastodon-Async-Refresh`;
  `Api.last_async_refresh()` reads the last response's headers (thread-local);
  `Core._await_refresh()` polls `/api/v1_alpha/async_refreshes/:id` and emits
  `thread_grew` when it's finished.
* **Remote profiles** — `Core.posts_from_origin(acc)`: the actor (acc.uri or url,
  AP Accept), its outbox's first pages (`replies.outbox_post_uris`: Create, public),
  each resolved through my server (`feed.remote_profiles`, `remote_posts`);
  `AccountWidget._from_origin` asks when my server has fewer posts than the profile
  counts. `Core.people_from_origin(acc, which)`: the actor's followers/following
  collection, resolved likewise, on the "more — from their server" button
  (`feed.remote_people`).
* **Direct** — lane `direct` = source mentions, visibility direct; with
  `lanes.direct_apart` such posts leave comments/mentions (`LaneContext.direct_apart`).
* **Posting extras** — `Core.post(..., sensitive, poll, quote, scheduled_at)`: polls
  (`Compose._build_poll`), `quoted_status_id` + `post.quote_policy`, GoToSocial
  `interaction_policy` from `post.who_can_*` (`model.interaction_policy`, sent only to
  GoToSocial), `scheduled_at` (the answer is a ScheduledStatus; `show_scheduled`).
* **Moderation and people** — `core.report` (`/api/v1/reports`), `core.block_domain`
  (`blocked_domains` joins `silenced()`), `core.set_note` (relationship.note), pinned
  posts (`core.pinned`, `core.pin`; `AccountWidget.render` puts them first).
* **Keys** — `FeedView.keyPressEvent`: j/k move `cursor_key` (card property `keyed`),
  r/f/b/m/o act through `ctx.on_link` (`ui.post_keys`).
* **Profiles and tags** — `AccountWidget` (info card: bio, fields, counts, since,
  "follows you", Follow/Mention/Add to list/browser; `core.relationship/follow`)
  and `TagWidget` (`core.tag_timeline`) share `_PagedTab` (a server timeline read
  page by page). Clicking the name of the person whose tab is open scrolls back
  to their card.

## 13. Events (core → frontend)

Emitted with `Core.emit(name, payload)` from any thread; the Qt Bridge re-emits
them in the GUI thread; `MainWindow.on_event` dispatches.

| event | payload | when | GUI reaction |
|---|---|---|---|
| `ready` | me | connected | — (the connect future's callback does the work) |
| `lanes_updated` | {lane: [item ids]} | new items, older loaded, lists membership | refresh those lanes, badges |
| `parents` | — | parents or "my replies" fetched | refresh lanes and account tabs |
| `read_changed` | [status ids] | marks added | un-highlight cards, badges |
| `status_updated` | status | favourite/boost/honest counters | rows re-read from the store |
| `status_deleted` | id | my post deleted | rows removed |
| `requests_updated` | [accounts] | each poll | requests lane, badge |
| `activity_updated` / `activity_seen` | count / sort key | new activity / seen | activity lane, badge |
| `lists_changed` | [lists] | lists or members changed | sidebar list block rebuilt |
| `subs_changed` | root id | subscribe/unsubscribe | thread header buttons |
| `me_updated` | me | profile saved | sidebar name/avatar, my profile tab |
| `notify` | [(lane, obj)] | after a poll | `Notifier` (desktop notifications) |
| `error` | text | recoverable failure | status bar (and the log) |
| `auth_failed` | text | 401/403 | re-login dialog |

## 14. The Qt frontend

* **`ViewContext`** (window.py) is what a card needs from the window: cfg, theme,
  images, `on_link`, `open_url`, `show_images`, `me_id`, `subscribed`,
  `fill_list_menu`, `save_image`. Cards never import the window.
* **In-app links** are `fedtail:<action>/<arg>` (`text.link()`), handled in
  `MainWindow.on_link`: `thread`, `account`, `tag`, `resolve`, `reply`, `fav`,
  `boost`, `open`, `delete`, `sub`, `unsub`. Labels style links inline (QLabel ignores QSS for `<a>`).
* **`CardSpec`** (card.py) describes one row: status, depth, `/N` number, parent,
  unread, focus, in_thread, extra (my_replies, short_id, separator). `PostRow`
  rebuilds only when the spec really changed (`update_spec`).
* **`FeedView`** (feed.py) is a QScrollArea with a centred column of rows
  (`ui.max_width`), the target logic of §10 and the "seen" signal.
* **`LaneWidget`** = header (title, "N new", posts-only control, To new, All
  read, refresh) + FeedView + "Older" button. `refresh()` builds specs from
  `lane_entries`, parents, my replies, short ids and the separator.
* **`MainWindow`**: sidebar (account, Write, `QListWidget#lanes` of `LaneItem`s,
  the lists block, footer), a `QTabWidget` whose first tab is a `QStackedWidget`
  of lane widgets and whose other tabs are threads/profiles, the find bar,
  the tray, shortcuts. Esc closes what's on top; the last Esc shows the *curtain* (`right_stack` page 1: no lane on screen, so nothing is marked read; `ui.esc`).
* **Compose**: drafts are saved while typing (`post.drafts_autosave`); all exits
  go through `reject()` → `_leave()`; never call `close()` inside `reject()`
  (Qt's closeEvent calls reject → infinite loop). The core deletes the draft
  itself after a successful post (`draft_key`), even if the dialog is gone.
* **Images**: `get(url, callback, max_side, failed)`; memory cache of QPixmaps
  (an LRU bounded in bytes by `ui.image_cache_mb`) + disk cache (`cache/` by sha1 of the URL; only decodable files are kept); the
  feed asks for 1200 px, the viewer for the full size.
* **Notifications**: `notify.Notifier` → `notify-send --action=open --wait` in a
  thread (so "Open" can bring the window to the thread), tray balloon otherwise;
  silent while the window is active unless `notify.when_focused`.

## 15. Themes

* Files: `fedtail/data/themes/*.toml` (built-in) and
  `~/.config/fedtail/themes/*.toml` (user's, win over built-ins). A theme may
  `inherit` another. `system.toml` is the reference: every key with a comment.
  `themefile.load()` resolves inheritance and validates (no Qt).
* Sections: `[font]` (family list, mono, post_scale), `[colors]` (hex or "auto" =
  derived from the desktop palette), `[shape]` (radius, card style card|rule,
  avatars, icons, header rich|compact, unread mark, posts-only control), `[words]`
  (templates such as `lane_title = "== {text} =="`, date format, lowercase),
  `[icon]` (style bubble|terminal and colours; "auto" = from the accent — the
  frontend draws the icon with `iconart.svg()` into the cache dir at start-up).
* `qt/theme.py`: `Theme` resolves colours (`_auto_colors`, `_readable_on`),
  `stylesheet()` generates the whole QSS, `apply()` sets palette, fonts (only
  installed families — a missing one may be substituted with absurd metrics) and
  the stylesheet.

## 16. Configuration

* `core/config.py: DEFAULTS` is the single source of truth: section → key →
  default. `validate()` checks types strictly (bool is not int), `CHOICES`,
  `MINIMUM`, lane names; unknown keys are warnings, wrong values are errors.
* `fedtail/data/config.example.toml` documents every option in Russian, in chapters
  (a banner before each section, sub-headings inside `[ui]`; a comment block followed by
  a blank line belongs to no option), every option set to its default; a test asserts
  that parsing it gives exactly `DEFAULTS`.
* `config_update.py`: finds options the user's file doesn't mention, inserts them with
  their explanations (`--update-config`); `rebuild()` lays the user's file out anew from
  the example with their values put in (`--rebuild-config`).

## 17. Strings (i18n)

`i18n._("key", **kw)`; dicts for `ru` and `en` in `i18n.py`; a list value means
plural forms chosen by `n` (Russian has three). A test checks both languages have
the same keys. Code comments and docs are English; the UI defaults to the system
language.

## 18. Diagnostics

See `docs/DEBUGGING.md` for the user's side. In code: `fedtail/diag.py` sets up
the log (`SessionLog`: a file per start and per hour in `debug.log_dir/<profile>/`,
`latest.log` linking the current one, capped by `debug.keep_mb`), `crash.log` (faulthandler), `stacks.log`
(SIGUSR1, menu, watchdog), exception hooks for all threads, a stats thread with
providers (`diag.add_stats(name, fn)`: the core adds store/pool/cache counts, the
Qt frontend widget and image counts) and `bug_report()`. `qt/diagnostics.py`
routes Qt messages into the log and drives the `Watchdog` from a 1 s timer.
`api.py` logs every request (method, path, paging params, status, time, size —
never the token or bodies). Use `logging.getLogger(__name__)` in new modules.

## 19. Tests and CI

* `python3 -m unittest discover -s tests -t .` — no network, no display needed.
  Qt tests skip without PySide6; CI runs them offscreen.
* `tests/fakes.py`: `FakeApi` + `World` — an in-memory server (timelines,
  notifications, statuses with context, lists, activity, profile). `World.add()`,
  `World.act()`; `FakeApi.world` is shared by all instances the core creates.
* `test_core.py` — catch-up, lanes, notify, subscriptions, lists, activity,
  deep find, honest counters, drafts, store migration.
  `test_qt_smoke.py` — one long walk through the window (open lanes, compose,
  threads, find, Esc, profile, lists, activity, images, diagnostics).
  Others: config/CLI, themes, notifications text, search, text cleaning, saving,
  diagnostics.
* CI (`.github/workflows/ci.yml`): ruff; tests on Python 3.11–3.13 with pip
  PySide6; tests on Debian 13 with Qt from apt (the real target; it has no
  QtTest); `tools/screenshots.py` renders every theme with made-up data and
  force-pushes PNGs to the `screenshots` branch. `.github/annotate.py` turns
  failures into annotations (job logs aren't always downloadable).
* Lint: `ruff check .` (line length 100).

## 20. Recipes

**Add a config option.** Add it to `DEFAULTS` (and `CHOICES`/`MINIMUM` if needed),
document it in `config.example.toml` as `#key = value` with a Russian comment
above, read it via `cfg["section"]["key"]`. The example-equals-defaults test
tells you if they differ.

**Add a lane.** Filter function + `LANES` entry in `lanes.py`, add the name to
`config.LANE_NAMES` and (if on by default) to `lanes.enabled` in DEFAULTS and the
example; `lane_<name>` strings in both languages; an icon in `window.LANE_ICON`.
If it isn't a status stream, give it `source=None` and a widget in
`MainWindow._lane_clicked`.

**Add an event.** `self.emit("name", payload)` in the core; a branch in
`MainWindow.on_event`; a row in §13.

**Add a theme key.** Add it to `system.toml` with a comment (it's the
reference), use it in `qt/theme.py` / cards; the theme test checks all built-ins
still validate.

**Add a frontend.** A package `fedtail/frontends/<name>/` with
`run(core, instance, argv) -> int`, registered in `frontends/__init__.py`. Use only
the Core API (futures + events); see §13 for what to react to.

**Add a string.** Same key in `ru` and `en` of `i18n.py`.

## 21. Conventions and traps

* The public repo never names the author's own server; no server is hardcoded.
* The token lives only in `auth.json` (0600) and the `Authorization` header;
  nothing logs it; bug reports exclude it and the database.
* Requests to servers other than the user's (images, honest counters) never carry
  the token.
* `Compose.reject()` must not call `close()`.
* Debian's PySide6 has no QtTest: tests send key events with `QApplication.sendEvent`.
* Qt deletes widgets under you: guard callbacks (`RuntimeError … already deleted`).
* A test helper inserted between a decorator and its class silently drops the
  decorator — keep `@unittest.skipUnless(HAVE_QT…)` directly above the class.
* Commit messages: what changed and why; English. Comments: English. Russian
  for the user-facing config reference and README.ru.md.
