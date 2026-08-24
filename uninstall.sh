#!/usr/bin/env bash
set -euo pipefail

UUID='agents-tray-limits@realleo'
TARGET="${HOME}/.local/share/gnome-shell/extensions/${UUID}"
SCHEMA='org.gnome.shell.extensions.agents-tray-limits'

if [[ -x "${TARGET}/bin/agents-tray-limits-helper.py" && -f "${TARGET}/schemas/gschemas.compiled" ]]; then
  profiles_raw="$(GSETTINGS_SCHEMA_DIR="${TARGET}/schemas" gsettings get "${SCHEMA}" profiles-json 2>/dev/null || true)"
  if [[ -n "$profiles_raw" ]]; then
    while IFS= read -r -d '' profile_id && IFS= read -r -d '' config_dir; do
      if ! /usr/bin/python3 "${TARGET}/bin/agents-tray-limits-helper.py" \
        --provider claude \
        --profile-id "$profile_id" \
        --config-dir "$config_dir" \
        --restore-claude-monitor >/dev/null; then
        echo "Warning: Claude statusLine for profile '$profile_id' was not restored automatically." >&2
        echo "Run its agents-tray-limits/statusline.py --restore command manually after resolving conflicts." >&2
      fi
    done < <(/usr/bin/python3 -c '
import ast, json, sys
try:
    raw = ast.literal_eval(sys.argv[1])
    profiles = json.loads(raw).get("profiles", [])
except Exception:
    profiles = []
for profile in profiles:
    if profile.get("provider") == "claude":
        sys.stdout.buffer.write(str(profile.get("id", "")).encode() + b"\0")
        sys.stdout.buffer.write(str(profile.get("configDir", "")).encode() + b"\0")
' "$profiles_raw")
  fi
fi

gnome-extensions disable "$UUID" 2>/dev/null || true
rm -rf -- "$TARGET"
echo "Extension $UUID was removed. In a Wayland session, log out and sign in again if necessary."
