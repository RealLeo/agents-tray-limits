from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


EXTENSION_ROOT = Path(__file__).resolve().parents[1]
HELPER = EXTENSION_ROOT / "bin" / "agents-tray-limits-helper.py"
FAKE_CODEX = EXTENSION_ROOT / "tests" / "fake-codex"


class HelperTests(unittest.TestCase):
    def run_helper(
        self,
        scenario: str = "success",
        *,
        codex_binary: Path | None = FAKE_CODEX,
        environment: dict[str, str] | None = None,
        timeout: float = 8.0,
        provider: str = "codex",
        profile_id: str = "default-codex",
        config_dir: Path | None = None,
        extra_args: list[str] | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        child_environment = os.environ.copy()
        child_environment["FAKE_CODEX_SCENARIO"] = scenario
        if environment:
            child_environment.update(environment)

        command = [
            sys.executable,
            os.fspath(HELPER),
            "--timeout",
            "2",
            "--provider",
            provider,
            "--profile-id",
            profile_id,
        ]
        if config_dir is not None:
            command.extend(["--config-dir", os.fspath(config_dir)])
        if codex_binary is not None:
            command.extend(["--codex-bin", os.fspath(codex_binary)])
        if extra_args:
            command.extend(extra_args)

        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=child_environment,
        )
        self.assertTrue(completed.stdout.strip(), completed.stderr)
        return completed, json.loads(completed.stdout)

    def test_success(self) -> None:
        completed, payload = self.run_helper()
        self.assertEqual(completed.returncode, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["helperVersion"], "3.0.0")
        self.assertEqual(payload["rateLimits"]["rateLimits"]["limitId"], "codex")
        self.assertEqual(payload["usage"]["summary"]["lifetimeTokens"], 1_234_567)

    def test_default_codex_profile_does_not_inherit_codex_home(self) -> None:
        completed, payload = self.run_helper(
            environment={"CODEX_HOME": "/tmp/must-not-leak"},
        )
        self.assertEqual(completed.returncode, 0, payload)
        self.assertIsNone(payload["serverInfo"]["codexHome"])

    def test_logged_out(self) -> None:
        completed, payload = self.run_helper("logged-out")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["errorCode"], "not_logged_in")

    def test_api_key_auth(self) -> None:
        completed, payload = self.run_helper("api-key")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["errorCode"], "unsupported_auth")

    def test_old_codex(self) -> None:
        completed, payload = self.run_helper("old-codex")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["errorCode"], "codex_too_old")

    def test_usage_is_optional(self) -> None:
        completed, payload = self.run_helper("no-usage")
        self.assertEqual(completed.returncode, 0)
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["usage"])
        self.assertEqual(payload["usageError"]["code"], -32601)

    def test_timeout(self) -> None:
        completed, payload = self.run_helper("timeout")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["errorCode"], "timeout")

    def test_explicit_codex_home_and_file_store_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_dir = Path(temporary) / "codex-work"
            completed, payload = self.run_helper(
                config_dir=config_dir,
                profile_id="codex-work",
                environment={"FAKE_CODEX_EMAIL": "work@example.com"},
            )
            self.assertEqual(completed.returncode, 0, payload)
            self.assertEqual(payload["profileId"], "codex-work")
            self.assertEqual(payload["provider"], "codex")
            self.assertEqual(payload["account"]["email"], "work@example.com")
            server = payload["serverInfo"]
            self.assertEqual(server["codexHome"], os.fspath(config_dir))
            self.assertEqual(server["argv"][-1], "app-server")
            self.assertIn('cli_auth_credentials_store="file"', server["argv"])

            second_dir = Path(temporary) / "codex-personal"
            completed, second = self.run_helper(
                config_dir=second_dir,
                profile_id="codex-personal",
                environment={"FAKE_CODEX_EMAIL": "personal@example.com"},
            )
            self.assertEqual(completed.returncode, 0, second)
            self.assertEqual(second["account"]["email"], "personal@example.com")
            self.assertEqual(second["serverInfo"]["codexHome"], os.fspath(second_dir))
            self.assertNotEqual(server["codexHome"], second["serverInfo"]["codexHome"])

    def test_claude_cache_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "cache" / "agents-tray-limits" / "claude" / "claude-work.json"
            cache.parent.mkdir(parents=True)
            now = int(time.time())
            cache.write_text(json.dumps({
                "version": "2.1.200",
                "fetchedAt": now,
                "rate_limits": {
                    "five_hour": {"used_percentage": 25, "resets_at": now + 3600},
                    "seven_day": {"used_percentage": 60, "resets_at": now + 86400},
                },
            }), encoding="utf-8")
            completed, payload = self.run_helper(
                provider="claude",
                profile_id="claude-work",
                codex_binary=None,
                environment={"XDG_CACHE_HOME": os.fspath(root / "cache")},
            )
            self.assertEqual(completed.returncode, 0, payload)
            bucket = payload["rateLimits"]["rateLimits"]
            self.assertEqual(bucket["limitId"], "claude")
            self.assertEqual(bucket["primary"]["usedPercent"], 25)
            self.assertEqual(bucket["secondary"]["usedPercent"], 60)

    def test_claude_cache_missing_and_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = {"XDG_CACHE_HOME": os.fspath(root / "cache")}
            completed, payload = self.run_helper(
                provider="claude",
                profile_id="claude-personal",
                codex_binary=None,
                environment=environment,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(payload["errorCode"], "claude_cache_missing")

            cache = root / "cache" / "agents-tray-limits" / "claude" / "claude-personal.json"
            cache.parent.mkdir(parents=True)
            cache.write_text(json.dumps({
                "fetchedAt": int(time.time()) - 600,
                "rate_limits": {
                    "five_hour": {"used_percentage": 99, "resets_at": int(time.time()) - 1},
                },
            }), encoding="utf-8")
            completed, payload = self.run_helper(
                provider="claude",
                profile_id="claude-personal",
                codex_binary=None,
                environment=environment,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(payload["errorCode"], "claude_limits_stale")

    def test_claude_monitor_delegates_and_restores_statusline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_dir = root / "claude-work"
            config_dir.mkdir()
            original = {
                "type": "command",
                "command": "printf original-status",
                "padding": 2,
            }
            settings_path = config_dir / "settings.json"
            settings_path.write_text(json.dumps({
                "theme": "dark",
                "statusLine": original,
            }), encoding="utf-8")
            environment = {"XDG_CACHE_HOME": os.fspath(root / "cache")}
            completed, payload = self.run_helper(
                provider="claude",
                profile_id="claude-work",
                config_dir=config_dir,
                codex_binary=None,
                environment=environment,
                extra_args=["--install-claude-monitor"],
            )
            self.assertEqual(completed.returncode, 0, payload)
            self.assertEqual(payload["monitorState"], "installed")
            script = config_dir / "agents-tray-limits" / "statusline.py"
            backup = config_dir / "agents-tray-limits" / "statusline-backup.json"
            self.assertEqual(script.stat().st_mode & 0o777, 0o700)
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)

            now = int(time.time())
            status_input = json.dumps({
                "version": "2.1.200",
                "rate_limits": {
                    "five_hour": {
                        "used_percentage": 12,
                        "resets_at": now + 3600,
                        "status": "allowed",
                        "sensitive_future_field": "must-not-be-cached",
                    },
                    "seven_day": {"used_percentage": 34, "resets_at": now + 86400},
                    "overage": {"enabled": True},
                },
                "workspace": {"current_dir": "/private/project"},
            })
            delegated = subprocess.run(
                [sys.executable, os.fspath(script)],
                input=status_input,
                text=True,
                capture_output=True,
                check=False,
                env={**os.environ, **environment},
            )
            self.assertEqual(delegated.returncode, 0, delegated.stderr)
            self.assertEqual(delegated.stdout, "original-status")
            cache = root / "cache" / "agents-tray-limits" / "claude" / "claude-work.json"
            cached = json.loads(cache.read_text(encoding="utf-8"))
            self.assertEqual(cached, {
                "fetchedAt": cached["fetchedAt"],
                "rate_limits": {
                    "five_hour": {
                        "used_percentage": 12.0,
                        "resets_at": now + 3600,
                    },
                    "seven_day": {
                        "used_percentage": 34.0,
                        "resets_at": now + 86400,
                    },
                },
                "version": "2.1.200",
            })

            completed, payload = self.run_helper(
                provider="claude",
                profile_id="claude-work",
                config_dir=config_dir,
                codex_binary=None,
                environment=environment,
                extra_args=["--restore-claude-monitor"],
            )
            self.assertEqual(completed.returncode, 0, payload)
            restored = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(restored, {"theme": "dark", "statusLine": original})
            self.assertFalse(script.exists())

    def test_claude_monitor_is_idempotent_and_conflict_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_dir = Path(temporary) / "claude"
            environment = {"XDG_CACHE_HOME": os.fspath(Path(temporary) / "cache")}
            arguments = dict(
                provider="claude",
                profile_id="claude-profile",
                config_dir=config_dir,
                codex_binary=None,
                environment=environment,
                extra_args=["--install-claude-monitor"],
            )
            self.assertEqual(self.run_helper(**arguments)[0].returncode, 0)
            self.assertEqual(self.run_helper(**arguments)[0].returncode, 0)
            settings_path = config_dir / "settings.json"
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            settings["statusLine"]["padding"] = 9
            settings_path.write_text(json.dumps(settings), encoding="utf-8")
            completed, payload = self.run_helper(
                provider="claude",
                profile_id="claude-profile",
                config_dir=config_dir,
                codex_binary=None,
                environment=environment,
                extra_args=["--restore-claude-monitor"],
            )
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(payload["errorCode"], "claude_monitor_conflict")
            current = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(current["statusLine"]["padding"], 9)

    def test_claude_monitor_without_original_can_restore_itself(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_dir = root / "claude"
            environment = {"XDG_CACHE_HOME": os.fspath(root / "cache")}
            completed, payload = self.run_helper(
                provider="claude",
                profile_id="claude-personal",
                config_dir=config_dir,
                codex_binary=None,
                environment=environment,
                extra_args=["--install-claude-monitor"],
            )
            self.assertEqual(completed.returncode, 0, payload)
            managed = config_dir / "agents-tray-limits"
            script = managed / "statusline.py"
            backup = managed / "statusline-backup.json"
            lock = managed / "statusline.lock"
            self.assertEqual(managed.stat().st_mode & 0o777, 0o700)
            self.assertEqual(script.stat().st_mode & 0o777, 0o700)
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
            self.assertEqual(lock.stat().st_mode & 0o777, 0o600)

            delegated = subprocess.run(
                [sys.executable, os.fspath(script)],
                input=json.dumps({"version": "2.1", "rate_limits": None}),
                text=True,
                capture_output=True,
                check=False,
                env={**os.environ, **environment},
            )
            self.assertEqual(delegated.returncode, 0, delegated.stderr)
            cache = root / "cache" / "agents-tray-limits" / "claude" / "claude-personal.json"
            self.assertEqual(cache.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(cache.read_text(encoding="utf-8"))["rate_limits"], {})
            completed, payload = self.run_helper(
                provider="claude",
                profile_id="claude-personal",
                codex_binary=None,
                environment=environment,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(payload["errorCode"], "claude_limits_unavailable")

            restored = subprocess.run(
                [sys.executable, os.fspath(script), "--restore"],
                text=True,
                capture_output=True,
                check=False,
                env={**os.environ, **environment},
            )
            self.assertEqual(restored.returncode, 0, restored.stderr)
            self.assertEqual(
                json.loads((config_dir / "settings.json").read_text(encoding="utf-8")),
                {},
            )
            self.assertFalse(script.exists())
            self.assertFalse(cache.exists())

    def test_invalid_claude_settings_are_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_dir = Path(temporary) / "claude"
            config_dir.mkdir()
            settings_path = config_dir / "settings.json"
            settings_path.write_text("{broken", encoding="utf-8")
            completed, payload = self.run_helper(
                provider="claude",
                profile_id="claude-profile",
                config_dir=config_dir,
                codex_binary=None,
                extra_args=["--install-claude-monitor"],
            )
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(payload["errorCode"], "claude_settings_invalid")
            self.assertEqual(settings_path.read_text(encoding="utf-8"), "{broken")

    def test_nvm_launcher_uses_adjacent_node_with_gnome_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            volta_bin = home / ".volta" / "bin"
            nvm_bin = home / ".nvm" / "versions" / "node" / "v24.11.1" / "bin"
            codex_js = (
                nvm_bin.parent
                / "lib"
                / "node_modules"
                / "@openai"
                / "codex"
                / "bin"
                / "codex.js"
            )
            marker = home / "selected-node"

            volta_bin.mkdir(parents=True)
            codex_js.parent.mkdir(parents=True)
            nvm_bin.mkdir(parents=True, exist_ok=True)

            old_node = volta_bin / "node"
            old_node.write_text(
                "#!/bin/sh\n"
                "printf 'volta\\n' > \"$NODE_MARKER\"\n"
                "printf 'SyntaxError: Unexpected reserved word\\n' >&2\n"
                "exit 86\n",
                encoding="utf-8",
            )
            old_node.chmod(0o755)

            matching_node = nvm_bin / "node"
            matching_node.write_text(
                "#!/bin/sh\n"
                "printf 'nvm\\n' > \"$NODE_MARKER\"\n"
                "shift\n"
                "exec /usr/bin/python3 \"$FAKE_CODEX_SCRIPT\" \"$@\"\n",
                encoding="utf-8",
            )
            matching_node.chmod(0o755)

            codex_js.write_text("#!/usr/bin/env node\n", encoding="utf-8")
            codex_js.chmod(0o755)
            codex_launcher = nvm_bin / "codex"
            codex_launcher.symlink_to(codex_js)

            gnome_path = os.pathsep.join(
                [
                    os.fspath(volta_bin),
                    "/usr/local/sbin",
                    "/usr/local/bin",
                    "/usr/sbin",
                    "/usr/bin",
                    "/sbin",
                    "/bin",
                ]
            )
            completed, payload = self.run_helper(
                codex_binary=None,
                environment={
                    "HOME": os.fspath(home),
                    "PATH": gnome_path,
                    "FAKE_CODEX_SCRIPT": os.fspath(FAKE_CODEX),
                    "NODE_MARKER": os.fspath(marker),
                },
            )

            self.assertEqual(completed.returncode, 0, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["codexBinary"], os.fspath(codex_launcher))
            self.assertEqual(marker.read_text(encoding="utf-8").strip(), "nvm")

    def test_incompatible_node_has_specific_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_home:
            launcher_dir = Path(temporary_home) / "bin"
            launcher_dir.mkdir(parents=True)
            codex_js = launcher_dir / "codex.js"
            node = launcher_dir / "node"

            codex_js.write_text("#!/usr/bin/env node\n", encoding="utf-8")
            codex_js.chmod(0o755)
            node.write_text(
                "#!/bin/sh\n"
                "printf 'file:///tmp/codex.js:233\\n' >&2\n"
                "printf 'SyntaxError: Unexpected reserved word\\n' >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            node.chmod(0o755)

            completed, payload = self.run_helper(
                codex_binary=codex_js,
                environment={"HOME": temporary_home, "PATH": "/usr/bin:/bin"},
            )
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(payload["errorCode"], "app_server_stopped")
            self.assertIn("incompatible Node.js version", payload["message"])


if __name__ == "__main__":
    unittest.main()
