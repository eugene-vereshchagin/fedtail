# Writing

The compose panel and everything in it.

## The compose panel and drafts

Write (`Ctrl+N`) opens a panel right in the main window: the keyboard layout isn't reset. ⤡ —
bigger / smaller, ✕ or Esc — close. The draft is saved as you type: close the panel and nothing
is lost. `Ctrl+Enter` — send.

## Visibility

A new post is seen by followers only, by default. A reply is never more public than the post it
answers. Change it for one post — the list in the panel; for all — `post.default_visibility`.

## Markdown, CW, language

- **Markdown** — if the server understands it (GoToSocial, Akkoma). "👁 Preview" shows how it
  comes out.
- **CW** — "⚠ Content warning": the text hides behind a "show" button. In a reply the original
  post's CW is filled in by itself.
- **Language** — servers filter and translate by it. "Another language…" adds any ISO 639 code.

## Pictures

Drag a file onto the window or paste it (`Ctrl+V`). A double click on a picture — its
description (alt) and focus point. Without a description fedtail asks before sending. A picture
too big for the server is shrunk to its limit; your file stays as it is.

## Polls, quotes, chains, scheduled posts

- "📊 Poll" — instead of pictures.
- "Quote" in the ⋯ menu of a post its author lets quote.
- A line of nothing but `---` splits the text into a chain of posts: they go at once, each a
  reply to the one before.
- "⏰ Later" — the post waits on the server, even with fedtail closed. The list — ≡ → "Scheduled
  posts".

## Calling someone into a thread

⋯ → "Call into the thread…": a reply with only "@" in it and the people list open. The one you
name gets a notification and opens the thread at home. The thread's others aren't bothered.

## Edit, delete, redraft

In the ⋯ menu of your own post: "Edit", "Delete", "Pin" and "Delete and redraft" — the post is
deleted, and its text, CW, visibility and language open as a new draft.

In detail → [Writing](ref/features.md#writing) · [post settings](ref/config.md#5-posts)
