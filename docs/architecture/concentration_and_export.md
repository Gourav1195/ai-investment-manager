# Concentration insights and portfolio export

## Concentration (`portfolio_concentration.py`)

Uses the combined holdings frame from `build_portfolio_summary` (already has `allocation_pct`).

- **Top holdings** table: largest positions by `current_value`.
- **Insights**: flags when a single name ≥ 25% of portfolio, or top 3 ≥ 60%, and coarse equity weight messages (≥90% or ≤20% equity).
- **MF category table**: sums MF `current_value` by AMFI category from `PortfolioStore.get_scheme_meta` — a practical overlap proxy (many flexi-cap funds in one category).

Displayed on **Portfolio** after asset allocation.

## Report export (`portfolio_report_export.py`)

`build_portfolio_report_zip()` writes a ZIP of CSV files:

- Holdings (equity, MF, combined), totals, optional MF XIRR and SIP history
- Concentration and category breakdown
- Upcoming SIP calendar (when schedules exist)
- Goal progress rows (when goals are saved in prefs)
- FIFO capital-gains tables when trade/MF data allows

Triggered by **Download portfolio report** on the Portfolio page. No external PDF service; users can open CSVs in Excel or Google Sheets.
