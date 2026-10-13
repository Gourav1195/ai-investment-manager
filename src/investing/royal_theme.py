"""Royal premium styling for the Streamlit wealth dashboard."""

from __future__ import annotations

import streamlit as st

from .friendly_copy import TERM_HELP

GOOGLE_FONTS = (
    "https://fonts.googleapis.com/css2?"
    "family=Cinzel:wght@500;600;700&family=Playfair+Display:wght@500;600;700&"
    "family=Source+Sans+3:wght@400;500;600;700&display=swap"
)

ROYAL_CSS = """
<style>
@import url('GOOGLE_FONTS_PLACEHOLDER');

:root {
  --royal-navy: #0b1026;
  --royal-purple: #1a1230;
  --royal-panel: #151b3b;
  --royal-gold: #d4af37;
  --royal-gold-soft: #f0d78c;
  --royal-cream: #f5f0e6;
  --royal-muted: #b8b2c8;
  --royal-up: #3dd68c;
  --royal-down: #ff6b7a;
}

html, body, [class*="css"] {
  font-family: "Source Sans 3", "Segoe UI", sans-serif;
  font-size: 17px;
}

[data-testid="stMetricValue"] {
  font-size: 1.35rem !important;
}

div[data-testid="stButton"] > button {
  min-height: 2.85rem;
  font-size: 1.05rem;
  font-weight: 600;
  border-radius: 10px;
}

div[data-testid="stButton"] > button[kind="primary"] {
  background: linear-gradient(135deg, #d4af37 0%, #b8922e 100%);
  color: #0b1026;
  border: 1px solid #f0d78c;
}

div[data-testid="stButton"] > button[kind="primary"]:hover {
  border-color: #fff;
  color: #0b1026;
}

.royal-onboarding-badge {
  display: inline-block;
  background: rgba(212, 175, 55, 0.15);
  border: 1px solid rgba(212, 175, 55, 0.5);
  color: #f0d78c;
  padding: 0.35rem 0.75rem;
  border-radius: 999px;
  font-size: 0.9rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.royal-onboarding-badge--done {
  background: rgba(61, 214, 140, 0.12);
  border-color: rgba(61, 214, 140, 0.45);
  color: #9ef0c8;
}

.royal-tooltip-label {
  cursor: help;
  border-bottom: 1px dotted rgba(212, 175, 55, 0.6);
}

.royal-friendly-error {
  background: rgba(255, 107, 122, 0.12);
  border: 1px solid rgba(255, 107, 122, 0.45);
  border-radius: 12px;
  padding: 1rem 1.25rem;
  color: #ffe8ec;
  font-size: 1.05rem;
  margin: 1rem 0;
}

h1, h2, h3, .royal-title {
  font-family: "Playfair Display", "Cinzel", Georgia, serif !important;
  letter-spacing: 0.02em;
}

[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #0b1026 0%, #1a1230 55%, #151b3b 100%);
  border-right: 1px solid rgba(212, 175, 55, 0.25);
}

[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
  color: var(--royal-gold-soft) !important;
}

.royal-welcome {
  padding: 0.25rem 0 0.75rem 0;
  border-bottom: 1px solid rgba(212, 175, 55, 0.2);
  margin-bottom: 0.75rem;
}

.royal-welcome h2 {
  margin: 0;
  font-size: 1.35rem;
  color: var(--royal-gold-soft);
}

.royal-welcome p {
  margin: 0.15rem 0 0 0;
  color: var(--royal-muted);
  font-size: 0.95rem;
}

.royal-hero {
  background: linear-gradient(135deg, #1a1230 0%, #151b3b 45%, #0b1026 100%);
  border: 1px solid rgba(212, 175, 55, 0.45);
  border-radius: 16px;
  padding: 1.25rem 1.5rem 1rem 1.5rem;
  margin-bottom: 1rem;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
}

.royal-hero h2 {
  margin: 0 0 0.75rem 0;
  font-size: 1.5rem;
  color: var(--royal-gold);
}

.royal-metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0.75rem;
}

.royal-metric-card {
  background: rgba(11, 16, 38, 0.65);
  border: 1px solid rgba(212, 175, 55, 0.35);
  border-radius: 12px;
  padding: 0.85rem 1rem;
}

.royal-metric-label {
  font-size: 0.85rem;
  letter-spacing: 0.04em;
  color: var(--royal-muted);
  margin-bottom: 0.25rem;
}

.royal-metric-value {
  font-size: 1.55rem;
  font-weight: 600;
  color: var(--royal-cream);
  line-height: 1.2;
}

.royal-metric-delta {
  font-size: 0.85rem;
  margin-top: 0.2rem;
}

.royal-up { color: var(--royal-up); }
.royal-down { color: var(--royal-down); }

.royal-insights {
  margin-top: 0.85rem;
  padding-top: 0.75rem;
  border-top: 1px dashed rgba(212, 175, 55, 0.25);
}

.royal-insights li {
  color: var(--royal-cream);
  margin-bottom: 0.35rem;
}

.royal-empty {
  text-align: center;
  padding: 2rem 1.25rem;
  border-radius: 16px;
  border: 1px dashed rgba(212, 175, 55, 0.35);
  background: rgba(21, 27, 59, 0.55);
  margin: 0.5rem 0 1rem 0;
}

.royal-empty-icon {
  font-size: 2.5rem;
  line-height: 1;
  margin-bottom: 0.5rem;
}

.royal-empty h3 {
  color: var(--royal-gold-soft);
  margin: 0.25rem 0;
}

.royal-empty p {
  color: var(--royal-muted);
  max-width: 32rem;
  margin: 0 auto;
}

.royal-section-title {
  font-family: "Playfair Display", serif;
  color: var(--royal-gold-soft);
  margin-top: 0.5rem;
}

.royal-disclaimer {
  color: var(--royal-muted);
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
}

.royal-persistence-badge {
  font-size: 0.9rem;
  padding: 0.5rem 0.75rem;
  border-radius: 8px;
  margin-bottom: 0.75rem;
  border: 1px solid rgba(212, 175, 55, 0.25);
}

.royal-persistence-cloud {
  background: rgba(61, 214, 140, 0.12);
  color: var(--royal-cream);
}

.royal-persistence-temp {
  background: rgba(184, 178, 200, 0.12);
  color: var(--royal-muted);
}

.royal-persistence-warn {
  background: rgba(255, 107, 122, 0.12);
  color: var(--royal-cream);
}

.royal-sidebar-nav-title {
  font-family: "Playfair Display", serif;
  color: var(--royal-gold-soft);
  font-size: 1rem;
  font-weight: 600;
  margin: 0.5rem 0 0.25rem 0;
}

section[data-testid="stSidebar"] div[data-testid="stRadio"] {
  max-height: 15rem;
  overflow-y: auto;
  padding-right: 0.25rem;
}

section[data-testid="stSidebar"] div[data-testid="stRadio"] label p {
  font-size: 0.95rem;
  font-weight: 500;
}

[data-testid="stTabs"] [data-baseweb="tab-list"] {
  flex-wrap: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
  -webkit-overflow-scrolling: touch;
  gap: 0.15rem;
  padding-bottom: 0.25rem;
}

[data-testid="stTabs"] [data-baseweb="tab"] {
  white-space: nowrap;
  flex-shrink: 0;
}

@media (max-width: 768px) {
  html, body, [class*="css"] { font-size: 16px; }
  .royal-hero { padding: 1rem; }
  .royal-metric-value { font-size: 1.25rem; }
  .royal-metric-grid { grid-template-columns: 1fr 1fr; }
  [data-testid="stTabs"] button { font-size: 0.8rem; padding: 0.45rem 0.3rem; }
}
</style>
""".replace("GOOGLE_FONTS_PLACEHOLDER", GOOGLE_FONTS)


PLOTLY_LAYOUT = {
    "paper_bgcolor": "rgba(11,16,38,0)",
    "plot_bgcolor": "rgba(21,27,59,0.6)",
    "font": {"color": "#F5F0E6", "family": "Source Sans 3, sans-serif"},
    "colorway": ["#D4AF37", "#9B7EDE", "#5EC4FF", "#3DD68C", "#FF6B7A", "#F0D78C"],
    "xaxis": {"gridcolor": "rgba(212,175,55,0.15)", "zerolinecolor": "rgba(212,175,55,0.2)"},
    "yaxis": {"gridcolor": "rgba(212,175,55,0.15)", "zerolinecolor": "rgba(212,175,55,0.2)"},
    "legend": {"bgcolor": "rgba(11,16,38,0.5)", "bordercolor": "rgba(212,175,55,0.3)"},
}


def apply_royal_theme() -> None:
    st.markdown(ROYAL_CSS, unsafe_allow_html=True)


def render_welcome_header(display_name: str) -> None:
    greeting = f"Welcome back, {display_name}" if display_name else "Welcome to your wealth home"
    st.markdown(
        f"""
        <div class="royal-welcome">
          <h2>👑 {greeting}</h2>
          <p>Your Zerodha portfolio and mutual funds, explained in plain English.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_wealth_hero(
    *,
    total_value: float | None,
    total_pnl: float | None,
    xirr: float | None,
    today_change: float | None,
    today_change_pct: float | None,
    insights: list[str],
) -> None:
    value_html = _money_html(total_value)
    pnl_html, pnl_class = _signed_money(total_pnl)
    xirr_html = f"{xirr * 100:.2f}%" if xirr is not None else "—"
    today_html, today_class = _signed_money(today_change, today_change_pct)

    insight_items = "".join(f"<li>{item}</li>" for item in insights) if insights else (
        "<li>Load your portfolio or try the demo to see personalised insights here.</li>"
    )

    st.markdown(
        f"""
        <div class="royal-hero">
          <h2>Your wealth at a glance</h2>
          <div class="royal-metric-grid">
            <div class="royal-metric-card">
              <div class="royal-metric-label royal-tooltip-label" title="What your stocks and mutual funds are worth right now.">Total value today</div>
              <div class="royal-metric-value">{value_html}</div>
            </div>
            <div class="royal-metric-card">
              <div class="royal-metric-label royal-tooltip-label" title="{_esc(TERM_HELP['pnl'])}">Total profit or loss</div>
              <div class="royal-metric-value {pnl_class}">{pnl_html}</div>
            </div>
            <div class="royal-metric-card">
              <div class="royal-metric-label royal-tooltip-label" title="{_esc(TERM_HELP['xirr'])}">Annual return (XIRR)</div>
              <div class="royal-metric-value">{xirr_html}</div>
            </div>
            <div class="royal-metric-card">
              <div class="royal-metric-label royal-tooltip-label" title="Change since the previous trading day we could measure.">Change since yesterday</div>
              <div class="royal-metric-value {today_class}">{today_html}</div>
              <div class="royal-metric-delta {today_class}">{_pct_label(today_change_pct)}</div>
            </div>
          </div>
          <div class="royal-insights"><ul>{insight_items}</ul></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(icon: str, title: str, message: str) -> None:
    st.markdown(
        f"""
        <div class="royal-empty">
          <div class="royal-empty-icon">{icon}</div>
          <h3>{title}</h3>
          <p>{message}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def style_plotly_figure(fig):
    fig.update_layout(**PLOTLY_LAYOUT)
    return fig


def render_term_glossary() -> None:
    with st.expander("What do these words mean?", expanded=False):
        for key, label in (
            ("xirr", "Annual return (XIRR)"),
            ("cagr", "Average yearly growth (CAGR)"),
            ("nav", "Fund unit price (NAV)"),
            ("benchmark", "Market comparison (benchmark)"),
        ):
            st.markdown(f"**{label}** — {TERM_HELP[key]}")


def render_friendly_error(message: str) -> None:
    st.markdown(
        f'<div class="royal-friendly-error"><strong>We hit a snag</strong><br>{_esc(message)}</div>',
        unsafe_allow_html=True,
    )


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _money_html(value: float | None) -> str:
    if value is None:
        return "—"
    return f"₹{value:,.0f}"


def _signed_money(value: float | None, pct: float | None = None) -> tuple[str, str]:
    if value is None:
        return "—", ""
    css = "royal-up" if value >= 0 else "royal-down"
    sign = "+" if value >= 0 else "−"
    text = f"{sign}₹{abs(value):,.0f}"
    if pct is not None:
        text += f" ({_pct_label(pct)})"
    return text, css


def _pct_label(pct: float | None) -> str:
    if pct is None:
        return ""
    sign = "+" if pct >= 0 else "−"
    return f"{sign}{abs(pct) * 100:.2f}%"
