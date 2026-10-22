# SIP change detection and manual overrides

## Change detection (`detect_sip_changes`)

Operates on SIP-labelled rows in `mf_transactions`.

Per fund (scheme code + name):

- **Amount change**: median of last 2 SIP amounts vs median of earlier SIPs; flag if relative change ≥ 10%.
- **Debit day change**: mode of calendar day in last 2 SIPs vs mode of earlier SIPs.

Shown on **Portfolio** when any flags exist.

## Manual overrides (`AppPreferences.sip_schedule_overrides`)

JSON list: `scheme_name`, optional `scheme_code`, `day_of_month`, `amount_inr`, `enabled`.

`resolve_sip_schedules()` merges inferred schedules with overrides; manual rows replace inferred ones for the same fund name. Disabled overrides remove the fund from the calendar.

Used for:

- Upcoming SIP calendar
- Financial goal projections (monthly SIP total)
- Portfolio ZIP export SIP section

Overrides are stored in `ui_prefs.json` (not the portfolio DB), same as financial goals.
