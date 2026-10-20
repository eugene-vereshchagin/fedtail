# Notes for coding agents (and humans in a hurry)

Read `docs/ARCHITECTURE.md` first: it maps every module, the threads, the store
schema, the lanes, the poll cycle, the events and the Qt frontend, with recipes
for common changes. `docs/DESIGN.md` (Russian) is the product spec and the queue
of planned work. `docs/DEBUGGING.md` explains the logs a user can send; `docs/TESTING.md` is the page
for alpha testers (install, what to try, how to report); `docs/en/features.md` (and
`docs/ru/`) is the feature table (have / partly / no / planned, since which version, other
clients, the config switch for each) — generated, see "Docs" below.

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
* Every behaviour is a flag: add new options to `config.DEFAULTS` **and** both
  `fedtail/data/config.example.ru.toml` and `config.example.en.toml` (set to the default,
  the explanation above in that file's language) — tests check they match `DEFAULTS` and
  each other line for line, comments aside.
* Strings go to both `ru` and `en` in `fedtail/i18n.py` (a test checks).
* Never log or send the token; requests to other servers go without it; the bug
  report excludes `auth.json` and `state.db`.
* The repository never names the author's own server; nothing is hardcoded. One
  exception, the author's wish: `version.AUTHOR` / `AUTHOR_URL`, his fediverse address
  linked from About — nothing else may use them.
* Comments and commit messages in English. User-facing docs come in Russian and English:
  README.md / README.ru.md, `docs/en/` / `docs/ru/`, `fedtail/data/help/en|ru/`.
  ARCHITECTURE.md and CHANGELOG.md are English only, DESIGN.md Russian only.
* Versions: releases are tags `vX.Y.Z`; in the tagged commit `fedtail/__init__.py`
  says `X.Y.Z` and CHANGELOG has `## X.Y.Z — <date>`. Right after, bump to the next
  `X.Y+1.0.dev0` with `## X.Y+1.0 — in progress`. Every user-visible change gets a
  CHANGELOG line in the "in progress" section; cut a release when a batch of
  features has landed: set the release version and CHANGELOG date and push — CI's
  `release` job tags the commit and publishes a GitHub release once tests are green.
* Add a test with every fix (tests/fakes.py is an in-memory Mastodon), and keep
  `CHANGELOG.md` and the docs in step with the code — a new feature or switch also
  gets its entry in `docs/src/features/<chapter>.toml`, in the same commit: status,
  `since` (the version it comes in), config key, API, other clients, `name`/`details`
  in both `ru` and `en`. That list is what fedtail does *now* (not a history: that's the
  CHANGELOG's job) — a changed behaviour rewrites its entry, a removed one goes, a
  planned one becomes "has" with its `since` when done.

## Docs

* `python3 tools/docs_build.py` after any change to `docs/src/`, the example configs or a
  part; it writes `docs/<lang>/features.md`, `comparison.md`, `config.md`, the generated
  parts, and refills every `<!-- include: … -->` block in the READMEs, `docs/` and the
  in-app help. Never edit generated files or the text between include markers by hand —
  a test runs `--check` and fails.
* Reused texts are parts: `docs/<lang>/parts/*.md`, no top heading, links from the repo
  root (`/docs/en/…`), no includes inside. The in-app help is `fedtail/data/help/<lang>/`.
* Docstrings: Google style; every module starts with what it is for.
