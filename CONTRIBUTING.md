# Contributing to fedtail

[По-русски — ниже](#по-русски)

## Reporting a bug

Open an [issue](https://github.com/eugene-vereshchagin/fedtail/issues/new/choose) and say:

* what you did, what you expected, what happened (a screenshot helps a lot);
* the version: the bottom of the sidebar, or `python3 -m fedtail --version`;
* your server software if you know it (GoToSocial, Mastodon, Akkoma, Friendica…);
* attach `latest.log` from the log folder (menu ≡ → Debugging → Open the log folder), or the archive made by
  `python3 -m fedtail --bug-report`.

Logs never contain your token or the texts of posts — API paths, ids, timings and errors only.
The bug-report archive includes your config: look it over before attaching. Security problems
go privately, see [SECURITY.md](SECURITY.md).

## Proposing a change

Ideas are welcome as issues first: fedtail has a point of view (see the README and
[docs/DESIGN.md](docs/DESIGN.md)), and every behaviour is meant to be a config flag rather
than a fork in the road.

For code:

```sh
python3 -m unittest discover -s tests -t .   # Qt tests skip without PySide6
QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_qt_smoke
ruff check .                                 # line length 100
```

Read [AGENTS.md](AGENTS.md) (one page of rules) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
(the map). In short: the core never imports Qt; every option goes into `config.DEFAULTS` and the
`fedtail/data/config.example.toml` (with its explanation); every string into both `ru` and `en`; every fix
comes with a test; `CHANGELOG.md` and the docs keep up with the code. Comments and commit
messages in English.

Most of fedtail is written by an AI (Claude) under a human's review. Contributions by people
and by their tools are judged the same way: by the diff, the tests and whether it fits.

By contributing you agree that your work is licensed under GPL-3.0-or-later, like the rest.

## По-русски

**Ошибка:** заведи [issue](https://github.com/eugene-vereshchagin/fedtail/issues/new/choose):
что делал, что ждал, что получилось (скриншот очень помогает), версия (внизу боковой панели
или `python3 -m fedtail --version`), какой у тебя сервер, и приложи
`latest.log` из папки логов (меню ≡ → «Отладка» → «Открыть папку логов») или архив `python3 -m fedtail --bug-report`. В журнале
нет токена и текстов постов; в архиве есть конфиг — посмотри его перед отправкой. Уязвимости —
не в issue, а приватно, см. [SECURITY.md](SECURITY.md).

**Изменения:** сначала идея в issue — у fedtail есть свой взгляд на вещи, и любое поведение
должно быть флагом в конфиге. Для кода — тесты, `ruff check .`, правила в
[AGENTS.md](AGENTS.md), карта в [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Вклад
лицензируется под GPL-3.0-or-later.
