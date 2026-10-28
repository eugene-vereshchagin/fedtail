# Developer tools

Everything in `tools/` — what each one is for and how to start it. Each script's docstring
says more (`python3 tools/NAME.py --help` where it has switches). A test checks that every
`tools/*.py` is in this table, in both languages.

## Checking everything at once

| tool | what it does | how to run |
|---|---|---|
| `selfcheck.py` | everything below that can run on this machine, in one go: tests, walks through every interface with screenshots, window sizes, speed, parity; then the same on your own account (a read-only copy); a report and a zip to send | `python3 tools/selfcheck.py --night` (1–3 h), `--quick` (5 min) |
| `devenv.py` | Playwright and Chromium for the web walk and the gallery, in a venv of their own (Debian's Python stays as it is) | `python3 tools/devenv.py`, once |
| `real.py` | `--real` for the tours and benches: your own account instead of the fake server — a copy of the profile, only GET goes out | `--real[=PROFILE]` on other tools |
| `windows_check.py` | docs/en/dev/windows.md done on this Windows: every command of the page that can run without a person, in a profile of its own | `py -3.13 tools/windows_check.py OUT --tests` |

## Walks through the interfaces

| tool | what it does | how to run |
|---|---|---|
| `qt_tour.py` | the Qt window on a fake server: every theme, every menu with its inventory, every dialog, the settings window, window sizes, widget leaks | `python3 tools/qt_tour.py OUT --native` |
| `gtk_screenshots.py` | the GTK window with made-up data: every theme light and dark, HiDPI, real screen sizes | `xvfb-run -a python3 tools/gtk_screenshots.py OUT system point` |
| `tui_check.py` | the terminal interface (Textual), headless: every lane, screen and key; SVG shots | `python3 tools/tui_check.py OUT` |
| `web_check.py` | the web page in Chromium (Playwright): lanes, menus, the editor, the viewer, a phone's width, JS errors | `python3 tools/web_check.py OUT` |
| `screenshots.py` | the real Qt window with made-up data, a PNG per theme (CI publishes them on the `screenshots` branch) | `QT_QPA_PLATFORM=offscreen python3 tools/screenshots.py OUT` |
| `tabs_stress.py` | dozens of threads, profiles and tags opened and closed round after round in Qt, GTK and the terminal: what stays alive is a leak | `python3 tools/tabs_stress.py OUT --ui qt` |

## Behaviour and parity

| tool | what it does | how to run |
|---|---|---|
| `behaviour.py` | one scenario (a lane, ⋯, like, boost, thread, reply, profile, delete, the command line…) through all four interfaces, held against what `frontends/common` decides | `python3 tools/behaviour.py OUT.md` |
| `parity.py` | which words of the interface (buttons, menu items, dialogs) one frontend shows and the others don't | `python3 tools/parity.py OUT.md` |
| `cross_check.py` | several self-check runs side by side: KDE as the reference, Windows, GTK — looks, menus, behaviour, failures | `python3 tools/cross_check.py REF OTHER…` |
| `theme_compare.py` | each theme in Qt and in GTK side by side, with their main colours compared | `python3 tools/theme_compare.py SELFCHECK_OUT` |

## Speed and coverage

| tool | what it does | how to run |
|---|---|---|
| `qt_bench.py` | how fast the Qt window is: start, lanes, scrolling thousands of posts, menus, the editor, themes, split | `python3 tools/qt_bench.py` |
| `membench.py` | memory and speed on one synthetic day: USS/PSS/RSS, where Python's memory is (`--trace`), the start, the lanes, the rules, scrolling (`--ui qt`) — the baseline of [memory.md](memory.md) | `python3 tools/membench.py --ui qt` |
| `gtk_bench.py` | the same for the GTK window | `python3 tools/gtk_bench.py` |
| `coverage_lite.py` | line coverage with nothing installed (sys.monitoring, Python 3.12+), every process of a night run counted (`tools/covhook/`) | `python3 tools/coverage_lite.py OUT` |

## Data, pictures and sounds

| tool | what it does | how to run |
|---|---|---|
| `showcase.py` | the made-up world every screenshot shows (people, a thread, a poll, pictures), drawn without network or toolkit | imported by the other tools |
| `gallery.py` | the site's and the docs' pictures: every interface in the made-up world, plus `gallery.toml` with captions in both languages | `python3 tools/gallery.py OUT` |
| `userthemes.py` | your own themes from `~/.config/fedtail/themes`: the tours check them, the gallery never shows them | imported by the other tools |
| `make_sounds.py` | fedtail's own sound sets, synthesized (no samples), so they're ours under GPL-3 | `python3 tools/make_sounds.py`, `--check` |
| `model_check.py` | runs the Mastodon adapter over every post a profile has stored, read-only, and says how the model came out | `python3 tools/model_check.py [PROFILE]` |
| `push_probe.py` | does your server push? Web Push from it to an ntfy topic, decrypted here | `python3 tools/push_probe.py` |
| `android_icons.py` | the Android app's launcher icons (adaptive, round, themed) from `fedtail/data/icons/fedtail.png` | `python3 tools/android_icons.py` |
| `swing_frames.py` | the swinging opossum's frames for GTK (a sheet and their times) from `fedtail/data/icons/fedtail-swing.gif` | `python3 tools/swing_frames.py` |

## Docs

| tool | what it does | how to run |
|---|---|---|
| `docs_build.py` | builds every generated document (features, comparison, config, parts, the help) and refills every include | `python3 tools/docs_build.py`, `--check` |
| `config_doc.py` | the config reference from the example configs (docs_build calls it) | `python3 tools/config_doc.py` |
| `lane_pictures.py` | draws the lanes' library of pictures (`fedtail/data/icons/lanes`, 16×16, the theme's {c} {l} {d} {o}) | `python3 tools/lane_pictures.py` |
