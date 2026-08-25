from __future__ import annotations

import json
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from tools import stage_release


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_ROOT = REPO_ROOT / "shared"
UUID = "agents-tray-limits@realleo"
SCHEMA_ID = "org.gnome.shell.extensions.agents-tray-limits"


class ReleaseIdentityTests(unittest.TestCase):
    def test_metadata_and_runtime_names_use_public_identity(self) -> None:
        metadata = json.loads((ROOT / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["uuid"], UUID)
        self.assertEqual(metadata["name"], "Agents Tray Limits")
        self.assertEqual(metadata["version"], 18)
        self.assertEqual(metadata["settings-schema"], SCHEMA_ID)
        self.assertEqual(metadata["url"], "https://github.com/RealLeo/agents-tray-limits")

        self.assertTrue((ROOT / "bin" / "agents-tray-limits-helper.py").is_file())
        self.assertTrue((ROOT / "icons" / "agents-tray-limits-symbolic.svg").is_file())
        self.assertFalse((ROOT / "bin" / "chatgpt-usage-helper.py").exists())
        self.assertFalse((ROOT / "icons" / "chatgpt-usage-symbolic.svg").exists())

        runtime_paths = [
            "extension.js",
            "prefs.js",
            "i18n.js",
            "stylesheet.css",
            "themeLoader.js",
            "profileLogic.js",
            "metadata.json",
            "bin/agents-tray-limits-helper.py",
            "schemas/org.gnome.shell.extensions.agents-tray-limits.gschema.xml",
        ]
        old_markers = (
            "chatgpt-usage@realleo",
            "chatgpt-usage-helper.py",
            "org.gnome.shell.extensions.chatgpt-usage",
        )
        for relative in runtime_paths:
            source = (ROOT / relative).read_text(encoding="utf-8")
            for marker in old_markers:
                self.assertNotIn(marker, source, f"old identity in {relative}")

    def test_schema_defaults_and_language_choices(self) -> None:
        schema_path = (
            ROOT
            / "schemas"
            / "org.gnome.shell.extensions.agents-tray-limits.gschema.xml"
        )
        schema = ET.parse(schema_path).getroot().find("schema")
        self.assertIsNotNone(schema)
        self.assertEqual(schema.get("id"), SCHEMA_ID)
        self.assertEqual(schema.get("path"), "/org/gnome/shell/extensions/agents-tray-limits/")

        keys = {key.get("name"): key for key in schema.findall("key")}
        self.assertEqual(keys["theme-id"].findtext("default"), "'fallout-2'")
        self.assertEqual(keys["language"].findtext("default"), "'system'")
        self.assertEqual(keys["profiles-json"].findtext("default"), "''")
        self.assertEqual(keys["active-profile-id"].findtext("default"), "''")
        choices = [choice.get("value") for choice in keys["language"].findall("choices/choice")]
        self.assertEqual(choices, ["system", "en", "ru", "de", "fr", "zh-CN"])

    def test_every_helper_error_code_is_localized(self) -> None:
        helper_source = (
            ROOT / "bin" / "agents-tray-limits-helper.py"
        ).read_text(encoding="utf-8")
        error_codes = set(re.findall(
            r"HelperError\(\s*[\"']([^\"']+)",
            helper_source,
        ))
        error_codes.update(re.findall(
            r"[\"']errorCode[\"']\s*:\s*[\"']([^\"']+)",
            helper_source,
        ))
        error_codes.update(re.findall(
            r"_read_json_object\(\s*[^,]+,\s*[\"']([^\"']+)",
            helper_source,
        ))
        self.assertEqual(error_codes, {
            "app_server_error",
            "app_server_start_failed",
            "app_server_stopped",
            "codex_not_found",
            "codex_too_old",
            "internal_error",
            "no_rate_limits",
            "not_logged_in",
            "protocol_error",
            "timeout",
            "unsupported_auth",
            "invalid_profile",
            "invalid_profile_path",
            "claude_cache_missing",
            "claude_cache_invalid",
            "claude_limits_unavailable",
            "claude_limits_stale",
            "claude_settings_invalid",
            "claude_monitor_invalid",
            "claude_monitor_conflict",
        })

        for language in ("en", "ru", "de", "fr", "zh-CN"):
            catalog = json.loads(
                (SHARED_ROOT / "locales" / f"{language}.json").read_text(encoding="utf-8")
            )
            for code in error_codes:
                self.assertTrue(
                    catalog.get(f"errors.{code}"),
                    f"{language} is missing errors.{code}",
                )

    def test_curated_stage_contains_runtime_only(self) -> None:
        build_root = REPO_ROOT / "build" / "gnome"
        build_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build_root) as temporary_directory:
            stage = Path(temporary_directory) / "stage"
            stage_release.build(stage)
            names = {
                path.relative_to(stage).as_posix()
                for path in stage.rglob("*")
                if path.is_file()
            }

            self.assertIn("LICENSE", names)
            self.assertIn("NOTICE.md", names)
            self.assertIn("profileLogic.js", names)
            for locale in ("en", "ru", "de", "fr", "zh-CN"):
                self.assertIn(f"locales/{locale}.json", names)
            self.assertIn("themes/fallout-2/assets/ui/device-shell-v3.png", names)
            self.assertIn("themes/night-video-deck/theme.json", names)
            self.assertIn("themes/night-video-deck/theme.css", names)
            self.assertIn("themes/night-video-deck/assets/ui/device-shell.png", names)
            for status in ("good", "worried", "critical", "dead"):
                self.assertIn(f"themes/night-video-deck/assets/art/{status}.png", names)
                self.assertIn(f"themes/night-video-deck/assets/panel/{status}.png", names)
            self.assertFalse(any(name.startswith("themes/fallout-3/") for name in names))
            self.assertNotIn("README.md", names)
            self.assertFalse(any(name.startswith("tests/") for name in names))
            self.assertFalse(any(name.startswith("tools/") for name in names))
            self.assertFalse(any("art-source" in Path(name).parts for name in names))

            staged_ui = {
                Path(name).name
                for name in names
                if name.startswith("themes/fallout-2/assets/ui/")
            }
            self.assertEqual(
                staged_ui,
                {
                    "device-shell-v3.png",
                    "red-button-v4.png",
                    "red-button-pressed-v4.png",
                },
            )

    def test_uninstall_restores_claude_monitors_before_removal(self) -> None:
        source = (ROOT / "uninstall.sh").read_text(encoding="utf-8")
        restore = source.index("--restore-claude-monitor")
        removal = source.index('rm -rf -- "$TARGET"')
        self.assertLess(restore, removal)
        self.assertIn("profiles-json", source)
        self.assertIn("statusline.py --restore", source)


if __name__ == "__main__":
    unittest.main()
