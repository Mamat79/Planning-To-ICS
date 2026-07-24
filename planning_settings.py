"""Persistent application settings shared by desktop interfaces."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from planning_to_ics import OUTPUT_DIR, SOURCE_DIR

SETTINGS_KEYS = {"planning_dir", "output_dir", "dark_mode"}


def settings_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Planning To ICS" / "settings.json"
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "Planning To ICS" / "settings.json"
    return Path.home() / ".planning_to_ics" / "settings.json"


def default_settings() -> dict[str, str]:
    return {
        "planning_dir": str(SOURCE_DIR),
        "output_dir": str(OUTPUT_DIR),
        "dark_mode": "false",
    }


def load_settings() -> dict[str, str]:
    settings = default_settings()
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except Exception:
        return settings
    if isinstance(data, dict):
        for key in SETTINGS_KEYS:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                settings[key] = value.strip()
            elif key == "dark_mode" and isinstance(value, bool):
                settings[key] = "true" if value else "false"
    return settings


def save_settings(updates: dict[str, str]) -> dict[str, str]:
    settings = load_settings()
    for key, value in updates.items():
        if key in SETTINGS_KEYS and isinstance(value, str) and value.strip():
            settings[key] = value.strip()
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return settings


def import_settings(data: object) -> dict[str, str]:
    if not isinstance(data, dict):
        raise ValueError("Fichier de réglages invalide.")
    updates = {
        key: ("true" if value else "false") if isinstance(value, bool) else value.strip()
        for key, value in data.items()
        if key in SETTINGS_KEYS
        and (isinstance(value, bool) or (isinstance(value, str) and value.strip()))
    }
    if not updates:
        raise ValueError("Aucun réglage valide dans le fichier.")
    return save_settings(updates)


def reset_settings() -> dict[str, str]:
    try:
        settings_path().unlink()
    except FileNotFoundError:
        pass
    return default_settings()
