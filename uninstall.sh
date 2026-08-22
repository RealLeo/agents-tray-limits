#!/usr/bin/env bash
set -euo pipefail

UUID='agents-tray-limits@realleo'
TARGET="${HOME}/.local/share/gnome-shell/extensions/${UUID}"

gnome-extensions disable "$UUID" 2>/dev/null || true
rm -rf -- "$TARGET"
echo "Extension $UUID was removed. In a Wayland session, log out and sign in again if necessary."
