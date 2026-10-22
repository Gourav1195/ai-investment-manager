"""Parse SEBI-style monthly MF portfolio disclosure Excel/CSV files."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd

DISCLOSURE_COLUMN_ALIASES = {
    "isin": ("isin",),
    "security_name": (
        "company/issuer name",
        "company name",
        "issuer name",
        "name of the instrument",
        "name of instrument",
        "security name",
        "instrument",
    ),
    "pct_nav": (
        "% to nav",
        "% to net assets",
        "% to net asset",
        "% of net assets",
        "percent to nav",
        "pct to nav",
    ),
    "instrument_type": ("instrument type", "instrument", "asset class"),
    "as_of": ("as on", "as of", "portfolio date", "date"),
    "scheme_code": ("scheme code", "amfi code", "code"),
    "scheme_name": ("scheme name", "scheme", "fund name"),
}


def parse_portfolio_disclosure(path: str | Path) -> tuple[pd.DataFrame, str | None]:
    """
    Return holdings rows with isin, security_name, pct_nav, instrument_type, scheme_code, scheme_name, as_of.
    """

    file_path = Path(path)
    if file_path.suffix.lower() in {".xlsx", ".xls"}:
        frame = _read_excel_disclosure(file_path)
    else:
        frame = pd.read_csv(file_path)
    return _normalize_disclosure_frame(frame)


def _read_excel_disclosure(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, header=None)
    header_row = _find_header_row(raw)
    if header_row is None:
        return pd.read_excel(path)
    return pd.read_excel(path, header=header_row)


def _find_header_row(frame: pd.DataFrame) -> int | None:
    for index, row in frame.iterrows():
        text = " ".join(str(value).lower() for value in row.tolist() if value is not None)
        if "isin" in text and ("nav" in text or "net asset" in text):
            return int(index)
    return None


def _normalize_disclosure_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, str | None]:
    renamed = frame.copy()
    renamed.columns = [
        re.sub(r"\s+", " ", str(column).strip().lower()) for column in renamed.columns
    ]
    mapping: dict[str, str] = {}
    for canonical, aliases in DISCLOSURE_COLUMN_ALIASES.items():
        for column in renamed.columns:
            if column in aliases:
                mapping[column] = canonical
                break
    if not mapping:
        raise ValueError("Could not find ISIN / % to NAV columns in portfolio disclosure file.")
    data = renamed.rename(columns=mapping)
    if "isin" not in data.columns or "pct_nav" not in data.columns:
        raise ValueError("Portfolio disclosure must include ISIN and % to NAV columns.")

    as_of: str | None = None
    if "as_of" in data.columns:
        for value in data["as_of"].dropna().tolist():
            parsed = _parse_as_of(value)
            if parsed:
                as_of = parsed
                break

    rows: list[dict[str, object]] = []
    file_scheme_code = _first_non_empty(data.get("scheme_code"))
    file_scheme_name = _first_non_empty(data.get("scheme_name"))
    for record in data.to_dict(orient="records"):
        isin = str(record.get("isin") or "").strip().upper()
        if not isin or isin in {"ISIN", "NAN"} or len(isin) < 10:
            continue
        try:
            pct = float(str(record.get("pct_nav")).replace("%", "").replace(",", "").strip())
        except (TypeError, ValueError):
            continue
        if pct <= 0 or pct > 100:
            continue
        name = str(record.get("security_name") or isin).strip()
        instrument = str(record.get("instrument_type") or "").strip()
        row_code = record.get("scheme_code") or file_scheme_code
        row_name = record.get("scheme_name") or file_scheme_name
        rows.append(
            {
                "isin": isin,
                "security_name": name,
                "pct_nav": pct / 100.0 if pct > 1.0 else pct,
                "instrument_type": instrument,
                "scheme_code": str(row_code).strip() if row_code else None,
                "scheme_name": str(row_name).strip() if row_name else None,
            }
        )
    if not rows:
        raise ValueError("No holdings rows with valid ISIN and % to NAV were found.")
    return pd.DataFrame(rows), as_of


def _first_non_empty(series: object) -> str | None:
    if series is None or not isinstance(series, pd.Series):
        return None
    for value in series.dropna().tolist():
        text = str(value).strip()
        if text:
            return text
    return None


def _parse_as_of(value: object) -> str | None:
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            from datetime import datetime

            return datetime.strptime(text[:12], fmt).date().isoformat()
        except ValueError:
            continue
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    return None
