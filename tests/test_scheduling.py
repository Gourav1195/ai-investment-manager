from __future__ import annotations

from datetime import date

from src.investing.scheduling import (
    QuarterlyResearchSchedule,
    price_window_for_quarter_range,
    quarterly_schedule_from_env,
    render_schedule_recipes,
    resolve_quarterly_windows,
    rolling_quarter_range,
)


def test_rolling_quarter_range_returns_latest_four_quarters() -> None:
    start, end = rolling_quarter_range(date(2025, 6, 30), quarters=4)

    assert end.isoformat() == "2025-06-30"
    assert start.isoformat() == "2024-09-30"


def test_price_window_covers_lookback_and_forward_period() -> None:
    prices_start, prices_end = price_window_for_quarter_range(
        date(2024, 9, 30),
        date(2025, 6, 30),
        lookback_years=3,
        forward_days=365,
        buffer_days=30,
    )

    assert prices_start == "2021-09-30"
    assert prices_end == "2026-07-30"


def test_quarterly_schedule_from_env_reads_flags() -> None:
    schedule = quarterly_schedule_from_env(
        {
            "INVESTING_RESEARCH_DB": "tmp/research.db",
            "INVESTING_INDEX": "NIFTY 100",
            "INVESTING_QUARTERS": "2",
            "INVESTING_EXPLAIN": "false",
        }
    )

    assert schedule.database.as_posix() == "tmp/research.db"
    assert schedule.index_name == "NIFTY 100"
    assert schedule.quarters == 2
    assert schedule.explain is False


def test_resolve_quarterly_windows_counts_as_of_dates() -> None:
    schedule = QuarterlyResearchSchedule(quarters=4)
    windows = resolve_quarterly_windows(schedule, reference=date(2025, 6, 30))

    assert windows.as_of_count == 4
    assert windows.quarter_range_end.isoformat() == "2025-06-30"


def test_render_schedule_recipes_includes_cron_and_task_scheduler() -> None:
    schedule = QuarterlyResearchSchedule(database="work/research.db")
    text = render_schedule_recipes(
        schedule,
        reference=date(2025, 6, 30),
        project_root=".",
    )

    assert "Linux cron" in text
    assert "Windows Task Scheduler" in text
    assert "schedule run-quarterly" in text
