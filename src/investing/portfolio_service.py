"""High-level portfolio import and sync operations."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .filings import IST
from .kite_client import KiteReadOnlyClient
from .kite_config import KiteCredentials, load_kite_credentials
from .portfolio_store import PortfolioStore
from .cas_import import parse_cas_pdf, parse_cas_transactions_table
from .mf_portfolio_disclosure import parse_portfolio_disclosure
from .zerodha_import import (
    parse_equity_holdings,
    parse_mf_holdings,
    parse_mf_transactions,
    parse_tradebook,
)

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples" / "zerodha_portfolio"


def _clear_legacy_demo_data(store: PortfolioStore) -> None:
    """Remove labelled sample data only after a real import has been parsed."""
    frames = (store.list_equity_holdings(), store.list_mf_holdings())
    only_demo = any(not frame.empty for frame in frames) and all(
        frame.empty or frame["source"].eq("example").all() for frame in frames
    )
    with store._connect() as connection:
        for table in ("equity_holdings", "mf_holdings", "equity_trades", "mf_transactions"):
            connection.execute(f"DELETE FROM {table} WHERE source = ?", ("example",))
        if only_demo:
            connection.execute("DELETE FROM price_cache")
            connection.execute("DELETE FROM nav_cache")


def import_equity_holdings_file(
    store: PortfolioStore,
    path: Path,
    *,
    source: str = "zerodha_csv",
) -> int:
    frame = parse_equity_holdings(path)
    if source != "example":
        _clear_legacy_demo_data(store)
    import_key = store.record_import(
        source=source,
        kind="equity_holdings",
        file_name=path.name,
        row_count=len(frame),
    )
    return store.replace_equity_holdings(frame, source=source, import_key=import_key)


def import_tradebook_file(
    store: PortfolioStore,
    path: Path,
    *,
    source: str = "zerodha_csv",
    replace_existing: bool = False,
) -> int:
    frame = parse_tradebook(path)
    if source != "example":
        _clear_legacy_demo_data(store)
    import_key = store.record_import(
        source=source,
        kind="tradebook",
        file_name=path.name,
        row_count=len(frame),
    )
    return store.append_equity_trades(
        frame,
        source=source,
        import_key=import_key,
        replace_existing=replace_existing,
    )


def import_mf_holdings_file(
    store: PortfolioStore,
    path: Path,
    *,
    source: str = "zerodha_csv",
) -> int:
    frame = parse_mf_holdings(path)
    if source != "example":
        _clear_legacy_demo_data(store)
    import_key = store.record_import(
        source=source,
        kind="mf_holdings",
        file_name=path.name,
        row_count=len(frame),
    )
    return store.replace_mf_holdings(frame, source=source, import_key=import_key)


def import_mf_transactions_file(
    store: PortfolioStore,
    path: Path,
    *,
    source: str = "zerodha_csv",
    replace_existing: bool = False,
) -> int:
    frame = parse_mf_transactions(path)
    if source != "example":
        _clear_legacy_demo_data(store)
    import_key = store.record_import(
        source=source,
        kind="mf_transactions",
        file_name=path.name,
        row_count=len(frame),
    )
    return store.append_mf_transactions(
        frame,
        source=source,
        import_key=import_key,
        replace_existing=replace_existing,
    )


def import_cas_transactions_file(
    store: PortfolioStore,
    path: Path,
    *,
    password: str | None = None,
    source: str = "cas",
    replace_existing: bool = False,
) -> int:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        if not password:
            raise ValueError("CAS PDF import requires the PDF password.")
        frame = parse_cas_pdf(path, password)
    else:
        frame = parse_cas_transactions_table(path)
    if source != "example":
        _clear_legacy_demo_data(store)
    import_key = store.record_import(
        source=source,
        kind="cas_transactions",
        file_name=path.name,
        row_count=len(frame),
    )
    return store.append_mf_transactions(
        frame,
        source=source,
        import_key=import_key,
        replace_existing=replace_existing,
    )


def import_mf_portfolio_disclosure_file(
    store: PortfolioStore,
    path: Path,
    *,
    scheme_code: str | None = None,
    source: str = "mf_disclosure",
) -> int:
    frame, as_of = parse_portfolio_disclosure(path)
    codes = (
        {str(value).strip() for value in frame["scheme_code"].dropna().tolist() if str(value).strip()}
        if "scheme_code" in frame.columns
        else set()
    )
    if scheme_code:
        codes = {str(scheme_code).strip()}
    if len(codes) > 1:
        raise ValueError("Upload one scheme per disclosure file (multiple scheme codes found).")
    code = next(iter(codes)) if codes else None
    if not code:
        raise ValueError(
            "Could not determine AMFI scheme code. Add a Scheme Code column or pass scheme_code=."
        )
    as_of_date = as_of or datetime.now(tz=IST).date().isoformat()
    if source != "example":
        _clear_legacy_demo_data(store)
    import_key = store.record_import(
        source=source,
        kind="mf_portfolio_disclosure",
        file_name=path.name,
        row_count=len(frame),
    )
    return store.replace_mf_disclosure_holdings(
        code,
        as_of_date,
        frame,
        source=source,
        import_key=import_key,
    )


def sync_kite_holdings(
    store: PortfolioStore,
    *,
    kite_config: Path | None = None,
    credentials: KiteCredentials | None = None,
) -> tuple[int, int]:
    client = KiteReadOnlyClient(credentials or load_kite_credentials(kite_config))
    equity = client.equity_holdings_frame()
    mf = client.mf_holdings_frame()
    # Resolve a code only when the cached AMFI name identifies one unique scheme.
    master = store._read_table("mf_scheme_master")
    if not mf.empty and not master.empty:
        for index, row in mf.iterrows():
            if str(row["scheme_code"]).isdigit():
                continue
            name = str(row["scheme_name"]).strip().casefold()
            matches = master[master["scheme_name"].astype(str).str.strip().str.casefold() == name]
            if len(matches) == 1:
                mf.at[index, "scheme_code"] = str(matches.iloc[0]["scheme_code"])
    _clear_legacy_demo_data(store)
    equity_key = store.record_import(
        source="kite_api",
        kind="equity_holdings",
        file_name="kite:/portfolio/holdings",
        row_count=len(equity),
    )
    mf_key = store.record_import(
        source="kite_api",
        kind="mf_holdings",
        file_name="kite:/mf/holdings",
        row_count=len(mf),
    )
    equity_rows = store.replace_equity_holdings(
        equity, source="kite_api", import_key=equity_key
    )
    mf_rows = store.replace_mf_holdings(mf, source="kite_api", import_key=mf_key)
    from .portfolio_pricing import cache_stock_prices, cache_navs

    stock_prices = {
        str(row["symbol"]): float(row["last_price"])
        for row in equity.to_dict(orient="records")
        if row.get("last_price") is not None and float(row["last_price"]) > 0
    }
    navs = {
        str(row["scheme_code"]): float(row["last_price"])
        for row in mf.to_dict(orient="records")
        if row.get("scheme_code") and row.get("last_price") is not None and float(row["last_price"]) > 0
    }
    cache_stock_prices(store, stock_prices)
    cache_navs(store, navs)
    return equity_rows, mf_rows


def load_example_portfolio(store: PortfolioStore) -> dict[str, int]:
    counts = {
        "equity_holdings": import_equity_holdings_file(
            store, EXAMPLES_DIR / "equity_holdings.example.csv", source="example"
        ),
        "tradebook": import_tradebook_file(
            store,
            EXAMPLES_DIR / "tradebook.example.csv",
            source="example",
            replace_existing=True,
        ),
        "mf_holdings": import_mf_holdings_file(
            store, EXAMPLES_DIR / "mf_holdings.example.csv", source="example"
        ),
        "mf_transactions": import_mf_transactions_file(
            store,
            EXAMPLES_DIR / "mf_transactions.example.csv",
            source="example",
            replace_existing=True,
        ),
    }
    return counts
