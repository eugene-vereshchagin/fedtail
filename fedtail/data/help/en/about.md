# About

The principles fedtail grows from, who wrote it and under which licence.

## Principles

<!-- include: parts/principles -->
1. **Nothing jumps.** Open a lane and you stand at the first unread. New posts come and your
   place doesn't move, only the counter grows. You read in order, like RSS.
2. **Every reply knows what it answers.** Over a reply, a strip with the start of the original
   post; a click opens the whole thread as a tree.
3. **Lanes are apart.** People apart, bots apart, replies to me apart from other mentions.
4. **Private by default.** A new post goes to followers only. A reply is never more public than
   the original.
5. **Every behaviour is a config key.** There's no settings window and there won't be. The
   defaults are as the author likes them; "like everyone else" is a flag away. New features
   come switchable.
6. **Other servers get no token of yours.** Whatever fedtail takes straight from the author's
   server over ActivityPub goes anonymously: they see only your IP.
7. **The core knows nothing of a GUI.** Interfaces are plugins: a Qt window, a terminal, a
   browser; GTK next.
8. **One profile, one account.** A second account is a second profile (`--profile`); if you
   like, all accounts come together in one window (`ui.merge`).
9. **Grown-ups sort things out themselves.** Arts mode (after @arts, the founder of Point.im):
   everything as the author posted it, no nannying. Anyone can be told where to go, an admin
   too — and the admin can say the same back.
<!-- /include -->

## Only in fedtail

What none of the thirteen clients we compared with has ([the whole matrix](ref/comparison.md)):

<!-- include: parts/only-in-fedtail -->
- **Lanes:** Bots in a lane of their own · Who is in a list leaves the general lanes · Into a list — the author or the booster; only people you follow · Into a list right after a follow · An empty live lane says why it's empty · Filtering a lane by media and boosts · Repeated boosts don't bring an old post up again · Find in a lane · Sending to a slow server without doubles · Find in every lane at once
- **Threads:** A whole thread: replies from the author's server · Thread subscriptions, as on Point
- **Read marks and place:** Oldest on top, nothing jumps · Catching up with no holes · When a post counts as read · Cards are built around the reading place · Esc draws a curtain instead of closing the window
- **The post card:** Arts mode · Honest counters
- **Pictures and video:** Video without a hardware decoder (the default) · Pictures and video ahead of time, a disk cache
- **Profiles:** Posts older than my server knows · “Following since …”
- **Writing:** Visibility: private by default, a reply never wider than the post · CamelCase hint for hashtags · Call someone into a thread · Reply with quotes, piece by piece · A command line as on Point
- **Notifications and activity:** Desktop notifications with privacy levels · Approve a reply, like, boost (GoToSocial) · Direct messages read here are read on the server too
<!-- /include -->

## Who wrote it

The code, from the first line to the icon, is written by Claude (Anthropic), an AI. The idea,
testing every build on his own node and every remark are a human's. The version, the build and
the links — ≡ → "About".

## Licence

GPL-3.0-or-later. The opossum on the icon isn't under the GPL: it is a sticker from an official
Telegram sticker pack.
