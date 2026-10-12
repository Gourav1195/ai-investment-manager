from __future__ import annotations

from src.investing.about_ui import _data_flow_svg, _feature_mind_map_svg, _mind_map_nodes


def test_mind_map_lists_main_features() -> None:
    labels = " ".join(label for _, label in _mind_map_nodes())
    assert "Portfolio" in labels
    assert "Stock Research" in labels
    assert "backup" in labels.lower()


def test_svg_fallbacks_are_self_contained() -> None:
    mind = _feature_mind_map_svg()
    flow = _data_flow_svg()
    assert "<svg" in mind and "Portfolio" in mind
    assert "<svg" in flow and "Zerodha" in flow
    assert "stroke-dasharray" in flow
