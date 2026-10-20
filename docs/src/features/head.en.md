# What fedtail does, what it doesn't yet, and what's next

[По-русски](/docs/ru/features.md)

As of version **@VERSION@**. This is the full list of fedtail's features: what each one does,
what turns it on and off, since which version it's there, which API or protocol it stands on
and how other clients do the same. The plans are here too, and what was turned down, with the
reasons.

The full settings reference is [config.md](/docs/en/config.md), in tables by chapter. The same
as one "fedtail and other clients" matrix — [comparison.md](/docs/en/comparison.md). How the
code is built — [ARCHITECTURE.md](/docs/ARCHITECTURE.md); the spec and the queue —
[DESIGN.md](/docs/DESIGN.md) (in Russian).

> **This file is built** from `docs/src/features/*.toml` by `python3 tools/docs_build.py` —
> edit there, not here. A test checks this file keeps up.

## How to read it

Each chapter is a table: the feature, its status, since which version, the config key, the API
or protocol, how others do it. Under the table, in "In detail", is what each one does, in words.

- **Statuses:** *has* · *partly* · *no* · *planned*; at the end — *won't do* and *not decided*.
- **Since** — the fedtail version it first came in. For the very first features it's 0.1.0–0.3.0
  roughly: not everything was written down then.
- **Config** — the key as `section.key`. "—" means there's no key of its own: the feature is
  simply in a menu or a window and does nothing until you call it. For *planned* features the
  key's name is tentative and may change once it's made.
- **Others** — the same things in other clients: Mastodon web, Tusky, Ivory, Phanpy, Elk,
  Tokodon, Ice Cubes, Fedilab, Sengi, Megalodon, tut, Tuba, Whalebird. From their READMEs and
  release notes (as of autumn 2026) and general knowledge about them, without trying each one
  live. **Only in fedtail** means none of those listed has it so.
- What a particular server supports (GoToSocial above all), check on yours. fedtail itself
  hides what the server can't do: it explains an empty lane and draws no needless buttons.

The main principles everything else grows from:

<!-- include: parts/principles -->
<!-- /include -->

This is the list of what there is **now**, not a history: what changed in each version is in the
[CHANGELOG](/CHANGELOG.md).

**Contents:** @CONTENTS@
