# SIP calendar inference

Zerodha exports label recurring purchases as `SIP` in MF transaction history. The app does **not** call the broker for future debits; it infers schedules locally.

## Algorithm (`portfolio_sip_calendar.py`)

1. Filter `mf_transactions` where `txn_type` is `sip` (case-insensitive).
2. Group by `(scheme_code, scheme_name)`.
3. **Debit day**: mode of calendar day-of-month across historical SIP dates.
4. **Amount**: median SIP amount in that group.
5. **Upcoming dates**: from `as_of`, walk monthly using the debit day, clamping to the last day of short months (e.g. day 31 → 30 Apr).

The Portfolio page shows the next **90 days** in **Upcoming SIP calendar**. Amounts are indicative (median of history).

## Change detection & overrides

See [sip_change_detection.md](sip_change_detection.md). Recent amount/day shifts are flagged; manual overrides in `ui_prefs.json` override inferred schedules for the calendar and goals.

## Limitations

- Funds with only lump-sum `Purchase` rows do not appear in the calendar unless you add a manual override.
- Equity SIPs (if exported separately) are out of scope until parsed into the same table.
