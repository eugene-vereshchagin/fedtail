# CI и релизы

Всё, что работает на GitHub Actions, и как выпускается релиз. Тест проверяет, что каждая задача
`.github/workflows/ci.yml`, `site.yml` и `vendor.yml` есть в этих таблицах на обоих языках.

## `ci.yml`: на каждый пуш

Пуш в `main` запускает всё: около часа вместе со сборками, поэтому пушить пачками, а не после каждой мелочи.
Коммит с `[skip ci]` в сообщении не запускает ничего.

| задача | когда | что делает |
|---|---|---|
| `lint` | каждый пуш и PR | `ruff check .` (длина строки 100) |
| `types` | каждый пуш и PR | `mypy` по `fedtail/model`, `fedtail/core` и `fedtail/protocols` (`[tool.mypy]` в pyproject), мягко: в функцию без аннотаций заглядывает, аннотировать ничего не обязывает; только предупреждения, релиз не держит. Чисто с 24.11 — так и держать: `~/.cache/fedtail/devenv/bin/python3 -m mypy` перед коммитом, который трогает ядро |
| `security` | каждый пуш и PR | код синхронизации смотрит в интернет: `bandit` и правила bandit в ruff по `fedtail/core/sync`; клиент против настоящего сервера (main репозитория fedtail-syncserver, его версия должна быть версией fedtail), на Python 3.11 и 3.13 — собственные тесты сервера идут в его репозитории |
| `audit` | каждый пуш и PR | известные уязвимости в том, на чём работает fedtail (`pip-audit`): только предупреждения, новая CVE у зависимости релиз не держит |
| `test` | каждый пуш и PR | все тесты на Python 3.11, 3.12 и 3.13 с Qt из pip, без экрана; потом fedtail ставится как пакет и запускается |
| `web-check` | каждый пуш и PR | веб-страница в Chromium (Playwright): `tools/web_check.py` — все ленты, меню ≡ и ⋯, редактор, тред, просмотрщик, ширина телефона, удержание карточки при открытии, чтение в колонке; при неудаче её скриншоты остаются; `release` её ждёт |
| `budgets` | каждый пуш и PR | стенд памяти (`tools/membench.py`: 2000 постов, 20 лент, час опроса) — одно ядро и окно Qt — против потолков памяти, времени, виджетов и кэша картинок (`tests/test_budgets.py`, docs/ru/dev/memory.md, шаг 8); `release` его ждёт |
| `debian` | каждый пуш и PR | все тесты на Debian 13 с Qt и GTK 4 из apt, под Xvfb — настоящая цель; затем отдельно `tests.test_qt_by_hand`, Qt на X11 (xcb) |
| `windows` | каждый пуш и PR | все тесты на Windows с Qt из pip (docs/ru/dev/windows.md использует те же пакеты и команду, тест проверяет) |
| `windows-build` | пуш в `main` | `fedtail.exe` одним файлом (PyInstaller, `packaging/build.py`) с Qt 6.9, как и для Linux (6.10 и новее требуют SSE4.2), один раз запускается; установщик `fedtail-setup.exe` (Inno Setup, `packaging/windows/fedtail.iss`); оба подписываются, если есть сертификат для подписи кода (секреты `WINDOWS_CERT_PFX` — .pfx в base64 — и `WINDOWS_CERT_PASSWORD`), иначе без подписи |
| `linux-build` | пуш в `main` | `fedtail` для Linux одним файлом, собирается на Debian 12, чтобы работал и на старых системах, с Qt 6.9 (6.10 и новее требуют SSE4.2), и проверяется на эмулированном процессоре времён Phenom |
| `deb` | каждый пуш и PR | `.deb` для Debian 13, по пакету на интерфейс (`packaging/deb.py`): `fedtail-common` (сама программа), `fedtail-qt`, `fedtail-gtk`, `fedtail-tui` (каждый — свой тулкит), `fedtail` (программа и окно) |
| `deb-install` | после `deb` | каждый способ их поставить в чистом Debian через apt — обычный (`fedtail`), только GTK, терминал, одна программа: запускается, `ui.frontend = "auto"` берёт окно, которое пришло, пакет GTK никогда не тянет Qt, одна программа — ни одного тулкита |
| `pypi` | каждый пуш и PR | пакет Python (`python -m build`: sdist и wheel), `twine check --strict`, установка в чистый venv и запуск; каждый файл из `fedtail/data/` должен быть в wheel (`tests/test_packaging.py` держит к этому маски `pyproject.toml`) |
| `arch` | каждый пуш и PR | пакет для Arch Linux (`packaging/arch.py`: PKGBUILD из имён `arch` в `fedtail/deps.py`) собирается `makepkg` из архива `packaging/source.py` в чистом Arch, namcap, установка через pacman и запуск; `fedtail --check` там подсказывает `pacman -S` |
| `rpm` | каждый пуш и PR | RPM для Fedora (`packaging/rpm.py`: spec из имён `rpm` той же таблицы, pyproject-макросы Fedora) собирается в чистой Fedora, rpmlint (говорит, но не держит), установка через dnf, проверка пункта меню и файла AppStream, запуск; `fedtail --check` там подсказывает `dnf install` |
| `appimage` | пуш в `main` (и руками) | AppImage (`packaging/appimage.py`): папка PyInstaller (`packaging/build.py --onedir`) собирается на Debian 12, appimagetool закреплён по sha256, образ и его `.zsync`; запуск из образа |
| `flatpak` | пуш в `main` (и руками) | бандл Flatpak из `packaging/flatpak/online.dmesg.fedtail.yml` (рантайм KDE, BaseApp с PySide6; пакеты Python закреплены по sha256) в образе сборщика flathub-infra |
| `nix` | пуш в `main` (и руками) | `nix build` flake (`flake.nix`, `packaging/nix/package.nix`) из nixpkgs, как их держит `flake.lock`; запуск |
| `docker` | каждый пуш и PR | образ веб-интерфейса (`packaging/docker/`; `.dockerignore` пускает только сам пакет) собирается и запускается: страница отвечает 403 без ключа, ссылка для входа — в журнале |
| `apk` | пуш в `main` | только если в `fedtail/__init__.py` версия релиза без тега: APK для Android, собранный и подписанный релизным ключом (секреты `ANDROID_KEYSTORE`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`; android/README.md, «Releases»); без ключа — предупреждение, релиз выходит без него |
| `screenshots` | вручную (Actions → CI → Run workflow), только `main` | каждая тема рисуется с выдуманными данными, PNG принудительно пушатся в ветку `screenshots` |
| `release` | пуш в `main`, когда всё выше зелёное | если в `fedtail/__init__.py` версия релиза, у которой ещё нет тега: ставит на коммит тег `vX.Y.Z`, публикует релиз на GitHub с разделом CHANGELOG как заметками и файлами — Windows (.exe и установщик), Linux (один файл, AppImage с его `.zsync`, Flatpak), Debian, Arch, Fedora, wheel, архив исходников с `PKGBUILD` для AUR и `fedtail.spec`, которые его называют, Android (если подписан), `SHA256SUMS` |
| `pypi-publish` | после того как `release` выпустил релиз | sdist и wheel релиза — на PyPI через trusted publishing (PyPI → проект → Publishing: этот репозиторий, `ci.yml`, окружение `pypi`); пока переменная репозитория `PYPI_PUBLISH` не `true` — предупреждение, ничего не отправляется |
| `docker-publish` | после того как `release` выпустил релиз | образ по тегу релиза — в `ghcr.io/eugene-vereshchagin/fedtail` как `X.Y.Z` и `latest`, собственным токеном репозитория |
| `apt` | после того как `release` выпустил релиз | `.deb` релиза — в apt-репозиторий: ветка `apt` (её отдаёт GitHub Pages), индексы заново и подписаны ключом репозитория (секрет `APT_GPG_KEY`, приватный ключ в armor без пароля; `packaging/apt_repo.py`); без ключа — предупреждение, ничего не публикуется; руками для уже вышедшего релиза — `apt.yml` (Actions → apt → Run workflow, версия) |
| `site` | после того как `release` выпустил релиз (и после `apt`) | `site.yml` для новой версии: сайт пересобирается, и задача ждёт, пока он покажет этот релиз (ниже) |

Когда тест падает, `.github/annotate.py` превращает падения в аннотации прогона (журналы задач
не всегда можно скачать).


`android.yml` собирает dev-APK для телефона (свой id `online.dmesg.fedtail.dev`, dev-ключ) при пуше в `main`, задевающем
`android/` или ядро, запускает его на эмуляторе — скриншоты и UI-тесты (`android/app/src/androidTest`) в ветку
`android-shots` — и прикладывает APK к прогону (android/README.md). Если релизный ключ есть в секретах, он ещё
собирает тот же коммит, подписанный им, `online.dmesg.fedtail` (`fedtail-android-update-N`): этот ставится поверх
вышедшего приложения, с его входом и данными.
## `site.yml`: сайт

| задача | когда | что делает |
|---|---|---|
| `rebuild` | каждую ночь в 05:37 по Тбилиси, после релиза (`site` в ci.yml) и вручную | зовёт deploy hook сайта (секрет `SITE_DEPLOY_HOOK` или `DOCS_UPDATE`), чтобы «что будет» не отставало от `main`; потом до 20 минут ждёт, пока `/version.txt` живого сайта назовёт релиз (заданный, иначе последний тег), а главная станет ссылаться на apk и бинарник для Linux из релиза, и падает, если нет (сайт, собранный до загрузки файлов, писал, что такого файла нет) — сборка сайта что-то отвергла и Cloudflare оставил старую версию; в сводке прогона — какую сборку Cloudflare смотреть |

Сайт живёт в своём репозитории и собирается из этого: доки последнего релиза, доки разработчика
из `main`, ссылки на файлы релиза. Релиз пересобирает его сразу. Сборка сайта проверяет себя
(`tools/check_site.py` там): сломанная страница валит сборку, и онлайн остаётся старый сайт — это
`rebuild` превращает в красный прогон. Доки, взятые отсюда, там дают только предупреждения: их
пары RU/EN проверяют здешние тесты.

## `vendor.yml`: пакеты в комплекте fedtail

| задача | когда | что делает |
|---|---|---|
| `vendored` | каждую ночь в 06:17 по Тбилиси и вручную | `tools/vendor.py --check`: нет ли на PyPI новой версии пакета из `fedtail/_vendor/` (textual-image)? Если есть — красный прогон, а в аннотации команда, которая её принесёт (`tools/vendor.py --update`) |

Чего нет в Debian, а fedtail нужно, лежит внутри него: wheel с PyPI как есть, контрольная сумма
сверена, список — `fedtail/_vendor/VENDORED.toml`; копия в системе или из pip главнее.

## Как выпустить релиз

1. В разделе `## What's next` в `CHANGELOG.md` есть всё, что пользователь заметит со времени прошлого релиза.
2. Одним коммитом: в `fedtail/__init__.py` — `X.Y.Z`, заголовок CHANGELOG становится `## X.Y.Z — <дата>`,
   у пришедших в нём возможностей в `docs/src/features/` вместо `"next"` стоит `since = "X.Y.Z"`, `python3 tools/docs_build.py`,
   `python3 tools/stats.py` (цифры в README пересчитаны, вместе с ними `docs/src/tokens.json`).
3. Пуш. Когда CI зелёный, задача `release` ставит тег и публикует; сайт подтягивается.
4. Сразу после: поднять до `X.Y.Z+1.dev0` с новым разделом `## What's next` — без номера: какой будет следующий, решается при выпуске.

Релизы выпускаются только по слову автора.
