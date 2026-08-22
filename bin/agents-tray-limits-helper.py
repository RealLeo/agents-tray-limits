#!/usr/bin/env python3
"""Read ChatGPT/Codex usage through the official Codex App Server.

The program writes exactly one JSON object to stdout. It never reads or
prints ChatGPT credentials; authentication remains managed by Codex CLI.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

HELPER_VERSION = "2.0.0"
CLIENT_INFO = {
    "name": "agents_tray_limits_gnome",
    "title": "Agents Tray Limits for GNOME",
    "version": HELPER_VERSION,
}


@dataclass
class HelperError(Exception):
    code: str
    message: str
    details: str | None = None

    def __str__(self) -> str:
        return self.message


def _is_executable(path: str | os.PathLike[str] | None) -> bool:
    if not path:
        return False
    candidate = os.path.expanduser(os.fspath(path))
    return os.path.isfile(candidate) and os.access(candidate, os.X_OK)


def _absolute_launcher(path: str | os.PathLike[str]) -> str:
    """Return an absolute launcher path without resolving its symlinks.

    Node version managers install ``codex`` next to their matching ``node``
    executable. Resolving the launcher symlink to ``codex.js`` loses that
    relationship and lets ``/usr/bin/env node`` select an unrelated runtime.
    """
    return os.path.abspath(os.path.expanduser(os.fspath(path)))


def find_codex(explicit: str | None) -> str:
    """Find Codex even when GNOME Shell has a smaller PATH than a login shell."""
    if explicit:
        expanded = os.path.expandvars(os.path.expanduser(explicit.strip()))
        if os.sep not in expanded:
            located = shutil.which(expanded)
            if located:
                return _absolute_launcher(located)
        if _is_executable(expanded):
            return _absolute_launcher(expanded)
        raise HelperError(
            "codex_not_found",
            "Codex CLI was not found at the configured path.",
            expanded,
        )

    located = shutil.which("codex")
    if located:
        return _absolute_launcher(located)

    home = Path.home()
    candidates: list[Path] = [
        home / ".local" / "bin" / "codex",
        home / ".cargo" / "bin" / "codex",
        home / ".volta" / "bin" / "codex",
        home / ".bun" / "bin" / "codex",
        home / ".npm-global" / "bin" / "codex",
        home / ".local" / "share" / "pnpm" / "codex",
        home / ".asdf" / "shims" / "codex",
        home / ".local" / "share" / "mise" / "shims" / "codex",
        Path("/usr/local/bin/codex"),
        Path("/usr/bin/codex"),
        Path("/snap/bin/codex"),
    ]

    # NVM keeps one executable per installed Node version. Prefer the newest
    # executable by modification time rather than relying on lexical sorting.
    nvm_candidates = [Path(p) for p in glob.glob(str(home / ".nvm/versions/node/*/bin/codex"))]
    nvm_candidates.sort(
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )
    candidates[0:0] = nvm_candidates

    seen: set[str] = set()
    for candidate in candidates:
        key = os.fspath(candidate)
        if key in seen:
            continue
        seen.add(key)
        if _is_executable(candidate):
            return _absolute_launcher(candidate)

    raise HelperError(
        "codex_not_found",
        "Codex CLI was not found. Install Codex and sign in with ChatGPT once.",
    )


class AppServerClient:
    def __init__(self, codex_binary: str, timeout: float) -> None:
        self.codex_binary = codex_binary
        self.timeout = timeout
        self.process: subprocess.Popen[str] | None = None
        self.events: queue.Queue[tuple[str, str | None]] = queue.Queue()
        self.pending: dict[int | str, dict[str, Any]] = {}
        self.stderr_lines: list[str] = []
        self.invalid_stdout_lines: list[str] = []

    def __enter__(self) -> "AppServerClient":
        environment = os.environ.copy()
        launcher_dir = os.path.dirname(self.codex_binary)
        inherited_path = environment.get("PATH", "")
        path_entries = [entry for entry in inherited_path.split(os.pathsep) if entry]
        environment["PATH"] = os.pathsep.join(
            [launcher_dir, *[entry for entry in path_entries if entry != launcher_dir]]
        )

        try:
            self.process = subprocess.Popen(
                [self.codex_binary, "app-server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=os.path.expanduser("~"),
                env=environment,
            )
        except OSError as exc:
            raise HelperError(
                "app_server_start_failed",
                "Failed to start Codex App Server.",
                str(exc),
            ) from exc

        assert self.process.stdout is not None
        assert self.process.stderr is not None
        threading.Thread(
            target=self._read_stream,
            args=("stdout", self.process.stdout),
            daemon=True,
        ).start()
        threading.Thread(
            target=self._read_stream,
            args=("stderr", self.process.stderr),
            daemon=True,
        ).start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def _read_stream(self, kind: str, stream: TextIO) -> None:
        try:
            for line in stream:
                self.events.put((kind, line.rstrip("\r\n")))
        finally:
            self.events.put((kind, None))

    def close(self) -> None:
        process = self.process
        self.process = None
        if process is None:
            return

        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass

        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=0.8)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=0.8)
                except subprocess.TimeoutExpired:
                    pass
            except OSError:
                pass

    def send(self, message: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise HelperError("protocol_error", "Codex App Server is not running.")
        try:
            self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            details = self._diagnostics() or str(exc)
            raise HelperError(
                "app_server_stopped",
                "Codex App Server stopped unexpectedly.",
                details,
            ) from exc

    def request(self, method: str, request_id: int, params: dict[str, Any] | None = None) -> dict[str, Any]:
        message: dict[str, Any] = {"method": method, "id": request_id}
        if params is not None:
            message["params"] = params
        self.send(message)
        return self.wait_for(request_id)

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = params
        self.send(message)

    def wait_for(self, request_id: int) -> dict[str, Any]:
        if request_id in self.pending:
            return self.pending.pop(request_id)

        deadline = time.monotonic() + self.timeout
        stdout_closed = False
        while time.monotonic() < deadline:
            remaining = max(0.05, deadline - time.monotonic())
            try:
                kind, line = self.events.get(timeout=min(0.25, remaining))
            except queue.Empty:
                if self.process is not None and self.process.poll() is not None:
                    raise self._stopped_error()
                continue

            if kind == "stderr":
                if line:
                    self.stderr_lines.append(line)
                    self.stderr_lines = self.stderr_lines[-30:]
                continue

            if line is None:
                stdout_closed = True
                if self.process is not None and self.process.poll() is not None:
                    break
                continue

            if not line.strip():
                continue

            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self.invalid_stdout_lines.append(line[:500])
                self.invalid_stdout_lines = self.invalid_stdout_lines[-5:]
                continue

            if not isinstance(message, dict):
                continue
            message_id = message.get("id")
            if message_id == request_id:
                return message
            if message_id is not None:
                self.pending[message_id] = message
            # Server notifications deliberately have no id and can be ignored
            # for this one-shot reader.

        if stdout_closed or (self.process is not None and self.process.poll() is not None):
            raise self._stopped_error()
        raise HelperError(
            "timeout",
            "Codex did not return usage data before the timeout.",
            self._diagnostics(),
        )

    def _diagnostics(self) -> str | None:
        lines: list[str] = []
        if self.stderr_lines:
            lines.extend(self.stderr_lines[-8:])
        if self.invalid_stdout_lines:
            lines.append("Invalid stdout: " + " | ".join(self.invalid_stdout_lines[-2:]))
        text = "\n".join(lines).strip()
        return text[-2000:] if text else None

    def _stopped_error(self) -> HelperError:
        details = self._diagnostics()
        lowered = (details or "").lower()
        incompatible_node = (
            "codex.js" in lowered
            and (
                "syntaxerror" in lowered
                or "unexpected reserved word" in lowered
                or "unexpected token" in lowered
            )
        )
        message = (
            "Codex CLI is running with an incompatible Node.js version."
            if incompatible_node
            else "Codex App Server stopped before returning a response."
        )
        return HelperError("app_server_stopped", message, details)


def _rpc_result(response: dict[str, Any], method: str, *, optional: bool = False) -> tuple[Any, dict[str, Any] | None]:
    error = response.get("error")
    if error is not None:
        if optional:
            return None, error if isinstance(error, dict) else {"message": str(error)}

        message = error.get("message") if isinstance(error, dict) else str(error)
        error_code = error.get("code") if isinstance(error, dict) else None
        if error_code == -32601 or "not found" in str(message).lower():
            raise HelperError(
                "codex_too_old",
                "This Codex CLI version cannot read usage limits. Update Codex and try again.",
                str(message),
            )
        raise HelperError(
            "app_server_error",
            f"Codex did not return data for {method}.",
            str(message),
        )
    return response.get("result"), None


def collect_usage(codex_binary: str, timeout: float) -> dict[str, Any]:
    started_at = time.monotonic()
    with AppServerClient(codex_binary, timeout) as client:
        initialize_response = client.request(
            "initialize",
            1,
            {"clientInfo": CLIENT_INFO},
        )
        initialize_result, _ = _rpc_result(initialize_response, "initialize")
        client.notify("initialized", {})

        account_response = client.request(
            "account/read",
            2,
            {"refreshToken": False},
        )
        account_result, _ = _rpc_result(account_response, "account/read")
        if not isinstance(account_result, dict):
            raise HelperError(
                "protocol_error",
                "Codex returned an unexpected account data format.",
            )

        account = account_result.get("account")
        if account is None:
            raise HelperError(
                "not_logged_in",
                "Codex CLI has no active session. Run 'codex' and choose Sign in with ChatGPT.",
            )

        account_type = account.get("type") if isinstance(account, dict) else None
        if account_type in {"apiKey", "amazonBedrock"}:
            raise HelperError(
                "unsupported_auth",
                "Subscription limits require Codex sign-in with ChatGPT, not an API key or Bedrock.",
                f"account.type={account_type}",
            )

        # The two reads are independent. Send both first so a slow network
        # request does not double the perceived refresh time.
        client.send({"method": "account/rateLimits/read", "id": 3})
        client.send({"method": "account/usage/read", "id": 4})

        rate_response = client.wait_for(3)
        rate_result, _ = _rpc_result(rate_response, "account/rateLimits/read")
        if not isinstance(rate_result, dict):
            raise HelperError(
                "no_rate_limits",
                "Codex did not return any available ChatGPT limits.",
            )

        # Token activity was added after the rate-limit surface. Keep the
        # extension useful with an older server by treating this call as optional.
        try:
            usage_response = client.wait_for(4)
            usage_result, usage_error = _rpc_result(
                usage_response,
                "account/usage/read",
                optional=True,
            )
        except HelperError as exc:
            usage_result = None
            usage_error = {"code": exc.code, "message": exc.message}

        result: dict[str, Any] = {
            "ok": True,
            "helperVersion": HELPER_VERSION,
            "source": "codex-app-server",
            "fetchedAt": int(time.time()),
            "elapsedMs": round((time.monotonic() - started_at) * 1000),
            "codexBinary": codex_binary,
            "account": account,
            "requiresOpenaiAuth": account_result.get("requiresOpenaiAuth"),
            "rateLimits": rate_result,
            "usage": usage_result if isinstance(usage_result, dict) else None,
        }
        if isinstance(initialize_result, dict) and initialize_result.get("serverInfo"):
            result["serverInfo"] = initialize_result.get("serverInfo")
        if usage_error:
            result["usageError"] = {
                "code": usage_error.get("code"),
                "message": usage_error.get("message", "Token activity is unavailable."),
            }
        return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-bin", default="", help="Explicit path to the codex executable")
    parser.add_argument("--timeout", type=float, default=15.0, help="Timeout for one RPC request, in seconds")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the JSON response")
    return parser.parse_args(argv)


def emit(payload: dict[str, Any], pretty: bool) -> None:
    if pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    timeout = min(max(args.timeout, 2.0), 60.0)
    try:
        codex_binary = find_codex(args.codex_bin or None)
        payload = collect_usage(codex_binary, timeout)
        emit(payload, args.pretty)
        return 0
    except HelperError as exc:
        payload: dict[str, Any] = {
            "ok": False,
            "helperVersion": HELPER_VERSION,
            "fetchedAt": int(time.time()),
            "errorCode": exc.code,
            "message": exc.message,
        }
        if exc.details:
            payload["details"] = exc.details
        emit(payload, args.pretty)
        return 2
    except Exception as exc:  # Defensive: always leave the extension valid JSON.
        emit(
            {
                "ok": False,
                "helperVersion": HELPER_VERSION,
                "fetchedAt": int(time.time()),
                "errorCode": "internal_error",
                "message": "Agents Tray Limits helper encountered an internal error.",
                "details": f"{type(exc).__name__}: {exc}",
            },
            args.pretty,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
