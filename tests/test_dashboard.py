from __future__ import annotations

from datetime import datetime

from src.investing.dashboard_data import (
    calibration_report,
    explanation_for_snapshot,
    filter_options,
    orchestration_calibration_summary,
    orchestration_runs,
    overview_metrics,
    snapshot_detail,
    snapshot_summary_frame,
)
from src.investing.orchestration import OrchestrationStore, UniverseRunResult
from src.investing.explanations import ScoreExplainer
from src.investing.filings import IST
from src.investing.research import ResearchStore, _snapshot_key
from src.investing.research import WalkForwardEvaluator
from tests.test_walkforward import FakeFilingStore, synthetic_prices


class _EmptyFilingStore:
    def filing_summaries(self, filing_keys):
        return []


def _seed_research_store(path) -> ResearchStore:
    evaluator = WalkForwardEvaluator(filing_store=FakeFilingStore())
    as_of = datetime(2025, 7, 1, tzinfo=IST)
    records = evaluator.evaluate(
        ["TEST"],
        [as_of],
        synthetic_prices(),
        benchmark_index="NIFTY 50",
        forward_days=30,
    )
    store = ResearchStore(path)
    store.save_records(records)
    record = records[0]
    explanation = ScoreExplainer().explain_record(record, _EmptyFilingStore())
    store.save_explanations(
        [
            (
                _snapshot_key(record.evaluation_key, record.snapshot.symbol),
                record.evaluation_key,
                explanation.to_record(),
            )
        ]
    )
    return store


def test_overview_metrics_reports_counts(tmp_path) -> None:
    store = _seed_research_store(tmp_path / "research.db")
    metrics = overview_metrics(store)

    assert metrics["evaluations"] == 1
    assert metrics["snapshots"] == 1
    assert metrics["explanations"] == 1
    assert metrics["symbols"] == 1
    assert metrics["latest_as_of"] is not None


def test_snapshot_summary_frame_filters_by_view(tmp_path) -> None:
    store = _seed_research_store(tmp_path / "research.db")
    snapshots = store.list_snapshots(symbol="TEST")
    research_view = snapshots.iloc[0]["research_view"]

    summary = snapshot_summary_frame(
        store,
        symbol="TEST",
        research_view=research_view,
    )

    assert len(summary) == 1
    assert summary.iloc[0]["symbol"] == "TEST"
    assert summary.iloc[0]["research_view"] == research_view


def test_calibration_report_and_orchestration_runs(tmp_path) -> None:
    store = _seed_research_store(tmp_path / "research.db")
    report = calibration_report(store)
    assert not report.score_buckets.empty

    orchestration_store = OrchestrationStore(tmp_path / "research.db")
    orchestration_store.save_run(
        UniverseRunResult(
            run_key="run-1",
            index_name="NIFTY 50",
            as_of_dates=("2025-07-01T00:00:00+05:30",),
            symbols_requested=1,
            symbols_evaluated=1,
            records_persisted=1,
            skipped_symbols=(),
            archive_status="recorded",
            calibration=report,
        ),
        benchmark_index="NIFTY 50",
        forward_days=30,
    )
    runs = orchestration_runs(tmp_path / "research.db")
    assert len(runs) == 1

    summary = orchestration_calibration_summary(tmp_path / "research.db", store=store)
    assert summary is not None
    assert summary.source == "persisted"
    assert not summary.report.score_buckets.empty


def test_orchestration_calibration_summary_recomputes_without_persisted_payload(
    tmp_path,
) -> None:
    store = _seed_research_store(tmp_path / "research.db")
    orchestration_store = OrchestrationStore(tmp_path / "research.db")
    orchestration_store.save_run(
        UniverseRunResult(
            run_key="run-legacy",
            index_name="NIFTY 50",
            as_of_dates=("2025-07-01T00:00:00+05:30",),
            symbols_requested=1,
            symbols_evaluated=1,
            records_persisted=1,
            skipped_symbols=(),
            archive_status="recorded",
        ),
        benchmark_index="NIFTY 50",
        forward_days=30,
    )

    summary = orchestration_calibration_summary(tmp_path / "research.db", store=store)

    assert summary is not None
    assert summary.source == "recomputed"
    assert not summary.report.score_buckets.empty


def test_filter_options_and_detail_include_explanation(tmp_path) -> None:
    store = _seed_research_store(tmp_path / "research.db")
    options = filter_options(store)
    as_of = options["as_of_dates"][0]

    detail = snapshot_detail(store, symbol="TEST", as_of=as_of)
    explanation = explanation_for_snapshot(store, symbol="TEST", as_of=as_of)

    assert "TEST" in options["symbols"]
    assert detail is not None
    assert detail["explanation"] is not None
    assert explanation is not None
    assert explanation["score_drivers"]
