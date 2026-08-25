# Changelog

All notable changes to Agents Tray Limits are documented in this file.

The project uses the integer version in `metadata.json`; Git release tags use the corresponding `vN` form.

## [Unreleased]

### Added

- Added the built-in Night Video Deck theme: a 680×520 VCR/CRT GNOME layout with one gray tabby across four resource states, localized hardware controls, subtle CRT motion, and a Classic fallback on macOS.
- Extended theme manifest v2 with the GNOME `video-deck` layout.

## [18] - 2026-08-25

### Changed

- Rebuilt the Fallout 2 `worried` and `critical` scenes as deterministic 32-frame animations matching the accepted `good` pipeline.
- Made the seated X-eyed `dead` state explicitly static and extended theme manifests to accept one-frame states.
- Standardized animated Fallout 2 states on a 28 ms frame interval.

### Fixed

- Status art now follows the rounded percentage shown to the user, so a displayed `0%` always selects `dead`.
- Used-percentage mode is now the exact complement of the rounded remaining percentage.

### Release

- Bumped the extension metadata version to 18.

## [17] - 2026-08-24

### Added

- Added explicit, isolated Codex and Claude Code profiles with a persistent active-profile selector in every menu layout.
- Added reversible Claude Code status-line collection for documented five-hour and seven-day subscription limits.
- Added profile creation, editing, removal, copied sign-in commands, localized states, and contextual provider links.

### Changed

- Refreshes now keep independent data, error, process, and loading state per profile and run at most three helper processes concurrently.
- Additional Codex profiles use their own `CODEX_HOME` and force the file credential store without exposing credentials to the extension.
- Bumped the extension metadata version to 17 and included the profile runtime module in release staging.

### Security

- Claude caches contain only percentages, reset times, version, and update time; credentials and unrelated status-line input are never persisted.
- Claude status-line installation and restoration are atomic, preserve the exact prior setting, and refuse conflicting changes.
- Uninstallation attempts to restore every configured Claude status line; the self-contained collector also supports `--restore`.

## [16] - 2026-08-24

### Changed

- Integrated the staged Blender 2D `good` animation into the Fallout 2 theme for live interface review.
- Increased the `good` sequence to 32 frames, shortened it to 28 ms per frame, and extended manifest v1 with optional per-status intervals.

### Fixed

- Removed the moving shoulder's internal outline and late depth-plane flicker.

## [15] - 2026-08-23

### Changed

- Rebuilt all four Fallout 2 character animations from a deterministic layered 2D rig.
- Increased each one-shot sequence from 10 to 16 frames while keeping a compact 750 ms duration.
- Extended theme manifest v1 frame animations to accept 2–24 safe raster frames per state.

### Fixed

- Removed character, arm, and body-shape drift caused by independently drawn animation frames.
- Kept direct single-frame switching without opacity crossfades or optical-flow deformation.

## [14] - 2026-08-23

### Added

- Initial public release as Agents Tray Limits.
- English, Russian, German, French, and Simplified Chinese interfaces.
- Automatic system-language detection with English fallback and a manual language selector.
- Clean source and release packaging, CI checks, and tagged GitHub releases.
- English project, contribution, security, and licensing documentation.

### Changed

- Adopted the UUID `agents-tray-limits@realleo` and GSettings schema `org.gnome.shell.extensions.agents-tray-limits`.
- Made `fallout-2` the theme selected for new installations, while retaining `classic` as the protected fallback.
- Moved user themes to `~/.local/share/agents-tray-limits/themes/`.

### Compatibility

- This is a separate extension and does not automatically import settings from `chatgpt-usage@realleo`.
- The legacy theme ID `pipboy-classic` continues to migrate to `fallout-3`.

[Unreleased]: https://github.com/RealLeo/agents-tray-limits/compare/v18...HEAD
[18]: https://github.com/RealLeo/agents-tray-limits/releases/tag/v18
[17]: https://github.com/RealLeo/agents-tray-limits/releases/tag/v17
[16]: https://github.com/RealLeo/agents-tray-limits/releases/tag/v16
[15]: https://github.com/RealLeo/agents-tray-limits/releases/tag/v15
[14]: https://github.com/RealLeo/agents-tray-limits/releases/tag/v14
