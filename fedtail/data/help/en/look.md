# The look

Themes and everything that changes the look.

## Themes

Built in: `system` (as in KDE), `terminal`, `juick`, `juick-classic`, `bnw`, `point`, `night`,
`contrast` (for weak eyes), `pink`, `nord`, `solarized`, `paper`, the messengers' `qip-retro`,
`qip-modern`, `mra`, `mra-blue`, `mra-green`, `mra-violet`, `psi`, and `debug` (for hunting
what's unfinished). ≡ → "Try a theme" — at once, no restart, the config isn't touched; for good —
`ui.theme`. Your own theme is a file in the themes folder (≡ → "Open themes folder", README.txt
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

## As in a messenger: the split layout

`fedtail --layout split` (for good — `ui.layout = "split"`): the lanes, threads, talks and
the people you follow each other with in a narrow roster window, as in QIP, Psi or the
Mail.ru Agent; a double click opens one as a tab of the messages window, with an input
line always at its bottom. Best with one of the messengers' themes — they set its look too:
where the faces go, how the roster's items look, the pictures on the buttons.
`ui.additional_icons` — those pictures in every layout, or in none.

## Width, font, buttons, emoji

- ↔ at the top left — posts across the full width or in a column of `ui.max_width`.
- `ui.font_size` — the size of the posts' font.
- `ui.actions` — the buttons under a post with an icon and a label, icons only or labels only.
- `feed.emoji = false` — not a single emoji in the feed.

In detail → [The application](ref/features.md#the-application) · [Look and window](ref/config.md#1-look-and-window)
