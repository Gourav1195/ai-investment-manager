"""Parse Zerodha Console CSV/XLSX exports for holdings and tradebooks."""

from __future__ import annotations

from pathlib import Path
import re

import pandas as pd

EQUITY_HOLDINGS_ALIASES = {
    "symbol": ("symbol", "tradingsymbol", "trading symbol", "instrument"),
    "isin": ("isin",),
    "quantity": ("quantity", "qty", "net qty", "net quantity"),
    "average_price": (
        "average price",
        "avg. price",
        "avg price",
        "average_price",
        "buy avg",
        "buy average",
    ),
    "product": ("product", "product type"),
    "exchange": ("exchange",),
}

TRADEBOOK_ALIASES = {
    "trade_date": (
        "trade date",
        "trade_date",
        "order execution time",
        "execution time",
        "date",
    ),
    "symbol": ("symbol", "tradingsymbol", "trading symbol", "instrument"),
    "side": ("trade type", "transaction type", "type", "buy/sell", "side"),
    "quantity": ("quantity", "qty"),
    "price": ("price", "trade price", "average price"),
    "exchange": ("exchange",),
    "trade_id": ("trade id", "trade_id", "order id", "order_id"),
}

MF_HOLDINGS_ALIASES = {
    "scheme_name": (
        "scheme name",
        "scheme",
        "fund name",
        "mutual fund",
        "name",
    ),
    "scheme_code": ("scheme code", "amfi code", "code", "isin"),
    "folio": ("folio", "folio no", "folio no.", "folio number"),
    "units": ("units", "balance units", "closing units", "unit balance"),
    "average_nav": (
        "average nav",
        "avg nav",
        "average price",
        "avg. nav",
        "purchase nav",
    ),
}


def load_zerodha_table(path: str | Path) -> pd.DataFrame:
    """Load a CSV or XLSX export from Zerodha Console."""

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(file_path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(file_path)
    raise ValueError(f"Unsupported file type: {suffix}")


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    renamed = frame.copy()
    renamed.columns = [
        re.sub(r"\s+", " ", str(column).strip().lower()) for column in renamed.columns
    ]
    return renamed


def _map_columns(
    frame: pd.DataFrame,
    aliases: dict[str, tuple[str, ...]],
    *,
    required: tuple[str, ...],
) -> pd.DataFrame:
    normalized = _normalize_columns(frame)
    rename: dict[str, str] = {}
    for target, options in aliases.items():
        for option in options:
            if option in normalized.columns:
                rename[option] = target
                break
    missing = [key for key in required if key not in rename.values()]
    if missing:
        raise ValueError(
            f"Could not map required columns {missing}. Found: {list(normalized.columns)}"
        )
    mapped = normalized.rename(columns=rename)
    columns = [key for key in aliases if key in mapped.columns]
    return mapped[columns]


def parse_equity_holdings(path: str | Path) -> pd.DataFrame:
    raw = load_zerodha_table(path)
    frame = _map_columns(
        raw,
        EQUITY_HOLDINGS_ALIASES,
        required=("symbol", "quantity", "average_price"),
    )
    frame["symbol"] = frame["symbol"].map(_clean_symbol)
    frame["quantity"] = frame["quantity"].map(_to_float)
    frame["average_price"] = frame["average_price"].map(_to_float)
    frame = frame[frame["quantity"] > 0]
    return frame.reset_index(drop=True)


def parse_tradebook(path: str | Path) -> pd.DataFrame:
    raw = load_zerodha_table(path)
    frame = _map_columns(
        raw,
        TRADEBOOK_ALIASES,
        required=("trade_date", "symbol", "side", "quantity", "price"),
    )
    frame["symbol"] = frame["symbol"].map(_clean_symbol)
    frame["quantity"] = frame["quantity"].map(_to_float)
    frame["price"] = frame["price"].map(_to_float)
    frame["side"] = frame["side"].map(_normalize_side)
    frame["trade_date"] = frame["trade_date"].map(_normalize_trade_date)
    return frame.reset_index(drop=True)


def parse_mf_holdings(path: str | Path) -> pd.DataFrame:
    raw = load_zerodha_table(path)
    frame = _map_columns(
        raw,
        MF_HOLDINGS_ALIASES,
        required=("scheme_name", "units"),
    )
    frame["units"] = frame["units"].map(_to_float)
    if "average_nav" in frame.columns:
        frame["average_nav"] = frame["average_nav"].map(_optional_float)
    if "scheme_code" in frame.columns:
        frame["scheme_code"] = frame["scheme_code"].map(_clean_scheme_code)
    frame = frame[frame["units"] > 0]
    return frame.reset_index(drop=True)


def _clean_symbol(value: object) -> str:
    text = str(value).strip().upper()
    if text.endswith("-BE") or text.endswith("-EQ"):
        text = text.rsplit("-", 1)[0]
    return text


def _clean_scheme_code(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if text.isdigit():
        return text
    match = re.search(r"\b(\d{5,6})\b", text)
    return match.group(1) if match else None


def _to_float(value: object) -> float:
    if isinstance(value, str):
        value = value.replace(",", "").strip()
    return float(value)


def _optional_float(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return _to_float(value)


def _normalize_side(value: object) -> str:
    text = str(value).strip().lower()
    if text in {"buy", "b", "purchase"}:
        return "buy"
    if text in {"sell", "s", "sale"}:
        return "sell"
    raise ValueError(f"Unrecognized trade side: {value}")


def _normalize_trade_date(value: object) -> str:
    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Unrecognized trade date: {value}")
    return parsed.date().isoformat()
