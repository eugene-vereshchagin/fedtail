#!/usr/bin/env bash
# The UI tests (android/app/src/androidTest) on CI's emulator, after the screenshots:
# Compose tests over the real app in its demo world. Each failure becomes an annotation
# (.github/android_junit.py) and a line in shots/uitests.txt (the android-shots branch).
set -u
mkdir -p shots
cd android
./gradlew --no-daemon connectedDebugAndroidTest > ../shots/uitests.log 2>&1
rc=$?
cd ..
# a failure: what the app said meanwhile (the core's Python logs there too) — for the
# card menu whose items didn't come on CI only (12.11)
if [ "$rc" != 0 ]; then adb logcat -d -t 4000 > shots/logcat.txt 2>&1 || true; fi
python3 .github/android_junit.py android/app/build/outputs/androidTest-results/connected \
    shots/uitests.txt || true
tail -40 shots/uitests.log
exit $rc
