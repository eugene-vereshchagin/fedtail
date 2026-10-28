# For developers

fedtail is a Python program: a core that knows nothing of GUIs, a protocol layer with
Mastodon as the first protocol, and four interfaces on top — a Qt window, a GTK window, the
terminal (Textual) and a web page. Most of the code is written by an AI (Claude) under a
human's review; contributions by people and their tools are judged the same way: by the diff,
the tests and whether it fits.

## Where to read what

| document | what's in it |
|---|---|
| [architecture.md](architecture.md) | the map: every module, the threads, the store schema, lanes, the poll cycle, events, the frontends, recipes for common changes |
| [design.md](design.md) | the product spec, the principles and the queue of planned work |
| [protocols.md](protocols.md) | how Mastodon became one protocol among others behind fedtail's own data model |
| [memory.md](memory.md) | making fedtail lighter: the plan, step by step, the bench and its numbers before and after each step |
| [gtk.md](gtk.md) | the plan and the state of the GTK 4 frontend |
| [layouts.md](layouts.md) | the messenger-style layouts (QIP, Psi+, Mail.ru Agent) and their themes |
| [windows.md](windows.md) | running and testing on Windows from the source |
| [robustness.md](robustness.md) | robustness: the network, the OS, the disk, the interface, security — questions, answers and decisions |
| [testplan.md](testplan.md) | what checks itself, with what and where; what's left for the eyes |
| [testing.md](testing.md) | the page for alpha testers: installing, what to try, how to report |
| [debugging.md](debugging.md) | the logs: what's in them, how to hunt leaks and freezes |
| [tools.md](tools.md) | every developer tool in `tools/` |
| [ci.md](ci.md) | CI jobs and how a release is made |
| [roadmap.md](roadmap.md) | the plan for the next version |
| [feeds.md](feeds.md) | free lanes: atoms, rules, what can be reached, the problems (a design) |
| [feeds-survey.md](feeds-survey.md) | other clients' lanes in our atoms; what we lack; presets |

## Run, test, lint

```sh
python3 -m fedtail                       # run from the checkout (needs PySide6 + requests)
python3 -m unittest discover -s tests -t .   # all tests; Qt ones skip without PySide6
QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_qt_smoke
xvfb-run -a python3 -m unittest tests.test_gtk_smoke   # the GTK window (python3-gi gir1.2-gtk-4.0)
ruff check .                             # line length 100
python3 tools/docs_build.py              # after any change to docs/src/ or the example configs
python3 tools/selfcheck.py --quick       # walks through every interface, 5 minutes
```

Debian 13 packages: `python3-pyside6.qtwidgets python3-pyside6.qtdbus python3-requests`;
at run time also `qt6-image-formats-plugins` (webp/avif pictures) and `libnotify-bin`
(notifications). Elsewhere with Python ≥ 3.11: `pip install requests PySide6-Essentials`.

## The rules, in short

The full list is [AGENTS.md](../../../AGENTS.md) (one page, in English).

* The core never imports a toolkit; frontends talk to it through futures and events only.
* Every behaviour is a config flag: a new option goes into `config.DEFAULTS` and both example
  configs, with its explanation in each language.
* Every interface string goes to both `ru` and `en`.
* The developer docs come in both languages, `docs/ru/dev/` and `docs/en/dev/`: change one, change
  the other in the same commit (a test compares their skeletons). The CHANGELOG is English only.
* Every fix comes with a test; the CHANGELOG and the feature list keep up with the code.
* The token is never logged and never sent to other servers.
* Comments and commit messages in English.
