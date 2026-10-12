"""Load read-only Kite Connect credentials from environment or a local file."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path

DEFAULT_KITE_CONFIG_PATH = Path("work/kite.local.json")


@dataclass(frozen=True)
class KiteCredentials:
    api_key: str
    access_token: str
    api_secret: str | None = None


def load_kite_credentials(
    config_path: str | Path | None = None,
) -> KiteCredentials:
    path = Path(config_path) if config_path else DEFAULT_KITE_CONFIG_PATH
    file_values: dict[str, str] = {}
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Kite config must be a JSON object: {path}")
        file_values = {str(key): str(value) for key, value in payload.items()}

    api_key = os.environ.get("KITE_API_KEY") or file_values.get("api_key")
    access_token = os.environ.get("KITE_ACCESS_TOKEN") or file_values.get("access_token")
    api_secret = os.environ.get("KITE_API_SECRET") or file_values.get("api_secret")

    if not api_key or not access_token:
        raise ValueError(
            "Kite credentials are missing. Set KITE_API_KEY and KITE_ACCESS_TOKEN "
            f"or create {DEFAULT_KITE_CONFIG_PATH} with api_key and access_token."
        )
    return KiteCredentials(
        api_key=api_key.strip(),
        access_token=access_token.strip(),
        api_secret=api_secret.strip() if api_secret else None,
    )
