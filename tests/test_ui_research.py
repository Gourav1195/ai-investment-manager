from __future__ import annotations

from pathlib import Path

from src.investing.research import ResearchStore
from src.investing.ui_research import run_ui_research


def test_run_ui_research_offline_persists_snapshots(tmp_path: Path) -> None:
    db = tmp_path / "research.db"
    result = run_ui_research(
        db,
        universe_choice="Quick demo (10 well-known stocks)",
        offline=True,
    )
    assert result.records_persisted > 0
    store = ResearchStore(db)
    snapshots = store.list_snapshots()
    assert not snapshots.empty
