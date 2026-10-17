# Notes for coding agents (and humans in a hurry)

Read `docs/ARCHITECTURE.md` first: it maps every module, the threads, the store
schema, the lanes, the poll cycle, the events and the Qt frontend, with recipes
for common changes. `docs/DESIGN.md` (Russian) is the product spec and the queue
of planned work. `docs/DEBUGGING.md` explains the logs a user can send; `docs/TESTING.md` is the page
for alpha testers (install, what to try, how to report); `docs/FEATURES.md` is the
feature table (have / partly / no / planned, other clients, the config switch for each).

## Run, test, lint

```sh
python3 -m fedtail                       # run from the checkout (needs PySide6 + requests)
python3 -m unittest discover -s tests -t .   # all tests; Qt ones skip without PySide6
QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_qt_smoke
ruff check .                             # line length 100
python3 tools/screenshots.py out/        # PNGs of every theme with made-up data
```

Debian 13 packages: `python3-pyside6.qtwidgets python3-pyside6.qtdbus python3-requests`
(no QtTest there); at run time also `qt6-image-formats-plugins` (webp/avif pictures) and
`libnotify-bin` (notify-send). The deb package's dependency list is in docs/DESIGN.md.

## Rules

* The core (`fedtail/core`, `fedtail/diag.py`) never imports Qt. Frontends talk to
  `Core` through futures and events only.
* Qt objects only in the GUI thread; results come back via `Bridge.call`.
* Every behaviour is a flag: add new options to `config.DEFAULTS` **and**
  `fedtail/data/config.example.toml` (set to the default, Russian explanation above) — a test
  checks they match.
* Strings go to both `ru` and `en` in `fedtail/i18n.py` (a test checks).
* Never log or send the token; requests to other servers go without it; the bug
  report excludes `auth.json` and `state.db`.
* The repository never names the author's own server; nothing is hardcoded.
* Comments and commit messages in English; user-facing config reference and
  README.ru.md in Russian.
* Versions: releases are tags `vX.Y.Z`; in the tagged commit `fedtail/__init__.py`
  says `X.Y.Z` and CHANGELOG has `## X.Y.Z — <date>`. Right after, bump to the next
  `X.Y+1.0.dev0` with `## X.Y+1.0 — in progress`. Every user-visible change gets a
  CHANGELOG line in the "in progress" section; cut a release when a batch of
  features has landed: set the release version and CHANGELOG date and push — CI's
  `release` job tags the commit and publishes a GitHub release once tests are green.
* Add a test with every fix (tests/fakes.py is an in-memory Mastodon), and keep
  `CHANGELOG.md` and the docs in step with the code — a new feature or switch also
  gets its row in `docs/FEATURES.md`.
