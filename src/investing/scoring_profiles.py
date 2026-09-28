"""Industry-specific scorer thresholds for Indian listed companies.

Thresholds are documented research defaults, not calibrated model outputs.
Percentage-like fundamentals use decimals (18% ROE -> 0.18). Bank prudential
ratios such as gross NPA and CET1 use percentage points (1.2% NPA -> 1.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

Direction = Literal["higher", "lower"]


@dataclass(frozen=True)
class Metric:
    column: str
    category: str
    direction: Direction
    poor: float
    strong: float

NON_BANK_METRICS: tuple[Metric, ...] = (
    Metric("roe", "quality", "higher", 0.00, 0.25),
    Metric("roce", "quality", "higher", 0.00, 0.30),
    Metric("operating_margin", "quality", "higher", 0.05, 0.25),
    Metric("revenue_cagr_3y", "growth", "higher", -0.05, 0.20),
    Metric("earnings_cagr_3y", "growth", "higher", -0.10, 0.25),
    Metric("debt_to_equity", "financial_strength", "lower", 2.00, 0.00),
    Metric("interest_coverage", "financial_strength", "higher", 1.00, 10.00),
    Metric("pe", "valuation", "lower", 50.00, 10.00),
    Metric("pb", "valuation", "lower", 8.00, 1.00),
    Metric("free_cash_flow_yield", "valuation", "higher", -0.02, 0.08),
    Metric("volatility_1y", "price_discipline", "lower", 0.60, 0.15),
)

BANK_METRICS: tuple[Metric, ...] = (
    Metric("roe", "quality", "higher", 0.08, 0.18),
    Metric("return_on_assets", "quality", "higher", 0.005, 0.015),
    Metric("operating_margin", "quality", "higher", 0.20, 0.45),
    Metric("revenue_cagr_3y", "growth", "higher", -0.03, 0.15),
    Metric("earnings_cagr_3y", "growth", "higher", -0.05, 0.18),
    Metric("gross_npa_ratio", "financial_strength", "lower", 5.00, 1.00),
    Metric("cet1_ratio", "financial_strength", "higher", 8.00, 14.00),
    Metric("pe", "valuation", "lower", 30.00, 12.00),
    Metric("pb", "valuation", "lower", 3.00, 1.00),
    Metric("volatility_1y", "price_discipline", "lower", 0.50, 0.18),
)

INSURANCE_METRICS: tuple[Metric, ...] = (
    Metric("roe", "quality", "higher", 0.08, 0.18),
    Metric("return_on_assets", "quality", "higher", 0.003, 0.012),
    Metric("profit_margin", "quality", "higher", 0.02, 0.12),
    Metric("investment_income_ratio", "quality", "higher", 0.08, 0.25),
    Metric("revenue_cagr_3y", "growth", "higher", -0.03, 0.15),
    Metric("earnings_cagr_3y", "growth", "higher", -0.05, 0.18),
    Metric("equity_to_assets", "financial_strength", "higher", 0.05, 0.18),
    Metric("pe", "valuation", "lower", 35.00, 12.00),
    Metric("pb", "valuation", "lower", 4.00, 1.20),
    Metric("volatility_1y", "price_discipline", "lower", 0.50, 0.18),
)

NBFC_METRICS: tuple[Metric, ...] = (
    Metric("roe", "quality", "higher", 0.10, 0.22),
    Metric("return_on_assets", "quality", "higher", 0.015, 0.035),
    Metric("pre_tax_margin", "quality", "higher", 0.10, 0.30),
    Metric("revenue_cagr_3y", "growth", "higher", -0.03, 0.18),
    Metric("earnings_cagr_3y", "growth", "higher", -0.08, 0.22),
    Metric("debt_to_equity", "financial_strength", "lower", 5.00, 1.50),
    Metric("pe", "valuation", "lower", 40.00, 12.00),
    Metric("pb", "valuation", "lower", 5.00, 1.50),
    Metric("volatility_1y", "price_discipline", "lower", 0.55, 0.18),
)

INDUSTRY_PROFILES: Mapping[str, tuple[Metric, ...]] = {
    "non_bank": NON_BANK_METRICS,
    "bank": BANK_METRICS,
    "nbfc": NBFC_METRICS,
    "insurance": INSURANCE_METRICS,
}

DEFAULT_ENTITY_TYPE = "non_bank"
BASELINE_PROFILE_VERSION = 1


def metrics_for(entity_type: str | None) -> tuple[Metric, ...]:
    """Return the scorer metric set for an entity type."""

    normalized = (entity_type or DEFAULT_ENTITY_TYPE).strip().lower()
    return INDUSTRY_PROFILES.get(normalized, NON_BANK_METRICS)
