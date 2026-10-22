# fedtail for Android

The phone app: native screens (Kotlin, Jetpack Compose, Material 3) over the very same
Python core the desktop runs, put inside the APK by [Chaquopy](https://chaquo.com/chaquopy/).
The plan, the reasons and the options weighed are in the porting plan; in short:

```
Compose screens (Kotlin)  ──►  Core.kt  ──►  fedtail_android/bridge.py  ──►  fedtail/ (the core)
                                JSON in, JSON out, never on the main thread
```

* The core is **not** copied into this folder: the build's `copyFedtail` task takes the
  repository's `fedtail/` package (without the Qt, GTK, terminal and web interfaces) every
  time, so the phone runs the core of the same commit as the desktop. The version comes
  from `fedtail/__init__.py`, written into `_build.py` (no git on a phone).
* `bridge.py` is the one door from Kotlin: module functions, plain values. fedtail's paths
  follow XDG, so the app's private folders become `XDG_CONFIG_HOME` / `XDG_DATA_HOME` /
  `XDG_CACHE_HOME` — the core needs no Android branch for where its files live.
* The dev build is `online.dmesg.fedtail.dev` and stands next to a released one.
* `allowBackup` is off: the token and the read marks never go into a cloud backup.

## Where it stands

* **Logging in**: the server's page opens in the browser; after "allow" the server sends
  it back to `fedtail://oauth?code=…`, which this app catches (`MainActivity`, singleTask).
  A server that won't take that address gets the desktop's way: the code shown, pasted.
* **Lanes**: the drawer lists them with unread counts; a lane's cards come from the web
  interface's JSON layer (`frontends/web/server.py`, class `Web`) — the very cards, "new
  below" divider and order the windows and the browser page use. A lane opens on its first
  unread post; what stood whole on screen when scrolling stopped is marked read (and goes
  into sync's journal like any read mark). Pull down or ⟳ asks the server at once.
* **Live**: while the app is on screen the core polls as on the desktop, and the screen
  waits on `bridge.wait()` for anything that changed; out of sight polling pauses.
* **Demo** (dev builds): `adb shell am start -n online.dmesg.fedtail.dev/online.dmesg.fedtail.MainActivity --ez demo true`
  — the made-up world of fedtail's screenshots (`tools/showcase.py`), in a profile of its own.
* Plain Material 3 for now; the look (fedtail's themes, the card, threads as trees) is
  designed next, from mockups.

Dev builds are signed with `dev.keystore` (in the repository on purpose: it signs only
`online.dmesg.fedtail.dev`), so each one installs over the last.

## Building

CI builds the dev APK on every push to the `android` branch (`.github/workflows/android.yml`;
the desktop's CI leaves this branch alone) and attaches it to the run as an artifact. Then
it starts the APK on an emulator and photographs it (`.github/android_shots.sh`): the login
screen and the demo world's Home lane, with Python's and Android's log — as an artifact and
in the `android-shots` branch (one commit, rewritten by every run). A failed build says
why in annotations (`.github/android_why.py`).

By hand: JDK 17, the Android SDK (`ANDROID_HOME`), Python 3.12 on PATH (Chaquopy builds
with the same version it ships), then

```sh
cd android
./gradlew assembleDebug        # → app/build/outputs/apk/debug/
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

`tests/test_android_bridge.py` checks the Python door on any desktop Python, no phone needed.
