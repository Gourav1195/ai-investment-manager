from __future__ import annotations

from src.investing.mf_peer_comparison import FundReturnMetrics, PeerComparisonReport
from src.investing.wealth_insights import plain_english_insights


def _report(percentile: float | None = 82.0) -> PeerComparisonReport:
    held = FundReturnMetrics(
        scheme_code="123",
        scheme_name="ABC Flexi Cap Direct Growth",
        category="Equity Scheme - Flexi Cap Fund",
        plan_type="Direct",
        option_type="Growth",
        cagr_1y=0.1,
        cagr_3y=0.15,
        cagr_5y=0.12,
        rolling_1y_median=0.08,
        percentile_3y=percentile,
        rank_3y=5,
        peer_count_3y=40,
        category_avg_3y=0.11,
        is_underperformer=False,
    )
    import pandas as pd

    return PeerComparisonReport(held_fund=held, peers=pd.DataFrame(), top_peers=pd.DataFrame())


def test_plain_english_insights_mentions_percentile() -> None:
    lines = plain_english_insights([_report()], limit=2)
    assert lines
    assert "Flexi Cap" in lines[0]
    assert "82" in lines[0]
