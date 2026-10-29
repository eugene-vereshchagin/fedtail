# fedtail's principles

What fedtail is for, and what it holds to in three chapters: how the program behaves for
the one who reads, how it is built, how its code is written. Every change is checked against
them; a change that breaks one either changes the principle here first, in its own commit,
or doesn't go in. The details live where this page links to.

## The goal

1. **As much as there is, in one program.** fedtail covers the most features and the most
   ways of behaving a fediverse client can have. We take every good idea of every client we
   can reach, without shame — and add what no one else has. Even gathering in one place what
   already exists is something none of the donors has.
2. **Everyone sets it up their own way.** Each feature can be switched on and off. The
   author's way is a preset, not something nailed into the code: the interface (which one,
   which layout, which theme), what goes into each lane, which lanes there are and how many,
   filtering the content or none at all — all of it can be changed.
3. **The author's taste is the default, not the limit.** The defaults are as the author
   likes them; "like everyone else" and anything between is a setting away.

## 1. How the program behaves

<!-- include: parts/principles lang=en -->
1. **Nothing jumps.** Open a lane and you stand at the first unread. New posts come and your
   place doesn't move, only the counter grows. You read in order, like RSS.
2. **Every reply knows what it answers.** Over a reply, a strip with the start of the original
   post; under someone's comment, what you said back to it: come back to a thread a week later
   and you see at once where you were. A click opens the whole thread as a tree.
3. **Lanes are apart.** People apart, bots apart, replies to me apart from other mentions.
4. **Private by default.** A new post goes to followers only. A reply is never more public than
   the original.
5. **Every behaviour is a config key.** The settings window is a face of the same
   `config.toml`: it shows its keys and writes back into it. The defaults are as the author
   likes them; "like everyone else" is a flag away. New features come switchable.
6. **Other servers get no token of yours.** Whatever fedtail takes straight from the author's
   server over ActivityPub goes anonymously: they see only your IP.
7. **One core, many faces.** The Qt window, the GTK window, the terminal, the browser and the
   phone show the same things and behave the same: the core decides, the interfaces only
   draw.
8. **One profile, one account.** A second account is a second profile (`--profile`); if you
   like, all accounts come together in one window (`accounts.merge`).
9. **Grown-ups sort things out themselves.** Arts mode (after @arts, the founder of Point.im):
   everything as the author posted it, no nannying. Anyone can be told where to go, an admin
   too — and the admin can say the same back.
<!-- /include -->

## 2. How it is built

1. **The core decides, the interfaces draw.** Everything about behaviour — what is read,
   where a lane opens, which thread an answer grows, what a lane holds, what is in memory —
   is decided once, in `fedtail/core`, and comes to the interfaces as data and events. An
   interface only draws what it is given and reports what it shows (what is on screen, the
   card read last). A rule an interface would have to copy is a rule in the wrong place:
   the five interfaces never keep crutches in step by hand. What only a toolkit can do (how
   a scroll is held while a picture comes in, a widget's size) stays in the interface.
2. **The core knows nothing of a toolkit.** `fedtail/core` and `fedtail/diag.py` never import
   Qt, GTK or Textual; the interfaces talk to the core through futures and events only. What
   several interfaces share without a toolkit (what a link does, a post's actions, the
   editor, the places, the settings) is `frontends/common/` — a test in `test_layering.py`
   checks.
3. **Three layers, Mastodon the first protocol.** The interfaces see only fedtail's model
   (`Post`, `Account`, `Thread`…); the core calls only the protocol's interface; Mastodon is a
   module in `protocols/`, not the shape of the program. The yardstick of the model is
   ActivityPub's vocabulary, not Mastodon's JSON — [protocols.md](protocols.md).
4. **A lane is its rule.** Every question about a lane is asked of its rule, never of its
   name — the first lane, sounds, private messages, sections, columns; the built-in lanes
   are presets of rules — [feeds.md](feeds.md).
5. **The same everywhere.** The Qt window, the GTK window, the terminal, the web page and the
   phone offer the same things. One that lacks something says so, and why, in
   `docs/src/parity.toml`; a test holds it against the code. A fix is made for every
   interface at once, never for one platform.
6. **Only what is seen is in memory.** The core decides what is in memory; an interface gets
   what is on screen. Lightness is measured, and kept by tests with ceilings of memory and
   time — [memory.md](memory.md).
7. **Every behaviour is a flag.** A new option goes into `config.DEFAULTS` and both example
   configs, at its default, explained in each one's language; the settings window shows what
   they say.
8. **The token goes nowhere but its server.** Never logged, never sent to other servers:
   whatever comes straight from another server is asked anonymously. The bug report leaves
   out `auth.json`, `state.db` and sync's secrets; a sync server never gets the account's
   token. No server is written into the code.
9. **Awkward cases decided beforehand.** The network, the OS, the disk, the interface, security
   — each case with its answer and its decision in [robustness.md](robustness.md); a choice
   that changes the product is the author's call.

## 3. How the code is written

1. **A fix comes with its test.** The test fails without the fix and passes with it;
   `tests/fakes.py` is an in-memory Mastodon. A test checks what the program does, not how a
   test happened to see it.
2. **Measure first, then change.** A change for speed or memory is confirmed by the bench's
   numbers — [tools.md](tools.md).
3. **The code reads like the code around it.** Comments, names and idiom as in the file; the
   comments and commit messages in English; docstrings Google style, every module starting
   with what it is for; `ruff check .`, lines up to 100.
4. **The docs keep up with the code, in the same commit.** A user-visible change gets its
   CHANGELOG line; a feature or a switch — its entry in `docs/src/features/`; generated docs
   are rebuilt, never edited by hand. The user's docs and the developer's come in Russian and
   English, both changed at once — [AGENTS.md](../../../AGENTS.md).
5. **Every string in both languages.** `ru` and `en` in `fedtail/i18n.py`; a test checks.
6. **In batches, and the author releases.** Changes go in batches pushed with `[skip ci]`; a
   release is cut only on the author's word — [ci.md](ci.md).
7. **No shortcut on F1 or Shift+F1, ever:** they sit next to Esc.
