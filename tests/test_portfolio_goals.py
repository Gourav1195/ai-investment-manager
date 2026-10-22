from __future__ import annotations

from datetime import date

from src.investing.portfolio_goals import (
    InvestmentGoal,
    compute_goal_progress,
    parse_goals,
)


def test_parse_goals_skips_invalid() -> None:
    raw = [
        {"goal_id": "a1", "name": "Retire", "target_inr": 1_000_000, "target_date": "2030-01-01"},
        {"goal_id": "bad", "name": "", "target_inr": 100},
    ]
    goals = parse_goals(raw)
    assert len(goals) == 1
    assert goals[0].name == "Retire"


def test_goal_progress_on_track() -> None:
    goal = InvestmentGoal(
        goal_id="g1",
        name="Education",
        target_inr=1_000_000,
        target_date=date(2030, 6, 1),
    )
    rows = compute_goal_progress(
        [goal],
        current_portfolio_inr=500_000,
        as_of=date(2025, 1, 1),
        annual_return=0.12,
        monthly_sip_inr=10_000,
    )
    assert rows[0].progress_pct == 50.0
    assert rows[0].projected_inr is not None
    assert rows[0].projected_inr > 500_000
