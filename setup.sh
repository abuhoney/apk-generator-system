#!/usr/bin/env bash
# setup.sh — Detect Android SDK + JDK paths and write sdk_config/paths.json.
# Safe to run on any host — skips detection if tools aren't installed.
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p sdk_config

detect() {
  local name="$1"; shift
  local cmd="$1"; shift
  local paths=("$@")
  for p in "${paths[@]}"; do
    if [ -x "$p" ]; then
      echo "$p"
      return 0
    fi
  done
  # Try PATH
  if command -v "$cmd" >/dev/null 2>&1; then
    command -v "$cmd"
    return 0
  fi
  echo ""
  return 1
}

AAPT2=$(detect aapt2 aapt2 \
  "$ANDROID_HOME/build-tools/34.0.0/aapt2" \
  "$ANDROID_SDK_ROOT/build-tools/34.0.0/aapt2" \
  "/opt/android-sdk/build-tools/34.0.0/aapt2" || true)

JAVAC=$(detect javac javac \
  "/usr/lib/jvm/java-17-openjdk/bin/javac" \
  "/usr/lib/jvm/java-11-openjdk/bin/javac" \
  "/opt/java/bin/javac" || true)

D8=$(detect d8 d8 \
  "$ANDROID_HOME/build-tools/34.0.0/d8" \
  "$ANDROID_SDK_ROOT/build-tools/34.0.0/d8" \
  "/opt/android-sdk/build-tools/34.0.0/d8" || true)

ZIPALIGN=$(detect zipalign zipalign \
  "$ANDROID_HOME/build-tools/34.0.0/zipalign" \
  "$ANDROID_SDK_ROOT/build-tools/34.0.0/zipalign" \
  "/opt/android-sdk/build-tools/34.0.0/zipalign" || true)

APKSIGNER=$(detect apksigner apksigner \
  "$ANDROID_HOME/build-tools/34.0.0/apksigner" \
  "$ANDROID_SDK_ROOT/build-tools/34.0.0/apksigner" \
  "/opt/android-sdk/build-tools/34.0.0/apksigner" || true)

KEYTOOL=$(detect keytool keytool \
  "/usr/lib/jvm/java-17-openjdk/bin/keytool" \
  "/usr/lib/jvm/java-11-openjdk/bin/keytool" \
  "/opt/java/bin/keytool" || true)

SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-/opt/android-sdk}}"

cat > sdk_config/paths.json <<EOF
{
  "android_sdk_root": "$SDK_ROOT",
  "java_home": "${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk}",
  "aapt2": "$AAPT2",
  "javac": "$JAVAC",
  "d8": "$D8",
  "zipalign": "$ZIPALIGN",
  "apksigner": "$APKSIGNER",
  "keytool": "$KEYTOOL"
}
EOF

echo "Wrote sdk_config/paths.json:"
cat sdk_config/paths.json

if [ -z "$AAPT2" ] || [ -z "$JAVAC" ]; then
  echo ""
  echo "⚠ Android SDK / JDK not fully detected."
  echo "  The backend will still run — APK builds will fall back to 'webapk' mode."
  echo "  Install Android SDK + JDK 17 to enable full Gradle builds."
fi
