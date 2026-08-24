#!/usr/bin/env python3
"""Create and validate the curated Agents Tray Limits runtime package."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = (ROOT / "build").resolve()
UUID = "agents-tray-limits@realleo"
TOP_LEVEL_FILES = (
    "metadata.json",
    "extension.js",
    "prefs.js",
    "stylesheet.css",
    "themeLogic.js",
    "profileLogic.js",
    "themeLoader.js",
    "LICENSE",
    "NOTICE.md",
)
OPTIONAL_TOP_LEVEL_FILES = ("i18n.js",)
FORBIDDEN_PARTS = {
    ".git",
    ".github",
    "art-source",
    "docs",
    "tests",
    "tools",
    "__pycache__",
}
CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^)'\"]+)\1\s*\)")


def fail(message: str) -> None:
    raise ValueError(message)


def safe_source(base: Path, relative: str) -> Path:
    candidate = base / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        fail(f"unsafe runtime path: {relative}")
    if candidate.is_symlink() or not candidate.is_file():
        fail(f"runtime file must be a regular non-symlink file: {candidate}")
    resolved_base = base.resolve()
    resolved_candidate = candidate.resolve()
    if resolved_candidate != resolved_base and resolved_base not in resolved_candidate.parents:
        fail(f"runtime file escapes its source directory: {candidate}")
    return candidate


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def iter_manifest_assets(manifest: dict[str, Any]) -> Iterable[str]:
    for section_name in ("art", "panelArt"):
        section = manifest.get(section_name)
        if isinstance(section, dict):
            for value in section.values():
                if isinstance(value, str):
                    yield value

    frame_animation = manifest.get("frameAnimation")
    frames = frame_animation.get("frames") if isinstance(frame_animation, dict) else None
    if isinstance(frames, dict):
        for sequence in frames.values():
            if isinstance(sequence, list):
                for value in sequence:
                    if isinstance(value, str):
                        yield value


def stage_theme(theme_dir: Path, destination: Path) -> None:
    manifest_path = safe_source(theme_dir, "theme.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    copy_file(manifest_path, destination / "theme.json")

    referenced = set(iter_manifest_assets(manifest))
    stylesheet = manifest.get("stylesheet")
    if isinstance(stylesheet, str) and stylesheet:
        stylesheet_path = safe_source(theme_dir, stylesheet)
        stylesheet_text = stylesheet_path.read_text(encoding="utf-8")
        copy_file(stylesheet_path, destination / stylesheet)
        for _quote, value in CSS_URL_RE.findall(stylesheet_text):
            if not value.startswith(("data:", "resource:")):
                referenced.add(value)

    for relative in sorted(referenced):
        copy_file(safe_source(theme_dir, relative), destination / relative)


def stage_locales(destination: Path) -> None:
    source = ROOT / "locales"
    if not source.is_dir():
        return
    for path in source.rglob("*"):
        if path.is_file() and not path.is_symlink() and path.suffix in {".js", ".json"}:
            copy_file(path, destination / path.relative_to(source))


def build(stage: Path) -> None:
    metadata = json.loads((ROOT / "metadata.json").read_text(encoding="utf-8"))
    if metadata.get("uuid") != UUID:
        fail(f"metadata UUID must be {UUID}")

    stage = stage.resolve()
    if stage == BUILD_ROOT or BUILD_ROOT not in stage.parents:
        fail(f"staging directory must be inside {BUILD_ROOT}: {stage}")
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    for relative in TOP_LEVEL_FILES:
        copy_file(safe_source(ROOT, relative), stage / relative)
    for relative in OPTIONAL_TOP_LEVEL_FILES:
        if (ROOT / relative).is_file():
            copy_file(safe_source(ROOT, relative), stage / relative)

    copy_file(
        safe_source(ROOT / "bin", "agents-tray-limits-helper.py"),
        stage / "bin" / "agents-tray-limits-helper.py",
    )
    copy_file(
        safe_source(ROOT / "icons", "agents-tray-limits-symbolic.svg"),
        stage / "icons" / "agents-tray-limits-symbolic.svg",
    )
    copy_file(
        safe_source(
            ROOT / "schemas",
            "org.gnome.shell.extensions.agents-tray-limits.gschema.xml",
        ),
        stage / "schemas" / "org.gnome.shell.extensions.agents-tray-limits.gschema.xml",
    )
    stage_locales(stage / "locales")

    themes_root = ROOT / "themes"
    for theme_dir in sorted(path for path in themes_root.iterdir() if path.is_dir()):
        if theme_dir.is_symlink():
            fail(f"theme directory must not be a symlink: {theme_dir}")
        stage_theme(theme_dir, stage / "themes" / theme_dir.name)


def verify(archive: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        names = [name for name in bundle.namelist() if not name.endswith("/")]
        if not names:
            fail("release archive is empty")
        for name in names:
            path = Path(name)
            if path.is_absolute() or ".." in path.parts:
                fail(f"unsafe archive member: {name}")
            if FORBIDDEN_PARTS.intersection(path.parts):
                fail(f"forbidden release member: {name}")
            if path.name.lower() in {
                "readme.md",
                "changelog.md",
                "contributing.md",
                "security.md",
            }:
                fail(f"documentation must not be included in the runtime ZIP: {name}")

        required = {
            "metadata.json",
            "LICENSE",
            "NOTICE.md",
            "extension.js",
            "profileLogic.js",
            "i18n.js",
            "prefs.js",
            "locales/en.json",
            "locales/ru.json",
            "locales/de.json",
            "locales/fr.json",
            "locales/zh-CN.json",
            "schemas/gschemas.compiled",
            "bin/agents-tray-limits-helper.py",
            "icons/agents-tray-limits-symbolic.svg",
            "themes/fallout-2/theme.json",
            "themes/fallout-3/theme.json",
        }
        missing = required.difference(names)
        if missing:
            fail("release archive is missing: " + ", ".join(sorted(missing)))

        metadata = json.loads(bundle.read("metadata.json"))
        if metadata.get("uuid") != UUID:
            fail(f"release metadata UUID must be {UUID}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", nargs="?", type=Path, help="Destination staging directory")
    parser.add_argument("--verify", type=Path, metavar="ZIP", help="Validate an existing release ZIP")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.verify:
            verify(args.verify)
        elif args.stage:
            build(args.stage.resolve())
        else:
            fail("provide a staging directory or --verify ZIP")
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(f"release staging error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
