# Financial goals

Goals are stored in `ui_prefs.json` via `AppPreferences.get_investment_goals()` / `set_investment_goals()`. They are **not** tied to the portfolio SQLite file, so demo vs personal portfolio selection does not duplicate goal rows.

## Model

Each goal has `goal_id`, `name`, `target_inr`, and `target_date` (ISO date). Logic lives in `src/investing/portfolio_goals.py`.

## Progress math

The Portfolio page treats the **entire portfolio current value** as progress toward each goal (single-wallet assumption suitable for household net-worth targets).

- **Progress %** = `current_value / target_inr` (capped at 100% for the bar).
- **Annual return** for projections: portfolio XIRR when available, else 10% p.a.
- **Monthly SIP** added to projections: sum of inferred SIP amounts from MF transaction history (`portfolio_sip_calendar.monthly_sip_total`).
- **Projected value** at `target_date`: month-by-month compounding with `monthly_sip_inr` added each month.
- **Required monthly** savings: solves for the flat monthly contribution needed to reach `target_inr` given current value and the same return assumption.

Status labels (`On track`, `Behind`, etc.) compare projected value to 98% / 85% of the target.

## UI

`dashboard._render_investment_goals()` — expander on **Portfolio**, above holdings tables. Goal IDs are shown so users can remove a goal from the form.
