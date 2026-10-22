"""Import CAMS / KFintech consolidated account statement exports."""

from __future__ import annotations

from pathlib import Path
import re

import pandas as pd

from .zerodha_import import load_zerodha_table

CAS_TRANSACTION_ALIASES = {
    "txn_date": ("date", "transaction date", "trxn date"),
    "scheme_name": ("scheme", "scheme name", "fund name", "mutual fund"),
    "scheme_code": ("amfi", "amfi code", "scheme code", "rta code"),
    "txn_type": ("transaction type", "trxn type", "description", "transaction description"),
    "amount": ("amount", "transaction amount"),
    "units": ("units", "quantity", "trxn units"),
    "nav": ("nav", "price", "purchase price"),
    "folio": ("folio", "folio no"),
    "amc": ("amc", "fund house"),
}


def parse_cas_transactions_table(path: str | Path) -> pd.DataFrame:
    """Parse CAS CSV/Excel (e.g. casparser ``output=csv``) into mf_transactions shape."""

    frame = load_zerodha_table(path)
    normalized = frame.copy()
    normalized.columns = [
        re.sub(r"\s+", " ", str(column).strip().lower()) for column in normalized.columns
    ]
    mapping: dict[str, str] = {}
    for canonical, aliases in CAS_TRANSACTION_ALIASES.items():
        for column in normalized.columns:
            if column in aliases:
                mapping[column] = canonical
                break
    missing = {"txn_date", "scheme_name", "amount"} - set(mapping.values())
    if missing:
        raise ValueError(
            "CAS file missing required columns. Export detailed CAS as CSV "
            f"(missing: {sorted(missing)})."
        )
    data = normalized.rename(columns={key: value for key, value in mapping.items()})
    rows: list[dict[str, object]] = []
    for record in data.to_dict(orient="records"):
        scheme = str(record.get("scheme_name") or "").strip()
        if not scheme:
            continue
        txn_date = _normalize_date(record.get("txn_date"))
        if not txn_date:
            continue
        try:
            amount = float(record.get("amount"))
        except (TypeError, ValueError):
            continue
        txn_type = _cas_txn_type(str(record.get("txn_type") or ""))
        code = str(record.get("scheme_code") or "").strip() or None
        units = record.get("units")
        nav = record.get("nav")
        rows.append(
            {
                "txn_date": txn_date,
                "scheme_name": scheme,
                "scheme_code": code if code and code.isdigit() else None,
                "txn_type": txn_type,
                "amount": abs(amount),
                "units": float(units) if units is not None and not pd.isna(units) else None,
                "nav": float(nav) if nav is not None and not pd.isna(nav) else None,
            }
        )
    if not rows:
        raise ValueError("No transactions found in CAS file.")
    return pd.DataFrame(rows)


def parse_cas_pdf(path: str | Path, password: str) -> pd.DataFrame:
    """Parse original CAMS/KFintech CAS PDF when ``casparser`` is installed."""

    try:
        import casparser
    except ImportError as error:
        raise RuntimeError(
            "PDF CAS import needs the optional casparser package. "
            "Use a CSV export from casparser, or add casparser to your environment."
        ) from error
    data = casparser.read_cas_pdf(str(path), password)
    rows: list[dict[str, object]] = []
    for folio in data.folios:
        for scheme in folio.schemes:
            for txn in scheme.transactions:
                rows.append(
                    {
                        "txn_date": txn.date.isoformat(),
                        "scheme_name": scheme.scheme,
                        "scheme_code": None,
                        "txn_type": _cas_txn_type(txn.description),
                        "amount": float(txn.amount),
                        "units": float(txn.units) if txn.units is not None else None,
                        "nav": float(txn.nav) if txn.nav is not None else None,
                    }
                )
    if not rows:
        raise ValueError("CAS PDF contained no transactions.")
    return pd.DataFrame(rows)


def _cas_txn_type(description: str) -> str:
    text = description.lower()
    if "sip" in text or "systematic" in text:
        return "sip"
    if "redemption" in text or "sell" in text or "withdraw" in text:
        return "redemption"
    if "purchase" in text or "buy" in text:
        return "purchase"
    if "dividend" in text:
        return "dividend"
    return "purchase"


def _normalize_date(value: object) -> str | None:
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            from datetime import datetime

            return datetime.strptime(text[:11], fmt).date().isoformat()
        except ValueError:
            continue
    return None
