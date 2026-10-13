"""Asset allocation buckets and Regular vs Direct cost flags."""

from __future__ import annotations

import pandas as pd

# Typical annual expense gap Regular vs Direct (illustrative; not from live TER feed).
REGULAR_VS_DIRECT_EXPENSE_GAP = 0.006


def _asset_bucket_from_category(category: str | None) -> str:
    if not category:
        return "Other"
    text = category.lower()
    if "gold" in text:
        return "Gold"
    if "hybrid" in text or "balanced" in text or "aggressive hybrid" in text:
        return "Hybrid"
    if "debt" in text or "liquid" in text or "money market" in text or " gilt" in text:
        return "Debt"
    if "equity" in text or "elss" in text or "cap" in text or "flexi" in text:
        return "Equity"
    return "Other"


def _cap_bucket_from_category(category: str | None) -> str:
    if not category:
        return "Unclassified"
    text = category.lower()
    if "large" in text and "mid" not in text:
        return "Large cap"
    if "mid" in text and "small" not in text:
        return "Mid cap"
    if "small" in text:
        return "Small cap"
    if "flexi" in text or "multi" in text or "focused" in text:
        return "Flexi / multi cap"
    if "debt" in text or "liquid" in text:
        return "Debt (N/A)"
    if "gold" in text:
        return "Gold"
    if "hybrid" in text:
        return "Hybrid"
    return "Other equity"


def _plan_type_from_meta(meta: dict[str, str | None], scheme_name: str) -> str:
    plan = (meta.get("plan_type") or "").strip()
    if plan:
        return plan
    upper = scheme_name.upper()
    return "Direct" if "DIRECT" in upper else "Regular"


def build_allocation_frames(
    equity_holdings: pd.DataFrame,
    mf_holdings: pd.DataFrame,
    *,
    scheme_meta_lookup,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Returns (by_asset_class, by_cap_bucket, regular_plan_flags).
    scheme_meta_lookup: callable(scheme_code) -> dict with category, plan_type.
    """

    rows: list[dict[str, object]] = []
    for record in equity_holdings.to_dict(orient="records"):
        value = record.get("current_value")
        if value is None or float(value) <= 0:
            continue
        rows.append(
            {
                "label": str(record.get("identifier") or record.get("symbol")),
                "asset_class": "Equity",
                "cap_bucket": "Stocks (single names)",
                "current_value": float(value),
                "plan_type": "—",
            }
        )

    regular_flags: list[dict[str, object]] = []
    for record in mf_holdings.to_dict(orient="records"):
        value = record.get("current_value")
        if value is None or float(value) <= 0:
            continue
        code = str(record.get("scheme_code") or "").strip()
        name = str(record.get("scheme_name") or record.get("identifier") or code)
        meta = scheme_meta_lookup(code) if code else {}
        category = str(meta.get("category") or "")
        plan = _plan_type_from_meta(meta, name)
        rows.append(
            {
                "label": name,
                "asset_class": _asset_bucket_from_category(category),
                "cap_bucket": _cap_bucket_from_category(category),
                "current_value": float(value),
                "plan_type": plan,
            }
        )
        if plan.lower() == "regular":
            est_extra = float(value) * REGULAR_VS_DIRECT_EXPENSE_GAP
            regular_flags.append(
                {
                    "scheme_name": name,
                    "scheme_code": code,
                    "current_value": float(value),
                    "est_extra_cost_per_year": est_extra,
                    "note": (
                        f"~{REGULAR_VS_DIRECT_EXPENSE_GAP * 100:.1f}%/yr illustrative gap vs Direct "
                        "(commission + higher TER; not from live AMFI TER)."
                    ),
                }
            )

    detail = pd.DataFrame(rows)
    if detail.empty:
        empty = pd.DataFrame(columns=["bucket", "current_value", "allocation_pct"])
        return empty, empty, pd.DataFrame(regular_flags)

    by_asset = (
        detail.groupby("asset_class", as_index=False)["current_value"]
        .sum()
        .rename(columns={"asset_class": "bucket"})
    )
    total = by_asset["current_value"].sum()
    by_asset["allocation_pct"] = by_asset["current_value"] / total if total else None

    by_cap = (
        detail.groupby("cap_bucket", as_index=False)["current_value"]
        .sum()
        .rename(columns={"cap_bucket": "bucket"})
    )
    by_cap["allocation_pct"] = by_cap["current_value"] / total if total else None

    return by_asset, by_cap, pd.DataFrame(regular_flags)
