"""About dialog: feature map, data-flow diagram, privacy (non-technical copy)."""

from __future__ import annotations

import shutil

import streamlit as st

ROYAL_NODE = "#151B3B"
ROYAL_GOLD = "#D4AF37"
ROYAL_CREAM = "#F5F0E6"
ROYAL_MUTED = "#B8B2C8"


def render_about_button(*, key: str = "about_app") -> None:
    """Sidebar or header trigger for the About dialog."""
    if st.button(
        "About this app",
        key=key,
        use_container_width=True,
        help="How features fit together and how your data is used.",
    ):
        about_dialog()


@st.dialog("About your wealth dashboard", width="large")
def about_dialog() -> None:
    st.markdown(
        "This app helps you **see** your Zerodha stocks and mutual funds in one place — "
        "with plain-English summaries, charts, and comparisons. "
        "You never need the command line."
    )
    st.markdown("### What you can do here")
    _render_feature_mind_map()
    st.markdown("### How it works (step by step)")
    _render_data_flow_diagram()
    st.markdown("### Privacy & safety")
    st.markdown(
        """
- **Your files stay in this session** — uploads are saved in a database on the machine running the app. On Streamlit Cloud that storage is temporary unless you use **download backup** in Advanced.
- **Read-only** — we only read Console exports and public market data. **We never place orders** or log in to your Zerodha account.
- **Public data sources** — mutual fund data from [AMFI](https://www.amfiindia.com/) and [mfapi.in](https://mfapi.in/); share prices from Yahoo Finance (`yfinance`).
- **Not investment advice** — for tracking and learning about your own portfolio only. Speak to a qualified adviser before investing.
        """
    )


def _render_feature_mind_map() -> None:
    if _try_graphviz_mind_map():
        return
    st.markdown(_feature_mind_map_svg(), unsafe_allow_html=True)


def _render_data_flow_diagram() -> None:
    if _try_graphviz_flow():
        return
    st.markdown(_data_flow_svg(), unsafe_allow_html=True)


def _try_graphviz_mind_map() -> bool:
    if shutil.which("dot") is None:
        return False
    try:
        import graphviz
    except ImportError:
        return False
    graph = graphviz.Digraph("features", format="svg")
    graph.attr(
        rankdir="TB",
        bgcolor="transparent",
        fontname="Source Sans 3, sans-serif",
        pad="0.4",
    )
    graph.attr(
        "node",
        shape="box",
        style="rounded,filled",
        fillcolor=ROYAL_NODE,
        fontcolor=ROYAL_CREAM,
        color=ROYAL_GOLD,
        fontsize="11",
    )
    graph.attr("edge", color=ROYAL_GOLD, style="solid")
    graph.node("hub", "Your wealth dashboard", fillcolor="#1A1230", fontsize="12")
    for node_id, label in _mind_map_nodes():
        graph.node(node_id, label)
        graph.edge("hub", node_id)
    st.graphviz_chart(graph)
    return True


def _try_graphviz_flow() -> bool:
    if shutil.which("dot") is None:
        return False
    try:
        import graphviz
    except ImportError:
        return False
    graph = graphviz.Digraph("flow", format="svg")
    graph.attr(
        rankdir="LR",
        bgcolor="transparent",
        fontname="Source Sans 3, sans-serif",
        nodesep="0.35",
    )
    graph.attr(
        "node",
        shape="box",
        style="rounded,filled",
        fillcolor=ROYAL_NODE,
        fontcolor=ROYAL_CREAM,
        color=ROYAL_GOLD,
        fontsize="10",
    )
    graph.attr("edge", color=ROYAL_GOLD, style="dashed", penwidth="1.4")
    steps = [
        ("s1", "Zerodha Console\n(CSV / Excel exports)"),
        ("s2", "Upload in the app\n(or try demo)"),
        ("s3", "We calculate\nvalue, P&L, XIRR"),
        ("s4", "Compare vs peers\n& Nifty (AMFI,\nmfapi.in, yfinance)"),
        ("s5", "Charts &\nplain-English\ninsights"),
    ]
    for node_id, label in steps:
        graph.node(node_id, label)
    for left, right in zip(steps, steps[1:]):
        graph.edge(left[0], right[0])
    st.graphviz_chart(graph)
    return True


def _mind_map_nodes() -> list[tuple[str, str]]:
    return [
        ("portfolio", "Portfolio\n(holdings & benchmark)"),
        ("my_mf", "My Mutual Funds\n(your funds vs peers)"),
        ("top_mf", "Top Mutual Funds\n(category rankings)"),
        ("compare", "Fund comparison\n(side-by-side)"),
        ("research", "Stock Research\n(optional scores)"),
        ("data", "Data import\n& backup"),
    ]


def _feature_mind_map_svg() -> str:
    """Mobile-friendly SVG mind map (fallback when Graphviz is unavailable)."""
    return """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 420" width="100%" role="img"
  aria-label="Mind map of dashboard features">
  <defs>
    <style>
      .n { fill:#151B3B; stroke:#D4AF37; stroke-width:1.2; }
      .t { fill:#F5F0E6; font-family:Source Sans 3,Segoe UI,sans-serif; font-size:13px; }
      .hub { fill:#1A1230; stroke:#F0D78C; stroke-width:1.5; }
      .l { stroke:#D4AF37; stroke-width:1.2; fill:none; }
    </style>
  </defs>
  <rect class="hub" x="260" y="175" width="200" height="52" rx="10"/>
  <text class="t" x="360" y="205" text-anchor="middle" font-weight="600">Your wealth dashboard</text>
  <line class="l" x1="360" y1="175" x2="120" y2="70"/>
  <rect class="n" x="40" y="40" width="160" height="52" rx="8"/>
  <text class="t" x="120" y="70" text-anchor="middle">Portfolio</text>
  <line class="l" x1="360" y1="175" x2="360" y2="55"/>
  <rect class="n" x="280" y="25" width="160" height="52" rx="8"/>
  <text class="t" x="360" y="55" text-anchor="middle">My Mutual Funds</text>
  <line class="l" x1="460" y1="175" x2="600" y2="70"/>
  <rect class="n" x="520" y="40" width="160" height="52" rx="8"/>
  <text class="t" x="600" y="70" text-anchor="middle">Top Mutual Funds</text>
  <line class="l" x1="360" y1="227" x2="120" y2="330"/>
  <rect class="n" x="40" y="300" width="160" height="52" rx="8"/>
  <text class="t" x="120" y="330" text-anchor="middle">Fund comparison</text>
  <line class="l" x1="360" y1="227" x2="360" y2="345"/>
  <rect class="n" x="270" y="315" width="180" height="52" rx="8"/>
  <text class="t" x="360" y="345" text-anchor="middle">Stock Research</text>
  <line class="l" x1="460" y1="227" x2="600" y2="330"/>
  <rect class="n" x="520" y="300" width="160" height="52" rx="8"/>
  <text class="t" x="600" y="330" text-anchor="middle">Import &amp; backup</text>
</svg>
"""


def _data_flow_svg() -> str:
    return """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 200" width="100%" role="img"
  aria-label="Data flow from Zerodha to insights">
  <defs>
    <style>
      .b { fill:#151B3B; stroke:#D4AF37; stroke-width:1.2; }
      .tx { fill:#F5F0E6; font-family:Source Sans 3,Segoe UI,sans-serif; font-size:11px; }
      .d { stroke:#D4AF37; stroke-width:1.5; stroke-dasharray:6 4; fill:none; marker-end:url(#arrow); }
    </style>
    <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
      <path d="M0,0 L6,3 L0,6 Z" fill="#D4AF37"/>
    </marker>
  </defs>
  <rect class="b" x="10" y="60" width="130" height="80" rx="8"/>
  <text class="tx" x="75" y="92" text-anchor="middle">Zerodha Console</text>
  <text class="tx" x="75" y="110" text-anchor="middle" fill="#B8B2C8">CSV / Excel</text>
  <path class="d" d="M 145 100 L 175 100"/>
  <rect class="b" x="180" y="60" width="120" height="80" rx="8"/>
  <text class="tx" x="240" y="100" text-anchor="middle">Upload here</text>
  <path class="d" d="M 305 100 L 335 100"/>
  <rect class="b" x="340" y="55" width="130" height="90" rx="8"/>
  <text class="tx" x="405" y="88" text-anchor="middle">App calculates</text>
  <text class="tx" x="405" y="106" text-anchor="middle" fill="#B8B2C8">P&amp;L, XIRR</text>
  <path class="d" d="M 475 100 L 505 100"/>
  <rect class="b" x="510" y="45" width="150" height="110" rx="8"/>
  <text class="tx" x="585" y="82" text-anchor="middle">Compare peers</text>
  <text class="tx" x="585" y="100" text-anchor="middle" fill="#B8B2C8">AMFI, mfapi.in</text>
  <text class="tx" x="585" y="118" text-anchor="middle" fill="#B8B2C8">yfinance / Nifty</text>
  <path class="d" d="M 665 100 L 695 100"/>
  <rect class="b" x="700" y="60" width="130" height="80" rx="8"/>
  <text class="tx" x="765" y="92" text-anchor="middle">Charts &amp;</text>
  <text class="tx" x="765" y="110" text-anchor="middle">insights</text>
</svg>
"""
