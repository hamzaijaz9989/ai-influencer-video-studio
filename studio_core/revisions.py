"""Safe, allowlisted render revisions loaded from a user-editable JSON file."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "silence_threshold_db": -38,
    "silence_min_seconds": 5.0,
    "smart_zoom_strength": 0.06,
}

BOUNDS = {
    "silence_threshold_db": (-60, -20),
    "silence_min_seconds": (1.0, 20.0),
    "smart_zoom_strength": (0.0, 0.15),
}


def load_revisions(path: Path | None) -> dict[str, Any]:
    """Load only known numeric controls; reject malformed or unsafe values."""
    settings = dict(DEFAULTS)
    if path is None or not path.exists():
        return settings
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read revision file {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Revision file must contain a JSON object.")
    unknown = sorted(set(raw) - set(DEFAULTS))
    if unknown:
        raise ValueError("Unsupported revision setting(s): " + ", ".join(unknown))
    for key, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be a number.")
        low, high = BOUNDS[key]
        if not low <= value <= high:
            raise ValueError(f"{key} must be between {low} and {high}.")
        settings[key] = value
    return settings
