# Changelog

All notable changes to Agents Tray Limits are documented in this file.

The project uses the integer version in `metadata.json`; Git release tags use the corresponding `vN` form.

## [Unreleased]

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

[Unreleased]: https://github.com/RealLeo/agents-tray-limits/compare/v14...HEAD
[14]: https://github.com/RealLeo/agents-tray-limits/releases/tag/v14
