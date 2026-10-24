# fedtail's test plan

What checks itself, with what and where; what's left for the eyes. One run for everything:

```sh
python3 tools/selfcheck.py --night      # overnight: everything, plus your own account (read only)
python3 tools/selfcheck.py --quick      # in 5 minutes: one layout of each and a couple of themes
```

Once, before the first run: `python3 tools/devenv.py` — Playwright and Chromium for
the web and the gallery, in an environment of their own (Debian's system Python won't let pip in; the environment
sees the system's PySide6, GTK, Textual — nothing is installed twice).

In the morning — `~/fedtail_log/DATE_TIME/` (on Windows `%USERPROFILE%\fedtail_log\…`): all
the pictures and the steps' logs, `report.md` and, in the same folder, a zip to send. Interrupted (Ctrl+C, closed the terminal)
— the run is marked "interrupted", no zip is made, temporary copies are wiped;
`selfcheck.py --clean` removes such unfinished runs (and temporary folders after
crashed ones), `--clean all` — every run in the folder. Temporary folders (with a copy of
your login with `--real`) are wiped after every run by themselves. Screenshots of your own account are blurred
(`--no-blur` — as they are), requests to the server are GET only (tools/real.py).

## Levels

| Level | With what | What it catches |
|---|---|---|
| Core, model, protocol | `tests/` (unittest) | the logic: lanes, read marks, threads, filters, commands, the config |
| Windows on a fake server | `tests/test_qt_smoke.py`, `test_gtk_smoke.py`, `test_tui.py`, `test_web.py` | that a window builds, buttons and keys do their thing |
| The settings window | `tests/test_settings.py` (+ the Qt/GTK/TUI smoke tests) | the config edited by exactly one line, comments intact, .bak, refusal of a bad value; every option of the reference in the window in both languages; saving and "Default" through the `settings` place |
| Coverage | `tools/coverage_lite.py` + `tools/covhook/` (in `--night`) | which lines of fedtail/ never ran during the whole night — by part and by file (`coverage/report.md`, `lines.json`). Every process of every step counts: tests, tours, the Qt and GTK windows they open, the web server. Nothing to install (sys.monitoring, Python 3.12+) |
| Interface parity | `tests/test_parity.py` (`tools/parity.py`, the registry `docs/src/parity.toml`) | a word of the interface (a menu item, a button, a tooltip) one interface shows and another doesn't, unexplained in the registry; "has" in the registry but not in the code; "no" but done already. The registry gives the "Four interfaces" table of features.md |
| Qt tour | `tools/qt_tour.py` | every theme (and split for the messenger ones), every menu (≡, submenus, accounts, a post's ⋯, right clicks all over the window, the roster, the tray), every dialog from ≡, tabs, the settings window — every chapter (`settings-NN.png`, nothing is pressed: on your own account it's your config); window sizes; widget leaks |
| Terminal tour | `tools/tui_check.py` | all lanes, a thread, a profile, the picture screen, the command line, every key; whether pictures are drawn |
| Web tour | `tools/web_check.py` (Playwright) | all lanes, the ≡ and ⋯ menus, the editor, the picture viewer, a phone's width, JS console errors |
| GTK look | `tools/gtk_screenshots.py` | every theme light and dark, split, dialogs |
| Speed | `tools/qt_bench.py`, `tools/gtk_bench.py` | start, lanes, scrolling 2–4 thousand posts (a screen a frame, 6 and 15 screens a second, a fling — 4 screens a frame, the thumb to the end at once and dragged fast): how often the edge of what's built was hit and how long it waited, empty frames; menus, the editor, switching themes, dragging the window's and the sidebar's edge |
| Behaviour | `tools/behaviour.py` (`tests/scenario.py`, `tests/drivers.py`, `tests/test_behaviour.py`) | one scenario in all four interfaces, each by its own path (the web — by the page's requests, the terminal — by Textual keys, the windows — by their own links, cards and editor): a lane, a post's ⋯, like, boost, bookmark, a thread, following and silencing a thread, a reply, a profile, following a person, deleting, the command line, "read up to here", "all read"; the result — on the fake server and in the core, against what `frontends/common` decides; and whether every window has all the places a link may ask for |
| Tabs | `tools/tabs_stress.py` (steps `tabs-qt`, `tabs-gtk`, `tabs-tui`, at night also `-split` and `real-tabs-*`) | dozens of threads, profiles and tags opened and closed, round after round (at night 20 × 40): the time to open and close, how many widgets, objects and how much memory stays — what grows from round to round is a leak; any exception is an error |
| Themes | `tools/theme_compare.py` (the `themes` step, after the Qt tour and the GTK shots) | each theme in Qt and in GTK side by side (`themes/pairs/<theme>.png`) and a comparison of their main colours: what share of the window is in colours the other doesn't have; the web and the terminal — when they get themes |
| Comparing systems | `tools/cross_check.py REFERENCE OTHER…` (folders or zips of runs) | the run on KDE is the reference; Windows and the GTK window next to it: the main window for each theme as a triple of pictures with colours (`pictures/`), the words of all menus (`menus.txt`) as a line diff, the steps and failed tests of each system, the behaviour of all the interfaces of each system |
| Places | `tests/test_places.py` | silence, lists, search, requests, activity, reports, editing the profile, help — `common/places.py`, shared by the web and the terminal |
| Parity | `tools/parity.py` | which words of the interface (buttons, menu items, dialogs) are in one interface and not in another; a post's ⋯ in Qt and the web side by side |
| Your own account | `--real` for all tours and benches | the real network and database: timeouts, slow servers, thousands of posts, pictures |

## Themes

The Qt tour (`qt_tour.py`) and the GTK shots (`gtk_screenshots.py`) go through all the built-in
themes and your own ones from `~/.config/fedtail/themes` (what didn't come with fedtail:
yours, pirated) — yours in split too. Yours are only checked: they never get into the gallery or onto the site
(`tools/userthemes.py`). Benches — on four themes (system, point
or nord, qip-retro, mra): speed hardly depends on the theme.

## The gallery (site and docs)

`tools/gallery.py OUT` (and the `gallery` step in `--night`): ~20 pictures of all the interfaces in
one made-up world (`tools/showcase.py`) — Qt in themes and layouts, a thread, the editor,
a picture, a menu, two messenger windows side by side; GTK light, dark, nord; the terminal; the web
on a computer, dark and on a phone. Next to them `gallery.toml`: a title and a line about
each picture in Russian and English, in the gallery's order — the site and the docs read it.
Built-in themes only.

## What counts as an error (errors.txt, report.md)

- an exception anywhere, an error in the status bar, a WARNING in the log;
- an empty menu; a dialog that didn't open;
- at sizes from 1024 px: a button or a line of text cut off, a widget sticking out of the window;
  the window won't shrink to 800 px (something in it is too wide);
- dragging the window's edge takes longer than 250 ms a step;
- more than 50 widgets stay alive after a window is closed (a leak: Qt repaints
  every living widget on a theme switch — so a leak also slows things down);
- a test failed or hung (a hung one — with a stack showing where exactly: faulthandler).

## Window sizes

1920×1080, 1366×768, 1024×768, 800×600, 640×480 and the narrow 480×860 — in the themes system
(a proportional font), terminal and bnw (monospace, the widest buttons),
qip-retro and mra (messengers). For each — a `size-…` screenshot and an analysis in `sizes.txt`;
then the window's edge is dragged 1600 ↔ 640 a frame at a time, and the sidebar's edge 180 ↔ 480.

## What's left for the eyes

Screenshots are for what code can't see: colours, contrast, alignment, "is it pretty".
Look by report.md: Qt's themes (`qt-tour/*-single.png`), the same themes in GTK
(`gtk-shots/`), menus (`qt-tour/menu-*.png`), sizes (`size-*`), the web on a phone.
Found something ugly — name the file, I'll sort out the rest.

## What isn't there yet (next steps)

- a GTK tour like Qt's: menus, dialogs, sizes (now — shots and a bench);
- Qt and GTK shots in one world are there already (`tools/showcase.py`); next — comparing
  them automatically: a theme in Qt against the same theme in GTK;
- a wider behaviour scenario: editing, quoting, polls, lists and silence through every interface;
- Windows and macOS: the same selfcheck (GTK is skipped there).
