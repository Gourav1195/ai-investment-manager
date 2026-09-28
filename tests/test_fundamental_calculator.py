from __future__ import annotations

from datetime import datetime

import pytest

from src.investing.filings import IST
from src.investing.fundamentals import FundamentalCalculator


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


def test_non_bank_calculator_derives_long_term_metrics() -> None:
    snapshot = FundamentalCalculator().calculate(
        non_bank_history(),
        symbol="test",
        as_of=datetime(2025, 7, 1, tzinfo=IST),
    )

    assert snapshot.period_end == "2025-03-31"
    assert snapshot.roe == pytest.approx(17.28 / 90.0)
    assert snapshot.roce == pytest.approx(22.0 / 180.0)
    assert snapshot.operating_margin == pytest.approx(21.0 / 172.8)
    assert snapshot.revenue_cagr_3y == pytest.approx(0.20)
    assert snapshot.earnings_cagr_3y == pytest.approx(0.20)
    assert snapshot.debt_to_equity == pytest.approx(0.40)
    assert snapshot.interest_coverage == pytest.approx(11.0)
    assert snapshot.free_cash_flow == pytest.approx(20.0)


def test_calculator_honors_as_of_revisions_and_prefers_consolidated() -> None:
    rows = non_bank_history()
    rows.extend(
        [
            duration(
                "revenue",
                999.0,
                2025,
                consolidated="Non-Consolidated",
                filing_at="2025-06-01T12:00:00+05:30",
                filing_key="standalone",
            ),
            duration(
                "revenue",
                200.0,
                2025,
                filing_at="2025-08-01T12:00:00+05:30",
                filing_key="revision",
            ),
        ]
    )

    before_revision = FundamentalCalculator().calculate(
        rows, symbol="TEST", as_of=datetime(2025, 7, 1, tzinfo=IST)
    )
    after_revision = FundamentalCalculator().calculate(
        rows, symbol="TEST", as_of=datetime(2025, 9, 1, tzinfo=IST)
    )

    assert before_revision.operating_margin == pytest.approx(21.0 / 172.8)
    assert after_revision.operating_margin == pytest.approx(21.0 / 200.0)
    assert "revision" in after_revision.source_filing_keys
    assert "standalone" not in before_revision.source_filing_keys


def test_bank_calculator_uses_bank_specific_ratios() -> None:
    rows: list[dict[str, object]] = []
    for year, income, earnings in [
        (2022, 100.0, 10.0),
        (2023, 110.0, 11.0),
        (2024, 121.0, 12.1),
        (2025, 133.1, 13.31),
    ]:
        rows.extend(
            [
                duration("total_income", income, year, entity_type="bank"),
                duration("net_income_attributable", earnings, year, entity_type="bank"),
            ]
        )
    for year, capital, reserves, assets in [
        (2024, 10.0, 70.0, 800.0),
        (2025, 12.0, 88.0, 1000.0),
    ]:
        rows.extend(
            [
                instant("equity_share_capital", capital, year, entity_type="bank"),
                instant("reserves", reserves, year, entity_type="bank"),
                instant("total_assets", assets, year, entity_type="bank"),
            ]
        )
    rows.extend(
        [
            duration("pre_provision_operating_profit", 40.0, 2025, entity_type="bank"),
            duration("profit_before_tax", 20.0, 2025, entity_type="bank"),
            duration(
                "gross_npa_ratio",
                1.2,
                2025,
                entity_type="bank",
                start_month=1,
            ),
            duration("cet1_ratio", 16.0, 2025, entity_type="bank", start_month=1),
        ]
    )

    snapshot = FundamentalCalculator().calculate(
        rows, symbol="TEST", as_of=datetime(2025, 7, 1, tzinfo=IST)
    )

    assert snapshot.roe == pytest.approx(13.31 / 90.0)
    assert snapshot.return_on_assets == pytest.approx(13.31 / 900.0)
    assert snapshot.operating_margin == pytest.approx(40.0 / 133.1)
    assert snapshot.pre_tax_margin == pytest.approx(20.0 / 133.1)
    assert snapshot.gross_npa_ratio == pytest.approx(1.2)
    assert snapshot.cet1_ratio == pytest.approx(16.0)
    assert snapshot.roce is None
    assert snapshot.interest_coverage is None
