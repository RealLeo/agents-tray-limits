#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MACOS_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd -- "${MACOS_ROOT}/../.." && pwd)"
BUILD_ROOT="${REPO_ROOT}/build/macos"
DERIVED_DATA="${BUILD_ROOT}/DerivedData"
ARCHIVE="${BUILD_ROOT}/AgentsTrayMacApp.xcarchive"
APP="${BUILD_ROOT}/Agents Tray Limits.app"
CONTENTS="${APP}/Contents"
DIST="${REPO_ROOT}/dist"
ZIP="${DIST}/Agents-Tray-Limits-macOS.zip"

if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Error: macOS is required to build, sign, and notarize the application.' >&2
  exit 1
fi
for command_name in xcodebuild codesign ditto xcrun lipo shasum; do
  command -v "$command_name" >/dev/null || { echo "Error: required command '$command_name' was not found." >&2; exit 1; }
done
: "${DEVELOPER_ID_APPLICATION:?Set DEVELOPER_ID_APPLICATION to the Developer ID Application identity.}"
: "${NOTARY_PROFILE:?Set NOTARY_PROFILE to a notarytool keychain profile.}"

xcodebuild \
  -scheme AgentsTrayCore \
  -configuration Release \
  -destination 'platform=macOS' \
  -derivedDataPath "$DERIVED_DATA" \
  CODE_SIGNING_ALLOWED=NO \
  test
rm -rf -- "$ARCHIVE"
xcodebuild \
  -scheme AgentsTrayMacApp \
  -configuration Release \
  -destination 'generic/platform=macOS' \
  -derivedDataPath "$DERIVED_DATA" \
  -archivePath "$ARCHIVE" \
  ARCHS='arm64 x86_64' \
  ONLY_ACTIVE_ARCH=NO \
  CODE_SIGNING_ALLOWED=NO \
  archive

xcodebuild \
  -scheme AgentsTrayMacApp \
  -configuration Release \
  -destination 'generic/platform=macOS' \
  -derivedDataPath "$DERIVED_DATA" \
  ARCHS='arm64 x86_64' \
  ONLY_ACTIVE_ARCH=NO \
  CODE_SIGNING_ALLOWED=NO \
  build
xcodebuild \
  -scheme AgentsTrayCollector \
  -configuration Release \
  -destination 'generic/platform=macOS' \
  -derivedDataPath "$DERIVED_DATA" \
  ARCHS='arm64 x86_64' \
  ONLY_ACTIVE_ARCH=NO \
  CODE_SIGNING_ALLOWED=NO \
  build

rm -rf -- "$APP"
mkdir -p "$CONTENTS/MacOS" "$CONTENTS/Helpers" "$CONTENTS/Resources"
cp -f "${DERIVED_DATA}/Build/Products/Release/AgentsTrayMacApp" "$CONTENTS/MacOS/AgentsTrayMacApp"
cp -f "${DERIVED_DATA}/Build/Products/Release/AgentsTrayCollector" "$CONTENTS/Helpers/AgentsTrayCollector"
cp -f "${MACOS_ROOT}/Info.plist" "$CONTENTS/Info.plist"
cp -a "${REPO_ROOT}/shared/locales" "$CONTENTS/Resources/locales"
cp -a "${REPO_ROOT}/shared/themes" "$CONTENTS/Resources/themes"
cp -f "${REPO_ROOT}/LICENSE" "$CONTENTS/Resources/LICENSE"
cp -f "${REPO_ROOT}/NOTICE.md" "$CONTENTS/Resources/NOTICE.md"
chmod 0755 "$CONTENTS/MacOS/AgentsTrayMacApp" "$CONTENTS/Helpers/AgentsTrayCollector"

lipo -verify_arch arm64 x86_64 "$CONTENTS/MacOS/AgentsTrayMacApp"
lipo -verify_arch arm64 x86_64 "$CONTENTS/Helpers/AgentsTrayCollector"
codesign --force --timestamp --options runtime --sign "$DEVELOPER_ID_APPLICATION" "$CONTENTS/Helpers/AgentsTrayCollector"
codesign --force --timestamp --options runtime --entitlements "${MACOS_ROOT}/AgentsTrayLimits.entitlements" --sign "$DEVELOPER_ID_APPLICATION" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

mkdir -p "$DIST"
TEMP_ZIP="${BUILD_ROOT}/notary-upload.zip"
rm -f -- "$TEMP_ZIP" "$ZIP" "${ZIP}.sha256"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$TEMP_ZIP"
xcrun notarytool submit "$TEMP_ZIP" --keychain-profile "$NOTARY_PROFILE" --wait
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
shasum -a 256 "$ZIP" > "${ZIP}.sha256"
shasum -a 256 -c "${ZIP}.sha256"
spctl --assess --type execute --verbose=2 "$APP"
echo "Created ${ZIP}"
