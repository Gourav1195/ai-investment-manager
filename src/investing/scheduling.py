"""Helpers and runners for recurring India research schedules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import os
import shlex
import textwrap

from .constituents import (
    SUPPORTED_INDICES,
    ConstituentHistoryStore,
    archive_current_constituents,
    latest_fiscal_quarter_end,
)
from .orchestration import UniverseResearchOrchestrator, UniverseRunResult, resolve_orchestration_dates
from .providers import NiftyIndexUniverseProvider
from .research import fiscal_quarter_end_dates

DEFAULT_DATABASE = Path("work/research.db")


@dataclass(frozen=True)
class QuarterlyResearchSchedule:
    database: Path = DEFAULT_DATABASE
    index_name: str = "NIFTY 50"
    benchmark_index: str = "NIFTY 50"
    quarters: int = 4
    price_lookback_years: int = 3
    forward_days: int = 365
    archive_all_indices: bool = True
    archive_constituents: bool = True
    historical_constituents: bool = True
    use_active_profile: bool = True
    explain: bool = True
    persist: bool = True

    def __post_init__(self) -> None:
        if self.quarters < 1:
            raise ValueError("quarters must be at least 1")
        if self.price_lookback_years < 1:
            raise ValueError("price_lookback_years must be at least 1")
        if self.forward_days < 1:
            raise ValueError("forward_days must be at least 1")


@dataclass(frozen=True)
class ResolvedQuarterlyWindows:
    quarter_range_start: date
    quarter_range_end: date
    prices_start: str
    prices_end: str
    as_of_count: int


def rolling_quarter_range(
    reference: date | None = None,
    *,
    quarters: int = 4,
) -> tuple[date, date]:
    """Return fiscal quarter bounds covering the latest ``quarters`` quarter-ends."""

    if quarters < 1:
        raise ValueError("quarters must be at least 1")
    end = reference or latest_fiscal_quarter_end()
    lookback_start = date(end.year - max(1, (quarters + 3) // 4), 4, 1)
    candidates = fiscal_quarter_end_dates(lookback_start, end)
    if not candidates:
        return end, end
    selected = candidates[-quarters:]
    return selected[0].date(), selected[-1].date()


def price_window_for_quarter_range(
    quarter_range_start: date,
    quarter_range_end: date,
    *,
    lookback_years: int = 3,
    forward_days: int = 365,
    buffer_days: int = 30,
) -> tuple[str, str]:
    """Return ISO price bounds that cover lookback and forward-return evaluation."""

    prices_start = date(
        quarter_range_start.year - lookback_years,
        quarter_range_start.month,
        quarter_range_start.day,
    ).isoformat()
    prices_end = (
        quarter_range_end + timedelta(days=forward_days + buffer_days)
    ).isoformat()
    return prices_start, prices_end


def resolve_quarterly_windows(
    schedule: QuarterlyResearchSchedule,
    *,
    reference: date | None = None,
) -> ResolvedQuarterlyWindows:
    quarter_range_start, quarter_range_end = rolling_quarter_range(
        reference,
        quarters=schedule.quarters,
    )
    prices_start, prices_end = price_window_for_quarter_range(
        quarter_range_start,
        quarter_range_end,
        lookback_years=schedule.price_lookback_years,
        forward_days=schedule.forward_days,
    )
    as_of_dates = resolve_orchestration_dates(
        quarter_range_start=quarter_range_start.isoformat(),
        quarter_range_end=quarter_range_end.isoformat(),
    )
    return ResolvedQuarterlyWindows(
        quarter_range_start=quarter_range_start,
        quarter_range_end=quarter_range_end,
        prices_start=prices_start,
        prices_end=prices_end,
        as_of_count=len(as_of_dates),
    )


def quarterly_schedule_from_env(
    environ: dict[str, str] | None = None,
) -> QuarterlyResearchSchedule:
    """Build a quarterly schedule from environment variables."""

    values = environ or os.environ

    def _bool(name: str, default: bool) -> bool:
        raw = values.get(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    return QuarterlyResearchSchedule(
        database=Path(values.get("INVESTING_RESEARCH_DB", str(DEFAULT_DATABASE))),
        index_name=values.get("INVESTING_INDEX", "NIFTY 50"),
        benchmark_index=values.get("INVESTING_BENCHMARK_INDEX", "NIFTY 50"),
        quarters=int(values.get("INVESTING_QUARTERS", "4")),
        price_lookback_years=int(values.get("INVESTING_PRICE_LOOKBACK_YEARS", "3")),
        forward_days=int(values.get("INVESTING_FORWARD_DAYS", "365")),
        archive_all_indices=_bool("INVESTING_ARCHIVE_ALL_INDICES", True),
        archive_constituents=_bool("INVESTING_ARCHIVE_CONSTITUENTS", True),
        historical_constituents=_bool("INVESTING_HISTORICAL_CONSTITUENTS", True),
        use_active_profile=_bool("INVESTING_USE_ACTIVE_PROFILE", True),
        explain=_bool("INVESTING_EXPLAIN", True),
        persist=_bool("INVESTING_PERSIST", True),
    )


def archive_indices_for_schedule(
    schedule: QuarterlyResearchSchedule,
) -> list[str]:
    store = ConstituentHistoryStore(schedule.database)
    indices = list(SUPPORTED_INDICES) if schedule.archive_all_indices else [schedule.index_name]
    statuses: list[str] = []
    for index_name in indices:
        results = archive_current_constituents(
            store,
            NiftyIndexUniverseProvider(index_name),
        )
        statuses.extend(result.status for result in results)
    return statuses


def run_quarterly_research(
    schedule: QuarterlyResearchSchedule,
    *,
    reference: date | None = None,
    orchestrator: UniverseResearchOrchestrator | None = None,
) -> UniverseRunResult:
    """Archive constituents (optional) and run a rolling quarterly orchestration."""

    windows = resolve_quarterly_windows(schedule, reference=reference)
    if schedule.archive_constituents:
        archive_indices_for_schedule(schedule)

    runner = orchestrator or UniverseResearchOrchestrator(database=schedule.database)
    as_of_dates = resolve_orchestration_dates(
        quarter_range_start=windows.quarter_range_start.isoformat(),
        quarter_range_end=windows.quarter_range_end.isoformat(),
    )
    return runner.run(
        index_name=schedule.index_name,
        as_of_dates=as_of_dates,
        prices_start=windows.prices_start,
        prices_end=windows.prices_end,
        benchmark_index=schedule.benchmark_index,
        forward_days=schedule.forward_days,
        archive_constituents=False,
        use_historical_constituents=schedule.historical_constituents,
        persist=schedule.persist,
        explain=schedule.explain,
        use_active_profile=schedule.use_active_profile,
    )


def render_schedule_recipes(
    schedule: QuarterlyResearchSchedule,
    *,
    python_executable: str = "python",
    project_root: str = ".",
    reference: date | None = None,
) -> str:
    """Return copy-paste cron and Task Scheduler recipes for ``schedule``."""

    windows = resolve_quarterly_windows(schedule, reference=reference)
    database = Path(schedule.database).as_posix()
    module = f"{python_executable} -m src.investing.cli"
    archive_cmd = (
        f"{module} constituents archive --all-indices --database {shlex.quote(database)}"
        if schedule.archive_all_indices
        else (
            f"{module} constituents archive --index {shlex.quote(schedule.index_name)} "
            f"--database {shlex.quote(database)}"
        )
    )
    orchestrate_flags = [
        f"--index {shlex.quote(schedule.index_name)}",
        f"--quarter-range-start {windows.quarter_range_start.isoformat()}",
        f"--quarter-range-end {windows.quarter_range_end.isoformat()}",
        f"--prices-start {windows.prices_start}",
        f"--prices-end {windows.prices_end}",
        f"--database {shlex.quote(database)}",
        f"--benchmark-index {shlex.quote(schedule.benchmark_index)}",
        f"--forward-days {schedule.forward_days}",
    ]
    if schedule.historical_constituents:
        orchestrate_flags.append("--historical-constituents")
    if schedule.use_active_profile:
        orchestrate_flags.append("--use-active-profile")
    if schedule.explain:
        orchestrate_flags.append("--explain")
    if schedule.persist:
        orchestrate_flags.append("--persist")
    orchestrate_cmd = f"{module} schedule run-quarterly"
    quarterly_cmd = f"{module} schedule run-quarterly --database {shlex.quote(database)}"

    cron_archive = f"15 6 1 */3 * cd {shlex.quote(project_root)} && {archive_cmd}"
    cron_orchestrate = f"30 6 1 */3 * cd {shlex.quote(project_root)} && {quarterly_cmd}"
    task_command = (
        f'powershell -NoProfile -ExecutionPolicy Bypass -File '
        f'"{Path(project_root, "scripts", "india-research-quarterly.ps1").as_posix()}"'
    )

    return textwrap.dedent(
        f"""
        Quarterly research schedule
        ---------------------------
        Quarter range: {windows.quarter_range_start.isoformat()} to {windows.quarter_range_end.isoformat()}
        As-of dates: {windows.as_of_count}
        Price window: {windows.prices_start} to {windows.prices_end}

        Preferred single command
        ------------------------
        cd {project_root}
        {quarterly_cmd}

        Linux cron (first day of each calendar quarter, IST-friendly morning slots)
        -------------------------------------------------------------------------------
        {cron_archive}
        {cron_orchestrate}

        Windows Task Scheduler
        ----------------------
        Program: powershell
        Arguments: -NoProfile -ExecutionPolicy Bypass -File "{Path(project_root, "scripts", "india-research-quarterly.ps1").as_posix()}"
        Start in: {project_root}
        Trigger: monthly on day 1 at 06:30, repeat every 3 months

        schtasks example:
        schtasks /Create /TN "IndiaResearchQuarterly" /SC MONTHLY /MO 3 /D 1 /ST 06:30 /TR "{task_command}" /F

        Manual split (archive then orchestrate with explicit windows)
        -------------------------------------------------------------
        {archive_cmd}
        {module} orchestrate {' '.join(orchestrate_flags)}
        """
    ).strip()
