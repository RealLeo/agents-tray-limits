# Agents Tray Limits

Agents Tray Limits is a GNOME Shell extension that shows ChatGPT/Codex subscription rate limits in the top panel. Its menu includes all rate-limit windows returned by the local Codex App Server, reset times, account details, and optional token statistics.

> [!IMPORTANT]
> This is an unofficial community project. It is not affiliated with, endorsed by, or sponsored by OpenAI, Bethesda Softworks, ZeniMax Media, GNOME, or their affiliates. See [Licensing and artwork](#licensing-and-artwork) before redistributing the extension.

## Features

- A compact panel value such as `65% · reset 4d 22h`, calculated from the primary Codex window.
- Remaining-usage and used-usage display modes.
- Detailed primary, secondary, and additional rate-limit groups in the menu.
- Reset countdowns and optional token statistics.
- Automatic Codex CLI discovery, including NVM, Volta, Bun, pnpm, asdf, and mise installations.
- Three built-in themes:
  - `fallout-2`, the default Pip-Boy 2000-inspired theme with one-shot character animations;
  - `fallout-3`, a bright green CRT-inspired theme;
  - `classic`, the native GNOME-style fallback.
- Declarative user themes without executable theme code.
- English, Russian, German, French, and Simplified Chinese interfaces.
- Automatic system-language selection with English fallback, plus a manual language override.

The extension reports only the subscription limits exposed by Codex App Server. It does not scrape ChatGPT, and it does not report OpenAI API billing or arbitrary model-specific message limits that Codex does not expose.

## Requirements

- GNOME Shell 45–50;
- Python 3;
- Codex CLI;
- a Codex session authenticated with **Sign in with ChatGPT**.

Check your GNOME version:

```bash
gnome-shell --version
```

Install and start Codex using the official installer:

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
codex
```

Choose **Sign in with ChatGPT** during authentication. An API-key-only or Bedrock login cannot expose ChatGPT subscription limits.

## Install from a release

1. Download `agents-tray-limits@realleo.zip` from the [latest release](https://github.com/RealLeo/agents-tray-limits/releases/latest).
2. Install and enable the extension:

```bash
gnome-extensions install --force ./agents-tray-limits@realleo.zip
gnome-extensions enable agents-tray-limits@realleo
```

3. Open its preferences:

```bash
gnome-extensions prefs agents-tray-limits@realleo
```

On Wayland, GNOME Shell may not discover a newly installed extension until you sign out and sign back in. Do not use `gnome-shell --replace`; it can terminate or destabilize the active session.

If the former `chatgpt-usage@realleo` extension is installed, disable it manually to avoid two panel indicators:

```bash
gnome-extensions disable chatgpt-usage@realleo
```

Agents Tray Limits is a separate extension and does not import the former extension's settings automatically.

## Install from source

```bash
git clone https://github.com/RealLeo/agents-tray-limits.git
cd agents-tray-limits
make check
make pack
./install.sh
```

The packaged extension is written to `dist/agents-tray-limits@realleo.zip`, with a SHA-256 checksum next to it.

To update a source installation, pull the new source, rerun the checks, and reinstall:

```bash
git pull --ff-only
make check
./install.sh
```

If GNOME retains old JavaScript modules after an update, sign out and sign back in. Do not restart GNOME Shell with `--replace`.

To uninstall:

```bash
./uninstall.sh
```

## Settings

The preferences window provides:

- **Language:** System, English, Russian, German, French, or Simplified Chinese. System mode is the default; unsupported system languages fall back to English.
- **Display:** show either the remaining or used percentage.
- **Refresh interval:** from one minute to one hour.
- **Panel icon:** show or hide the state icon after the panel text.
- **Theme:** choose a built-in or user theme. `fallout-2` is selected on new installations; invalid or missing themes safely fall back to `classic`.
- **Theme animation:** disable the large menu artwork animation. GNOME's system animation preference is also respected.
- **Detailed limits and tokens:** show all returned limit groups and token statistics.
- **Codex CLI path:** explicitly select the Codex launcher if GNOME Shell cannot see your normal terminal `PATH`.

Language changes update the panel and an open menu without requesting fresh data. Stable helper errors are translated; unknown technical details remain available in the journal.

## How status is calculated

The top panel uses only the primary window of the main Codex group. Secondary windows and groups such as Spark remain visible in the detailed menu but do not affect the panel value or character state.

Character states are based on the **remaining** primary percentage, even when the numeric display is set to used percentage:

| Remaining | State |
| ---: | --- |
| `0%` | Dead |
| `1–20%` | Critical |
| `21–50%` | Worried |
| `51–100%` | Good |

## User themes

Place each theme in its own directory below:

```text
~/.local/share/agents-tray-limits/themes/
└── my-theme/
    ├── theme.json
    ├── theme.css
    └── assets/
        ├── good.png
        ├── worried.png
        ├── critical.png
        └── dead.png
```

A minimal manifest uses schema version 1:

```json
{
  "version": 1,
  "id": "my-theme",
  "name": "My Theme",
  "description": "A custom theme",
  "stylesheet": "theme.css",
  "art": {
    "good": "assets/good.png",
    "worried": "assets/worried.png",
    "critical": "assets/critical.png",
    "dead": "assets/dead.png"
  }
}
```

Theme IDs may contain lowercase ASCII letters, digits, `_`, and `-`; the directory name must equal the ID. The four `art` images are required. Optional `panelArt` can provide four separate panel icons. A `frameAnimation` can provide 2–10 raster frames for every state, while the older `animation` field defines transform steps; the two animation forms are mutually exclusive.

All manifest paths must resolve to regular raster files inside the theme directory. Absolute paths, `..` traversal, and symbolic links are rejected. User themes may override built-in IDs except for the reserved `classic` theme. Use **Reload themes** in preferences after editing a theme.

Theme names and descriptions from user manifests are displayed exactly as authored. Built-in theme metadata follows the selected interface language.

## Privacy

Agents Tray Limits starts the local `codex app-server` process and uses its account, rate-limit, and token-usage read methods. Authentication remains managed by Codex CLI. The extension:

- does not request or store an API key;
- does not read browser cookies;
- does not store access or refresh tokens;
- does not send account data to third-party services;
- displays the account email only in the local menu.

## Troubleshooting

Run the installed helper directly:

```bash
/usr/bin/python3 ~/.local/share/gnome-shell/extensions/agents-tray-limits@realleo/bin/agents-tray-limits-helper.py --pretty
```

A successful response includes `"ok": true`. Common errors include:

- `codex_not_found`: install Codex or set its path in preferences;
- `not_logged_in`: run `codex` and sign in with ChatGPT;
- `unsupported_auth`: switch from API-key or Bedrock authentication to ChatGPT authentication;
- `codex_too_old`: update Codex CLI;
- `app_server_stopped`: check that the Codex launcher uses a compatible Node.js runtime;
- `timeout`: check connectivity and retry.

Inspect current extension state and the GNOME Shell journal:

```bash
gnome-extensions info agents-tray-limits@realleo
journalctl --user -f -o cat /usr/bin/gnome-shell
```

If all user extensions were disabled after a session failure, re-enable the global extension switch and then this extension from the GNOME Extensions application. Do not run a second GNOME Shell process.

## Development

Install the development dependencies available from your distribution: Python 3, Node.js, GJS, GLib schema tools, `zip`, and `unzip`. Then run:

```bash
make check
make pack
unzip -t dist/agents-tray-limits@realleo.zip
```

`make check` validates JavaScript, Python, schemas, translations, themes, UI source contracts, and the helper test suite. `make pack` creates a clean runtime archive with compiled schemas and a checksum.

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution rules and [SECURITY.md](SECURITY.md) for private vulnerability reporting.

## Official documentation

- [Codex App Server](https://developers.openai.com/codex/app-server)
- [Codex CLI](https://developers.openai.com/codex/cli)
- [GNOME Shell extension development](https://gjs.guide/extensions/)

## Licensing and artwork

Source code is available under the [MIT License](LICENSE), copyright © 2026 RealLeo.

The MIT License **does not apply** to the Fallout/Pip-Boy/Vault Boy-inspired raster artwork under `themes/fallout-2/assets/` and `themes/fallout-3/assets/`. Those assets may incorporate third-party intellectual property. No additional rights to that intellectual property are granted by this repository. Read [NOTICE.md](NOTICE.md) before copying or redistributing a build that contains the artwork.

