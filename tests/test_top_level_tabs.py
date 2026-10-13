from __future__ import annotations

from src.investing.sidebar_nav import SIDEBAR_SECTIONS, TOP_LEVEL_TABS


def test_top_level_tabs_include_pro_research() -> None:
    assert "Portfolio" in TOP_LEVEL_TABS
    assert "Snapshots" in TOP_LEVEL_TABS
    assert "Profile review" in TOP_LEVEL_TABS
    assert "Orchestration" in TOP_LEVEL_TABS
    assert "Stock Research" not in TOP_LEVEL_TABS
    assert TOP_LEVEL_TABS[0] == "Dashboard"
    assert "Run research" in SIDEBAR_SECTIONS
    assert "Import & backup" in SIDEBAR_SECTIONS
    assert "MF peers" in SIDEBAR_SECTIONS
    assert "About" in SIDEBAR_SECTIONS
