#!/usr/bin/env python3
"""Dependency-free structural checks for the macOS implementation on non-macOS hosts."""

from __future__ import annotations

import plistlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MACOS = ROOT / "apps" / "macos"


def text(relative: str) -> str:
    path = MACOS / relative
    if not path.is_file():
        raise ValueError(f"missing macOS source file: {relative}")
    return path.read_text(encoding="utf-8")


def require(relative: str, *needles: str) -> None:
    source = text(relative)
    missing = [needle for needle in needles if needle not in source]
    if missing:
        raise ValueError(f"{relative}: missing required implementation markers: {missing}")


def main() -> int:
    with (MACOS / "Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    expected = {
        "CFBundleIdentifier": "com.realleo.AgentsTrayLimits",
        "LSMinimumSystemVersion": "13.0",
        "LSUIElement": True,
    }
    for key, value in expected.items():
        if info.get(key) != value:
            raise ValueError(f"Info.plist: {key} must be {value!r}")

    require("Package.swift", ".macOS(.v13)", "AgentsTrayCore", "AgentsTrayCollector", "AgentsTrayMacApp")
    require("Sources/AgentsTrayMacApp/AgentsTrayLimitsApp.swift", "MenuBarExtra", "Settings", "panelImage")
    require("Sources/AgentsTrayMacApp/AppStore.swift", "SMAppService.mainApp", "by: 3", "panelArt", "localizedError")
    require("Sources/AgentsTrayMacApp/ThemeViews.swift", "accessibilityReduceMotion", "pipboy2000", "pipboy3000")
    require(
        "Sources/AgentsTrayCore/CodexProvider.swift",
        "agents_tray_limits_macos",
        '"account/read"',
        '"account/rateLimits/read"',
        '"account/usage/read"',
        "/opt/homebrew/bin/codex",
        "/usr/local/bin/codex",
        ".nvm/versions/node",
        ".volta/bin/codex",
        ".bun/bin/codex",
        ".asdf/shims/codex",
        ".local/share/mise/shims/codex",
    )
    require(
        "Sources/AgentsTrayCore/ClaudeProvider.swift",
        "FileLock",
        "atomicWrite",
        "claude_monitor_conflict",
        "originalStatusLine",
        "Agents Tray Limits/claude",
    )
    require("Sources/AgentsTrayCollector/main.swift", '"/bin/sh"', '"-c"', "terminationStatus")
    require(
        "scripts/package_release.sh",
        "ARCHS='arm64 x86_64'",
        "AgentsTrayMacApp.xcarchive",
        "  test",
        "  archive",
        "codesign --verify --deep --strict",
        "notarytool submit",
        "stapler staple",
        "spctl --assess",
        "shasum -a 256",
    )
    print("macOS source and bundle contracts: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
