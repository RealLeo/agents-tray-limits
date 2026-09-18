from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "bin/agents-tray-limits-helper.py"
spec = importlib.util.spec_from_file_location("reset_helper", HELPER)
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)


class ResetHelperTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = {
            **os.environ,
            "XDG_STATE_HOME": str(self.root / "state"),
            "FAKE_CODEX_RESET_STORE": str(self.root / "backend.json"),
            "FAKE_CODEX_REQUEST_LOG": str(self.root / "requests.jsonl"),
            "FAKE_CODEX_USED": "90",
        }
        self.key = str(uuid.uuid4())
        _, self.snapshot = self.run_helper()

    def run_helper(self, scenario="success", *, reset=False, key=None, account=None, extra=None):
        command = [sys.executable, str(HELPER), "--codex-bin", str(ROOT / "tests/fake-codex"),
                   "--timeout", "2", "--config-dir", str(self.root / "codex"),
                   "--profile-id", "personal"]
        if reset:
            command += ["--reset-limits", "--idempotency-key", key or self.key,
                        "--expected-account", account or self.snapshot["resetAccount"]]
        if extra:
            command += extra
        completed = subprocess.run(command, env={**self.environment, "FAKE_CODEX_SCENARIO": scenario},
                                   capture_output=True, text=True, timeout=10)
        return completed, json.loads(completed.stdout) if completed.stdout else None

    def consume_requests(self):
        return [json.loads(line) for line in (self.root / "requests.jsonl").read_text().splitlines()
                if json.loads(line)["method"] == "account/rateLimitResetCredit/consume"]

    def test_success_and_completed_replay_do_not_spend_twice(self):
        completed, result = self.run_helper(reset=True)
        self.assertEqual(completed.returncode, 0, result)
        self.assertEqual(result["outcome"], "reset")
        self.assertEqual(result["snapshot"]["rateLimits"]["rateLimitResetCredits"]["availableCount"], 1)
        self.assertEqual(result["snapshot"]["rateLimits"]["rateLimits"]["primary"]["usedPercent"], 0)
        self.assertIsNone(result["snapshot"]["resetAttempt"])
        self.assertEqual(result["snapshot"]["resetLastResult"]["idempotencyKey"], self.key)
        _, replay = self.run_helper(reset=True)
        self.assertEqual(replay["outcome"], "reset")
        self.assertEqual(len(self.consume_requests()), 1)
        journal = next((self.root / "state/agents-tray-limits/codex-resets").glob("*.json"))
        self.assertEqual(journal.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("@", journal.read_text())
        self.assertNotIn("token", journal.read_text())

    def test_timeout_is_recovered_across_processes_with_same_key(self):
        _, result = self.run_helper("reset-timeout", reset=True)
        self.assertEqual(result["errorCode"], "reset_uncertain")
        _, snapshot = self.run_helper()
        self.assertEqual(snapshot["resetAttempt"]["idempotencyKey"], self.key)
        # The backend already reset the windows, so a retry must not be blocked
        # by the eligibility preflight for a NEW reset.
        _, result = self.run_helper(reset=True, key=str(uuid.uuid4()))
        self.assertEqual(result["errorCode"], "reset_pending")
        _, result = self.run_helper(reset=True)
        self.assertEqual(result["outcome"], "alreadyRedeemed")
        self.assertEqual({r["params"]["idempotencyKey"] for r in self.consume_requests()}, {self.key})
        self.assertEqual(json.loads((self.root / "backend.json").read_text()), [self.key])

    def test_server_declines_without_claiming_success(self):
        for scenario, outcome in [("reset-no-credit", "noCredit"), ("reset-nothing", "nothingToReset")]:
            with self.subTest(scenario=scenario):
                _, result = self.run_helper(scenario, reset=True, key=str(uuid.uuid4()))
                self.assertEqual(result["outcome"], outcome)
                self.assertIsNotNone(result["snapshot"])
        self.assertFalse((self.root / "backend.json").exists())

    def test_success_survives_failed_refresh(self):
        _, result = self.run_helper("reset-read-failed", reset=True)
        self.assertEqual(result["outcome"], "reset")
        self.assertTrue(result["ok"])
        self.assertIsNone(result["snapshot"])
        self.assertIn("refreshError", result)

    def test_old_cli_does_not_break_monitoring(self):
        _, result = self.run_helper("reset-unsupported", reset=True)
        self.assertEqual(result["errorCode"], "reset_unsupported")
        _, snapshot = self.run_helper()
        self.assertTrue(snapshot["ok"])
        self.assertIsNone(snapshot["resetAttempt"])

    def test_account_change_prevents_consume(self):
        self.environment["FAKE_CODEX_EMAIL"] = "another@example.com"
        _, result = self.run_helper(reset=True)
        self.assertEqual(result["errorCode"], "reset_account_changed")
        self.assertEqual(self.consume_requests(), [])
        self.assertIsNone(helper.reset_account_identity({"type": "chatgpt", "email": None}))

    def test_fresh_preflight_not_cached_confirmation(self):
        for name, value, expected in [("FAKE_CODEX_USED", "89.99", "reset_above_threshold"),
                                      ("FAKE_CODEX_CREDITS", "0", "reset_no_credit")]:
            with self.subTest(name=name):
                old = self.environment.get(name)
                self.environment[name] = value
                _, result = self.run_helper(reset=True)
                self.assertEqual(result["errorCode"], expected)
                self.assertEqual(self.consume_requests(), [])
                if old is None:
                    del self.environment[name]
                else:
                    self.environment[name] = old

    def test_weekly_limit_can_enable_reset(self):
        self.environment.update(FAKE_CODEX_USED="2", FAKE_CODEX_SECONDARY="90")
        _, result = self.run_helper(reset=True)
        self.assertEqual(result["outcome"], "reset")

    def test_cli_requires_explicit_mode_key_and_account(self):
        for arguments in [["--reset-limits"], ["--idempotency-key", self.key],
                          ["--reset-limits", "--idempotency-key", "invalid"],
                          ["--reset-limits", "--idempotency-key", self.key, "--provider", "claude"]]:
            completed, _ = self.run_helper(extra=arguments)
            self.assertEqual(completed.returncode, 2)
        self.assertEqual(self.consume_requests(), [])

    def test_corrupt_journal_blocks_reset_but_not_monitoring(self):
        state_dir = self.root / "state/agents-tray-limits/codex-resets"
        _, _ = self.run_helper("reset-unsupported", reset=True)
        next(state_dir.glob("*.json")).write_text("not json")
        _, snapshot = self.run_helper()
        self.assertTrue(snapshot["ok"])
        self.assertTrue(snapshot["resetStateError"])
        _, result = self.run_helper(reset=True)
        self.assertEqual(result["errorCode"], "reset_state_invalid")

    def test_policy_ignores_other_buckets_and_bad_windows(self):
        rates = self.snapshot["rateLimits"]
        main = rates["rateLimitsByLimitId"]["codex"]
        rates["rateLimits"] = main
        rates["rateLimitsByLimitId"]["codex_other"]["primary"]["usedPercent"] = 100
        main["primary"]["usedPercent"] = 89.99
        self.assertEqual(helper.reset_unavailable_reason(rates, 100), "reset_above_threshold")
        for used in [None, "100", True, -1, float("nan"), 101]:
            main["primary"]["usedPercent"] = used
            main["secondary"] = None
            self.assertEqual(helper.reset_unavailable_reason(rates, 100), "reset_no_data")
        main["primary"].update(usedPercent=100, resetsAt=50)
        self.assertEqual(helper.reset_unavailable_reason(rates, 100), "reset_no_data")
        main["primary"].update(resetsAt=200, windowDurationMins=60)
        self.assertEqual(helper.reset_unavailable_reason(rates, 100), "reset_no_data")


if __name__ == "__main__":
    unittest.main()
