# fedtail: protocols and a normalized model

Status: **agreed on 20 Oct 2026**. Stages 0–4 are done (0.17.0); the rest come in turn;
as each is ready, its description moves to architecture.md.

## Why

Right now fedtail knows exactly one protocol — the Mastodon API — and knows it everywhere:

| where | how it's nailed down |
|---|---|
| `core/api.py` | the Mastodon REST client — that's fine, the transport is isolated |
| `core/store.py` | the database holds the server's raw JSON (`statuses.data`) |
| the core (`threads`, `stream`, `counters`, `app`, `health`) | direct `/api/v1…` paths, the fields `reblog`, `in_reply_to_id` |
| frontends (13 files, ~77 places) | read Mastodon's fields directly: `account`, `spoiler_text`, `reblog`… |
| order | `id_after()` and `sort_key()` rely on ids being snowflakes or ULIDs |

The goal: Mastodon-compatible servers become **the first protocol**, not the shape of the
program. A second protocol (Misskey/Sharkey, Lemmy, Bluesky) is added as a new module,
without touching the frontends. On the way, the roster for the QIP layout is built on the
normalized model.

What we **don't** do now: we don't write a second protocol. We only take Mastodon out of
everything that isn't the adapter.

**The yardstick is ActivityPub's vocabulary**, not the shape of Mastodon's JSON: `Note` — a
post, `Announce` — a boost, `Like`, `Follow`, `Question` — a poll, `Article` — a long post,
`Group` — a community (Lemmy). Any server of this family has a client API an adapter can lay
onto the model. Matrix, rooms and E2EE are not designed for.

## Three layers

```
frontends (qt, gtk, tui, web, cli, later flet)
      │   see only fedtail.model: Post, Account, Thread, Activity…
      ▼
core (Core: lanes, read marks, thread subscriptions, drafts, short ids, roster)
      │   calls only the Protocol interface
      ▼
protocols: protocols/mastodon (api.py + adapter)   [later: misskey, lemmy, bluesky]
```

The rule, like today's "the core doesn't import Qt": **outside `protocols/` there isn't a
single protocol field**. A test checks it (a grep for `"reblog"`, `"spoiler_text"`, `/api/v1`
and the like outside `protocols/`). Frontends don't see raw data at all: the exchange goes
only over the model's bus, and the debugging "show the JSON" gets the data through the core.

## The normalized model (`fedtail/model/`)

Dataclasses, immutable; a change of counters is a new object through `replace()`.

| type | main fields | Mastodon API | ActivityPub |
|---|---|---|---|
| `Ref` | `proto`, `profile`, `native_id` | the status id | the object's `id` (a URI) |
| `Account` | `ref`, `handle`, `name`, `avatar`, `bot`, `locked`, `fields`, `url` | account | `Person` / `Service` (a bot) / `Group` |
| `Post` | `ref`, `author`, `created`, `text` (an HTML subset), `plain`, `warning` (CW), `visibility`, `reply_to`, `thread_root`, `media`, `poll`, `quote`, `counts`, `my` (fav/boost/bookmark), `lang`, `url`, `edited` | status | `Note` / `Article` / `Page` |
| `Share` | `by`, `post`, `created`, `sort` | boost (`reblog`) | `Announce` |
| `Media` | `kind`, `url`, `preview`, `alt`, `size` | attachment | `Image` / `Video` / `Document` |
| `Poll` | `options`, `multiple`, `expires`, `voted` | poll | `Question` |
| `Activity` | `kind` (fav/share/follow/mention/…), `who`, `post`, `when` | notification | `Like` / `Announce` / `Follow` / `Create` with a mention |
| `Conversation` | `ref`, `title`, `kind` (lane/thread/list/tag/community), `unread` | — | `OrderedCollection` / `Group` |
| `Capabilities` | a set of flags, see below | from the server's version and 404s | by protocol |

Text: the common language is **a sanitized HTML subset** (what `richtext.py` already
understands). Mastodon and ActivityPub give HTML; Misskey's MFM and Bluesky's facets are
turned into HTML by the adapter. Frontends parse one format.

### Order and ids

`native_id` is opaque to the core. **The protocol** gives the order: a `Post` has `sort`
(a string, compared as text). For Mastodon it's today's `sort_key(created_at, id)`. `id_after()` moves into the Mastodon adapter.

Point-style short ids (`#a3f`) stay in the core and are given to a `Ref` — they don't care
which protocol it is.

## The protocol's capabilities (`Capabilities`)

The seed is already there: the `unsupported` event, when the server answers 404. We make an
explicit set out of it, which the protocol declares on connecting and refines as it goes.

| flag | Mastodon/GTS | Misskey | Lemmy | Bluesky |
|---|---|---|---|---|
| `share` (boost) | yes | yes | no | yes |
| `quote` | depends on the server | yes | no | yes |
| `warning` (CW) | yes | yes | an NSFW mark | labels |
| `visibility` | 4 levels | 4+ | public only | public only |
| `edit` | yes | yes | yes | no |
| `poll` | yes | yes | no | no |
| `lists`, `filters`, `followed_tags` | yes | partly | communities | feeds |
| `threads_tree` | yes | yes | yes | yes |
| `markdown_input` | GTS/Akkoma/Pleroma | MFM | yes | no |

A frontend hides buttons and menu items by the flags — just as it does now by `unsupported`.
That fits the principle "every feature can be switched off".

## The protocol interface (`protocols/base.py`)

A mandatory part and optional extensions (can't do it — doesn't declare it).

| group | methods | mandatory |
|---|---|---|
| login | `login_start`, `login_finish`, `logout`, `me` | yes |
| sources | `sources()` → which lanes there are; `page(source, before/after)` | yes |
| threads | `thread(ref)` → ancestors + descendants | yes |
| post | `get`, `send(draft)`, `delete` | yes |
| reactions | `favourite`, `share`, `bookmark`, `vote` | by flags |
| people | `account`, `relationship`, `follow`, `mute`, `block`, `followers/following` | yes (except blocks) |
| notifications | `activity(page)`, `mark_seen` | yes |
| stream | `stream()` → a generator of the protocol's events | no (then polling) |
| search | `search(q, kind)` | no |
| extensions | `lists`, `filters`, `tags`, `announcements`, `translate`, `scheduled`, `report`, `markers` | no |

Besides the client, a `Protocol` carries what the core needs around it: `address` (what a
person typed → the server's URL), `tune` (the client's settings), `probe`, `counters`, `urls`
(other servers' public pages, fetched without a token through `core/remote.py`). The core
reaches all of it through `core/proto.py` alone.

The protocol is **synchronous**, as `api.py` is now: the core runs it in worker threads itself.
That keeps today's threading model without an async rewrite.

## The database (`state.db`): speed and growth

**Decided:** we store the protocol's raw data + a `proto` column, and normalize on reading.

Speed: the JSON is parsed on every read already; building a dataclass on top is
microseconds per post, with hundreds of posts in a window. Plus a cache of normalized objects
by `status_version`, like the lanes' cache. It won't get slower.

**Growth is a real problem already, rewrite or not.** `prune()` cleans only `items` (3000 a
lane) and `first_seen`, while the `statuses` table is never cleaned: every post seen in a
lane, a thread or a profile stays forever. `read`, `activity`, `sub_members` grow the same
way. A year of an active lane is hundreds of megabytes — gigabytes.

Fixed by garbage collection (stage 0, before the rewrite):

| what | rule |
|---|---|
| `statuses` | delete posts nothing refers to: not `items`, not `sub_members`, not `activity`, not a reply draft, not an open thread; a deleted post is fetched from the server again when needed |
| `read` | marks for posts no longer in the database and older than N days |
| `activity` | keep the last M notifications, like the lanes |
| `sub_members` | of left and gone-quiet threads |
| `aliases` | left alone: short ids are stable for ever, the rows are tiny |
| the file | `auto_vacuum = INCREMENTAL` and `incremental_vacuum` after cleaning, so the file really shrinks |

How much to keep — config flags, sensible by default, like everything else.

## Several accounts and mixed protocols

Already there: one profile — one account, `accounts.merge` gathers several `Core`s into one window
(`core/merged.py`). That's exactly the way for different protocols: **one `Core` = one account =
one protocol**, the window mixes them. A `Ref` carries `profile`, so objects of different
accounts don't get mixed up. Nothing new to invent.

## The roster for the QIP layout (on top of the model)

`View.roster()` → `[RosterGroup]` of `RosterItem`s: lanes, lists, followed threads, private
conversations, mutuals ("People", `Core.refresh_mutuals` once a day); later Lemmy
communities. Layouts (`window.layout = single | columns | split`) are the frontend's business;
the roster is the model's data, the same for all.

## The plan of work (in batches, a push at the end of each)

| stage | what | how we check |
|---|---|---|
| 0 ✓ | garbage collection in the database + incremental vacuum | a test: the database doesn't grow over a run of thousands of posts |
| 1 ✓ | `fedtail/model/` + the Mastodon adapter → model; nobody uses it yet | adapter tests on `tests/fakes.py` and samples from GTS/Mastodon/Akkoma; `tools/model_check.py` — the adapter run over your own database |
| 2 ✓ | the core gives frontends the model (`core/view.py`: View over Core); frontends one by one: cli ✓ → tui ✓ → web ✓ (rewritten) → qt ✓ | `tests/test_layering.py`: no protocol or database fields anywhere in `frontends/` |
| 3 ✓ | `api.py`, the stream, honest counters and the capability probe moved to `protocols/mastodon/`; the core takes the client, its errors, the stream and `Capabilities` from a `Protocol` (`protocols/base.py`), and the client methods it calls are listed there too (`CLIENT`). Since 29.10 the core has one door, `core/proto.py`: besides those, `Protocol` gives the address parser, the client's settings, the probe, the counters and the addresses of other servers' public pages — no module of the core imports `protocols.mastodon` any more | `tests/test_protocols.py`: no `/api/v…` paths in the code outside `protocols/`, the core calls only `CLIENT`, the Mastodon client has all of `CLIENT`, nothing outside `protocols/` but `core/proto.py` imports a protocol's modules |
| 4 ✓ | `Capabilities` (`protocols/base.py`) — one place: what the server said about itself, the probe's answers, "no such thing" refusals and what's known of the software (`KNOWN`); `Core.supports` asks it, the answers survive a reconnect, the last probe counts from the start; the `capabilities_changed` event — frontends hide buttons at once | `tests/test_protocols.py`, `test_social.py`, smoke: "Clear" goes as soon as the server refused |
| 5 ✓ | the roster (`View.roster()` → `RosterGroup` / `RosterItem`) and `window.layout = "split"` on Qt: a roster window, a messages window with its own tabs, an input line, faces — [layouts.md](layouts.md) | `tests/test_roster.py`, smoke + screenshots by `tools/screenshots.py` |
| 6 ✓ | themes in the spirit of QIP, Psi+ and Agent; a theme sets the layout's look too (`shape.faces`, `roster_rows`, `tab_rows`, `icons`) | `tests/test_themes.py`, `test_icons.py`, screenshots |

The user shouldn't notice stages 0–4 at all: the behaviour is the same, the CHANGELOG says
"an internal rewrite". Each stage ships separately as a dev build, which you run with
detailed logs.

## Decisions

| question | decision |
|---|---|
| storage | raw JSON + `proto`, normalized on reading; growth cured by garbage collection |
| raw data in frontends | no, only the model's bus |
| the layer's name | `protocols/` |
| the yardstick | ActivityPub's vocabulary; Matrix not designed for |
