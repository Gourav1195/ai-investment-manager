"""India-focused, research-only long-term investing tools."""

from .calibration import (
    analyze_universe_backtest,
    build_profile_version,
    score_bucket_report,
    threshold_suggestions,
)
from .constituent_expansion import (
    backfill_quarter_snapshots_from_changes,
    backfill_quarter_snapshots_from_intervals,
    load_membership_intervals_csv,
    load_reconstitution_changes_csv,
)
from .constituents import (
    ConstituentHistoryStore,
    archive_current_constituents,
    constituent_coverage,
    import_snapshots_csv,
    latest_fiscal_quarter_end,
    resolve_portfolio_symbols,
)
from .orchestration import (
    OrchestrationStore,
    UniverseResearchOrchestrator,
    UniverseRunResult,
    resolve_orchestration_dates,
)
from .profile_store import ScoringProfileStore, resolve_metrics
from .scheduling import (
    QuarterlyResearchSchedule,
    quarterly_schedule_from_env,
    render_schedule_recipes,
    resolve_quarterly_windows,
    rolling_quarter_range,
    run_quarterly_research,
)
from .dashboard_data import overview_metrics, snapshot_summary_frame
from .scoring_profiles import INDUSTRY_PROFILES, metrics_for
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
    "analyze_universe_backtest",
    "OrchestrationStore",
    "archive_current_constituents",
    "backfill_quarter_snapshots_from_changes",
    "backfill_quarter_snapshots_from_intervals",
    "load_membership_intervals_csv",
    "load_reconstitution_changes_csv",
    "build_profile_version",
    "constituent_coverage",
    "ConstituentHistoryStore",
    "import_snapshots_csv",
    "latest_fiscal_quarter_end",
    "resolve_metrics",
    "resolve_orchestration_dates",
    "ScoringProfileStore",
    "score_bucket_report",
    "threshold_suggestions",
    "UniverseResearchOrchestrator",
    "UniverseRunResult",
    "INDUSTRY_PROFILES",
    "overview_metrics",
    "QuarterlyResearchSchedule",
    "quarterly_schedule_from_env",
    "render_schedule_recipes",
    "resolve_quarterly_windows",
    "rolling_quarter_range",
    "run_quarterly_research",
    "resolve_portfolio_symbols",
    "metrics_for",
    "snapshot_summary_frame",
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
