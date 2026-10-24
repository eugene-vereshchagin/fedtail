# CI and releases

Everything that runs on GitHub Actions, and how a release is made. A test checks that every job
of `.github/workflows/ci.yml` and `site.yml` is in these tables, in both languages.

## `ci.yml`: on every push

A push to `main` runs all of it: about an hour with the builds, so push in batches, not after every small change.
A commit with `[skip ci]` in its message runs nothing.

| job | when | what it does |
|---|---|---|
| `lint` | every push and PR | `ruff check .` (line length 100) |
| `security` | every push and PR | the sync code faces the internet: `bandit` and ruff's bandit rules over `syncserver/` and `fedtail/core/sync`, its security tests, on Python 3.11 and 3.13 |
| `audit` | every push and PR | known vulnerabilities in what fedtail runs on (`pip-audit`): warnings only, a new CVE upstream never holds a release |
| `test` | every push and PR | all the tests on Python 3.11, 3.12 and 3.13 with Qt from pip, offscreen; then fedtail installed as a package and started |
| `debian` | every push and PR | all the tests on Debian 13 with Qt and GTK 4 from apt, under Xvfb — the real target |
| `windows` | every push and PR | all the tests on Windows with Qt from pip (docs/en/dev/windows.md uses the same packages and command, a test checks) |
| `windows-build` | a push to `main` | `fedtail.exe` as one file (PyInstaller, `packaging/build.py`), started once |
| `linux-build` | a push to `main` | `fedtail` for Linux as one file, built on Debian 12 so it runs on older systems too |
| `deb` | every push and PR | the `.deb` for Debian 13 (`packaging/deb.py`), installed with apt and started |
| `screenshots` | by hand (Actions → CI → Run workflow), `main` only | every theme rendered with made-up data, the PNGs force-pushed to the `screenshots` branch |
| `release` | a push to `main`, once everything above is green | if `fedtail/__init__.py` holds a release version that has no tag yet: tags the commit `vX.Y.Z`, publishes a GitHub release with the CHANGELOG section as notes and the three files, and pokes the site's deploy hook |

When a test fails, `.github/annotate.py` turns the failures into annotations on the run (job logs
can't always be downloaded).

## `site.yml`: the website

| job | when | what it does |
|---|---|---|
| `rebuild` | every night at 05:37 Tbilisi time and by hand | calls the site's deploy hook (secret `SITE_DEPLOY_HOOK` or `DOCS_UPDATE`), so "coming next" follows `main` |

The site lives in a repo of its own and builds itself from this one: the docs of the latest release,
the developer docs from `main`, the release files' links. A release rebuilds it at once.

## Making a release

1. The `## X.Y.Z — in progress` section of `CHANGELOG.md` has everything user-visible since the last release.
2. In one commit: `fedtail/__init__.py` says `X.Y.Z`, the CHANGELOG heading becomes `## X.Y.Z — <date>`,
   the features that came in it have `since = "X.Y.Z"` in `docs/src/features/`, `python3 tools/docs_build.py`.
3. Push. When CI is green, the `release` job tags and publishes; the site follows.
4. Right after: bump to `X.Y+1.0.dev0` with a new `## X.Y+1.0 — in progress` section.

Releases are made only on the author's word.
