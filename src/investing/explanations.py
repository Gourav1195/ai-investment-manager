"""Deterministic score explanations grounded in saved source documents.

Explanations describe scorer output and material risks. They do not calculate or
override financial scores.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Iterable, Mapping

import pandas as pd

from .filings import FilingStore
from .fundamentals import FundamentalSnapshot
from .research import ResearchRecord
from .scoring import LongTermScorer
from .scoring_profiles import Metric

EXPLANATION_VERSION = 1

METRIC_LABELS: dict[str, str] = {
    "roe": "ROE",
    "roce": "ROCE",
    "operating_margin": "operating margin",
    "pre_tax_margin": "pre-tax margin",
    "profit_margin": "profit margin on premiums",
    "investment_income_ratio": "investment income ratio",
    "equity_to_assets": "equity to assets",
    "return_on_assets": "return on assets",
    "revenue_cagr_3y": "three-year revenue CAGR",
    "earnings_cagr_3y": "three-year earnings CAGR",
    "debt_to_equity": "debt to equity",
    "interest_coverage": "interest coverage",
    "gross_npa_ratio": "gross NPA ratio",
    "cet1_ratio": "CET1 ratio",
    "pe": "P/E",
    "pb": "P/B",
    "free_cash_flow_yield": "free cash flow yield",
    "volatility_1y": "one-year volatility",
}


@dataclass(frozen=True)
class ResearchExplanation:
    symbol: str
    as_of: str
    research_view: str | None
    overall_score: float | None
    data_coverage: float | None
    score_drivers: tuple[str, ...]
    risk_flags: tuple[str, ...]
    source_documents: tuple[dict[str, Any], ...]
    explanation_version: int = EXPLANATION_VERSION

    def to_record(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "as_of": self.as_of,
            "research_view": self.research_view,
            "overall_score": self.overall_score,
            "data_coverage": self.data_coverage,
            "score_drivers": "; ".join(self.score_drivers),
            "risk_flags": "; ".join(self.risk_flags),
            "score_drivers_json": json.dumps(list(self.score_drivers)),
            "risk_flags_json": json.dumps(list(self.risk_flags)),
            "source_documents_json": json.dumps(
                list(self.source_documents), sort_keys=True
            ),
            "explanation_version": self.explanation_version,
        }


class ScoreExplainer:
    """Explain scorer output using metric contributions and filing lineage."""

    def __init__(self, *, scorer: LongTermScorer | None = None) -> None:
        self.scorer = scorer or LongTermScorer()

    def explain_record(
        self,
        record: ResearchRecord,
        filing_store: FilingStore,
    ) -> ResearchExplanation:
        return self.explain_snapshot(
            record.snapshot,
            overall_score=record.overall_score,
            research_view=record.research_view,
            data_coverage=record.data_coverage,
            filing_store=filing_store,
        )

    def explain_snapshot(
        self,
        snapshot: FundamentalSnapshot,
        *,
        overall_score: float | None,
        research_view: str | None,
        data_coverage: float | None,
        filing_store: FilingStore,
    ) -> ResearchExplanation:
        row = snapshot.to_scorer_row()
        metric_scores = _metric_scores(row, self.scorer)
        drivers = _score_drivers(row, metric_scores, self.scorer)
        risks = _risk_flags(row, data_coverage=data_coverage, snapshot=snapshot)
        sources = filing_store.filing_summaries(snapshot.source_filing_keys)
        return ResearchExplanation(
            symbol=snapshot.symbol,
            as_of=snapshot.as_of,
            research_view=research_view,
            overall_score=overall_score,
            data_coverage=data_coverage,
            score_drivers=tuple(drivers),
            risk_flags=tuple(risks),
            source_documents=tuple(sources),
        )


def explanations_to_frame(
    explanations: Iterable[ResearchExplanation],
) -> pd.DataFrame:
    materialized = [item.to_record() for item in explanations]
    return pd.DataFrame(materialized) if materialized else pd.DataFrame()


def _metric_scores(row: Mapping[str, Any], scorer: LongTermScorer) -> dict[str, float]:
    scores: dict[str, float] = {}
    entity_type = row.get("entity_type") or "non_bank"
    for metric in scorer.metrics_for(str(entity_type)):
        value = row.get(metric.column)
        if value is None or pd.isna(value):
            continue
        score = LongTermScorer._metric_score(
            pd.Series([float(value)]), metric
        ).iloc[0]
        if pd.notna(score):
            scores[metric.column] = float(score)
    return scores


def _score_drivers(
    row: Mapping[str, Any],
    metric_scores: Mapping[str, float],
    scorer: LongTermScorer,
) -> list[str]:
    contributions: list[tuple[float, str]] = []
    entity_type = row.get("entity_type") or "non_bank"
    for metric in scorer.metrics_for(str(entity_type)):
        score = metric_scores.get(metric.column)
        if score is None:
            continue
        weight = LongTermScorer.CATEGORY_WEIGHTS[metric.category]
        contributions.append(
            (
                score * weight,
                (
                    f"{METRIC_LABELS[metric.column]} "
                    f"({_format_metric_value(metric, row.get(metric.column))}) "
                    f"scored {score:.0f}/100 in {metric.category.replace('_', ' ')} "
                    f"({weight:.0%} weight)"
                ),
            )
        )
    contributions.sort(key=lambda item: item[0], reverse=True)
    return [text for _, text in contributions[:4]]


def _risk_flags(
    row: Mapping[str, Any],
    *,
    data_coverage: float | None,
    snapshot: FundamentalSnapshot,
) -> list[str]:
    flags: list[str] = []
    if data_coverage is not None and data_coverage < 0.60:
        flags.append(
            f"Only {data_coverage:.0%} of scorer inputs were available at the as-of date."
        )
    if _value(row, "debt_to_equity") is not None and row["debt_to_equity"] > 1.5:
        flags.append("Elevated leverage: debt to equity is above 1.5x.")
    if _value(row, "interest_coverage") is not None and row["interest_coverage"] < 2.0:
        flags.append("Weak interest coverage below 2.0x.")
    if _value(row, "volatility_1y") is not None and row["volatility_1y"] > 0.40:
        flags.append("High one-year price volatility above 40%.")
    if _value(row, "pe") is not None and row["pe"] > 40.0:
        flags.append("Rich earnings valuation: trailing P/E is above 40x.")
    if _value(row, "pb") is not None and row["pb"] > 6.0:
        flags.append("Rich book valuation: P/B is above 6x.")
    if _value(row, "free_cash_flow_yield") is not None and row["free_cash_flow_yield"] < 0:
        flags.append("Negative free cash flow yield.")
    if _value(row, "revenue_cagr_3y") is not None and row["revenue_cagr_3y"] < 0:
        flags.append("Three-year revenue CAGR is negative.")
    if _value(row, "earnings_cagr_3y") is not None and row["earnings_cagr_3y"] < 0:
        flags.append("Three-year earnings CAGR is negative.")
    if snapshot.gross_npa_ratio is not None and snapshot.gross_npa_ratio > 3.0:
        flags.append("Bank gross NPA ratio is above 3%.")
    if snapshot.entity_type == "insurance":
        if _value(row, "equity_to_assets") is not None and row["equity_to_assets"] < 0.06:
            flags.append("Low equity to assets ratio below 6%.")
        if _value(row, "profit_margin") is not None and row["profit_margin"] < 0.02:
            flags.append("Low profit margin on premiums below 2%.")
    if snapshot.market_join_version is not None and snapshot.price is None:
        flags.append("Market metrics were requested but no point-in-time price was available.")
    if not snapshot.source_filing_keys:
        flags.append("No source filing keys were attached to the fundamental snapshot.")
    return flags


def _format_metric_value(metric: Metric, value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    numeric = float(value)
    if metric.column in {
        "roe",
        "roce",
        "operating_margin",
        "pre_tax_margin",
        "profit_margin",
        "investment_income_ratio",
        "equity_to_assets",
        "return_on_assets",
        "revenue_cagr_3y",
        "earnings_cagr_3y",
        "free_cash_flow_yield",
        "volatility_1y",
    }:
        return f"{numeric:.1%}"
    if metric.column in {"gross_npa_ratio", "cet1_ratio"}:
        return f"{numeric:.1f}%"
    if metric.column in {"debt_to_equity", "interest_coverage", "pe", "pb"}:
        return f"{numeric:.2f}"
    return f"{numeric:.4g}"


def _value(row: Mapping[str, Any], column: str) -> float | None:
    value = row.get(column)
    if value is None or pd.isna(value):
        return None
    return float(value)
