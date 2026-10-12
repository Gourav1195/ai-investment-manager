"""High-level portfolio import and sync operations."""

from __future__ import annotations

from pathlib import Path

from .kite_client import KiteReadOnlyClient
from .kite_config import load_kite_credentials
from .portfolio_store import PortfolioStore
from .zerodha_import import parse_equity_holdings, parse_mf_holdings, parse_tradebook

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples" / "zerodha_portfolio"


def import_equity_holdings_file(
    store: PortfolioStore,
    path: Path,
    *,
    source: str = "zerodha_csv",
) -> int:
    frame = parse_equity_holdings(path)
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
    import_key = store.record_import(
        source=source,
        kind="mf_holdings",
        file_name=path.name,
        row_count=len(frame),
    )
    return store.replace_mf_holdings(frame, source=source, import_key=import_key)


def sync_kite_holdings(
    store: PortfolioStore,
    *,
    kite_config: Path | None = None,
) -> tuple[int, int]:
    client = KiteReadOnlyClient(load_kite_credentials(kite_config))
    equity = client.equity_holdings_frame()
    mf = client.mf_holdings_frame()
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
    }
    return counts
