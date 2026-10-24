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
  Works on a Pixel 8 against GoToSocial — but there the sign-in page took only a password
  typed by hand: a saved (autofilled) or pasted one was refused (cause unknown yet; in the
  help's "If it breaks").
* **The overview of lanes** is home (`Hub.kt`, `bridge.hub()`): every lane by kind — for
  you (Direct, Replies, Mentions, Requests, Activity), reading (Subscriptions, Home, Bots),
  lists — with its count and its first unread post ("who: the first words"); lanes without
  counts (Federated, Local, tag lanes, Bookmarks, My posts) are chips to browse. "Read in
  a row" opens the first lane with news, yours first.
* **A lane** (`Lane.kt`): the cards of the web interface's JSON layer
  (`frontends/web/server.py`, class `Web`) — the very cards, "new below" divider and order
  the windows and the browser page use. It opens on its first unread post; what stood
  whole on screen when scrolling stopped is marked read (and goes into sync's journal).
  Under the title, the other lanes with news as chips; a tap on the title — the switcher
  (search, the counted lanes as tiles, the browsed ones); at the end of the lane, "read —
  next: Mentions · 3", and a swipe to the left goes there. Pull down or ⟳ asks the server.
* **Pictures** (Coil): avatars, previews (one wide by its proportions, more two per row),
  sensitive ones blurred until tapped (`feed.sensitive_media`), a link's card; a tap opens
  the viewer — pinch to zoom, ‹ ›, the description below. Video and sound open in the
  browser for now. Fetched straight from their servers, never with the account's token.
* **Point's command line** (`ui.command_line`): off on the phone — the app writes
  `command_line = false` into the config once (`bridge.PHONE_DEFAULTS`); set it to true
  and the lane gets the line at the bottom ("#abc text" answers, "#abc" opens…, what Enter
  will do said above it), a tap on a card's #abc puts it there.
* **Live**: while the app is on screen the core polls as on the desktop, and the screen
  waits on `bridge.wait()` for anything that changed; out of sight polling pauses.
* **Demo** (dev builds): `adb shell am start -n online.dmesg.fedtail.dev/online.dmesg.fedtail.MainActivity --ez demo true`
  — the made-up world of fedtail's screenshots (`tools/showcase.py`), in a profile of its own.
* **A thread**: a tap on a card opens its thread from the root, depth as an indent (up to
  six levels), each comment with its /N, standing on the post tapped.
* **Writing**: ✎ for a new post, 💬 on a card for a reply; who sees it as chips (a reply
  left alone keeps its parent's — the core decides, as on the desktop). ☆ likes.
* **Settings** (`Settings.kt`, `bridge.settings()`): the desktop's settings window as a
  page — the same model (`frontends/common/settings.py`: chapters, names, explanations,
  choices with what each means, ticks for lanes), only the options the phone heeds
  (`bridge.NOT_ON_PHONE`, `ONLY_ON_PHONE`); a change is that one line of config.toml
  (`core/config_edit.py`), the core made anew once the page is left. "As a file" — the
  file itself, edited in the app, checked before it is written.
* **Tiles**: which lanes and in which order — "change" over them (↑ ↓ ✕, ＋); the core
  keeps them (`pinned_tiles`), sync carries them to the other devices (`sync.tiles`).
* **Sync**: status, a round now, logging in to the sync server (its page shows a code to
  paste), showing this device's key and taking another device's.
* The look is the mockups' variant A ("calm": `Theme.kt`), light and dark by the
  phone's setting; fedtail's other themes (terminal, Point, Juick) come later.

Dev builds are signed with `dev.keystore` (in the repository on purpose: it signs only
`online.dmesg.fedtail.dev`), so each one installs over the last.

## Building

CI builds the dev APK on every push to the `android` branch (`.github/workflows/android.yml`;
the desktop's CI leaves this branch alone) and attaches it to the run as an artifact. Then
it starts the APK on an emulator and photographs it (`.github/android_shots.sh`): the login
screen, the demo world's overview of lanes, its Home lane and a thread, with Python's and Android's log — as an artifact and
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
