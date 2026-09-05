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


def forbid(relative: str, *needles: str) -> None:
    source = text(relative)
    present = [needle for needle in needles if needle in source]
    if present:
        raise ValueError(f"{relative}: contains removed implementation markers: {present}")


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
    require(
        "Sources/AgentsTrayMacApp/AppStore.swift",
        "SMAppService.mainApp",
        "by: 3",
        "panelArt",
        "localizedError",
        'themes.first(where: { $0.id == "fallout-2" })?.id ?? "classic"',
    )
    require(
        "Sources/AgentsTrayMacApp/ThemeViews.swift",
        "accessibilityReduceMotion",
        "pipboy2000",
        "AgentsAmpView",
        "AgentsAmpModule",
        "AgentsAmpLimitRow",
        "AgentsAmpSevenSegmentNumber",
        "ForEach((1...12).reversed()",
        'ForEach(["PRE", "60", "170", "310", "600", "1K", "3K", "6K", "12K", "16K"]',
        'assets/ui/chrome-shell-v2.png',
        r'assets/ui/button-\(assetKey)-\(state)-v1.png',
        "AgentsAmpRasterButtonStyle",
        "resetCounters",
        "Array(repeating: 2, count: 28)",
        "120_000_000",
        "store.preferences.themeAnimation",
        "store.closeMenu()",
    )
    require("Sources/AgentsTrayCore/ThemeManifest.swift", 'case agentsAmp = "agents-amp"')
    require("Sources/AgentsTrayMacApp/AppStore.swift", "func closeMenu()", "orderOut(nil)")
    theme_views = text("Sources/AgentsTrayMacApp/ThemeViews.swift")
    agents_amp = theme_views.split("struct AgentsAmpView: View {", 1)[1].split(
        "private struct ThemePalette", 1
    )[0]
    for forbidden in ("Picker(", "ProgressView(", "store.quit()"):
        if forbidden in agents_amp:
            raise ValueError(f"AgentsAmpView must use custom controls: found {forbidden}")
    for forbidden in ("AgentsAmpDither().opacity", ".agentsAmpInsetBorder"):
        if forbidden in agents_amp:
            raise ValueError(f"AgentsAmpView must leave raster chrome unobstructed: found {forbidden}")
    forbid("Sources/AgentsTrayCore/ThemeManifest.swift", "pipboy3000", "pipboy-3000")
    forbid("Sources/AgentsTrayMacApp/ThemeViews.swift", "PipBoy3000", "pipboy3000")
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
