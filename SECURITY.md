# Security Policy

## Supported versions

Security fixes are provided for the latest published release. Upgrade to the newest release before reporting a problem that may already have been fixed.

## Report a vulnerability privately

Do not open a public issue for a suspected vulnerability or include secrets in logs, screenshots, or attachments.

Use [GitHub private vulnerability reporting](https://github.com/RealLeo/agents-tray-limits/security/advisories/new) and include:

  - the installed application version and GNOME Shell or macOS version;
- distribution and session type (Wayland or X11);
- affected component and expected security boundary;
- minimal reproduction steps or a proof of concept;
- impact and any known workarounds;
- sanitized logs with account email, tokens, paths, and identifiers removed.

Please allow maintainers time to confirm, fix, and release a correction before public disclosure. If private vulnerability reporting is unavailable, open a public issue containing no exploit details and ask the maintainer for a private contact channel.

## Security boundaries

Agents Tray Limits starts the locally installed Codex CLI and reads account and rate-limit data from Codex App Server. The macOS application also installs an optional local Claude status-line collector. Reports are particularly useful when they concern:

- execution of an unintended binary or arguments;
- unsafe handling of configured executable paths;
- user-theme path traversal or symbolic-link bypasses;
- disclosure or persistence of Codex credentials or account data;
- unsafe extension installation, archive extraction, or update behavior.
- unsafe Claude collector installation, delegation, restoration, or cache permissions.

General Codex or GNOME vulnerabilities that reproduce without this extension should be reported to the relevant upstream project.
