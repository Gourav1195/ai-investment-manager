"""India-focused, research-only long-term investing tools."""

from .explanations import ResearchExplanation, ScoreExplainer, explanations_to_frame
from .filings import FilingStore, NseFinancialResultsClient
from .fundamentals import CanonicalFactMapper, FundamentalCalculator, FundamentalSnapshot
from .insurance import InsuranceTaxonomyReport, InsuranceTaxonomyValidator
from .market import MarketMetricsJoiner, snapshots_to_scorer_frame
from .providers import (
    NiftyIndexUniverseProvider,
    YFinancePriceProvider,
    nifty_benchmark_symbol,
)
from .research import (
    ResearchStore,
    WalkForwardEvaluator,
    fiscal_quarter_end_dates,
    records_to_frame,
    walkforward_report,
)
from .scoring import LongTermScorer
from .xbrl import NseXbrlClient, XbrlParser

__all__ = [
    "FilingStore",
    "CanonicalFactMapper",
    "FundamentalCalculator",
    "FundamentalSnapshot",
    "InsuranceTaxonomyReport",
    "InsuranceTaxonomyValidator",
    "MarketMetricsJoiner",
    "LongTermScorer",
    "ResearchExplanation",
    "ResearchStore",
    "ScoreExplainer",
    "WalkForwardEvaluator",
    "explanations_to_frame",
    "fiscal_quarter_end_dates",
    "nifty_benchmark_symbol",
    "records_to_frame",
    "snapshots_to_scorer_frame",
    "walkforward_report",
    "NseFinancialResultsClient",
    "NseXbrlClient",
    "NiftyIndexUniverseProvider",
    "XbrlParser",
    "YFinancePriceProvider",
]
