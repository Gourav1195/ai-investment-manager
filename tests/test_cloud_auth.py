from __future__ import annotations

from src.investing.cloud_auth import _configured_password


def test_configured_password_reads_environment(monkeypatch) -> None:
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    assert _configured_password() is None
    monkeypatch.setenv("APP_PASSWORD", "secret")
    assert _configured_password() == "secret"
