# CAMS / KFintech CAS import

## Supported inputs

| Format | Source |
|--------|--------|
| CSV / Excel | Detailed CAS export (e.g. from [casparser](https://github.com/codereverser/casparser) `output=csv`) |
| PDF | Original CAMS or KFintech mailback PDF + password (requires optional `casparser` package) |

**Not supported:** MF Central CAS template (different PDF layout), re-printed “Save as PDF” CAS files (casparser rejects flattened watermarks).

## Pipeline

`cas_import.parse_cas_transactions_table()` → normalised columns → `portfolio_service.import_cas_transactions_file()` → `mf_transactions` via `append_mf_transactions()` (same table as Zerodha Coin exports).

Transaction types are inferred from description text (`SIP`, `Purchase`, `Redemption`, etc.).

## UI

**Import & backup** → CAMS / KFintech CAS uploader. PDF password field is required for `.pdf` files.

Importing real CAS on a personal portfolio clears labelled `example` holdings per existing `portfolio_service._clear_legacy_demo_data` rules.
