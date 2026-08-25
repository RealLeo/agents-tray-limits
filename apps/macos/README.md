# Agents Tray Limits for macOS

Native macOS 13+ menu-bar application for Codex and Claude Code subscription
limits. It uses SwiftUI `MenuBarExtra`, stores preferences in `UserDefaults`,
and has no Python runtime dependency.

## Architecture

- `AgentsTrayCore` contains shared Swift models, profile validation, usage
  formatting, Theme Manifest parsing, and provider implementations.
- `AgentsTrayMacApp` is the `LSUIElement` SwiftUI application.
- `AgentsTrayCollector` is copied transactionally into an enabled Claude
  profile and preserves any previous status-line command.
- Shared locales, contracts, fixtures, and theme artwork live under
  `../../shared` and are copied into the application bundle at packaging time.

Codex data is read from the locally installed `codex app-server` over its
default stdio JSONL transport. Claude data is limited to documented
`rate_limits.five_hour` and `rate_limits.seven_day` status-line input. Neither
component reads credential files or sends telemetry.

## Development

Requirements: Xcode 15 or newer and macOS 13 or newer.

```bash
make check-macos
make -C apps/macos build
```

The core package and its XCTest suite are intentionally isolated from AppKit;
they can also be built with a Swift 5.9+ Linux toolchain. Full UI and lifecycle
verification still requires macOS.

## User themes

Place themes under:

```text
~/Library/Application Support/Agents Tray Limits/themes/<theme-id>/
```

Theme Manifest v2 uses common `art`, `panelArt`, and animation fields plus a
typed `platforms.macos` block. GNOME CSS is not executed. Version 1 themes use
the safe Classic layout while retaining valid raster art and animation.

## Release

The direct release is a universal, hardened-runtime, Developer ID signed and
notarized ZIP. Configure a Developer ID identity and notarytool profile, then:

```bash
DEVELOPER_ID_APPLICATION='Developer ID Application: Example (TEAMID)' \
NOTARY_PROFILE='agents-tray-notary' \
make pack-macos
```

Release packaging includes `LICENSE` and `NOTICE.md`. Fallout/Pip-Boy/Vault
Boy-inspired raster artwork is excluded from the MIT License; the publisher is
responsible for any permissions required for redistribution.
