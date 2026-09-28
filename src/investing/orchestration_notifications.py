"""Optional notifications for universe orchestration runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import smtplib
from email.message import EmailMessage
from typing import Literal

import requests

from .filings import IST
from .orchestration import UniverseRunResult

NotifyMode = Literal["skipped", "always", "never"]


@dataclass(frozen=True)
class NotificationConfig:
    mode: NotifyMode = "never"
    webhook_url: str | None = None
    output_file: Path | None = None
    email_to: tuple[str, ...] = ()
    email_from: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True

    def is_configured(self) -> bool:
        return bool(self.webhook_url or self.output_file or self.email_to)


def notification_config_from_env(
    environ: dict[str, str] | None = None,
) -> NotificationConfig:
    values = environ or os.environ
    email_to = tuple(
        address.strip()
        for address in values.get("INVESTING_NOTIFY_EMAIL_TO", "").split(",")
        if address.strip()
    )
    output_file = values.get("INVESTING_NOTIFY_OUTPUT")
    webhook_url = values.get("INVESTING_NOTIFY_WEBHOOK_URL")
    mode = values.get("INVESTING_NOTIFY_ON", "never").strip().lower()
    if mode not in {"skipped", "always", "never"}:
        raise ValueError("INVESTING_NOTIFY_ON must be skipped, always, or never")
    if mode == "never" and (webhook_url or output_file or email_to):
        mode = "skipped"
    return NotificationConfig(
        mode=mode,
        webhook_url=webhook_url,
        output_file=Path(output_file) if output_file else None,
        email_to=email_to,
        email_from=values.get("INVESTING_NOTIFY_EMAIL_FROM"),
        smtp_host=values.get("INVESTING_SMTP_HOST"),
        smtp_port=int(values.get("INVESTING_SMTP_PORT", "587")),
        smtp_user=values.get("INVESTING_SMTP_USER"),
        smtp_password=values.get("INVESTING_SMTP_PASSWORD"),
        smtp_use_tls=values.get("INVESTING_SMTP_USE_TLS", "true").strip().lower()
        in {"1", "true", "yes", "on"},
    )


def should_notify(result: UniverseRunResult, config: NotificationConfig) -> bool:
    if config.mode == "never" or not config.is_configured():
        return False
    if config.mode == "always":
        return True
    return bool(result.skipped_symbols)


def format_orchestration_notification(result: UniverseRunResult) -> str:
    skipped_lines = [
        f"- {symbol}: {message}"
        for symbol, message in result.skipped_symbols[:20]
    ]
    skipped_section = (
        "\n".join(skipped_lines)
        if skipped_lines
        else "- none"
    )
    if len(result.skipped_symbols) > 20:
        skipped_section += f"\n- ... and {len(result.skipped_symbols) - 20} more"
    return (
        f"India research orchestration completed for {result.index_name}\n"
        f"Run key: {result.run_key}\n"
        f"Evaluated: {result.symbols_evaluated}/{result.symbols_requested}\n"
        f"Persisted snapshots: {result.records_persisted}\n"
        f"Skipped symbols: {len(result.skipped_symbols)}\n"
        f"{skipped_section}"
    )


def build_orchestration_payload(result: UniverseRunResult) -> dict[str, object]:
    return {
        "event": "orchestration_completed",
        "text": format_orchestration_notification(result),
        "run_key": result.run_key,
        "index_name": result.index_name,
        "symbols_requested": result.symbols_requested,
        "symbols_evaluated": result.symbols_evaluated,
        "records_persisted": result.records_persisted,
        "skipped_count": len(result.skipped_symbols),
        "skipped_symbols": [
            {"symbol": symbol, "reason": message}
            for symbol, message in result.skipped_symbols
        ],
        "archive_status": result.archive_status,
        "as_of_dates": list(result.as_of_dates),
    }


def notify_orchestration_result(
    result: UniverseRunResult,
    config: NotificationConfig,
    *,
    session: requests.Session | None = None,
) -> list[str]:
    """Deliver orchestration notifications when ``config`` says to."""

    if not should_notify(result, config):
        return []

    message = format_orchestration_notification(result)
    payload = build_orchestration_payload(result)
    delivered: list[str] = []

    if config.output_file is not None:
        _write_notification_file(config.output_file, message)
        delivered.append(f"file:{config.output_file}")

    if config.webhook_url:
        _post_webhook(config.webhook_url, payload, session=session)
        delivered.append("webhook")

    if config.email_to:
        _send_email(config, subject=_notification_subject(result), body=message)
        delivered.append("email")

    return delivered


def _notification_subject(result: UniverseRunResult) -> str:
    skipped = len(result.skipped_symbols)
    if skipped:
        return (
            f"[India Research] {result.index_name} orchestration skipped {skipped} symbols"
        )
    return f"[India Research] {result.index_name} orchestration completed"


def _write_notification_file(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=IST).isoformat()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}]\n{message}\n\n")


def _post_webhook(
    url: str,
    payload: dict[str, object],
    *,
    session: requests.Session | None,
) -> None:
    http = session or requests.Session()
    response = http.post(url, json=payload, timeout=20)
    response.raise_for_status()


def _send_email(config: NotificationConfig, *, subject: str, body: str) -> None:
    if not config.smtp_host:
        raise ValueError("INVESTING_SMTP_HOST is required for email notifications")
    if not config.email_from:
        raise ValueError("INVESTING_NOTIFY_EMAIL_FROM is required for email notifications")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.email_from
    message["To"] = ", ".join(config.email_to)
    message.set_content(body)

    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=20) as smtp:
        if config.smtp_use_tls:
            smtp.starttls()
        if config.smtp_user and config.smtp_password:
            smtp.login(config.smtp_user, config.smtp_password)
        smtp.send_message(message)
