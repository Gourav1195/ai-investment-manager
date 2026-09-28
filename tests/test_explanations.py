from __future__ import annotations

from datetime import datetime

import pytest

from src.investing.explanations import ScoreExplainer
from src.investing.filings import FilingStore, IST
from src.investing.fundamentals import FundamentalSnapshot
from src.investing.research import ResearchStore, _snapshot_key
from tests.test_financial_filings import filing_record
from tests.test_fundamental_calculator import non_bank_history
from tests.test_walkforward import FakeFilingStore, synthetic_prices
from src.investing.research import WalkForwardEvaluator


def test_explainer_lists_drivers_risks_and_source_documents(tmp_path) -> None:
    store = FilingStore(tmp_path / "research.db")
    record = filing_record(symbol="INFY", bank="N")
    store.ingest([record], request_symbol="INFY", request_period="Quarterly")
    with store._connect() as connection:
        row = connection.execute(
            "SELECT filing_key FROM financial_result_filings WHERE symbol = ?",
            ("INFY",),
        ).fetchone()
    assert row is not None
    filing_key = row["filing_key"]

    snapshot = FundamentalSnapshot(
        symbol="INFY",
        entity_type="non_bank",
        as_of=datetime(2025, 7, 1, tzinfo=IST).isoformat(),
        period_end="2025-03-31",
        roe=0.24,
        roce=0.28,
        operating_margin=0.24,
        revenue_cagr_3y=0.18,
        earnings_cagr_3y=0.22,
        debt_to_equity=0.10,
        interest_coverage=15.0,
        pe=18.0,
        pb=2.0,
        free_cash_flow_yield=0.07,
        volatility_1y=0.18,
        source_filing_keys=(filing_key,),
    )

    explanation = ScoreExplainer().explain_snapshot(
        snapshot,
        overall_score=82.0,
        research_view="Strong candidate",
        data_coverage=1.0,
        filing_store=store,
    )

    assert explanation.score_drivers
    assert explanation.risk_flags == ()
    assert len(explanation.source_documents) == 1
    assert explanation.source_documents[0]["filing_key"] == filing_key


def test_explainer_flags_material_risks() -> None:
    snapshot = FundamentalSnapshot(
        symbol="RISKY",
        entity_type="non_bank",
        as_of="2025-07-01T00:00:00+05:30",
        period_end="2025-03-31",
        debt_to_equity=2.0,
        interest_coverage=1.0,
        volatility_1y=0.55,
        pe=50.0,
        free_cash_flow_yield=-0.02,
        revenue_cagr_3y=-0.05,
    )
    explanation = ScoreExplainer().explain_snapshot(
        snapshot,
        overall_score=30.0,
        research_view="Avoid",
        data_coverage=0.5,
        filing_store=_EmptyFilingStore(),
    )

    joined = " ".join(explanation.risk_flags)
    assert "leverage" in joined
    assert "interest coverage" in joined
    assert "volatility" in joined
    assert "Insufficient" not in joined
    assert "50%" in joined


def test_explanations_persist_with_research_snapshots(tmp_path) -> None:
    evaluator = WalkForwardEvaluator(filing_store=FakeFilingStore())
    as_of = datetime(2025, 7, 1, tzinfo=IST)
    records = evaluator.evaluate(
        ["TEST"],
        [as_of],
        synthetic_prices(),
        benchmark_index="NIFTY 50",
        forward_days=30,
    )
    research_store = ResearchStore(tmp_path / "research.db")
    research_store.save_records(records)
    record = records[0]
    explanation = ScoreExplainer().explain_record(record, _EmptyFilingStore())
    inserted = research_store.save_explanations(
        [
            (
                _snapshot_key(record.evaluation_key, record.snapshot.symbol),
                record.evaluation_key,
                explanation.to_record(),
            )
        ]
    )
    saved = research_store.list_explanations(symbol="TEST")

    assert inserted == 1
    assert len(saved) == 1
    assert saved.iloc[0]["symbol"] == "TEST"


class _EmptyFilingStore:
    def filing_summaries(self, filing_keys):
        return []


def test_fundamental_snapshot_round_trips_from_record() -> None:
    snapshot = FundamentalSnapshot(
        symbol="INFY",
        entity_type="non_bank",
        as_of="2025-07-01T00:00:00+05:30",
        period_end="2025-03-31",
        roe=0.2,
        source_filing_keys=("abc", "def"),
    )
    row = snapshot.to_record()
    restored = FundamentalSnapshot.from_record(row)
    assert restored.symbol == "INFY"
    assert restored.source_filing_keys == ("abc", "def")
