"""Lightweight UI preferences persisted beside portfolio data."""

from __future__ import annotations

import json
from pathlib import Path


class AppPreferences:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def get_display_name(self) -> str:
        data = self._read()
        return str(data.get("display_name") or "").strip()

    def set_display_name(self, name: str) -> None:
        data = self._read()
        data["display_name"] = name.strip()
        self._write(data)

    def get_onboarding_complete(self) -> bool:
        return bool(self._read().get("onboarding_complete"))

    def set_onboarding_complete(self, value: bool) -> None:
        data = self._read()
        data["onboarding_complete"] = bool(value)
        self._write(data)

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict[str, object]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
