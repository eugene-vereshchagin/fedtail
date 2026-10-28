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
| `windows-build` | a push to `main` | `fedtail.exe` as one file (PyInstaller, `packaging/build.py`), started once; the installer `fedtail-setup.exe` (Inno Setup, `packaging/windows/fedtail.iss`); both signed when the code-signing certificate is there (secrets `WINDOWS_CERT_PFX` — the .pfx in base64 — and `WINDOWS_CERT_PASSWORD`), unsigned otherwise |
| `linux-build` | a push to `main` | `fedtail` for Linux as one file, built on Debian 12 so it runs on older systems too |
| `deb` | every push and PR | the `.deb` for Debian 13 (`packaging/deb.py`), installed with apt and started |
| `apk` | a push to `main` | only when `fedtail/__init__.py` holds an untagged release version: the Android APK built and signed with the release key (secrets `ANDROID_KEYSTORE`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`; android/README.md, "Releases"); without the key — a warning, the release goes without it |
| `screenshots` | by hand (Actions → CI → Run workflow), `main` only | every theme rendered with made-up data, the PNGs force-pushed to the `screenshots` branch |
| `release` | a push to `main`, once everything above is green | if `fedtail/__init__.py` holds a release version that has no tag yet: tags the commit `vX.Y.Z`, publishes a GitHub release with the CHANGELOG section as notes and the files — Windows (the .exe and the installer), Linux, Debian and Android (when signed) |
| `apt` | after `release` published one | the release's `.deb` into the apt repository: the `apt` branch (GitHub Pages serves it), its indexes made anew and signed with the repository's key (secret `APT_GPG_KEY`, an armored private key without a passphrase; `packaging/apt_repo.py`); without the key — a warning, nothing published; by hand for a release already out — `apt.yml` (Actions → apt → Run workflow, the version) |
| `site` | after `release` published one (and after `apt`) | `site.yml` for the new version: the site rebuilt and waited for until it shows that release (below) |

`android.yml` builds the phone's dev APK (its own id, `online.dmesg.fedtail.dev`, the dev key) on a push to `main`
touching `android/` or the core, starts it on an emulator — screenshots and the UI tests (`android/app/src/androidTest`),
pushed to the `android-shots` branch — and attaches the APK to the run (android/README.md).

When a test fails, `.github/annotate.py` turns the failures into annotations on the run (job logs
can't always be downloaded).

## `site.yml`: the website

| job | when | what it does |
|---|---|---|
| `rebuild` | every night at 05:37 Tbilisi time, after a release (ci.yml's `site`) and by hand | calls the site's deploy hook (secret `SITE_DEPLOY_HOOK` or `DOCS_UPDATE`), so "coming next" follows `main`; then waits up to 20 minutes for the live site's `/version.txt` to name the release (the given one, else the latest tag) and fails otherwise — the site's build refused something and Cloudflare kept the old version; the run's summary names the Cloudflare build to look at |

The site lives in a repo of its own and builds itself from this one: the docs of the latest release,
the developer docs from `main`, the release files' links. A release rebuilds it at once. Its build
checks itself (`tools/check_site.py` there): a broken page fails the build and the old site stays
online, which `rebuild` turns into a red run. The docs taken from here only warn there: their
RU/EN twins are checked here, by the tests.

## Making a release

1. The `## X.Y.Z — in progress` section of `CHANGELOG.md` has everything user-visible since the last release.
2. In one commit: `fedtail/__init__.py` says `X.Y.Z`, the CHANGELOG heading becomes `## X.Y.Z — <date>`,
   the features that came in it have `since = "X.Y.Z"` in `docs/src/features/`, `python3 tools/docs_build.py`.
3. Push. When CI is green, the `release` job tags and publishes; the site follows.
4. Right after: bump to `X.Y+1.0.dev0` with a new `## X.Y+1.0 — in progress` section.

Releases are made only on the author's word.
