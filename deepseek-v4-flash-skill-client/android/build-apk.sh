#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
TOOLS="$PWD/.android-tools"
export JAVA_HOME="$TOOLS/jdk/Contents/Home"
export ANDROID_HOME="$TOOLS/sdk"
export GRADLE_USER_HOME="$TOOLS/gradle-cache"
export PATH="$JAVA_HOME/bin:$PATH"
if [ ! -x "$JAVA_HOME/bin/java" ] || [ ! -x "$TOOLS/gradle-8.9/bin/gradle" ]; then
  echo '缺少本地 JDK 17 / Gradle 8.9，请先安装构建工具。' >&2
  exit 1
fi
"$TOOLS/gradle-8.9/bin/gradle" -p android --no-daemon assembleDebug
mkdir -p output/android
cp android/app/build/outputs/apk/debug/app-debug.apk output/android/qiyu-0.1.1-debug.apk
"$ANDROID_HOME/build-tools/34.0.0/apksigner" verify --verbose output/android/qiyu-0.1.1-debug.apk
