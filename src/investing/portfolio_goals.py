"""Investment goal progress and simple forward projections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class InvestmentGoal:
    goal_id: str
    name: str
    target_inr: float
    target_date: date


@dataclass(frozen=True)
class GoalProgressRow:
    goal_id: str
    name: str
    target_inr: float
    target_date: date
    current_inr: float
    progress_pct: float
    months_remaining: int
    projected_inr: float | None
    required_monthly_inr: float | None
    status: str


def parse_goals(raw: list[dict[str, object]]) -> list[InvestmentGoal]:
    goals: list[InvestmentGoal] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        goal_id = str(item.get("goal_id") or item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not goal_id or not name:
            continue
        try:
            target_inr = float(item["target_inr"])
        except (KeyError, TypeError, ValueError):
            continue
        if target_inr <= 0:
            continue
        target_date = _parse_date(item.get("target_date"))
        if target_date is None:
            continue
        goals.append(
            InvestmentGoal(
                goal_id=goal_id,
                name=name,
                target_inr=target_inr,
                target_date=target_date,
            )
        )
    return goals


def goals_to_json(goals: list[InvestmentGoal]) -> list[dict[str, object]]:
    return [
        {
            "goal_id": goal.goal_id,
            "name": goal.name,
            "target_inr": goal.target_inr,
            "target_date": goal.target_date.isoformat(),
        }
        for goal in goals
    ]


def compute_goal_progress(
    goals: list[InvestmentGoal],
    *,
    current_portfolio_inr: float,
    as_of: date | None = None,
    annual_return: float | None = None,
    monthly_sip_inr: float = 0.0,
) -> list[GoalProgressRow]:
    """Project each goal using whole-portfolio value (single-wallet assumption)."""

    as_of = as_of or date.today()
    rate = annual_return if annual_return is not None else 0.10
    rows: list[GoalProgressRow] = []
    for goal in goals:
        months = _months_between(as_of, goal.target_date)
        progress = min(100.0, (current_portfolio_inr / goal.target_inr) * 100.0)
        projected = _project_value(
            current_portfolio_inr,
            months=months,
            annual_return=rate,
            monthly_contribution=monthly_sip_inr,
        )
        required = _required_monthly(
            current_portfolio_inr,
            goal.target_inr,
            months=months,
            annual_return=rate,
        )
        status = _status(progress, projected, goal.target_inr)
        rows.append(
            GoalProgressRow(
                goal_id=goal.goal_id,
                name=goal.name,
                target_inr=goal.target_inr,
                target_date=goal.target_date,
                current_inr=current_portfolio_inr,
                progress_pct=progress,
                months_remaining=months,
                projected_inr=projected,
                required_monthly_inr=required,
                status=status,
            )
        )
    return rows


def goal_progress_frame(rows: list[GoalProgressRow]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(
            columns=[
                "goal_id",
                "name",
                "target_inr",
                "target_date",
                "progress_pct",
                "projected_inr",
                "required_monthly_inr",
                "status",
            ]
        )
    return pd.DataFrame(
        [
            {
                "goal_id": row.goal_id,
                "name": row.name,
                "target_inr": row.target_inr,
                "target_date": row.target_date.isoformat(),
                "progress_pct": row.progress_pct,
                "projected_inr": row.projected_inr,
                "required_monthly_inr": row.required_monthly_inr,
                "status": row.status,
            }
            for row in rows
        ]
    )


def _project_value(
    current: float,
    *,
    months: int,
    annual_return: float,
    monthly_contribution: float,
) -> float | None:
    if months < 0:
        return None
    if months == 0:
        return current
    monthly_rate = (1.0 + annual_return) ** (1.0 / 12.0) - 1.0
    value = current
    for _ in range(months):
        value = value * (1.0 + monthly_rate) + monthly_contribution
    return value


def _required_monthly(
    current: float,
    target: float,
    *,
    months: int,
    annual_return: float,
) -> float | None:
    if months <= 0:
        return None if current >= target else max(target - current, 0.0)
    monthly_rate = (1.0 + annual_return) ** (1.0 / 12.0) - 1.0
    if abs(monthly_rate) < 1e-9:
        gap = target - current
        return max(gap / months, 0.0)
    grown = current * ((1.0 + monthly_rate) ** months)
    if grown >= target:
        return 0.0
    factor = ((1.0 + monthly_rate) ** months - 1.0) / monthly_rate
    if factor <= 0:
        return max((target - current) / months, 0.0)
    return max((target - grown) / factor, 0.0)


def _status(progress_pct: float, projected: float | None, target: float) -> str:
    if progress_pct >= 100:
        return "Reached"
    if projected is None:
        return "Past target date"
    if projected >= target * 0.98:
        return "On track"
    if projected >= target * 0.85:
        return "Needs attention"
    return "Behind"


def _months_between(start: date, end: date) -> int:
    if end <= start:
        return 0
    return (end.year - start.year) * 12 + (end.month - start.month)


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None
