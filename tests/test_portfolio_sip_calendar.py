from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from src.investing.portfolio_sip_calendar import (
    infer_sip_schedules,
    monthly_sip_total,
    upcoming_sip_dates,
)
from src.investing.zerodha_import import parse_mf_transactions

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "zerodha_portfolio"


def test_infer_sip_schedules_from_example() -> None:
    frame = parse_mf_transactions(EXAMPLES / "mf_transactions.example.csv")
    schedules = infer_sip_schedules(frame)
    assert len(schedules) == 1
    assert schedules[0].scheme_code == "119063"
    assert schedules[0].day_of_month == 1
    assert schedules[0].typical_amount == 10000.0


def test_upcoming_sip_dates_within_horizon() -> None:
    frame = parse_mf_transactions(EXAMPLES / "mf_transactions.example.csv")
    schedules = infer_sip_schedules(frame)
    upcoming = upcoming_sip_dates(
        schedules,
        as_of=date(2024, 3, 15),
        horizon_days=90,
    )
    assert not upcoming.empty
    assert upcoming.iloc[0]["due_date"] == "2024-04-01"
    assert monthly_sip_total(schedules) == 10000.0


def test_infer_sip_handles_month_end_day() -> None:
    frame = pd.DataFrame(
        [
            {
                "txn_date": "2024-01-31",
                "scheme_name": "Test Fund",
                "scheme_code": "999999",
                "txn_type": "sip",
                "amount": 5000,
            },
            {
                "txn_date": "2024-03-31",
                "scheme_name": "Test Fund",
                "scheme_code": "999999",
                "txn_type": "sip",
                "amount": 5000,
            },
        ]
    )
    schedules = infer_sip_schedules(frame)
    assert schedules[0].day_of_month == 31
    next_date = upcoming_sip_dates(
        schedules,
        as_of=date(2024, 3, 1),
        horizon_days=60,
    )
    assert next_date.iloc[0]["due_date"] == "2024-03-31"
