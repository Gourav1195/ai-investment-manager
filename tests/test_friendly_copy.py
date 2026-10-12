from __future__ import annotations

from src.investing.friendly_copy import friendly_import_error, friendly_runtime_error


def test_friendly_import_error_includes_console_hint() -> None:
    message = friendly_import_error("equity-holdings", "bad column")
    assert "Console" in message
    assert "Holdings" in message


def test_friendly_runtime_error_hides_stack_tone() -> None:
    message = friendly_runtime_error(TimeoutError("connection timed out"))
    assert "too long" in message.lower() or "connection" in message.lower()
    assert "Traceback" not in message
