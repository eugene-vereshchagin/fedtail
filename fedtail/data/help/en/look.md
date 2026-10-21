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

## Picture packs

The pictures on the buttons come from the pack a theme names: `[shape] icon_set`.
Built in: `gloss` (the base: a gradient and a shine in the theme's colour), `qip` (each
its own bright colour, a thick dark outline), `agent` (the Agent: brighter, an "@" for a
person), `flat` (plain, a star), `psi` (Psi+'s own pictures). A pack of your own is a
folder, `~/.config/fedtail/icons/<name>/`: `pack.toml` in it (the name, which pack it
inherits, how it colours, its pictures' own colours) and a file a picture — `reply.svg`
or `reply.png`; what the pack lacks comes from the one it inherits. An SVG may leave its
colours blank — `{c}` the colour, `{l}` its light top, `{d}` the outline — and the pack
fills them from the theme. Samples of the built-in packs and the list of all pictures:
`~/.config/fedtail/icons/builtin/` and `README.txt` beside it. A theme can also bring a
few pictures of its own: `themes/<theme>/icons/reply.svg`, over its pack.

## Width, font, buttons, emoji

- ↔ at the top left — posts across the full width or in a column of `ui.max_width`.
- `ui.font_size` — the size of the posts' font.
- `ui.actions` — the buttons under a post with an icon and a label, icons only or labels only.
- `feed.emoji = false` — not a single emoji in the feed.

In detail → [The application](ref/features.md#the-application) · [Look and window](ref/config.md#1-look-and-window)
