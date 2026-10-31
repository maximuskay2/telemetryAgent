#!/usr/bin/env bash
# Build the Android APK users download from How to / GitHub releases.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root/apps/mobile"
flutter pub get
flutter build apk --release
mkdir -p "$root/apps/web/public/downloads"
cp -f build/app/outputs/flutter-apk/app-release.apk \
  "$root/apps/web/public/downloads/telemetry-agent.apk"
echo "APK: $root/apps/web/public/downloads/telemetry-agent.apk"
echo "Publish: gh release upload <tag> that file --clobber"
