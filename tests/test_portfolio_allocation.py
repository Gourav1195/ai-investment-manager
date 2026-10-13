from __future__ import annotations

import pandas as pd

from src.investing.portfolio_allocation import (
    REGULAR_VS_DIRECT_EXPENSE_GAP,
    _asset_bucket_from_category,
    _cap_bucket_from_category,
    build_allocation_frames,
)


def test_category_buckets() -> None:
    assert _asset_bucket_from_category("Equity Scheme - Large Cap Fund") == "Equity"
    assert _asset_bucket_from_category("Debt Scheme - Corporate Bond") == "Debt"
    assert _asset_bucket_from_category("Other Scheme - Gold ETF") == "Gold"
    assert _cap_bucket_from_category("Equity Scheme - Mid Cap Fund") == "Mid cap"


def test_build_allocation_frames_regular_flag() -> None:
    equity = pd.DataFrame(
        [{"identifier": "RELIANCE", "current_value": 100_000.0}]
    )
    mf = pd.DataFrame(
        [
            {
                "scheme_code": "999",
                "scheme_name": "Example Regular Fund",
                "current_value": 50_000.0,
            }
        ]
    )

    def lookup(code: str) -> dict[str, str]:
        return {
            "category": "Equity Scheme - Large Cap Fund",
            "plan_type": "Regular",
        }

    by_asset, by_cap, regular = build_allocation_frames(
        equity, mf, scheme_meta_lookup=lookup
    )
    assert by_asset["current_value"].sum() == 150_000.0
    assert len(regular) == 1
    assert regular.iloc[0]["est_extra_cost_per_year"] == 50_000.0 * REGULAR_VS_DIRECT_EXPENSE_GAP
