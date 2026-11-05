"""Crash-safe job tracking for the folder watcher.

A completed source is skipped after a Colab restart. Failed jobs remain retryable.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JobStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "jobs": {}}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if value.get("version") != 1 or not isinstance(value.get("jobs"), dict):
                raise ValueError("Unsupported job-state format")
            return value
        except Exception as exc:
            backup = self.path.with_suffix(self.path.suffix + ".corrupt")
            self.path.replace(backup)
            print(f"WARNING: invalid job state moved to {backup}: {exc}")
            return {"version": 1, "jobs": {}}

    @staticmethod
    def key(source: Path) -> str:
        stat = source.stat()
        return f"{source.resolve()}::{stat.st_size}::{stat.st_mtime_ns}"

    def status(self, key: str) -> str | None:
        item = self.data["jobs"].get(key)
        return item.get("status") if item else None

    def set(self, key: str, status: str, **details: Any) -> None:
        self.data["jobs"][key] = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **details,
        }
        self.save()

    def save(self) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        temporary.replace(self.path)
