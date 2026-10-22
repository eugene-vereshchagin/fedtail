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

Step one: the app starts Python and the core, opens the profile's database and shows
what the core says about itself (versions, TLS, the database, profiles, whether sync's
`cryptography` is there, how long the start took). That proves the chain on a phone.
Next: logging in, the lanes, a lane's posts, a thread as a tree, marking read — each a
call in `bridge.py` over the core's `View`, and a screen.

## Building

CI builds the dev APK on every push to the `android` branch (`.github/workflows/android.yml`;
the desktop's CI leaves this branch alone) and attaches it to the run as an artifact.

By hand: JDK 17, the Android SDK (`ANDROID_HOME`), Python 3.12 on PATH (Chaquopy builds
with the same version it ships), then

```sh
cd android
./gradlew assembleDebug        # → app/build/outputs/apk/debug/
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

`tests/test_android_bridge.py` checks the Python door on any desktop Python, no phone needed.
