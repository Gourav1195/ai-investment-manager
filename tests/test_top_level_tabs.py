from __future__ import annotations

from src.investing.dashboard import TOP_LEVEL_TABS


def test_top_level_tabs_include_pro_research() -> None:
    assert "Portfolio" in TOP_LEVEL_TABS
    assert "Snapshots" in TOP_LEVEL_TABS
    assert "Profile review" in TOP_LEVEL_TABS
    assert "Orchestration runs" in TOP_LEVEL_TABS
    assert "Stock Research" not in TOP_LEVEL_TABS
    assert TOP_LEVEL_TABS[0] == "Wealth at a glance"
