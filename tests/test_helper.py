from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
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
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        child_environment = os.environ.copy()
        child_environment["FAKE_CODEX_SCENARIO"] = scenario
        if environment:
            child_environment.update(environment)

        command = [sys.executable, os.fspath(HELPER), "--timeout", "2"]
        if codex_binary is not None:
            command.extend(["--codex-bin", os.fspath(codex_binary)])

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
        self.assertEqual(payload["helperVersion"], "2.0.0")
        self.assertEqual(payload["rateLimits"]["rateLimits"]["limitId"], "codex")
        self.assertEqual(payload["usage"]["summary"]["lifetimeTokens"], 1_234_567)

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
