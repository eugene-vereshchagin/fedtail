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
