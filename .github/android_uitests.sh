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
python3 .github/android_junit.py android/app/build/outputs/androidTest-results/connected \
    shots/uitests.txt || true
tail -40 shots/uitests.log
exit $rc
