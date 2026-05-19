"""Persistent HUD preference storage."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)


class HUDPreferences:
    """Small JSON store for rider-adjustable HUD settings."""

    def __init__(self, path: Path | str | None = "settings/hud_settings.json") -> None:
        self.path = Path(path) if path is not None else None

    def load(self) -> dict[str, Any]:
        if self.path is None or not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("HUD preferences could not be loaded from %s: %s", self.path, exc)
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, preferences: dict[str, Any]) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(preferences, handle, indent=2, sort_keys=True)
                handle.write("\n")
            temp_path.replace(self.path)
        except OSError as exc:
            LOGGER.warning("HUD preferences could not be saved to %s: %s", self.path, exc)
