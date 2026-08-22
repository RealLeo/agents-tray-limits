#!/usr/bin/env bash
set -euo pipefail

UUID='agents-tray-limits@realleo'
OLD_UUID='chatgpt-usage@realleo'
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
EXTENSIONS_DIR="${HOME}/.local/share/gnome-shell/extensions"
TARGET="${EXTENSIONS_DIR}/${UUID}"
OLD_TARGET="${EXTENSIONS_DIR}/${OLD_UUID}"
ARCHIVE="${1:-}"

for command_name in gnome-extensions python3 unzip; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Error: required command '$command_name' was not found." >&2
    exit 1
  fi
done

if command -v gnome-shell >/dev/null 2>&1; then
  version="$(gnome-shell --version 2>/dev/null || true)"
  major="$(printf '%s' "$version" | grep -oE '[0-9]+' | head -n1 || true)"
  if [[ -n "$major" && "$major" -lt 45 ]]; then
    echo "Error: GNOME Shell 45 or newer is required; detected: ${version}." >&2
    exit 1
  fi
fi

if [[ -d "$OLD_TARGET" ]] || gnome-extensions info "$OLD_UUID" >/dev/null 2>&1; then
  echo "Warning: the old $OLD_UUID extension is installed." >&2
  echo 'Disable or remove it manually to avoid duplicate panel indicators.' >&2
fi

if [[ -z "$ARCHIVE" ]]; then
  make -C "$SCRIPT_DIR" pack
  ARCHIVE="${SCRIPT_DIR}/dist/${UUID}.zip"
elif [[ "$ARCHIVE" != /* ]]; then
  ARCHIVE="${SCRIPT_DIR}/${ARCHIVE}"
fi

if [[ ! -f "$ARCHIVE" ]]; then
  echo "Error: release archive not found: $ARCHIVE" >&2
  exit 1
fi

python3 "$SCRIPT_DIR/tools/stage_release.py" --verify "$ARCHIVE"

TEMP_DIR="$(mktemp -d)"
trap 'rm -rf -- "$TEMP_DIR"' EXIT
unzip -q "$ARCHIVE" -d "$TEMP_DIR"

archive_uuid="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["uuid"])' "$TEMP_DIR/metadata.json")"
if [[ "$archive_uuid" != "$UUID" ]]; then
  echo "Error: archive UUID is '$archive_uuid', expected '$UUID'." >&2
  exit 1
fi

mkdir -p "$EXTENSIONS_DIR"
rm -rf -- "$TARGET"
mkdir -p "$TARGET"
cp -a -- "$TEMP_DIR"/. "$TARGET"/
chmod 0755 "$TARGET/bin/agents-tray-limits-helper.py"

if ! gnome-extensions enable "$UUID" 2>/dev/null; then
  echo
  echo 'The extension was installed, but the current GNOME Shell has not loaded the new UUID yet.'
  echo 'Log out of Ubuntu and sign in again, then run:'
  echo "  gnome-extensions enable $UUID"
else
  echo "Extension $UUID was installed and enabled."
fi

if ! command -v codex >/dev/null 2>&1; then
  echo
  echo 'Codex CLI was not found in PATH.'
  echo 'Install it using the official installer, then sign in with ChatGPT:'
  echo '  curl -fsSL https://chatgpt.com/codex/install.sh | sh'
  echo '  codex'
fi
