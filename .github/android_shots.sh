#!/usr/bin/env bash
# The dev APK on CI's emulator: installed, started twice, photographed.
#   1-login.png  — a fresh start, no account: the login screen
#   2-lanes.png  — the demo world (the one every fedtail screenshot shows): the overview
#   3-home.png   — its Home lane
#   4-thread.png — a thread of that world, as a tree
#   6-settings.png — the settings page (the config's options, each with its explanation)
#   7-profile.png — someone's profile (Кот): the header, the buttons, the posts
#   8-place.png  — a place of the windows' ≡ menu (the lists), as the phone draws it
#   9-compose.png — the editor: words, a warning, pictures, a poll, the language
#   5-wide.png   — a tablet's screen (wm size): the overview, the lane and a thread side by side
#   logcat.txt   — what Python and Android said meanwhile (a crash is there)
# Run by reactivecircus/android-emulator-runner (android.yml) from the repository's root.
set -u
APP=online.dmesg.fedtail.dev
ACT=$APP/online.dmesg.fedtail.MainActivity
OUT=shots
mkdir -p "$OUT"
APK=$(ls android/app/build/outputs/apk/debug/*.apk | head -1)
adb install -r "$APK"
adb logcat -c || true

shot() {  # name, seconds to let it settle
    sleep "$2"
    adb exec-out screencap -p > "$OUT/$1.png"
}

adb shell am start -W -n "$ACT"
shot 1-login 25
adb shell am force-stop "$APP"
adb shell am start -W -n "$ACT" --ez demo true
shot 2-lanes 30
adb shell am force-stop "$APP"
adb shell am start -W -n "$ACT" --ez demo true --es lane home
shot 3-home 25
adb shell am force-stop "$APP"
adb shell am start -W -n "$ACT" --ez demo true --es thread 101
shot 4-thread 25
adb shell am force-stop "$APP"
adb shell am start -W -n "$ACT" --ez demo true --ez settings true
shot 6-settings 25
adb shell am force-stop "$APP"
adb shell am start -W -n "$ACT" --ez demo true --es profile K
shot 7-profile 25
adb shell am force-stop "$APP"
adb shell am start -W -n "$ACT" --ez demo true --es page lists
shot 8-place 25
adb shell am force-stop "$APP"
adb shell am start -W -n "$ACT" --ez demo true --ez compose true
shot 9-compose 25
adb shell am force-stop "$APP"
adb shell wm size 2560x1600
adb shell wm density 320
adb shell am start -W -n "$ACT" --ez demo true --es lane home --es thread 101
shot 5-wide 25
adb shell wm size reset
adb shell wm density reset

# everything the app said (Python's stdout/stderr come as python.* tags), and crashes
adb logcat -d -v time > "$OUT/logcat-all.txt" || true
grep -E "python\.|AndroidRuntime|chaquopy|fedtail" "$OUT/logcat-all.txt" > "$OUT/logcat.txt" || true
rm -f "$OUT/logcat-all.txt"
ls -la "$OUT"
