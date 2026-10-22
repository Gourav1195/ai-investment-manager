"""Concentration and overlap-style insights for a combined holdings table."""

from __future__ import annotations

import pandas as pd

DEFAULT_SINGLE_NAME_WARN = 0.25
DEFAULT_TOP3_WARN = 0.60


def build_concentration_tables(
    combined: pd.DataFrame,
    *,
    single_name_threshold: float = DEFAULT_SINGLE_NAME_WARN,
    top3_threshold: float = DEFAULT_TOP3_WARN,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Returns (top_holdings, insight_messages) from a combined holdings frame
    that includes ``allocation_pct`` and ``current_value``.
    """

    if combined.empty or "current_value" not in combined.columns:
        empty = pd.DataFrame(columns=["name", "current_value", "allocation_pct"])
        return empty, []

    frame = combined.copy()
    frame["current_value"] = pd.to_numeric(frame["current_value"], errors="coerce")
    frame = frame.dropna(subset=["current_value"])
    frame = frame[frame["current_value"] > 0]
    if frame.empty:
        return pd.DataFrame(columns=["name", "current_value", "allocation_pct"]), []

    total = float(frame["current_value"].sum())
    if "allocation_pct" not in frame.columns or frame["allocation_pct"].isna().all():
        frame["allocation_pct"] = frame["current_value"] / total

    name_col = "name" if "name" in frame.columns else "identifier"
    top = (
        frame.sort_values("current_value", ascending=False)
        .head(10)[[name_col, "current_value", "allocation_pct"]]
        .rename(columns={name_col: "name"})
        .reset_index(drop=True)
    )

    insights: list[str] = []
    if not top.empty:
        leader = top.iloc[0]
        leader_pct = float(leader["allocation_pct"])
        if leader_pct >= single_name_threshold:
            insights.append(
                f"{leader['name']} is {leader_pct * 100:.1f}% of portfolio value — "
                f"above the {single_name_threshold * 100:.0f}% single-name guideline."
            )
        top3_pct = float(top.head(3)["allocation_pct"].sum())
        if top3_pct >= top3_threshold:
            insights.append(
                f"Your top 3 holdings are {top3_pct * 100:.1f}% of the portfolio "
                f"(guideline: stay below {top3_threshold * 100:.0f}% for diversification)."
            )

    if "asset_class" in frame.columns:
        by_class = (
            frame.groupby("asset_class", as_index=False)["current_value"]
            .sum()
            .sort_values("current_value", ascending=False)
        )
        by_class["allocation_pct"] = by_class["current_value"] / total
        equity_row = by_class[by_class["asset_class"].astype(str).str.lower() == "equity"]
        if not equity_row.empty:
            eq_pct = float(equity_row.iloc[0]["allocation_pct"])
            if eq_pct >= 0.90:
                insights.append(
                    f"Equity is {eq_pct * 100:.1f}% of holdings — consider debt or gold "
                    "if your risk profile needs more balance."
                )
            elif eq_pct <= 0.20 and total > 0:
                insights.append(
                    f"Equity is only {eq_pct * 100:.1f}% of holdings — growth goals may need "
                    "a higher equity share (personal choice)."
                )

    return top, insights


def mf_category_concentration(
    mf_holdings: pd.DataFrame,
    scheme_meta_lookup,
) -> pd.DataFrame:
    """Aggregate MF value by AMFI category (proxy for style overlap)."""

    if mf_holdings.empty:
        return pd.DataFrame(columns=["category", "current_value", "allocation_pct", "fund_count"])

    rows: list[dict[str, object]] = []
    for record in mf_holdings.to_dict(orient="records"):
        value = record.get("current_value")
        if value is None or float(value) <= 0:
            continue
        code = str(record.get("scheme_code") or "").strip()
        meta = scheme_meta_lookup(code) if code else {}
        category = str(meta.get("category") or "Unknown category")
        rows.append({"category": category, "current_value": float(value)})

    if not rows:
        return pd.DataFrame(columns=["category", "current_value", "allocation_pct", "fund_count"])

    frame = pd.DataFrame(rows)
    grouped = (
        frame.groupby("category", as_index=False)
        .agg(current_value=("current_value", "sum"), fund_count=("current_value", "count"))
        .sort_values("current_value", ascending=False)
    )
    total = float(grouped["current_value"].sum())
    grouped["allocation_pct"] = grouped["current_value"] / total if total else None
    return grouped.reset_index(drop=True)
