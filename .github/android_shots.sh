#!/usr/bin/env bash
# The dev APK on CI's emulator: installed, started twice, photographed.
#   1-login.png  — a fresh start, no account: the login screen
#   2-demo.png   — the demo world (the one every fedtail screenshot shows), the Home lane
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
shot 2-demo 30

adb logcat -d -v time python.stdout:V python.stderr:V AndroidRuntime:E fedtail:V '*:S' \
    > "$OUT/logcat.txt" || true
ls -la "$OUT"
