# Stock-level mutual fund overlap

## Data source (honest limits)

SEBI requires AMCs to publish **monthly portfolio disclosures** (ISIN, % to NAV). There is **no stable free AMFI API** that returns full holdings for every scheme in this app’s CI environment.

This app therefore uses **user-uploaded** disclosure CSV/Excel files (`mf_portfolio_disclosure.py`), one scheme per file, stored in SQLite table `mf_disclosure_holdings`.

**Not included (yet):**

- Automatic download from every AMC website (URLs change; would need per-AMC scrapers).
- MF Central CAS (different format; CAS import covers transaction history, not underlying stock weights).
- Third-party holdings APIs that were tested and found unavailable (e.g. public mirror endpoints returning 404).

## Overlap metric (`mf_overlap.py`)

For each pair of schemes with cached disclosures:

- Keep equity-like ISINs (`INE…` or instrument type containing “equity”).
- Weight = `% to NAV` as a fraction of 1.
- **Overlap** = Σ min(wₐ, wᵦ) over shared ISINs (standard “duplicate exposure” measure).

UI: **Portfolio → Stock-level fund overlap** when ≥2 held funds have disclosure data.
