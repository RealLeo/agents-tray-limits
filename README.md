# Agents Tray Limits

Agents Tray Limits is a local, privacy-preserving subscription-limit monitor
for Codex and Claude Code. This repository contains platform applications and
their shared contracts and visual resources.

![Agents Tray Limits on Ubuntu with the Fallout 2 theme](docs/images/agents-tray-limits-fallout-2.png)

_GNOME Shell interface on Ubuntu — Fallout 2 / Pip-Boy 2000 theme._

## Platforms

- [GNOME Shell extension](apps/gnome/README.md) — production implementation for
  GNOME Shell 45–50.
- [macOS menu-bar app](apps/macos/README.md) — native Swift/SwiftUI
  implementation targeting macOS 13 and newer.

## Repository layout

```text
apps/gnome/   GNOME Shell runtime, tests, and release staging
apps/macos/   Swift package, menu-bar application, collector, and tests
shared/       JSON contracts, golden fixtures, locales, and theme resources
tools/        Shared artwork and validation tools
```

## Common commands

```bash
make check          # Shared and GNOME checks available on Linux
make pack           # Backward-compatible GNOME release ZIP
make check-macos    # Swift/core and Xcode checks when their toolchains exist
make pack-macos     # Signed/notarized packaging requires macOS credentials
make clean          # Remove local builds, caches, and generated animation previews
```

The existing `make check`, `make pack`, `./install.sh`, and `./uninstall.sh`
commands retain their GNOME behavior. GitHub Actions are intentionally not
used; validation and releases are performed locally.

`make clean` removes only known generated outputs. It preserves the accepted
runtime artwork and the current v16/v18 animation sources, rigs, and fixtures.

Code is licensed under the [MIT License](LICENSE). Fallout/Pip-Boy/Vault
Boy-inspired raster artwork is excluded from that license; read [NOTICE.md](NOTICE.md)
before redistributing source or binaries containing it.
