"""Remembers the user's settings and output folder between runs (~/.snipbg/config.json)."""

import json
import os
from dataclasses import asdict

from core import Settings

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".snipbg")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


def _load_raw():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_raw(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _to_settings(raw) -> Settings:
    valid = {k: v for k, v in (raw or {}).items() if k in Settings.__dataclass_fields__}
    return Settings(**valid)


def load_settings() -> Settings:
    data = _load_raw()
    if "settings" in data:
        return _to_settings(data["settings"])
    # Older versions stored named presets; fall back to the last one used.
    last = data.get("last")
    if last and last in data.get("presets", {}):
        return _to_settings(data["presets"][last])
    return Settings()


def save_settings(settings: Settings):
    data = _load_raw()
    data["settings"] = asdict(settings)
    _save_raw(data)


def get_output_dir():
    return _load_raw().get("output", "")


def set_output_dir(path: str):
    data = _load_raw()
    data["output"] = path
    _save_raw(data)
