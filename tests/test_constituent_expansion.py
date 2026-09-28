from __future__ import annotations

from datetime import date

import pandas as pd

from src.investing.constituent_expansion import (
    backfill_quarter_snapshots_from_changes,
    backfill_quarter_snapshots_from_intervals,
    import_wide_snapshots_csv,
    load_membership_intervals_csv,
    load_reconstitution_changes_csv,
    load_snapshots_wide_csv,
    members_at_date_from_changes,
    members_on_date,
    normalize_nse_changes_frame,
    ReconstitutionChange,
)
from src.investing.constituents import ConstituentHistoryStore


def test_members_on_date_uses_half_open_intervals() -> None:
    intervals = load_membership_intervals_csv(
        "examples/nifty50_membership_intervals.example.csv"
    )

    assert members_on_date(intervals, date(2024, 9, 26)) == ["RELIANCE", "INFY", "PEL"]
    assert members_on_date(intervals, date(2024, 9, 27)) == ["RELIANCE", "INFY", "BSE"]


def test_members_at_date_from_changes_replays_backward_from_anchor() -> None:
    changes = [
        ReconstitutionChange(date(2024, 6, 1), "NEW", "add"),
        ReconstitutionChange(date(2024, 6, 1), "OLD", "remove"),
    ]

    members = members_at_date_from_changes(
        ["AAA", "NEW"],
        changes,
        date(2024, 5, 31),
        anchor_date=date(2024, 9, 30),
    )

    assert members == ["AAA", "OLD"]


def test_backfill_quarter_snapshots_from_intervals(tmp_path) -> None:
    store = ConstituentHistoryStore(tmp_path / "research.db")
    intervals = load_membership_intervals_csv(
        "examples/nifty50_membership_intervals.example.csv"
    )

    result = backfill_quarter_snapshots_from_intervals(
        store,
        "NIFTY 50",
        intervals,
        quarter_range_start=date(2024, 3, 31),
        quarter_range_end=date(2024, 9, 30),
    )

    assert result.snapshots_written == 3
    assert store.members_as_of("NIFTY 50", date(2024, 6, 30)) == ["RELIANCE", "INFY", "PEL"]
    assert store.members_as_of("NIFTY 50", date(2024, 9, 30)) == ["RELIANCE", "INFY", "BSE"]


def test_backfill_quarter_snapshots_from_changes(tmp_path) -> None:
    store = ConstituentHistoryStore(tmp_path / "research.db")
    changes = load_reconstitution_changes_csv(
        "examples/nifty50_reconstitution_changes.example.csv"
    )

    result = backfill_quarter_snapshots_from_changes(
        store,
        "NIFTY 50",
        changes,
        anchor_members=["RELIANCE", "INFY", "BSE"],
        anchor_date=date(2024, 9, 30),
        quarter_range_start=date(2024, 3, 31),
        quarter_range_end=date(2024, 9, 30),
    )

    assert result.snapshots_written == 3
    assert store.members_as_of("NIFTY 50", date(2024, 6, 30)) == ["INFY", "PEL", "RELIANCE"]


def test_import_wide_snapshots_csv(tmp_path) -> None:
    store = ConstituentHistoryStore(tmp_path / "research.db")
    snapshots = load_snapshots_wide_csv("examples/nifty50_membership_wide.example.csv")

    assert snapshots[date(2024, 9, 30)] == ["RELIANCE", "INFY", "BSE"]

    imported = import_wide_snapshots_csv(
        store,
        "examples/nifty50_membership_wide.example.csv",
        index_name="NIFTY 50",
    )

    assert imported == 3
    assert store.members_as_of("NIFTY 50", date(2024, 6, 30)) == ["RELIANCE", "INFY", "PEL"]


def test_normalize_nse_changes_frame_splits_inclusion_and_exclusion_dates() -> None:
    frame = pd.DataFrame(
        {
            "Symbol": ["AAA", "BBB"],
            "Inclusion Date": ["2024-03-28", pd.NA],
            "Exclusion Date": [pd.NA, "2024-09-27"],
        }
    )

    normalized = normalize_nse_changes_frame(frame, index_name="NIFTY 50")

    assert normalized.loc[0, "action"] == "add"
    assert normalized.loc[0, "symbol"] == "AAA"
    assert normalized.loc[1, "action"] == "remove"
    assert normalized.loc[1, "symbol"] == "BBB"
