# fedtail on Windows from the source: running and testing

For testers and developers: how to put fedtail on Windows 10/11 from git, run it
and go through the same checks as on Linux. For people it's simpler as one file — `fedtail-…-windows.exe`
from a [release](https://github.com/eugene-vereshchagin/fedtail/releases).

The commands are for PowerShell. A test checks this file (`tests/test_windows_doc.py`):
the packages are the ones CI installs for Windows, the commands and switches are the ones in the code.

## 1. Python and git

Python 3.13 from python.org (it brings `py` — the launcher of the right version) and git. Through winget —
one package per command (an old winget won't take more than one at a time):

```powershell
winget install -e --id Python.Python.3.13
winget install -e --id Git.Git
```

Close PowerShell and open it again (to see the new programs), check:

```powershell
py -3.13 --version
git --version
```

## 2. The code and the packages

```powershell
git clone https://github.com/eugene-vereshchagin/fedtail.git
cd fedtail
py -3.13 -m pip install --user requests PySide6-Essentials textual cryptography
```

`PySide6-Essentials` — the Qt window, `textual` — the terminal interface, `cryptography` —
sync between devices. No GTK on Windows: Qt is there.

## 3. Running

```powershell
py -3.13 -m fedtail
py -3.13 -m fedtail --install-desktop
```

The first start: the server's address → logging in in the browser → the code from the browser into fedtail's window. The second
line — a Start menu entry (if you want one).

If the server's login page says "wrong password" for the right one (GoToSocial: "password/email
combination was incorrect"), fedtail isn't involved yet: the server didn't accept what
came from the form. What exactly, the server's log tells by the Request ID from the error (with GoToSocial:
`journalctl -u gotosocial | grep <Request ID>` — "password hash didn't match" means the email
is right, but a different password came). A way around: open the same link in a browser on another machine —
the code from there will do.

To update:

```powershell
git pull
py -3.13 -m fedtail --update-config
```

## Logs

Where they are (the default profile is `default`; run from the source, fedtail itself
prints `fedtail: logs in …` to the console at start):

| what | where |
|---|---|
| logs (send `latest.log`) | `%LOCALAPPDATA%\fedtail\default\logs\` |
| crashes (stacks) | the same place, `crash.log` |
| config, login | `%APPDATA%\fedtail\default\` |
| database, picture cache | `%LOCALAPPDATA%\fedtail\default\` |

Open the logs folder, watch the log live, make a report for a bug:

```powershell
explorer "$env:LOCALAPPDATA\fedtail\default\logs"
Get-Content "$env:LOCALAPPDATA\fedtail\default\logs\latest.log" -Tail 50 -Wait
py -3.13 -m fedtail --bug-report
```

From the window: the ≡ menu → Debugging → "Open the logs folder".

## 4. Tests

All the tests, the way CI runs them on Windows (Qt windows without a screen, `offscreen`):

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:PYTHONIOENCODING = "utf-8"
py -3.13 -X faulthandler -m unittest discover -s tests -t . -v
Remove-Item Env:QT_QPA_PLATFORM
```

The last line is a must (or a new PowerShell): with `offscreen` in this window fedtail itself
would draw its window "into nowhere". fedtail notices that and ignores it, but says so.

Skipped ones are what Windows doesn't have: GTK, `.desktop`, D-Bus. Failed ones — send
the whole output: the easiest is to add `2>&1 | Tee-Object tests.txt` to the test command —
the output stays in `tests.txt` in fedtail's folder. The tests write no logs of their own: it's all in the output.

## 4½. This page — in one command

Everything on this page that can run without a person (checking Python, git and the packages,
starting, the Start menu entry, `--update-config`, `--bug-report`, the tests) — in order, in a profile
of its own in a temporary folder (your fedtail, its entry and its logs aren't touched):

```powershell
py -3.13 tools/windows_check.py windows-check --tests
```

The `windows-check` folder gets `report.md` (what was done, what was skipped and why) and `errors.txt`.
The self-check (below) does the same by itself, as its `windows` step.

## 5. The self-check (as on Linux)

A walk through every window with screenshots, speed, the interfaces' parity — `tools/selfcheck.py`.
The web interface's walk needs Playwright (a venv of its own, once):

```powershell
py -3.13 tools/devenv.py
py -3.13 tools/selfcheck.py --quick
py -3.13 tools/selfcheck.py
py -3.13 tools/selfcheck.py --night
```

`--quick` — 3–5 minutes, no switches — 20–40 minutes, `--night` — everything, overnight (with your account
read only, screenshots blurred). At the end — the folder `C:\Users\<you>\fedtail_log\<date_time>\`: all the pictures and logs,
`report.md` and a zip in the same folder — send that one. Interrupted — `py -3.13 tools/selfcheck.py --clean` removes what's unfinished.
