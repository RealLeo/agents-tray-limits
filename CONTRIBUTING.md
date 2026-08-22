# Contributing

Thank you for helping improve Agents Tray Limits.

## Before you start

- Search existing issues and pull requests before opening a duplicate.
- Use an issue to discuss changes that alter behavior, settings, theme manifests, dependencies, or supported GNOME versions.
- Never include credentials, Codex authentication files, access tokens, private account data, or unredacted diagnostic output.
- Do not contribute copyrighted characters, logos, screenshots, music, or other assets unless you have the rights and can document the applicable license.

## Development setup

Install Python 3, Node.js, GJS, GLib schema tools, `zip`, and `unzip`, then clone the repository:

```bash
git clone https://github.com/RealLeo/agents-tray-limits.git
cd agents-tray-limits
make check
make pack
```

Install the development copy with `./install.sh`. On Wayland, sign out and sign back in if GNOME Shell does not discover new modules. Never use `gnome-shell --replace` to reload this extension.

## Making changes

- Keep the extension compatible with every GNOME Shell version listed in `metadata.json`.
- Preserve the declarative, non-executable user-theme format and its path-traversal and symlink protections.
- Keep helper output machine-readable and use stable `errorCode` values for user-facing failures.
- Add or update tests for behavior changes.
- Keep source, settings-schema, helper, installation paths, and documentation aligned with `agents-tray-limits@realleo`.
- Avoid committing generated files such as `dist/`, `gschemas.compiled`, `__pycache__`, previews, and contact sheets.

### Translations

English is the canonical catalog and fallback. When adding or changing a message:

1. Add the key to the English catalog.
2. Add the same key to Russian, German, French, and Simplified Chinese catalogs.
3. Preserve all interpolation placeholders exactly in every language.
4. Run the catalog completeness and formatting tests through `make check`.

Do not translate product names such as ChatGPT, Codex, or `PIP-BOY 2000`. The physical Pip-Boy action labels remain `REFRESH`, `CODEX`, `SETTINGS`, and `CLOSE`; their tooltips and accessibility labels are translated.

### Themes and assets

Custom themes should use original or properly licensed assets. Include source and licensing information for every contributed asset. A pull request may be rejected if asset rights are unclear.

The `classic` ID is reserved and cannot be overridden by a user theme. Avoid extending manifest schema version 1 unless a behavior cannot be represented safely by the existing declarative fields.

## Tests

Before submitting a pull request, run:

```bash
make check
make pack
unzip -t dist/agents-tray-limits@realleo.zip
```

Confirm that the release archive contains `schemas/gschemas.compiled` and does not contain Git metadata, tests, source artwork, cache files, or unused assets.

For UI changes, also test normal, loading, and error states on a supported GNOME Shell version. Verify extension enable/disable, preferences, menu lifecycle, language switching, and both animation-enabled and animation-disabled behavior.

## Pull requests

- Keep each pull request focused on one change.
- Explain the user-visible result, compatibility impact, and verification performed.
- Update `README.md` and `CHANGELOG.md` when behavior or installation changes.
- Do not include unrelated formatting or generated-file changes.
- Ensure all GitHub Actions checks pass.

By submitting code or documentation, you agree that your contribution is licensed under the project's MIT License. Asset contributions remain subject to their explicitly documented licenses and are not automatically covered by the MIT License.
