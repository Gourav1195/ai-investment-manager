# Per-stock XIRR

Logic in `portfolio_analytics.build_equity_holding_xirr_table()`.

For each equity holding with at least one tradebook row:

1. Filter `equity_trades` to that symbol (case-insensitive).
2. Build cash flows: buys negative, sells positive (`compute_portfolio_xirr` on the subset).
3. Terminal flow on `as_of` = current holding **market value** (quantity × saved price).

Displayed on **Portfolio** under the stocks table when a tradebook exists. Requires saved prices ( **Update prices & charts** ) for terminal value.

Same Newton–Raphson XIRR as portfolio-level and per-fund MF XIRR.
