#!/usr/bin/env python3
"""Read isolated Codex and Claude Code subscription-limit profiles.

The program writes exactly one JSON object to stdout. Codex authentication
remains managed by Codex CLI. Claude data comes only from documented
status-line fields; neither provider's credential file is read directly.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import glob
import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

HELPER_VERSION = "3.0.0"
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


PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
CLAUDE_MONITOR_DIR = "agents-tray-limits"
CLAUDE_MONITOR_SCRIPT = "statusline.py"
CLAUDE_MONITOR_BACKUP = "statusline-backup.json"


class AppServerClient:
    def __init__(self, codex_binary: str, timeout: float, config_dir: str = "") -> None:
        self.codex_binary = codex_binary
        self.timeout = timeout
        self.config_dir = config_dir
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

        command = [self.codex_binary]
        if self.config_dir:
            environment["CODEX_HOME"] = self.config_dir
            command.extend(["-c", 'cli_auth_credentials_store="file"'])
        else:
            environment.pop("CODEX_HOME", None)
        command.append("app-server")

        try:
            self.process = subprocess.Popen(
                command,
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
            stopped = self._stopped_error()
            if not stopped.details:
                stopped.details = str(exc)
            raise stopped from exc

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

    def _drain_diagnostics(self) -> None:
        """Give reader threads a brief chance to publish exit diagnostics."""
        deadline = time.monotonic() + 0.15
        while time.monotonic() < deadline:
            try:
                kind, line = self.events.get(timeout=0.02)
            except queue.Empty:
                continue
            if kind == "stderr" and line:
                self.stderr_lines.append(line)
                self.stderr_lines = self.stderr_lines[-30:]
            elif kind == "stdout" and line:
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    self.invalid_stdout_lines.append(line[:500])
                    self.invalid_stdout_lines = self.invalid_stdout_lines[-5:]

    def _stopped_error(self) -> HelperError:
        self._drain_diagnostics()
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


def collect_codex_usage(
    codex_binary: str,
    timeout: float,
    profile_id: str = "default-codex",
    config_dir: str = "",
) -> dict[str, Any]:
    started_at = time.monotonic()
    with AppServerClient(codex_binary, timeout, config_dir) as client:
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
            "profileId": profile_id,
            "provider": "codex",
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


def collect_usage(codex_binary: str, timeout: float) -> dict[str, Any]:
    """Backward-compatible entry point used by downstream helper consumers."""
    return collect_codex_usage(codex_binary, timeout)


def _profile_id(value: str) -> str:
    profile_id = value.strip()
    if not PROFILE_ID_RE.fullmatch(profile_id):
        raise HelperError(
            "invalid_profile",
            "The profile ID must contain only letters, digits, dots, underscores, or hyphens.",
        )
    return profile_id


def _config_directory(provider: str, value: str) -> Path:
    raw = value.strip()
    if raw:
        if any(ord(character) < 32 or ord(character) == 127 for character in raw) or not (
            raw.startswith("/") or raw.startswith("~/")
        ):
            raise HelperError(
                "invalid_profile_path",
                "Profile directories must be absolute paths or start with ~/.",
                raw,
            )
        path = Path(os.path.expanduser(raw))
        if not path.is_absolute():
            raise HelperError(
                "invalid_profile_path",
                "Profile directories must be absolute paths or start with ~/.",
                raw,
            )
        return path
    return Path.home() / (".claude" if provider == "claude" else ".codex")


def _cache_root() -> Path:
    configured = os.environ.get("XDG_CACHE_HOME", "").strip()
    root = Path(os.path.expanduser(configured)) if configured else Path.home() / ".cache"
    if not root.is_absolute():
        root = Path.home() / ".cache"
    return root / "agents-tray-limits" / "claude"


def _claude_cache_file(profile_id: str) -> Path:
    return _cache_root() / f"{_profile_id(profile_id)}.json"


def _read_json_object(path: Path, error_code: str, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        raise HelperError(error_code, description, str(exc)) from exc
    if not isinstance(value, dict):
        raise HelperError(error_code, description, "Top-level JSON value is not an object.")
    return value


def _atomic_write_text(path: Path, text: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=os.fspath(path.parent),
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def _atomic_write_json(path: Path, value: dict[str, Any], mode: int = 0o600) -> None:
    _atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        mode,
    )


def _claude_window(value: Any, duration_minutes: int) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    used = value.get("used_percentage")
    resets_at = value.get("resets_at")
    try:
        used_number = float(used)
        reset_number = int(float(resets_at))
    except (TypeError, ValueError, OverflowError):
        return None
    if not (0 <= used_number <= 100) or reset_number <= 0:
        return None
    return {
        "usedPercent": used_number,
        "windowDurationMins": duration_minutes,
        "resetsAt": reset_number,
    }


def collect_claude_usage(profile_id: str, config_dir: str = "") -> dict[str, Any]:
    profile_id = _profile_id(profile_id)
    config_directory = _config_directory("claude", config_dir)
    cache_file = _claude_cache_file(profile_id)
    if not cache_file.is_file():
        raise HelperError(
            "claude_cache_missing",
            "Claude Code has not reported limits for this profile yet.",
            os.fspath(cache_file),
        )
    cache = _read_json_object(
        cache_file,
        "claude_cache_invalid",
        "The Claude Code limit cache is invalid.",
    )
    rate_limits = cache.get("rate_limits")
    if not isinstance(rate_limits, dict):
        raise HelperError(
            "claude_limits_unavailable",
            "Claude Code did not expose subscription rate limits for this profile.",
        )
    primary = _claude_window(rate_limits.get("five_hour"), 300)
    secondary = _claude_window(rate_limits.get("seven_day"), 10080)
    if primary is None:
        raise HelperError(
            "claude_limits_unavailable",
            "Claude Code did not expose its five-hour subscription limit.",
        )
    if primary["resetsAt"] <= int(time.time()):
        raise HelperError(
            "claude_limits_stale",
            "Claude Code must run once to refresh the expired limit data.",
        )

    bucket = {
        "limitId": "claude",
        "limitName": "Claude Code",
        "primary": primary,
        "secondary": secondary,
        "rateLimitReachedType": None,
    }
    fetched_at = cache.get("fetchedAt")
    try:
        fetched_at = int(fetched_at) if fetched_at is not None else int(time.time())
    except (TypeError, ValueError, OverflowError) as exc:
        raise HelperError(
            "claude_cache_invalid",
            "The Claude Code limit cache has an invalid update time.",
        ) from exc
    return {
        "ok": True,
        "helperVersion": HELPER_VERSION,
        "profileId": profile_id,
        "provider": "claude",
        "source": "claude-statusline",
        "fetchedAt": fetched_at,
        "account": {"type": "claude"},
        "rateLimits": {
            "rateLimits": bucket,
            "rateLimitsByLimitId": {"claude": bucket},
        },
        "usage": None,
        "claudeVersion": cache.get("version"),
        "configDir": os.fspath(config_directory),
    }


def _monitor_paths(config_dir: str) -> tuple[Path, Path, Path, Path]:
    root = _config_directory("claude", config_dir)
    managed = root / CLAUDE_MONITOR_DIR
    return (
        root / "settings.json",
        managed / CLAUDE_MONITOR_SCRIPT,
        managed / CLAUDE_MONITOR_BACKUP,
        managed / "statusline.lock",
    )


def _wrapper_command(script_path: Path) -> str:
    return f"/usr/bin/python3 {shlex.quote(os.fspath(script_path))}"


def _collector_source(
    profile_id: str,
    cache_file: Path,
    original_command: str,
    wrapper_command: str,
) -> str:
    return f'''#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROFILE_ID = {profile_id!r}
CACHE_FILE = Path({os.fspath(cache_file)!r})
ORIGINAL_COMMAND = {original_command!r}
WRAPPER_COMMAND = {wrapper_command!r}
SCRIPT_FILE = Path(__file__).resolve()
BACKUP_FILE = SCRIPT_FILE.with_name({CLAUDE_MONITOR_BACKUP!r})
SETTINGS_FILE = SCRIPT_FILE.parent.parent / "settings.json"


def atomic_json(path, value, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent), text=True)
    temporary = Path(name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def clean_window(value):
    if not isinstance(value, dict):
        return None
    try:
        used = float(value.get("used_percentage"))
        resets_at = int(float(value.get("resets_at")))
    except (TypeError, ValueError, OverflowError):
        return None
    if not 0 <= used <= 100 or resets_at <= 0:
        return None
    return {{"used_percentage": used, "resets_at": resets_at}}


def clean_rate_limits(value):
    if not isinstance(value, dict):
        return {{}}
    cleaned = {{}}
    for name in ("five_hour", "seven_day"):
        window = clean_window(value.get(name))
        if window is not None:
            cleaned[name] = window
    return cleaned


def restore():
    try:
        backup = json.loads(BACKUP_FILE.read_text(encoding="utf-8"))
        settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8")) if SETTINGS_FILE.exists() else {{}}
    except Exception as exc:
        print("Agents Tray Limits restore failed: " + str(exc), file=sys.stderr)
        return 2
    current = settings.get("statusLine")
    if current != backup.get("installedStatusLine"):
        print("Agents Tray Limits did not restore statusLine because it was changed independently.", file=sys.stderr)
        return 4
    if backup.get("originalPresent"):
        settings["statusLine"] = backup.get("originalStatusLine")
    else:
        settings.pop("statusLine", None)
    atomic_json(SETTINGS_FILE, settings)
    BACKUP_FILE.unlink(missing_ok=True)
    CACHE_FILE.unlink(missing_ok=True)
    try:
        SCRIPT_FILE.unlink()
        SCRIPT_FILE.parent.rmdir()
    except OSError:
        pass
    return 0


if "--restore" in sys.argv[1:]:
    raise SystemExit(restore())

raw = sys.stdin.read()
try:
    source = json.loads(raw)
    version = source.get("version")
    if not isinstance(version, str):
        version = None
    payload = {{
        "version": version,
        "rate_limits": clean_rate_limits(source.get("rate_limits")),
        "fetchedAt": int(time.time()),
    }}
    atomic_json(CACHE_FILE, payload)
except Exception as exc:
    print("Agents Tray Limits cache update failed: " + str(exc), file=sys.stderr)

if not ORIGINAL_COMMAND:
    raise SystemExit(0)
completed = subprocess.run(
    ORIGINAL_COMMAND,
    shell=True,
    input=raw,
    text=True,
    capture_output=True,
    check=False,
)
sys.stdout.write(completed.stdout)
sys.stderr.write(completed.stderr)
raise SystemExit(completed.returncode)
'''


@contextlib.contextmanager
def _monitor_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock_path.open("a+", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _settings_object(settings_path: Path) -> dict[str, Any]:
    if not settings_path.exists():
        return {}
    return _read_json_object(
        settings_path,
        "claude_settings_invalid",
        "Claude Code settings.json is not valid JSON.",
    )


def claude_monitor_status(profile_id: str, config_dir: str = "") -> dict[str, Any]:
    profile_id = _profile_id(profile_id)
    settings_path, script_path, backup_path, _ = _monitor_paths(config_dir)
    settings = _settings_object(settings_path)
    current = settings.get("statusLine")
    current_command = current.get("command") if isinstance(current, dict) else None
    expected = _wrapper_command(script_path)
    backup = _read_json_object(
        backup_path,
        "claude_monitor_invalid",
        "The Claude monitor backup is invalid.",
    ) if backup_path.exists() else {}
    if backup:
        state = "installed" if (
            backup.get("profileId") == profile_id and
            current == backup.get("installedStatusLine")
        ) else "conflict"
    elif current_command == expected or script_path.exists():
        state = "conflict"
    else:
        state = "not_installed"
    return {
        "ok": True,
        "helperVersion": HELPER_VERSION,
        "profileId": profile_id,
        "provider": "claude",
        "operation": "monitor-status",
        "monitorState": state,
        "scriptPath": os.fspath(script_path),
        "cachePath": os.fspath(_claude_cache_file(profile_id)),
    }


def install_claude_monitor(profile_id: str, config_dir: str = "") -> dict[str, Any]:
    profile_id = _profile_id(profile_id)
    settings_path, script_path, backup_path, lock_path = _monitor_paths(config_dir)
    cache_file = _claude_cache_file(profile_id)
    wrapper_command = _wrapper_command(script_path)
    with _monitor_lock(lock_path):
        created_backup = False
        settings = _settings_object(settings_path)
        current = settings.get("statusLine")
        current_command = current.get("command") if isinstance(current, dict) else None
        if backup_path.exists():
            backup = _read_json_object(
                backup_path,
                "claude_monitor_invalid",
                "The Claude monitor backup is invalid.",
            )
            if (
                backup.get("profileId") != profile_id or
                current != backup.get("installedStatusLine")
            ):
                raise HelperError(
                    "claude_monitor_conflict",
                    "Claude Code statusLine changed after monitoring was installed.",
                )
            original_present = bool(backup.get("originalPresent"))
            original = backup.get("originalStatusLine")
        else:
            if current_command == wrapper_command or script_path.exists():
                raise HelperError(
                    "claude_monitor_conflict",
                    "Claude monitor files exist without a restorable backup.",
                )
            original_present = "statusLine" in settings
            original = current
            backup = {
                "version": 1,
                "profileId": profile_id,
                "originalPresent": original_present,
                "originalStatusLine": original,
                "wrapperCommand": wrapper_command,
            }
            created_backup = True

        original_command = original.get("command", "") if isinstance(original, dict) else ""
        wrapper = dict(original) if isinstance(original, dict) else {}
        wrapper["type"] = "command"
        wrapper["command"] = wrapper_command
        if created_backup:
            backup["installedStatusLine"] = wrapper
        settings["statusLine"] = wrapper
        try:
            if created_backup:
                _atomic_write_json(backup_path, backup)
            _atomic_write_text(
                script_path,
                _collector_source(profile_id, cache_file, original_command, wrapper_command),
                0o700,
            )
            _atomic_write_json(settings_path, settings)
        except Exception:
            if created_backup:
                script_path.unlink(missing_ok=True)
                backup_path.unlink(missing_ok=True)
            raise

    result = claude_monitor_status(profile_id, config_dir)
    result["operation"] = "monitor-install"
    return result


def restore_claude_monitor(profile_id: str, config_dir: str = "") -> dict[str, Any]:
    profile_id = _profile_id(profile_id)
    settings_path, script_path, backup_path, lock_path = _monitor_paths(config_dir)
    with _monitor_lock(lock_path):
        if not backup_path.exists():
            if script_path.exists():
                raise HelperError(
                    "claude_monitor_conflict",
                    "Claude monitor files exist without a restorable backup.",
                )
            return {
                "ok": True,
                "helperVersion": HELPER_VERSION,
                "profileId": profile_id,
                "provider": "claude",
                "operation": "monitor-restore",
                "monitorState": "not_installed",
            }
        backup = _read_json_object(
            backup_path,
            "claude_monitor_invalid",
            "The Claude monitor backup is invalid.",
        )
        settings = _settings_object(settings_path)
        current = settings.get("statusLine")
        if (
            backup.get("profileId") != profile_id or
            current != backup.get("installedStatusLine")
        ):
            raise HelperError(
                "claude_monitor_conflict",
                "Claude Code statusLine changed independently; it was not overwritten.",
            )
        if backup.get("originalPresent"):
            settings["statusLine"] = backup.get("originalStatusLine")
        else:
            settings.pop("statusLine", None)
        _atomic_write_json(settings_path, settings)
        backup_path.unlink(missing_ok=True)
        script_path.unlink(missing_ok=True)
        _claude_cache_file(profile_id).unlink(missing_ok=True)
        try:
            script_path.parent.rmdir()
        except OSError:
            pass
    return {
        "ok": True,
        "helperVersion": HELPER_VERSION,
        "profileId": profile_id,
        "provider": "claude",
        "operation": "monitor-restore",
        "monitorState": "not_installed",
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("codex", "claude"), default="codex")
    parser.add_argument("--profile-id", default="default-codex", help="Stable profile identifier")
    parser.add_argument("--config-dir", default="", help="CODEX_HOME or CLAUDE_CONFIG_DIR")
    parser.add_argument("--codex-bin", default="", help="Explicit path to the codex executable")
    parser.add_argument("--timeout", type=float, default=15.0, help="Timeout for one RPC request, in seconds")
    monitor = parser.add_mutually_exclusive_group()
    monitor.add_argument("--install-claude-monitor", action="store_true")
    monitor.add_argument("--restore-claude-monitor", action="store_true")
    monitor.add_argument("--claude-monitor-status", action="store_true")
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
        profile_id = _profile_id(args.profile_id)
        if args.install_claude_monitor:
            payload = install_claude_monitor(profile_id, args.config_dir)
        elif args.restore_claude_monitor:
            payload = restore_claude_monitor(profile_id, args.config_dir)
        elif args.claude_monitor_status:
            payload = claude_monitor_status(profile_id, args.config_dir)
        elif args.provider == "claude":
            payload = collect_claude_usage(profile_id, args.config_dir)
        else:
            codex_binary = find_codex(args.codex_bin or None)
            config_dir = os.fspath(_config_directory("codex", args.config_dir)) \
                if args.config_dir else ""
            payload = collect_codex_usage(
                codex_binary,
                timeout,
                profile_id,
                config_dir,
            )
        emit(payload, args.pretty)
        return 0
    except HelperError as exc:
        payload: dict[str, Any] = {
            "ok": False,
            "helperVersion": HELPER_VERSION,
            "fetchedAt": int(time.time()),
            "profileId": getattr(args, "profile_id", ""),
            "provider": getattr(args, "provider", "codex"),
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
                "profileId": getattr(args, "profile_id", ""),
                "provider": getattr(args, "provider", "codex"),
                "errorCode": "internal_error",
                "message": "Agents Tray Limits helper encountered an internal error.",
                "details": f"{type(exc).__name__}: {exc}",
            },
            args.pretty,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
