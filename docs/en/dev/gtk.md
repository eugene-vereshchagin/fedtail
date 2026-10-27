# fedtail: the GTK frontend

Status: **a draft plan, 21 Oct 2026**. Stage 0 started (`palette.py`, `pango.py`), the skeleton (stage 1)
is ready; the rest in turn. As things get ready, their description moves to architecture.md (§14 — Qt, there will be §14a — GTK).

## Why and for whom

Qt is a native KDE application. GTK is for the "GNOME folk": GNOME, Cinnamon, MATE, XFCE, Budgie,
so that fedtail looks at home there and not like a guest from KDE. The principles are the same:
nothing jumps, every reply shows its parent, all behaviour is config flags, there's no settings
window. The frontend is picked with `ui.frontend = "gtk"` or `fedtail --ui gtk`.

## The stack

| what | choice | why |
|---|---|---|
| toolkit | **GTK 4** through PyGObject | GTK 3 is living out its days; Debian 13 has GTK 4.18 |
| libadwaita | **when possible, not required** (`ui.adwaita = auto / on / off`) | in GNOME it's "not native" without it, in XFCE/MATE/Cinnamon it's foreign with it; the frontend must work without it |
| minimal versions | GTK ≥ 4.10, libadwaita ≥ 1.4 (if present) | Debian 12 has 4.8, too old; Ubuntu 24.04 — 4.14 and Adw 1.5; Debian 13 — 4.18 and Adw 1.7 |
| Debian 13 packages | `python3-gi gir1.2-gtk-4.0` (+ `gir1.2-adw-1`) | go into the deb package's "Recommends", not "Depends" |
| Windows | **not doing it** | GTK on Windows means MSYS2 and pain; Qt stays there |

## What's already there and fits as it is

The core and `core/view.View` (the model, not the server's JSON), `richtext` (the sanitizer), `themefile` (themes
without Qt), `helpdocs`, `notifytext`, `fedstatus`, `iconart`, `core/commands`, `model.text`,
`View.roster()`. The protocol layer (stages 0–4 of protocols.md) is exactly what's needed: GTK
is written on the model from the start and never sees raw data.

## The main problem: logic stuck in Qt

A look through `frontends/qt/` showed that of ~16,000 lines roughly **2,700–3,000 aren't Qt**, but
decisions about "what to show and what to do" living inside widgets. Unless they're moved out, GTK
will copy them, and the two frontends will start to behave differently. Candidates, by size:

| what | where now | lines | where to |
|---|---|---|---|
| the picture cache: an LRU in bytes, a queue "newest first, but no starving", retries, disk cleaning | `qt/images.py` | ~400 | `common/images.py` ✓ (the decoder, the size, "on screen" and the timer stay with the toolkit: `qt/images.py`, `gtk/images.py`) |
| building cards for a lane/thread/profile, the "new below" separator, the start position, filters, "read" | `qt/feed.py`, `qt/card.py` (`CardSpec`, `make_spec`) | ~450 | `common/lane.py` ✓ (Qt and GTK on it: filters, conversations, the media funnel, "read") |
| a post's menu and buttons: which actions, when, with which `fedtail:` link | `qt/card.py` `_fill_more`, `_actions` | ~150 | `common/actions.py` ✓ (Qt on it) |
| parsing `fedtail:<action>/<arg>` links | `qt/window.py` `on_link` | ~90 | `common/links.py` ✓ (Qt on it; confirmations through a window hook) |
| the rules of "write": the draft key, a reply's visibility, mentions, CW, the counter, completion | `qt/compose.py`, `qt/dock.py` | ~260 | `common/compose.py` ✓ (Qt on it) |
| a theme's colours: "auto" from the palette, FOLLOWS/TINTS, mixing, contrast | `qt/theme.py` | ~150 | `frontends/palette.py` ✓ (Qt on it) |
| the Point command line | `qt/cmdline.py` (nearly a copy of `tui/model.Commands`) | ~110 | `common/commands.py` ✓ (Qt, TUI, web on it) |
| the split rules: the input line (where it goes, who sees it), tabs, the face under the cursor | `qt/dock.py`, `qt/roster.py`, `qt/window.py` | ~130 | `common/split.py` ✓, `common/roster.py` ✓ (Qt on them; GTK — at stage 6) |
| grouping and the words of "Activity" | `qt/feed.py` | ~80 | `common/activity.py` ✓ (Qt on it) |
| search, the sidebar's badges/folding, notification decisions | `find.py`, `window.py`, `notify.py` | ~270 | `common/find.py` ✓, `common/sidebar.py` ✓ (GTK folds sections), `notifytext.due` ✓ |
| handling the bridge's results; the server page, the probe table, editing the profile; announcements, filters, the muted — on the model | `bridge.py`, `social.py`, `profile.py`, `announce.py`, `silence.py` | ~200 | `common/results.py` ✓, `common/server.py` ✓, `common/announce.py` ✓; `model.WordFilter`, `Silenced`, `Announcement` ✓ |

**How we do it:** move out one at a time; Qt switches to the shared module in the same go. The
decisions are checked in `tests/test_common.py` without a toolkit; the Qt smoke test runs locally on your
machine (the sandbox has no PySide6). Shared code doesn't import a toolkit — a test checks that. What stays in
Qt is about widgets: layout, the message window's tabs (`MessageTabs.sync`), drawing.

Leaks found along the way that must be closed before copying: `qt/silence.py` and
`qt/announce.py` read the server's raw dicts; `View.read_ids` reaches into `_core.store`;
`richtext.plain_tip` wraps text in Qt's `<qt>…</qt>`; architecture.md §13 doesn't describe the
events `arrived`, `thread_grew`, `rate_limited`, `capabilities_changed`, `prefetch`,
`prefetch_video`.

## GTK's problems and the answers

| problem | answer |
|---|---|
| **A post's text.** Qt draws an HTML subset in a QLabel; GTK understands only Pango markup: no `<p>`, `<br>`, `<blockquote>`, `<ul>`, no styles on links | `frontends/pango.py` ✓: sanitized HTML → Pango (paragraphs — an empty line, a quote — `▎` and italics, lists — `•`/numbers, `<code>` → `<tt>`); links stay `<a href>`, Gtk.Label catches them with the `activate-link` signal |
| **Themes.** Qt's QSS is generated whole; GTK has CSS with other selectors | the shared `palette.py` works out the colours, and `gtk/theme.py` writes its own CSS from them (classes `.ft-card`, `.ft-unread`…). Theme keys are the same, theme files are shared |
| **"auto" colours.** GTK 4 has no desktop palette API (like `QPalette`) | light/dark — from `Adw.StyleManager` or `gtk-application-prefer-dark-theme`; the accent — from Adw ≥ 1.6 (`get_accent_color_rgba`), otherwise Adwaita blue; the base — Adwaita light/dark reference colours. The "system" theme on GTK means "like Adwaita" |
| **"Nothing jumps".** Qt keeps its own column with its own scroll-window maths | a lane is a `Gtk.ListBox` in a `ScrolledWindow`, rows by key, nothing on screen is rebuilt: new ones are appended at the end (`oldest_first` — the default), "Older" inserts on top and shifts the scroll by the added height. For `newest_first` — the same, mirrored. Long lanes later — `Gtk.ListView` with a model (virtualization), when we hit the limit |
| **Read marks.** Qt decides "seen" by the cards' geometry | the same predicate (moved out of `feed._emit_seen` into a function of the card's and the window's top/bottom), GTK calls it on the scroll's `value-changed` |
| **Threads.** The core calls back from its own threads | `gtk/bridge.py` ✓: `GLib.idle_add` — the counterpart of Qt's signal queue, the same error classification |
| **The tray.** GTK 4 has no tray, GNOME has none at all | `StatusNotifierItem` over D-Bus through Gio, if there's a host (KDE, XFCE, Cinnamon, GNOME with AppIndicator); no host — `ui.close_to_tray` honestly doesn't work, and the log says so |
| **Notifications** | `Gio.Notification` through the application (native in GNOME, with an "Open" button), `notify-send` as the fallback, the "when" decisions shared with Qt |
| **One instance** | fedtail has its own socket (`SingleInstance`) — `Gtk.Application` is set `NON_UNIQUE` so they don't argue |
| **Video** | `Gtk.Video` (GStreamer) comes out of the box; no GStreamer plugins — "open outside" |
| **Pictures** | decode with `GdkPixbuf`/`Gdk.Texture.new_from_bytes` in a worker thread, `Gdk.Texture` is thread-safe (unlike QPixmap); the cache is the shared module |
| **The "split" layout (QIP)** | done on Qt; on GTK — after the usual layout, on the same `View.roster()` |
| **Checking without a screen** | in CI (Debian 13) — `xvfb-run`; `tests/test_gtk_smoke.py` runs the window on a fake server, `tools/gtk_screenshots.py` shoots it through `Gtk.WidgetPaintable` → PNG (no window manager) |
| **The taskbar icon** | `GApplication` wants an id with a dot; on Wayland the icon is found by the id. The id is `online.dmesg.fedtail`, the `.desktop` is named the same; on X11 — `prgname` "fedtail" under `StartupWMClass` |

## Order (in batches, a push at the end of a batch)

| stage | what | how we check |
|---|---|---|
| 0 ✓ | shared modules without Qt: `palette.py`, `pango.py`, `common/` — links, actions, compose, commands, activity, lane, images, sidebar, split, roster, find, results, server, announce | `tests/test_common.py`; the Qt smoke test locally |
| 1 ✓ | **the skeleton**: the application, the bridge, login (OAuth OOB), the sidebar of lanes in groups with badges, a lane of cards (context, CW, attachments as a line, ★ ♻), "seen is read", "All read", "older", a thread in a tab, fedtail's themes | `tests/test_gtk_smoke.py` under Xvfb on a fake server; screenshots |
| 2 ✓ | the whole card: the face, the reply's context, "you replied", pictures, CW, polls (results), a quote, a link card, the post's buttons and menu (shared with Qt), short ids → the command line; confirmations (delete, block…) | smoke + screenshots |
| 3 ✓ | write/reply/quote/call in/edit (drafts, visibility, CW, pictures with captions and "sensitive", shrunk to the server's limits, a reminder about the caption, a poll, completion on Tab, Ctrl+Enter), the Point command line (Ctrl+L), keys Ctrl+N/F5/Ctrl+W/Ctrl+Q; the editor is a panel over the window, as in Qt (⤡, the post's language, "Later", preview, "Discard", "Close"; `ui.compose = "window"` — as a window). ✓ (0.18) pictures and files by drag and drop and from the clipboard (`gtk/dropin.py`: into the editor — attachments, onto the window — a new post with them; Ctrl+Shift+V — always as text) | smoke: the post goes to the fake server |
| 4 ◐ | ✓ read marks by scrolling, "nothing jumps", "older", profiles (a tab: face, bio, fields, Follow, Mention, posts), "Activity" (rows from `common/activity.py`, shared with Qt; approve/decline, ×, seen is read), follow requests (let in/refuse), lane filters (all / posts only / new), "as conversations", the media funnel, folding the sidebar's sections, pictures from disk and with retries as in Qt; the sidebar's head as in Qt (face, ≡ ↔ ❯, "Write", searching people and tags, "+" by the lists, the version at the bottom), ↔ full width, ❯ columns, tabs: search, tag, suggestions, directory, trends; a status bar with the account; ✓ (0.18) Ctrl+F in a lane (`gtk/find.py`, the rules — `common/find.py`), a profile with all of Qt's buttons (`common/profile.py`: the bell, boosts and languages, mute, block, remove from followers, endorse, a note, following / followers) and editing my own (`gtk/profiledit.py`), voting in polls, translating a post, "read it whole", the edit history, reports, who liked / boosted, the quotes of my post, "read up to here" (`gtk/postinfo.py`), quotes with a reason, the "old" and "edited" marks. ✓ (0.18, evening) the thread's head, "open all CWs", the profile: paging back and from the author's server, pinned, "of the people you follow", featured tags and people; lists in full; tag groups; the "curtain" on Esc; selecting text and "Quote in reply" | smoke + a manual check on your machine |
| 5 ◐ | ✓ notifications (Gio.Notification, a click — to the thread or lane; notify-send without the bus); the ≡ menu as in Qt: silence (filters, muted, blocked, servers), filtered notifications, scheduled, who to follow, account and server (switching, all in one window, add, the main one, log in again, log out, about the server and what it can do), config/themes/data, try a theme, all of debugging, help as a panel over the lanes (contents, ← →, search, anchors), "What's this?", about; the picture viewer over the window (← →, Z — 1:1, S, O, Esc); pictures in a card in their own shape (one — ui.image_height, several — tiled by three). ✓ (0.18) the tray — StatusNotifierItem over D-Bus (`gtk/tray.py`, a test on a bus of its own), the video player over the window (`gtk/player.py`, Gtk.Video) | a manual check in GNOME and XFCE |
| parity | what Qt has and GTK doesn't (nor the web, nor the terminal) — `tools/parity.py` by the interface's words; in the self-check report (`tools/selfcheck.py`) — `parity.md` | `parity.md` after every night |
| 6 ✓ | the split layout: the roster as a window of its own (groups that fold, rows with a face and the last post, search, double click, "all read", the ⚙ view, ≡ and accounts at the bottom), the messages window — a tab per lane, thread, profile, private conversation; above the lane — the author of the post under the cursor (Follow of one width, ✉, 👤); tabs as chips in several rows (shape.tab_rows); the input line at the bottom (answers the thread in front, writes privately in a conversation, Point commands on Enter); in the "Agent" themes (`faces = "agent"`) — the other person's face as a column right of the posts. ✓ (0.18) a contact card on hover (`gtk/contact.py`) | `GtkSplitTest`, `GtkAgentTest`; screenshots |
| 7 ✓ | (0.18) deb: GTK dependencies in "Recommends" (`python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`), the GTK window as an action of the menu entry (`[Desktop Action gtk]`, "FedTail (GTK)" on a right click: one application, one id and icon), GTK in the docs — "has" | `tests/test_desktop.py`; CI |

## Decisions (21 Oct 2026)

1. libadwaita — when it's there, we use it; when not, we work without it (`ui.adwaita = "auto"`, `on`/`off`
   force it).
2. The "system" theme on GTK is "like Adwaita".
3. No GTK on Windows: Qt is there.
4. The order of stages 2–6 — as in the table, for now.
5. The application id is `online.dmesg.fedtail` (after the site fedtail.dmesg.online), `version.APP_ID`;
   the `.desktop` is renamed to it for both toolkits, the entry and the icon are checked and fixed
   at every start of the window, the old `fedtail.desktop` goes (`ui.desktop_entry`).

## What's checked and what isn't (21 Oct 2026)

The sandbox this was written in had GTK 4.14 (as in Ubuntu 24.04) without libadwaita and without
PySide6. Checked: all the tests (the Qt ones skipped), the GTK smoke test under Xvfb, screenshots of the themes
system / point / terminal, light and dark. **Not** checked: with libadwaita (`ui.adwaita =
"auto"` will find it on your machine — look there first), GTK 4.18 from Debian 13, Wayland,
comparing colours with Qt (`tests/test_palette.py::SameAsQtTest` — will run in CI).
The Qt frontend isn't touched by a single line in this batch; in the core — one thing: `View.on` turns event
payloads into the model through the new `View.event_payload` (the same behaviour, the GTK bridge uses it).
