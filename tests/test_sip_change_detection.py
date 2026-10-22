from __future__ import annotations

import pandas as pd

from src.investing.portfolio_sip_calendar import (
    detect_sip_changes,
    overrides_to_json,
    parse_sip_overrides,
    resolve_sip_schedules,
    SipScheduleOverride,
)


def test_detect_sip_amount_change() -> None:
    frame = pd.DataFrame(
        [
            {"txn_date": "2024-01-01", "scheme_name": "Fund A", "scheme_code": "1", "txn_type": "sip", "amount": 5000},
            {"txn_date": "2024-02-01", "scheme_name": "Fund A", "scheme_code": "1", "txn_type": "sip", "amount": 5000},
            {"txn_date": "2024-03-01", "scheme_name": "Fund A", "scheme_code": "1", "txn_type": "sip", "amount": 5000},
            {"txn_date": "2024-04-01", "scheme_name": "Fund A", "scheme_code": "1", "txn_type": "sip", "amount": 8000},
            {"txn_date": "2024-05-01", "scheme_name": "Fund A", "scheme_code": "1", "txn_type": "sip", "amount": 8000},
        ]
    )
    changes = detect_sip_changes(frame)
    assert not changes.empty
    assert changes.iloc[0]["change_type"] == "amount"


def test_manual_sip_override_replaces_inferred() -> None:
    frame = pd.DataFrame(
        [
            {"txn_date": "2024-01-01", "scheme_name": "Fund A", "scheme_code": "1", "txn_type": "sip", "amount": 5000},
        ]
    )
    overrides = parse_sip_overrides(
        overrides_to_json(
            [
                SipScheduleOverride(
                    scheme_code="1",
                    scheme_name="Fund A",
                    day_of_month=15,
                    amount_inr=12000,
                )
            ]
        )
    )
    schedules = resolve_sip_schedules(frame, overrides)
    assert len(schedules) == 1
    assert schedules[0].day_of_month == 15
    assert schedules[0].typical_amount == 12000
    assert schedules[0].source == "manual"
