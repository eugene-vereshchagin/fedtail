# Notes for coding agents (and humans in a hurry)

Read `docs/ARCHITECTURE.md` first: it maps every module, the threads, the store
schema, the lanes, the poll cycle, the events and the Qt frontend, with recipes
for common changes. `docs/DESIGN.md` (Russian) is the product spec and the queue
of planned work. `docs/DEBUGGING.md` explains the logs a user can send.

## Run, test, lint

```sh
python3 -m fedtail                       # run from the checkout (needs PySide6 + requests)
python3 -m unittest discover -s tests -t .   # all tests; Qt ones skip without PySide6
QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_qt_smoke
ruff check .                             # line length 100
python3 tools/screenshots.py out/        # PNGs of every theme with made-up data
```

Debian 13 packages: `python3-pyside6.qtwidgets python3-requests` (no QtTest there).

## Rules

* The core (`fedtail/core`, `fedtail/diag.py`) never imports Qt. Frontends talk to
  `Core` through futures and events only.
* Qt objects only in the GUI thread; results come back via `Bridge.call`.
* Every behaviour is a flag: add new options to `config.DEFAULTS` **and**
  `fedtail/data/config.example.toml` (commented, Russian explanation) — a test
  checks they match.
* Strings go to both `ru` and `en` in `fedtail/i18n.py` (a test checks).
* Never log or send the token; requests to other servers go without it; the bug
  report excludes `auth.json` and `state.db`.
* The repository never names the author's own server; nothing is hardcoded.
* Comments and commit messages in English; user-facing config reference and
  README.ru.md in Russian.
* Add a test with every fix (tests/fakes.py is an in-memory Mastodon), and keep
  `CHANGELOG.md` and the docs in step with the code.
