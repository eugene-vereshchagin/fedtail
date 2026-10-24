# fedtail: messenger-style layouts (QIP, Psi+, Mail.ru Agent)

Status: **done in 0.17.0** (stages 5 and 6 of protocols.md), further — as tests go. The references are screenshots of QIP 2005
and Infium, QIP 2012, Psi / Psi+, Mail.ru Agent; they aren't in the repo (other people's pictures), the description is
below.

Decided: **settings stay a file**. There will be no settings window; the window "in the spirit of settings"
(sections on the left with icons, a page on the right) is **"Info"**: help, about the server,
what the server can do, the state of the federation.

## What all three have in common

| | QIP 2005 / Infium | QIP 2012 | Psi+ | Mail.ru Agent |
|---|---|---|---|---|
| roster | a narrow window, a row of small icons on top, groups "▾ Friends — 7/35", a status flower by the nick, the nick in red — has written | flat, a big header: avatar, name, "what are you thinking about" | an account header with a lock and "(9/44)", groups, a small signature line, the avatar on the right | a header: avatar, name, "no new mail"; big avatars, name, status, signature in italics; icons in a column on the right |
| roster bottom | buttons, "🌼 Online ▾" | calls and such | menu, "★ Online ▾" | "Menu", "Online ▾", "Add contact" |
| messages window | tabs with ×, a header "Name / Email / number", the avatar on the right | on the left "Find a conversation" and conversations by day: Today / Yesterday / This week | tabs, "Topic:", the conference's members on the right | big buttons, "Archive / Profile", the other person's avatar on the right, my own "Change look" |
| a message | **Nick (15:25:43 23/06/2007)** in bold, red / blue, the text below | **Name 18:09 20.09** in colour, media in the feed | [time] &lt;nick&gt; text on one line | **Nick (18:50) :**, the text below |
| input | a row of small icons, a counter "0", "✕ Close", "Send ▾" | "Characters: 0", "Send ▾" | a toolbar, a field, a button | "Text / SMS", a toolbar, at the bottom "last message received…", "Send" |

## How it maps onto the fediverse

* **The account** — the roster's header (avatar, name, @address); with `ui.merge` — several, like
  servers with a lock in Psi. "No new mail" — "N new notifications" (Activity).
* **Roster groups** — what's in the sidebar now: Timelines (Home, Local,
  Federated, Bots…), Lists, Threads (followed, with fresh posts), Conversations (private, by
  person), Tags. A group's counter "(unread/total)".
* **A "contact"** — a lane, a thread or a conversation: an icon of its kind, the title, a signature line
  (the last post as a snippet, like a status signature), the avatar of the last post's author,
  unread — by the nick's colour (like "has written" in QIP) and a number.
* **The messages window** — a tab for every open "contact"; a thread or a lane is shown
  as a chat: "**Author (time date)**", the text below, small pictures, replies as messages.
  On the right of a thread — who takes part in it (instead of the conference's members).
* **Input** — at the bottom of the window: a reply to the tab's thread (in a lane — a new post), a character counter,
  "Send ▾" (▾ — who will see it).
* **The status button at the bottom of the roster** — the default visibility (public / followers /
  …) and "invisible" — don't mark anything read.
* **Instantly** — news comes into the roster (in bold, with a number), like messages in ICQ.

## Stage 5 — the common part (layout `ui.layout = "split"`, any theme)

1. ✓ **The roster.** `View.roster()` → `[RosterGroup]`, each with `RosterItem`s (kind, key,
   title, unread, total, the last post — signature and avatar); built from the
   public core (and `MergedCore`), updated by the same events as the sidebar's
   badges. Items are lanes, and also followed threads ("Threads") and private conversations
   ("Conversations") as "contacts" of their own, the freshest (`ui.roster_threads`).
2. ✓ **The roster window** (Qt, `frontends/qt/roster.py`): a window of its own, narrow, remembers its
   place, `ui.roster_on_top`; an account header with "N new in activity", search (Enter — the
   only match or Search on the server), groups "▾ Personal (2/9)" that
   fold, an item — a counter, the last post's line, the author's face; the item's menu.
   The main window is the messages window without a sidebar (for now — the same lanes and tabs).
3. ✓ **The messages window:** tabs of its own (`MessageTabs`, in several rows), a lane or a thread
   as messages — cards with the header `card_header = "chat"`; a conversation with a person —
   `TalkWidget`; faces — the author's strip (`AuthorBar`) or Agent's column (`AgentFace`).
4. ✓ **The input line** (`frontends/qt/dock.py`, `InputDock`): a reply to the tab's thread, a private message
   in a conversation, a new post in a lane; visibility, CW, pictures, language, Point commands.
5. ✓ **"Info"** — the help panel: under its contents a "Server and federation" section
   (about the server, what it can do, the state of the federation) opens on the right, like pages;
   in any layout. The "About the server" and "Federation status" dialogs are the same widgets.
6. ✓ Screenshots by `tools/screenshots.py`, smoke tests.

## Stage 6 — themes (each with both colours and shape: `shape` and words)

✓ Made from screenshots of the originals:

* `qip-retro` — QIP on Windows XP: beige windows, white fields in grey-blue frames, XP tabs
  with an orange stripe, square corners; pictures — a set of its own with `style = "qip"`.
* `qip-modern` — QIP Infium: pale blue gloss, posts on a diagonal from white to
  blue, groups "▾ Friends - 3/25".
* `mra`, `mra-blue`, `mra-green`, `mra-violet` — Agent's skins: glossy frames and buttons,
  faces in a column on the right (`faces = "agent"`), roster items with a big face.
* `psi` — Psi+ on KDE: flat, Breeze, Psi+'s own pictures (the theme's own set).

Status and kind icons are drawn by us; the ICQ, QIP, Mail.ru logos aren't copied —
the themes are "in the spirit", not fakes. Theme names are descriptive.

## Pictures on buttons (✓ `shape.icons`, `ui.icons`)

What the references had (QIP 2007/2012, Psi+, Mail.ru Agent) and what it is here:

* the status icon in the roster and on a tab (a flower / a star / "@") → a post's visibility:
  public / not in lanes / followers / private; on a tab — the lane's icon and ×;
* groups "▾ Name (n/m)" → roster sections, there; "an envelope with a number" → Activity;
* at the bottom of the roster "add", search, a spanner, the status → following, search, menu, accounts;
* above the conversation: profile, history, find, clear, bookmark → profile, thread, find in the
  lane, all read, bookmark;
* by the input line: a smiley, a paper clip, the font, a quote, templates, a counter, a calendar, ABC,
  "Send ▾" → emoji, an attachment, Markdown, a quote, drafts, a counter, schedule,
  language, send; there was no poll or warning there — we draw our own;
* by every message an arrow "mine / to me" (Psi, QIP) → a mark of a reply or a boost;
* faces: QIP — the other person top left, me at the bottom by the buttons; Agent — both on the right (~90 px),
  the other person by the conversation, me by the input line (done just so: `ui.faces`); Psi — only
  in the roster.

The drawings are our own SVGs in the spirit of 2007, or free ones (MIT, CC BY — with the author named in
a LICENSE.txt next to them), recoloured with the theme's colours. The theme decides (`frontends/iconpack.py`):
`[shape] icons` — `"desktop"` (system, debug: the desktop's icons by their
freedesktop names), `"own"` (a set of its own: `themes/<theme>/icons/`, a file a picture),
`"words"` (terminal, bnw); `ui.icons` can override it, `"additional"` — the messenger
pictures outside split too. Pictures come in two sorts: standard (menu, width, columns, lanes,
the buttons under a post, visibility, close, refresh…) — always, when the theme has pictures;
extended (the input line, the roster, the author's strip, the flower, the silhouette) — in split or with
`"additional"`. What isn't in the theme's folder comes from the folders of the themes it inherits from, then from
`[pictures] from` (mra-blue takes from mra, qip-modern from qip-retro), then from the emergency
`data/icons/fallback/` — built-in themes don't need it (a test), for a theme of your own the log says
which pictures were missing. SVG colouring — `[pictures] style` (gloss, agent, flat, qip,
none) and `[pictures.colors]`. Qt and GTK only draw what iconpack gives (GTK — SVG
through the gdk-pixbuf loader, librsvg).
The ICQ flower — only as an icon inside windows in the retro themes, marked as its
owner's sign.

## The theme sets the look of split (done)

`shape.faces` (qip | agent | none), `shape.roster_rows` (lines | faces), `shape.roster_face`,
`shape.tab_rows` (wrap | one), `colors.view_end` (a diagonal behind the posts, QIP Infium),
`colors.tab_mark` (a stripe over the front tab, XP), `words.roster_group`. The layout of faces and
tabs is taken from the theme at start; "try a theme" changes the colours, not the layout.
