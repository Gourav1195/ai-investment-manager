from __future__ import annotations

import pandas as pd

from src.investing.portfolio_concentration import build_concentration_tables


def test_concentration_flags_large_holding() -> None:
    combined = pd.DataFrame(
        [
            {"name": "Big", "current_value": 80000.0, "allocation_pct": 0.8, "asset_class": "Equity"},
            {"name": "Small", "current_value": 20000.0, "allocation_pct": 0.2, "asset_class": "Equity"},
        ]
    )
    top, insights = build_concentration_tables(combined)
    assert len(top) == 2
    assert any("Big" in message for message in insights)
