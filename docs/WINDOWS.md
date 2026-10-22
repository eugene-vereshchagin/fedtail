# fedtail на Windows из исходников: запуск и тесты

[English below](#english)

Для тестировщиков и разработчиков: как поставить fedtail на Windows 10/11 из git, запустить
и прогнать те же проверки, что на Linux. Людям проще одним файлом — `fedtail-…-windows.exe`
из [релиза](https://github.com/eugene-vereshchagin/fedtail/releases).

Команды — для PowerShell. Этот файл проверяется тестом (`tests/test_windows_doc.py`):
пакеты — те же, что ставит CI для Windows, команды и ключи — те, что есть в коде.

## 1. Python и git

Python 3.13 с python.org (в нём есть `py` — запускалка нужной версии) и git. Через winget —
по одному пакету в команде (старый winget больше одного за раз не принимает):

```powershell
winget install -e --id Python.Python.3.13
winget install -e --id Git.Git
```

Закрыть PowerShell и открыть заново (чтобы увидеть новые программы), проверить:

```powershell
py -3.13 --version
git --version
```

## 2. Код и пакеты

```powershell
git clone https://github.com/eugene-vereshchagin/fedtail.git
cd fedtail
py -3.13 -m pip install --user requests PySide6-Essentials textual cryptography
```

`PySide6-Essentials` — окно Qt, `textual` — интерфейс в терминале, `cryptography` —
синхронизация между устройствами. GTK на Windows не делаем: там Qt.

## 3. Запуск

```powershell
py -3.13 -m fedtail
py -3.13 -m fedtail --install-desktop
```

Первый запуск: адрес сервера → вход в браузере → код из браузера в окно fedtail. Вторая
строка — ярлык в меню «Пуск» (по желанию).

Если страница входа сервера говорит «неверный пароль» при верном (GoToSocial: «password/email
combination was incorrect»), до fedtail дело ещё не дошло: это сервер не принял то, что
пришло из формы. Что именно, скажет лог сервера по Request ID из ошибки (у GoToSocial:
`journalctl -u gotosocial | grep <Request ID>` — «password hash didn't match» значит, email
верный, а пароль пришёл другой). Обойти: открыть ту же ссылку в браузере на другой машине —
код оттуда подойдёт.

Обновиться:

```powershell
git pull
py -3.13 -m fedtail --update-config
```

## Логи

Где лежат (профиль по умолчанию — `default`; запущенный из исходников fedtail при старте
сам пишет в консоль `fedtail: logs in …`):

| что | где |
|---|---|
| логи (присылать `latest.log`) | `%LOCALAPPDATA%\fedtail\default\logs\` |
| падения (стеки) | там же, `crash.log` |
| конфиг, вход | `%APPDATA%\fedtail\default\` |
| база, кэш картинок | `%LOCALAPPDATA%\fedtail\default\` |

Открыть папку логов, смотреть лог вживую, собрать отчёт для багрепорта:

```powershell
explorer "$env:LOCALAPPDATA\fedtail\default\logs"
Get-Content "$env:LOCALAPPDATA\fedtail\default\logs\latest.log" -Tail 50 -Wait
py -3.13 -m fedtail --bug-report
```

Из окна: меню ≡ → Отладка → «Открыть папку логов».

## 4. Тесты

Все тесты, как их гоняет CI на Windows (окна Qt — без экрана, `offscreen`):

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:PYTHONIOENCODING = "utf-8"
py -3.13 -X faulthandler -m unittest discover -s tests -t . -v
```

Пропущенные (skipped) — то, чего на Windows нет: GTK, `.desktop`, D-Bus. Упавшие — присылать
вывод целиком: удобнее всего дописать к команде тестов `2>&1 | Tee-Object tests.txt` —
вывод останется в `tests.txt` в папке fedtail. Своих логов тесты не пишут: всё в выводе.

## 5. Самопроверка (как на Linux)

Обход всех окон со скриншотами, скорость, паритет интерфейсов — `tools/selfcheck.py`.
Для обхода веб-интерфейса нужен Playwright (свой venv, один раз):

```powershell
py -3.13 tools/devenv.py
py -3.13 tools/selfcheck.py --quick
py -3.13 tools/selfcheck.py
py -3.13 tools/selfcheck.py --night
```

`--quick` — 3–5 минут, без ключей — 20–40 минут, `--night` — всё, на ночь (с твоим аккаунтом
только на чтение, скриншоты размыты). В конце — папка `selfcheck-<дата>` с `report.md` и zip
рядом: zip и присылать. Прервал — `py -3.13 tools/selfcheck.py --clean` уберёт недоделанное.

---

<a id="english"></a>
# fedtail on Windows from the source: running and testing

For testers and developers: fedtail on Windows 10/11 from git, run, and the same checks as on
Linux. People are better off with the one file `fedtail-…-windows.exe` from a release. The
commands are PowerShell's; `tests/test_windows_doc.py` checks this file against CI and the
code.

1. Python and git, one package per winget command (an old winget takes no more), then a new
   PowerShell:

   ```powershell
   winget install -e --id Python.Python.3.13
   winget install -e --id Git.Git
   ```

2. The code and the packages (the same as CI's Windows job):

   ```powershell
   git clone https://github.com/eugene-vereshchagin/fedtail.git
   cd fedtail
   py -3.13 -m pip install --user requests PySide6-Essentials textual cryptography
   ```

3. Run: `py -3.13 -m fedtail` (server address → sign in in the browser → the code back into
   fedtail); `py -3.13 -m fedtail --install-desktop` — a Start menu shortcut. A sign-in page
   saying the right password is wrong is the server refusing what the form sent, before
   fedtail has any part: its log by the error's Request ID says what (GoToSocial: "password
   hash didn't match" — the email is right, the password came different); open the link on
   another machine and bring the code back. Update: `git pull`, `py -3.13 -m fedtail
   --update-config`. Logs (fedtail from the source says where at start: `fedtail: logs in
   …`): `%LOCALAPPDATA%\fedtail\default\logs\latest.log`, crashes in `crash.log` there;
   config and login: `%APPDATA%\fedtail\default\`. Open the folder: `explorer
   "$env:LOCALAPPDATA\fedtail\default\logs"`; follow the log: `Get-Content
   "$env:LOCALAPPDATA\fedtail\default\logs\latest.log" -Tail 50 -Wait`. Test output to a
   file: add `2>&1 | Tee-Object tests.txt` to the test command.

4. Tests, as CI runs them:

   ```powershell
   $env:QT_QPA_PLATFORM = "offscreen"
   $env:PYTHONIOENCODING = "utf-8"
   py -3.13 -X faulthandler -m unittest discover -s tests -t . -v
   ```

5. Selfcheck: `py -3.13 tools/devenv.py` once (Playwright), then `py -3.13 tools/selfcheck.py
   --quick` / no flags / `--night`; send the zip next to the `selfcheck-<date>` folder.
