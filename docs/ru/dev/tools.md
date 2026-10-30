# Инструменты разработчика

Всё, что лежит в `tools/`: зачем каждый и как запустить. Подробнее — в докстринге каждого
скрипта (`python3 tools/ИМЯ.py --help`, где есть ключи). Тест проверяет, что каждый
`tools/*.py` есть в этой таблице на обоих языках.

## Проверить всё разом

| инструмент | что делает | как запустить |
|---|---|---|
| `selfcheck.py` | всё, что ниже и что может работать на этой машине, за один заход: тесты, обходы всех интерфейсов со скриншотами, размеры окна, скорость, паритет; потом то же на твоём аккаунте (копия, только чтение); отчёт и zip для отправки | `python3 tools/selfcheck.py --night` (1–3 ч), `--quick` (5 мин) |
| `affected.py` | тесты, которые изменение может сломать, а не все: по модулям, функциям и событиям из диффа и по области, плюс проверки слоёв, паритета и документации; GUI — под xvfb | `python3 tools/affected.py`, `--since @{u}`, `--list` |
| `devenv.py` | Playwright и Chromium для обхода веба и галереи, в своём venv (питон Debian остаётся как есть) | `python3 tools/devenv.py`, один раз |
| `real.py` | `--real` для обходов и бенчей: твой аккаунт вместо фейкового сервера — копия профиля, наружу только GET | `--real[=ПРОФИЛЬ]` у других инструментов |
| `windows_check.py` | docs/ru/dev/windows.md, выполненный на этой Windows: каждая команда страницы, которую можно выполнить без человека, в отдельном профиле | `py -3.13 tools/windows_check.py OUT --tests` |

## Обходы интерфейсов

| инструмент | что делает | как запустить |
|---|---|---|
| `qt_tour.py` | окно Qt на фейковом сервере: каждая тема, каждое меню с описью, каждый диалог, окно настроек, размеры окна, утечки виджетов | `python3 tools/qt_tour.py OUT --native` |
| `gtk_screenshots.py` | окно GTK с выдуманными данными: каждая тема светлая и тёмная, HiDPI, размеры настоящих экранов | `xvfb-run -a python3 tools/gtk_screenshots.py OUT system point` |
| `tui_check.py` | интерфейс в терминале (Textual) без экрана: каждая лента, экран и клавиша; снимки в SVG | `python3 tools/tui_check.py OUT` |
| `web_check.py` | веб-страница в Chromium (Playwright): ленты, меню, редактор, просмотрщик, ширина телефона, ошибки JS | `python3 tools/web_check.py OUT` |
| `vendor.py` | пакеты в комплекте fedtail (`fedtail/_vendor/`, textual-image): нет ли новее на PyPI (`--check`, задача CI `vendored`); принести новую, сверив контрольную сумму (`--update`) | `python3 tools/vendor.py --check` |
| `screenshots.py` | настоящее окно Qt с выдуманными данными, PNG на тему (CI публикует их в ветке `screenshots`) | `QT_QPA_PLATFORM=offscreen python3 tools/screenshots.py OUT` |
| `tabs_stress.py` | десятки тредов, профилей и тегов открываются и закрываются раунд за раундом в Qt, GTK и терминале: что остаётся живым — утечка | `python3 tools/tabs_stress.py OUT --ui qt` |

## Поведение и паритет

| инструмент | что делает | как запустить |
|---|---|---|
| `behaviour.py` | один сценарий (лента, ⋯, лайк, буст, тред, ответ, профиль, удаление, командная строка…) через все пять интерфейсов, сверка с тем, что решает `frontends/common` | `python3 tools/behaviour.py OUT.md` |
| `parity.py` | какие слова интерфейса (кнопки, пункты меню, диалоги) показывает один фронтенд и не показывают другие | `python3 tools/parity.py OUT.md` |
| `cross_check.py` | несколько прогонов самопроверки рядом: KDE как эталон, Windows, GTK — вид, меню, поведение, падения | `python3 tools/cross_check.py ЭТАЛОН ДРУГОЙ…` |
| `theme_compare.py` | каждая тема в Qt и в GTK рядом, со сравнением их главных цветов | `python3 tools/theme_compare.py SELFCHECK_OUT` |

## Скорость и покрытие

| инструмент | что делает | как запустить |
|---|---|---|
| `qt_bench.py` | насколько быстро окно Qt: старт, ленты, прокрутка тысяч постов, меню, редактор, темы, split | `python3 tools/qt_bench.py` |
| `membench.py` | память и скорость на одних синтетических сутках: USS/PSS/RSS, где лежит память Python (`--trace`), старт, ленты, правила, прокрутка (`--ui qt`) — базовая линия [memory.md](memory.md) | `python3 tools/membench.py --ui qt` |
| `gtk_bench.py` | то же для окна GTK | `python3 tools/gtk_bench.py` |
| `coverage_lite.py` | покрытие строк без установки чего-либо (sys.monitoring, Python 3.12+), считаются все процессы ночного прогона (`tools/covhook/`) | `python3 tools/coverage_lite.py OUT` |
| `stats.py` | числа для README: строки каждой части, тесты, покрытие → `docs/src/stats.toml` и часть `stats` (пишет ночной самопроверочный прогон; `tests/test_stats.py` скажет, когда они устарели) | `python3 tools/stats.py --write [--coverage DIR]` |

## Данные, картинки и звуки

| инструмент | что делает | как запустить |
|---|---|---|
| `showcase.py` | выдуманный мир, который показывают все скриншоты (люди, тред, опрос, картинки), нарисованный без сети и тулкита | его импортируют другие инструменты |
| `gallery.py` | картинки для сайта и доков: каждый интерфейс в выдуманном мире, плюс `gallery.toml` с подписями на двух языках | `python3 tools/gallery.py OUT` |
| `userthemes.py` | твои собственные темы из `~/.config/fedtail/themes`: обходы их проверяют, галерея не показывает никогда | его импортируют другие инструменты |
| `make_sounds.py` | собственные звуковые наборы fedtail, синтезом (без чужих сэмплов), поэтому они наши под GPL-3 | `python3 tools/make_sounds.py`, `--check` |
| `model_check.py` | прогоняет адаптер Mastodon по всем постам, сохранённым в профиле, только чтение, и говорит, как вышла модель | `python3 tools/model_check.py [ПРОФИЛЬ]` |
| `push_probe.py` | пушит ли твой сервер? Web Push от него в тему ntfy, расшифровывается здесь | `python3 tools/push_probe.py` |
| `android_icons.py` | значки Android-приложения (адаптивный, круглый, монохромный для тем) из `fedtail/data/icons/fedtail.png` | `python3 tools/android_icons.py` |
| `swing_frames.py` | кадры качающегося опоссума для GTK (лист кадров и их времена) из `fedtail/data/icons/fedtail-swing.gif` | `python3 tools/swing_frames.py` |

## Документация

| инструмент | что делает | как запустить |
|---|---|---|
| `docs_build.py` | собирает все генерируемые документы (возможности, сравнение, настройки, руководство по лентам, части, справку) и заново заполняет все вставки | `python3 tools/docs_build.py`, `--check` |
| `config_doc.py` | справочник настроек из примеров конфига (его зовёт docs_build) | `python3 tools/config_doc.py` |
| `lane_pictures.py` | рисует библиотеку картинок для лент (`fedtail/data/icons/lanes`, 16×16, цвета темы {c} {l} {d} {o}) | `python3 tools/lane_pictures.py` |
