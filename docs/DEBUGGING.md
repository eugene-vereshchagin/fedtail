# Отладка и логи / Debugging and logs

[English below](#english)

До версии 1.0 (и в сборках для разработки) fedtail пишет подробный журнал сам —
это режим отладки, `debug.mode = "auto"`. Клиент держат открытым сутками, и если он
упадёт, зависнет, начнёт есть память или процессор — по журналу видно, что происходило.
В релизах с 1.0 режим выключен: в папке данных профиля, `logs/`, остаются только
предупреждения и ошибки, несколько МБ, и crash.log. Включить — `debug.mode = "on"` или
на один запуск `python3 -m fedtail --debug`.

## Где лежит

В домашней папке, `~/fedtail-logs/<профиль>/` (другое место — `debug.log_dir`;
`""` — папка данных профиля, `logs/`):

```
~/fedtail-logs/default/
    2026-10-16_15-04-12.log   журнал: новый файл при каждом запуске и каждый час
                              (и при debug.log_mb), всего не больше debug.keep_mb —
                              самые старые удаляются сами
    latest.log       ссылка на файл, который пишется сейчас, — его и присылай
    crash.log        стеки всех потоков, если процесс упал (segfault в Qt и т.п.)
    stacks.log       стеки по запросу и при зависании окна
```

Кроме запросов и опросов, журнал пишет и действия: какая лента открыта, какие вкладки,
клики по действиям у постов (лайк, ответ, тред — по id, без текстов), что отправлено
(длина и куда, не текст), сколько строк нарисовано и за сколько, долгие события окна.

Быстро открыть: меню ≡ → «Отладка» → «Открыть папку логов».

## Что в журнале

* шапка каждого запуска: версия и коммит, Python, Qt/PySide6, рабочий стол,
  PID, профиль;
* каждый запрос к серверу: метод, путь, параметры листания, код ответа, время,
  размер. Медленные (дольше `debug.slow_request_seconds`) и ошибочные — с пометкой
  WARNING. **Токена, текстов постов и тел запросов в журнале нет**;
* каждый опрос сервера: сколько занял и что пришло;
* ошибки — с полной трассировкой, включая ошибки в фоновых потоках;
* раз в `debug.stats_minutes` минут — строка `stats`: память (rss_mb, peak_mb),
  процессор (cpu_pct за интервал), потоки, открытые файлы, размер базы и число
  строк в ней, очереди пулов, кэши, число виджетов Qt и строк в лентах, кэш
  картинок. По этим строкам видно утечку: что растёт со временем;
* сообщения самого Qt (раньше сыпались в терминал);
* если окно не отвечает дольше `debug.watchdog_seconds` секунд — стеки всех
  потоков (на чём именно висит) и потом «responsive again after N s».

## Если что-то случилось

**Упало.** Запусти `python3 -m fedtail --bug-report` — в домашней папке появится
`fedtail-report-<профиль>-<дата>.tar.gz`. Пришли этот файл. В нём журналы,
crash.log, stacks.log, config.toml и сводка о системе. Файла с токеном
(`auth.json`) и базы (`state.db`) там нет.

**Зависло / тормозит.** Не закрывая клиент:

* меню ≡ → «Отладка» → «Записать стеки потоков и статистику», или
* в терминале: `kill -USR1 $(pgrep -f "python3 -m fedtail")` — стеки уйдут в
  `stacks.log` даже если окно совсем не отвечает;

потом `--bug-report` (или меню → «Собрать отчёт для разбора») и прислать.

**Нет уведомлений.** Меню ≡ → «Отладка» → «Проверить уведомление». Если не пришло —
в журнале будут строки `notifications:` (какой способ выбран и почему) и `notify-send exit …`
(что ответила система). Без пакета `libnotify-bin` уведомления идут через трей.

**Ест память или процессор.** Достаточно `--bug-report` через какое-то время
работы: в журнале строки `stats` за всё время.

## Настройки — секция `[debug]`

```toml
[debug]
level = "debug"            # "debug" | "info" | "warning" — подробность журнала
log_mb = 10                # размер одного файла журнала
keep = 5                   # сколько старых хранить
stats_minutes = 5          # 0 — не писать статистику
watchdog_seconds = 8       # 0 — не следить за зависаниями окна
slow_request_seconds = 5
rss_warn_mb = 1500
```

`--debug` дополнительно выводит весь журнал в терминал.

---

<a name="english"></a>
## English

Until 1.0 fedtail always keeps a detailed log. It's meant to stay open for days,
so when it crashes, hangs or grows, the log shows what happened.

**Where:** `~/fedtail-logs/<profile>/` (`debug.log_dir`) — a new
`YYYY-MM-DD_HH-MM-SS.log` per start and per hour, `latest.log` links to the current one,
the folder kept under `debug.keep_mb`;
`crash.log` (all thread stacks on a fatal crash), `stacks.log` (stacks on demand
and when the window freezes). Menu ≡ → Debugging → Open the logs folder.

**What's in it:** a header per run (versions, desktop, pid); every API request
with method, path, paging, status, time and size (never the token, post texts or
request bodies); every poll with its timing and what came; errors with full
tracebacks from any thread; a `stats` line every `debug.stats_minutes` (memory,
CPU, threads, fds, database size and rows, pool queues, caches, Qt widgets and
rows, image cache) — growth over time shows a leak; Qt's own messages; when the
GUI thread doesn't answer for `debug.watchdog_seconds`, the stacks of all threads.

**When something happens:** `python3 -m fedtail --bug-report` makes
`~/fedtail-report-<profile>-<date>.tar.gz` with the logs, crash and stack files,
the config and a system summary — without `auth.json` and `state.db`. For a hang,
first dump the stacks: menu → Debugging → Write thread stacks, or
`kill -USR1 <pid>` (works even when the window is frozen).

**Settings:** the `[debug]` section (level, log size and count, stats interval,
watchdog, slow request and memory thresholds). `--debug` also prints the whole
log to the terminal.

For how the diagnostics are built, see ARCHITECTURE.md §18.
