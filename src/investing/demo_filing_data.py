"""Synthetic filing observations for demos, tests, and offline UI research."""

from __future__ import annotations

from datetime import datetime


def duration(
    metric: str,
    value: float,
    year: int,
    *,
    filing_at: str | None = None,
    filing_key: str | None = None,
    entity_type: str = "non_bank",
    consolidated: str = "Consolidated",
    start_month: int = 4,
) -> dict[str, object]:
    start_year = year - 1 if start_month == 4 else year
    start = f"{start_year:04d}-{start_month:02d}-01"
    end = f"{year:04d}-03-31"
    return {
        "filing_key": filing_key or f"filing-{year}",
        "symbol": "TEST",
        "entity_type": entity_type,
        "consolidated": consolidated,
        "filing_at": filing_at or f"{year:04d}-05-15T12:00:00+05:30",
        "metric": metric,
        "period_kind": "duration",
        "period_start": start,
        "period_end": end,
        "instant": None,
        "mapping_priority": 100,
        "value_numeric": str(value),
        "is_primary": 1,
    }


def instant(
    metric: str,
    value: float,
    year: int,
    *,
    entity_type: str = "non_bank",
) -> dict[str, object]:
    return {
        "filing_key": f"filing-{year}",
        "symbol": "TEST",
        "entity_type": entity_type,
        "consolidated": "Consolidated",
        "filing_at": f"{year:04d}-05-15T12:00:00+05:30",
        "metric": metric,
        "period_kind": "instant",
        "period_start": None,
        "period_end": None,
        "instant": f"{year:04d}-03-31",
        "mapping_priority": 100,
        "value_numeric": str(value),
        "is_primary": 1,
    }


def non_bank_history() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for year, revenue, earnings in [
        (2022, 100.0, 10.0),
        (2023, 120.0, 12.0),
        (2024, 144.0, 14.4),
        (2025, 172.8, 17.28),
    ]:
        rows.extend(
            [
                duration("revenue", revenue, year),
                duration("net_income_attributable", earnings, year),
            ]
        )
    rows.extend(
        [
            duration("profit_before_tax", 20.0, 2025),
            duration("finance_cost", 2.0, 2025),
            duration("other_income", 1.0, 2025),
            duration("operating_cash_flow", 25.0, 2025),
            duration("capital_expenditure_ppe", 5.0, 2025),
            instant("total_equity", 80.0, 2024),
            instant("total_equity", 100.0, 2025),
            instant("total_assets", 200.0, 2024),
            instant("total_assets", 250.0, 2025),
            instant("current_liabilities", 40.0, 2024),
            instant("current_liabilities", 50.0, 2025),
            instant("borrowings_current", 10.0, 2025),
            instant("borrowings_noncurrent", 30.0, 2025),
        ]
    )
    return rows
