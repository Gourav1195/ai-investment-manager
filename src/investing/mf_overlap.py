"""Pairwise mutual fund overlap from cached monthly portfolio disclosures."""

from __future__ import annotations

import pandas as pd

EQUITY_INSTRUMENT_HINTS = ("equity", "share", "stock", "reit", "invit")


def compute_pairwise_overlap(
    holdings_by_scheme: dict[str, pd.DataFrame],
    *,
    equity_only: bool = True,
) -> pd.DataFrame:
    """
    Overlap coefficient = sum(min(w_i, w_j)) for shared ISINs (weights as fraction of NAV).
    """

    codes = sorted(holdings_by_scheme.keys())
    rows: list[dict[str, object]] = []
    for left in codes:
        for right in codes:
            if left >= right:
                continue
            overlap, shared = _overlap_between(
                holdings_by_scheme[left],
                holdings_by_scheme[right],
                equity_only=equity_only,
            )
            if overlap is None:
                continue
            rows.append(
                {
                    "scheme_a": left,
                    "scheme_b": right,
                    "overlap_pct": overlap,
                    "shared_holdings": shared,
                }
            )
    if not rows:
        return pd.DataFrame(columns=["scheme_a", "scheme_b", "overlap_pct", "shared_holdings"])
    frame = pd.DataFrame(rows)
    return frame.sort_values("overlap_pct", ascending=False).reset_index(drop=True)


def top_shared_holdings(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    limit: int = 10,
    equity_only: bool = True,
) -> pd.DataFrame:
    a = _weight_map(left, equity_only=equity_only)
    b = _weight_map(right, equity_only=equity_only)
    shared = set(a.keys()) & set(b.keys())
    rows: list[dict[str, object]] = []
    for isin in shared:
        rows.append(
            {
                "isin": isin,
                "weight_a": a[isin],
                "weight_b": b[isin],
                "overlap_contribution": min(a[isin], b[isin]),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["isin", "weight_a", "weight_b", "overlap_contribution"])
    frame = pd.DataFrame(rows)
    return frame.sort_values("overlap_contribution", ascending=False).head(limit)


def _overlap_between(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    equity_only: bool,
) -> tuple[float | None, int]:
    a = _weight_map(left, equity_only=equity_only)
    b = _weight_map(right, equity_only=equity_only)
    if not a or not b:
        return None, 0
    shared = set(a.keys()) & set(b.keys())
    if not shared:
        return 0.0, 0
    overlap = sum(min(a[isin], b[isin]) for isin in shared)
    return overlap, len(shared)


def _weight_map(frame: pd.DataFrame, *, equity_only: bool) -> dict[str, float]:
    weights: dict[str, float] = {}
    for record in frame.to_dict(orient="records"):
        isin = str(record.get("isin") or "").strip().upper()
        if not isin:
            continue
        instrument = str(record.get("instrument_type") or "").lower()
        if equity_only:
            if instrument:
                if not any(hint in instrument for hint in EQUITY_INSTRUMENT_HINTS):
                    if "equity" not in instrument:
                        continue
            elif not isin.startswith("INE"):
                continue
        try:
            pct = float(record.get("pct_nav"))
        except (TypeError, ValueError):
            continue
        weights[isin] = weights.get(isin, 0.0) + pct
    return weights
