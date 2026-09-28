from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.investing.orchestration import UniverseRunResult
from src.investing.orchestration_notifications import (
    NotificationConfig,
    format_orchestration_notification,
    notification_config_from_env,
    notify_orchestration_result,
    should_notify,
)


def _result(skipped: tuple[tuple[str, str], ...] = ()) -> UniverseRunResult:
    return UniverseRunResult(
        run_key="run-1",
        index_name="NIFTY 50",
        as_of_dates=("2025-06-30T18:29:59.999999+05:30",),
        symbols_requested=2,
        symbols_evaluated=2 - len(skipped),
        records_persisted=1,
        skipped_symbols=skipped,
        archive_status="skipped",
    )


def test_should_notify_only_when_skipped_by_default() -> None:
    config = NotificationConfig(
        mode="skipped",
        output_file=Path("work/notify.log"),
    )

    assert should_notify(_result((("MISSING", "no data"),)), config)
    assert not should_notify(_result(), config)


def test_notification_config_from_env_defaults_to_skipped_when_channel_set() -> None:
    config = notification_config_from_env(
        {
            "INVESTING_NOTIFY_WEBHOOK_URL": "https://example.com/hook",
        }
    )

    assert config.mode == "skipped"
    assert config.webhook_url == "https://example.com/hook"


def test_notify_writes_file_when_symbols_skipped(tmp_path) -> None:
    output = tmp_path / "orchestration.log"
    config = NotificationConfig(mode="skipped", output_file=output)

    delivered = notify_orchestration_result(
        _result((("MISSING", "no fundamentals"),)),
        config,
    )

    assert delivered == [f"file:{output}"]
    assert "MISSING" in output.read_text(encoding="utf-8")


@patch("src.investing.orchestration_notifications._post_webhook")
def test_notify_posts_webhook_for_skipped_symbols(mock_post: MagicMock) -> None:
    config = NotificationConfig(
        mode="skipped",
        webhook_url="https://example.com/hook",
    )

    delivered = notify_orchestration_result(
        _result((("MISSING", "no fundamentals"),)),
        config,
    )

    assert delivered == ["webhook"]
    mock_post.assert_called_once()
    payload = mock_post.call_args.args[1]
    assert payload["skipped_count"] == 1
    assert payload["skipped_symbols"][0]["symbol"] == "MISSING"


def test_format_orchestration_notification_lists_skipped_symbols() -> None:
    text = format_orchestration_notification(
        _result((("AAA", "reason a"), ("BBB", "reason b")))
    )

    assert "AAA: reason a" in text
    assert "Skipped symbols: 2" in text
