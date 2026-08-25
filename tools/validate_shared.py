#!/usr/bin/env python3
"""Validate dependency-free shared contracts, fixtures, locales, and themes."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"
STATUSES = ("good", "worried", "critical", "dead")
PROFILE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
THEME_ID = re.compile(r"^[a-z0-9_-]+$")
COLOR = re.compile(r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def safe_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or value.startswith(("/", "~")):
        return False
    if "\\" in value:
        return False
    return all(part not in {"", ".", ".."} for part in value.split("/"))


def validate_schema_documents() -> None:
    for path in sorted((SHARED / "contracts").glob("*.schema.json")):
        schema = read_object(path)
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise ValueError(f"{path}: unsupported JSON Schema draft")
        if not schema.get("$id") or not schema.get("title"):
            raise ValueError(f"{path}: schema identity is incomplete")


def validate_fixtures() -> None:
    for path in sorted((SHARED / "fixtures").glob("*.json")):
        value = read_object(path)
        for key in ("ok", "profileId", "provider", "fetchedAt"):
            if key not in value:
                raise ValueError(f"{path}: missing {key}")
        if value["provider"] not in {"codex", "claude"}:
            raise ValueError(f"{path}: invalid provider")
        if not PROFILE_ID.fullmatch(str(value["profileId"])):
            raise ValueError(f"{path}: invalid profile id")
        if value["ok"] is True and not isinstance(value.get("rateLimits"), dict):
            raise ValueError(f"{path}: successful fixture needs rateLimits")
        if value["ok"] is False and not all(value.get(key) for key in ("errorCode", "message")):
            raise ValueError(f"{path}: error fixture needs errorCode and message")

    malformed = (SHARED / "fixtures" / "malformed-json.txt").read_text(encoding="utf-8")
    try:
        json.loads(malformed)
    except json.JSONDecodeError:
        pass
    else:
        raise ValueError("malformed-json.txt must remain invalid JSON")


def validate_locales() -> None:
    catalogs = {
        path.stem: read_object(path)
        for path in sorted((SHARED / "locales").glob("*.json"))
    }
    if set(catalogs) != {"en", "ru", "de", "fr", "zh-CN"}:
        raise ValueError("shared locales must contain exactly five supported catalogs")
    english_keys = set(catalogs["en"])
    translation_keys = english_keys - {"_meta"}
    if len(translation_keys) != 213:
        raise ValueError(f"English locale must retain the 213-key baseline, found {len(translation_keys)}")
    for language, catalog in catalogs.items():
        if set(catalog) != english_keys:
            raise ValueError(f"{language}: locale key set differs from English")


def validate_theme(path: Path) -> None:
    manifest = read_object(path / "theme.json")
    version = manifest.get("version")
    if version not in {1, 2}:
        raise ValueError(f"{path}: unsupported manifest version")
    theme_id = manifest.get("id")
    if not isinstance(theme_id, str) or not THEME_ID.fullmatch(theme_id) or theme_id == "classic":
        raise ValueError(f"{path}: invalid theme id")
    if theme_id != path.name:
        raise ValueError(f"{path}: theme id must match directory")
    for section in ("art", "panelArt"):
        values = manifest.get(section)
        if section == "panelArt" and values is None:
            continue
        if not isinstance(values, dict) or set(values) != set(STATUSES):
            raise ValueError(f"{path}: {section} must contain four statuses")
        for value in values.values():
            if not safe_path(value) or not (path / value).is_file() or (path / value).is_symlink():
                raise ValueError(f"{path}: unsafe or missing {section} asset {value}")
    if version == 2:
        platforms = manifest.get("platforms")
        if not isinstance(platforms, dict) or not platforms:
            raise ValueError(f"{path}: v2 requires platforms")
        gnome = platforms.get("gnome")
        if isinstance(gnome, dict):
            if gnome.get("layout") not in {None, "pipboy-2000", "video-deck"}:
                raise ValueError(f"{path}: invalid GNOME layout")
            stylesheet = gnome.get("stylesheet")
            if stylesheet is not None and (
                not safe_path(stylesheet)
                or not (path / stylesheet).is_file()
                or (path / stylesheet).is_symlink()
            ):
                raise ValueError(f"{path}: unsafe or missing GNOME stylesheet")
        macos = platforms.get("macos")
        if isinstance(macos, dict):
            if macos.get("layout") not in {"classic", "pipboy-2000", "pipboy-3000"}:
                raise ValueError(f"{path}: invalid macOS layout")
            palette = macos.get("palette", {})
            if not isinstance(palette, dict) or not all(COLOR.fullmatch(str(value)) for value in palette.values()):
                raise ValueError(f"{path}: invalid macOS palette")


def main() -> int:
    validate_schema_documents()
    validate_fixtures()
    validate_locales()
    for path in sorted(item for item in (SHARED / "themes").iterdir() if item.is_dir()):
        validate_theme(path)
    print("shared contracts, fixtures, locales, and themes: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
