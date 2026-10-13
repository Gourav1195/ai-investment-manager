from __future__ import annotations

import time

from src.investing.auth_remember import mint_remember_token, verify_remember_token


def test_remember_token_round_trip(monkeypatch) -> None:
    monkeypatch.setenv("APP_AUTH_SIGNING_KEY", "test-signing-key")
    token = mint_remember_token("secret-password", ttl_seconds=3600)
    assert verify_remember_token(token, "secret-password")
    assert not verify_remember_token(token, "wrong-password")


def test_remember_token_expires(monkeypatch) -> None:
    monkeypatch.setenv("APP_AUTH_SIGNING_KEY", "test-signing-key")
    token = mint_remember_token("secret-password", ttl_seconds=-10)
    assert not verify_remember_token(token, "secret-password")
