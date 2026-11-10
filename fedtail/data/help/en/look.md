# The look

Themes and everything that changes the look.

## Themes

Built in: `system` (as in KDE), `terminal`, `juick`, `juick-classic`, `bnw`, `point`, `night`,
`contrast` (for weak eyes), `pink`, `nord`, `solarized`, `paper`, the messengers' `qip-retro`,
`qip-modern`, `mra`, `mra-blue`, `mra-green`, `mra-violet`, `psi`, and `debug` (for hunting
what's unfinished). ≡ → "Try a theme" — at once, no restart, the config isn't touched; for good —
`appearance.theme`. Your own theme is a file in the themes folder (≡ → "Open themes folder", README.txt
is there): a theme sets not only the colours but the card's layout too.

## Themes of your own

Your themes live in `~/.config/fedtail/themes/` (shared by all profiles), one `name.toml`
each, and fedtail reads them right there — nothing is copied; one named as a built-in wins
over it. The built-in themes work from fedtail's own folder, and `themes/builtin/` gets a
copy of them at every start — a sample to start from only (fedtail doesn't read them and
rewrites them with every version: editing them is no use). A theme's fonts go next to it
(`[font] files`), fonts for any theme into `~/.config/fedtail/fonts/`, nothing to install.
Your themes are handy in git: make `~/.config/fedtail/themes/` a working copy of your own
repository and put `builtin/` in its `.gitignore` — a `git pull` there gives working themes
at once.

## A theme as a file

<!-- include: parts/theme-files -->
A theme travels as one zip file: off a phone (where the themes folder is out of a file
manager's reach), to another computer, to a friend. The archive is laid out as the themes
folder is, and this manual comes inside it.

**Take a theme out.** The windows: ≡ → "Try a theme" → "Save the theme to a file…" (the
theme on screen). The phone: ≡ → "Save the theme to a file…". The command line:
`fedtail --theme-export NAME FILE.zip`. Any theme can be taken out, a built-in one too. In
the archive:

- `NAME.toml` — the theme itself: colours, fonts, the card's shape;
- `NAME/icons/` and `NAME/sounds/` — its pictures and sounds, if it has its own;
- `fonts/` — the font files it names in `[font] files`;
- the themes of your own it rests on (`inherit`, `[pictures] from`, `[sound] from`) —
  the built-in ones are on every device and don't go in;
- `README.en.md` and `README.ru.md` — this manual.

**Change it.** Unpack the archive and edit `NAME.toml` in any text editor: the colours are
in `[colors]` (`#rrggbb`), the fonts in `[font]`, the rest in `[shape]`, `[pictures]`,
`[sound]`. Every key there is, each with a comment on what it does, is in the theme
`system` — take it out the same way to have the list at hand. A small theme of your own
can be a few lines over another one:

```toml
name = "My green"
inherit = "terminal"

[colors]
text = "#a8ff60"
```

A picture of the set is a file `NAME/icons/<picture>.svg` (or `.png`) — replace it with
yours under the same name; a sound is `NAME/sounds/<event>.wav` (`message`, `reply`,
`mention`, `direct`, `thread`, `request`, `activity`, `online`, `sent`).

**Rename it** — so it stands next to the one it came from, not instead of it. Three
things, all with the same new name (say, `mine`): the file `point.toml` → `mine.toml`, its
folder `point/` → `mine/` (if there is one), and the line `name = "…"` inside — that is the
name the menus show. The `fonts/` folder stays as it is.

**Bring it back.** Pack the files into a zip again: `mine.toml` at the archive's top (or
all of it inside one folder — that is understood too). The windows: ≡ → "Try a theme" →
"Add a theme from a file…"; the phone: ≡ → "Add a theme from a file…"; the command line:
`fedtail --theme-import FILE.zip`. The theme is in the "Try a theme" list at once; for good —
`appearance.theme = "mine"` in the settings. A theme of the same name already there is
replaced only when you say so (the command line: `--replace`); one named as a built-in theme
wins over it. fedtail takes only a theme's own kinds of files (`.toml`, `.svg`, `.png`,
sounds, fonts) — the rest is left out and said — and an archive of 64 MB at most.

On a computer the themes folder is open, too: `~/.config/fedtail/themes/` (on Windows
`%APPDATA%\fedtail\themes`) — an archive unpacked there works as it is.
<!-- /include -->

## As in a messenger: the split layout

`fedtail --layout split` (for good — `window.layout = "split"`): the lanes, threads, talks and
the people you follow each other with in a narrow roster window, as in QIP, Psi or the
Mail.ru Agent; a double click opens one as a tab of the messages window, with an input
line always at its bottom. Best with one of the messengers' themes — they set its look too:
where the faces go, how the roster's items look, the pictures on the buttons.

## Pictures on the buttons

Where the pictures on the buttons and by the lanes come from is the theme's choice
(`[shape] icons`): `system` and `debug` take the desktop's icons (Breeze and the like),
`terminal` and `bnw` do with words and the glyphs ≡ ↔ ❯, the rest bring a set of their
own — a folder next to the theme's file: `themes/<theme>/icons/`, a file a picture
(`reply.svg` or `reply.png`). Pictures are standard (the menu, the width, the columns,
the lanes, the buttons under a post, who sees it) — there whenever the theme has
pictures at all — and the messengers' (the input line, the roster, the author's bar, a
person's flower) — in the split layout. `appearance.icons` in the config may decide otherwise:
`"desktop"`, `"own"`, `"words"`, or `"additional"` — the messengers' pictures outside the
split layout too, wherever their buttons are (the post window, a profile).

A theme of yours takes the pictures of the one it inherits (`inherit`), or of the one
named in `[pictures] from`, and keeps in its folder only those it wants different. An SVG
may leave its colours blank — `{c}` the colour, `{l}` its light top, `{d}` the outline —
filled by `[pictures] style` from the theme's colour or `[pictures.colors]`. What's
nowhere comes from fedtail's emergency set, and the log says which pictures the theme
lacked. The built-in themes' sets lie in `themes/builtin/<theme>/icons/` to start from,
the list of all pictures in `themes/builtin/PICTURES.txt`.

## Width, font, buttons, emoji

- ↔ at the top left — posts across the full width or in a column of `appearance.max_width`.
- `appearance.font_size` — the size of the posts' font.
- `card.actions` — the buttons under a post with an icon and a label, icons only or labels only.
- `appearance.emoji = false` — not a single emoji in the feed.

In detail → [The application](ref/features.md#the-application) · [Appearance](ref/config.md#1-appearance)
